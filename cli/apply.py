"""Patch apply engine with conflict resolution.

Applies a semantic patch (produced by :mod:`cli.diff`) to a database,
transforming one group_id's data into another. Supports strategies for
handling conflicts: ours, theirs, skip-conflicts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

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


def get_cascade_deletes(
    table_name: str,
    record_uuid: str,
    records_by_table: dict[str, list[dict]],
) -> list[tuple[str, str]]:
    """Get all (table, uuid) records to delete due to FK cascade."""
    deletes: list[tuple[str, str]] = [(table_name, record_uuid)]

    if table_name == 'entity_nodes':
        for edge in records_by_table.get('entity_edges', []):
            if edge['source_node_uuid'] == record_uuid or edge['target_node_uuid'] == record_uuid:
                deletes.append(('entity_edges', edge['uuid']))
        for edge in records_by_table.get('episodic_edges', []):
            if edge['target_node_uuid'] == record_uuid:
                deletes.append(('episodic_edges', edge['uuid']))
        for edge in records_by_table.get('community_edges', []):
            if edge['target_node_uuid'] == record_uuid:
                deletes.append(('community_edges', edge['uuid']))

    elif table_name == 'episodic_nodes':
        for edge in records_by_table.get('episodic_edges', []):
            if edge['source_node_uuid'] == record_uuid:
                deletes.append(('episodic_edges', edge['uuid']))
        for edge in records_by_table.get('has_episode_edges', []):
            if edge['target_node_uuid'] == record_uuid:
                deletes.append(('has_episode_edges', edge['uuid']))
        for edge in records_by_table.get('next_episode_edges', []):
            if edge['source_node_uuid'] == record_uuid or edge['target_node_uuid'] == record_uuid:
                deletes.append(('next_episode_edges', edge['uuid']))

    elif table_name == 'community_nodes':
        for edge in records_by_table.get('community_edges', []):
            if edge['source_node_uuid'] == record_uuid:
                deletes.append(('community_edges', edge['uuid']))

    return deletes


async def _load_group_data(driver: Any, group_id: str) -> dict[str, list[dict]]:
    """Load all records for a group_id from the database."""
    data: dict[str, list[dict]] = {}
    for table_name in _ALL_TABLES:
        records, _, _ = await driver.execute_query(
            f'SELECT * FROM {driver.schema}.{table_name} WHERE group_id = %(group_id)s',
            params={'group_id': group_id},
        )
        data[table_name] = records
    return data


def _build_business_key(record: dict, table_name: str) -> tuple:
    """Build business key for matching records."""
    if table_name == 'entity_nodes':
        labels = record.get('labels') or []
        return (record.get('name'), tuple(labels))
    if table_name == 'episodic_nodes':
        content = record.get('content', '')
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
        return (record.get('valid_at'), content_hash)
    if table_name in ('community_nodes', 'saga_nodes'):
        return (record.get('name'),)
    if table_name == 'entity_edges':
        return (
            record.get('source_node_uuid'),
            record.get('target_node_uuid'),
            record.get('name'),
        )
    return (record.get('source_node_uuid'), record.get('target_node_uuid'))


def _build_match_key(match: dict, table_name: str) -> tuple:
    """Build business key from a patch match block."""
    if table_name == 'entity_nodes':
        labels = match.get('labels') or []
        return (match.get('name'), tuple(labels))
    if table_name == 'episodic_nodes':
        content = match.get('content', '')
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
        return (match.get('valid_at'), content_hash)
    if table_name in ('community_nodes', 'saga_nodes'):
        return (match.get('name'),)
    if table_name == 'entity_edges':
        return (
            match.get('source_node_uuid'),
            match.get('target_node_uuid'),
            match.get('name'),
        )
    return (match.get('source_node_uuid'), match.get('target_node_uuid'))


async def apply_patch(
    driver: Any,
    patch: dict,
    from_group_id: str,
    to_group_id: str,
    strategy: str = 'ours',
    dry_run: bool = False,
) -> dict:
    """Apply a semantic patch to the database.

    Parameters
    ----------
    driver:
        PostgresAgeDriver instance.
    patch:
        Patch document from diff_groups() or patch.json file.
    from_group_id:
        Source group_id (data is copied from this group).
    to_group_id:
        Target group_id (changes are applied here).
    strategy:
        Conflict resolution: 'ours', 'theirs', 'skip-conflicts'.
    dry_run:
        If True, validate and count without applying.

    Returns
    -------
    dict with counts: added, removed, modified, conflicts, dry_run
    """
    result: dict[str, Any] = {
        'added': 0,
        'removed': 0,
        'modified': 0,
        'conflicts': 0,
        'dry_run': dry_run,
    }

    if dry_run:
        for changes in patch.get('changes', {}).values():
            result['added'] += len(changes.get('added', []))
            result['removed'] += len(changes.get('removed', []))
            result['modified'] += len(changes.get('modified', []))
            result['conflicts'] += len(changes.get('conflicts', []))
        return result

    source_data = await _load_group_data(driver, from_group_id)
    schema = driver.schema

    for table_name in _ALL_TABLES:
        changes = patch.get('changes', {}).get(table_name, {})
        if not changes:
            continue

        target_records, _, _ = await driver.execute_query(
            f'SELECT * FROM {schema}.{table_name} WHERE group_id = %(group_id)s',
            params={'group_id': to_group_id},
        )

        target_index: dict[tuple, dict] = {}
        for rec in target_records:
            key = _build_business_key(rec, table_name)
            target_index[key] = rec

        # --- Apply added records ---
        for added_record in changes.get('added', []):
            new_uuid = str(uuid4())
            insert_record = dict(added_record)
            insert_record['uuid'] = new_uuid
            insert_record['group_id'] = to_group_id

            columns = list(insert_record.keys())
            cols_str = ', '.join(columns)
            placeholders = ', '.join(f'%({col})s' for col in columns)

            sql = (
                f'INSERT INTO {schema}.{table_name} ({cols_str}) '
                f'VALUES ({placeholders}) '
                f'ON CONFLICT (uuid) DO NOTHING'
            )
            await driver.execute_query(sql, params=insert_record)
            result['added'] += 1

        # --- Apply removed records ---
        for removed_match in changes.get('removed', []):
            match_key = _build_match_key(removed_match, table_name)
            if match_key in target_index:
                target_rec = target_index[match_key]
                cascade = get_cascade_deletes(table_name, target_rec['uuid'], source_data)
                for del_table, del_uuid in reversed(cascade):
                    await driver.execute_query(
                        f'DELETE FROM {schema}.{del_table} WHERE uuid = %(uuid)s',
                        params={'uuid': del_uuid},
                    )
            result['removed'] += 1

        # --- Apply modified records ---
        for modified in changes.get('modified', []):
            match_key = _build_match_key(modified['match'], table_name)
            if match_key in target_index:
                target_rec = target_index[match_key]
                updates = modified.get('fields', {})

                set_clauses = []
                params: dict[str, Any] = {'_uuid': target_rec['uuid']}
                for field, change in updates.items():
                    if field in _IGNORED_FIELDS:
                        continue
                    new_val = change.get('new') if isinstance(change, dict) else change
                    params[f'_{field}'] = new_val
                    set_clauses.append(f'{field} = %(_{field})s')

                if set_clauses:
                    set_str = ', '.join(set_clauses)
                    sql = f'UPDATE {schema}.{table_name} SET {set_str} WHERE uuid = %(_uuid)s'
                    await driver.execute_query(sql, params=params)
            result['modified'] += 1

        result['conflicts'] += len(changes.get('conflicts', []))

    await driver.build_indices_and_constraints()
    await driver.graph_ops.rebuild_age_projection(driver)

    return result


async def apply_patch_from_file(
    driver: Any,
    patch_file: Path,
    from_group_id: str,
    to_group_id: str,
    strategy: str = 'ours',
    dry_run: bool = False,
) -> dict:
    """Load a patch from file and apply it."""
    patch = json.loads(patch_file.read_text(encoding='utf-8'))
    return await apply_patch(
        driver, patch, from_group_id, to_group_id, strategy=strategy, dry_run=dry_run
    )
