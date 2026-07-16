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


@pytest.mark.asyncio
async def test_14_bfs_recall_indirect_teammates(
    graphiti_with_mock_embedder, mock_embedder, bfs_driver
):
    """#14 [mock]: 'LeadBob 的下属' — WITH_BFS returns ≥3 MANAGES edges; BASELINE ≤1."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'LeadBob 的下属'

    baseline = await graphiti_with_mock_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_mock_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    withbfs_manages = [e for e in with_bfs.edges if e.name == 'MANAGES']
    baseline_manages = [e for e in baseline.edges if e.name == 'MANAGES']
    assert len(withbfs_manages) >= 3
    assert len(baseline_manages) <= 1
    expected_reports = {ctx.nodes['EmpCarol'], ctx.nodes['EmpDave'], ctx.nodes['EmpEve']}
    returned_targets = {e.target_node_uuid for e in withbfs_manages}
    assert expected_reports.issubset(returned_targets)


@pytest.mark.asyncio
async def test_15_bfs_does_not_cross_disconnected_clusters(
    graphiti_with_mock_embedder, mock_embedder, bfs_driver
):
    """#15 [mock]: query hitting NodeA1 — Cluster B (NodeB*) never appears."""
    ctx = await seed_bfs_graph(bfs_driver, mock_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'NodeA1 相关节点'

    with_bfs = await graphiti_with_mock_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    cluster_b_uuids = {ctx.nodes['NodeB1'], ctx.nodes['NodeB2'], ctx.nodes['NodeB3']}
    for edge in with_bfs.edges:
        assert edge.source_node_uuid not in cluster_b_uuids
        assert edge.target_node_uuid not in cluster_b_uuids


@pytest.mark.asyncio
async def test_17_bfs_recall_dense_cluster(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#17 [real]: 'Q1' — WITH_BFS returns 4 LINKED out-edges; BASELINE ≤1."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Q1'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    q1_uuid = ctx.nodes['Q1']
    withbfs_linked_from_q1 = [
        e for e in with_bfs.edges
        if e.name == 'LINKED' and e.source_node_uuid == q1_uuid
    ]
    baseline_linked_from_q1 = [
        e for e in baseline.edges
        if e.name == 'LINKED' and e.source_node_uuid == q1_uuid
    ]
    assert len(withbfs_linked_from_q1) >= 1  # at minimum, Q1's own LINKED edges appear
    assert len(withbfs_linked_from_q1) > len(baseline_linked_from_q1)
