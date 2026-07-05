"""Semantic diff between two export directories.

Compares JSONL exports from two group_ids using business key matching and
produces a structured patch (JSON) describing added, removed, and modified
records across all 9 canonical tables.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# The 9 canonical tables in processing order
_ALL_TABLES: list[str] = [
    'entity_nodes',
    'episodic_nodes',
    'community_nodes',
    'saga_nodes',
    'entity_edges',
    'episodic_edges',
    'community_edges',
    'has_episode_edges',
    'next_episode_edges',
]

# Identity / reference fields that change between groups and must be ignored
# during field comparison and stripped from added/removed records.
_IGNORED_FIELDS: frozenset[str] = frozenset(
    {
        'uuid',
        'group_id',
        'source_node_uuid',
        'target_node_uuid',
        'episodes',
        'entity_edges',
        'first_episode_uuid',
        'last_episode_uuid',
        'created_at',
    }
)


def get_business_key(record: dict, table_name: str) -> tuple:
    """Extract the business key for a record based on its table type.

    Business keys are the minimal set of fields that uniquely identify a
    logical record independent of its UUID assignment.
    """
    if table_name == 'entity_nodes':
        labels = record.get('labels') or []
        return (record.get('name'), tuple(labels))

    if table_name == 'episodic_nodes':
        content = record.get('content', '')
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
        return (record.get('valid_at'), content_hash)

    if table_name in ('community_nodes', 'saga_nodes'):
        return (record.get('name'),)

    # Edge tables: use semantic fields (not UUIDs) for cross-group matching
    if table_name == 'entity_edges':
        return (
            record.get('source_name'),
            record.get('target_name'),
            record.get('name'),
        )

    if table_name == 'episodic_edges':
        return (
            record.get('source_content_hash'),
            record.get('target_name'),
        )

    if table_name == 'community_edges':
        return (
            record.get('source_name'),
            record.get('target_name'),
        )

    if table_name == 'has_episode_edges':
        return (
            record.get('source_name'),
            record.get('target_content_hash'),
        )

    if table_name == 'next_episode_edges':
        return (
            record.get('source_content_hash'),
            record.get('target_content_hash'),
        )

    # Fallback (should not be reached for canonical tables)
    return (record.get('source_node_uuid'), record.get('target_node_uuid'))


def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file into a list of records, skipping blank lines."""
    records: list[dict] = []
    with path.open('r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def build_index(records: list[dict], table_name: str) -> dict[tuple, dict]:
    """Build a business-key → record index. Last record wins on collision."""
    index: dict[tuple, dict] = {}
    for record in records:
        key = get_business_key(record, table_name)
        index[key] = record
    return index


def compare_fields(left: dict, right: dict) -> dict:
    """Compare two records field-by-field, ignoring identity fields.

    Returns a dict of ``{field_name: {'old': left_val, 'new': right_val}}``
    for every field that differs (and is not in :data:`_IGNORED_FIELDS`).
    """
    all_keys = set(left.keys()) | set(right.keys())
    changes: dict[str, dict] = {}

    for key in all_keys:
        if key in _IGNORED_FIELDS:
            continue
        old_val = left.get(key)
        new_val = right.get(key)
        if old_val != new_val:
            changes[key] = {'old': old_val, 'new': new_val}

    return changes


def extract_match_fields(record: dict, table_name: str) -> dict:
    """Extract the fields needed to identify a matched record in the patch.

    These correspond to the business key fields (using their original names
    rather than the hashed form for episodic nodes).
    """
    if table_name == 'entity_nodes':
        return {'name': record.get('name'), 'labels': record.get('labels')}

    if table_name == 'episodic_nodes':
        return {'valid_at': record.get('valid_at'), 'content': record.get('content')}

    if table_name in ('community_nodes', 'saga_nodes'):
        return {'name': record.get('name')}

    # Edge tables: use semantic fields (not UUIDs) for cross-group matching
    if table_name == 'entity_edges':
        return {
            'source_name': record.get('source_name'),
            'target_name': record.get('target_name'),
            'name': record.get('name'),
        }

    if table_name == 'episodic_edges':
        return {
            'source_content_hash': record.get('source_content_hash'),
            'target_name': record.get('target_name'),
        }

    if table_name == 'community_edges':
        return {
            'source_name': record.get('source_name'),
            'target_name': record.get('target_name'),
        }

    if table_name == 'has_episode_edges':
        return {
            'source_name': record.get('source_name'),
            'target_content_hash': record.get('target_content_hash'),
        }

    if table_name == 'next_episode_edges':
        return {
            'source_content_hash': record.get('source_content_hash'),
            'target_content_hash': record.get('target_content_hash'),
        }

    # Fallback (should not be reached for canonical tables)
    return {
        'source_node_uuid': record.get('source_node_uuid'),
        'target_node_uuid': record.get('target_node_uuid'),
    }


def _strip_ignored(record: dict) -> dict:
    """Return a copy of *record* without identity/reference fields."""
    return {k: v for k, v in record.items() if k not in _IGNORED_FIELDS}


def _read_metadata(input_dir: Path) -> dict:
    """Read metadata.json from an export directory."""
    metadata_path = input_dir / 'metadata.json'
    if not metadata_path.exists():
        return {}
    return json.loads(metadata_path.read_text(encoding='utf-8'))


def _diff_table(
    left_records: list[dict],
    right_records: list[dict],
    table_name: str,
) -> dict:
    """Diff a single table's records and return the change dict."""
    left_index = build_index(left_records, table_name)
    right_index = build_index(right_records, table_name)

    left_keys = set(left_index.keys())
    right_keys = set(right_index.keys())

    added: list[dict] = []
    removed: list[dict] = []
    modified: list[dict] = []
    conflicts: list[dict] = []

    # Added: in right but not in left
    for key in sorted(right_keys - left_keys, key=str):
        added.append(_strip_ignored(right_index[key]))

    # Removed: in left but not in right
    for key in sorted(left_keys - right_keys, key=str):
        removed.append(_strip_ignored(left_index[key]))

    # Modified: in both but with field differences
    for key in sorted(left_keys & right_keys, key=str):
        field_changes = compare_fields(left_index[key], right_index[key])
        if field_changes:
            modified.append(
                {
                    'match': extract_match_fields(right_index[key], table_name),
                    'fields': field_changes,
                }
            )

    return {
        'added': added,
        'removed': removed,
        'modified': modified,
        'conflicts': conflicts,
    }


def diff_groups(left_dir: Path, right_dir: Path) -> dict:
    """Compare two export directories and generate a semantic patch.

    Parameters
    ----------
    left_dir:
        Path to the "from" export directory (baseline).
    right_dir:
        Path to the "to" export directory (target state).

    Returns
    -------
    dict
        A patch document with version, metadata, and per-table changes.
    """
    left_meta = _read_metadata(left_dir)
    right_meta = _read_metadata(right_dir)

    from_group_id = left_meta.get('group_id', '')
    to_group_id = right_meta.get('group_id', '')

    changes: dict[str, dict] = {}

    for table_name in _ALL_TABLES:
        left_path = left_dir / f'{table_name}.jsonl'
        right_path = right_dir / f'{table_name}.jsonl'

        left_records = load_jsonl(left_path) if left_path.exists() else []
        right_records = load_jsonl(right_path) if right_path.exists() else []

        changes[table_name] = _diff_table(left_records, right_records, table_name)

    return {
        'version': 1,
        'metadata': {
            'from_group_id': from_group_id,
            'to_group_id': to_group_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
        'changes': changes,
    }
