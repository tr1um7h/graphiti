from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession, GraphProvider
from graphiti_core.driver.operations.community_edge_ops import CommunityEdgeOperations
from graphiti_core.driver.operations.community_node_ops import CommunityNodeOperations
from graphiti_core.driver.operations.entity_edge_ops import EntityEdgeOperations
from graphiti_core.driver.operations.entity_node_ops import EntityNodeOperations
from graphiti_core.driver.operations.episode_node_ops import EpisodeNodeOperations
from graphiti_core.driver.operations.episodic_edge_ops import EpisodicEdgeOperations
from graphiti_core.driver.operations.graph_ops import GraphMaintenanceOperations
from graphiti_core.driver.operations.has_episode_edge_ops import HasEpisodeEdgeOperations
from graphiti_core.driver.operations.next_episode_edge_ops import NextEpisodeEdgeOperations
from graphiti_core.driver.operations.search_ops import SearchOperations
from graphiti_core.driver.postgres_age.deps import import_postgres_age_dependencies
from graphiti_core.driver.postgres_age.interfaces import (
    PostgresAgeGraphOperationsInterface,
    PostgresAgeSearchInterface,
)
from graphiti_core.driver.postgres_age.operations.community_edge_ops import (
    PostgresAgeCommunityEdgeOperations,
)
from graphiti_core.driver.postgres_age.operations.community_node_ops import (
    PostgresAgeCommunityNodeOperations,
)
from graphiti_core.driver.postgres_age.operations.entity_edge_ops import (
    PostgresAgeEntityEdgeOperations,
)
from graphiti_core.driver.postgres_age.operations.entity_node_ops import (
    PostgresAgeEntityNodeOperations,
)
from graphiti_core.driver.postgres_age.operations.episode_node_ops import (
    PostgresAgeEpisodeNodeOperations,
)
from graphiti_core.driver.postgres_age.operations.episodic_edge_ops import (
    PostgresAgeEpisodicEdgeOperations,
)
from graphiti_core.driver.postgres_age.operations.graph_ops import (
    PostgresAgeGraphMaintenanceOperations,
)
from graphiti_core.driver.postgres_age.operations.has_episode_edge_ops import (
    PostgresAgeHasEpisodeEdgeOperations,
)
from graphiti_core.driver.postgres_age.operations.next_episode_edge_ops import (
    PostgresAgeNextEpisodeEdgeOperations,
)
from graphiti_core.driver.postgres_age.operations.saga_node_ops import (
    PostgresAgeSagaNodeOperations,
)
from graphiti_core.driver.postgres_age.operations.search_ops import PostgresAgeSearchOperations
from graphiti_core.driver.postgres_age.projection import cypher_sql, decode_agtype_value
from graphiti_core.driver.postgres_age.schema import (
    drop_canonical_indexes,
    rebuild_schema,
)
from graphiti_core.driver.query_executor import Transaction

PostgresAgeResult = tuple[list[dict[str, Any]], None, list[str]]


