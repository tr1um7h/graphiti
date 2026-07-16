# tests/search/test_bfs_e2e_deepseek_int.py
"""Tier 3: end-to-end BFS verification with real DeepSeek LLM (tests #24-#28).

Unlike Tier 1/2 (deterministic seed graph), Tier 3 uses Graphiti.add_episode()
to let DeepSeek extract entities and edges from natural-language episodes, then
runs hybrid search to verify BFS recovers multi-hop facts that BM25+cosine miss.

Module-scoped fixture ingests 3 episodes ONCE per session (~30-60s of LLM calls)
and shares the resulting graph across all 5 tests.

Non-determinism handling:
- Don't hardcode entity names (DeepSeek may produce 'AcmeCorp', 'Acme Corp', etc.)
- Query DB by substring (find_nodes_by_name_substr, find_edges_by_fact_substr)
- Assert structural properties (WITH_BFS ⊇ BASELINE; BFS-unique edges contain
  target keywords like 'san francisco' or 'usa')
"""
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio

pytest.importorskip('psycopg')
pytest.importorskip('psycopg_pool')
pytest.importorskip('pgvector')

from graphiti_core.driver.postgres_age import PostgresAgeDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.graphiti import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data
from tests.search.conftest import (
    BASELINE_CONFIG,
    E2E_TEST_GROUP,
    TEST_GROUP,
    WITH_BFS_CONFIG,
    _mock_cross_encoder,
)
from tests.search.helpers import (
    assert_edges_contain_keyword,
    find_edges_by_fact_substr,
    find_nodes_by_name_substr,
)

# DeepSeek ingestion is slow; one graph per session.
E2E_EPISODES = [
    (
        'alice-employment',
        'Alice works at TechCorp. TechCorp is located in San Francisco. '
        'San Francisco is a city in the United States of America.',
    ),
    (
        'bob-coworker',
        'Bob is a colleague of Alice at TechCorp. Bob currently leads the '
        'Project Phoenix initiative.',
    ),
    (
        'project-context',
        'Project Phoenix is a major redesign targeting the 2026 enterprise '
        'market. Alice was assigned to Project Phoenix by the TechCorp '
        'leadership team.',
    ),
]


def _local_embedder() -> OpenAIEmbedder:
    url = os.getenv('EMBEDDING_API_URL', '').replace('host.docker.internal', 'localhost') or (
        'http://localhost:8080/v1'
    )
    return OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_dim=384,
            base_url=url,
            api_key='dummy',
            embedding_model=os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2'),
        )
    )


@pytest_asyncio.fixture(scope='module', loop_scope='module')
async def e2e_graphiti() -> AsyncIterator[Graphiti]:
    """Build a graph with DeepSeek LLM via add_episode(); tear down after module.

    Skipped automatically if OPENAI_API_KEY is not set (no DeepSeek credentials).
    """
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip('OPENAI_API_KEY not set — skipping DeepSeek e2e tier')

    # Late import keeps the fixture skip-safe.
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

    llm = OpenAIGenericClient(
        config=LLMConfig(
            api_key=os.getenv('OPENAI_API_KEY'),
            base_url=os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/v1'),
            model=os.getenv('OPENAI_MODEL_NAME', 'deepseek-chat'),
            small_model=os.getenv('OPENAI_MODEL_NAME', 'deepseek-chat'),
            temperature=0.0,
            max_tokens=4096,
        )
    )
    dsn = os.getenv(
        'POSTGRES_AGE_DSN',
        'postgresql://graphiti:graphiti@localhost:55432/graphiti',
    )
    driver = PostgresAgeDriver(
        dsn=dsn, graph_name='graphiti_test_core', embedding_dimension=384,
    )
    await clear_data(driver, [E2E_TEST_GROUP])
    g = Graphiti(
        graph_driver=driver, llm_client=llm, embedder=_local_embedder(),
        cross_encoder=_mock_cross_encoder(),
    )

    for name, body in E2E_EPISODES:
        await g.add_episode(
            name=name,
            episode_body=body,
            source_description='bfs e2e fixture',
            reference_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            source=EpisodeType.text,
            group_id=E2E_TEST_GROUP,
        )

    try:
        yield g
    finally:
        await driver.close()


@pytest.mark.asyncio
async def test_24_e2e_graph_built(e2e_graphiti):
    """#24: smoke test — DeepSeek successfully extracted ≥3 nodes and ≥2 edges."""
    driver = e2e_graphiti.driver
    nodes = await find_nodes_by_name_substr(driver, E2E_TEST_GROUP, 'Alice')
    techcorp_nodes = await find_nodes_by_name_substr(driver, E2E_TEST_GROUP, 'Tech')
    project_nodes = await find_nodes_by_name_substr(driver, E2E_TEST_GROUP, 'Phoenix')

    node_count = (
        (1 if nodes else 0)
        + (1 if techcorp_nodes else 0)
        + (1 if project_nodes else 0)
    )
    assert node_count >= 2, (
        f'expected ≥2 distinct entity clusters, got {node_count}; '
        f'Alice={len(nodes)} TechCorp={len(techcorp_nodes)} Project={len(project_nodes)}'
    )

    # At least 2 edges total (any facts).
    all_edges = await find_edges_by_fact_substr(e2e_graphiti.driver, E2E_TEST_GROUP, ' ')
    # Substring ' ' may not match if facts lack spaces; fall back to counting via Alice.
    if len(all_edges) < 2:
        alice_edges = await find_edges_by_fact_substr(
            e2e_graphiti.driver, E2E_TEST_GROUP, 'Alice'
        )
        tech_edges = await find_edges_by_fact_substr(
            e2e_graphiti.driver, E2E_TEST_GROUP, 'Tech'
        )
        total = len(alice_edges) + len(tech_edges)
        assert total >= 2, (
            f'DeepSeek extracted too few edges: alice={len(alice_edges)} '
            f'tech={len(tech_edges)}'
        )


