"""Tests for cli/import_.py - JSONL import with UUID remapping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli.import_ import import_group

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write records as JSONL."""
    with path.open('w', encoding='utf-8') as fh:
        for rec in records:
            fh.write(json.dumps(rec) + '\n')


def _write_metadata(
    path: Path, embedding_dimension: int = 1024, group_id: str = 'old-group'
) -> None:
    """Write metadata.json matching export format."""
    metadata = {
        'group_id': group_id,
        'exported_at': '2025-01-01T00:00:00+00:00',
        'schema': 'public',
        'embedding_dimension': embedding_dimension,
        'schema_version': 1,
        'counts': {},
    }
    path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')


def _make_mock_driver(
    embedding_dimension: int = 1024,
    group_exists: bool = False,
) -> MagicMock:
    """Create a mock PostgresAgeDriver.

    Parameters
    ----------
    embedding_dimension:
        The driver's embedding dimension for metadata validation.
    group_exists:
        If True, the check_group_exists query returns data (group exists).
    """
    driver = MagicMock()
    driver.embedding_dimension = embedding_dimension
    driver.schema = 'public'
    driver.close = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()

    # graph_ops mock
    graph_ops = MagicMock()
    graph_ops.clear_data = AsyncMock()
    graph_ops.rebuild_age_projection = AsyncMock()
    driver.graph_ops = graph_ops

    async def fake_execute_query(query: str, **kwargs: Any) -> tuple[list[dict], None, list[str]]:
        # Check if this is the group existence check
        if 'group_id' in str(kwargs.get('params', {})) and 'SELECT' in query:
            if group_exists:
                return [{'group_id': 'old-group'}], None, ['group_id']
            return [], None, []
        # Default: INSERT returns empty
        return [], None, []

    driver.execute_query = AsyncMock(side_effect=fake_execute_query)
    return driver


def _create_export_dir(
    tmp_path: Path,
    *,
    embedding_dimension: int = 1024,
    entity_nodes: list[dict] | None = None,
    episodic_nodes: list[dict] | None = None,
    community_nodes: list[dict] | None = None,
    saga_nodes: list[dict] | None = None,
    entity_edges: list[dict] | None = None,
    episodic_edges: list[dict] | None = None,
    community_edges: list[dict] | None = None,
    has_episode_edges: list[dict] | None = None,
    next_episode_edges: list[dict] | None = None,
) -> Path:
    """Create a temp export directory with JSONL files."""
    export_dir = tmp_path / 'export'
    export_dir.mkdir()

    _write_metadata(export_dir / 'metadata.json', embedding_dimension=embedding_dimension)

    # Write all 9 JSONL files (empty if no data provided)
    table_data = {
        'entity_nodes': entity_nodes or [],
        'episodic_nodes': episodic_nodes or [],
        'community_nodes': community_nodes or [],
        'saga_nodes': saga_nodes or [],
        'entity_edges': entity_edges or [],
        'episodic_edges': episodic_edges or [],
        'community_edges': community_edges or [],
        'has_episode_edges': has_episode_edges or [],
        'next_episode_edges': next_episode_edges or [],
    }
    for table_name, records in table_data.items():
        _write_jsonl(export_dir / f'{table_name}.jsonl', records)

    return export_dir


