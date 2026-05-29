from __future__ import annotations

from typing import Any, Generic, TypeVar

from graphiti_core.driver.postgres_age.operations._helpers import (
    operation_transaction,
    run_age_cypher,
    run_statement,
)
from graphiti_core.driver.postgres_age.projection import (
    edge_delete_projection_cypher,
    edge_projection_cypher,
)
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.edges import CommunityEdge, EpisodicEdge, HasEpisodeEdge, NextEpisodeEdge
from graphiti_core.errors import EdgeNotFoundError

SimpleEdge = TypeVar('SimpleEdge', CommunityEdge, EpisodicEdge, HasEpisodeEdge, NextEpisodeEdge)


class PostgresAgeSimpleEdgeOperations(Generic[SimpleEdge]):
    table_name: str
    edge_type: str
    source_label: str
    target_label: str

    def edge_to_row(self, edge: SimpleEdge) -> dict[str, Any]:
        raise NotImplementedError

    def edge_from_row(self, row: dict[str, Any]) -> SimpleEdge:
        raise NotImplementedError

    async def save(
        self,
        executor: QueryExecutor,
        edge: SimpleEdge,
        tx: Transaction | None = None,
    ) -> None:
        async with operation_transaction(executor, tx) as op_tx:
            await run_statement(
                executor,
                op_tx,
                f"""
                INSERT INTO {self.table_name} (
                    uuid, group_id, source_node_uuid, target_node_uuid, created_at
                )
                VALUES (
                    %(uuid)s, %(group_id)s, %(source_node_uuid)s,
                    %(target_node_uuid)s, %(created_at)s
                )
                ON CONFLICT (uuid) DO UPDATE SET
                    group_id = EXCLUDED.group_id,
                    source_node_uuid = EXCLUDED.source_node_uuid,
                    target_node_uuid = EXCLUDED.target_node_uuid,
                    created_at = EXCLUDED.created_at
                """,
                self.edge_to_row(edge),
            )
            await self._save_projection(executor, op_tx, edge)

    async def save_bulk(
        self,
        executor: QueryExecutor,
        edges: list[SimpleEdge],
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        async with operation_transaction(executor, tx) as bulk_tx:
            for edge in edges:
                await self.save(executor, edge, bulk_tx)

    async def delete(
        self,
        executor: QueryExecutor,
        edge: SimpleEdge,
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
                await self._delete_projection(executor, op_tx, uuid)
            await run_statement(
                executor,
                op_tx,
                f'DELETE FROM {self.table_name} WHERE uuid = ANY(%(uuids)s)',
                {'uuids': uuids},
            )

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> SimpleEdge:
        records, _, _ = await executor.execute_query(
            f'SELECT * FROM {self.table_name} WHERE uuid = %(uuid)s',
            params={'uuid': uuid},
            routing_='r',
        )
        if not records:
            raise EdgeNotFoundError(uuid)
        return self.edge_from_row(records[0])

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[SimpleEdge]:
        if not uuids:
            return []
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM {self.table_name}
            WHERE uuid = ANY(%(uuids)s)
            ORDER BY uuid
            """,
            params={'uuids': uuids},
            routing_='r',
        )
        return [self.edge_from_row(row) for row in records]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[SimpleEdge]:
        limit_clause = 'LIMIT %(limit)s' if limit is not None else ''
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM {self.table_name}
            WHERE group_id = ANY(%(group_ids)s)
              AND (%(uuid_cursor)s::text IS NULL OR uuid < %(uuid_cursor)s)
            ORDER BY uuid DESC
            {limit_clause}
            """,
            params={'group_ids': group_ids, 'uuid_cursor': uuid_cursor, 'limit': limit},
            routing_='r',
        )
        return [self.edge_from_row(row) for row in records]

    async def _save_projection(
        self,
        executor: QueryExecutor,
        tx: Transaction | None,
        edge: SimpleEdge,
    ) -> None:
        await self._delete_projection(executor, tx, edge.uuid)
        await run_age_cypher(
            executor,
            tx,
            edge_projection_cypher(
                self.edge_type,
                self.source_label,
                self.target_label,
                edge.uuid,
                edge.group_id,
                edge.source_node_uuid,
                edge.target_node_uuid,
            ),
        )

    async def _delete_projection(
        self,
        executor: QueryExecutor,
        tx: Transaction | None,
        uuid: str,
    ) -> None:
        await run_age_cypher(
            executor,
            tx,
            edge_delete_projection_cypher(self.edge_type, uuid),
        )
