"""UUID remapping core for import and apply workflows.

Two-phase approach:
  Phase 1: ``generate_uuid_mappings`` scans all JSONL files and pre-generates
           old_uuid -> new_uuid mapping so that every reference can be resolved.
  Phase 2: Per-table ``remap_*`` functions replace uuids and group_ids in
           individual records while preserving every other field unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


def generate_uuid_mappings(jsonl_files: list[Path]) -> dict[str, str]:
    """Pre-generate old_uuid -> new_uuid mapping for all records.

    Reads every JSONL file, extracts the ``uuid`` field from each record,
    and assigns a fresh UUID.  Duplicates (same uuid in multiple files) are
    mapped only once.
    """
    seen: set[str] = set()
    mapping: dict[str, str] = {}

    for file_path in jsonl_files:
        with file_path.open('r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                uuid_value = record.get('uuid')
                if uuid_value and uuid_value not in seen:
                    seen.add(uuid_value)
                    mapping[uuid_value] = str(uuid4())

    return mapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _remap_uuid(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Return a shallow copy with uuid and group_id remapped."""
    result = dict(record)
    result['uuid'] = uuid_map[record['uuid']]
    result['group_id'] = new_group_id
    return result


def _remap_edge_endpoints(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap uuid, group_id, source_node_uuid, target_node_uuid."""
    result = _remap_uuid(record, uuid_map, new_group_id)
    result['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    result['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    return result


# ---------------------------------------------------------------------------
# Per-table remap functions
# ---------------------------------------------------------------------------


def remap_entity_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap entity node: uuid, group_id only."""
    return _remap_uuid(record, uuid_map, new_group_id)


def remap_entity_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap entity edge: uuid, group_id, source/target, episodes[]."""
    result = _remap_edge_endpoints(record, uuid_map, new_group_id)
    result['episodes'] = [uuid_map[ep] for ep in record.get('episodes', [])]
    return result


def remap_episodic_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap episodic node: uuid, group_id, entity_edges[]."""
    result = _remap_uuid(record, uuid_map, new_group_id)
    result['entity_edges'] = [uuid_map[e] for e in record.get('entity_edges', [])]
    return result


def remap_episodic_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap episodic edge: uuid, group_id, source/target."""
    return _remap_edge_endpoints(record, uuid_map, new_group_id)


def remap_community_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap community node: uuid, group_id only."""
    return _remap_uuid(record, uuid_map, new_group_id)


def remap_community_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap community edge (polymorphic - source can be community or entity)."""
    return _remap_edge_endpoints(record, uuid_map, new_group_id)


def remap_saga_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap saga node with nullable episode references."""
    result = _remap_uuid(record, uuid_map, new_group_id)

    first_ep = record.get('first_episode_uuid')
    result['first_episode_uuid'] = uuid_map[first_ep] if first_ep is not None else None

    last_ep = record.get('last_episode_uuid')
    result['last_episode_uuid'] = uuid_map[last_ep] if last_ep is not None else None

    return result


def remap_has_episode_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap HAS_EPISODE edge: uuid, group_id, source/target."""
    return _remap_edge_endpoints(record, uuid_map, new_group_id)


def remap_next_episode_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap NEXT_EPISODE edge: uuid, group_id, source/target."""
    return _remap_edge_endpoints(record, uuid_map, new_group_id)
