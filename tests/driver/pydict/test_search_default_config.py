"""Unit tests for Graphiti.search_ with COMBINED_HYBRID_SEARCH_JCHEN default config.

Verifies that the PyDict driver supports the full search pipeline:
- Node bm25 + rrf reranker
- Edge bm25 + bfs + mmr reranker
"""

from unittest.mock import Mock

import pytest

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.pydict_driver import PydictDriver
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.graphiti import Graphiti
from graphiti_core.llm_client import LLMClient
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_JCHEN
from graphiti_core.search.search_config import SearchResults


class MockEmbedder(EmbedderClient):
    """Mock embedder that returns deterministic 384-dim vectors."""

    async def create(self, input_data):
        return [0.1] * 384

    async def create_batch(self, input_data_list):
        return [[0.1 * (i + 1)] * 384 for i in range(len(input_data_list))]


@pytest.fixture
def mock_embedder():
    """Mock embedder that returns 384-dim vectors."""
    return MockEmbedder()


@pytest.fixture
def mock_llm_client():
    """Mock LLM client (not called during search, but required by Graphiti)."""
    mock = Mock(spec=LLMClient)
    mock.config = Mock()
    mock.model = 'test-model'
    mock.small_model = 'test-small-model'
    mock.temperature = 0.0
    mock.max_tokens = 1000
    mock.cache_enabled = False
    mock.cache_dir = None
    return mock


@pytest.fixture
def mock_cross_encoder():
    """Mock cross encoder (not called for MMR, but required by Graphiti)."""
    mock = Mock(spec=CrossEncoderClient)
    mock.config = Mock()
    mock.rank = Mock(return_value=[])
    return mock


@pytest.fixture
def pydict_driver():
    """Fresh PyDict driver for each test."""
    return PydictDriver()


@pytest.fixture
def graphiti(pydict_driver, mock_llm_client, mock_embedder, mock_cross_encoder):
    """Graphiti instance backed by PyDict driver."""
    return Graphiti(
        graph_driver=pydict_driver,
        llm_client=mock_llm_client,
        embedder=mock_embedder,
        cross_encoder=mock_cross_encoder,
    )


class TestSearchDefaultConfig:
    """Test Graphiti.search_ with the default COMBINED_HYBRID_SEARCH_JCHEN config."""

    @pytest.mark.asyncio
    async def test_default_config_is_jchen(self):
        """Verify that search_ uses COMBINED_HYBRID_SEARCH_JCHEN by default."""
        import inspect

        sig = inspect.signature(Graphiti.search_)
        default_value = sig.parameters['config'].default
        assert default_value is COMBINED_HYBRID_SEARCH_JCHEN

    @pytest.mark.asyncio
    async def test_search_returns_search_results(self, graphiti, pydict_driver):
        """search_ should return a SearchResults object."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', embedder=graphiti.embedder)
        await pydict_driver.add_memory('bob', 'works_at', 'google', embedder=graphiti.embedder)

        results = await graphiti.search_('alice works_at', group_ids=['default'])

        assert isinstance(results, SearchResults)

    @pytest.mark.asyncio
    async def test_search_finds_edges_via_bm25_and_mmr(self, graphiti, pydict_driver):
        """Edge bm25 + MMR should find and rank matching edges."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', embedder=graphiti.embedder)
        await pydict_driver.add_memory('bob', 'works_at', 'google', embedder=graphiti.embedder)
        await pydict_driver.add_memory('carol', 'lives_in', 'beijing', embedder=graphiti.embedder)

        results = await graphiti.search_('works_at', group_ids=['default'])

        # Should find both 'works_at' edges, not 'lives_in'
        edge_names = [e.name for e in results.edges]
        assert len(results.edges) == 2
        assert all(name == 'works_at' for name in edge_names)
        # MMR should produce scores
        assert len(results.edge_reranker_scores) == 2

    @pytest.mark.asyncio
    async def test_search_finds_nodes_via_bm25(self, graphiti, pydict_driver):
        """Node bm25 + rrf should find matching nodes."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', embedder=graphiti.embedder)
        await pydict_driver.add_memory('bob', 'works_at', 'google', embedder=graphiti.embedder)

        results = await graphiti.search_('alice', group_ids=['default'])

        # Should find alice node
        node_names = [n.name for n in results.nodes]
        assert 'alice' in node_names

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, graphiti, pydict_driver):
        """Empty query should return empty SearchResults."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', embedder=graphiti.embedder)

        results = await graphiti.search_('', group_ids=['default'])

        assert isinstance(results, SearchResults)
        assert len(results.edges) == 0
        assert len(results.nodes) == 0

    @pytest.mark.asyncio
    async def test_search_bfs_explores_graph(self, graphiti, pydict_driver):
        """BFS search should explore connected edges."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', embedder=graphiti.embedder)
        await pydict_driver.add_memory('paic', 'located_in', 'shenzhen', embedder=graphiti.embedder)

        results = await graphiti.search_('works_at', group_ids=['default'])

        assert isinstance(results, SearchResults)
        # Should find at least the works_at edge
        assert len(results.edges) >= 1

    @pytest.mark.asyncio
    async def test_search_mmr_with_embeddings(self, graphiti, pydict_driver):
        """MMR reranker should return scores when edges have embeddings."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', embedder=graphiti.embedder)
        await pydict_driver.add_memory('bob', 'works_at', 'google', embedder=graphiti.embedder)

        results = await graphiti.search_('works_at', group_ids=['default'])

        # MMR scores should be non-empty
        assert len(results.edge_reranker_scores) > 0
        # All scores should be floats
        assert all(isinstance(s, float) for s in results.edge_reranker_scores)

    @pytest.mark.asyncio
    async def test_search_filters_by_group(self, graphiti, pydict_driver):
        """search_ should only return results from the specified group."""
        await pydict_driver.add_memory('alice', 'works_at', 'paic', group_id='group-a', embedder=graphiti.embedder)
        await pydict_driver.add_memory('bob', 'works_at', 'google', group_id='group-b', embedder=graphiti.embedder)

        results = await graphiti.search_('works_at', group_ids=['group-a'])

        # All edges should be from group-a
        for edge in results.edges:
            assert edge.group_id == 'group-a'

    @pytest.mark.asyncio
    async def test_full_pipeline_multiple_memories(self, graphiti, pydict_driver):
        """Full pipeline test with multiple memories and complex query."""
        # Seed diverse data
        await pydict_driver.add_memory('alice', 'works_at', 'paic', target_type='company', embedder=graphiti.embedder)
        await pydict_driver.add_memory('alice', 'lives_in', 'shenzhen', embedder=graphiti.embedder)
        await pydict_driver.add_memory('bob', 'works_at', 'google', target_type='company', embedder=graphiti.embedder)
        await pydict_driver.add_memory('carol', 'studies_at', 'tsinghua', target_type='university', embedder=graphiti.embedder)

        results = await graphiti.search_('alice company', group_ids=['default'])

        assert isinstance(results, SearchResults)
        # Should find results (edges and/or nodes mentioning alice or company)
        total_results = len(results.edges) + len(results.nodes)
        assert total_results > 0