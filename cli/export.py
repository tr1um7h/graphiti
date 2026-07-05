"""JSONL export with business key sorting.

Exports all 9 canonical tables (4 node + 5 edge) for a given group_id to
individual JSONL files, sorted by business keys for deterministic diffing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Embedding fields to compress (applies to any table that has them)
_EMBEDDING_FIELDS: frozenset[str] = frozenset({'name_embedding', 'fact_embedding'})

# Fields that must never appear in export output
_SKIP_FIELDS: frozenset[str] = frozenset({'search_vector'})


def format_embedding(vec: list[float] | None) -> list[float] | None:
    """Compress embedding vector to 6 decimal places."""
    if vec is None:
        return None
    return [round(f, 6) for f in vec]


def serialize_record(record: dict, table_name: str) -> dict:
    """Serialize a DB record for JSONL export.

    - Skips ``search_vector`` (GENERATED column)
    - Compresses embedding fields via :func:`format_embedding`
    - Converts ``datetime`` objects to ISO format strings
    """
    result: dict[str, Any] = {}

    for key, value in record.items():
        if key in _SKIP_FIELDS:
            continue
        if key in _EMBEDDING_FIELDS:
            result[key] = format_embedding(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# SQL queries — keyed by (schema placeholder, group_id placeholder)
# ---------------------------------------------------------------------------

# Node tables: simple ORDER BY on the table itself
_NODE_QUERIES: dict[str, str] = {
    'entity_nodes': (
        'SELECT * FROM {schema}.entity_nodes WHERE group_id = %(group_id)s ORDER BY name, labels'
    ),
    'episodic_nodes': (
        'SELECT * FROM {schema}.episodic_nodes '
        'WHERE group_id = %(group_id)s '
        'ORDER BY valid_at, md5(content)'
    ),
    'community_nodes': (
        'SELECT * FROM {schema}.community_nodes WHERE group_id = %(group_id)s ORDER BY name'
    ),
    'saga_nodes': ('SELECT * FROM {schema}.saga_nodes WHERE group_id = %(group_id)s ORDER BY name'),
}

# Edge tables: JOIN sorting via related node tables
_EDGE_QUERIES: dict[str, str] = {
    'entity_edges': (
        'SELECT e.* FROM {schema}.entity_edges e '
        'JOIN {schema}.entity_nodes src ON e.source_node_uuid = src.uuid '
        'JOIN {schema}.entity_nodes tgt ON e.target_node_uuid = tgt.uuid '
        'WHERE e.group_id = %(group_id)s '
        'ORDER BY src.name, tgt.name, e.name'
    ),
    'episodic_edges': (
        'SELECT e.* FROM {schema}.episodic_edges e '
        'JOIN {schema}.episodic_nodes ep ON e.source_node_uuid = ep.uuid '
        'JOIN {schema}.entity_nodes ent ON e.target_node_uuid = ent.uuid '
        'WHERE e.group_id = %(group_id)s '
        'ORDER BY md5(ep.content), ent.name'
    ),
    'community_edges': (
        'SELECT e.* FROM {schema}.community_edges e '
        'JOIN {schema}.community_nodes cm ON e.source_node_uuid = cm.uuid '
        'LEFT JOIN {schema}.entity_nodes ent ON e.target_node_uuid = ent.uuid '
        'WHERE e.group_id = %(group_id)s '
        "ORDER BY cm.name, COALESCE(ent.name, '')"
    ),
    'has_episode_edges': (
        'SELECT e.* FROM {schema}.has_episode_edges e '
        'JOIN {schema}.saga_nodes s ON e.source_node_uuid = s.uuid '
        'JOIN {schema}.episodic_nodes ep ON e.target_node_uuid = ep.uuid '
        'WHERE e.group_id = %(group_id)s '
        'ORDER BY s.name, md5(ep.content)'
    ),
    'next_episode_edges': (
        'SELECT e.* FROM {schema}.next_episode_edges e '
        'JOIN {schema}.episodic_nodes src ON e.source_node_uuid = src.uuid '
        'JOIN {schema}.episodic_nodes tgt ON e.target_node_uuid = tgt.uuid '
        'WHERE e.group_id = %(group_id)s '
        'ORDER BY md5(src.content), md5(tgt.content)'
    ),
}

# Ordered list: nodes first, then edges
_ALL_TABLES: list[str] = list(_NODE_QUERIES.keys()) + list(_EDGE_QUERIES.keys())


def _build_query(table_name: str, schema: str) -> str:
    """Format a query template with the concrete schema name."""
    queries = {**_NODE_QUERIES, **_EDGE_QUERIES}
    return queries[table_name].format(schema=schema)


async def export_group_with_sorting(
    driver: Any,
    group_id: str,
    schema: str,
    output_dir: Path,
) -> None:
    """Export all tables for a group to JSONL files with business key sorting.

    Creates one JSONL file per table plus a ``metadata.json`` summary.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    for table_name in _ALL_TABLES:
        query = _build_query(table_name, schema)
        records, _, _keys = await driver.execute_query(query, params={'group_id': group_id})

        serialized = [serialize_record(r, table_name) for r in records]

        jsonl_path = output_dir / f'{table_name}.jsonl'
        with jsonl_path.open('w', encoding='utf-8') as fh:
            for rec in serialized:
                fh.write(json.dumps(rec) + '\n')

        counts[table_name] = len(serialized)

    # Write metadata
    metadata = {
        'group_id': group_id,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'schema': schema,
        'embedding_dimension': driver.embedding_dimension,
        'schema_version': 1,
        'counts': counts,
    }
    metadata_path = output_dir / 'metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
