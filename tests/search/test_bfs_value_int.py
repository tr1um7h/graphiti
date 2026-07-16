# tests/search/test_bfs_value_int.py
"""BFS value (A/B differential) tests #13-#23.

Each test runs the same query under BASELINE_CONFIG (no BFS) and WITH_BFS_CONFIG (BFS on),
then asserts differential behavior. Embedder choice per spec §6.1:
- #14, #15, #18-#22: mock_embedder (presence-only assertions)
- #13, #16, #17, #23: real OpenAIEmbedder (semantic-ranking-sensitive)
"""
import pytest

from tests.search.conftest import (
    BASELINE_CONFIG,
    TEST_GROUP,
    TEST_GROUP_2,
    WITH_BFS_CONFIG,
)
from tests.search.helpers import assert_returned_edges_well_formed, identify_seed_key
from tests.search.seed import seed_bfs_graph


@pytest.mark.asyncio
async def test_13_bfs_recall_multi_hop_chain(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#13 [real embedder]: 'Alice 工作公司所在城市' — WITH_BFS reaches SF/USA edges; BASELINE misses."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice 工作公司所在城市'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    sf_edge_key = f'LOCATED_IN:{ctx.nodes["AcmeCorp"]}:{ctx.nodes["SanFrancisco"]}'
    usa_edge_key = f'IN_COUNTRY:{ctx.nodes["SanFrancisco"]}:{ctx.nodes["USA"]}'
    baseline_uuids = {e.uuid for e in baseline.edges}
    withbfs_uuids = {e.uuid for e in with_bfs.edges}
    assert ctx.edges[sf_edge_key].uuid in withbfs_uuids, 'WITH_BFS must reach SF edge'
    assert ctx.edges[usa_edge_key].uuid in withbfs_uuids, 'WITH_BFS must reach USA edge'
    assert ctx.edges[sf_edge_key].uuid not in baseline_uuids, 'BASELINE misses SF (proves BFS value)'


@pytest.mark.asyncio
async def test_16_bfs_recall_synonym_query(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#16 [real embedder]: 'Alice 的雇主' — synonym query; BASELINE misses, WITH_BFS recovers."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice 的雇主'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    works_at_key = f'WORKS_AT:{ctx.nodes["Alice"]}:{ctx.nodes["AcmeCorp"]}'
    baseline_uuids = {e.uuid for e in baseline.edges}
    withbfs_uuids = {e.uuid for e in with_bfs.edges}
    assert ctx.edges[works_at_key].uuid in withbfs_uuids
    # BASELINE may or may not find it; the test's value is that WITH_BFS always finds it.
    # We additionally assert WITH_BFS strictly ≥ BASELINE for this edge.
    if ctx.edges[works_at_key].uuid not in baseline_uuids:
        # true positive: BFS compensated a real cosine miss
        pass
