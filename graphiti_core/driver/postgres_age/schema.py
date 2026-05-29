from __future__ import annotations

from typing import Any

from graphiti_core.driver.postgres_age.types import (
    B_TREE_INDEX_SPECS,
    CANONICAL_TABLES,
    GIN_INDEX_SPECS,
    HNSW_INDEX_SPECS,
    INDEX_NAMES,
    VECTOR_COLUMNS,
)


async def rebuild_schema(
    conn: Any,
    deps: Any,
    schema: str,
    graph_name: str,
    embedding_dimension: int,
    delete_existing: bool = False,
) -> None:
    if embedding_dimension <= 0:
        raise ValueError('embedding_dimension must be positive')

    await _create_extensions(conn)
    await _create_schema(conn, deps, schema)
    await _setup_age(conn, deps, schema)

    if delete_existing:
        await drop_age_graph(conn, graph_name)
        await drop_canonical_tables(conn, deps, schema)

    await create_canonical_tables(conn, deps, schema, embedding_dimension)
    await validate_vector_dimensions(conn, schema, embedding_dimension)
    await create_canonical_indexes(conn, deps, schema)
    await create_age_graph(conn, graph_name)


async def _create_extensions(conn: Any) -> None:
    await conn.execute('CREATE EXTENSION IF NOT EXISTS age')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')


async def _create_schema(conn: Any, deps: Any, schema: str) -> None:
    await conn.execute(
        deps.sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(deps.sql.Identifier(schema))
    )


async def _setup_age(conn: Any, deps: Any, schema: str) -> None:
    await deps.register_vector_async(conn)
    await conn.execute("LOAD 'age'")
    await conn.execute(
        deps.sql.SQL('SET search_path = {}, ag_catalog, "$user", public').format(
            deps.sql.Identifier(schema)
        )
    )


async def drop_age_graph(conn: Any, graph_name: str) -> None:
    result = await conn.execute('SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s', (graph_name,))
    if await result.fetchone() is not None:
        await conn.execute('SELECT drop_graph(%s, true)', (graph_name,))


async def create_age_graph(conn: Any, graph_name: str) -> None:
    result = await conn.execute('SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s', (graph_name,))
    if await result.fetchone() is None:
        await conn.execute('SELECT create_graph(%s)', (graph_name,))


async def drop_canonical_tables(conn: Any, deps: Any, schema: str) -> None:
    for table in CANONICAL_TABLES:
        await conn.execute(
            deps.sql.SQL('DROP TABLE IF EXISTS {}.{} CASCADE').format(
                deps.sql.Identifier(schema),
                deps.sql.Identifier(table),
            )
        )


