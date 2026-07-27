"""Unit tests for PydictDriver.add_memory and search methods."""

from datetime import datetime, timezone

import pytest

from graphiti_core.driver.pydict_driver import PydictDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodicNode


@pytest.fixture
def driver() -> PydictDriver:
    """Create a fresh PydictDriver for each test."""
    return PydictDriver()


class TestAddMemory:
    """Tests for PydictDriver.add_memory."""

    @pytest.mark.asyncio
    async def test_add_memory_creates_entity_nodes(self, driver: PydictDriver):
        """add_memory should create source and target EntityNodes."""
        await driver.add_memory('alice', 'works_at', 'paic', target_type='company')

        # Verify nodes exist
        nodes = await driver.entity_node_ops.get_by_group_ids(driver, ['default'])
        names = {n.name for n in nodes}
        assert 'alice' in names
        assert 'paic' in names

    @pytest.mark.asyncio
    async def test_add_memory_sets_target_labels(self, driver: PydictDriver):
        """add_memory should set labels on target node when target_type is provided."""
        await driver.add_memory('alice', 'works_at', 'paic', target_type='company')

        nodes = await driver.entity_node_ops.get_by_group_ids(driver, ['default'])
        paic_node = next(n for n in nodes if n.name == 'paic')
        assert 'company' in paic_node.labels

    @pytest.mark.asyncio
    async def test_add_memory_creates_entity_edge(self, driver: PydictDriver):
        """add_memory should create an EntityEdge connecting source and target."""
        await driver.add_memory('alice', 'works_at', 'paic')

        edges = await driver.entity_edge_ops.get_by_group_ids(driver, ['default'])
        assert len(edges) == 1
        assert edges[0].name == 'works_at'
        assert edges[0].fact == 'alice works_at paic'

    @pytest.mark.asyncio
    async def test_add_memory_creates_episode(self, driver: PydictDriver):
        """add_memory should create an EpisodicNode recording the fact."""
        await driver.add_memory('alice', 'works_at', 'paic')

        episodes = await driver.episode_node_ops.get_by_group_ids(driver, ['default'])
        assert len(episodes) == 1
        assert 'alice works_at paic' in episodes[0].content

    @pytest.mark.asyncio
    async def test_add_memory_creates_episodic_edges(self, driver: PydictDriver):
        """add_memory should create MENTIONS edges from episode to both entities."""
        await driver.add_memory('alice', 'works_at', 'paic')

        episodic_edges = await driver.episodic_edge_ops.get_by_group_ids(driver, ['default'])
        assert len(episodic_edges) == 2  # episode -> alice, episode -> paic

    @pytest.mark.asyncio
    async def test_add_memory_multiple_triplets(self, driver: PydictDriver):
        """add_memory should handle multiple triplets independently."""
        await driver.add_memory('alice', 'works_at', 'paic', target_type='company')
        await driver.add_memory('bob', 'works_at', 'google', target_type='company')
        await driver.add_memory('alice', 'lives_in', 'shenzhen')

        nodes = await driver.entity_node_ops.get_by_group_ids(driver, ['default'])
        # alice, paic, bob, google, shenzhen = 5 unique nodes
        # Note: alice may appear twice due to separate calls
        unique_names = {n.name for n in nodes}
        assert 'alice' in unique_names
        assert 'bob' in unique_names
        assert 'paic' in unique_names
        assert 'google' in unique_names
        assert 'shenzhen' in unique_names

        edges = await driver.entity_edge_ops.get_by_group_ids(driver, ['default'])
        assert len(edges) == 3

    @pytest.mark.asyncio
    async def test_add_memory_with_custom_group_id(self, driver: PydictDriver):
        """add_memory should respect the group_id parameter."""
        await driver.add_memory('alice', 'works_at', 'paic', group_id='test-group')

        nodes = await driver.entity_node_ops.get_by_group_ids(driver, ['test-group'])
        assert len(nodes) == 2  # alice and paic

        nodes_default = await driver.entity_node_ops.get_by_group_ids(driver, ['default'])
        assert len(nodes_default) == 0