# ---------------------------------------------------------------------------
# Test 1: Successful import with UUID remapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_success_with_uuid_remapping(tmp_path: Path) -> None:
    """Import reads JSONL, remaps UUIDs, INSERTs to SQL."""
    entity_record = {
        'uuid': 'old-entity-uuid-1',
        'group_id': 'old-group',
        'name': 'Python',
        'summary': 'A programming language',
        'labels': ['Entity'],
        'attributes': {'version': '3.12'},
        'name_embedding': [0.1, 0.2, 0.3],
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        embedding_dimension=3,
        entity_nodes=[entity_record],
    )

    driver = _make_mock_driver(embedding_dimension=3)

    await import_group(driver, export_dir, 'new-group')

    # Verify execute_query was called for INSERT (not just the group check)
    insert_calls = [
        call for call in driver.execute_query.call_args_list if 'INSERT INTO' in str(call)
    ]
    assert len(insert_calls) >= 1, 'At least one INSERT should be executed'

    # Verify the INSERT was called with remapped UUID
    insert_call = insert_calls[0]
    params = insert_call.kwargs.get('params', {})
    assert params['uuid'] != 'old-entity-uuid-1', 'UUID must be remapped'
    assert params['group_id'] == 'new-group', 'group_id must be remapped'
    assert params['name'] == 'Python', 'Non-UUID fields preserved'

    # Verify build_indices_and_constraints was called
    driver.build_indices_and_constraints.assert_called_once()

    # Verify graph_ops.rebuild_age_projection was called
    driver.graph_ops.rebuild_age_projection.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Import fails when group exists without --overwrite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_fails_when_group_exists(tmp_path: Path) -> None:
    """Import raises ValueError if group already has data and overwrite=False."""
    export_dir = _create_export_dir(tmp_path)
    driver = _make_mock_driver(group_exists=True)

    with pytest.raises(ValueError, match='already contains data'):
        await import_group(driver, export_dir, 'new-group', overwrite=False)


# ---------------------------------------------------------------------------
# Test 3: Import with --overwrite clears existing data first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_with_overwrite_clears_data(tmp_path: Path) -> None:
    """Import with overwrite=True clears existing data before inserting."""
    export_dir = _create_export_dir(tmp_path)
    driver = _make_mock_driver(group_exists=True)

    await import_group(driver, export_dir, 'new-group', overwrite=True)

    # Verify clear_data was called with the new group_id
    driver.graph_ops.clear_data.assert_called_once()
    call_kwargs = driver.graph_ops.clear_data.call_args
    # clear_data is called with (executor, group_ids=[...])
    assert call_kwargs[0][0] is driver  # executor is the driver
    assert 'new-group' in call_kwargs[0][1] or call_kwargs[1].get('group_ids') == ['new-group']


# ---------------------------------------------------------------------------
# Test 4: Embedding dimension mismatch raises error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_embedding_dimension_mismatch(tmp_path: Path) -> None:
    """Import raises ValueError if export embedding_dimension != driver embedding_dimension."""
    export_dir = _create_export_dir(tmp_path, embedding_dimension=512)
    driver = _make_mock_driver(embedding_dimension=1024)

    with pytest.raises(ValueError, match='[Ee]mbedding.*dimension'):
        await import_group(driver, export_dir, 'new-group')


