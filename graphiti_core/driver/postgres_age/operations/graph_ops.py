from __future__ import annotations

from typing import Any

from graphiti_core.driver.operations.graph_ops import GraphMaintenanceOperations
from graphiti_core.driver.operations.graph_utils import Neighbor, label_propagation
from graphiti_core.driver.postgres_age.operations._helpers import (
    operation_transaction,
    run_age_cypher,
    run_statement,
)
from graphiti_core.driver.postgres_age.projection import (
    edge_projection_cypher,
    node_projection_cypher,
)
from graphiti_core.driver.postgres_age.records import community_node_from_row, entity_node_from_row
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodicNode


class PostgresAgeGraphMaintenanceOperations(GraphMaintenanceOperations):
    async def clear_data(
        self,
        executor: QueryExecutor,
        group_ids: list[str] | None = None,
    ) -> None:
        async with operation_transaction(executor, None) as tx:
            if group_ids is None:
                await run_age_cypher(executor, tx, 'MATCH (n) DETACH DELETE n')
                for table_name in _CANONICAL_DELETE_ORDER:
                    await run_statement(executor, tx, f'DELETE FROM {table_name}', {})
                return

            for table_name in _EDGE_TABLES:
                await run_statement(
                    executor,
                    tx,
                    f'DELETE FROM {table_name} WHERE group_id = ANY(%(group_ids)s)',
                    {'group_ids': group_ids},
                )
            for table_name in _NODE_DELETE_ORDER:
                await run_statement(
                    executor,
                    tx,
                    f'DELETE FROM {table_name} WHERE group_id = ANY(%(group_ids)s)',
                    {'group_ids': group_ids},
                )
            await _delete_dangling_community_edges(executor, tx)
            await self._rebuild_age_projection_in_transaction(executor, tx)

    async def build_indices_and_constraints(
        self,
        executor: QueryExecutor,
        delete_existing: bool = False,
    ) -> None:
        postgres_executor: Any = executor
        await postgres_executor.build_indices_and_constraints(delete_existing=delete_existing)

    async def delete_all_indexes(
        self,
        executor: QueryExecutor,
    ) -> None:
        postgres_executor: Any = executor
        await postgres_executor.delete_all_indexes()

    async def get_community_clusters(
        self,
        executor: QueryExecutor,
        group_ids: list[str] | None = None,
    ) -> list[Any]:
        resolved_group_ids = group_ids
        if resolved_group_ids is None:
            group_records, _, _ = await executor.execute_query(
                """
                SELECT DISTINCT group_id
                FROM entity_nodes
                ORDER BY group_id
                """,
                routing_='r',
            )
            resolved_group_ids = [row['group_id'] for row in group_records]

        community_clusters: list[list[EntityNode]] = []
        for group_id in resolved_group_ids or []:
            node_records, _, _ = await executor.execute_query(
                """
                SELECT *
                FROM entity_nodes
                WHERE group_id = %(group_id)s
                ORDER BY uuid
                """,
                params={'group_id': group_id},
                routing_='r',
            )
            nodes = [entity_node_from_row(row) for row in node_records]
            projection: dict[str, list[Neighbor]] = {node.uuid: [] for node in nodes}

            edge_records, _, _ = await executor.execute_query(
                """
                SELECT source_node_uuid, target_node_uuid, count(*) AS edge_count
                FROM entity_edges
                WHERE group_id = %(group_id)s
                GROUP BY source_node_uuid, target_node_uuid
                """,
                params={'group_id': group_id},
                routing_='r',
            )
            for row in edge_records:
                source = row['source_node_uuid']
                target = row['target_node_uuid']
                count = int(row['edge_count'])
                if source in projection and target in projection:
                    projection[source].append(Neighbor(node_uuid=target, edge_count=count))
                    projection[target].append(Neighbor(node_uuid=source, edge_count=count))

            for cluster in label_propagation(projection):
                if not cluster:
                    continue
                community_clusters.append([node for node in nodes if node.uuid in cluster])

        return community_clusters

    async def remove_communities(
        self,
        executor: QueryExecutor,
    ) -> None:
        async with operation_transaction(executor, None) as tx:
            await run_statement(executor, tx, 'DELETE FROM community_edges', {})
            await run_statement(executor, tx, 'DELETE FROM community_nodes', {})
            await self._rebuild_age_projection_in_transaction(executor, tx)

    async def determine_entity_community(
        self,
        executor: QueryExecutor,
        entity: EntityNode,
    ) -> Any:
        records, _, _ = await executor.execute_query(
            """
            SELECT c.*
            FROM community_nodes c
            JOIN community_edges e ON e.source_node_uuid = c.uuid
            WHERE e.target_node_uuid = %(entity_uuid)s
            ORDER BY c.uuid
            LIMIT 1
            """,
            params={'entity_uuid': entity.uuid},
            routing_='r',
        )
        if records:
            return community_node_from_row(records[0]), False

        records, _, _ = await executor.execute_query(
            """
            SELECT c.*, count(*) AS membership_count
            FROM community_nodes c
            JOIN community_edges ce ON ce.source_node_uuid = c.uuid
            JOIN entity_edges ee ON (
                (ee.source_node_uuid = %(entity_uuid)s AND ee.target_node_uuid = ce.target_node_uuid)
                OR (ee.target_node_uuid = %(entity_uuid)s AND ee.source_node_uuid = ce.target_node_uuid)
            )
            GROUP BY c.uuid,
                     c.group_id,
                     c.name,
                     c.summary,
                     c.name_embedding,
                     c.created_at,
                     c.search_vector
            ORDER BY membership_count DESC, c.uuid
            LIMIT 1
            """,
            params={'entity_uuid': entity.uuid},
            routing_='r',
        )
        if records:
            return community_node_from_row(records[0]), True

        return None, False

    async def get_mentioned_nodes(
        self,
        executor: QueryExecutor,
        episodes: list[EpisodicNode],
    ) -> list[EntityNode]:
        episode_uuids = [episode.uuid for episode in episodes]
        if not episode_uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            SELECT DISTINCT n.*
            FROM entity_nodes n
            JOIN episodic_edges e ON e.target_node_uuid = n.uuid
            WHERE e.source_node_uuid = ANY(%(episode_uuids)s)
            ORDER BY n.uuid
            """,
            params={'episode_uuids': episode_uuids},
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def get_communities_by_nodes(
        self,
        executor: QueryExecutor,
        nodes: list[EntityNode],
    ) -> list[CommunityNode]:
        node_uuids = [node.uuid for node in nodes]
        if not node_uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            SELECT DISTINCT c.*
            FROM community_nodes c
            JOIN community_edges e ON e.source_node_uuid = c.uuid
            WHERE e.target_node_uuid = ANY(%(node_uuids)s)
            ORDER BY c.uuid
            """,
            params={'node_uuids': node_uuids},
            routing_='r',
        )
        return [community_node_from_row(row) for row in records]

    async def rebuild_age_projection(self, executor: QueryExecutor) -> None:
        async with operation_transaction(executor, None) as tx:
            await self._rebuild_age_projection_in_transaction(executor, tx)

    async def _rebuild_age_projection_in_transaction(
        self,
        executor: QueryExecutor,
        tx: Transaction | None,
    ) -> None:
        await _delete_dangling_community_edges(executor, tx)
        await run_age_cypher(executor, tx, 'MATCH (n) DETACH DELETE n')
        await _rebuild_nodes(executor, tx)
        await _rebuild_edges(executor, tx)


