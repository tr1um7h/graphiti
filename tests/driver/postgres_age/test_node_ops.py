from datetime import datetime, timezone

import pytest

from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode, SagaNode

CREATED_AT = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
VALID_AT = datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc)


@pytest.mark.integration
async def test_entity_node_ops_save_load_embedding_and_delete(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    node = EntityNode(
        uuid='entity-1',
        name='Alice',
        group_id='main',
        labels=['Person'],
        summary='Graph engineer',
        attributes={'level': 7},
        name_embedding=[0.1] * 384,
        created_at=CREATED_AT,
    )

    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, node)
    loaded = await postgres_age_driver.entity_node_ops.get_by_uuid(postgres_age_driver, node.uuid)

    assert loaded.uuid == node.uuid
    assert loaded.labels == ['Person']
    assert loaded.attributes == {'level': 7}

    loaded.name_embedding = None
    await postgres_age_driver.entity_node_ops.load_embeddings(postgres_age_driver, loaded)
    assert loaded.name_embedding == pytest.approx([0.1] * 384)

    await postgres_age_driver.entity_node_ops.delete(postgres_age_driver, node)
    with pytest.raises(NodeNotFoundError):
        await postgres_age_driver.entity_node_ops.get_by_uuid(postgres_age_driver, node.uuid)