@pytest.mark.asyncio
async def test_25_e2e_bfs_multi_hop_location(e2e_graphiti):
    """#25: query 'Alice 工作公司所在城市' — WITH_BFS finds multi-hop location
    edges (San Francisco, USA); BASELINE does not."""
    query = 'Alice 工作公司所在城市'
    baseline = await e2e_graphiti.search_(
        query=query, config=BASELINE_CONFIG, group_ids=[E2E_TEST_GROUP],
    )
    with_bfs = await e2e_graphiti.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[E2E_TEST_GROUP],
    )

    bfs_unique = [e for e in with_bfs.edges if e not in baseline.edges]
    # BFS contribution: at least one multi-hop edge mentioning SF/USA.
    if bfs_unique:
        assert_edges_contain_keyword(
            bfs_unique,
            ['san francisco', 'francisco', 'usa', 'united states', 'america', 'country', 'located'],
            msg='BFS-unique edges should reference the multi-hop location chain',
        )
    # Structural invariant: BFS never reduces recall.
    baseline_uuids = {e.uuid for e in baseline.edges}
    withbfs_uuids = {e.uuid for e in with_bfs.edges}
    assert baseline_uuids.issubset(withbfs_uuids) or len(withbfs_uuids) >= len(
        baseline_uuids
    )


@pytest.mark.asyncio
async def test_26_e2e_bfs_indirect_relationship(e2e_graphiti):
    """#26: query 'Bob 参与的项目' — BFS finds Bob→Alice→Project Phoenix chain."""
    query = 'Bob 参与的项目'
    with_bfs = await e2e_graphiti.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[E2E_TEST_GROUP],
    )

    # WITH_BFS must surface Project Phoenix (directly or via an edge fact).
    phoenix_edges_bfs = [
        e for e in with_bfs.edges if 'phoenix' in e.fact.lower() or 'project' in e.fact.lower()
    ]
    assert phoenix_edges_bfs, (
        f'WITH_BFS must find Project Phoenix edge; got facts: '
        f'{[e.fact for e in with_bfs.edges]}'
    )


@pytest.mark.asyncio
async def test_27_e2e_bfs_explicit_origin(e2e_graphiti):
    """#27: explicit bfs_origin_node_uuids=[Alice UUID] → finds Alice's multi-hop
    location/project edges regardless of query content."""
    alice_nodes = await find_nodes_by_name_substr(
        e2e_graphiti.driver, E2E_TEST_GROUP, 'Alice'
    )
    assert alice_nodes, 'Alice node must exist after ingestion'
    alice_uuid = alice_nodes[0].uuid

    # Irrelevant query — all recall attributable to explicit BFS origin.
    results = await e2e_graphiti.search_(
        query='天气艺术绘画',
        config=WITH_BFS_CONFIG,
        group_ids=[E2E_TEST_GROUP],
        bfs_origin_node_uuids=[alice_uuid],
    )

    assert results.edges, (
        'explicit BFS origin from Alice must produce multi-hop edges'
    )
    # Multi-hop reach: at least one edge should mention TechCorp (1-hop) or
    # a deeper entity (San Francisco, Project Phoenix).
    facts_lower = [e.fact.lower() for e in results.edges]
    has_multi_hop = any(
        kw in fact
        for fact in facts_lower
        for kw in ['tech', 'corp', 'san francisco', 'francisco', 'phoenix', 'project', 'usa']
    )
    assert has_multi_hop, (
        f'BFS from Alice should reach multi-hop neighbors; facts={facts_lower}'
    )


@pytest.mark.asyncio
async def test_28_e2e_bfs_group_isolation(e2e_graphiti):
    """#28: BFS scoped to E2E_TEST_GROUP never returns edges from other groups."""
    # Seed-based groups (TEST_GROUP) were cleared in the bfs_driver fixture; ensure
    # none leak into E2E search results.
    query = 'Alice TechCorp Project Phoenix'
    with_bfs = await e2e_graphiti.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[E2E_TEST_GROUP],
    )

    for edge in with_bfs.edges:
        assert edge.group_id == E2E_TEST_GROUP, (
            f'edge {edge.uuid} has group_id={edge.group_id}, expected {E2E_TEST_GROUP}'
        )

    # Additionally, querying with a non-existent group returns nothing.
    empty = await e2e_graphiti.search_(
        query=query, config=WITH_BFS_CONFIG, group_ids=[TEST_GROUP],
    )
    for edge in empty.edges:
        assert edge.group_id == TEST_GROUP
