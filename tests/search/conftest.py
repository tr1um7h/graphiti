# tests/search/conftest.py
"""Fixtures and SearchConfigs for the BFS integration test suite."""
import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip('psycopg')
pytest.importorskip('psycopg_pool')
pytest.importorskip('pgvector')

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.postgres_age import PostgresAgeDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.graphiti import Graphiti
from graphiti_core.llm_client import LLMClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
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
E2E_TEST_GROUP = 'bfs_e2e_deepseek'

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


@pytest.fixture
def real_embedder():
    """Real embedder using local MiniLM service (port 8080).

    Produces 384-dim embeddings compatible with the test fixture graph.
    """
    local_embedding_url = os.getenv('EMBEDDING_API_URL', '').replace(
        'host.docker.internal', 'localhost'
    ) or 'http://localhost:8080/v1'
    local_model = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
    return OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_dim=384,
            base_url=local_embedding_url,
            api_key='dummy',
            embedding_model=local_model,
        )
    )


@pytest.fixture
def deepseek_llm_client():
    """Real DeepSeek LLM client for e2e tests."""
    return OpenAIGenericClient(
        config=LLMConfig(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/v1'),
            model=os.getenv('OPENAI_MODEL_NAME', 'deepseek-chat'),
            small_model=os.getenv('OPENAI_MODEL_NAME', 'deepseek-chat'),
            temperature=0.0,
            max_tokens=4096,
        )
    )


def _mock_llm_client() -> LLMClient:
    mock_llm = Mock(spec=LLMClient)
    mock_llm.config = Mock()
    mock_llm.model = 'test-model'
    mock_llm.small_model = 'test-small-model'
    mock_llm.temperature = 0.0
    mock_llm.max_tokens = 1000
    mock_llm.cache_enabled = False
    mock_llm.cache_dir = None
    mock_llm.generate_response = AsyncMock(return_value={'answer': '', 'content': ''})
    mock_llm.set_tracer = Mock()
    return mock_llm


def _mock_cross_encoder() -> CrossEncoderClient:
    mock_ce = Mock(spec=CrossEncoderClient)
    mock_ce.config = Mock()
    mock_ce.rank = AsyncMock(return_value=[])
    return mock_ce


@pytest.fixture
async def graphiti_with_real_embedder(bfs_driver, real_embedder):
    """Graphiti instance wired with real MiniLM embedder + mock LLM/cross-encoder."""
    g = Graphiti(
        graph_driver=bfs_driver,
        llm_client=_mock_llm_client(),
        embedder=real_embedder,
        cross_encoder=_mock_cross_encoder(),
    )
    return g
