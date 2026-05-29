from __future__ import annotations

from datetime import datetime

from graphiti_core.driver.operations.saga_node_ops import SagaNodeOperations
from graphiti_core.driver.postgres_age.operations._helpers import (
    delete_node_projection,
    fetch_records,
    operation_transaction,
    run_statement,
)
from graphiti_core.driver.postgres_age.records import saga_node_from_row
from graphiti_core.driver.postgres_age.serialization import saga_node_to_row
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import SagaNode


class PostgresAgeSagaNodeOperations(SagaNodeOperations):
    async def save(
        self,
        executor: QueryExecutor,
        node: SagaNode,
        tx: Transaction | None = None,
    ) -> None:
        await run_statement(
            executor,
            tx,
            """
            INSERT INTO saga_nodes (
                uuid, group_id, name, summary, first_episode_uuid, last_episode_uuid,
                last_summarized_at, last_summarized_episode_valid_at, created_at
            )
            VALUES (
                %(uuid)s, %(group_id)s, %(name)s, %(summary)s,
                %(first_episode_uuid)s, %(last_episode_uuid)s,
                %(last_summarized_at)s, %(last_summarized_episode_valid_at)s,
                %(created_at)s
            )
            ON CONFLICT (uuid) DO UPDATE SET
                group_id = EXCLUDED.group_id,
                name = EXCLUDED.name,
                summary = EXCLUDED.summary,
                first_episode_uuid = EXCLUDED.first_episode_uuid,
                last_episode_uuid = EXCLUDED.last_episode_uuid,
                last_summarized_at = EXCLUDED.last_summarized_at,
                last_summarized_episode_valid_at = EXCLUDED.last_summarized_episode_valid_at,
                created_at = EXCLUDED.created_at
            """,
            saga_node_to_row(node),
        )

    async def save_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[SagaNode],
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        async with operation_transaction(executor, tx) as bulk_tx:
            for node in nodes:
                await self.save(executor, node, bulk_tx)

    async def delete(
        self,
        executor: QueryExecutor,
        node: SagaNode,
        tx: Transaction | None = None,
    ) -> None:
        await self.delete_by_uuids(executor, [node.uuid], tx)

    async def delete_by_group_id(
        self,
        executor: QueryExecutor,
        group_id: str,
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        async with operation_transaction(executor, tx) as op_tx:
            records = await fetch_records(
                executor,
                op_tx,
                'SELECT uuid FROM saga_nodes WHERE group_id = %(group_id)s',
                {'group_id': group_id},
            )
            await self._delete_by_uuids_in_transaction(
                executor, [row['uuid'] for row in records], op_tx
            )

    async def delete_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        if not uuids:
            return
        async with operation_transaction(executor, tx) as op_tx:
            await self._delete_by_uuids_in_transaction(executor, uuids, op_tx)

    async def _delete_by_uuids_in_transaction(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None,
    ) -> None:
        if not uuids:
            return
        await delete_node_projection(executor, tx, 'Saga', uuids)
        await run_statement(
            executor,
            tx,
            'DELETE FROM saga_nodes WHERE uuid = ANY(%(uuids)s)',
            {'uuids': uuids},
        )

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> SagaNode:
        records, _, _ = await executor.execute_query(
            'SELECT * FROM saga_nodes WHERE uuid = %(uuid)s',
            params={'uuid': uuid},
            routing_='r',
        )
        if not records:
            raise NodeNotFoundError(uuid)
        return saga_node_from_row(records[0])

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[SagaNode]:
        if not uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            SELECT *
            FROM saga_nodes
            WHERE uuid = ANY(%(uuids)s)
            ORDER BY uuid
            """,
            params={'uuids': uuids},
            routing_='r',
        )
        return [saga_node_from_row(row) for row in records]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[SagaNode]:
        limit_clause = 'LIMIT %(limit)s' if limit is not None else ''
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM saga_nodes
            WHERE group_id = ANY(%(group_ids)s)
              AND (%(uuid_cursor)s::text IS NULL OR uuid < %(uuid_cursor)s)
            ORDER BY uuid DESC
            {limit_clause}
            """,
            params={'group_ids': group_ids, 'uuid_cursor': uuid_cursor, 'limit': limit},
            routing_='r',
        )
        return [saga_node_from_row(row) for row in records]

    async def get_previous_episode_uuid(
        self,
        executor: QueryExecutor,
        saga_uuid: str,
        current_episode_uuid: str,
    ) -> str | None:
        records, _, _ = await executor.execute_query(
            """
            SELECT ep.uuid
            FROM has_episode_edges he
            JOIN episodic_nodes ep ON ep.uuid = he.target_node_uuid
            WHERE he.source_node_uuid = %(saga_uuid)s
              AND ep.uuid <> %(current_episode_uuid)s
            ORDER BY ep.valid_at DESC, ep.created_at DESC
            LIMIT 1
            """,
            params={'saga_uuid': saga_uuid, 'current_episode_uuid': current_episode_uuid},
            routing_='r',
        )
        if not records:
            return None
        return records[0]['uuid']

    async def get_episode_contents(
        self,
        executor: QueryExecutor,
        saga_uuid: str,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[tuple[str, datetime | None]]:
        records, _, _ = await executor.execute_query(
            """
            SELECT content, valid_at
            FROM (
                SELECT ep.content, ep.valid_at, ep.created_at
                FROM has_episode_edges he
                JOIN episodic_nodes ep ON ep.uuid = he.target_node_uuid
                WHERE he.source_node_uuid = %(saga_uuid)s
                  AND (%(since)s::timestamptz IS NULL OR ep.created_at > %(since)s)
                ORDER BY ep.valid_at DESC, ep.created_at DESC
                LIMIT %(limit)s
            ) recent
            ORDER BY valid_at ASC, created_at ASC
            """,
            params={'saga_uuid': saga_uuid, 'since': since, 'limit': limit},
            routing_='r',
        )
        return [(row['content'], row['valid_at']) for row in records]