async def _rebuild_nodes(executor: QueryExecutor, tx: Transaction | None) -> None:
    for table_name, label in _NODE_PROJECTION_TABLES:
        records, _, _ = await _run_read(
            executor,
            tx,
            f"""
            SELECT uuid, group_id, name
            FROM {table_name}
            ORDER BY uuid
            """,
            {},
        )
        for row in records:
            await run_age_cypher(
                executor,
                tx,
                node_projection_cypher(label, row['uuid'], row['group_id'], row['name']),
            )


async def _rebuild_edges(executor: QueryExecutor, tx: Transaction | None) -> None:
    await _rebuild_entity_edges(executor, tx)
    await _rebuild_simple_edges(executor, tx, 'episodic_edges', 'MENTIONS', 'Episodic', 'Entity')
    await _rebuild_community_edges(executor, tx)
    await _rebuild_simple_edges(executor, tx, 'has_episode_edges', 'HAS_EPISODE', 'Saga', 'Episodic')
    await _rebuild_simple_edges(
        executor, tx, 'next_episode_edges', 'NEXT_EPISODE', 'Episodic', 'Episodic'
    )


async def _rebuild_entity_edges(executor: QueryExecutor, tx: Transaction | None) -> None:
    records, _, _ = await _run_read(
        executor,
        tx,
        """
        SELECT uuid, group_id, source_node_uuid, target_node_uuid, name
        FROM entity_edges
        ORDER BY uuid
        """,
        {},
    )
    for row in records:
        await run_age_cypher(
            executor,
            tx,
            edge_projection_cypher(
                'RELATES_TO',
                'Entity',
                'Entity',
                row['uuid'],
                row['group_id'],
                row['source_node_uuid'],
                row['target_node_uuid'],
                row['name'],
            ),
        )


