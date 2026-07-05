"""Tests for cli/remap.py - UUID remapping core."""

import json
from pathlib import Path

import pytest

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


@pytest.fixture()
def uuid_map() -> dict[str, str]:
    """Static UUID mapping for deterministic tests."""
    return {
        'old-entity-1': 'new-entity-1',
        'old-entity-2': 'new-entity-2',
        'old-episode-1': 'new-episode-1',
        'old-episode-2': 'new-episode-2',
        'old-community-1': 'new-community-1',
        'old-saga-1': 'new-saga-1',
        'old-edge-ee-1': 'new-edge-ee-1',
        'old-edge-ep-1': 'new-edge-ep-1',
        'old-edge-ce-1': 'new-edge-ce-1',
        'old-edge-he-1': 'new-edge-he-1',
        'old-edge-ne-1': 'new-edge-ne-1',
    }


@pytest.fixture()
def new_group_id() -> str:
    return 'new-group-id'


# ---------------------------------------------------------------------------
# generate_uuid_mappings
# ---------------------------------------------------------------------------


def test_generate_uuid_mappings(tmp_path: Path) -> None:
    """Phase 1 must scan every JSONL file and produce old->new mapping."""
    entity_file = tmp_path / 'entity_nodes.jsonl'
    episode_file = tmp_path / 'episodic_nodes.jsonl'

    entity_file.write_text(
        '\n'.join(
            [
                json.dumps({'uuid': 'aaa', 'name': 'A'}),
                json.dumps({'uuid': 'bbb', 'name': 'B'}),
            ]
        )
        + '\n'
    )
    episode_file.write_text(json.dumps({'uuid': 'ccc', 'content': 'episode'}) + '\n')

    mapping = generate_uuid_mappings([entity_file, episode_file])

    # Every original UUID must be present as a key
    assert set(mapping.keys()) == {'aaa', 'bbb', 'ccc'}
    # New UUIDs must be distinct (no collisions)
    assert len(set(mapping.values())) == 3
    # No old UUID may equal its replacement
    for old, new in mapping.items():
        assert old != new


def test_generate_uuid_mappings_empty_files(tmp_path: Path) -> None:
    """Empty JSONL files produce an empty mapping."""
    empty_file = tmp_path / 'empty.jsonl'
    empty_file.write_text('')
    assert generate_uuid_mappings([empty_file]) == {}


def test_generate_uuid_mappings_dedup(tmp_path: Path) -> None:
    """Duplicate UUIDs across files are mapped only once."""
    file1 = tmp_path / 'a.jsonl'
    file2 = tmp_path / 'b.jsonl'
    file1.write_text(json.dumps({'uuid': 'same-uuid'}) + '\n')
    file2.write_text(json.dumps({'uuid': 'same-uuid'}) + '\n')

    mapping = generate_uuid_mappings([file1, file2])
    assert 'same-uuid' in mapping
    assert len(mapping) == 1


# ---------------------------------------------------------------------------
# remap_entity_node
# ---------------------------------------------------------------------------