async def drop_canonical_indexes(conn: Any, deps: Any, schema: str) -> None:
    result = await conn.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s
          AND indexname = ANY(%s)
        """,
        (schema, list(INDEX_NAMES)),
    )
    rows = await result.fetchall()
    for row in rows:
        await conn.execute(
            deps.sql.SQL('DROP INDEX IF EXISTS {}.{}').format(
                deps.sql.Identifier(schema),
                deps.sql.Identifier(row['indexname']),
            )
        )


async def create_canonical_tables(
    conn: Any, deps: Any, schema: str, embedding_dimension: int
) -> None:
    dim = deps.sql.SQL(str(embedding_dimension))
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.entity_nodes (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                name text NOT NULL,
                summary text NOT NULL DEFAULT '',
                labels text[] NOT NULL DEFAULT '{{}}',
                attributes jsonb NOT NULL DEFAULT '{{}}',
                name_embedding vector({}),
                created_at timestamptz NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(summary, '')), 'B')
                ) STORED
            )
            """
        ).format(deps.sql.Identifier(schema), dim)
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.episodic_nodes (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                name text NOT NULL,
                source text NOT NULL,
                source_description text NOT NULL,
                content text NOT NULL,
                valid_at timestamptz NOT NULL,
                entity_edges text[] NOT NULL DEFAULT '{{}}',
                episode_metadata jsonb,
                created_at timestamptz NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(content, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(source_description, '')), 'C')
                ) STORED
            )
            """
        ).format(deps.sql.Identifier(schema))
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.community_nodes (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                name text NOT NULL,
                summary text NOT NULL DEFAULT '',
                name_embedding vector({}),
                created_at timestamptz NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(summary, '')), 'B')
                ) STORED
            )
            """
        ).format(deps.sql.Identifier(schema), dim)
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.saga_nodes (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                name text NOT NULL,
                summary text NOT NULL DEFAULT '',
                first_episode_uuid text REFERENCES {}.episodic_nodes(uuid) ON DELETE SET NULL,
                last_episode_uuid text REFERENCES {}.episodic_nodes(uuid) ON DELETE SET NULL,
                last_summarized_at timestamptz,
                last_summarized_episode_valid_at timestamptz,
                created_at timestamptz NOT NULL
            )
            """
        ).format(
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
        )
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.entity_edges (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                source_node_uuid text NOT NULL
                    REFERENCES {}.entity_nodes(uuid) ON DELETE CASCADE,
                target_node_uuid text NOT NULL
                    REFERENCES {}.entity_nodes(uuid) ON DELETE CASCADE,
                name text NOT NULL,
                fact text NOT NULL,
                fact_embedding vector({}),
                episodes text[] NOT NULL DEFAULT '{{}}',
                expired_at timestamptz,
                valid_at timestamptz,
                invalid_at timestamptz,
                reference_time timestamptz,
                attributes jsonb NOT NULL DEFAULT '{{}}',
                created_at timestamptz NOT NULL,
                search_vector tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(fact, '')), 'B')
                ) STORED
            )
            """
        ).format(
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
            dim,
        )
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.episodic_edges (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                source_node_uuid text NOT NULL
                    REFERENCES {}.episodic_nodes(uuid) ON DELETE CASCADE,
                target_node_uuid text NOT NULL
                    REFERENCES {}.entity_nodes(uuid) ON DELETE CASCADE,
                created_at timestamptz NOT NULL
            )
            """
        ).format(
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
        )
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.community_edges (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                source_node_uuid text NOT NULL
                    REFERENCES {}.community_nodes(uuid) ON DELETE CASCADE,
                target_node_uuid text NOT NULL,
                created_at timestamptz NOT NULL
            )
            """
        ).format(
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
        )
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.has_episode_edges (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                source_node_uuid text NOT NULL
                    REFERENCES {}.saga_nodes(uuid) ON DELETE CASCADE,
                target_node_uuid text NOT NULL
                    REFERENCES {}.episodic_nodes(uuid) ON DELETE CASCADE,
                created_at timestamptz NOT NULL
            )
            """
        ).format(
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
        )
    )
    await conn.execute(
        deps.sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {}.next_episode_edges (
                uuid text PRIMARY KEY,
                group_id text NOT NULL,
                source_node_uuid text NOT NULL
                    REFERENCES {}.episodic_nodes(uuid) ON DELETE CASCADE,
                target_node_uuid text NOT NULL
                    REFERENCES {}.episodic_nodes(uuid) ON DELETE CASCADE,
                created_at timestamptz NOT NULL
            )
            """
        ).format(
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
            deps.sql.Identifier(schema),
        )
    )


async def validate_vector_dimensions(conn: Any, schema: str, embedding_dimension: int) -> None:
    for table_name, column_name in VECTOR_COLUMNS:
        result = await conn.execute(
            """
            SELECT a.atttypmod
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relname = %s
              AND a.attname = %s
            """,
            (schema, table_name, column_name),
        )
        row = await result.fetchone()
        if row is None:
            raise RuntimeError(f'Missing vector column {schema}.{table_name}.{column_name}')
        if row['atttypmod'] != embedding_dimension:
            raise ValueError(
                f'Existing {schema}.{table_name}.{column_name} dimension '
                f'{row["atttypmod"]} does not match configured embedding_dimension '
                f'{embedding_dimension}. Rebuild with delete_existing=True to replace the schema.'
            )


async def create_canonical_indexes(conn: Any, deps: Any, schema: str) -> None:
    for index_name, table_name, column_name in B_TREE_INDEX_SPECS:
        await conn.execute(
            deps.sql.SQL('CREATE INDEX IF NOT EXISTS {} ON {}.{} ({})').format(
                deps.sql.Identifier(index_name),
                deps.sql.Identifier(schema),
                deps.sql.Identifier(table_name),
                deps.sql.Identifier(column_name),
            )
        )

    for index_name, table_name in GIN_INDEX_SPECS:
        await conn.execute(
            deps.sql.SQL('CREATE INDEX IF NOT EXISTS {} ON {}.{} USING gin (search_vector)').format(
                deps.sql.Identifier(index_name),
                deps.sql.Identifier(schema),
                deps.sql.Identifier(table_name),
            )
        )

    for index_name, table_name, column_name in HNSW_INDEX_SPECS:
        await conn.execute(
            deps.sql.SQL(
                'CREATE INDEX IF NOT EXISTS {} ON {}.{} '
                'USING hnsw ({} vector_cosine_ops) WHERE {} IS NOT NULL'
            ).format(
                deps.sql.Identifier(index_name),
                deps.sql.Identifier(schema),
                deps.sql.Identifier(table_name),
                deps.sql.Identifier(column_name),
                deps.sql.Identifier(column_name),
            )
        )
