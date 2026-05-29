from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

pytest.importorskip('pgvector')
pytest.importorskip('psycopg')
pytest.importorskip('psycopg_pool')

from graphiti_core.driver.postgres_age.spike import PostgresAgeSpike

DSN = 'postgresql://graphiti:graphiti@localhost:55432/graphiti'
SPIKE_TEST_LOCK = 'graphiti_postgres_age_spike_tests'


@pytest.mark.asyncio
async def test_spike_helper_can_be_imported():
    helper = PostgresAgeSpike(dsn=DSN)
    assert helper.graph_name == 'graphiti_spike'


@pytest.mark.asyncio
async def test_connection_before_open_raises():
    helper = PostgresAgeSpike(dsn=DSN)

    with pytest.raises(RuntimeError, match='open'):
        async with helper.connection():
            pass


@pytest.mark.asyncio
async def test_execute_cypher_rejects_dollar_quote_breakout_before_connecting():
    helper = PostgresAgeSpike(dsn=DSN)

    with pytest.raises(ValueError, match='dollar-quote delimiter'):
        await helper.execute_cypher('RETURN $$', 'uuid agtype')


@pytest.mark.asyncio
async def test_execute_cypher_rejects_non_agtype_columns_before_connecting():
    helper = PostgresAgeSpike(dsn=DSN)

    with pytest.raises(ValueError, match='columns'):
        await helper.execute_cypher('RETURN 1', 'uuid text')


@pytest.mark.asyncio
async def test_bfs_rejects_unbounded_depth_before_connecting():
    helper = PostgresAgeSpike(dsn=DSN)

    with pytest.raises(ValueError, match='between 1 and 5'):
        await helper.bfs_entity_uuids('alice', max_depth=6)


@pytest.mark.asyncio
async def test_search_rejects_non_positive_limit_before_connecting():
    helper = PostgresAgeSpike(dsn=DSN)

    with pytest.raises(ValueError, match='positive integer'):
        await helper.vector_search_entity_uuids([0.1, 0.2, 0.3], limit=0)

    with pytest.raises(ValueError, match='positive integer'):
        await helper.fulltext_search_entity_uuids('graph database', limit=0)


async def _drop_spike_objects(helper: PostgresAgeSpike) -> None:
    if helper.pool is None:
        raise RuntimeError('helper must be open before cleanup')

    async with helper.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute('CREATE EXTENSION IF NOT EXISTS age')
            await cur.execute("LOAD 'age'")
            await cur.execute('SET search_path = ag_catalog, "$user", public')
            await cur.execute('SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s', (helper.graph_name,))
            if await cur.fetchone() is not None:
                await cur.execute('SELECT drop_graph(%s, true)', (helper.graph_name,))
            await cur.execute('DROP TABLE IF EXISTS public.spike_entity_edges')
            await cur.execute('DROP TABLE IF EXISTS public.spike_entity_nodes')
        await conn.commit()


async def _drop_age_graph(helper: PostgresAgeSpike) -> None:
    if helper.pool is None:
        raise RuntimeError('helper must be open before graph cleanup')

    async with helper.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute('CREATE EXTENSION IF NOT EXISTS age')
            await cur.execute("LOAD 'age'")
            await cur.execute('SET search_path = ag_catalog, "$user", public')
            await cur.execute('SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s', (helper.graph_name,))
            if await cur.fetchone() is not None:
                await cur.execute('SELECT drop_graph(%s, true)', (helper.graph_name,))
        await conn.commit()