def test_remap_entity_node(uuid_map: dict, new_group_id: str) -> None:
    """Entity node: uuid and group_id replaced, all other fields preserved."""
    record = {
        'uuid': 'old-entity-1',
        'group_id': 'old-group',
        'name': 'Python',
        'name_norm': 'python',
        'summary': 'A programming language',
        'attributes': {'version': '3.12'},
        'embedding': [0.1, 0.2, 0.3],
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_entity_node(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-entity-1'
    assert result['group_id'] == new_group_id
    # Immutable fields
    assert result['name'] == 'Python'
    assert result['name_norm'] == 'python'
    assert result['summary'] == 'A programming language'
    assert result['attributes'] == {'version': '3.12'}
    assert result['embedding'] == [0.1, 0.2, 0.3]
    assert result['created_at'] == '2025-01-01T00:00:00Z'


# ---------------------------------------------------------------------------
# remap_entity_edge
# ---------------------------------------------------------------------------


def test_remap_entity_edge(uuid_map: dict, new_group_id: str) -> None:
    """Entity edge: uuid, group_id, source/target, episodes[] replaced."""
    record = {
        'uuid': 'old-edge-ee-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-entity-1',
        'target_node_uuid': 'old-entity-2',
        'name': 'RELATES_TO',
        'episodes': ['old-episode-1', 'old-episode-2'],
        'summary': 'edge summary',
        'embedding': [0.5],
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_entity_edge(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-edge-ee-1'
    assert result['group_id'] == new_group_id
    assert result['source_node_uuid'] == 'new-entity-1'
    assert result['target_node_uuid'] == 'new-entity-2'
    assert result['episodes'] == ['new-episode-1', 'new-episode-2']
    # Preserved
    assert result['name'] == 'RELATES_TO'
    assert result['summary'] == 'edge summary'
    assert result['embedding'] == [0.5]


# ---------------------------------------------------------------------------
# remap_episodic_node
# ---------------------------------------------------------------------------


def test_remap_episodic_node(uuid_map: dict, new_group_id: str) -> None:
    """Episodic node: uuid, group_id, entity_edges[] replaced."""
    record = {
        'uuid': 'old-episode-1',
        'group_id': 'old-group',
        'content': 'Episode content',
        'entity_edges': ['old-edge-ee-1'],
        'source': 'txt',
        'source_description': 'desc',
        'reference_time': '2025-01-01T00:00:00Z',
        'valid_at': '2025-01-01T00:00:00Z',
        'embedding': [0.1],
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_episodic_node(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-episode-1'
    assert result['group_id'] == new_group_id
    assert result['entity_edges'] == ['new-edge-ee-1']
    # Preserved
    assert result['content'] == 'Episode content'
    assert result['source'] == 'txt'
    assert result['reference_time'] == '2025-01-01T00:00:00Z'
    assert result['embedding'] == [0.1]


# ---------------------------------------------------------------------------
# remap_episodic_edge
# ---------------------------------------------------------------------------


def test_remap_episodic_edge(uuid_map: dict, new_group_id: str) -> None:
    """Episodic edge: uuid, group_id, source/target replaced."""
    record = {
        'uuid': 'old-edge-ep-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-episode-1',
        'target_node_uuid': 'old-entity-1',
        'name': 'MENTIONS',
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_episodic_edge(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-edge-ep-1'
    assert result['group_id'] == new_group_id
    assert result['source_node_uuid'] == 'new-episode-1'
    assert result['target_node_uuid'] == 'new-entity-1'
    assert result['name'] == 'MENTIONS'


# ---------------------------------------------------------------------------
# remap_community_node
# ---------------------------------------------------------------------------


def test_remap_community_node(uuid_map: dict, new_group_id: str) -> None:
    """Community node: only uuid and group_id replaced."""
    record = {
        'uuid': 'old-community-1',
        'group_id': 'old-group',
        'name': 'Cluster A',
        'summary': 'community summary',
        'embedding': [0.3],
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_community_node(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-community-1'
    assert result['group_id'] == new_group_id
    assert result['name'] == 'Cluster A'
    assert result['summary'] == 'community summary'


# ---------------------------------------------------------------------------
# remap_community_edge (polymorphic - source can be community or entity)
# ---------------------------------------------------------------------------


def test_remap_community_edge_from_community(uuid_map: dict, new_group_id: str) -> None:
    """Community edge with community source: source_node_uuid is a community."""
    record = {
        'uuid': 'old-edge-ce-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-community-1',
        'target_node_uuid': 'old-entity-1',
        'name': 'HAS_MEMBER',
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_community_edge(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-edge-ce-1'
    assert result['group_id'] == new_group_id
    assert result['source_node_uuid'] == 'new-community-1'
    assert result['target_node_uuid'] == 'new-entity-1'
    assert result['name'] == 'HAS_MEMBER'


# ---------------------------------------------------------------------------
# remap_saga_node (nullable episode references)
# ---------------------------------------------------------------------------


def test_remap_saga_node_with_episodes(uuid_map: dict, new_group_id: str) -> None:
    """Saga node with both episode refs: all remapped."""
    record = {
        'uuid': 'old-saga-1',
        'group_id': 'old-group',
        'name': 'Saga 1',
        'first_episode_uuid': 'old-episode-1',
        'last_episode_uuid': 'old-episode-2',
        'max_valid_at': '2025-06-01T00:00:00Z',
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_saga_node(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-saga-1'
    assert result['group_id'] == new_group_id
    assert result['first_episode_uuid'] == 'new-episode-1'
    assert result['last_episode_uuid'] == 'new-episode-2'
    assert result['name'] == 'Saga 1'


def test_remap_saga_node_null_episodes(uuid_map: dict, new_group_id: str) -> None:
    """Saga node with None episode refs stays None."""
    record = {
        'uuid': 'old-saga-1',
        'group_id': 'old-group',
        'name': 'Saga 1',
        'first_episode_uuid': None,
        'last_episode_uuid': None,
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_saga_node(record, uuid_map, new_group_id)

    assert result['first_episode_uuid'] is None
    assert result['last_episode_uuid'] is None


def test_remap_saga_node_missing_episodes(uuid_map: dict, new_group_id: str) -> None:
    """Saga node missing episode fields treated as None."""
    record = {
        'uuid': 'old-saga-1',
        'group_id': 'old-group',
        'name': 'Saga 1',
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_saga_node(record, uuid_map, new_group_id)

    assert result.get('first_episode_uuid') is None
    assert result.get('last_episode_uuid') is None


# ---------------------------------------------------------------------------
# remap_has_episode_edge / remap_next_episode_edge
# ---------------------------------------------------------------------------


def test_remap_has_episode_edge(uuid_map: dict, new_group_id: str) -> None:
    record = {
        'uuid': 'old-edge-he-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-saga-1',
        'target_node_uuid': 'old-episode-1',
        'name': 'HAS_EPISODE',
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_has_episode_edge(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-edge-he-1'
    assert result['group_id'] == new_group_id
    assert result['source_node_uuid'] == 'new-saga-1'
    assert result['target_node_uuid'] == 'new-episode-1'


def test_remap_next_episode_edge(uuid_map: dict, new_group_id: str) -> None:
    record = {
        'uuid': 'old-edge-ne-1',
        'group_id': 'old-group',
        'source_node_uuid': 'old-episode-1',
        'target_node_uuid': 'old-episode-2',
        'name': 'NEXT_EPISODE',
        'created_at': '2025-01-01T00:00:00Z',
    }

    result = remap_next_episode_edge(record, uuid_map, new_group_id)

    assert result['uuid'] == 'new-edge-ne-1'
    assert result['group_id'] == new_group_id
    assert result['source_node_uuid'] == 'new-episode-1'
    assert result['target_node_uuid'] == 'new-episode-2'


# ---------------------------------------------------------------------------
# Edge case: original record must not be mutated
# ---------------------------------------------------------------------------


def test_remap_does_not_mutate_original(uuid_map: dict, new_group_id: str) -> None:
    """Remap functions must return a new dict, not modify the input."""
    record = {
        'uuid': 'old-entity-1',
        'group_id': 'old-group',
        'name': 'Python',
    }
    original = dict(record)

    remap_entity_node(record, uuid_map, new_group_id)

    assert record == original
