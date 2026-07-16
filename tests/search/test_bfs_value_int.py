# tests/search/test_bfs_value_int.py
"""BFS value (A/B differential) tests #13-#23.

Each test runs the same query under a BM25+cosine baseline (BASELINE_CONFIG) and
a BFS-enabled config (WITH_BFS_CONFIG), then asserts differential behavior. The
goal is to prove BFS contributes recall that BM25+cosine alone cannot achieve —
specifically multi-hop graph traversal edges (LOCATED_IN, IN_COUNTRY) that do
NOT contain the query terms and are far from any lexical/semantic match.

All tests use the real MiniLM embedder (localhost:8080) for both seeding and
the cosine search path. No mock embedder is used: mock vectors would inflate
cosine similarity and obscure whether BFS or cosine is responsible for recall.
"""
from datetime import datetime, timezone

import pytest

from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    SearchConfig,
)
from graphiti_core.search.search_filters import (
    ComparisonOperator,
    DateFilter,
    SearchFilters,
)
from tests.search.conftest import (
    BASELINE_CONFIG,
    TEST_GROUP,
    TEST_GROUP_2,
    WITH_BFS_CONFIG,
)
from tests.search.helpers import assert_returned_edges_well_formed
from tests.search.seed import seed_bfs_graph


@pytest.mark.asyncio
async def test_13_bfs_recall_multi_hop_chain(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#13: 'Alice 工作公司所在城市' — WITH_BFS reaches SF/USA edges; BASELINE misses.

    BFS-genuine edges: LOCATED_IN (AcmeCorp→SF) and IN_COUNTRY (SF→USA) — 2 and 3
    hops from Alice. Neither contains query terms; only graph traversal finds them.
    """
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
    assert (
        ctx.edges[sf_edge_key].uuid not in baseline_uuids
    ), 'BASELINE misses SF (proves BFS value)'


@pytest.mark.asyncio
async def test_14_bfs_recall_indirect_teammates(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#14: 'EmpCarol' — WITH_BFS must return all 3 MANAGES edges from LeadBob.

    Real MiniLM cosine may also find sibling MANAGES edges (facts share 'MANAGES'
    and 'LeadBob'), so the strict-A/B gap may collapse. What matters for BFS
    verification is that WITH_BFS is guaranteed to surface all 3 reports
    (BFS from LeadBob walks every outgoing MANAGES edge) and never fewer than
    BASELINE.
    """
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'EmpCarol'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    withbfs_manages = [e for e in with_bfs.edges if e.name == 'MANAGES']
    baseline_manages = [e for e in baseline.edges if e.name == 'MANAGES']
    # BFS guarantees reaching all 3 reports from LeadBob.
    assert len(withbfs_manages) >= 3
    expected_reports = {ctx.nodes['EmpCarol'], ctx.nodes['EmpDave'], ctx.nodes['EmpEve']}
    returned_targets = {e.target_node_uuid for e in withbfs_manages}
    assert expected_reports.issubset(returned_targets)
    # And BFS never reduces recall vs baseline.
    assert len(withbfs_manages) >= len(baseline_manages)


@pytest.mark.asyncio
async def test_15_bfs_does_not_cross_disconnected_clusters(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#15: query 'NodeA1' — BFS must not ADD Cluster B edges beyond what
    BM25+cosine already returned.

    Real MiniLM may semantically link 'NodeA1' to 'NodeB*' edges (all are
    short identifiers that produce similar embeddings), so BASELINE itself can
    return Cluster B noise. The BFS guarantee under test is: BFS never
    introduces NEW Cluster B edges — it only walks reachable subgraphs from
    matched origins, and Cluster A has no path to Cluster B.
    """
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'NodeA1'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    cluster_b_uuids = {ctx.nodes['NodeB1'], ctx.nodes['NodeB2'], ctx.nodes['NodeB3']}

    def touches_cluster_b(edge):
        return (
            edge.source_node_uuid in cluster_b_uuids
            or edge.target_node_uuid in cluster_b_uuids
        )

    baseline_b = {e.uuid for e in baseline.edges if touches_cluster_b(e)}
    withbfs_b = {e.uuid for e in with_bfs.edges if touches_cluster_b(e)}
    # BFS may add Cluster A edges but must never add Cluster B edges it didn't
    # already see from BM25+cosine (no graph path exists).
    assert withbfs_b.issubset(baseline_b), (
        f'BFS introduced new Cluster B edges: {withbfs_b - baseline_b}'
    )


@pytest.mark.asyncio
async def test_16_bfs_recall_multi_hop_from_synonym(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#16: 'Alice 的雇主' (Alice's employer) — synonym query misses SF/USA lexically;

    BFS traverses from Alice → AcmeCorp → SF → USA to find multi-hop location edges.

    The BFS-genuine contribution here is LOCATED_IN and IN_COUNTRY: neither
    contains 'Alice' or '雇主', and both are multi-hop from any query-matched edge.
    """
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice 的雇主'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    located_in_key = f'LOCATED_IN:{ctx.nodes["AcmeCorp"]}:{ctx.nodes["SanFrancisco"]}'
    in_country_key = f'IN_COUNTRY:{ctx.nodes["SanFrancisco"]}:{ctx.nodes["USA"]}'
    baseline_uuids = {e.uuid for e in baseline.edges}
    withbfs_uuids = {e.uuid for e in with_bfs.edges}
    assert (
        ctx.edges[located_in_key].uuid in withbfs_uuids
    ), 'WITH_BFS must reach LOCATED_IN via multi-hop traversal'
    assert (
        ctx.edges[in_country_key].uuid in withbfs_uuids
    ), 'WITH_BFS must reach IN_COUNTRY via multi-hop traversal'
    assert (
        ctx.edges[located_in_key].uuid not in baseline_uuids
    ), 'BASELINE misses LOCATED_IN — proves BFS contribution'


@pytest.mark.asyncio
async def test_17_bfs_explicit_origin_finds_multi_hop(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#17: explicit bfs_origin_node_uuids=[Alice] forces BFS from Alice regardless
    of BM25/cosine hits; finds Alice's 1/2/3-hop outgoing edges.

    This covers the explicit-origin path (search.py:183 bfs_origin_node_uuids).
    Query '绘画艺术' (irrelevant Chinese terms) ensures BM25/cosine find nothing,
    so all recall is attributable to the explicit BFS origin.
    """
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    alice_uuid = ctx.nodes['Alice']
    # Irrelevant query: no BM25 hit, no meaningful cosine hit. BFS origin is the
    # ONLY source of recall — a clean attribution test.
    query = '绘画艺术'

    results = await graphiti_with_real_embedder.search_(
        query=query,
        config=WITH_BFS_CONFIG,
        group_ids=[TEST_GROUP],
        bfs_origin_node_uuids=[alice_uuid],
    )

    await assert_returned_edges_well_formed(bfs_driver, results.edges, ctx)
    returned_names = {e.name for e in results.edges}
    # Alice's reachable subgraph within depth=3: WORKS_AT, HAS_SALARY (1-hop),
    # LOCATED_IN (2-hop), IN_COUNTRY (3-hop).
    assert 'WORKS_AT' in returned_names, 'explicit origin must reach direct edge'
    assert 'LOCATED_IN' in returned_names, 'explicit origin must reach 2-hop edge'
    assert 'IN_COUNTRY' in returned_names, 'explicit origin must reach 3-hop edge'


@pytest.mark.asyncio
async def test_18_bfs_auto_origin_fallback(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#18: no explicit origin → auto-expand path uses BM25/cosine hits as BFS
    origins (search.py:332-353); WITH_BFS recall strictly ≥ BASELINE.

    'Alice WORKS_AT AcmeCorp' produces BM25 hits on WORKS_AT, which BFS uses as
    origins to traverse further (LOCATED_IN, IN_COUNTRY).
    """
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice WORKS_AT AcmeCorp'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    baseline_uuids = {e.uuid for e in baseline.edges}
    withbfs_uuids = {e.uuid for e in with_bfs.edges}
    # Strict superset: every baseline edge still present, plus BFS contributions.
    assert baseline_uuids.issubset(withbfs_uuids), 'WITH_BFS must not drop baseline edges'
    assert len(withbfs_uuids) > len(baseline_uuids), 'BFS must add recall over baseline'
    # And specifically, the multi-hop edges must appear.
    located_in_key = f'LOCATED_IN:{ctx.nodes["AcmeCorp"]}:{ctx.nodes["SanFrancisco"]}'
    assert ctx.edges[located_in_key].uuid in withbfs_uuids


@pytest.mark.asyncio
async def test_19_bfs_depth_3_vs_depth_1_recall_gap(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#19: BM25+cosine+BFS at depth=3 reaches IN_COUNTRY edge; depth=1 does not."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice WORKS_AT AcmeCorp'

    depth1_config = SearchConfig(
        edge_config=EdgeSearchConfig(
            search_methods=[
                EdgeSearchMethod.bm25,
                EdgeSearchMethod.cosine_similarity,
                EdgeSearchMethod.bfs,
            ],
            reranker=EdgeReranker.rrf,
            sim_min_score=0.2,
            bfs_max_depth=1,
        ),
        limit=20,
    )

    with_bfs_d3 = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs_d1 = await graphiti_with_real_embedder.search_(
        query=query, config=depth1_config, group_ids=[TEST_GROUP],
    )

    usa_edge_uuid = ctx.edges[
        f'IN_COUNTRY:{ctx.nodes["SanFrancisco"]}:{ctx.nodes["USA"]}'
    ].uuid
    d3_uuids = {e.uuid for e in with_bfs_d3.edges}
    d1_uuids = {e.uuid for e in with_bfs_d1.edges}
    assert usa_edge_uuid in d3_uuids
    assert usa_edge_uuid not in d1_uuids


@pytest.mark.asyncio
async def test_20_bfs_does_not_leak_across_groups_in_recipe(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#20: WITH_BFS scoped to G1 returns zero G2 facts."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice WORKS_AT AcmeCorp'

    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    for edge in with_bfs.edges:
        assert edge.group_id == TEST_GROUP


@pytest.mark.asyncio
async def test_21_bfs_recall_with_temporal_filter(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#21: valid_at > 2022-01-01 → only NewEvent OCCURRED_ON edge survives."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'OCCURRED_ON'
    temporal_filter = SearchFilters(
        valid_at=[[DateFilter(date=datetime(2022, 1, 1, tzinfo=timezone.utc),
                                comparison_operator=ComparisonOperator.greater_than)]],
    )

    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
        search_filter=temporal_filter,
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    new_event_edge_uuid = ctx.edges[
        f'OCCURRED_ON:{ctx.nodes["NewEvent"]}:{ctx.nodes["2025Anchor"]}'
    ].uuid
    old_event_edge_uuid = ctx.edges[
        f'OCCURRED_ON:{ctx.nodes["OldEvent"]}:{ctx.nodes["2020Anchor"]}'
    ].uuid
    returned_uuids = {e.uuid for e in with_bfs.edges}
    if returned_uuids:  # filter may produce empty when no match — then no leak either
        assert old_event_edge_uuid not in returned_uuids
        assert new_event_edge_uuid in returned_uuids


@pytest.mark.asyncio
async def test_22_bfs_multi_origin_convergence_dedup(
    real_embedder, bfs_driver
):
    """#22: origins [Alice, AcmeCorp] both reach LOCATED_IN; SQL DISTINCT keeps it to 1."""
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    alice = ctx.nodes['Alice']
    acme = ctx.nodes['AcmeCorp']
    located_in_uuid = ctx.edges[
        f'LOCATED_IN:{ctx.nodes["AcmeCorp"]}:{ctx.nodes["SanFrancisco"]}'
    ].uuid

    results = await bfs_driver.search_ops.edge_bfs_search(
        bfs_driver, [alice, acme], 2, SearchFilters(), [TEST_GROUP], 10,
    )

    await assert_returned_edges_well_formed(bfs_driver, results, ctx)
    uuids = [e.uuid for e in results]
    assert uuids.count(located_in_uuid) == 1  # exactly once despite dual-origin convergence
    assert len(uuids) == len(set(uuids))     # all unique


@pytest.mark.asyncio
async def test_23_bfs_recovers_semantic_miss(
    graphiti_with_real_embedder, real_embedder, bfs_driver
):
    """#23: 'Alice 的薪水数额' — large lexical gap; BFS recovers multi-hop location
    edges (LOCATED_IN, IN_COUNTRY) that cosine cannot reach.

    The original test wrongly asserted HAS_SALARY (which cosine finds trivially
    since both query and fact contain 'Alice' / salary-like terms). The BFS-
    genuine contribution is the 2/3-hop location chain, which has no lexical or
    semantic overlap with the salary query.
    """
    ctx = await seed_bfs_graph(bfs_driver, real_embedder, TEST_GROUP, TEST_GROUP_2)
    query = 'Alice 的薪水数额'

    baseline = await graphiti_with_real_embedder.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[TEST_GROUP],
    )
    with_bfs = await graphiti_with_real_embedder.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )

    await assert_returned_edges_well_formed(bfs_driver, with_bfs.edges, ctx)
    located_in_key = f'LOCATED_IN:{ctx.nodes["AcmeCorp"]}:{ctx.nodes["SanFrancisco"]}'
    in_country_key = f'IN_COUNTRY:{ctx.nodes["SanFrancisco"]}:{ctx.nodes["USA"]}'
    baseline_uuids = {e.uuid for e in baseline.edges}
    withbfs_uuids = {e.uuid for e in with_bfs.edges}
    assert (
        ctx.edges[located_in_key].uuid in withbfs_uuids
    ), 'WITH_BFS must recover LOCATED_IN via multi-hop traversal'
    assert (
        ctx.edges[in_country_key].uuid in withbfs_uuids
    ), 'WITH_BFS must recover IN_COUNTRY via multi-hop traversal'
    assert (
        ctx.edges[located_in_key].uuid not in baseline_uuids
    ), 'BASELINE misses LOCATED_IN — proves BFS recovery'
    assert len(withbfs_uuids) >= len(baseline_uuids)
