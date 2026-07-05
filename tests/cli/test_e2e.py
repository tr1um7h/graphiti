"""E2E integration tests — full export → import → diff → apply pipeline.

These tests exercise the entire CLI data migration workflow using mock drivers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

from cli.apply import apply_patch
from cli.diff import diff_groups

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_driver(
    table_data: dict[str, list[dict]] | None = None,
    embedding_dimension: int = 3,
    group_exists: bool = False,
) -> Mock:
    """Create a mock driver for export/apply operations."""
    driver = Mock()
    driver.schema = 'public'
    driver.embedding_dimension = embedding_dimension
    driver.close = AsyncMock()
    driver.build_indices_and_constraints = AsyncMock()

    graph_ops = Mock()
    graph_ops.rebuild_age_projection = AsyncMock()
    graph_ops.clear_data = AsyncMock()
    driver.graph_ops = graph_ops

    table_data = table_data or {}

    async def fake_execute_query(query: str, **kwargs: Any) -> tuple[list[dict], None, list[str]]:
        params = kwargs.get('params', {})
        # Group existence check
        if 'group_id' in params and 'SELECT' in query and 'LIMIT' in query:
            if group_exists and params['group_id'] != 'other-group':
                return [{'group_id': params['group_id']}], None, ['group_id']
            return [], None, []

        # Table data queries
        query_lower = query.lower()
        for table_name, rows in table_data.items():
            if f'from public.{table_name}' in query_lower:
                keys = list(rows[0].keys()) if rows else []
                return rows, None, keys
        return [], None, []

    driver.execute_query = AsyncMock(side_effect=fake_execute_query)
    return driver


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open('w', encoding='utf-8') as fh:
        for rec in records:
            fh.write(json.dumps(rec) + '\n')


ALL_TABLES = [
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


def _make_export_dir(tmp_path: Path, name: str, tables: dict[str, list[dict]]) -> Path:
    """Create an export directory with JSONL files and metadata.json."""
    export_dir = tmp_path / name
    export_dir.mkdir()
    metadata = {
        'group_id': name,
        'exported_at': '2025-01-01T00:00:00+00:00',
        'schema': 'public',
        'embedding_dimension': 3,
        'schema_version': 1,
        'counts': {t: len(tables.get(t, [])) for t in ALL_TABLES},
    }
    (export_dir / 'metadata.json').write_text(
        json.dumps(metadata, indent=2) + '\n', encoding='utf-8'
    )
    for table_name in ALL_TABLES:
        _write_jsonl(export_dir / f'{table_name}.jsonl', tables.get(table_name, []))
    return export_dir


# ---------------------------------------------------------------------------
# E2E Test: Full data migration pipeline with mocks
# ---------------------------------------------------------------------------


class TestE2EFullPipeline:
    """End-to-end tests exercising the full export → import → diff → apply pipeline."""

    async def test_full_pipeline_export_diff_apply(self, tmp_path: Path) -> None:
        """Full pipeline: export group_a, export group_b, diff, apply patch."""
        # --- Phase 1: Simulate two group exports ---
        entity_a = [
            {
                'uuid': 'ua1',
                'group_id': 'group_a',
                'name': 'Alice',
                'labels': ['Person'],
                'summary': 'Engineer',
                'created_at': '2025-01-01T00:00:00',
            },
            {
                'uuid': 'ua2',
                'group_id': 'group_a',
                'name': 'Bob',
                'labels': ['Person'],
                'summary': 'Designer',
                'created_at': '2025-01-01T00:00:00',
            },
            {
                'uuid': 'ua3',
                'group_id': 'group_a',
                'name': 'Dave',
                'labels': ['Person'],
                'summary': 'Removed person',
                'created_at': '2025-01-01T00:00:00',
            },
        ]
        edge_a = [
            {
                'uuid': 'ea1',
                'group_id': 'group_a',
                'source_node_uuid': 'ua1',
                'target_node_uuid': 'ua2',
                # Semantic fields for cross-group diff
                'source_name': 'Alice',
                'target_name': 'Bob',
                'name': 'KNOWS',
                'fact': 'Alice knows Bob',
                'fact_embedding': None,
                'episodes': [],
                'expired_at': None,
                'valid_at': None,
                'invalid_at': None,
                'reference_time': None,
                'attributes': {},
                'created_at': '2025-01-01T00:00:00',
            },
        ]

        entity_b = [
            {
                'uuid': 'ub1',
                'group_id': 'group_b',
                'name': 'Alice',
                'labels': ['Person'],
                'summary': 'Manager',
                'created_at': '2025-01-01T00:00:00',
            },
            {
                'uuid': 'ub2',
                'group_id': 'group_b',
                'name': 'Bob',
                'labels': ['Person'],
                'summary': 'Designer',
                'created_at': '2025-01-01T00:00:00',
            },
            {
                'uuid': 'ub3',
                'group_id': 'group_b',
                'name': 'Charlie',
                'labels': ['Person'],
                'summary': 'New person',
                'created_at': '2025-02-01T00:00:00',
            },
        ]
        edge_b = [
            {
                'uuid': 'eb1',
                'group_id': 'group_b',
                'source_node_uuid': 'ub1',
                'target_node_uuid': 'ub2',
                # Semantic fields for cross-group diff (same as edge_a: Alice → Bob, KNOWS)
                'source_name': 'Alice',
                'target_name': 'Bob',
                'name': 'KNOWS',
                'fact': 'Alice knows Bob well',  # Modified fact
                'fact_embedding': None,
                'episodes': [],
                'expired_at': None,
                'valid_at': None,
                'invalid_at': None,
                'reference_time': None,
                'attributes': {},
                'created_at': '2025-01-01T00:00:00',
            },
            {
                'uuid': 'eb2',
                'group_id': 'group_b',
                'source_node_uuid': 'ub1',
                'target_node_uuid': 'ub3',
                # New edge: Alice → Charlie, KNOWS
                'source_name': 'Alice',
                'target_name': 'Charlie',
                'name': 'KNOWS',
                'fact': 'Alice knows Charlie',
                'fact_embedding': None,
                'episodes': [],
                'expired_at': None,
                'valid_at': None,
                'invalid_at': None,
                'reference_time': None,
                'attributes': {},
                'created_at': '2025-02-01T00:00:00',
            },
        ]

        export_a = _make_export_dir(
            tmp_path,
            'group_a',
            {
                'entity_nodes': entity_a,
                'entity_edges': edge_a,
            },
        )
        export_b = _make_export_dir(
            tmp_path,
            'group_b',
            {
                'entity_nodes': entity_b,
                'entity_edges': edge_b,
            },
        )

        # --- Phase 2: Diff ---
        patch = diff_groups(export_a, export_b)

        assert patch['version'] == 1
        assert patch['metadata']['from_group_id'] == 'group_a'
        assert patch['metadata']['to_group_id'] == 'group_b'

        en_changes = patch['changes']['entity_nodes']
        # Added: Charlie (in B but not A)
        assert len(en_changes['added']) == 1
        assert en_changes['added'][0]['name'] == 'Charlie'
        # Removed: Dave (in A but not B)
        assert len(en_changes['removed']) == 1
        assert en_changes['removed'][0]['name'] == 'Dave'
        # Modified: Alice (summary changed)
        assert len(en_changes['modified']) == 1
        assert en_changes['modified'][0]['match']['name'] == 'Alice'
        assert en_changes['modified'][0]['fields'] == {
            'summary': {'old': 'Engineer', 'new': 'Manager'},
        }

        ee_changes = patch['changes']['entity_edges']
        # With semantic business keys (source_name, target_name, name):
        # (Alice, Bob, KNOWS) exists in both A and B → modified (fact changed)
        # (Alice, Charlie, KNOWS) exists only in B → added
        # No removed edges (the matching edge is modified, not removed)
        assert len(ee_changes['removed']) == 0
        assert len(ee_changes['added']) == 1
        assert ee_changes['added'][0]['target_name'] == 'Charlie'
        assert len(ee_changes['modified']) == 1
        assert ee_changes['modified'][0]['match']['target_name'] == 'Bob'
        assert ee_changes['modified'][0]['fields'] == {
            'fact': {'old': 'Alice knows Bob', 'new': 'Alice knows Bob well'},
        }

        # --- Phase 3: Apply patch ---
        # Target driver has group_b data (including Dave who should be removed)
        target_data = {
            'entity_nodes': [
                {
                    'uuid': 'ub1',
                    'group_id': 'group_b',
                    'name': 'Alice',
                    'labels': ['Person'],
                    'summary': 'Manager',
                },
                {
                    'uuid': 'ub2',
                    'group_id': 'group_b',
                    'name': 'Bob',
                    'labels': ['Person'],
                    'summary': 'Designer',
                },
                {
                    'uuid': 'ub3',
                    'group_id': 'group_b',
                    'name': 'Charlie',
                    'labels': ['Person'],
                    'summary': 'New person',
                },
                {
                    'uuid': 'ud1',
                    'group_id': 'group_b',
                    'name': 'Dave',
                    'labels': ['Person'],
                    'summary': 'Removed person',
                },
            ],
            'entity_edges': [
                {
                    'uuid': 'eb1',
                    'group_id': 'group_b',
                    'source_node_uuid': 'ub1',
                    'target_node_uuid': 'ub2',
                    'name': 'KNOWS',
                    'fact': 'Alice knows Bob well',
                },
                {
                    'uuid': 'eb2',
                    'group_id': 'group_b',
                    'source_node_uuid': 'ub1',
                    'target_node_uuid': 'ub3',
                    'name': 'KNOWS',
                    'fact': 'Alice knows Charlie',
                },
            ],
        }
        mock_driver = _make_mock_driver(target_data, embedding_dimension=3)

        result = await apply_patch(
            mock_driver, patch, 'group_a', 'group_b', strategy='ours', dry_run=False
        )

        # Verify outcome counts
        assert result['added'] >= 1  # Charlie added
        assert result['removed'] == 1  # Dave removed
        assert result['modified'] >= 1  # Alice modified or edge modified

    async def test_pipeline_with_episodic_and_communities(self, tmp_path: Path) -> None:
        """Pipeline including episodic nodes, communities, and saga nodes."""
        episodic_a = [
            {
                'uuid': 'epa1',
                'group_id': 'group_a',
                'name': 'Ep1',
                'source': 'txt',
                'source_description': 'a',
                'content': 'hello',
                'valid_at': '2025-01-01T00:00:00',
                'entity_edges': [],
                'episode_metadata': None,
                'created_at': '2025-01-01T00:00:00',
            },
        ]
        community_a = [
            {
                'uuid': 'ca1',
                'group_id': 'group_a',
                'name': 'Tech Community',
                'summary': 'Old summary',
                'created_at': '2025-01-01T00:00:00',
            },
        ]
        saga_a = [
            {
                'uuid': 'sa1',
                'group_id': 'group_a',
                'name': 'Old Saga',
                'summary': '',
                'first_episode_uuid': None,
                'last_episode_uuid': None,
                'last_summarized_at': None,
                'last_summarized_episode_valid_at': None,
                'created_at': '2025-01-01T00:00:00',
            },
        ]

        episodic_b = [
            {
                'uuid': 'epb1',
                'group_id': 'group_b',
                'name': 'Ep1',
                'source': 'txt',
                'source_description': 'b',
                'content': 'hello',
                'valid_at': '2025-01-01T00:00:00',
                'entity_edges': [],
                'episode_metadata': None,
                'created_at': '2025-01-01T00:00:00',
            },
            {
                'uuid': 'epb2',
                'group_id': 'group_b',
                'name': 'Ep2',
                'source': 'txt',
                'source_description': 'c',
                'content': 'world',
                'valid_at': '2025-02-01T00:00:00',
                'entity_edges': [],
                'episode_metadata': None,
                'created_at': '2025-02-01T00:00:00',
            },
        ]
        community_b = [
            {
                'uuid': 'cb1',
                'group_id': 'group_b',
                'name': 'Tech Community',
                'summary': 'New summary',
                'created_at': '2025-01-01T00:00:00',
            },
        ]
        saga_b = []  # Saga removed in group_b

        export_a = _make_export_dir(
            tmp_path,
            'group_a',
            {
                'episodic_nodes': episodic_a,
                'community_nodes': community_a,
                'saga_nodes': saga_a,
            },
        )
        export_b = _make_export_dir(
            tmp_path,
            'group_b',
            {
                'episodic_nodes': episodic_b,
                'community_nodes': community_b,
                'saga_nodes': saga_b,
            },
        )

        # Diff
        patch = diff_groups(export_a, export_b)

        # Episodic: 1 added (Ep2), 0 removed, 1 modified (source_description changed)
        ep_changes = patch['changes']['episodic_nodes']
        assert len(ep_changes['added']) == 1
        assert ep_changes['added'][0]['content'] == 'world'
        assert len(ep_changes['modified']) == 1
        assert ep_changes['modified'][0]['fields'] == {
            'source_description': {'old': 'a', 'new': 'b'},
        }
        assert len(ep_changes['removed']) == 0

        # Community: 1 modified (summary)
        comm_changes = patch['changes']['community_nodes']
        assert len(comm_changes['modified']) == 1
        assert comm_changes['modified'][0]['fields'] == {
            'summary': {'old': 'Old summary', 'new': 'New summary'},
        }

        # Saga: 1 removed
        saga_changes = patch['changes']['saga_nodes']
        assert len(saga_changes['removed']) == 1
        assert saga_changes['removed'][0]['name'] == 'Old Saga'

        # Apply
        target_data = {
            'entity_nodes': [],
            'episodic_nodes': [
                {
                    'uuid': 'epb1',
                    'group_id': 'group_b',
                    'name': 'Ep1',
                    'source': 'txt',
                    'source_description': 'b',
                    'content': 'hello',
                    'valid_at': '2025-01-01T00:00:00',
                    'entity_edges': [],
                    'episode_metadata': None,
                    'created_at': '2025-01-01T00:00:00',
                },
                {
                    'uuid': 'epb2',
                    'group_id': 'group_b',
                    'name': 'Ep2',
                    'source': 'txt',
                    'source_description': 'c',
                    'content': 'world',
                    'valid_at': '2025-02-01T00:00:00',
                    'entity_edges': [],
                    'episode_metadata': None,
                    'created_at': '2025-02-01T00:00:00',
                },
            ],
            'community_nodes': [
                {
                    'uuid': 'cb1',
                    'group_id': 'group_b',
                    'name': 'Tech Community',
                    'summary': 'New summary',
                    'created_at': '2025-01-01T00:00:00',
                },
            ],
            'saga_nodes': [],
            'entity_edges': [],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }
        mock_driver = _make_mock_driver(target_data, embedding_dimension=3)

        result = await apply_patch(
            mock_driver, patch, 'group_a', 'group_b', strategy='ours', dry_run=False
        )

        assert result['added'] == 1  # Ep2
        assert result['modified'] == 2  # Ep1 + Community
        # Saga already absent from target, so no actual removal happens
        assert result['removed'] == 0

    async def test_dry_run_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline dry run validates without applying."""
        entity_a = [
            {
                'uuid': 'ua1',
                'group_id': 'group_a',
                'name': 'Alice',
                'labels': ['Person'],
                'summary': 'Engineer',
            },
        ]
        entity_b = [
            {
                'uuid': 'ub1',
                'group_id': 'group_b',
                'name': 'Alice',
                'labels': ['Person'],
                'summary': 'Manager',
            },
            {
                'uuid': 'ub2',
                'group_id': 'group_b',
                'name': 'Bob',
                'labels': ['Person'],
                'summary': 'New',
            },
        ]

        export_a = _make_export_dir(tmp_path, 'group_a', {'entity_nodes': entity_a})
        export_b = _make_export_dir(tmp_path, 'group_b', {'entity_nodes': entity_b})

        patch = diff_groups(export_a, export_b)

        mock_driver = _make_mock_driver(embedding_dimension=3)

        result = await apply_patch(
            mock_driver, patch, 'group_a', 'group_b', strategy='ours', dry_run=True
        )

        assert result['dry_run'] is True
        assert result['added'] == 1  # Bob
        assert result['modified'] == 1  # Alice
        assert result['removed'] == 0
        # No DB operations in dry run
        assert mock_driver.execute_query.call_count == 0

    async def test_pipeline_with_conflicts(self, tmp_path: Path) -> None:
        """Pipeline handles conflict records between groups."""
        entity_a = [
            {
                'uuid': 'ua1',
                'group_id': 'group_a',
                'name': 'Alice',
                'labels': ['Person'],
                'summary': 'Engineer',
            },
        ]
        entity_b = [
            {
                'uuid': 'ub1',
                'group_id': 'group_b',
                'name': 'Alice',
                'labels': ['Person'],
                'summary': 'Manager',
            },
        ]

        export_a = _make_export_dir(tmp_path, 'group_a', {'entity_nodes': entity_a})
        export_b = _make_export_dir(tmp_path, 'group_b', {'entity_nodes': entity_b})

        patch = diff_groups(export_a, export_b)

        # Inject a conflict into the patch manually
        patch['changes']['entity_nodes']['conflicts'] = [
            {'match': {'name': 'Alice', 'labels': ['Person']}, 'reason': 'changed in both'},
        ]

        target_data = {
            'entity_nodes': [entity_b[0]],
            'episodic_nodes': [],
            'community_nodes': [],
            'saga_nodes': [],
            'entity_edges': [],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }
        mock_driver = _make_mock_driver(target_data, embedding_dimension=3)

        # Test skip-conflicts strategy
        result_skip = await apply_patch(
            mock_driver, patch, 'group_a', 'group_b', strategy='skip-conflicts', dry_run=False
        )
        assert result_skip['conflicts'] == 1
        assert result_skip['modified'] == 0  # modification skipped

        # Test ours strategy (fresh driver) - ours skips conflicts (keeps target)
        target_data2 = {
            'entity_nodes': [entity_b[0]],
            'episodic_nodes': [],
            'community_nodes': [],
            'saga_nodes': [],
            'entity_edges': [],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }
        mock_driver2 = _make_mock_driver(target_data2, embedding_dimension=3)

        result_ours = await apply_patch(
            mock_driver2, patch, 'group_a', 'group_b', strategy='ours', dry_run=False
        )
        assert result_ours['modified'] == 0  # conflicted modification skipped by ours

        # Test theirs strategy (fresh driver) - theirs applies conflicts (uses patch)
        target_data3 = {
            'entity_nodes': [entity_b[0]],
            'episodic_nodes': [],
            'community_nodes': [],
            'saga_nodes': [],
            'entity_edges': [],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }
        mock_driver3 = _make_mock_driver(target_data3, embedding_dimension=3)

        result_theirs = await apply_patch(
            mock_driver3, patch, 'group_a', 'group_b', strategy='theirs', dry_run=False
        )
        assert result_theirs['modified'] == 1  # theirs applies the modification (uses patch data)


