from __future__ import annotations

from typing import Any

from graphiti_core.driver.operations.entity_node_ops import EntityNodeOperations
from graphiti_core.driver.postgres_age.operations._helpers import (
    delete_node_projection,
    fetch_records,
    jsonb,
    operation_transaction,
    run_statement,
)
from graphiti_core.driver.postgres_age.records import entity_node_from_row
from graphiti_core.driver.postgres_age.serialization import entity_node_to_row
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import EntityNode


class PostgresAgeEntityNodeOperations(EntityNodeOperations):
    async def save(
        self,
        executor: QueryExecutor,
        node: EntityNode,
        tx: Transaction | None = None,
    ) -> None:
        row = entity_node_to_row(node)
        row['attributes'] = jsonb(executor, row['attributes'])
        await run_statement(
            executor,
            tx,
            """
            INSERT INTO entity_nodes (
                uuid, group_id, name, summary, labels, attributes, name_embedding, created_at
            )
            VALUES (
                %(uuid)s, %(group_id)s, %(name)s, %(summary)s, %(labels)s,
                %(attributes)s, %(name_embedding)s, %(created_at)s
            )
            ON CONFLICT (uuid) DO UPDATE SET
                group_id = EXCLUDED.group_id,
                name = EXCLUDED.name,
                summary = EXCLUDED.summary,
                labels = EXCLUDED.labels,
                attributes = EXCLUDED.attributes,
                name_embedding = EXCLUDED.name_embedding,
                created_at = EXCLUDED.created_at
            """,
            row,
        )

    async def save_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[EntityNode],
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        async with operation_transaction(executor, tx) as bulk_tx:
            for node in nodes:
                await self.save(executor, node, bulk_tx)

    async def delete(
        self,
        executor: QueryExecutor,
        node: EntityNode,
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
                'SELECT uuid FROM entity_nodes WHERE group_id = %(group_id)s',
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
        await delete_node_projection(executor, tx, 'Entity', uuids)
        await run_statement(
            executor,
            tx,
            'DELETE FROM community_edges WHERE target_node_uuid = ANY(%(uuids)s)',
            {'uuids': uuids},
        )
        await run_statement(
            executor,
            tx,
            'DELETE FROM entity_nodes WHERE uuid = ANY(%(uuids)s)',
            {'uuids': uuids},
        )

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EntityNode:
        records, _, _ = await executor.execute_query(
            'SELECT * FROM entity_nodes WHERE uuid = %(uuid)s',
            params={'uuid': uuid},
            routing_='r',
        )
        if not records:
            raise NodeNotFoundError(uuid)
        return entity_node_from_row(records[0])

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EntityNode]:
        if not uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            SELECT *
            FROM entity_nodes
            WHERE uuid = ANY(%(uuids)s)
            ORDER BY uuid
            """,
            params={'uuids': uuids},
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EntityNode]:
        params: dict[str, Any] = {'group_ids': group_ids, 'uuid_cursor': uuid_cursor, 'limit': limit}
        limit_clause = 'LIMIT %(limit)s' if limit is not None else ''
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM entity_nodes
            WHERE group_id = ANY(%(group_ids)s)
              AND (%(uuid_cursor)s::text IS NULL OR uuid < %(uuid_cursor)s)
            ORDER BY uuid DESC
            {limit_clause}
            """,
            params=params,
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def load_embeddings(
        self,
        executor: QueryExecutor,
        node: EntityNode,
    ) -> None:
        records, _, _ = await executor.execute_query(
            'SELECT name_embedding FROM entity_nodes WHERE uuid = %(uuid)s',
            params={'uuid': node.uuid},
            routing_='r',
        )
        if not records:
            raise NodeNotFoundError(node.uuid)
        node.name_embedding = entity_node_from_row({**entity_node_to_row(node), **records[0]}).name_embedding

    async def load_embeddings_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[EntityNode],
        batch_size: int = 100,
    ) -> None:
        uuids = [node.uuid for node in nodes]
        if not uuids:
            return
        records, _, _ = await executor.execute_query(
            'SELECT uuid, name_embedding FROM entity_nodes WHERE uuid = ANY(%(uuids)s)',
            params={'uuids': uuids},
            routing_='r',
        )
        embeddings = {row['uuid']: row['name_embedding'] for row in records}
        for node in nodes:
            if node.uuid in embeddings:
                node.name_embedding = entity_node_from_row(
                    {**entity_node_to_row(node), 'name_embedding': embeddings[node.uuid]}
                ).name_embedding
