from __future__ import annotations

from datetime import datetime

from graphiti_core.driver.operations.episode_node_ops import EpisodeNodeOperations
from graphiti_core.driver.postgres_age.operations._helpers import (
    delete_node_projection,
    fetch_records,
    jsonb,
    operation_transaction,
    run_statement,
    source_value,
)
from graphiti_core.driver.postgres_age.records import episodic_node_from_row
from graphiti_core.driver.postgres_age.serialization import episodic_node_to_row
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import EpisodicNode


class PostgresAgeEpisodeNodeOperations(EpisodeNodeOperations):
    async def save(
        self,
        executor: QueryExecutor,
        node: EpisodicNode,
        tx: Transaction | None = None,
    ) -> None:
        row = episodic_node_to_row(node)
        row['episode_metadata'] = jsonb(executor, row['episode_metadata'])
        await run_statement(
            executor,
            tx,
            """
            INSERT INTO episodic_nodes (
                uuid, group_id, name, source, source_description, content, valid_at,
                entity_edges, episode_metadata, created_at
            )
            VALUES (
                %(uuid)s, %(group_id)s, %(name)s, %(source)s, %(source_description)s,
                %(content)s, %(valid_at)s, %(entity_edges)s, %(episode_metadata)s,
                %(created_at)s
            )
            ON CONFLICT (uuid) DO UPDATE SET
                group_id = EXCLUDED.group_id,
                name = EXCLUDED.name,
                source = EXCLUDED.source,
                source_description = EXCLUDED.source_description,
                content = EXCLUDED.content,
                valid_at = EXCLUDED.valid_at,
                entity_edges = EXCLUDED.entity_edges,
                episode_metadata = EXCLUDED.episode_metadata,
                created_at = EXCLUDED.created_at
            """,
            row,
        )

    async def save_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[EpisodicNode],
        tx: Transaction | None = None,
        batch_size: int = 100,
    ) -> None:
        async with operation_transaction(executor, tx) as bulk_tx:
            for node in nodes:
                await self.save(executor, node, bulk_tx)

    async def delete(
        self,
        executor: QueryExecutor,
        node: EpisodicNode,
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
                'SELECT uuid FROM episodic_nodes WHERE group_id = %(group_id)s',
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
        await delete_node_projection(executor, tx, 'Episodic', uuids)
        await run_statement(
            executor,
            tx,
            'DELETE FROM episodic_nodes WHERE uuid = ANY(%(uuids)s)',
            {'uuids': uuids},
        )

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EpisodicNode:
        records, _, _ = await executor.execute_query(
            'SELECT * FROM episodic_nodes WHERE uuid = %(uuid)s',
            params={'uuid': uuid},
            routing_='r',
        )
        if not records:
            raise NodeNotFoundError(uuid)
        return episodic_node_from_row(records[0])

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EpisodicNode]:
        if not uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            SELECT *
            FROM episodic_nodes
            WHERE uuid = ANY(%(uuids)s)
            ORDER BY uuid
            """,
            params={'uuids': uuids},
            routing_='r',
        )
        return [episodic_node_from_row(row) for row in records]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EpisodicNode]:
        limit_clause = 'LIMIT %(limit)s' if limit is not None else ''
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM episodic_nodes
            WHERE group_id = ANY(%(group_ids)s)
              AND (%(uuid_cursor)s::text IS NULL OR uuid < %(uuid_cursor)s)
            ORDER BY uuid DESC
            {limit_clause}
            """,
            params={'group_ids': group_ids, 'uuid_cursor': uuid_cursor, 'limit': limit},
            routing_='r',
        )
        return [episodic_node_from_row(row) for row in records]

    async def get_by_entity_node_uuid(
        self,
        executor: QueryExecutor,
        entity_node_uuid: str,
    ) -> list[EpisodicNode]:
        records, _, _ = await executor.execute_query(
            """
            SELECT ep.*
            FROM episodic_nodes ep
            JOIN episodic_edges ee ON ee.source_node_uuid = ep.uuid
            WHERE ee.target_node_uuid = %(entity_node_uuid)s
            ORDER BY ep.valid_at ASC, ep.created_at ASC
            """,
            params={'entity_node_uuid': entity_node_uuid},
            routing_='r',
        )
        return [episodic_node_from_row(row) for row in records]

    async def retrieve_episodes(
        self,
        executor: QueryExecutor,
        reference_time: datetime,
        last_n: int = 3,
        group_ids: list[str] | None = None,
        source: str | None = None,
        saga: str | None = None,
    ) -> list[EpisodicNode]:
        group_filter = 'AND ep.group_id = ANY(%(group_ids)s)' if group_ids else ''
        normalized_source = source_value(source)
        source_filter = 'AND ep.source = %(source)s' if normalized_source is not None else ''
        saga_join = ''
        saga_filter = ''
        if saga is not None:
            saga_join = 'JOIN has_episode_edges he ON he.target_node_uuid = ep.uuid JOIN saga_nodes s ON s.uuid = he.source_node_uuid'
            saga_filter = 'AND s.name = %(saga)s'

        records, _, _ = await executor.execute_query(
            f"""
            SELECT ep.*
            FROM episodic_nodes ep
            {saga_join}
            WHERE ep.valid_at <= %(reference_time)s
            {group_filter}
            {source_filter}
            {saga_filter}
            ORDER BY ep.valid_at DESC, ep.created_at DESC
            LIMIT %(last_n)s
            """,
            params={
                'reference_time': reference_time,
                'group_ids': group_ids,
                'source': normalized_source,
                'saga': saga,
                'last_n': last_n,
            },
            routing_='r',
        )
        return [episodic_node_from_row(row) for row in reversed(records)]
