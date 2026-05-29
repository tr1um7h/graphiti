from __future__ import annotations

from graphiti_core.driver.operations.entity_edge_ops import EntityEdgeOperations
from graphiti_core.driver.postgres_age.operations._helpers import (
    jsonb,
    operation_transaction,
    run_age_cypher,
    run_statement,
)
from graphiti_core.driver.postgres_age.projection import (
    edge_delete_projection_cypher,
    edge_projection_cypher,
)
from graphiti_core.driver.postgres_age.records import entity_edge_from_row
from graphiti_core.driver.postgres_age.serialization import entity_edge_to_row
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.edges import EntityEdge
from graphiti_core.errors import EdgeNotFoundError


class PostgresAgeEntityEdgeOperations(EntityEdgeOperations):
    async def save(
        self,
        executor: QueryExecutor,
        edge: EntityEdge,
        tx: Transaction | None = None,
    ) -> None:
        row = entity_edge_to_row(edge)
        row['attributes'] = jsonb(executor, row['attributes'])
        async with operation_transaction(executor, tx) as op_tx:
            await run_statement(
                executor,
                op_tx,
                """
                INSERT INTO entity_edges (
                    uuid, group_id, source_node_uuid, target_node_uuid, name, fact,
                    fact_embedding, episodes, expired_at, valid_at, invalid_at,
                    reference_time, attributes, created_at
                )
                VALUES (
                    %(uuid)s, %(group_id)s, %(source_node_uuid)s, %(target_node_uuid)s,
                    %(name)s, %(fact)s, %(fact_embedding)s, %(episodes)s, %(expired_at)s,
                    %(valid_at)s, %(invalid_at)s, %(reference_time)s, %(attributes)s,
                    %(created_at)s
                )
                ON CONFLICT (uuid) DO UPDATE SET
                    group_id = EXCLUDED.group_id,
                    source_node_uuid = EXCLUDED.source_node_uuid,
                    target_node_uuid = EXCLUDED.target_node_uuid,
                    name = EXCLUDED.name,
                    fact = EXCLUDED.fact,
                    fact_embedding = EXCLUDED.fact_embedding,
                    episodes = EXCLUDED.episodes,
                    expired_at = EXCLUDED.expired_at,
                    valid_at = EXCLUDED.valid_at,
                    invalid_at = EXCLUDED.invalid_at,
                    reference_time = EXCLUDED.reference_time,
                    attributes = EXCLUDED.attributes,
                    created_at = EXCLUDED.created_at
                """,
                row,
            )
            await self._save_projection(executor, op_tx, edge)

    async def save_bulk(
        self,
        executor: QueryExecutor,
        edges: list[EntityEdge],
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        async with operation_transaction(executor, tx) as bulk_tx:
            for edge in edges:
                await self.save(executor, edge, bulk_tx)

    async def delete(
        self,
        executor: QueryExecutor,
        edge: EntityEdge,
        tx: Transaction | None = None,
    ) -> None:
        await self.delete_by_uuids(executor, [edge.uuid], tx)

    async def delete_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None = None,
    ) -> None:
        if not uuids:
            return

        async with operation_transaction(executor, tx) as op_tx:
            for uuid in uuids:
                await run_age_cypher(
                    executor,
                    op_tx,
                    edge_delete_projection_cypher('RELATES_TO', uuid),
                )
            await run_statement(
                executor,
                op_tx,
                'DELETE FROM entity_edges WHERE uuid = ANY(%(uuids)s)',
                {'uuids': uuids},
            )

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EntityEdge:
        records, _, _ = await executor.execute_query(
            'SELECT * FROM entity_edges WHERE uuid = %(uuid)s',
            params={'uuid': uuid},
            routing_='r',
        )
        if not records:
            raise EdgeNotFoundError(uuid)
        return entity_edge_from_row(records[0])

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EntityEdge]:
        if not uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            SELECT *
            FROM entity_edges
            WHERE uuid = ANY(%(uuids)s)
            ORDER BY uuid
            """,
            params={'uuids': uuids},
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EntityEdge]:
        limit_clause = 'LIMIT %(limit)s' if limit is not None else ''
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM entity_edges
            WHERE group_id = ANY(%(group_ids)s)
              AND (%(uuid_cursor)s::text IS NULL OR uuid < %(uuid_cursor)s)
            ORDER BY uuid DESC
            {limit_clause}
            """,
            params={'group_ids': group_ids, 'uuid_cursor': uuid_cursor, 'limit': limit},
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def get_between_nodes(
        self,
        executor: QueryExecutor,
        source_node_uuid: str,
        target_node_uuid: str,
    ) -> list[EntityEdge]:
        records, _, _ = await executor.execute_query(
            """
            SELECT *
            FROM entity_edges
            WHERE source_node_uuid = %(source_node_uuid)s
              AND target_node_uuid = %(target_node_uuid)s
            ORDER BY uuid
            """,
            params={
                'source_node_uuid': source_node_uuid,
                'target_node_uuid': target_node_uuid,
            },
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def get_by_node_uuid(
        self,
        executor: QueryExecutor,
        node_uuid: str,
    ) -> list[EntityEdge]:
        records, _, _ = await executor.execute_query(
            """
            SELECT *
            FROM entity_edges
            WHERE source_node_uuid = %(node_uuid)s
               OR target_node_uuid = %(node_uuid)s
            ORDER BY uuid
            """,
            params={'node_uuid': node_uuid},
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def load_embeddings(
        self,
        executor: QueryExecutor,
        edge: EntityEdge,
    ) -> None:
        records, _, _ = await executor.execute_query(
            'SELECT fact_embedding FROM entity_edges WHERE uuid = %(uuid)s',
            params={'uuid': edge.uuid},
            routing_='r',
        )
        if not records:
            raise EdgeNotFoundError(edge.uuid)
        edge.fact_embedding = entity_edge_from_row(
            {**entity_edge_to_row(edge), **records[0]}
        ).fact_embedding

    async def load_embeddings_bulk(
        self,
        executor: QueryExecutor,
        edges: list[EntityEdge],
        batch_size: int = 100,
    ) -> None:
        uuids = [edge.uuid for edge in edges]
        if not uuids:
            return
        records, _, _ = await executor.execute_query(
            'SELECT uuid, fact_embedding FROM entity_edges WHERE uuid = ANY(%(uuids)s)',
            params={'uuids': uuids},
            routing_='r',
        )
        embeddings = {row['uuid']: row['fact_embedding'] for row in records}
        for edge in edges:
            if edge.uuid in embeddings:
                edge.fact_embedding = entity_edge_from_row(
                    {**entity_edge_to_row(edge), 'fact_embedding': embeddings[edge.uuid]}
                ).fact_embedding

    async def _save_projection(
        self,
        executor: QueryExecutor,
        tx: Transaction | None,
        edge: EntityEdge,
    ) -> None:
        await run_age_cypher(
            executor,
            tx,
            edge_delete_projection_cypher('RELATES_TO', edge.uuid),
        )
        await run_age_cypher(
            executor,
            tx,
            edge_projection_cypher(
                'RELATES_TO',
                'Entity',
                'Entity',
                edge.uuid,
                edge.group_id,
                edge.source_node_uuid,
                edge.target_node_uuid,
                edge.name,
            ),
        )
