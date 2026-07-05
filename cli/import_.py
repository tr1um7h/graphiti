"""JSONL import with UUID remapping and direct SQL INSERT.

Imports all 9 canonical tables from JSONL files exported by :mod:`cli.export`,
remapping UUIDs and group_ids to avoid collisions with existing data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli.remap import (
    generate_uuid_mappings,
    remap_community_edge,
    remap_community_node,
    remap_entity_edge,
    remap_entity_node,
    remap_episodic_edge,
    remap_episodic_node,
    remap_has_episode_edge,
    remap_next_episode_edge,
    remap_saga_node,
)

# Field that must never be inserted (GENERATED column)
_GENERATED_FIELDS: frozenset[str] = frozenset({'search_vector'})

# Table processing order respecting FK dependencies: nodes first, then edges.
_TABLE_ORDER: list[str] = [
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

# Mapping from table name to its remap function
_REMAP_FUNCTIONS: dict[str, Any] = {
    'entity_nodes': remap_entity_node,
    'episodic_nodes': remap_episodic_node,
    'community_nodes': remap_community_node,
    'saga_nodes': remap_saga_node,
    'entity_edges': remap_entity_edge,
    'episodic_edges': remap_episodic_edge,
    'community_edges': remap_community_edge,
    'has_episode_edges': remap_has_episode_edge,
    'next_episode_edges': remap_next_episode_edge,
}


def _read_metadata(input_dir: Path) -> dict:
    """Read and return metadata.json from the export directory."""
    metadata_path = input_dir / 'metadata.json'
    if not metadata_path.exists():
        raise FileNotFoundError(f'metadata.json not found in {input_dir}')
    return json.loads(metadata_path.read_text(encoding='utf-8'))


def _jsonify_values(record: dict) -> dict:
    """Serialize dict values to JSON strings for psycopg jsonb compatibility.
    Lists are left as-is (handled natively for ARRAY columns and pgvector)."""
    return {k: json.dumps(v) if isinstance(v, dict) else v for k, v in record.items()}


def _build_insert_sql(schema: str, table_name: str, columns: list[str]) -> str:
    """Build an UPSERT SQL statement for the given table and columns.

    Uses ``ON CONFLICT (uuid) DO UPDATE SET`` to handle duplicates gracefully.
    Excludes GENERATED columns (already filtered out before calling).
    """
    cols_str = ', '.join(columns)
    placeholders = ', '.join(f'%({col})s' for col in columns)
    update_cols = [col for col in columns if col != 'uuid']
    update_str = ', '.join(f'{col} = EXCLUDED.{col}' for col in update_cols)

    return (
        f'INSERT INTO {schema}.{table_name} ({cols_str}) '
        f'VALUES ({placeholders}) '
        f'ON CONFLICT (uuid) DO UPDATE SET {update_str}'
    )


async def _check_group_exists(driver: Any, new_group_id: str) -> bool:
    """Check if the target group_id already has data in any table."""
    result, _, _ = await driver.execute_query(
        f'SELECT 1 FROM {driver.schema}.entity_nodes WHERE group_id = %(group_id)s LIMIT 1',
        params={'group_id': new_group_id},
    )
    return len(result) > 0


def _read_jsonl(path: Path) -> list[dict]:
    """Read all records from a JSONL file, skipping blank lines."""
    records: list[dict] = []
    with path.open('r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


async def import_group(
    driver: Any,
    input_dir: Path,
    new_group_id: str,
    overwrite: bool = False,
) -> None:
    """Import JSONL data from an export directory into the database.

    Parameters
    ----------
    driver:
        PostgresAgeDriver instance.
    input_dir:
        Directory containing metadata.json and JSONL files from export.
    new_group_id:
        The new group_id to assign to all imported records.
    overwrite:
        If True, clear existing data for new_group_id before importing.

    Raises
    ------
    FileNotFoundError:
        If metadata.json is missing.
    ValueError:
        If embedding dimension mismatches or group exists without overwrite.
    """
    # 1. Read and validate metadata
    metadata = _read_metadata(input_dir)
    export_dim = metadata.get('embedding_dimension')
    driver_dim = driver.embedding_dimension

    if export_dim is not None and export_dim != driver_dim:
        raise ValueError(
            f'Embedding dimension mismatch: export has {export_dim}, '
            f'but driver is configured for {driver_dim}'
        )

    # 2. Check if target group_id exists
    group_exists = await _check_group_exists(driver, new_group_id)
    if group_exists and not overwrite:
        raise ValueError(
            f'Target group_id "{new_group_id}" already contains data. '
            f'Use --overwrite to clear existing data first.'
        )

    # 3. If overwrite and group exists, clear existing data
    if group_exists and overwrite:
        await driver.graph_ops.clear_data(driver, [new_group_id])

    # 4. Phase 1: Pre-generate UUID mappings
    jsonl_files = [input_dir / f'{table}.jsonl' for table in _TABLE_ORDER]
    existing_files = [f for f in jsonl_files if f.exists()]
    uuid_map = generate_uuid_mappings(existing_files)

    # 5. Phase 2: Read, remap, and INSERT each table
    schema = driver.schema
    total_inserted = 0

    for table_name in _TABLE_ORDER:
        jsonl_path = input_dir / f'{table_name}.jsonl'
        if not jsonl_path.exists():
            continue

        records = _read_jsonl(jsonl_path)
        if not records:
            continue

        remap_fn = _REMAP_FUNCTIONS[table_name]
        columns: list[str] | None = None
        sql: str | None = None

        for record in records:
            # Remap the record
            remapped = remap_fn(record, uuid_map, new_group_id)

            # Filter out GENERATED fields and JSONify dict/list values
            filtered = {k: v for k, v in remapped.items() if k not in _GENERATED_FIELDS}
            filtered = _jsonify_values(filtered)

            # Build SQL on first record (columns are consistent across records)
            if columns is None:
                columns = list(filtered.keys())
                sql = _build_insert_sql(schema, table_name, columns)

            await driver.execute_query(sql, params=filtered)
            total_inserted += 1

    # 6. Post-import: rebuild indices and AGE projection
    await driver.build_indices_and_constraints()
    # Only rebuild AGE projection if clear_data wasn't called
    # (clear_data already rebuilds it internally)
    if not (group_exists and overwrite):
        await driver.graph_ops.rebuild_age_projection(driver)
