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

import numpy as np

# Build deterministic mock embeddings for all BFS fixture node names + edge facts.
# Uses a fixed seed so results are reproducible across runs.
_BFS_NAMES = [
    # G1 nodes
    'Alice', 'AcmeCorp', 'SanFrancisco', 'USA',
    'SinkX', 'MidY', 'TopZ',
    'LeadBob', 'EmpCarol', 'EmpDave', 'EmpEve',
    'NodeA1', 'NodeA2', 'NodeA3',
    'NodeB1', 'NodeB2', 'NodeB3',
    'Q1', 'Q2', 'Q3', 'Q4', 'Q5',
    'OldEvent', 'NewEvent', '2020Anchor', '2025Anchor',
    'SalaryNode',
    # G2 nodes
    'Alice2', 'AcmeCorp2', 'SanFrancisco2', 'USA2',
    'SinkX2', 'MidY2', 'TopZ2',
]
# Edge fact strings (matching _edge() default: '{src} {edge_name} {dst}')
_BFS_EDGE_NAMES = [
    'Alice WORKS_AT AcmeCorp', 'AcmeCorp LOCATED_IN SanFrancisco',
    'SanFrancisco IN_COUNTRY USA',
    'SinkX BELONGS_TO MidY', 'MidY PART_OF TopZ',
    'LeadBob MANAGES EmpCarol', 'LeadBob MANAGES EmpDave', 'LeadBob MANAGES EmpEve',
    'NodeA1 RELATED NodeA2', 'NodeA2 RELATED NodeA3', 'NodeA3 RELATED NodeA1',
    'NodeB1 RELATED NodeB2', 'NodeB2 RELATED NodeB3', 'NodeB3 RELATED NodeB1',
    'OldEvent OCCURRED_ON 2020Anchor', 'NewEvent OCCURRED_ON 2025Anchor',
    'Alice HAS_SALARY SalaryNode',
    # Clique Q (10 edges)
    'Q1 LINKED Q2', 'Q1 LINKED Q3', 'Q1 LINKED Q4', 'Q1 LINKED Q5',
    'Q2 LINKED Q3', 'Q2 LINKED Q4', 'Q2 LINKED Q5',
    'Q3 LINKED Q4', 'Q3 LINKED Q5', 'Q4 LINKED Q5',
    # G2 edges
    'Alice2 WORKS_AT AcmeCorp2', 'AcmeCorp2 LOCATED_IN SanFrancisco2',
    'SanFrancisco2 IN_COUNTRY USA2',
    'SinkX2 BELONGS_TO MidY2', 'MidY2 PART_OF TopZ2',
]
_rng = np.random.RandomState(42)
_BFS_EMBEDDINGS = {
    name: _rng.uniform(0.0, 0.9, 384).tolist()
    for name in _BFS_NAMES + _BFS_EDGE_NAMES
}

# Query strings used by mock-embedder tests (semantic-class tests go through real_embedder).
MOCK_QUERY_EMBEDDINGS = {
    **_BFS_EMBEDDINGS,
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
    """Mock embedder using the extended helpers.embeddings dict."""
    from unittest.mock import Mock
    from graphiti_core.embedder.client import EmbedderClient

    mock_model = Mock(spec=EmbedderClient)

    def mock_embed(input_data):
        if isinstance(input_data, str):
            return helpers.embeddings[input_data]
        elif isinstance(input_data, list):
            combined_input = ' '.join(input_data)
            return helpers.embeddings[combined_input]
        else:
            raise ValueError(f'Unsupported input type: {type(input_data)}')

    mock_model.create.side_effect = mock_embed
    return mock_model


@pytest.fixture
def real_embedder():
    """Real OpenAI embedder; skip cleanly when OPENAI_API_KEY is unset."""
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip('OPENAI_API_KEY not set; skipping real-embedder BFS test')
    return OpenAIEmbedder(config=OpenAIEmbedderConfig(embedding_dim=384))


from unittest.mock import AsyncMock, Mock

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.graphiti import Graphiti
from graphiti_core.llm_client import LLMClient


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
async def graphiti_with_mock_embedder(bfs_driver, mock_embedder):
    """Graphiti instance wired with mock_embedder + mock LLM/cross-encoder. Use for #14,#15,#18-#22."""
    g = Graphiti(
        graph_driver=bfs_driver,
        llm_client=_mock_llm_client(),
        embedder=mock_embedder,
        cross_encoder=_mock_cross_encoder(),
    )
    return g


@pytest.fixture
async def graphiti_with_real_embedder(bfs_driver, real_embedder):
    """Graphiti instance wired with real OpenAIEmbedder. Use for #13,#16,#17,#23."""
    g = Graphiti(
        graph_driver=bfs_driver,
        llm_client=_mock_llm_client(),
        embedder=real_embedder,
        cross_encoder=_mock_cross_encoder(),
    )
    return g
