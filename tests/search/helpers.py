# tests/search/helpers.py
"""Verification helpers: field equality, DB round-trip, reference BFS oracle."""
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge

from tests.search.seed import BFSGraphContext


def identify_seed_key(edge: EntityEdge, ctx: BFSGraphContext) -> str | None:
    """Reverse-lookup the seed edge key for a returned edge."""
    key = f'{edge.name}:{edge.source_node_uuid}:{edge.target_node_uuid}'
    return key if key in ctx.edges else None


def assert_edge_matches_seed(returned: EntityEdge, expected_key: str, ctx: BFSGraphContext) -> None:
    """Field-equality check against the seed ground truth."""
    expected = ctx.edges[expected_key]
    assert returned.uuid == expected.uuid, f'uuid mismatch: {returned.uuid} != {expected.uuid}'
    assert returned.source_node_uuid == expected.source_node_uuid
    assert returned.target_node_uuid == expected.target_node_uuid
    assert returned.name == expected.name
    assert returned.fact == expected.fact
    assert returned.group_id == expected.group_id


async def assert_edge_in_db(
    driver: GraphDriver, returned_uuid: str, expected_key: str, ctx: BFSGraphContext
) -> None:
    """DB round-trip: returned edge must exist in DB with matching core fields."""
    expected = ctx.edges[expected_key]
    db_edge = await EntityEdge.get_by_uuid(driver, returned_uuid)
    assert db_edge is not None, f'edge {returned_uuid} not found in DB'
    assert db_edge.source_node_uuid == expected.source_node_uuid
    assert db_edge.target_node_uuid == expected.target_node_uuid
    assert db_edge.group_id == expected.group_id
    assert db_edge.name == expected.name


async def reference_bfs_reachable_edges(
    driver: GraphDriver,
    origin_uuids: list[str],
    max_depth: int,
    group_ids: list[str] | None,
) -> set[str]:
    """Independent Cypher/SQL oracle for reachable edge UUIDs.

    Implemented via recursive CTE mirroring the spec semantics:
    walk outgoing entity_edges + episodic_edges; collect distinct edges whose
    source is at depth < max_depth. Used to validate edge_bfs_search output.
    """
    params: dict[str, object] = {
        'origin_uuids': origin_uuids,
        'max_depth': max_depth,
        'limit': 1000,
        'walk_group_ids': group_ids,
    }
    records, _, _ = await driver.execute_query(
        """
        WITH RECURSIVE walk(uuid, depth) AS (
            SELECT unnest(%(origin_uuids)s::text[]) AS uuid, 0 AS depth
            UNION
            SELECT adjacency.target_node_uuid, walk.depth + 1
            FROM walk
            JOIN (
                SELECT source_node_uuid, target_node_uuid, group_id FROM episodic_edges
                UNION ALL
                SELECT source_node_uuid, target_node_uuid, group_id FROM entity_edges
            ) adjacency ON adjacency.source_node_uuid = walk.uuid
            WHERE walk.depth < %(max_depth)s
              AND (
                %(walk_group_ids)s::text[] IS NULL
                OR adjacency.group_id = ANY(%(walk_group_ids)s::text[])
              )
        )
        SELECT DISTINCT e.uuid AS uuid
        FROM entity_edges e
        JOIN walk ON walk.uuid = e.source_node_uuid
        WHERE walk.depth < %(max_depth)s
        LIMIT %(limit)s
        """,
        params=params,
        routing_='r',
    )
    return {row['uuid'] for row in records}


async def reference_bfs_reachable_nodes(
    driver: GraphDriver,
    origin_uuids: list[str],
    max_depth: int,
    group_ids: list[str] | None,
) -> set[str]:
    """Reference oracle for node BFS: returns node UUIDs reachable in 1..max_depth hops."""
    params: dict[str, object] = {
        'origin_uuids': origin_uuids,
        'max_depth': max_depth,
        'limit': 1000,
        'walk_group_ids': group_ids,
    }
    records, _, _ = await driver.execute_query(
        """
        WITH RECURSIVE walk(uuid, depth) AS (
            SELECT unnest(%(origin_uuids)s::text[]) AS uuid, 0 AS depth
            UNION
            SELECT adjacency.target_node_uuid, walk.depth + 1
            FROM walk
            JOIN (
                SELECT source_node_uuid, target_node_uuid, group_id FROM episodic_edges
                UNION ALL
                SELECT source_node_uuid, target_node_uuid, group_id FROM entity_edges
            ) adjacency ON adjacency.source_node_uuid = walk.uuid
            WHERE walk.depth < %(max_depth)s
              AND (
                %(walk_group_ids)s::text[] IS NULL
                OR adjacency.group_id = ANY(%(walk_group_ids)s::text[])
              )
        )
        SELECT DISTINCT n.uuid AS uuid
        FROM entity_nodes n
        JOIN walk ON walk.uuid = n.uuid
        WHERE walk.depth > 0
        LIMIT %(limit)s
        """,
        params=params,
        routing_='r',
    )
    return {row['uuid'] for row in records}


async def assert_returned_edges_well_formed(
    driver: GraphDriver,
    returned_edges: list[EntityEdge],
    ctx: BFSGraphContext,
) -> None:
    """Common post-condition: every returned edge matches a seed edge and round-trips via DB."""
    for edge in returned_edges:
        key = identify_seed_key(edge, ctx)
        assert key is not None, f'returned edge not in seed: {edge.uuid} name={edge.name}'
        assert_edge_matches_seed(edge, key, ctx)
        await assert_edge_in_db(driver, edge.uuid, key, ctx)
