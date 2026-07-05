"""Tests for cli/apply.py - Patch apply with conflict resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock

from cli.apply import apply_patch, get_cascade_deletes


def _make_driver(execute_results=None):
    """Create a mock driver that handles multi-query execution.

    Returns empty lists for all execute_query calls unless overridden.
    """
    mock = Mock()
    mock.schema = 'public'
    mock.embedding_dimension = 1024
    mock.build_indices_and_constraints = AsyncMock()
    mock.graph_ops = Mock()
    mock.graph_ops.rebuild_age_projection = AsyncMock()
    if execute_results is not None:
        mock.execute_query = AsyncMock(side_effect=execute_results)
    else:
        mock.execute_query = AsyncMock(return_value=([], None, []))
    return mock


class TestApplyPatch:
    """Tests for the apply_patch function."""

    async def test_apply_adds_records(self, tmp_path: Path) -> None:
        """Apply adds new records from patch."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [{'name': 'Charlie', 'labels': ['Person'], 'summary': 'Analyst'}],
                    'removed': [],
                    'modified': [],
                    'conflicts': [],
                }
            },
        }

        mock_driver = _make_driver()

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=False)

        insert_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'INSERT INTO' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        assert len(insert_calls) == 1
        assert result['added'] == 1
        assert result['removed'] == 0
        assert result['modified'] == 0

    async def test_apply_removes_records(self, tmp_path: Path) -> None:
        """Apply removes records by business key."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [],
                    'removed': [{'name': 'Bob', 'labels': ['Person']}],
                    'modified': [],
                    'conflicts': [],
                }
            },
        }

        bob_record = {
            'uuid': 'bob-uuid',
            'name': 'Bob',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Engineer',
        }
        target_response = ([bob_record], None, ['uuid', 'name', 'group_id', 'labels', 'summary'])
        empty = ([], None, [])
        # 9 for _load_group_data + target entity_nodes query + extras
        mock_driver = _make_driver(execute_results=[empty] * 9 + [target_response] + [empty] * 10)

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=False)

        assert result['removed'] == 1
        # Verify DELETE was called for Bob
        delete_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'DELETE FROM' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        assert len(delete_calls) >= 1

    async def test_apply_modifies_records(self, tmp_path: Path) -> None:
        """Apply modifies existing records."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [],
                    'removed': [],
                    'modified': [
                        {
                            'match': {'name': 'Alice', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'Engineer', 'new': 'Manager'}},
                        }
                    ],
                    'conflicts': [],
                }
            },
        }

        alice_record = {
            'uuid': 'alice-uuid',
            'name': 'Alice',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Engineer',
        }

        target_response = ([alice_record], None, ['uuid', 'name', 'group_id', 'labels', 'summary'])
        empty = ([], None, [])
        mock_driver = _make_driver(execute_results=[empty] * 9 + [target_response] + [empty] * 10)

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=False)

        assert result['modified'] == 1
        update_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'UPDATE' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        assert len(update_calls) >= 1

    async def test_dry_run_counts_but_does_not_apply(self, tmp_path: Path) -> None:
        """Dry run counts changes without applying."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [{'name': 'Charlie', 'labels': ['Person'], 'summary': 'A'}],
                    'removed': [{'name': 'Bob', 'labels': ['Person']}],
                    'modified': [
                        {
                            'match': {'name': 'Alice', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'E', 'new': 'M'}},
                        }
                    ],
                    'conflicts': [],
                }
            },
        }

        mock_driver = _make_driver()

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=True)

        assert result['dry_run'] is True
        assert result['added'] == 1
        assert result['removed'] == 1
        assert result['modified'] == 1
        # No DB operations called
        assert mock_driver.execute_query.call_count == 0

    async def test_strategy_ours_skips_conflicts(self, tmp_path: Path) -> None:
        """Ours strategy skips modifications for conflicting records (keeps target data)."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [],
                    'removed': [],
                    'modified': [
                        {
                            'match': {'name': 'Alice', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'E', 'new': 'M'}},
                        },
                        {
                            'match': {'name': 'Bob', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'X', 'new': 'Y'}},
                        },
                    ],
                    'conflicts': [
                        {'match': {'name': 'Alice', 'labels': ['Person']}, 'reason': 'both modified'},
                    ],
                }
            },
        }

        alice_record = {
            'uuid': 'alice-uuid',
            'name': 'Alice',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Engineer',
        }
        bob_record = {
            'uuid': 'bob-uuid',
            'name': 'Bob',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Developer',
        }
        target_response = (
            [alice_record, bob_record],
            None,
            ['uuid', 'name', 'group_id', 'labels', 'summary'],
        )
        empty = ([], None, [])
        mock_driver = _make_driver(execute_results=[empty] * 9 + [target_response] + [empty] * 10)

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=False)

        # Only Bob gets updated (Alice is conflicted, skipped by 'ours' strategy)
        assert result['modified'] == 1
        assert result['conflicts'] == 1
        # Only Bob's UPDATE should execute (Alice is conflicted, ours = keep target)
        update_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'UPDATE' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        assert len(update_calls) == 1

    async def test_strategy_skip_conflicts_ignores_all(self, tmp_path: Path) -> None:
        """skip-conflicts strategy handles conflicts gracefully."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [],
                    'removed': [],
                    'modified': [],
                    'conflicts': [{'match': {'name': 'Alice'}, 'reason': 'changed in both'}],
                }
            },
        }

        mock_driver = _make_driver()

        result = await apply_patch(
            mock_driver, patch, 'abc', 'xyz', strategy='skip-conflicts', dry_run=False
        )

        assert result['conflicts'] == 1

    async def test_apply_with_multiple_tables(self, tmp_path: Path) -> None:
        """Apply changes across multiple tables."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [{'name': 'New', 'labels': ['Person'], 'summary': 'X'}],
                    'removed': [],
                    'modified': [],
                    'conflicts': [],
                },
                'entity_edges': {
                    'added': [
                        {
                            'source_node_uuid': 'src',
                            'target_node_uuid': 'tgt',
                            'name': 'KNOWS',
                            'fact': 'knows',
                        }
                    ],
                    'removed': [],
                    'modified': [],
                    'conflicts': [],
                },
            },
        }

        mock_driver = _make_driver()

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=False)

        assert result['added'] >= 1

    async def test_remove_does_not_count_missing_record(self, tmp_path: Path) -> None:
        """Removed count only increments when record exists in target."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [],
                    'removed': [
                        {'name': 'Ghost', 'labels': ['Person']},
                        {'name': 'Bob', 'labels': ['Person']},
                    ],
                    'modified': [],
                    'conflicts': [],
                }
            },
        }

        # Only Bob exists in target, not Ghost
        bob_record = {
            'uuid': 'bob-uuid',
            'name': 'Bob',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Engineer',
        }
        target_response = ([bob_record], None, ['uuid', 'name', 'group_id', 'labels', 'summary'])
        empty = ([], None, [])
        mock_driver = _make_driver(execute_results=[empty] * 9 + [target_response] + [empty] * 10)

        result = await apply_patch(mock_driver, patch, 'abc', 'xyz', strategy='ours', dry_run=False)

        # Only Bob should be counted as removed
        assert result['removed'] == 1

    async def test_strategy_theirs_applies_conflict_modifications(self, tmp_path: Path) -> None:
        """Theirs strategy applies modifications for conflicting records (uses patch data)."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [],
                    'removed': [],
                    'modified': [
                        {
                            'match': {'name': 'Alice', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'E', 'new': 'M'}},
                        },
                        {
                            'match': {'name': 'Bob', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'X', 'new': 'Y'}},
                        },
                    ],
                    'conflicts': [
                        {'match': {'name': 'Alice', 'labels': ['Person']}, 'reason': 'both modified'},
                    ],
                }
            },
        }

        alice_record = {
            'uuid': 'alice-uuid',
            'name': 'Alice',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Engineer',
        }
        bob_record = {
            'uuid': 'bob-uuid',
            'name': 'Bob',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Developer',
        }
        target_response = (
            [alice_record, bob_record],
            None,
            ['uuid', 'name', 'group_id', 'labels', 'summary'],
        )
        empty = ([], None, [])
        mock_driver = _make_driver(execute_results=[empty] * 9 + [target_response] + [empty] * 10)

        result = await apply_patch(
            mock_driver, patch, 'abc', 'xyz', strategy='theirs', dry_run=False
        )

        # Both Alice and Bob get updated (theirs = apply patch data, including conflicts)
        assert result['modified'] == 2
        assert result['conflicts'] == 1
        # Both UPDATEs should execute (theirs = use their version)
        update_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'UPDATE' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        assert len(update_calls) == 2

    async def test_strategy_skip_conflicts_skips_table(self, tmp_path: Path) -> None:
        """skip-conflicts strategy skips entire table when conflicts exist."""
        patch = {
            'version': 1,
            'metadata': {'from_group_id': 'abc'},
            'changes': {
                'entity_nodes': {
                    'added': [{'name': 'Charlie', 'labels': ['Person'], 'summary': 'New'}],
                    'removed': [],
                    'modified': [
                        {
                            'match': {'name': 'Alice', 'labels': ['Person']},
                            'fields': {'summary': {'old': 'E', 'new': 'M'}},
                        },
                    ],
                    'conflicts': [
                        {'match': {'name': 'Alice', 'labels': ['Person']}, 'reason': 'both modified'},
                    ],
                },
                'episodic_nodes': {
                    'added': [{'content': 'Episode 1', 'valid_at': '2024-01-01T00:00:00Z'}],
                    'removed': [],
                    'modified': [],
                    'conflicts': [],
                },
            },
        }

        alice_record = {
            'uuid': 'alice-uuid',
            'name': 'Alice',
            'group_id': 'xyz',
            'labels': ['Person'],
            'summary': 'Engineer',
        }
        target_response = (
            [alice_record],
            None,
            ['uuid', 'name', 'group_id', 'labels', 'summary'],
        )
        empty = ([], None, [])
        # 9 for _load_group_data + entity_nodes target + episodic_nodes target + remaining extras
        mock_driver = _make_driver(
            execute_results=[empty] * 9 + [target_response] + [empty] + [empty] * 10
        )

        result = await apply_patch(
            mock_driver, patch, 'abc', 'xyz', strategy='skip-conflicts', dry_run=False
        )

        # entity_nodes table has conflicts → skipped entirely (no adds, no mods)
        # episodic_nodes has no conflicts → added should proceed
        assert result['added'] >= 1
        assert result['modified'] == 0
        assert result['conflicts'] == 1
        # No UPDATE calls at all since entity_nodes was skipped
        update_calls = [
            c
            for c in mock_driver.execute_query.call_args_list
            if 'UPDATE' in str(c.kwargs.get('query', c.args[0] if c.args else ''))
        ]
        assert len(update_calls) == 0