class TestE2ECascadeDelete:
    """E2E tests for cascade delete across related tables."""

    async def test_remove_entity_cascades_to_edges(self, tmp_path: Path) -> None:
        """Removing an entity_node cascades DELETE to entity_edges."""
        entity_a = [
            {
                'uuid': 'e1',
                'group_id': 'group_a',
                'name': 'Bob',
                'labels': ['Person'],
                'summary': 'To be removed',
            },
        ]
        edge_a = [
            {
                'uuid': 'ee1',
                'group_id': 'group_a',
                'source_node_uuid': 'e1',
                'target_node_uuid': 'e1',
                'name': 'KNOWS',
                'fact': 'self knows',
                'fact_embedding': None,
                'episodes': [],
                'expired_at': None,
                'valid_at': None,
                'invalid_at': None,
                'reference_time': None,
                'attributes': {},
                'created_at': '2025-01-01T00:00:00',
            },
        ]

        export_a = _make_export_dir(
            tmp_path,
            'group_a',
            {
                'entity_nodes': entity_a,
                'entity_edges': edge_a,
            },
        )
        export_b = _make_export_dir(
            tmp_path,
            'group_b',
            {  # Everything removed
                'entity_nodes': [],
                'entity_edges': [],
            },
        )

        patch = diff_groups(export_a, export_b)

        assert len(patch['changes']['entity_nodes']['removed']) == 1
        assert len(patch['changes']['entity_edges']['removed']) == 1

        # Apply: target has Bob and the edge
        target_data = {
            'entity_nodes': [entity_a[0]],
            'entity_edges': [edge_a[0]],
            'episodic_nodes': [],
            'community_nodes': [],
            'saga_nodes': [],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }
        # Override group_id in target to match to_group_id
        for row in target_data['entity_nodes']:
            row['group_id'] = 'group_b'
        for row in target_data['entity_edges']:
            row['group_id'] = 'group_b'
            row['source_node_uuid'] = 'e1'
            row['target_node_uuid'] = 'e1'

        mock_driver = _make_mock_driver(target_data, embedding_dimension=3)

        result = await apply_patch(
            mock_driver, patch, 'group_a', 'group_b', strategy='ours', dry_run=False
        )

        assert result['removed'] >= 1

        # Verify DELETE calls include both node and edge
        delete_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'DELETE FROM' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        deleted_uuids = {c.kwargs.get('params', {}).get('uuid') for c in delete_calls}
        assert 'e1' in deleted_uuids
        assert 'ee1' in deleted_uuids
