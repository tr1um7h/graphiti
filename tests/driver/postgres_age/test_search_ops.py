from datetime import datetime, timezone

import pytest

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode
from graphiti_core.search.search_filters import (
    ComparisonOperator,
    DateFilter,
    PropertyFilter,
    SearchFilters,
)

CREATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
VALID_AT = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)


async def _seed_search_data(postgres_age_driver):
    nodes = [
        EntityNode(
            uuid='node-alice',
            name='Alice',
            group_id='main',
            labels=['Person'],
            summary='Graph database engineer',
            name_embedding=[1.0] + [0.0] * 383,
            created_at=CREATED_AT,
        ),
        EntityNode(
            uuid='node-bob',
            name='Bob',
            group_id='main',
            labels=['Person'],
            summary='Product manager',
            name_embedding=[0.0, 1.0] + [0.0] * 382,
            created_at=CREATED_AT,
        ),
        EntityNode(
            uuid='node-cyd',
            name='Cyd',
            group_id='other',
            labels=['Person'],
            summary='Graph database researcher',
            name_embedding=[0.9, 0.1] + [0.0] * 382,
            created_at=CREATED_AT,
        ),
    ]
    await postgres_age_driver.entity_node_ops.save_bulk(postgres_age_driver, nodes)
    await postgres_age_driver.episode_node_ops.save(
        postgres_age_driver,
        EpisodicNode(
            uuid='episode-graph',
            name='Graph episode',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content='Alice discussed a graph database migration',
            valid_at=VALID_AT,
            created_at=CREATED_AT,
        ),
    )
    await postgres_age_driver.community_node_ops.save(
        postgres_age_driver,
        CommunityNode(
            uuid='community-graph',
            name='Graph Community',
            group_id='main',
            summary='People working on graph databases',
            name_embedding=[1.0] + [0.0] * 383,
            created_at=CREATED_AT,
        ),
    )
    await postgres_age_driver.entity_edge_ops.save(
        postgres_age_driver,
        EntityEdge(
            uuid='edge-graph',
            group_id='main',
            source_node_uuid='node-alice',
            target_node_uuid='node-bob',
            name='COLLABORATES_WITH',
            fact='Alice collaborates with Bob on graph database work',
            fact_embedding=[1.0] + [0.0] * 383,
            valid_at=VALID_AT,
            created_at=CREATED_AT,
        ),
    )
    await postgres_age_driver.episodic_edge_ops.save(
        postgres_age_driver,
        EpisodicEdge(
            uuid='mention-graph',
            group_id='main',
            source_node_uuid='episode-graph',
            target_node_uuid='node-alice',
            created_at=CREATED_AT,
        ),
    )


