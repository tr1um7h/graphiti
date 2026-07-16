# tests/search/test_bfs_primitives_int.py
"""BFS primitive contract tests (#1-#12).

All primitive tests use BFS_ONLY_EDGE_CONFIG or driver.search_ops.edge_bfs_search
directly — no cosine path → no embedder call during search. Seeding uses mock_embedder.
"""
import pytest

from graphiti_core.search.search_filters import SearchFilters
from tests.search.conftest import TEST_GROUP, TEST_GROUP_2
from tests.search.helpers import (
    assert_edge_in_db,
    assert_edge_matches_seed,
    assert_returned_edges_well_formed,
    identify_seed_key,
    reference_bfs_reachable_edges,
    reference_bfs_reachable_nodes,
)
from tests.search.seed import seed_bfs_graph


@pytest.mark.asyncio
async def test_01_bfs_explicit_origin_returns_direct_neighbors(bfs_driver, mock_embedder):
    """#1: depth=1 from LeadBob returns exactly 3 MANAGES edges; each target ∈ {Carol, Dave, Eve}."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    leadbob = ctx.nodes['LeadBob']
    expected_targets = {ctx.nodes['EmpCarol'], ctx.nodes['EmpDave'], ctx.nodes['EmpEve']}

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [leadbob], 1, SearchFilters(), [TEST_GROUP], 10,
    )

    assert len(results) == 3
    await assert_returned_edges_well_formed(bfs_driver, results, ctx)
    returned_targets = {e.target_node_uuid for e in results}
    assert returned_targets == expected_targets
    for e in results:
        assert e.source_node_uuid == leadbob
        assert e.name == 'MANAGES'


@pytest.mark.asyncio
async def test_02_bfs_depth_3_traverses_full_chain(bfs_driver, mock_embedder):
    """#2: origin=Alice, depth=3 → WORKS_AT + LOCATED_IN + IN_COUNTRY (3 edges)."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    alice = ctx.nodes['Alice']

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [alice], 3, SearchFilters(), [TEST_GROUP], 10,
    )

    assert len(results) == 3
    await assert_returned_edges_well_formed(bfs_driver, results, ctx)
    edge_names = {e.name for e in results}
    assert edge_names == {'WORKS_AT', 'LOCATED_IN', 'IN_COUNTRY'}


@pytest.mark.asyncio
async def test_03_bfs_depth_1_excludes_far_nodes(bfs_driver, mock_embedder):
    """#3: origin=Alice, depth=1 → only WORKS_AT; LOCATED_IN / IN_COUNTRY out of range."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    alice = ctx.nodes['Alice']

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [alice], 1, SearchFilters(), [TEST_GROUP], 10,
    )

    assert len(results) == 1
    assert results[0].name == 'WORKS_AT'
    await assert_returned_edges_well_formed(bfs_driver, results, ctx)
    # Reference oracle confirms SF and USA are not 1-hop reachable from Alice.
    reachable = await reference_bfs_reachable_edges(bfs_driver, [alice], 1, [TEST_GROUP])
    sf_edge_uuid = ctx.edges[
        f'LOCATED_IN:{ctx.nodes["AcmeCorp"]}:{ctx.nodes["SanFrancisco"]}'
    ].uuid
    usa_edge_uuid = ctx.edges[
        f'IN_COUNTRY:{ctx.nodes["SanFrancisco"]}:{ctx.nodes["USA"]}'
    ].uuid
    assert sf_edge_uuid not in reachable
    assert usa_edge_uuid not in reachable


@pytest.mark.asyncio
async def test_04_bfs_empty_origin_returns_empty(bfs_driver, mock_embedder):
    """#4: empty origin list → empty results, no error."""
    await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [], 3, SearchFilters(), [TEST_GROUP], 10,
    )

    assert results == []


@pytest.mark.asyncio
async def test_05_bfs_none_origin_returns_empty(bfs_driver, mock_embedder):
    """#5: None origin → edge_bfs_search contract says None becomes [] at interface layer
    (interfaces.py:639); verify it returns empty."""
    await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, None, 3, SearchFilters(), [TEST_GROUP], 10,
    )

    assert results == []


@pytest.mark.asyncio
async def test_06_bfs_depth_0_raises_value_error(bfs_driver, mock_embedder):
    """#6: max_depth=0 raises ValueError per _validate_bfs_depth (search_ops.py:531)."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    alice = ctx.nodes['Alice']

    with pytest.raises(ValueError, match='max_depth must be between 1 and 5'):
        await bfs_driver.search_ops.edge_bfs_search(
            bfs_driver, [alice], 0, SearchFilters(), [TEST_GROUP], 10,
        )


@pytest.mark.asyncio
async def test_07_bfs_depth_6_raises_value_error(bfs_driver, mock_embedder):
    """#7: max_depth=6 raises ValueError."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    alice = ctx.nodes['Alice']

    with pytest.raises(ValueError, match='max_depth must be between 1 and 5'):
        await bfs_driver.search_ops.edge_bfs_search(
            bfs_driver, [alice], 6, SearchFilters(), [TEST_GROUP], 10,
        )


@pytest.mark.asyncio
async def test_08_bfs_directed_no_outgoing_returns_empty(bfs_driver, mock_embedder):
    """#8: BFS from terminal node (TopZ, no outgoing edges) returns empty → directed."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    topz = ctx.nodes['TopZ']

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [topz], 3, SearchFilters(), [TEST_GROUP], 10,
    )

    assert results == []
    # Reference oracle: TopZ has no outgoing edges at any depth.
    reachable = await reference_bfs_reachable_edges(bfs_driver, [topz], 3, [TEST_GROUP])
    assert reachable == set()


@pytest.mark.asyncio
async def test_09_bfs_directed_reverse_traversal_excluded(bfs_driver, mock_embedder):
    """#9: origin=AcmeCorp, depth=2 → only LOCATED_IN; WORKS_AT (Alice→AcmeCorp) excluded.

    Alice→AcmeCorp is reverse-direction relative to AcmeCorp; BFS does not walk it.
    """
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    acme = ctx.nodes['AcmeCorp']

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [acme], 2, SearchFilters(), [TEST_GROUP], 10,
    )

    await assert_returned_edges_well_formed(bfs_driver, results, ctx)
    edge_names = {e.name for e in results}
    assert 'LOCATED_IN' in edge_names
    assert 'WORKS_AT' not in edge_names  # reverse traversal would be required to reach it
    # Reference oracle confirms Alice is not reachable from AcmeCorp via outgoing edges.
    reachable_nodes = await reference_bfs_reachable_nodes(bfs_driver, [acme], 2, [TEST_GROUP])
    assert ctx.nodes['Alice'] not in reachable_nodes
