from datetime import datetime, timezone

import pytest

from graphiti_core.edges import (
    CommunityEdge,
    EntityEdge,
    EpisodicEdge,
    HasEpisodeEdge,
    NextEpisodeEdge,
)
from graphiti_core.errors import EdgeNotFoundError, NodeNotFoundError
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode, SagaNode

CREATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
VALID_AT = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)


async def _seed_nodes(postgres_age_driver):
    entity_a = EntityNode(
        uuid='entity-a',
        name='Alice',
        group_id='main',
        labels=['Person'],
        created_at=CREATED_AT,
    )
    entity_b = EntityNode(
        uuid='entity-b',
        name='Bob',
        group_id='main',
        labels=['Person'],
        created_at=CREATED_AT,
    )
    episode = EpisodicNode(
        uuid='episode-1',
        name='episode one',
        group_id='main',
        source=EpisodeType.message,
        source_description='chat',
        content='Alice likes Bob',
        valid_at=VALID_AT,
        created_at=CREATED_AT,
    )
    community = CommunityNode(
        uuid='community-1',
        name='People',
        group_id='main',
        created_at=CREATED_AT,
    )
    community_two = CommunityNode(
        uuid='community-2',
        name='People Nested',
        group_id='main',
        created_at=CREATED_AT,
    )
    saga = SagaNode(
        uuid='saga-1',
        name='Daily Standup',
        group_id='main',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.entity_node_ops.save_bulk(postgres_age_driver, [entity_a, entity_b])
    await postgres_age_driver.episode_node_ops.save(postgres_age_driver, episode)
    await postgres_age_driver.community_node_ops.save_bulk(
        postgres_age_driver, [community, community_two]
    )
    await postgres_age_driver.saga_node_ops.save(postgres_age_driver, saga)


@pytest.mark.integration
async def test_entity_edge_ops_save_query_embedding_projection_and_delete(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    edge = EntityEdge(
        uuid='edge-entity-1',
        group_id='main',
        source_node_uuid='entity-a',
        target_node_uuid='entity-b',
        name='LIKES',
        fact='Alice likes Bob',
        fact_embedding=[0.4] * 384,
        episodes=['episode-1'],
        valid_at=VALID_AT,
        reference_time=VALID_AT,
        attributes={'confidence': 0.98},
        created_at=CREATED_AT,
    )

    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    loaded = await postgres_age_driver.entity_edge_ops.get_by_uuid(postgres_age_driver, edge.uuid)
    between = await postgres_age_driver.entity_edge_ops.get_between_nodes(
        postgres_age_driver, 'entity-a', 'entity-b'
    )
    by_node = await postgres_age_driver.entity_edge_ops.get_by_node_uuid(
        postgres_age_driver, 'entity-a'
    )
    by_group = await postgres_age_driver.entity_edge_ops.get_by_group_ids(
        postgres_age_driver, ['main'], limit=10
    )
    projection = await postgres_age_driver.execute_age_cypher(
        """
        MATCH (:Entity {uuid: "entity-a"})-[e:RELATES_TO {uuid: "edge-entity-1"}]->(:Entity {uuid: "entity-b"})
        RETURN e.uuid AS uuid, e.name AS name
        """,
        'uuid agtype, name agtype',
    )

    assert loaded.fact == edge.fact
    assert loaded.attributes == {'confidence': 0.98}
    assert [item.uuid for item in between] == [edge.uuid]
    assert [item.uuid for item in by_node] == [edge.uuid]
    assert [item.uuid for item in by_group] == [edge.uuid]
    assert projection == [{'uuid': edge.uuid, 'name': edge.name}]

    loaded.fact_embedding = None
    await postgres_age_driver.entity_edge_ops.load_embeddings(postgres_age_driver, loaded)
    assert loaded.fact_embedding == pytest.approx([0.4] * 384)

    await postgres_age_driver.entity_edge_ops.delete(postgres_age_driver, edge)
    with pytest.raises(EdgeNotFoundError):
        await postgres_age_driver.entity_edge_ops.get_by_uuid(postgres_age_driver, edge.uuid)
    projection_after_delete = await postgres_age_driver.execute_age_cypher(
        """
        MATCH ()-[e:RELATES_TO {uuid: "edge-entity-1"}]->()
        RETURN e.uuid AS uuid
        """,
        'uuid agtype',
    )
    assert projection_after_delete == []


@pytest.mark.integration
async def test_node_delete_removes_incident_age_edge_projection(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    edge = EntityEdge(
        uuid='edge-stale-projection',
        group_id='main',
        source_node_uuid='entity-a',
        target_node_uuid='entity-b',
        name='LIKES',
        fact='Alice likes Bob',
        created_at=CREATED_AT,
    )
    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)
    community_edge = CommunityEdge(
        uuid='edge-community-target-entity',
        group_id='main',
        source_node_uuid='community-1',
        target_node_uuid='entity-a',
        created_at=CREATED_AT,
    )
    await postgres_age_driver.community_edge_ops.save(postgres_age_driver, community_edge)

    await postgres_age_driver.entity_node_ops.delete_by_uuids(postgres_age_driver, ['entity-a'])

    canonical_edges, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM entity_edges WHERE uuid = %(uuid)s',
        params={'uuid': edge.uuid},
    )
    canonical_community_edges, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM community_edges WHERE uuid = %(uuid)s',
        params={'uuid': community_edge.uuid},
    )
    projection = await postgres_age_driver.execute_age_cypher(
        """
        MATCH ()-[e]->()
        WHERE e.uuid IN ["edge-stale-projection", "edge-community-target-entity"]
        RETURN e.uuid AS uuid
        """,
        'uuid agtype',
    )

    assert canonical_edges == []
    assert canonical_community_edges == []
    assert projection == []