class TestCascadeDeletes:
    """Tests for cascade delete logic."""

    def test_delete_entity_cascades_to_edges(self):
        """Deleting entity_node cascades to entity_edges."""
        records = {
            'entity_edges': [
                {
                    'uuid': 'ed1',
                    'source_node_uuid': 'e1',
                    'target_node_uuid': 'e2',
                },
                {
                    'uuid': 'ed2',
                    'source_node_uuid': 'e2',
                    'target_node_uuid': 'e1',
                },
            ],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }

        deletes = get_cascade_deletes('entity_nodes', 'e1', records)
        deleted_tables = {t for t, _ in deletes}
        assert 'entity_nodes' in deleted_tables
        assert 'entity_edges' in deleted_tables

    def test_delete_episodic_node_cascades(self):
        """Deleting episodic_node cascades to related edges."""
        records = {
            'entity_edges': [],
            'episodic_edges': [
                {
                    'uuid': 'ee1',
                    'source_node_uuid': 'ep1',
                    'target_node_uuid': 'e1',
                },
            ],
            'has_episode_edges': [
                {
                    'uuid': 'he1',
                    'source_node_uuid': 's1',
                    'target_node_uuid': 'ep1',
                },
            ],
            'next_episode_edges': [
                {
                    'uuid': 'ne1',
                    'source_node_uuid': 'ep1',
                    'target_node_uuid': 'ep2',
                },
            ],
            'community_edges': [],
        }

        deletes = get_cascade_deletes('episodic_nodes', 'ep1', records)
        deleted_tables = {t for t, _ in deletes}

        assert 'episodic_nodes' in deleted_tables
        assert 'episodic_edges' in deleted_tables
        assert 'has_episode_edges' in deleted_tables
        assert 'next_episode_edges' in deleted_tables

    def test_delete_community_node_cascades(self):
        """Deleting community_node cascades to community_edges."""
        records = {
            'entity_edges': [],
            'episodic_edges': [],
            'community_edges': [
                {
                    'uuid': 'ce1',
                    'source_node_uuid': 'c1',
                    'target_node_uuid': 'e1',
                },
            ],
            'has_episode_edges': [],
            'next_episode_edges': [],
        }

        deletes = get_cascade_deletes('community_nodes', 'c1', records)
        deleted_tables = {t for t, _ in deletes}

        assert 'community_nodes' in deleted_tables
        assert 'community_edges' in deleted_tables

    def test_delete_saga_node_cascades_to_has_episode_edges(self):
        """Deleting saga_node cascades to has_episode_edges."""
        records = {
            'entity_edges': [],
            'episodic_edges': [],
            'community_edges': [],
            'has_episode_edges': [
                {
                    'uuid': 'he1',
                    'source_node_uuid': 'saga1',
                    'target_node_uuid': 'ep1',
                },
                {
                    'uuid': 'he2',
                    'source_node_uuid': 'saga1',
                    'target_node_uuid': 'ep2',
                },
                {
                    'uuid': 'he3',
                    'source_node_uuid': 'saga2',
                    'target_node_uuid': 'ep3',
                },
            ],
            'next_episode_edges': [],
        }

        deletes = get_cascade_deletes('saga_nodes', 'saga1', records)
        deleted_tables = {t for t, _ in deletes}

        assert 'saga_nodes' in deleted_tables
        assert 'has_episode_edges' in deleted_tables
        # Only saga1's edges are deleted, not saga2's
        deleted_uuids = {u for _, u in deletes}
        assert 'he1' in deleted_uuids
        assert 'he2' in deleted_uuids
        assert 'he3' not in deleted_uuids