class PostgresAgeDriver(GraphDriver):
    provider = GraphProvider.POSTGRES_AGE
    default_group_id = ''

    def __init__(
        self,
        dsn: str,
        graph_name: str = 'graphiti',
        schema: str = 'public',
        embedding_dimension: int = 1536,
        pool_min_size: int = 1,
        pool_max_size: int = 10,
    ) -> None:
        self.dsn = dsn
        self.graph_name = _effective_graph_name(schema, graph_name)
        self.schema = schema
        self.embedding_dimension = embedding_dimension
        self._database = graph_name
        self._deps = import_postgres_age_dependencies()
        self._pool = self._deps.AsyncConnectionPool(
            conninfo=dsn,
            min_size=pool_min_size,
            max_size=pool_max_size,
            open=False,
            kwargs={'row_factory': self._deps.dict_row},
        )
        self._pool_opened = False
        self._closed = False
        self._entity_node_ops = PostgresAgeEntityNodeOperations()
        self._episode_node_ops = PostgresAgeEpisodeNodeOperations()
        self._community_node_ops = PostgresAgeCommunityNodeOperations()
        self._saga_node_ops = PostgresAgeSagaNodeOperations()
        self._entity_edge_ops = PostgresAgeEntityEdgeOperations()
        self._episodic_edge_ops = PostgresAgeEpisodicEdgeOperations()
        self._community_edge_ops = PostgresAgeCommunityEdgeOperations()
        self._has_episode_edge_ops = PostgresAgeHasEpisodeEdgeOperations()
        self._next_episode_edge_ops = PostgresAgeNextEpisodeEdgeOperations()
        self._graph_ops = PostgresAgeGraphMaintenanceOperations()
        self._search_ops = PostgresAgeSearchOperations()
        self.graph_operations_interface = PostgresAgeGraphOperationsInterface()
        self.search_interface = PostgresAgeSearchInterface()

    async def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError('PostgresAgeDriver is closed')

        if self._pool_opened:
            return

        await self._pool.open()
        self._pool_opened = True

    async def _setup_connection(self, conn: Any) -> None:
        await self._deps.register_vector_async(conn)
        await conn.execute("LOAD 'age'")
        await conn.execute(
            self._deps.sql.SQL('SET search_path = {}, ag_catalog, "$user", public').format(
                self._deps.sql.Identifier(self.schema)
            )
        )

    async def execute_query(self, cypher_query_: Any, **kwargs: Any) -> PostgresAgeResult:
        """Execute SQL directly; later AGE Cypher helpers will wrap graph queries."""
        await self._ensure_open()
        params = _query_params(kwargs.pop('params', None), kwargs)

        async with self._pool.connection() as conn:
            try:
                await self._setup_connection(conn)
                result = await _run_sql(conn, cypher_query_, params)
                await conn.commit()
                return result
            except Exception:
                await conn.rollback()
                raise

    async def execute_age_cypher(
        self,
        cypher_query: str,
        columns: str = 'value agtype',
    ) -> list[dict[str, Any]]:
        query = cypher_sql(self._deps, self.graph_name, cypher_query, columns)
        records, _, _ = await self.execute_query(query, params=None)
        return [
            {key: decode_agtype_value(value) for key, value in record.items()}
            for record in records
        ]

    def session(self, database: str | None = None) -> GraphDriverSession:
        if database is not None:
            raise NotImplementedError('PostgresAgeDriver does not support database override yet')

        return PostgresAgeDriverSession(self)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        await self._ensure_open()
        async with self._pool.connection() as conn:
            await self._setup_connection(conn)
            await conn.commit()
            async with conn.transaction():
                yield PostgresAgeTransaction(conn)

    async def close(self) -> None:
        if self._closed:
            return

        if not self._pool_opened:
            self._closed = True
            return

        await self._pool.close()
        self._closed = True

    async def delete_all_indexes(self) -> None:
        await self._ensure_open()
        async with self._pool.connection() as conn:
            try:
                await drop_canonical_indexes(conn, self._deps, self.schema)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def build_indices_and_constraints(self, delete_existing: bool = False) -> None:
        await self._ensure_open()
        async with self._pool.connection() as conn:
            try:
                await rebuild_schema(
                    conn,
                    self._deps,
                    self.schema,
                    self.graph_name,
                    self.embedding_dimension,
                    delete_existing=delete_existing,
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    @property
    def entity_node_ops(self) -> EntityNodeOperations:
        return self._entity_node_ops

    @property
    def episode_node_ops(self) -> EpisodeNodeOperations:
        return self._episode_node_ops

    @property
    def community_node_ops(self) -> CommunityNodeOperations:
        return self._community_node_ops

    @property
    def saga_node_ops(self) -> PostgresAgeSagaNodeOperations:
        return self._saga_node_ops

    @property
    def entity_edge_ops(self) -> EntityEdgeOperations:
        return self._entity_edge_ops

    @property
    def episodic_edge_ops(self) -> EpisodicEdgeOperations:
        return self._episodic_edge_ops

    @property
    def community_edge_ops(self) -> CommunityEdgeOperations:
        return self._community_edge_ops

    @property
    def has_episode_edge_ops(self) -> HasEpisodeEdgeOperations:
        return self._has_episode_edge_ops

    @property
    def next_episode_edge_ops(self) -> NextEpisodeEdgeOperations:
        return self._next_episode_edge_ops

    @property
    def graph_ops(self) -> GraphMaintenanceOperations:
        return self._graph_ops

    @property
    def search_ops(self) -> SearchOperations:
        return self._search_ops


class PostgresAgeTransaction(Transaction):
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def run(
        self, query: Any, params: Sequence[Any] | dict[str, Any] | None = None, **kwargs: Any
    ) -> PostgresAgeResult:
        return await _run_sql(self._conn, query, _query_params(params, kwargs))


class PostgresAgeDriverSession(GraphDriverSession):
    provider = GraphProvider.POSTGRES_AGE

    def __init__(self, driver: PostgresAgeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> PostgresAgeDriverSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def run(
        self, query: str, params: Sequence[Any] | dict[str, Any] | None = None, **kwargs: Any
    ) -> PostgresAgeResult:
        if params is not None:
            kwargs['params'] = params
        return await self._driver.execute_query(query, **kwargs)

    async def execute_write(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        async with self._driver.transaction() as tx:
            result = func(tx, *args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

    async def close(self) -> None:
        pass


async def _run_sql(
    conn: Any, query: Any, params: Sequence[Any] | dict[str, Any] | None
) -> PostgresAgeResult:
    async with conn.cursor() as cursor:
        await cursor.execute(query, params)
        keys = _result_keys(cursor)
        if not keys:
            return [], None, []

        rows = await cursor.fetchall()
        return [dict(row) for row in rows], None, keys


def _result_keys(cursor: Any) -> list[str]:
    if cursor.description is None:
        return []

    return [column.name for column in cursor.description]


def _query_params(
    params: Sequence[Any] | dict[str, Any] | None, kwargs: dict[str, Any]
) -> Sequence[Any] | dict[str, Any] | None:
    kwargs.pop('database_', None)
    kwargs.pop('routing_', None)

    if params is not None:
        return params

    if not kwargs:
        return None

    return kwargs


def _effective_graph_name(schema: str, graph_name: str) -> str:
    if schema != 'public' and graph_name == 'graphiti':
        return f'{schema}_graphiti'
    return graph_name
