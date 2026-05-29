from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection, AsyncCursor, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from typing_extensions import LiteralString

_CYPHER_COLUMNS_RE = re.compile(
    r'\A\s*[A-Za-z_][A-Za-z0-9_]*\s+agtype(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s+agtype)*\s*\Z'
)
_MAX_BFS_DEPTH = 5


class PostgresAgeSpike:
    def __init__(self, dsn: str, graph_name: str = 'graphiti_spike') -> None:
        self.dsn = dsn
        self.graph_name = graph_name
        self.pool: AsyncConnectionPool | None = None

    async def open(self) -> None:
        if self.pool is not None:
            raise RuntimeError('PostgresAgeSpike is already open')
        self.pool = AsyncConnectionPool(self.dsn, open=False)
        await self.pool.open()

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection]:
        if self.pool is None:
            raise RuntimeError('PostgresAgeSpike.open() must be called before use')
        async with self.pool.connection() as conn:
            await self._setup_age_session(conn)
            yield conn

    async def bootstrap(self) -> None:
        if self.pool is None:
            raise RuntimeError('PostgresAgeSpike.open() must be called before use')

        async with self.pool.connection() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute('CREATE EXTENSION IF NOT EXISTS age')
                    await cur.execute('CREATE EXTENSION IF NOT EXISTS vector')
                    await cur.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

                    await cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS public.spike_entity_nodes (
                            uuid text PRIMARY KEY,
                            group_id text NOT NULL,
                            name text NOT NULL,
                            summary text NOT NULL,
                            labels text[] NOT NULL DEFAULT '{}',
                            attributes jsonb NOT NULL DEFAULT '{}',
                            name_embedding vector(3),
                            created_at timestamptz NOT NULL DEFAULT now(),
                            search_vector tsvector GENERATED ALWAYS AS (
                                setweight(to_tsvector('simple', name), 'A')
                                || setweight(to_tsvector('simple', summary), 'B')
                            ) STORED
                        )
                        """
                    )
                    await cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS public.spike_entity_edges (
                            uuid text PRIMARY KEY,
                            group_id text NOT NULL,
                            source_node_uuid text NOT NULL
                                REFERENCES public.spike_entity_nodes(uuid) ON DELETE CASCADE,
                            target_node_uuid text NOT NULL
                                REFERENCES public.spike_entity_nodes(uuid) ON DELETE CASCADE,
                            name text NOT NULL,
                            fact text NOT NULL,
                            fact_embedding vector(3),
                            created_at timestamptz NOT NULL DEFAULT now(),
                            search_vector tsvector GENERATED ALWAYS AS (
                                setweight(to_tsvector('simple', name), 'A')
                                || setweight(to_tsvector('simple', fact), 'B')
                            ) STORED
                        )
                        """
                    )
                    await cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS spike_entity_nodes_group_id_idx
                        ON public.spike_entity_nodes (group_id)
                        """
                    )
                    await cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS spike_entity_edges_group_id_idx
                        ON public.spike_entity_edges (group_id)
                        """
                    )
                    await cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS spike_entity_nodes_search_vector_idx
                        ON public.spike_entity_nodes USING gin (search_vector)
                        """
                    )
                    await cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS spike_entity_edges_search_vector_idx
                        ON public.spike_entity_edges USING gin (search_vector)
                        """
                    )
                    await cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS spike_entity_nodes_name_embedding_hnsw_idx
                        ON public.spike_entity_nodes USING hnsw (name_embedding vector_cosine_ops)
                        """
                    )
                    await cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS spike_entity_edges_fact_embedding_hnsw_idx
                        ON public.spike_entity_edges USING hnsw (fact_embedding vector_cosine_ops)
                        """
                    )

                    await cur.execute("LOAD 'age'")
                    await cur.execute('SET search_path = ag_catalog, "$user", public')
                    await cur.execute(
                        'SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s',
                        (self.graph_name,),
                    )
                    if await cur.fetchone() is None:
                        await cur.execute('SELECT create_graph(%s)', (self.graph_name,))
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def _setup_age_session(self, conn: AsyncConnection) -> None:
        await register_vector_async(conn)
        async with conn.cursor() as cur:
            await cur.execute("LOAD 'age'")
            await cur.execute('SET search_path = ag_catalog, "$user", public')

    async def execute_sql(
        self, query: LiteralString, params: dict[str, Any] | None = None
    ) -> list[dict]:
        async with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or {})
            if cur.description is None:
                return []
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def clear(self) -> None:
        async with self.connection() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute('DELETE FROM public.spike_entity_edges')
                    await cur.execute('DELETE FROM public.spike_entity_nodes')
                    await self._execute_trusted_cypher(cur, 'MATCH (n) DETACH DELETE n')
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def save_entity_node(
        self,
        uuid: str,
        group_id: str,
        name: str,
        summary: str,
        labels: Sequence[str],
        attributes: dict[str, Any],
        embedding: Sequence[float] | None,
    ) -> None:
        await self._save_entity_node_with_projection(
            uuid,
            group_id,
            name,
            summary,
            labels,
            attributes,
            embedding,
            self._merge_entity_projection,
        )

    async def save_entity_node_then_fail_projection(
        self,
        uuid: str,
        group_id: str,
        name: str,
        summary: str,
        labels: Sequence[str],
        attributes: dict[str, Any],
        embedding: Sequence[float] | None,
    ) -> None:
        async def fail_projection(
            cur: AsyncCursor[Any],
            _uuid: str,
            _group_id: str,
            _name: str,
            _labels: Sequence[str],
        ) -> None:
            try:
                await self._execute_trusted_cypher(cur, 'THIS IS NOT VALID CYPHER')
            except Exception as exc:
                raise RuntimeError('forced projection failure') from exc

        await self._save_entity_node_with_projection(
            uuid,
            group_id,
            name,
            summary,
            labels,
            attributes,
            embedding,
            fail_projection,
        )

    async def _save_entity_node_with_projection(
        self,
        uuid: str,
        group_id: str,
        name: str,
        summary: str,
        labels: Sequence[str],
        attributes: dict[str, Any],
        embedding: Sequence[float] | None,
        projection_writer: Callable[
            [AsyncCursor[Any], str, str, str, Sequence[str]], Awaitable[None]
        ],
    ) -> None:
        labels_list = list(labels)
        async with self.connection() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO public.spike_entity_nodes (
                            uuid,
                            group_id,
                            name,
                            summary,
                            labels,
                            attributes,
                            name_embedding
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (uuid) DO UPDATE SET
                            group_id = EXCLUDED.group_id,
                            name = EXCLUDED.name,
                            summary = EXCLUDED.summary,
                            labels = EXCLUDED.labels,
                            attributes = EXCLUDED.attributes,
                            name_embedding = EXCLUDED.name_embedding
                        """,
                        (
                            uuid,
                            group_id,
                            name,
                            summary,
                            labels_list,
                            Jsonb(attributes),
                            list(embedding) if embedding is not None else None,
                        ),
                    )
                    await projection_writer(cur, uuid, group_id, name, labels_list)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def get_entity_node(self, uuid: str) -> dict[str, Any]:
        async with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT uuid, group_id, name, summary, labels, attributes
                FROM public.spike_entity_nodes
                WHERE uuid = %s
                """,
                (uuid,),
            )
            row = await cur.fetchone()
            if row is None:
                raise KeyError(uuid)
            return dict(row)

    async def save_entity_edge(
        self,
        uuid: str,
        group_id: str,
        source_node_uuid: str,
        target_node_uuid: str,
        name: str,
        fact: str,
        embedding: Sequence[float] | None,
    ) -> None:
        async with self.connection() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO public.spike_entity_edges (
                            uuid,
                            group_id,
                            source_node_uuid,
                            target_node_uuid,
                            name,
                            fact,
                            fact_embedding
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (uuid) DO UPDATE SET
                            group_id = EXCLUDED.group_id,
                            source_node_uuid = EXCLUDED.source_node_uuid,
                            target_node_uuid = EXCLUDED.target_node_uuid,
                            name = EXCLUDED.name,
                            fact = EXCLUDED.fact,
                            fact_embedding = EXCLUDED.fact_embedding
                        """,
                        (
                            uuid,
                            group_id,
                            source_node_uuid,
                            target_node_uuid,
                            name,
                            fact,
                            list(embedding) if embedding is not None else None,
                        ),
                    )
                    await self._merge_edge_projection(
                        cur,
                        uuid,
                        group_id,
                        source_node_uuid,
                        target_node_uuid,
                        name,
                    )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def get_entity_edge(self, uuid: str) -> dict[str, Any]:
        async with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT uuid, group_id, source_node_uuid, target_node_uuid, name, fact
                FROM public.spike_entity_edges
                WHERE uuid = %s
                """,
                (uuid,),
            )
            row = await cur.fetchone()
            if row is None:
                raise KeyError(uuid)
            return dict(row)

    async def vector_search_entity_uuids(
        self, embedding: Sequence[float], limit: int
    ) -> list[str]:
        self._validate_search_limit(limit)

        async with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT uuid
                FROM public.spike_entity_nodes
                WHERE name_embedding IS NOT NULL
                ORDER BY name_embedding <=> %(embedding)s::vector
                LIMIT %(limit)s
                """,
                {'embedding': list(embedding), 'limit': limit},
            )
            rows = await cur.fetchall()
            return [str(row['uuid']) for row in rows]

    async def fulltext_search_entity_uuids(self, query: str, limit: int) -> list[str]:
        self._validate_search_limit(limit)

        async with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT uuid
                FROM public.spike_entity_nodes
                WHERE search_vector @@ websearch_to_tsquery('simple', %(query)s)
                ORDER BY ts_rank(search_vector, websearch_to_tsquery('simple', %(query)s)) DESC,
                    uuid
                LIMIT %(limit)s
                """,
                {'query': query, 'limit': limit},
            )
            rows = await cur.fetchall()
            return [str(row['uuid']) for row in rows]

    async def bfs_entity_uuids(self, origin_uuid: str, max_depth: int = 1) -> list[str]:
        if type(max_depth) is not int or not 1 <= max_depth <= _MAX_BFS_DEPTH:
            raise ValueError(f'max_depth must be between 1 and {_MAX_BFS_DEPTH}')

        cypher_query = f"""
        MATCH (:Entity {{uuid: {json.dumps(origin_uuid)}}})-[:RELATES_TO*1..{max_depth}]->(n:Entity)
        RETURN DISTINCT n.uuid
        """
        rows = await self.execute_cypher(cypher_query, 'uuid agtype')
        return sorted(str(self.decode_agtype_scalar(row['uuid'])) for row in rows)

    @staticmethod
    def _validate_search_limit(limit: int) -> None:
        if type(limit) is not int or limit < 1:
            raise ValueError('limit must be a positive integer')

    async def execute_cypher(self, cypher_query: str, columns: str) -> list[dict]:
        """Execute trusted spike Cypher with conservative SQL breakout checks.

        AGE requires the result column definition to be structural SQL, and this spike helper
        embeds the Cypher body in a dollar-quoted SQL literal. Callers must pass trusted spike
        Cypher only; this method rejects the obvious dollar-quote breakout and limits columns
        to comma-separated ``<identifier> agtype`` definitions.
        """
        if '$$' in cypher_query:
            raise ValueError('cypher_query cannot contain the dollar-quote delimiter $$')
        if _CYPHER_COLUMNS_RE.fullmatch(columns) is None:
            raise ValueError('columns must be comma-separated <identifier> agtype definitions')

        async with self.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await self._execute_trusted_cypher(cur, cypher_query, columns)
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def _merge_entity_projection(
        self,
        cur: AsyncCursor[Any],
        uuid: str,
        group_id: str,
        name: str,
        labels: Sequence[str],
    ) -> None:
        cypher_query = f"""
        MERGE (n:Entity {{uuid: {json.dumps(uuid)}}})
        SET n.group_id = {json.dumps(group_id)},
            n.name = {json.dumps(name)},
            n.node_kind = 'Entity',
            n.labels = {json.dumps(list(labels))}
        """
        await self._execute_trusted_cypher(cur, cypher_query)

    async def _merge_edge_projection(
        self,
        cur: AsyncCursor[Any],
        uuid: str,
        group_id: str,
        source_node_uuid: str,
        target_node_uuid: str,
        name: str,
    ) -> None:
        await self._execute_trusted_cypher(
            cur,
            f"""
            MATCH ()-[old_edge:RELATES_TO {{uuid: {json.dumps(uuid)}}}]->()
            DELETE old_edge
            """,
        )
        cypher_query = f"""
        MATCH (source_node:Entity {{uuid: {json.dumps(source_node_uuid)}}})
        MATCH (target_node:Entity {{uuid: {json.dumps(target_node_uuid)}}})
        MERGE (source_node)-[e:RELATES_TO {{uuid: {json.dumps(uuid)}}}]->(target_node)
        SET e.group_id = {json.dumps(group_id)},
            e.edge_kind = 'RELATES_TO',
            e.name = {json.dumps(name)}
        """
        await self._execute_trusted_cypher(cur, cypher_query)

    async def _execute_trusted_cypher(
        self, cur: AsyncCursor[Any], cypher_query: str, columns: str = 'value agtype'
    ) -> None:
        # psycopg's SQL composer is typed for literal strings; these runtime strings are
        # accepted only after callers build trusted spike Cypher internally or validate inputs.
        cypher_sql = cast(LiteralString, cypher_query)
        columns_sql = cast(LiteralString, columns)
        query = sql.SQL('SELECT * FROM cypher({}, $$ {} $$) AS ({})').format(
            sql.Literal(self.graph_name),
            sql.SQL(cypher_sql),
            sql.SQL(columns_sql),
        )
        await cur.execute(query)

    @staticmethod
    def decode_agtype_scalar(value: Any) -> Any:
        text = str(value)
        if text.endswith('::numeric'):
            text = text.removesuffix('::numeric')
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text.strip('"')
