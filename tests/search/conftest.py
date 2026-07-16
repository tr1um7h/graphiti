# tests/search/conftest.py
"""Fixtures and SearchConfigs for the BFS integration test suite."""
import os
from collections.abc import AsyncIterator

import pytest

pytest.importorskip('psycopg')
pytest.importorskip('psycopg_pool')
pytest.importorskip('pgvector')

from graphiti_core.driver.postgres_age import PostgresAgeDriver
from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    SearchConfig,
)
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

TEST_GROUP = 'bfs_test_group'
TEST_GROUP_2 = 'bfs_test_group_2'

# Baseline: BM25 + cosine only (current CHAT_SEARCH_CONFIG shape).
BASELINE_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bm25, EdgeSearchMethod.cosine_similarity],
        reranker=EdgeReranker.rrf,
        sim_min_score=0.2,
    ),
    limit=10,
)

# WITH_BFS: BM25 + cosine + BFS, with node config for tests that need node BFS.
WITH_BFS_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[
            EdgeSearchMethod.bm25,
            EdgeSearchMethod.cosine_similarity,
            EdgeSearchMethod.bfs,
        ],
        reranker=EdgeReranker.rrf,
        sim_min_score=0.2,
        bfs_max_depth=3,
    ),
    node_config=NodeSearchConfig(
        search_methods=[
            NodeSearchMethod.bm25,
            NodeSearchMethod.cosine_similarity,
            NodeSearchMethod.bfs,
        ],
        reranker=NodeReranker.rrf,
        sim_min_score=0.2,
        bfs_max_depth=3,
    ),
    limit=10,
)

# BFS-only edge config (primitive tests; no cosine → no embedder call during search).
BFS_ONLY_EDGE_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bfs],
        reranker=EdgeReranker.rrf,
    ),
    limit=10,
)

# BFS-only node config (for #12 node_bfs asymmetry test).
BFS_ONLY_NODE_CONFIG = SearchConfig(
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.bfs],
        reranker=NodeReranker.rrf,
    ),
    limit=10,
)


@pytest.fixture
async def bfs_driver() -> AsyncIterator[PostgresAgeDriver]:
    """Yield a Postgres AGE driver with both test groups cleared before each test."""
    dsn = os.getenv(
        'POSTGRES_AGE_DSN',
        'postgresql://graphiti:graphiti@localhost:55432/graphiti',
    )
    driver = PostgresAgeDriver(
        dsn=dsn,
        graph_name='graphiti_test_core',
        embedding_dimension=384,
    )
    await clear_data(driver, [TEST_GROUP, TEST_GROUP_2])
    try:
        yield driver
    finally:
        await driver.close()


import tests.helpers_test as helpers
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

# Query strings used by mock-embedder tests (semantic-class tests go through real_embedder).
MOCK_QUERY_EMBEDDINGS = {
    'LeadBob 的下属': [0.2] * 384,
    'NodeA1 相关节点': [0.4] * 384,
    'OCCURRED_ON': [0.6] * 384,
    'Q1': [0.5] * 384,
    'Alice WORKS_AT AcmeCorp': [0.7] * 384,
    'AcmeCorp LOCATED_IN SanFrancisco': [0.8] * 384,
}


@pytest.fixture(autouse=True)
def extend_mock_embedder_dict():
    """Locally extend helpers.embeddings for the duration of each test,
    then restore. Does not modify tests/helpers_test.py."""
    saved = dict(helpers.embeddings)
    helpers.embeddings.update(MOCK_QUERY_EMBEDDINGS)
    try:
        yield
    finally:
        helpers.embeddings.clear()
        helpers.embeddings.update(saved)


@pytest.fixture
def mock_embedder():
    """Re-export of helpers_test.mock_embedder (object is request-scoped)."""
    from tests.helpers_test import mock_embedder as _mock
    return _mock


@pytest.fixture
def real_embedder():
    """Real OpenAI embedder; skip cleanly when OPENAI_API_KEY is unset."""
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip('OPENAI_API_KEY not set; skipping real-embedder BFS test')
    return OpenAIEmbedder(config=OpenAIEmbedderConfig(embedding_dim=384))
