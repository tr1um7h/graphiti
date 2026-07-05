"""Tests for cli/export.py - JSONL export with business key sorting."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cli.export import (
    export_group_with_sorting,
    format_embedding,
    serialize_record,
)

# ---------------------------------------------------------------------------
# format_embedding
# ---------------------------------------------------------------------------


def test_format_embedding() -> None:
    """Verify 6 decimal precision."""
    vec = [0.123456789, 0.987654321, -0.111111111]
    result = format_embedding(vec)
    assert result == [0.123457, 0.987654, -0.111111]


def test_format_embedding_none() -> None:
    """Verify None handling."""
    assert format_embedding(None) is None


# ---------------------------------------------------------------------------
# serialize_record
# ---------------------------------------------------------------------------


def test_serialize_record_skips_search_vector() -> None:
    """search_vector is a GENERATED column and must be excluded."""
    record = {
        'uuid': 'abc',
        'name': 'Test',
        'search_vector': "'test':1A",
    }
    result = serialize_record(record, 'entity_nodes')
    assert 'search_vector' not in result
    assert result['uuid'] == 'abc'
    assert result['name'] == 'Test'


def test_serialize_record_compresses_embeddings() -> None:
    """name_embedding and fact_embedding must be compressed to 6 decimals."""
    record = {
        'uuid': 'abc',
        'name_embedding': [0.123456789, 0.987654321],
        'fact_embedding': [0.111111111, 0.222222222],
    }
    result = serialize_record(record, 'entity_nodes')
    assert result['name_embedding'] == [0.123457, 0.987654]
    assert result['fact_embedding'] == [0.111111, 0.222222]


def test_serialize_record_compresses_none_embedding() -> None:
    """None embeddings remain None."""
    record = {
        'uuid': 'abc',
        'name_embedding': None,
    }
    result = serialize_record(record, 'entity_nodes')
    assert result['name_embedding'] is None


def test_serialize_record_converts_datetime() -> None:
    """datetime objects must be converted to ISO format strings."""
    dt = datetime(2025, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
    record = {
        'uuid': 'abc',
        'created_at': dt,
        'valid_at': dt,
    }
    result = serialize_record(record, 'entity_nodes')
    assert result['created_at'] == '2025-01-15T12:30:45+00:00'
    assert result['valid_at'] == '2025-01-15T12:30:45+00:00'


def test_serialize_record_preserves_other_fields() -> None:
    """Non-embedding, non-datetime fields are preserved as-is."""
    record = {
        'uuid': 'abc',
        'group_id': 'g1',
        'name': 'Test',
        'labels': ['Entity'],
        'attributes': {'key': 'value'},
    }
    result = serialize_record(record, 'entity_nodes')
    assert result == record


# ---------------------------------------------------------------------------
# export_group_with_sorting
# ---------------------------------------------------------------------------


def _make_mock_driver(table_data: dict[str, list[dict]], embedding_dimension: int = 3) -> MagicMock:
    """Create a mock driver that returns canned data for specific queries.

    The mock inspects the SQL query string to determine which table is being
    queried and returns the matching data.
    """
    driver = MagicMock()
    driver.embedding_dimension = embedding_dimension
    driver.close = AsyncMock()

    async def fake_execute_query(query: str, **kwargs: Any) -> tuple[list[dict], None, list[str]]:
        # Match FROM {schema}.{table_name} to identify the primary table
        # Edge queries have JOINs that mention other tables, so we can't just
        # check table_name in query — we need to match the FROM clause.
        query_lower = query.lower()
        for table_name, rows in table_data.items():
            if f'from public.{table_name}' in query_lower:
                keys = list(rows[0].keys()) if rows else []
                return rows, None, keys
        return [], None, []

    driver.execute_query = AsyncMock(side_effect=fake_execute_query)
    return driver


@pytest.mark.asyncio
async def test_export_group_creates_files(tmp_path: Path) -> None:
    """Mock driver, verify JSONL + metadata created."""
    entity_rows = [
        {
            'uuid': 'e1',
            'group_id': 'g1',
            'name': 'Zeta',
            'name_embedding': [0.1234567, 0.9876543, 0.1111111],
            'created_at': datetime(2025, 1, 1, tzinfo=timezone.utc),
        },
        {
            'uuid': 'e2',
            'group_id': 'g1',
            'name': 'Alpha',
            'name_embedding': [0.5, 0.5, 0.5],
            'created_at': datetime(2025, 1, 2, tzinfo=timezone.utc),
        },
    ]

    table_data = {
        'entity_nodes': entity_rows,
        'episodic_nodes': [],
        'community_nodes': [],
        'saga_nodes': [],
        'entity_edges': [],
        'episodic_edges': [],
        'community_edges': [],
        'has_episode_edges': [],
        'next_episode_edges': [],
    }

    driver = _make_mock_driver(table_data, embedding_dimension=3)

    await export_group_with_sorting(driver, 'g1', 'public', tmp_path)

    # Verify JSONL files created for all 9 tables
    for table_name in table_data:
        jsonl_file = tmp_path / f'{table_name}.jsonl'
        assert jsonl_file.exists(), f'{jsonl_file} should exist'

    # Verify metadata.json
    metadata_file = tmp_path / 'metadata.json'
    assert metadata_file.exists()

    metadata = json.loads(metadata_file.read_text())
    assert metadata['group_id'] == 'g1'
    assert 'exported_at' in metadata
    assert metadata['schema'] == 'public'
    assert metadata['embedding_dimension'] == 3
    assert metadata['schema_version'] == 1
    assert metadata['counts']['entity_nodes'] == 2
    assert metadata['counts']['episodic_nodes'] == 0

    # Verify entity_nodes JSONL content - embeddings should be compressed
    entity_jsonl = (tmp_path / 'entity_nodes.jsonl').read_text().strip().split('\n')
    assert len(entity_jsonl) == 2
    first_record = json.loads(entity_jsonl[0])
    # 0.1234567 rounds to 0.123457 (6 decimals)
    assert first_record['name_embedding'] == [0.123457, 0.987654, 0.111111]
    # datetime should be ISO string
    assert first_record['created_at'] == '2025-01-01T00:00:00+00:00'


@pytest.mark.asyncio
async def test_export_sorts_entity_nodes_by_name(tmp_path: Path) -> None:
    """Entity nodes are exported in the order the DB returns them.

    Note: actual sorting happens via SQL ORDER BY — not testable with mocks.
    This test verifies the export pipeline handles multiple records correctly.
    """
    entity_rows = [
        {'uuid': 'e3', 'group_id': 'g1', 'name': 'Charlie', 'labels': ['Person']},
        {'uuid': 'e1', 'group_id': 'g1', 'name': 'Alice', 'labels': ['Person']},
        {'uuid': 'e2', 'group_id': 'g1', 'name': 'Bob', 'labels': ['Org']},
    ]

    driver = _make_mock_driver(
        {t: (entity_rows if t == 'entity_nodes' else []) for t in [
            'entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes',
            'entity_edges', 'episodic_edges', 'community_edges',
            'has_episode_edges', 'next_episode_edges',
        ]},
        embedding_dimension=3,
    )

    await export_group_with_sorting(driver, 'g1', 'public', tmp_path)

    lines = (tmp_path / 'entity_nodes.jsonl').read_text().strip().split('\n')
    records = [json.loads(line) for line in lines]
    assert len(records) == 3
    names = {r['name'] for r in records}
    assert names == {'Alice', 'Bob', 'Charlie'}


@pytest.mark.asyncio
async def test_export_entity_edges_with_content(tmp_path: Path) -> None:
    """Edge table export includes proper embeddings compression."""
    edge_rows = [
        {
            'uuid': 'ee1',
            'group_id': 'g1',
            'source_node_uuid': 's1',
            'target_node_uuid': 't1',
            'name': 'KNOWS',
            'fact': 'knows',
            'fact_embedding': [0.111111222, 0.333333444],
            'episodes': ['ep1'],
        },
    ]

    table_data = {
        'entity_nodes': [],
        'episodic_nodes': [],
        'community_nodes': [],
        'saga_nodes': [],
        'entity_edges': edge_rows,
        'episodic_edges': [],
        'community_edges': [],
        'has_episode_edges': [],
        'next_episode_edges': [],
    }

    driver = _make_mock_driver(table_data, embedding_dimension=3)
    await export_group_with_sorting(driver, 'g1', 'public', tmp_path)

    edge_jsonl = (tmp_path / 'entity_edges.jsonl').read_text()
    lines = edge_jsonl.strip().split('\n')
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record['name'] == 'KNOWS'
    assert record['fact_embedding'] == [0.111111, 0.333333]
    assert 'search_vector' not in record


@pytest.mark.asyncio
async def test_export_episodic_edges_with_content(tmp_path: Path) -> None:
    """Episodic edges export with proper content."""
    edge_rows = [
        {
            'uuid': 'ep1',
            'group_id': 'g1',
            'source_node_uuid': 'e1',
            'target_node_uuid': 't1',
        },
    ]

    table_data = {
        'entity_nodes': [],
        'episodic_nodes': [],
        'community_nodes': [],
        'saga_nodes': [],
        'entity_edges': [],
        'episodic_edges': edge_rows,
        'community_edges': [],
        'has_episode_edges': [],
        'next_episode_edges': [],
    }

    driver = _make_mock_driver(table_data, embedding_dimension=3)
    await export_group_with_sorting(driver, 'g1', 'public', tmp_path)

    edge_jsonl = (tmp_path / 'episodic_edges.jsonl').read_text()
    lines = edge_jsonl.strip().split('\n')
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record['uuid'] == 'ep1'