@pytest.mark.integration
async def test_search_ops_fulltext_searches_canonical_tables(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_search_data(postgres_age_driver)

    nodes = await postgres_age_driver.search_ops.node_fulltext_search(
        postgres_age_driver, 'graph database', SearchFilters(), group_ids=['main'], limit=5
    )
    edges = await postgres_age_driver.search_ops.edge_fulltext_search(
        postgres_age_driver, 'collaborates graph', SearchFilters(), group_ids=['main'], limit=5
    )
    episodes = await postgres_age_driver.search_ops.episode_fulltext_search(
        postgres_age_driver, 'migration', SearchFilters(), group_ids=['main'], limit=5
    )
    communities = await postgres_age_driver.search_ops.community_fulltext_search(
        postgres_age_driver, 'graph databases', group_ids=['main'], limit=5
    )

    assert [node.uuid for node in nodes] == ['node-alice']
    assert [edge.uuid for edge in edges] == ['edge-graph']
    assert [episode.uuid for episode in episodes] == ['episode-graph']
    assert [community.uuid for community in communities] == ['community-graph']


@pytest.mark.integration
async def test_search_ops_edge_date_filters_and_rejects_property_filters(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_search_data(postgres_age_driver)

    labeled_edges = await postgres_age_driver.search_ops.edge_fulltext_search(
        postgres_age_driver,
        'graph',
        SearchFilters(node_labels=['Organization']),
        group_ids=['main'],
        limit=5,
    )
    edges = await postgres_age_driver.search_ops.edge_fulltext_search(
        postgres_age_driver,
        'graph',
        SearchFilters(
            valid_at=[
                [
                    DateFilter(
                        date=VALID_AT,
                        comparison_operator=ComparisonOperator.greater_than_equal,
                    )
                ]
            ]
        ),
        group_ids=['main'],
        limit=5,
    )

    assert labeled_edges == []
    assert [edge.uuid for edge in edges] == ['edge-graph']

    with pytest.raises(NotImplementedError, match='property_filters'):
        await postgres_age_driver.search_ops.edge_fulltext_search(
            postgres_age_driver,
            'graph',
            SearchFilters(
                property_filters=[
                    PropertyFilter(
                        property_name='confidence',
                        property_value=1,
                        comparison_operator=ComparisonOperator.equals,
                    )
                ]
            ),
            group_ids=['main'],
            limit=5,
        )


@pytest.mark.integration
async def test_search_ops_similarity_searches_pgvector_columns(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_search_data(postgres_age_driver)

    nodes = await postgres_age_driver.search_ops.node_similarity_search(
        postgres_age_driver,
        [1.0] + [0.0] * 383,
        SearchFilters(),
        group_ids=['main'],
        limit=5,
        min_score=0.5,
    )
    edges = await postgres_age_driver.search_ops.edge_similarity_search(
        postgres_age_driver,
        [1.0] + [0.0] * 383,
        source_node_uuid='node-alice',
        target_node_uuid=None,
        search_filter=SearchFilters(),
        group_ids=['main'],
        limit=5,
        min_score=0.5,
    )
    communities = await postgres_age_driver.search_ops.community_similarity_search(
        postgres_age_driver,
        [1.0] + [0.0] * 383,
        group_ids=['main'],
        limit=5,
        min_score=0.5,
    )

    assert [node.uuid for node in nodes] == ['node-alice']
    assert [edge.uuid for edge in edges] == ['edge-graph']
    assert [community.uuid for community in communities] == ['community-graph']


@pytest.mark.integration
async def test_search_ops_bfs_bounds_and_episode_origins(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_search_data(postgres_age_driver)

    with pytest.raises(ValueError, match='max_depth'):
        await postgres_age_driver.search_ops.node_bfs_search(
            postgres_age_driver,
            ['node-alice'],
            SearchFilters(),
            max_depth=6,
            group_ids=['main'],
        )

    nodes = await postgres_age_driver.search_ops.node_bfs_search(
        postgres_age_driver,
        ['episode-graph'],
        SearchFilters(),
        max_depth=1,
        group_ids=['main'],
        limit=5,
    )
    edges = await postgres_age_driver.search_ops.edge_bfs_search(
        postgres_age_driver,
        ['episode-graph'],
        max_depth=2,
        search_filter=SearchFilters(),
        group_ids=['main'],
        limit=5,
    )

    assert [node.uuid for node in nodes] == ['node-alice']
    assert [edge.uuid for edge in edges] == ['edge-graph']


@pytest.mark.integration
async def test_search_ops_rerankers_use_canonical_graph(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    await _seed_search_data(postgres_age_driver)

    distance_ranked = await postgres_age_driver.search_ops.node_distance_reranker(
        postgres_age_driver,
        ['node-bob', 'node-alice', 'node-cyd'],
        center_node_uuid='node-alice',
        min_score=0,
    )
    mentioned_ranked = await postgres_age_driver.search_ops.episode_mentions_reranker(
        postgres_age_driver,
        ['node-bob', 'node-alice'],
        min_score=1,
    )
    mentioned_with_zeroes = await postgres_age_driver.search_ops.episode_mentions_reranker(
        postgres_age_driver,
        ['node-bob', 'node-alice'],
        min_score=0,
    )

    assert [node.uuid for node in distance_ranked] == ['node-alice', 'node-bob', 'node-cyd']
    assert [node.uuid for node in mentioned_ranked] == ['node-alice']
    assert [node.uuid for node in mentioned_with_zeroes] == ['node-alice', 'node-bob']
