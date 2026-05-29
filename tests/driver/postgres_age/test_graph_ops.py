from datetime import datetime, timezone

import pytest

from graphiti_core.edges import CommunityEdge, EntityEdge, EpisodicEdge
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode

CREATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
VALID_AT = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)


async def _seed_projection_graph(postgres_age_driver):
    entities = [
        EntityNode(uuid='entity-a', name='Alice', group_id='main', created_at=CREATED_AT),
        EntityNode(uuid='entity-b', name='Bob', group_id='main', created_at=CREATED_AT),
        EntityNode(uuid='entity-c', name='Cyd', group_id='other', created_at=CREATED_AT),
        EntityNode(uuid='entity-d', name='Dee', group_id='other', created_at=CREATED_AT),
    ]
    episodes = [
        EpisodicNode(
            uuid='episode-main',
            name='main episode',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content='Alice likes Bob',
            valid_at=VALID_AT,
            created_at=CREATED_AT,
        ),
        EpisodicNode(
            uuid='episode-other',
            name='other episode',
            group_id='other',
            source=EpisodeType.message,
            source_description='chat',
            content='Cyd likes Dee',
            valid_at=VALID_AT,
            created_at=CREATED_AT,
        ),
    ]
    community = CommunityNode(
        uuid='community-main',
        name='Main community',
        group_id='main',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.entity_node_ops.save_bulk(postgres_age_driver, entities)
    await postgres_age_driver.episode_node_ops.save_bulk(postgres_age_driver, episodes)
    await postgres_age_driver.community_node_ops.save(postgres_age_driver, community)
    await postgres_age_driver.entity_edge_ops.save_bulk(
        postgres_age_driver,
        [
            EntityEdge(
                uuid='edge-main',
                group_id='main',
                source_node_uuid='entity-a',
                target_node_uuid='entity-b',
                name='LIKES',
                fact='Alice likes Bob',
                created_at=CREATED_AT,
            ),
            EntityEdge(
                uuid='edge-other',
                group_id='other',
                source_node_uuid='entity-c',
                target_node_uuid='entity-d',
                name='LIKES',
                fact='Cyd likes Dee',
                created_at=CREATED_AT,
            ),
        ],
    )
    await postgres_age_driver.episodic_edge_ops.save(
        postgres_age_driver,
        EpisodicEdge(
            uuid='mention-main',
            group_id='main',
            source_node_uuid='episode-main',
            target_node_uuid='entity-a',
            created_at=CREATED_AT,
        ),
    )
    await postgres_age_driver.community_edge_ops.save(
        postgres_age_driver,
        CommunityEdge(
            uuid='member-main',
            group_id='main',
            source_node_uuid='community-main',
            target_node_uuid='entity-a',
            created_at=CREATED_AT,
        ),
    )


@pytest.mark.integration
async def test_graph_ops_rebuilds_age_projection_from_canonical_tables(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_projection_graph(postgres_age_driver)
    await postgres_age_driver.execute_age_cypher('MATCH (n) DETACH DELETE n')

    await postgres_age_driver.graph_ops.rebuild_age_projection(postgres_age_driver)

    projection_edges = await postgres_age_driver.execute_age_cypher(
        """
        MATCH ()-[e]->()
        RETURN e.uuid AS uuid
        ORDER BY e.uuid
        """,
        'uuid agtype',
    )
    projection_nodes = await postgres_age_driver.execute_age_cypher(
        """
        MATCH (n)
        RETURN n.uuid AS uuid
        ORDER BY n.uuid
        """,
        'uuid agtype',
    )

    assert [row['uuid'] for row in projection_edges] == [
        'edge-main',
        'edge-other',
        'member-main',
        'mention-main',
    ]
    assert {row['uuid'] for row in projection_nodes} == {
        'community-main',
        'entity-a',
        'entity-b',
        'entity-c',
        'entity-d',
        'episode-main',
        'episode-other',
    }


@pytest.mark.integration
async def test_graph_ops_rebuild_drops_dangling_community_edges(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_projection_graph(postgres_age_driver)
    await postgres_age_driver.execute_query(
        """
        INSERT INTO community_edges (
            uuid, group_id, source_node_uuid, target_node_uuid, created_at
        )
        VALUES (
            'member-dangling', 'main', 'community-main', 'missing-target', %(created_at)s
        )
        """,
        params={'created_at': CREATED_AT},
    )

    await postgres_age_driver.graph_ops.rebuild_age_projection(postgres_age_driver)

    canonical_edges, _, _ = await postgres_age_driver.execute_query(
        """
        SELECT uuid
        FROM community_edges
        WHERE uuid = 'member-dangling'
        """
    )
    projection_nodes = await postgres_age_driver.execute_age_cypher(
        """
        MATCH (n {uuid: "missing-target"})
        RETURN n.uuid AS uuid
        """,
        'uuid agtype',
    )

    assert canonical_edges == []
    assert projection_nodes == []


@pytest.mark.integration
async def test_graph_ops_clear_data_by_group_rebuilds_remaining_projection(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_projection_graph(postgres_age_driver)

    await postgres_age_driver.graph_ops.clear_data(postgres_age_driver, group_ids=['main'])

    entity_rows, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM entity_nodes ORDER BY uuid'
    )
    edge_rows, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM entity_edges ORDER BY uuid'
    )
    projection_edges = await postgres_age_driver.execute_age_cypher(
        """
        MATCH ()-[e]->()
        RETURN e.uuid AS uuid
        ORDER BY e.uuid
        """,
        'uuid agtype',
    )

    assert [row['uuid'] for row in entity_rows] == ['entity-c', 'entity-d']
    assert [row['uuid'] for row in edge_rows] == ['edge-other']
    assert [row['uuid'] for row in projection_edges] == ['edge-other']


@pytest.mark.integration
async def test_graph_ops_determine_entity_community_uses_direct_then_neighbor_majority(
    postgres_age_driver,
):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_projection_graph(postgres_age_driver)
    entity_new = EntityNode(
        uuid='entity-new',
        name='New',
        group_id='main',
        created_at=CREATED_AT,
    )
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, entity_new)
    await postgres_age_driver.entity_edge_ops.save(
        postgres_age_driver,
        EntityEdge(
            uuid='edge-new-neighbor',
            group_id='main',
            source_node_uuid='entity-new',
            target_node_uuid='entity-a',
            name='KNOWS',
            fact='New knows Alice',
            created_at=CREATED_AT,
        ),
    )

    direct_community, direct_is_new = await postgres_age_driver.graph_ops.determine_entity_community(
        postgres_age_driver,
        EntityNode(uuid='entity-a', name='Alice', group_id='main', created_at=CREATED_AT),
    )
    inferred_community, inferred_is_new = (
        await postgres_age_driver.graph_ops.determine_entity_community(
            postgres_age_driver,
            entity_new,
        )
    )

    assert direct_community.uuid == 'community-main'
    assert direct_is_new is False
    assert inferred_community.uuid == 'community-main'
    assert inferred_is_new is True
