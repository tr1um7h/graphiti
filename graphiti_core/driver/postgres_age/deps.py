from __future__ import annotations

from typing import Any, NamedTuple


class PostgresAgeDependencies(NamedTuple):
    register_vector_async: Any
    AsyncConnection: Any
    AsyncCursor: Any
    AsyncConnectionPool: Any
    Jsonb: Any
    dict_row: Any
    sql: Any


def import_postgres_age_dependencies() -> PostgresAgeDependencies:
    try:
        from pgvector.psycopg import register_vector_async
        from psycopg import AsyncConnection, AsyncCursor, sql
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from psycopg_pool import AsyncConnectionPool
    except ImportError as exc:
        raise ImportError(
            'PostgresAgeDriver requires graphiti-core[postgres-age]. '
            'Install it with `pip install graphiti-core[postgres-age]` '
            'or `uv sync --extra postgres-age`.'
        ) from exc

    return PostgresAgeDependencies(
        register_vector_async,
        AsyncConnection,
        AsyncCursor,
        AsyncConnectionPool,
        Jsonb,
        dict_row,
        sql,
    )