@pytest.mark.integration
async def test_age_projection_accepts_values_containing_dollar_quote_marker(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    edge = EntityEdge(
        uuid='edge-dollar-quote',
        group_id='main',
        source_node_uuid='entity-a',
        target_node_uuid='entity-b',
        name='LIKES $$ MARKER',
        fact='Alice likes Bob',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    projection = await postgres_age_driver.execute_age_cypher(
        """
        MATCH ()-[e:RELATES_TO {uuid: "edge-dollar-quote"}]->()
        RETURN e.name AS name
        """,
        'name agtype',
    )
    assert projection == [{'name': 'LIKES $$ MARKER'}]


@pytest.mark.integration
async def test_simple_edge_ops_save_query_projection_and_delete(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    episodic_edge = EpisodicEdge(
        uuid='edge-episodic-1',
        group_id='main',
        source_node_uuid='episode-1',
        target_node_uuid='entity-a',
        created_at=CREATED_AT,
    )
    community_edge = CommunityEdge(
        uuid='edge-community-1',
        group_id='main',
        source_node_uuid='community-1',
        target_node_uuid='entity-a',
        created_at=CREATED_AT,
    )
    has_episode_edge = HasEpisodeEdge(
        uuid='edge-has-episode-1',
        group_id='main',
        source_node_uuid='saga-1',
        target_node_uuid='episode-1',
        created_at=CREATED_AT,
    )
    next_episode_edge = NextEpisodeEdge(
        uuid='edge-next-episode-1',
        group_id='main',
        source_node_uuid='episode-1',
        target_node_uuid='episode-1',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.episodic_edge_ops.save(postgres_age_driver, episodic_edge)
    await postgres_age_driver.community_edge_ops.save(postgres_age_driver, community_edge)
    await postgres_age_driver.has_episode_edge_ops.save(postgres_age_driver, has_episode_edge)
    await postgres_age_driver.next_episode_edge_ops.save(postgres_age_driver, next_episode_edge)

    assert (
        await postgres_age_driver.episodic_edge_ops.get_by_uuid(
            postgres_age_driver, episodic_edge.uuid
        )
    ).target_node_uuid == 'entity-a'
    assert (
        await postgres_age_driver.community_edge_ops.get_by_uuid(
            postgres_age_driver, community_edge.uuid
        )
    ).source_node_uuid == 'community-1'
    assert (
        await postgres_age_driver.has_episode_edge_ops.get_by_uuid(
            postgres_age_driver, has_episode_edge.uuid
        )
    ).target_node_uuid == 'episode-1'
    assert (
        await postgres_age_driver.next_episode_edge_ops.get_by_uuid(
            postgres_age_driver, next_episode_edge.uuid
        )
    ).source_node_uuid == 'episode-1'

    projection = await postgres_age_driver.execute_age_cypher(
        """
        MATCH ()-[e]->()
        WHERE e.uuid IN ["edge-episodic-1", "edge-community-1", "edge-has-episode-1", "edge-next-episode-1"]
        RETURN e.uuid AS uuid
        ORDER BY e.uuid
        """,
        'uuid agtype',
    )
    assert [row['uuid'] for row in projection] == [
        'edge-community-1',
        'edge-episodic-1',
        'edge-has-episode-1',
        'edge-next-episode-1',
    ]

    await postgres_age_driver.episodic_edge_ops.delete_by_uuids(
        postgres_age_driver, [episodic_edge.uuid]
    )
    with pytest.raises(EdgeNotFoundError):
        await postgres_age_driver.episodic_edge_ops.get_by_uuid(
            postgres_age_driver, episodic_edge.uuid
        )


@pytest.mark.integration
async def test_community_edge_ops_supports_community_targets(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    edge = CommunityEdge(
        uuid='edge-community-nested',
        group_id='main',
        source_node_uuid='community-1',
        target_node_uuid='community-2',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.community_edge_ops.save(postgres_age_driver, edge)

    loaded = await postgres_age_driver.community_edge_ops.get_by_uuid(
        postgres_age_driver, edge.uuid
    )
    projection = await postgres_age_driver.execute_age_cypher(
        """
        MATCH (:Community {uuid: "community-1"})-[e:HAS_MEMBER {uuid: "edge-community-nested"}]->(:Community {uuid: "community-2"})
        RETURN e.uuid AS uuid
        """,
        'uuid agtype',
    )

    assert loaded.target_node_uuid == 'community-2'
    assert projection == [{'uuid': edge.uuid}]


@pytest.mark.integration
async def test_community_edge_ops_rejects_missing_target(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    edge = CommunityEdge(
        uuid='edge-community-missing-target',
        group_id='main',
        source_node_uuid='community-1',
        target_node_uuid='missing-target',
        created_at=CREATED_AT,
    )

    with pytest.raises(NodeNotFoundError):
        await postgres_age_driver.community_edge_ops.save(postgres_age_driver, edge)

    rows, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM community_edges WHERE uuid = %(uuid)s',
        params={'uuid': edge.uuid},
    )
    assert rows == []


@pytest.mark.integration
async def test_entity_edge_projection_failure_rolls_back_canonical_row(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_nodes(postgres_age_driver)
    edge = EntityEdge(
        uuid='edge-rollback',
        group_id='main',
        source_node_uuid='entity-a',
        target_node_uuid='entity-b',
        name='ROLLBACKS',
        fact='Projection failures rollback canonical writes',
        created_at=CREATED_AT,
    )

    async def fail_projection(*args, **kwargs):
        raise RuntimeError('forced projection failure')

    original_projection = postgres_age_driver.entity_edge_ops._save_projection
    postgres_age_driver.entity_edge_ops._save_projection = fail_projection
    try:
        with pytest.raises(RuntimeError, match='forced projection failure'):
            await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)
    finally:
        postgres_age_driver.entity_edge_ops._save_projection = original_projection

    rows, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM entity_edges WHERE uuid = %(uuid)s',
        params={'uuid': edge.uuid},
    )
    assert rows == []