# ---------------------------------------------------------------------------
# Test 5: Import handles empty JSONL files gracefully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_empty_jsonl_files(tmp_path: Path) -> None:
    """Import with all empty JSONL files: no INSERTs but rebuild still happens."""
    export_dir = _create_export_dir(tmp_path)
    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Verify no INSERT calls
    insert_calls = [
        call for call in driver.execute_query.call_args_list if 'INSERT INTO' in str(call)
    ]
    assert len(insert_calls) == 0, 'No INSERTs should happen for empty JSONL'

    # Verify rebuild still happens
    driver.build_indices_and_constraints.assert_called_once()
    driver.graph_ops.rebuild_age_projection.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: Import with multiple tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_multiple_tables(tmp_path: Path) -> None:
    """Import with data in entity_nodes, entity_edges, episodic_nodes."""
    entity_record = {
        'uuid': 'old-entity-1',
        'group_id': 'old-group',
        'name': 'Python',
        'summary': 'A language',
        'labels': [],
        'attributes': {},
        'name_embedding': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    episodic_record = {
        'uuid': 'old-episode-1',
        'group_id': 'old-group',
        'name': 'Episode 1',
        'source': 'txt',
        'source_description': 'desc',
        'content': 'content',
        'valid_at': '2025-01-01T00:00:00+00:00',
        'entity_edges': ['old-edge-ee-1'],
        'episode_metadata': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    entity_edge_record = {
        'uuid': 'old-edge-ee-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-entity-1',
        'target_node_uuid': 'old-entity-1',
        'name': 'RELATES_TO',
        'fact': 'Python is great',
        'fact_embedding': None,
        'episodes': ['old-episode-1'],
        'expired_at': None,
        'valid_at': None,
        'invalid_at': None,
        'reference_time': None,
        'attributes': {},
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        entity_nodes=[entity_record],
        episodic_nodes=[episodic_record],
        entity_edges=[entity_edge_record],
    )

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Verify 3 INSERT calls (one per table with data)
    insert_calls = [
        call for call in driver.execute_query.call_args_list if 'INSERT INTO' in str(call)
    ]
    assert len(insert_calls) == 3, f'Expected 3 INSERTs, got {len(insert_calls)}'

    # Verify each INSERT has remapped UUIDs
    inserted_uuids = set()
    inserted_group_ids = set()
    for call in insert_calls:
        params = call.kwargs.get('params', {})
        inserted_uuids.add(params['uuid'])
        inserted_group_ids.add(params['group_id'])

    # All group_ids must be the new group
    assert inserted_group_ids == {'new-group'}

    # All UUIDs must be remapped (not the old ones)
    assert 'old-entity-1' not in inserted_uuids
    assert 'old-episode-1' not in inserted_uuids
    assert 'old-edge-ee-1' not in inserted_uuids


# ---------------------------------------------------------------------------
# Test 7: Import with saga node with nullable episode references
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_saga_node_null_episodes(tmp_path: Path) -> None:
    """Saga node with NULL episode references imports correctly."""
    saga_record = {
        'uuid': 'old-saga-1',
        'group_id': 'old-group',
        'name': 'Saga 1',
        'summary': '',
        'first_episode_uuid': None,
        'last_episode_uuid': None,
        'last_summarized_at': None,
        'last_summarized_episode_valid_at': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        saga_nodes=[saga_record],
    )

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Verify the INSERT was called with NULL episode references
    insert_calls = [
        call
        for call in driver.execute_query.call_args_list
        if 'INSERT INTO' in str(call) and 'saga_nodes' in str(call)
    ]
    assert len(insert_calls) == 1
    params = insert_calls[0].kwargs.get('params', {})
    assert params['first_episode_uuid'] is None
    assert params['last_episode_uuid'] is None
    assert params['group_id'] == 'new-group'


# ---------------------------------------------------------------------------
# Test 8: FK references are remapped in edge tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_remaps_fk_references_in_edges(tmp_path: Path) -> None:
    """source_node_uuid and target_node_uuid in edges are remapped."""
    entity_record = {
        'uuid': 'old-entity-1',
        'group_id': 'old-group',
        'name': 'Python',
        'summary': '',
        'labels': [],
        'attributes': {},
        'name_embedding': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    edge_record = {
        'uuid': 'old-edge-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-entity-1',
        'target_node_uuid': 'old-entity-1',
        'name': 'SELF_REF',
        'fact': '',
        'fact_embedding': None,
        'episodes': [],
        'expired_at': None,
        'valid_at': None,
        'invalid_at': None,
        'reference_time': None,
        'attributes': {},
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        entity_nodes=[entity_record],
        entity_edges=[edge_record],
    )
    _write_metadata(export_dir / 'metadata.json', embedding_dimension=1024)

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Find the entity_edges INSERT
    edge_inserts = [
        call
        for call in driver.execute_query.call_args_list
        if 'INSERT INTO' in str(call) and 'entity_edges' in str(call)
    ]
    assert len(edge_inserts) == 1
    params = edge_inserts[0].kwargs.get('params', {})

    # FK references must be remapped to new UUIDs
    assert params['source_node_uuid'] != 'old-entity-1'
    assert params['target_node_uuid'] != 'old-entity-1'
    # Both source and target point to the same old entity, so they remap to the same new UUID
    assert params['source_node_uuid'] == params['target_node_uuid']
    # Verify it's a valid UUID format (not the old value)
    import uuid
    uuid.UUID(params['source_node_uuid'])


# ---------------------------------------------------------------------------
# Test 9: Community nodes and edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_community_with_edges(tmp_path: Path) -> None:
    """Community nodes and community edges import correctly."""
    community = {
        'uuid': 'old-comm-1',
        'group_id': 'old-group',
        'name': 'Community A',
        'summary': '',
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    entity = {
        'uuid': 'some-entity-uuid',
        'group_id': 'old-group',
        'name': 'Entity X',
        'summary': '',
        'labels': [],
        'attributes': {},
        'name_embedding': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    comm_edge = {
        'uuid': 'old-ce-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-comm-1',
        'target_node_uuid': 'some-entity-uuid',
        'name': 'HAS_MEMBER',
        'fact': 'Community A has member X',
        'fact_embedding': None,
        'episodes': [],
        'expired_at': None,
        'valid_at': None,
        'invalid_at': None,
        'reference_time': None,
        'attributes': {},
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        entity_nodes=[entity],
        community_nodes=[community],
        community_edges=[comm_edge],
    )
    _write_metadata(export_dir / 'metadata.json', embedding_dimension=1024)

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Verify community_nodes INSERT
    comm_inserts = [
        call
        for call in driver.execute_query.call_args_list
        if 'INSERT INTO' in str(call) and 'community_nodes' in str(call)
    ]
    assert len(comm_inserts) == 1
    comm_params = comm_inserts[0].kwargs.get('params', {})
    assert comm_params['name'] == 'Community A'
    assert comm_params['group_id'] == 'new-group'

    # Verify community_edges INSERT with remapped source
    ce_inserts = [
        call
        for call in driver.execute_query.call_args_list
        if 'INSERT INTO' in str(call) and 'community_edges' in str(call)
    ]
    assert len(ce_inserts) == 1
    ce_params = ce_inserts[0].kwargs.get('params', {})
    # source_node_uuid should be remapped to the new community uuid
    assert ce_params['source_node_uuid'] == comm_params['uuid']
    assert ce_params['group_id'] == 'new-group'


# ---------------------------------------------------------------------------
# Test 10: Has_episode_edges and next_episode_edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_episode_relationship_edges(tmp_path: Path) -> None:
    """has_episode_edges and next_episode_edges import with remapped FKs."""
    saga_record = {
        'uuid': 'old-saga',
        'group_id': 'old-group',
        'name': 'Saga',
        'summary': '',
        'first_episode_uuid': None,
        'last_episode_uuid': None,
        'last_summarized_at': None,
        'last_summarized_episode_valid_at': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    episodic_record = {
        'uuid': 'old-ep',
        'group_id': 'old-group',
        'name': 'Ep',
        'source': 'txt',
        'source_description': '',
        'content': 'content',
        'valid_at': '2025-01-01T00:00:00+00:00',
        'entity_edges': [],
        'episode_metadata': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    episodic_record2 = {
        'uuid': 'old-ep2',
        'group_id': 'old-group',
        'name': 'Ep2',
        'source': 'txt',
        'source_description': '',
        'content': 'content 2',
        'valid_at': '2025-02-01T00:00:00+00:00',
        'entity_edges': [],
        'episode_metadata': None,
        'created_at': '2025-02-01T00:00:00+00:00',
    }
    has_ep = {
        'uuid': 'old-he',
        'group_id': 'old-group',
        'source_node_uuid': 'old-saga',
        'target_node_uuid': 'old-ep',
    }
    next_ep = {
        'uuid': 'old-ne',
        'group_id': 'old-group',
        'source_node_uuid': 'old-ep',
        'target_node_uuid': 'old-ep2',
    }

    export_dir = _create_export_dir(
        tmp_path,
        saga_nodes=[saga_record],
        episodic_nodes=[episodic_record, episodic_record2],
        has_episode_edges=[has_ep],
        next_episode_edges=[next_ep],
    )
    _write_metadata(export_dir / 'metadata.json', embedding_dimension=1024)

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Collect all inserted UUIDs by table (list per table for multi-record)
    inserted: dict[str, list[dict]] = {}
    for call in driver.execute_query.call_args_list:
        if 'INSERT INTO' not in str(call):
            continue
        query_str = str(call)
        for table in ['saga_nodes', 'episodic_nodes', 'has_episode_edges', 'next_episode_edges']:
            if table in query_str:
                params = call.kwargs.get('params', {})
                inserted.setdefault(table, []).append(params)
                break

    # has_episode_edges.source_node_uuid should point to the remapped saga
    assert inserted['has_episode_edges'][0]['source_node_uuid'] == inserted['saga_nodes'][0]['uuid']

    # has_episode_edges.target_node_uuid should point to old-ep (first episodic node)
    # Find the episodic node whose name is 'Ep' (old-ep → this is the one has_ep references)
    ep_uuids = {ep['name']: ep['uuid'] for ep in inserted['episodic_nodes']}
    assert inserted['has_episode_edges'][0]['target_node_uuid'] == ep_uuids['Ep']

    # next_episode_edges.source_node_uuid should point to old-ep
    assert inserted['next_episode_edges'][0]['source_node_uuid'] == ep_uuids['Ep']
    # next_episode_edges.target_node_uuid should point to old-ep2
    assert inserted['next_episode_edges'][0]['target_node_uuid'] == ep_uuids['Ep2']


# ---------------------------------------------------------------------------
# Test 11: search_vector is excluded from INSERT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_excludes_search_vector_from_insert(tmp_path: Path) -> None:
    """search_vector is a GENERATED column and must not appear in INSERT."""
    entity_record = {
        'uuid': 'old-e1',
        'group_id': 'old-group',
        'name': 'Entity',
        'summary': '',
        'labels': [],
        'attributes': {},
        'name_embedding': None,
        'search_vector': "'entity':1A",
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        entity_nodes=[entity_record],
    )
    _write_metadata(export_dir / 'metadata.json', embedding_dimension=1024)

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    insert_calls = [
        call
        for call in driver.execute_query.call_args_list
        if 'INSERT INTO' in str(call)
    ]
    assert len(insert_calls) == 1
    params = insert_calls[0].kwargs.get('params', {})
    assert 'search_vector' not in params
    assert 'name' in params


# ---------------------------------------------------------------------------
# Test 12: FK ordering — nodes before edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_inserts_nodes_before_edges(tmp_path: Path) -> None:
    """Node tables must be INSERTed before edge tables for FK integrity."""
    entity_record = {
        'uuid': 'old-e1',
        'group_id': 'old-group',
        'name': 'Entity',
        'summary': '',
        'labels': [],
        'attributes': {},
        'name_embedding': None,
        'created_at': '2025-01-01T00:00:00+00:00',
    }
    edge_record = {
        'uuid': 'old-ee-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-e1',
        'target_node_uuid': 'old-e1',
        'name': 'KNOWS',
        'fact': '',
        'fact_embedding': None,
        'episodes': [],
        'expired_at': None,
        'valid_at': None,
        'invalid_at': None,
        'reference_time': None,
        'attributes': {},
        'created_at': '2025-01-01T00:00:00+00:00',
    }

    export_dir = _create_export_dir(
        tmp_path,
        entity_nodes=[entity_record],
        entity_edges=[edge_record],
    )
    _write_metadata(export_dir / 'metadata.json', embedding_dimension=1024)

    driver = _make_mock_driver(embedding_dimension=1024)

    await import_group(driver, export_dir, 'new-group')

    # Find order of INSERTs
    insert_tables = []
    for call in driver.execute_query.call_args_list:
        query_str = str(call)
        if 'INSERT INTO' in query_str:
            for table in [
                'entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes',
                'entity_edges', 'episodic_edges', 'community_edges',
                'has_episode_edges', 'next_episode_edges',
            ]:
                if table in query_str:
                    insert_tables.append(table)
                    break

    # Find positions
    entity_pos = insert_tables.index('entity_nodes')
    edge_pos = insert_tables.index('entity_edges')
    assert entity_pos < edge_pos, (
        f'entity_nodes must be inserted before entity_edges, '
        f'got entity_nodes at {entity_pos}, entity_edges at {edge_pos}'
    )