@asynccontextmanager
async def _spike_database_lock(helper: PostgresAgeSpike) -> AsyncIterator[None]:
    if helper.pool is None:
        raise RuntimeError('helper must be open before acquiring lock')

    async with helper.pool.connection() as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (SPIKE_TEST_LOCK,))
            yield
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_projection_write_rolls_back_canonical_write():
    helper = PostgresAgeSpike(dsn=DSN, graph_name=f'graphiti_spike_{uuid4().hex}')
    await helper.open()
    try:
        async with _spike_database_lock(helper):
            await _drop_spike_objects(helper)
            try:
                await helper.bootstrap()
                await helper.clear()

                with pytest.raises(RuntimeError, match='forced projection failure'):
                    await helper.save_entity_node_then_fail_projection(
                        uuid='rollback-node',
                        group_id='main',
                        name='Rollback Node',
                        summary='This canonical write should roll back',
                        labels=['Entity'],
                        attributes={'rollback': True},
                        embedding=[0.1, 0.2, 0.3],
                    )

                async with helper.connection() as conn, conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT uuid
                        FROM public.spike_entity_nodes
                        WHERE uuid = %s
                        """,
                        ('rollback-node',),
                    )
                    rows = await cur.fetchall()
            finally:
                await _drop_spike_objects(helper)
    finally:
        await helper.close()

    assert rows == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_creates_extensions_schema_and_graph():
    helper = PostgresAgeSpike(dsn=DSN, graph_name=f'graphiti_spike_{uuid4().hex}')
    await helper.open()
    try:
        async with _spike_database_lock(helper):
            await _drop_spike_objects(helper)
            try:
                await helper.bootstrap()

                async with helper.connection() as conn, conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT extname
                        FROM pg_extension
                        WHERE extname = ANY(%s)
                        """,
                        (['age', 'pg_trgm', 'vector'],),
                    )
                    extensions = {row[0] for row in await cur.fetchall()}

                    await cur.execute(
                        """
                        SELECT tablename
                        FROM pg_tables
                        WHERE schemaname = 'public'
                          AND tablename = ANY(%s)
                        """,
                        (['spike_entity_edges', 'spike_entity_nodes'],),
                    )
                    tables = {row[0] for row in await cur.fetchall()}

                    await cur.execute(
                        'SELECT name FROM ag_catalog.ag_graph WHERE name = %s',
                        (helper.graph_name,),
                    )
                    graph_name = await cur.fetchone()
            finally:
                await _drop_spike_objects(helper)
    finally:
        await helper.close()

    assert extensions == {'age', 'pg_trgm', 'vector'}
    assert tables == {'spike_entity_edges', 'spike_entity_nodes'}
    assert graph_name == (helper.graph_name,)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_load_entity_node_from_canonical_table():
    helper = PostgresAgeSpike(dsn=DSN, graph_name=f'graphiti_spike_{uuid4().hex}')
    await helper.open()
    try:
        async with _spike_database_lock(helper):
            await _drop_spike_objects(helper)
            try:
                await helper.bootstrap()
                await helper.clear()

                await helper.save_entity_node(
                    uuid='alice',
                    group_id='main',
                    name='Alice',
                    summary='Alice likes graph databases',
                    labels=['Person'],
                    attributes={'role': 'engineer'},
                    embedding=[0.1, 0.2, 0.3],
                )

                node = await helper.get_entity_node('alice')
                projection_rows = await helper.execute_cypher(
                    """
                    MATCH (n:Entity {uuid: 'alice'})
                    RETURN n.uuid
                    """,
                    'uuid agtype',
                )
            finally:
                await _drop_spike_objects(helper)
    finally:
        await helper.close()

    assert node['uuid'] == 'alice'
    assert node['name'] == 'Alice'
    assert node['labels'] == ['Person']
    assert node['attributes'] == {'role': 'engineer'}
    assert [helper.decode_agtype_scalar(row['uuid']) for row in projection_rows] == ['alice']


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_entity_edge_and_bfs_through_age_projection():
    helper = PostgresAgeSpike(dsn=DSN, graph_name=f'graphiti_spike_{uuid4().hex}')
    await helper.open()
    try:
        async with _spike_database_lock(helper):
            await _drop_spike_objects(helper)
            try:
                await helper.bootstrap()
                await helper.clear()

                await helper.save_entity_node(
                    uuid='alice',
                    group_id='main',
                    name='Alice',
                    summary='Alice likes graph databases',
                    labels=['Person'],
                    attributes={'role': 'engineer'},
                    embedding=[0.1, 0.2, 0.3],
                )
                await helper.save_entity_node(
                    uuid='bob',
                    group_id='main',
                    name='Bob',
                    summary='Bob likes vector search',
                    labels=['Person'],
                    attributes={'role': 'designer'},
                    embedding=[0.2, 0.3, 0.4],
                )
                await helper.save_entity_node(
                    uuid='carol',
                    group_id='main',
                    name='Carol',
                    summary='Carol likes canonical rows',
                    labels=['Person'],
                    attributes={'role': 'analyst'},
                    embedding=[0.3, 0.4, 0.5],
                )

                await helper.save_entity_edge(
                    uuid='edge-1',
                    group_id='main',
                    source_node_uuid='alice',
                    target_node_uuid='bob',
                    name='LIKES',
                    fact='Alice likes Bob',
                    embedding=[0.1, 0.2, 0.3],
                )

                edge = await helper.get_entity_edge('edge-1')
                bfs_result = await helper.bfs_entity_uuids('alice', max_depth=1)

                await helper.save_entity_edge(
                    uuid='edge-1',
                    group_id='main',
                    source_node_uuid='alice',
                    target_node_uuid='carol',
                    name='LIKES',
                    fact='Alice likes Carol',
                    embedding=[0.4, 0.5, 0.6],
                )

                updated_edge = await helper.get_entity_edge('edge-1')
                updated_bfs_result = await helper.bfs_entity_uuids('alice', max_depth=1)
            finally:
                await _drop_spike_objects(helper)
    finally:
        await helper.close()

    assert edge['uuid'] == 'edge-1'
    assert edge['source_node_uuid'] == 'alice'
    assert edge['target_node_uuid'] == 'bob'
    assert bfs_result == ['bob']
    assert updated_edge['source_node_uuid'] == 'alice'
    assert updated_edge['target_node_uuid'] == 'carol'
    assert updated_bfs_result == ['carol']


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_and_fulltext_search_use_canonical_tables():
    helper = PostgresAgeSpike(dsn=DSN, graph_name=f'graphiti_spike_{uuid4().hex}')
    await helper.open()
    try:
        async with _spike_database_lock(helper):
            await _drop_spike_objects(helper)
            try:
                await helper.bootstrap()
                await helper.clear()

                await helper.save_entity_node(
                    uuid='alice',
                    group_id='main',
                    name='Alice',
                    summary='Graph database expert',
                    labels=['Person'],
                    attributes={'role': 'engineer'},
                    embedding=[0.1, 0.2, 0.3],
                )
                await helper.save_entity_node(
                    uuid='charlie',
                    group_id='main',
                    name='Charlie',
                    summary='Unrelated baker',
                    labels=['Person'],
                    attributes={'role': 'baker'},
                    embedding=[0.9, 0.1, 0.1],
                )
                await _drop_age_graph(helper)

                vector_result = await helper.vector_search_entity_uuids(
                    [0.1, 0.2, 0.3], limit=1
                )
                fulltext_result = await helper.fulltext_search_entity_uuids(
                    'graph database', limit=2
                )
            finally:
                await _drop_spike_objects(helper)
    finally:
        await helper.close()

    assert vector_result == ['alice']
    assert fulltext_result == ['alice']