async def _rebuild_simple_edges(
    executor: QueryExecutor,
    tx: Transaction | None,
    table_name: str,
    edge_type: str,
    source_label: str,
    target_label: str,
) -> None:
    records, _, _ = await _run_read(
        executor,
        tx,
        f"""
        SELECT uuid, group_id, source_node_uuid, target_node_uuid
        FROM {table_name}
        ORDER BY uuid
        """,
        {},
    )
    for row in records:
        await run_age_cypher(
            executor,
            tx,
            edge_projection_cypher(
                edge_type,
                source_label,
                target_label,
                row['uuid'],
                row['group_id'],
                row['source_node_uuid'],
                row['target_node_uuid'],
            ),
        )


async def _rebuild_community_edges(executor: QueryExecutor, tx: Transaction | None) -> None:
    records, _, _ = await _run_read(
        executor,
        tx,
        """
        SELECT e.uuid,
               e.group_id,
               e.source_node_uuid,
               e.target_node_uuid,
               CASE WHEN c.uuid IS NULL THEN 'Entity' ELSE 'Community' END AS target_label
        FROM community_edges e
        LEFT JOIN community_nodes c ON c.uuid = e.target_node_uuid
        ORDER BY e.uuid
        """,
        {},
    )
    for row in records:
        await run_age_cypher(
            executor,
            tx,
            edge_projection_cypher(
                'HAS_MEMBER',
                'Community',
                row['target_label'],
                row['uuid'],
                row['group_id'],
                row['source_node_uuid'],
                row['target_node_uuid'],
            ),
        )


async def _delete_dangling_community_edges(
    executor: QueryExecutor, tx: Transaction | None
) -> None:
    await run_statement(
        executor,
        tx,
        """
        DELETE FROM community_edges e
        WHERE NOT EXISTS (
            SELECT 1 FROM community_nodes c WHERE c.uuid = e.source_node_uuid
        )
           OR (
               NOT EXISTS (SELECT 1 FROM entity_nodes n WHERE n.uuid = e.target_node_uuid)
               AND NOT EXISTS (SELECT 1 FROM community_nodes c WHERE c.uuid = e.target_node_uuid)
           )
        """,
        {},
    )


async def _run_read(
    executor: QueryExecutor,
    tx: Transaction | None,
    query: str,
    params: dict[str, Any],
):
    if tx is not None:
        return await tx.run(query, params=params)
    return await executor.execute_query(query, params=params, routing_='r')


_EDGE_TABLES = (
    'next_episode_edges',
    'has_episode_edges',
    'community_edges',
    'episodic_edges',
    'entity_edges',
)
_NODE_DELETE_ORDER = ('saga_nodes', 'community_nodes', 'episodic_nodes', 'entity_nodes')
_CANONICAL_DELETE_ORDER = _EDGE_TABLES + _NODE_DELETE_ORDER
_NODE_PROJECTION_TABLES = (
    ('entity_nodes', 'Entity'),
    ('episodic_nodes', 'Episodic'),
    ('community_nodes', 'Community'),
    ('saga_nodes', 'Saga'),
)
