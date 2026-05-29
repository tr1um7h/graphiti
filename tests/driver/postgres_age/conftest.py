import os
from collections.abc import AsyncIterator

import pytest

pytest.importorskip('pgvector')
pytest.importorskip('psycopg')
pytest.importorskip('psycopg_pool')

from graphiti_core.driver.postgres_age import PostgresAgeDriver


@pytest.fixture
def postgres_age_dsn() -> str:
    return os.getenv(
        'POSTGRES_AGE_DSN',
        'postgresql://graphiti:graphiti@localhost:55432/graphiti',
    )


@pytest.fixture
async def postgres_age_driver(postgres_age_dsn: str) -> AsyncIterator[PostgresAgeDriver]:
    driver = PostgresAgeDriver(
        dsn=postgres_age_dsn,
        graph_name='graphiti_test_core',
        embedding_dimension=384,
    )
    try:
        yield driver
    finally:
        await driver.close()
