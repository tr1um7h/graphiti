"""Tests for cli/diff.py - Semantic diff between two export directories."""

from __future__ import annotations

import json
from pathlib import Path

from cli.diff import (
    build_index,
    compare_fields,
    diff_groups,
    extract_match_fields,
    get_business_key,
    load_jsonl,
)

# ---------------------------------------------------------------------------
# Helpers for building test fixtures
# ---------------------------------------------------------------------------

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


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open('w', encoding='utf-8') as fh:
        for rec in records:
            fh.write(json.dumps(rec) + '\n')


def _write_metadata(path: Path, group_id: str) -> None:
    metadata = {
        'group_id': group_id,
        'exported_at': '2026-07-05T12:00:00+00:00',
        'schema': 'public',
        'embedding_dimension': 3,
        'schema_version': 1,
        'counts': {},
    }
    (path / 'metadata.json').write_text(json.dumps(metadata) + '\n', encoding='utf-8')


def _make_export_dir(tmp_path: Path, group_id: str, tables: dict[str, list[dict]]) -> Path:
    """Create a minimal export directory with given table data."""
    export_dir = tmp_path / f'export_{group_id}'
    export_dir.mkdir(parents=True, exist_ok=True)
    _write_metadata(export_dir, group_id)
    for table_name in ALL_TABLES:
        records = tables.get(table_name, [])
        _write_jsonl(export_dir / f'{table_name}.jsonl', records)
    return export_dir


# ---------------------------------------------------------------------------
# Test 1: get_business_key for each table type
# ---------------------------------------------------------------------------


class TestGetBusinessKey:
    def test_entity_nodes(self) -> None:
        record = {'uuid': 'u1', 'name': 'Alice', 'labels': ['Person']}
        key = get_business_key(record, 'entity_nodes')
        assert key == ('Alice', ('Person',))

    def test_entity_nodes_multi_labels(self) -> None:
        record = {'name': 'Bob', 'labels': ['Org', 'Company']}
        key = get_business_key(record, 'entity_nodes')
        assert key == ('Bob', ('Org', 'Company'))

    def test_episodic_nodes(self) -> None:
        record = {'valid_at': '2026-01-01T00:00:00+00:00', 'content': 'Hello world'}
        key = get_business_key(record, 'episodic_nodes')
        # sha256('Hello world')[:12] is deterministic
        import hashlib

        expected_hash = hashlib.sha256(b'Hello world').hexdigest()[:12]
        assert key == ('2026-01-01T00:00:00+00:00', expected_hash)

    def test_community_nodes(self) -> None:
        record = {'name': 'Cluster A'}
        key = get_business_key(record, 'community_nodes')
        assert key == ('Cluster A',)

    def test_saga_nodes(self) -> None:
        record = {'name': 'Story 1'}
        key = get_business_key(record, 'saga_nodes')
        assert key == ('Story 1',)

    def test_entity_edges(self) -> None:
        # After fix: edge tables use semantic fields (not UUIDs)
        record = {'source_name': 'Alice', 'target_name': 'Bob', 'name': 'KNOWS'}
        key = get_business_key(record, 'entity_edges')
        assert key == ('Alice', 'Bob', 'KNOWS')

    def test_episodic_edges(self) -> None:
        # episodic_edges: source is episodic (no name, use content hash), target is entity
        record = {'source_content_hash': 'abc123', 'target_name': 'Bob'}
        key = get_business_key(record, 'episodic_edges')
        assert key == ('abc123', 'Bob')

    def test_community_edges(self) -> None:
        # community_edges: both source and target have names
        record = {'source_name': 'Cluster A', 'target_name': 'Alice'}
        key = get_business_key(record, 'community_edges')
        assert key == ('Cluster A', 'Alice')

    def test_has_episode_edges(self) -> None:
        # has_episode_edges: source is saga (has name), target is episodic (content hash)
        record = {'source_name': 'Story 1', 'target_content_hash': 'def456'}
        key = get_business_key(record, 'has_episode_edges')
        assert key == ('Story 1', 'def456')

    def test_next_episode_edges(self) -> None:
        # next_episode_edges: both are episodic (content hash)
        record = {'source_content_hash': 'abc123', 'target_content_hash': 'def456'}
        key = get_business_key(record, 'next_episode_edges')
        assert key == ('abc123', 'def456')


# ---------------------------------------------------------------------------
# Test: load_jsonl
# ---------------------------------------------------------------------------


