from uuid import uuid4

import pytest

from graphiti_core.driver.postgres_age import PostgresAgeDriver


@pytest.mark.integration
async def test_execute_query_returns_neo4j_like_tuple(postgres_age_driver):
    records, summary, keys = await postgres_age_driver.execute_query(
        'SELECT %s::text AS value',
        params=('ok',),
    )

    assert records == [{'value': 'ok'}]
    assert summary is None
    assert keys == ['value']


@pytest.mark.integration
async def test_named_kwargs_preserve_none_bindings(postgres_age_driver):
    records, summary, keys = await postgres_age_driver.execute_query(
        'SELECT %(value)s::text AS value',
        value=None,
    )

    assert records == [{'value': None}]
    assert summary is None
    assert keys == ['value']

    async with postgres_age_driver.transaction() as tx:
        tx_records, tx_summary, tx_keys = await tx.run(
            'SELECT %(value)s::text AS value',
            value=None,
        )

    assert tx_records == [{'value': None}]
    assert tx_summary is None
    assert tx_keys == ['value']


@pytest.mark.integration
async def test_execute_query_after_close_raises_clear_error(postgres_age_driver):
    await postgres_age_driver.execute_query('SELECT 1 AS value')
    await postgres_age_driver.close()

    with pytest.raises(RuntimeError, match='PostgresAgeDriver is closed'):
        await postgres_age_driver.execute_query('SELECT 1 AS value')


@pytest.mark.integration
async def test_connection_search_path_honors_schema(postgres_age_dsn):
    schema = 'graphiti_connection_test'
    setup_driver = PostgresAgeDriver(dsn=postgres_age_dsn)
    schema_driver = PostgresAgeDriver(dsn=postgres_age_dsn, schema=schema)

    try:
        await setup_driver.execute_query(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await setup_driver.execute_query('DROP TABLE IF EXISTS ag_catalog.schema_probe')
        await setup_driver.execute_query('DROP TABLE IF EXISTS public.schema_probe')
        await setup_driver.execute_query(f'CREATE SCHEMA {schema}')

        await schema_driver.execute_query('CREATE TABLE schema_probe (value text)')
        records, _, _ = await setup_driver.execute_query(
            """
            SELECT table_schema
            FROM information_schema.tables
            WHERE table_schema = %(schema)s
              AND table_name = 'schema_probe'
            """,
            schema=schema,
        )

        assert records == [{'table_schema': schema}]
    finally:
        await schema_driver.close()
        await setup_driver.execute_query(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        await setup_driver.execute_query('DROP TABLE IF EXISTS ag_catalog.schema_probe')
        await setup_driver.execute_query('DROP TABLE IF EXISTS public.schema_probe')
        await setup_driver.close()


@pytest.mark.integration
async def test_transaction_rolls_back_on_error(postgres_age_driver):
    table_name = f'graphiti_tx_probe_{uuid4().hex}'
    await postgres_age_driver.execute_query(f'CREATE TABLE {table_name} (value text)')

    try:
        with pytest.raises(RuntimeError):
            async with postgres_age_driver.transaction() as tx:
                await tx.run(f'INSERT INTO {table_name} (value) VALUES (%s)', ('rolled-back',))
                raise RuntimeError('force rollback')

        records, _, _ = await postgres_age_driver.execute_query(f'SELECT value FROM {table_name}')
        assert records == []
    finally:
        await postgres_age_driver.execute_query(f'DROP TABLE IF EXISTS {table_name}')


@pytest.mark.integration
async def test_session_execute_write_runs_callback(postgres_age_driver):
    async with postgres_age_driver.session() as session:
        result = await session.execute_write(
            lambda tx: tx.run('SELECT %s::text AS value', ('written',))
        )

    assert result[0][0]['value'] == 'written'
