from datetime import datetime, timezone

from graphiti_core.driver.postgres_age.records import (
    community_edge_from_row,
    community_node_from_row,
    entity_edge_from_row,
    entity_node_from_row,
    episodic_edge_from_row,
    episodic_node_from_row,
    has_episode_edge_from_row,
    next_episode_edge_from_row,
    saga_node_from_row,
)
from graphiti_core.driver.postgres_age.serialization import (
    community_edge_to_row,
    community_node_to_row,
    entity_edge_to_row,
    entity_node_to_row,
    episodic_edge_to_row,
    episodic_node_to_row,
    has_episode_edge_to_row,
    next_episode_edge_to_row,
    saga_node_to_row,
)
from graphiti_core.edges import (
    CommunityEdge,
    EntityEdge,
    EpisodicEdge,
    HasEpisodeEdge,
    NextEpisodeEdge,
)
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode, SagaNode

CREATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
VALID_AT = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)


def test_entity_node_round_trip_preserves_attributes_labels_and_embedding():
    node = EntityNode(
        uuid='node-1',
        name='Alice',
        group_id='main',
        labels=['Person'],
        summary='Engineer',
        attributes={'role': 'staff'},
        name_embedding=[0.1, 0.2, 0.3],
        created_at=CREATED_AT,
    )

    row = entity_node_to_row(node)
    original_row = dict(row)
    hydrated = entity_node_from_row(row)

    assert row == original_row
    assert hydrated.uuid == node.uuid
    assert hydrated.labels == ['Person']
    assert hydrated.attributes == {'role': 'staff'}
    assert hydrated.name_embedding == [0.1, 0.2, 0.3]


def test_episodic_node_round_trip_preserves_metadata_and_source_value():
    node = EpisodicNode(
        uuid='episode-1',
        name='Episode',
        group_id='main',
        source=EpisodeType.message,
        source_description='chat',
        content='Alice likes Bob',
        valid_at=VALID_AT,
        entity_edges=['edge-1'],
        episode_metadata={'channel': 'test'},
        created_at=CREATED_AT,
    )

    row = episodic_node_to_row(node)
    hydrated = episodic_node_from_row(row)

    assert row['source'] == 'message'
    assert hydrated.source == EpisodeType.message
    assert hydrated.episode_metadata == {'channel': 'test'}
    assert hydrated.entity_edges == ['edge-1']


def test_community_and_saga_nodes_round_trip():
    community = CommunityNode(
        uuid='community-1',
        name='Team',
        group_id='main',
        summary='A team',
        name_embedding=[0.4, 0.5],
        created_at=CREATED_AT,
    )
    saga = SagaNode(
        uuid='saga-1',
        name='Daily',
        group_id='main',
        summary='Summary',
        first_episode_uuid='episode-1',
        last_episode_uuid='episode-2',
        last_summarized_at=CREATED_AT,
        last_summarized_episode_valid_at=VALID_AT,
        created_at=CREATED_AT,
    )

    assert community_node_from_row(community_node_to_row(community)) == community
    assert saga_node_from_row(saga_node_to_row(saga)) == saga


def test_entity_edge_round_trip_preserves_temporal_fields_attributes_and_embedding():
    edge = EntityEdge(
        uuid='edge-1',
        group_id='main',
        source_node_uuid='alice',
        target_node_uuid='bob',
        name='LIKES',
        fact='Alice likes Bob',
        fact_embedding=[0.6, 0.7],
        episodes=['episode-1'],
        expired_at=None,
        valid_at=VALID_AT,
        invalid_at=None,
        reference_time=VALID_AT,
        attributes={'confidence': 0.9},
        created_at=CREATED_AT,
    )

    row = entity_edge_to_row(edge)
    original_attributes = dict(row['attributes'])
    hydrated = entity_edge_from_row(row)

    assert row['attributes'] == original_attributes
    assert hydrated.uuid == edge.uuid
    assert hydrated.fact_embedding == [0.6, 0.7]
    assert hydrated.attributes == {'confidence': 0.9}
    assert hydrated.valid_at == VALID_AT
    assert hydrated.reference_time == VALID_AT


def test_simple_edges_round_trip():
    edge_kwargs = {
        'uuid': 'edge-1',
        'group_id': 'main',
        'source_node_uuid': 'source',
        'target_node_uuid': 'target',
        'created_at': CREATED_AT,
    }

    assert episodic_edge_from_row(episodic_edge_to_row(EpisodicEdge(**edge_kwargs))).model_dump() == (
        EpisodicEdge(**edge_kwargs).model_dump()
    )
    assert community_edge_from_row(community_edge_to_row(CommunityEdge(**edge_kwargs))).model_dump() == (
        CommunityEdge(**edge_kwargs).model_dump()
    )
    assert has_episode_edge_from_row(
        has_episode_edge_to_row(HasEpisodeEdge(**edge_kwargs))
    ).model_dump() == HasEpisodeEdge(**edge_kwargs).model_dump()
    assert next_episode_edge_from_row(
        next_episode_edge_to_row(NextEpisodeEdge(**edge_kwargs))
    ).model_dump() == NextEpisodeEdge(**edge_kwargs).model_dump()