class TestSearch:
    """Tests for PydictDriver.search."""

    @pytest.mark.asyncio
    async def test_search_returns_matching_edges(self, driver: PydictDriver):
        """search should return EntityEdges matching the query."""
        await driver.add_memory('alice', 'works_at', 'paic')
        await driver.add_memory('bob', 'lives_in', 'beijing')

        result = await driver.search('works_at')

        assert len(result['edges']) >= 1
        edge_names = {e.name for e in result['edges']}
        assert 'works_at' in edge_names

    @pytest.mark.asyncio
    async def test_search_returns_matching_nodes(self, driver: PydictDriver):
        """search should return EntityNodes matching the query."""
        await driver.add_memory('alice', 'works_at', 'paic')
        await driver.add_memory('bob', 'works_at', 'google')

        result = await driver.search('alice')

        assert len(result['nodes']) >= 1
        node_names = {n.name for n in result['nodes']}
        assert 'alice' in node_names

    @pytest.mark.asyncio
    async def test_search_returns_matching_episodes(self, driver: PydictDriver):
        """search should return EpisodicNodes matching the query."""
        await driver.add_memory('alice', 'works_at', 'paic')

        result = await driver.search('works_at')

        assert len(result['episodes']) >= 1
        episode_contents = [e.content for e in result['episodes']]
        assert any('works_at' in c for c in episode_contents)

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, driver: PydictDriver):
        """search should limit results to the specified limit."""
        for i in range(10):
            await driver.add_memory(f'person{i}', 'knows', f'target{i}')

        result = await driver.search('knows', limit=3)

        assert len(result['nodes']) <= 3
        assert len(result['edges']) <= 3
        assert len(result['episodes']) <= 3

    @pytest.mark.asyncio
    async def test_search_filters_by_group_ids(self, driver: PydictDriver):
        """search should only return results from specified groups."""
        await driver.add_memory('alice', 'works_at', 'paic', group_id='group-a')
        await driver.add_memory('bob', 'works_at', 'google', group_id='group-b')

        result = await driver.search('works_at', group_ids=['group-a'])

        # All results should be from group-a
        for node in result['nodes']:
            assert node.group_id == 'group-a'
        for edge in result['edges']:
            assert edge.group_id == 'group-a'
        for episode in result['episodes']:
            assert episode.group_id == 'group-a'

    @pytest.mark.asyncio
    async def test_search_empty_store_returns_empty_results(self, driver: PydictDriver):
        """search on an empty store should return empty lists."""
        result = await driver.search('nonexistent')

        assert result['nodes'] == []
        assert result['edges'] == []
        assert result['episodes'] == []

    @pytest.mark.asyncio
    async def test_search_no_matches_returns_empty_results(self, driver: PydictDriver):
        """search with no matching content should return empty lists."""
        await driver.add_memory('alice', 'works_at', 'paic')

        result = await driver.search('xyzzy')

        assert result['nodes'] == []
        assert result['edges'] == []
        assert result['episodes'] == []


class TestSearchOperations:
    """Tests for PyDictSearchOperations methods."""

    @pytest.mark.asyncio
    async def test_node_fulltext_search_matches_name(self, driver: PydictDriver):
        """node_fulltext_search should match node names."""
        await driver.add_memory('alice', 'works_at', 'paic')

        from graphiti_core.search.search_filters import SearchFilters

        nodes = await driver.search_ops.node_fulltext_search(
            driver, 'alice', SearchFilters(), limit=10
        )
        assert any(n.name == 'alice' for n in nodes)

    @pytest.mark.asyncio
    async def test_edge_fulltext_search_matches_fact(self, driver: PydictDriver):
        """edge_fulltext_search should match edge facts."""
        await driver.add_memory('alice', 'works_at', 'paic')

        from graphiti_core.search.search_filters import SearchFilters

        edges = await driver.search_ops.edge_fulltext_search(
            driver, 'works_at', SearchFilters(), limit=10
        )
        assert any('works_at' in e.fact for e in edges)

    @pytest.mark.asyncio
    async def test_episode_fulltext_search_matches_content(self, driver: PydictDriver):
        """episode_fulltext_search should match episode content."""
        await driver.add_memory('alice', 'works_at', 'paic')

        from graphiti_core.search.search_filters import SearchFilters

        episodes = await driver.search_ops.episode_fulltext_search(
            driver, 'works_at', SearchFilters(), limit=10
        )
        assert any('works_at' in ep.content for ep in episodes)