class TestLoadJsonl:
    def test_load_records(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / 'test.jsonl'
        _write_jsonl(jsonl_path, [{'a': 1}, {'a': 2}])
        records = load_jsonl(jsonl_path)
        assert records == [{'a': 1}, {'a': 2}]

    def test_load_skips_blank_lines(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / 'test.jsonl'
        jsonl_path.write_text('{"a": 1}\n\n{"a": 2}\n\n', encoding='utf-8')
        records = load_jsonl(jsonl_path)
        assert len(records) == 2

    def test_load_empty_file(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / 'test.jsonl'
        jsonl_path.write_text('', encoding='utf-8')
        records = load_jsonl(jsonl_path)
        assert records == []


# ---------------------------------------------------------------------------
# Test: build_index
# ---------------------------------------------------------------------------


class TestBuildIndex:
    def test_build_index_entity_nodes(self) -> None:
        records = [
            {'name': 'Alice', 'labels': ['Person'], 'summary': 'Eng'},
            {'name': 'Bob', 'labels': ['Person'], 'summary': 'Des'},
        ]
        index = build_index(records, 'entity_nodes')
        assert ('Alice', ('Person',)) in index
        assert ('Bob', ('Person',)) in index
        assert index[('Alice', ('Person',))]['summary'] == 'Eng'

    def test_build_index_duplicate_key_last_wins(self) -> None:
        records = [
            {'name': 'Alice', 'labels': ['Person'], 'summary': 'v1'},
            {'name': 'Alice', 'labels': ['Person'], 'summary': 'v2'},
        ]
        index = build_index(records, 'entity_nodes')
        assert index[('Alice', ('Person',))]['summary'] == 'v2'


# ---------------------------------------------------------------------------
# Test: compare_fields
# ---------------------------------------------------------------------------


class TestCompareFields:
    def test_identical_records(self) -> None:
        record = {'name': 'Alice', 'labels': ['Person'], 'summary': 'Eng'}
        assert compare_fields(record, record) == {}

    def test_modified_field(self) -> None:
        left = {'name': 'Alice', 'summary': 'Engineer'}
        right = {'name': 'Alice', 'summary': 'Manager'}
        result = compare_fields(left, right)
        assert result == {'summary': {'old': 'Engineer', 'new': 'Manager'}}

    def test_ignores_identity_fields(self) -> None:
        left = {
            'uuid': 'u1',
            'group_id': 'g1',
            'source_node_uuid': 's1',
            'target_node_uuid': 't1',
            'episodes': ['e1'],
            'entity_edges': ['ee1'],
            'first_episode_uuid': 'fe1',
            'last_episode_uuid': 'le1',
            'created_at': '2026-01-01',
            'summary': 'same',
        }
        right = {
            'uuid': 'u2',
            'group_id': 'g2',
            'source_node_uuid': 's2',
            'target_node_uuid': 't2',
            'episodes': ['e2'],
            'entity_edges': ['ee2'],
            'first_episode_uuid': 'fe2',
            'last_episode_uuid': 'le2',
            'created_at': '2026-02-01',
            'summary': 'same',
        }
        assert compare_fields(left, right) == {}

    def test_detects_real_change_among_ignored(self) -> None:
        left = {'uuid': 'u1', 'group_id': 'g1', 'name': 'Alice', 'summary': 'Eng'}
        right = {'uuid': 'u2', 'group_id': 'g2', 'name': 'Alice', 'summary': 'Manager'}
        result = compare_fields(left, right)
        assert result == {'summary': {'old': 'Eng', 'new': 'Manager'}}

    def test_new_field_appears(self) -> None:
        left = {'name': 'Alice'}
        right = {'name': 'Alice', 'summary': 'Manager'}
        result = compare_fields(left, right)
        assert result == {'summary': {'old': None, 'new': 'Manager'}}

    def test_field_removed(self) -> None:
        left = {'name': 'Alice', 'summary': 'Eng'}
        right = {'name': 'Alice'}
        result = compare_fields(left, right)
        assert result == {'summary': {'old': 'Eng', 'new': None}}

    def test_nested_dict_comparison(self) -> None:
        """compare_fields detects changes in nested dict values."""
        left = {'name': 'Alice', 'attributes': {'version': '1.0', 'lang': 'en'}}
        right = {'name': 'Alice', 'attributes': {'version': '2.0', 'lang': 'en'}}
        result = compare_fields(left, right)
        assert 'attributes' in result
        assert result['attributes']['old'] == {'version': '1.0', 'lang': 'en'}
        assert result['attributes']['new'] == {'version': '2.0', 'lang': 'en'}

    def test_nested_list_comparison(self) -> None:
        """compare_fields detects changes in list values."""
        left = {'name': 'Alice', 'labels': ['Person', 'Employee']}
        right = {'name': 'Alice', 'labels': ['Person', 'Manager']}
        result = compare_fields(left, right)
        assert 'labels' in result
        assert result['labels']['old'] == ['Person', 'Employee']
        assert result['labels']['new'] == ['Person', 'Manager']

    def test_none_vs_empty_list(self) -> None:
        """None and empty list are correctly detected as different."""
        left = {'name': 'Alice', 'labels': None}
        right = {'name': 'Alice', 'labels': []}
        result = compare_fields(left, right)
        assert result == {'labels': {'old': None, 'new': []}}

    def test_falsey_values_compared_correctly(self) -> None:
        """0, False, empty string are compared by value, not truthiness."""
        left = {'name': 'Alice', 'count': 0, 'active': False, 'note': ''}
        right = {'name': 'Alice', 'count': 1, 'active': True, 'note': 'x'}
        result = compare_fields(left, right)
        assert result == {
            'count': {'old': 0, 'new': 1},
            'active': {'old': False, 'new': True},
            'note': {'old': '', 'new': 'x'},
        }


# ---------------------------------------------------------------------------
# Test: extract_match_fields
# ---------------------------------------------------------------------------


class TestExtractMatchFields:
    def test_entity_nodes(self) -> None:
        record = {'name': 'Alice', 'labels': ['Person'], 'summary': 'Eng', 'uuid': 'u1'}
        result = extract_match_fields(record, 'entity_nodes')
        assert result == {'name': 'Alice', 'labels': ['Person']}

    def test_entity_edges(self) -> None:
        # After fix: edge tables use semantic fields (not UUIDs)
        record = {
            'source_name': 'Alice',
            'target_name': 'Bob',
            'name': 'KNOWS',
            'uuid': 'u1',
        }
        result = extract_match_fields(record, 'entity_edges')
        assert result == {
            'source_name': 'Alice',
            'target_name': 'Bob',
            'name': 'KNOWS',
        }

    def test_episodic_edges(self) -> None:
        # episodic_edges: source is episodic (content hash), target is entity (name)
        record = {
            'source_content_hash': 'abc123',
            'target_name': 'Bob',
            'uuid': 'u1',
        }
        result = extract_match_fields(record, 'episodic_edges')
        assert result == {
            'source_content_hash': 'abc123',
            'target_name': 'Bob',
        }

    def test_community_edges(self) -> None:
        # community_edges: both source and target have names
        record = {
            'source_name': 'Cluster A',
            'target_name': 'Alice',
            'uuid': 'u1',
        }
        result = extract_match_fields(record, 'community_edges')
        assert result == {
            'source_name': 'Cluster A',
            'target_name': 'Alice',
        }

    def test_has_episode_edges(self) -> None:
        # has_episode_edges: source is saga (has name), target is episodic (content hash)
        record = {
            'source_name': 'Story 1',
            'target_content_hash': 'def456',
            'uuid': 'u1',
        }
        result = extract_match_fields(record, 'has_episode_edges')
        assert result == {
            'source_name': 'Story 1',
            'target_content_hash': 'def456',
        }

    def test_next_episode_edges(self) -> None:
        # next_episode_edges: both are episodic (content hash)
        record = {
            'source_content_hash': 'abc123',
            'target_content_hash': 'def456',
            'uuid': 'u1',
        }
        result = extract_match_fields(record, 'next_episode_edges')
        assert result == {
            'source_content_hash': 'abc123',
            'target_content_hash': 'def456',
        }


# ---------------------------------------------------------------------------
# Test 2-7: diff_groups integration tests
# ---------------------------------------------------------------------------


class TestDiffGroups:
    def test_empty_directories(self, tmp_path: Path) -> None:
        """Test 6: Empty directories produce empty changes."""
        left = _make_export_dir(tmp_path, 'g_left', {})
        right = _make_export_dir(tmp_path, 'g_right', {})

        patch = diff_groups(left, right)

        assert patch['version'] == 1
        assert patch['metadata']['from_group_id'] == 'g_left'
        assert patch['metadata']['to_group_id'] == 'g_right'
        assert 'created_at' in patch['metadata']

        for table_name in ALL_TABLES:
            changes = patch['changes'][table_name]
            assert changes['added'] == []
            assert changes['removed'] == []
            assert changes['modified'] == []
            assert changes['conflicts'] == []

    def test_added_records(self, tmp_path: Path) -> None:
        """Test 2: Diff detects added records."""
        left = _make_export_dir(tmp_path, 'g_left', {'entity_nodes': []})
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u1',
                        'group_id': 'g_right',
                        'name': 'Charlie',
                        'labels': ['Person'],
                        'summary': 'Designer',
                    }
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['entity_nodes']

        assert len(changes['added']) == 1
        added = changes['added'][0]
        assert added['name'] == 'Charlie'
        assert added['labels'] == ['Person']
        assert added['summary'] == 'Designer'
        # Ignored fields should not be in added
        assert 'uuid' not in added
        assert 'group_id' not in added

        assert changes['removed'] == []
        assert changes['modified'] == []

    def test_removed_records(self, tmp_path: Path) -> None:
        """Test 3: Diff detects removed records."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u1',
                        'group_id': 'g_left',
                        'name': 'Bob',
                        'labels': ['Person'],
                        'summary': 'Analyst',
                    }
                ]
            },
        )
        right = _make_export_dir(tmp_path, 'g_right', {'entity_nodes': []})

        patch = diff_groups(left, right)
        changes = patch['changes']['entity_nodes']

        assert len(changes['removed']) == 1
        removed = changes['removed'][0]
        assert removed['name'] == 'Bob'
        assert removed['summary'] == 'Analyst'
        assert 'uuid' not in removed
        assert 'group_id' not in removed

        assert changes['added'] == []
        assert changes['modified'] == []

    def test_modified_records(self, tmp_path: Path) -> None:
        """Test 4: Diff detects modified records."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u1',
                        'group_id': 'g_left',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Engineer',
                    }
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u2',
                        'group_id': 'g_right',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Manager',
                    }
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['entity_nodes']

        assert changes['added'] == []
        assert changes['removed'] == []
        assert len(changes['modified']) == 1

        mod = changes['modified'][0]
        assert mod['match'] == {'name': 'Alice', 'labels': ['Person']}
        assert mod['fields'] == {'summary': {'old': 'Engineer', 'new': 'Manager'}}

    def test_ignores_identity_fields(self, tmp_path: Path) -> None:
        """Test 5: Diff ignores identity/reference fields — only real changes appear."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u1',
                        'group_id': 'g_left',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Same',
                        'created_at': '2026-01-01',
                    }
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u2',
                        'group_id': 'g_right',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Same',
                        'created_at': '2026-07-01',
                    }
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['entity_nodes']

        # No modifications because only identity fields differ
        assert changes['modified'] == []
        assert changes['added'] == []
        assert changes['removed'] == []

    def test_mixed_changes(self, tmp_path: Path) -> None:
        """Test 7: Full diff with mixed changes (add + remove + modify)."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u1',
                        'group_id': 'g_left',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Eng',
                    },
                    {
                        'uuid': 'u2',
                        'group_id': 'g_left',
                        'name': 'Bob',
                        'labels': ['Person'],
                        'summary': 'Des',
                    },
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_nodes': [
                    # Alice modified
                    {
                        'uuid': 'u3',
                        'group_id': 'g_right',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Manager',
                    },
                    # Charlie added
                    {
                        'uuid': 'u4',
                        'group_id': 'g_right',
                        'name': 'Charlie',
                        'labels': ['Person'],
                        'summary': 'VP',
                    },
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['entity_nodes']

        # Bob removed
        assert len(changes['removed']) == 1
        assert changes['removed'][0]['name'] == 'Bob'

        # Charlie added
        assert len(changes['added']) == 1
        assert changes['added'][0]['name'] == 'Charlie'

        # Alice modified
        assert len(changes['modified']) == 1
        assert changes['modified'][0]['match'] == {'name': 'Alice', 'labels': ['Person']}
        assert changes['modified'][0]['fields'] == {'summary': {'old': 'Eng', 'new': 'Manager'}}

    def test_edge_table_diff(self, tmp_path: Path) -> None:
        """Test 8: Edge table diff using semantic fields as business keys."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'entity_edges': [
                    {
                        'uuid': 'e1',
                        'group_id': 'g_left',
                        'source_name': 'Alice',
                        'target_name': 'Bob',
                        'name': 'KNOWS',
                        'fact': 'Alice knows Bob',
                    },
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_edges': [
                    # Same edge, modified fact
                    {
                        'uuid': 'e2',
                        'group_id': 'g_right',
                        'source_name': 'Alice',
                        'target_name': 'Bob',
                        'name': 'KNOWS',
                        'fact': 'Alice knows Bob well',
                    },
                    # New edge
                    {
                        'uuid': 'e3',
                        'group_id': 'g_right',
                        'source_name': 'Charlie',
                        'target_name': 'Dave',
                        'name': 'LIKES',
                        'fact': 'Charlie likes Dave',
                    },
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['entity_edges']

        # New edge added
        assert len(changes['added']) == 1
        assert changes['added'][0]['name'] == 'LIKES'
        # Identity fields stripped
        assert 'uuid' not in changes['added'][0]
        assert 'group_id' not in changes['added'][0]
        assert 'source_node_uuid' not in changes['added'][0]
        assert 'target_node_uuid' not in changes['added'][0]

        # Existing edge modified
        assert len(changes['modified']) == 1
        mod = changes['modified'][0]
        # Match uses semantic fields (names, not UUIDs)
        assert mod['match'] == {
            'source_name': 'Alice',
            'target_name': 'Bob',
            'name': 'KNOWS',
        }
        assert mod['fields'] == {'fact': {'old': 'Alice knows Bob', 'new': 'Alice knows Bob well'}}

        assert changes['removed'] == []

    def test_community_nodes_diff(self, tmp_path: Path) -> None:
        """Community nodes keyed by name only."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'community_nodes': [
                    {'uuid': 'c1', 'group_id': 'g1', 'name': 'Cluster', 'summary': 'v1'},
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'community_nodes': [
                    {'uuid': 'c2', 'group_id': 'g2', 'name': 'Cluster', 'summary': 'v2'},
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['community_nodes']
        assert len(changes['modified']) == 1
        assert changes['modified'][0]['match'] == {'name': 'Cluster'}
        assert changes['modified'][0]['fields'] == {'summary': {'old': 'v1', 'new': 'v2'}}

    def test_episodic_nodes_diff(self, tmp_path: Path) -> None:
        """Episodic nodes keyed by (valid_at, content_hash)."""
        content = 'Episode content'
        valid_at = '2026-01-01T00:00:00+00:00'

        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'episodic_nodes': [
                    {
                        'uuid': 'ep1',
                        'group_id': 'g1',
                        'valid_at': valid_at,
                        'content': content,
                        'source_description': 'old',
                    },
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'episodic_nodes': [
                    {
                        'uuid': 'ep2',
                        'group_id': 'g2',
                        'valid_at': valid_at,
                        'content': content,
                        'source_description': 'new',
                    },
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['episodic_nodes']
        assert len(changes['modified']) == 1
        mod = changes['modified'][0]
        assert mod['match']['valid_at'] == valid_at
        assert mod['fields'] == {'source_description': {'old': 'old', 'new': 'new'}}

    def test_multiple_tables_with_changes(self, tmp_path: Path) -> None:
        """Changes across multiple tables are independently detected."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u1',
                        'group_id': 'g1',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Eng',
                    },
                ],
                'saga_nodes': [
                    {'uuid': 'sg1', 'group_id': 'g1', 'name': 'OldSaga'},
                ],
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_nodes': [
                    {
                        'uuid': 'u2',
                        'group_id': 'g2',
                        'name': 'Alice',
                        'labels': ['Person'],
                        'summary': 'Eng',
                    },
                ],
                'saga_nodes': [
                    {'uuid': 'sg2', 'group_id': 'g2', 'name': 'NewSaga'},
                ],
            },
        )

        patch = diff_groups(left, right)

        # entity_nodes: unchanged
        entity_changes = patch['changes']['entity_nodes']
        assert entity_changes['added'] == []
        assert entity_changes['removed'] == []
        assert entity_changes['modified'] == []

        # saga_nodes: removed OldSaga, added NewSaga
        saga_changes = patch['changes']['saga_nodes']
        assert len(saga_changes['added']) == 1
        assert saga_changes['added'][0]['name'] == 'NewSaga'
        assert len(saga_changes['removed']) == 1
        assert saga_changes['removed'][0]['name'] == 'OldSaga'

    def test_added_record_strips_all_ignored_fields(self, tmp_path: Path) -> None:
        """Added records must strip ALL ignored fields, not just uuid/group_id."""
        left = _make_export_dir(tmp_path, 'g_left', {'entity_edges': []})
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'entity_edges': [
                    {
                        'uuid': 'e1',
                        'group_id': 'g_right',
                        'source_node_uuid': 's1',
                        'target_node_uuid': 't1',
                        'name': 'KNOWS',
                        'fact': 'A knows B',
                        'episodes': ['ep1', 'ep2'],
                        'created_at': '2026-01-01',
                    }
                ]
            },
        )

        patch = diff_groups(left, right)
        added = patch['changes']['entity_edges']['added'][0]

        assert 'uuid' not in added
        assert 'group_id' not in added
        assert 'source_node_uuid' not in added
        assert 'target_node_uuid' not in added
        assert 'episodes' not in added
        assert 'created_at' not in added
        # But non-ignored fields remain
        assert added['name'] == 'KNOWS'
        assert added['fact'] == 'A knows B'

    def test_community_edges_diff(self, tmp_path: Path) -> None:
        """Community edges diff detects added/removed by (source_name, target_name) key."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'community_edges': [
                    {
                        'uuid': 'ce1', 'group_id': 'g_left',
                        'source_name': 'Cluster A', 'target_name': 'Alice',
                        'name': 'HAS_MEMBER', 'fact': 'old fact',
                    },
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'community_edges': [
                    {
                        'uuid': 'ce2', 'group_id': 'g_right',
                        'source_name': 'Cluster B', 'target_name': 'Bob',
                        'name': 'NEW_EDGE', 'fact': 'new fact',
                    },
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['community_edges']

        assert len(changes['added']) == 1
        assert len(changes['removed']) == 1
        assert changes['added'][0]['name'] == 'NEW_EDGE'
        assert changes['removed'][0]['name'] == 'HAS_MEMBER'

    def test_episodic_edges_diff(self, tmp_path: Path) -> None:
        """Episodic edges diff uses (source_content_hash, target_name) business key."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'episodic_edges': [
                    {'uuid': 'ee1', 'group_id': 'g_left',
                     'source_content_hash': 'hash1', 'target_name': 'Alice'},
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'episodic_edges': [
                    # Same key, no change
                    {'uuid': 'ee2', 'group_id': 'g_right',
                     'source_content_hash': 'hash1', 'target_name': 'Alice'},
                    # Different key
                    {'uuid': 'ee3', 'group_id': 'g_right',
                     'source_content_hash': 'hash2', 'target_name': 'Bob'},
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['episodic_edges']

        # One new edge added, zero removed
        assert len(changes['added']) == 1
        assert len(changes['removed']) == 0
        assert len(changes['modified']) == 0

    def test_has_episode_edges_diff(self, tmp_path: Path) -> None:
        """has_episode_edges diff uses (source_name, target_content_hash) key."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'has_episode_edges': [
                    {'uuid': 'he1', 'group_id': 'g_left',
                     'source_name': 'Story 1', 'target_content_hash': 'hash1'},
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'has_episode_edges': [
                    # Same key → no change
                    {'uuid': 'he2', 'group_id': 'g_right',
                     'source_name': 'Story 1', 'target_content_hash': 'hash1'},
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['has_episode_edges']

        # Identical business key → no changes
        assert changes['added'] == []
        assert changes['removed'] == []
        assert changes['modified'] == []

    def test_next_episode_edges_diff(self, tmp_path: Path) -> None:
        """next_episode_edges diff detects changes by (source_content_hash, target_content_hash) key."""
        left = _make_export_dir(
            tmp_path,
            'g_left',
            {
                'next_episode_edges': [
                    {'uuid': 'ne1', 'group_id': 'g_left',
                     'source_content_hash': 'hash1', 'target_content_hash': 'hash2'},
                ]
            },
        )
        right = _make_export_dir(
            tmp_path,
            'g_right',
            {
                'next_episode_edges': [
                    # Different target → different key
                    {'uuid': 'ne2', 'group_id': 'g_right',
                     'source_content_hash': 'hash1', 'target_content_hash': 'hash3'},
                ]
            },
        )

        patch = diff_groups(left, right)
        changes = patch['changes']['next_episode_edges']

        assert len(changes['added']) == 1
        assert len(changes['removed']) == 1