@pytest.mark.integration
async def test_entity_node_ops_bulk_and_group_queries(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    nodes = [
        EntityNode(uuid='entity-a', name='Alice', group_id='main', created_at=CREATED_AT),
        EntityNode(uuid='entity-b', name='Bob', group_id='main', created_at=CREATED_AT),
        EntityNode(uuid='entity-c', name='Cyd', group_id='other', created_at=CREATED_AT),
    ]

    await postgres_age_driver.entity_node_ops.save_bulk(postgres_age_driver, nodes)

    loaded = await postgres_age_driver.entity_node_ops.get_by_uuids(
        postgres_age_driver, ['entity-b', 'entity-a']
    )
    group_loaded = await postgres_age_driver.entity_node_ops.get_by_group_ids(
        postgres_age_driver, ['main'], limit=10
    )

    assert [node.uuid for node in loaded] == ['entity-a', 'entity-b']
    assert {node.uuid for node in group_loaded} == {'entity-a', 'entity-b'}

    await postgres_age_driver.entity_node_ops.delete_by_group_id(postgres_age_driver, 'main')
    remaining = await postgres_age_driver.entity_node_ops.get_by_uuids(
        postgres_age_driver, ['entity-a', 'entity-b', 'entity-c']
    )
    assert [node.uuid for node in remaining] == ['entity-c']


@pytest.mark.integration
async def test_entity_node_ops_save_bulk_rolls_back_on_failure(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    nodes = [
        EntityNode(uuid='entity-a', name='Alice', group_id='main', created_at=CREATED_AT),
        EntityNode(uuid='entity-b', name='Bob', group_id='main', created_at=CREATED_AT),
    ]

    async def fail_after_first_save(executor, node, tx=None):
        if node.uuid == 'entity-b':
            raise RuntimeError('forced bulk failure')
        await original_save(executor, node, tx)

    original_save = postgres_age_driver.entity_node_ops.save
    postgres_age_driver.entity_node_ops.save = fail_after_first_save
    try:
        with pytest.raises(RuntimeError, match='forced bulk failure'):
            await postgres_age_driver.entity_node_ops.save_bulk(postgres_age_driver, nodes)
    finally:
        postgres_age_driver.entity_node_ops.save = original_save

    loaded = await postgres_age_driver.entity_node_ops.get_by_uuids(
        postgres_age_driver, ['entity-a', 'entity-b']
    )
    assert loaded == []


@pytest.mark.integration
async def test_episodic_node_ops_save_retrieve_and_delete(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    episodes = [
        EpisodicNode(
            uuid='episode-1',
            name='episode one',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content='Alice likes Bob',
            valid_at=VALID_AT,
            entity_edges=['edge-1'],
            episode_metadata={'source': 'test'},
            created_at=CREATED_AT,
        ),
        EpisodicNode(
            uuid='episode-2',
            name='episode two',
            group_id='main',
            source=EpisodeType.text,
            source_description='note',
            content='Bob likes graphs',
            valid_at=CREATED_AT,
            entity_edges=[],
            created_at=CREATED_AT,
        ),
    ]

    await postgres_age_driver.episode_node_ops.save_bulk(postgres_age_driver, episodes)
    loaded = await postgres_age_driver.episode_node_ops.get_by_uuid(
        postgres_age_driver, 'episode-1'
    )
    retrieved = await postgres_age_driver.episode_node_ops.retrieve_episodes(
        postgres_age_driver, CREATED_AT, last_n=5, group_ids=['main']
    )

    assert loaded.episode_metadata == {'source': 'test'}
    assert [episode.uuid for episode in retrieved] == ['episode-1', 'episode-2']

    await postgres_age_driver.episode_node_ops.delete_by_uuids(
        postgres_age_driver, ['episode-1']
    )
    with pytest.raises(NodeNotFoundError):
        await postgres_age_driver.episode_node_ops.get_by_uuid(postgres_age_driver, 'episode-1')


@pytest.mark.integration
async def test_episodic_retrieve_treats_empty_group_ids_as_unfiltered_and_accepts_episode_type(
    postgres_age_driver,
):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    episodes = [
        EpisodicNode(
            uuid='episode-main',
            name='main episode',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content='Main content',
            valid_at=VALID_AT,
            created_at=CREATED_AT,
        ),
        EpisodicNode(
            uuid='episode-other',
            name='other episode',
            group_id='other',
            source=EpisodeType.message,
            source_description='chat',
            content='Other content',
            valid_at=CREATED_AT,
            created_at=CREATED_AT,
        ),
    ]
    await postgres_age_driver.episode_node_ops.save_bulk(postgres_age_driver, episodes)

    retrieved = await postgres_age_driver.episode_node_ops.retrieve_episodes(
        postgres_age_driver,
        CREATED_AT,
        last_n=5,
        group_ids=[],
        source=EpisodeType.message,
    )

    assert [episode.uuid for episode in retrieved] == ['episode-main', 'episode-other']


@pytest.mark.integration
async def test_community_node_ops_save_load_embedding_and_group_queries(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    nodes = [
        CommunityNode(
            uuid='community-a',
            name='Team A',
            group_id='main',
            summary='Alpha',
            name_embedding=[0.2] * 384,
            created_at=CREATED_AT,
        ),
        CommunityNode(
            uuid='community-b',
            name='Team B',
            group_id='other',
            summary='Beta',
            name_embedding=[0.3] * 384,
            created_at=CREATED_AT,
        ),
    ]

    await postgres_age_driver.community_node_ops.save_bulk(postgres_age_driver, nodes)
    loaded = await postgres_age_driver.community_node_ops.get_by_uuid(
        postgres_age_driver, 'community-a'
    )
    group_loaded = await postgres_age_driver.community_node_ops.get_by_group_ids(
        postgres_age_driver, ['main']
    )

    assert loaded.summary == 'Alpha'
    loaded.name_embedding = None
    await postgres_age_driver.community_node_ops.load_name_embedding(postgres_age_driver, loaded)
    assert loaded.name_embedding == pytest.approx([0.2] * 384)
    assert [node.uuid for node in group_loaded] == ['community-a']

    await postgres_age_driver.community_node_ops.delete_by_uuids(
        postgres_age_driver, ['community-a']
    )
    with pytest.raises(NodeNotFoundError):
        await postgres_age_driver.community_node_ops.get_by_uuid(
            postgres_age_driver, 'community-a'
        )


@pytest.mark.integration
async def test_saga_node_ops_save_queries_and_episode_contents(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    episodes = [
        EpisodicNode(
            uuid='episode-1',
            name='episode one',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content='First',
            valid_at=VALID_AT,
            created_at=VALID_AT,
        ),
        EpisodicNode(
            uuid='episode-2',
            name='episode two',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content='Second',
            valid_at=CREATED_AT,
            created_at=CREATED_AT,
        ),
    ]
    saga = SagaNode(
        uuid='saga-1',
        name='Daily Standup',
        group_id='main',
        summary='Initial summary',
        first_episode_uuid='episode-1',
        last_episode_uuid='episode-2',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.episode_node_ops.save_bulk(postgres_age_driver, episodes)
    await postgres_age_driver.saga_node_ops.save(postgres_age_driver, saga)
    await postgres_age_driver.execute_query(
        """
        INSERT INTO has_episode_edges (
            uuid, group_id, source_node_uuid, target_node_uuid, created_at
        )
        VALUES
            ('has-1', 'main', 'saga-1', 'episode-1', %(created_at)s),
            ('has-2', 'main', 'saga-1', 'episode-2', %(created_at)s)
        """,
        params={'created_at': CREATED_AT},
    )

    loaded = await postgres_age_driver.saga_node_ops.get_by_uuid(postgres_age_driver, saga.uuid)
    previous_uuid = await postgres_age_driver.saga_node_ops.get_previous_episode_uuid(
        postgres_age_driver, saga.uuid, 'episode-2'
    )
    contents = await postgres_age_driver.saga_node_ops.get_episode_contents(
        postgres_age_driver, saga.uuid, limit=10
    )

    assert loaded.summary == 'Initial summary'
    assert previous_uuid == 'episode-1'
    assert contents == [('First', VALID_AT), ('Second', CREATED_AT)]


@pytest.mark.integration
async def test_saga_episode_contents_limits_recent_window_then_returns_chronological(
    postgres_age_driver,
):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    episodes = [
        EpisodicNode(
            uuid=f'episode-{index}',
            name=f'episode {index}',
            group_id='main',
            source=EpisodeType.message,
            source_description='chat',
            content=f'Content {index}',
            valid_at=datetime(2026, 5, 26, 9 + index, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 5, 26, 9 + index, 0, tzinfo=timezone.utc),
        )
        for index in range(4)
    ]
    saga = SagaNode(
        uuid='saga-window',
        name='Window',
        group_id='main',
        created_at=CREATED_AT,
    )

    await postgres_age_driver.episode_node_ops.save_bulk(postgres_age_driver, episodes)
    await postgres_age_driver.saga_node_ops.save(postgres_age_driver, saga)
    for index in range(4):
        await postgres_age_driver.execute_query(
            """
            INSERT INTO has_episode_edges (
                uuid, group_id, source_node_uuid, target_node_uuid, created_at
            )
            VALUES (
                %(uuid)s, 'main', 'saga-window', %(episode_uuid)s, %(created_at)s
            )
            """,
            params={
                'uuid': f'has-window-{index}',
                'episode_uuid': f'episode-{index}',
                'created_at': CREATED_AT,
            },
        )

    contents = await postgres_age_driver.saga_node_ops.get_episode_contents(
        postgres_age_driver, saga.uuid, limit=2
    )

    assert contents == [
        ('Content 2', datetime(2026, 5, 26, 11, 0, tzinfo=timezone.utc)),
        ('Content 3', datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
    ]
