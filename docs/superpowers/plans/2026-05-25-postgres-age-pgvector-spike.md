# PostgreSQL AGE pgvector Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the new `postgres_age` backend shape with a minimal PostgreSQL canonical table, AGE projection, pgvector similarity query, AGE BFS query, and transaction rollback check.

**Architecture:** The spike adds an isolated test-only PostgreSQL AGE + pgvector environment and a small helper module under `graphiti_core/driver/postgres_age/`. Canonical data is written to ordinary PostgreSQL tables; AGE stores a rebuildable graph projection used only for traversal. The spike does not implement the full Graphiti driver yet.

**Tech Stack:** Python 3.10+, `psycopg` async pool, `pgvector`, PostgreSQL 16, Apache AGE Docker image, pytest, docker compose.

---

## File Structure

- Modify `pyproject.toml`: add a `postgres-age` optional dependency group.
- Create `docker/postgres-age/Dockerfile`: PostgreSQL image with Apache AGE and pgvector installed.
- Create `docker-compose.postgres-age.yml`: local test service for the spike.
- Create `graphiti_core/driver/postgres_age/__init__.py`: package marker.
- Create `graphiti_core/driver/postgres_age/spike.py`: small async SQL/AGE helper used only by tests.
- Create `tests/driver/test_postgres_age_spike.py`: focused spike tests.
- Update `docs/superpowers/specs/2026-05-25-postgres-age-pgvector-design.md`: append spike outcome notes after implementation.

## Task 1: Add Dependencies And Docker Test Service

**Files:**
- Modify: `pyproject.toml`
- Create: `docker/postgres-age/Dockerfile`
- Create: `docker-compose.postgres-age.yml`

- [x] **Step 1: Add the optional dependency group**

Edit `pyproject.toml` and add this entry under `[project.optional-dependencies]`:

```toml
postgres-age = ["psycopg[binary,pool]>=3.2.0", "pgvector>=0.3.6"]
```

- [x] **Step 2: Create the PostgreSQL AGE + pgvector Dockerfile**

Create `docker/postgres-age/Dockerfile`:

```dockerfile
FROM apache/age:dev_snapshot_PG16

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-16 \
    && git clone --branch v0.8.2 --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector \
    && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector /var/lib/apt/lists/*

USER postgres
```

- [x] **Step 3: Create docker compose service**

Create `docker-compose.postgres-age.yml`:

```yaml
services:
  postgres-age:
    build:
      context: .
      dockerfile: docker/postgres-age/Dockerfile
    ports:
      - "${POSTGRES_AGE_PORT:-55432}:5432"
    environment:
      POSTGRES_USER: graphiti
      POSTGRES_PASSWORD: graphiti
      POSTGRES_DB: graphiti
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U graphiti -d graphiti"]
      interval: 2s
      timeout: 5s
      retries: 30
```

- [x] **Step 4: Sync dependencies**

Run:

```bash
uv sync --extra dev --extra postgres-age
```

Expected: command exits 0 and installs `psycopg`, `psycopg_pool`, and `pgvector`.

- [x] **Step 5: Build and start the service**

Run:

```bash
docker compose -f docker-compose.postgres-age.yml up -d --build
```

Expected: `postgres-age` container starts and becomes healthy.

- [x] **Step 6: Verify extensions are available**

Run:

```bash
docker compose -f docker-compose.postgres-age.yml exec -T postgres-age psql -U graphiti -d graphiti -c "CREATE EXTENSION IF NOT EXISTS age; CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

Expected: command exits 0.

- [x] **Step 7: Commit**

Run:

```bash
git add pyproject.toml docker/postgres-age/Dockerfile docker-compose.postgres-age.yml uv.lock
git commit -m "add postgres age spike environment"
```

## Task 2: Add Spike Helper Skeleton

**Files:**
- Create: `graphiti_core/driver/postgres_age/__init__.py`
- Create: `graphiti_core/driver/postgres_age/spike.py`
- Test: `tests/driver/test_postgres_age_spike.py`

- [x] **Step 1: Write failing import test**

Create `tests/driver/test_postgres_age_spike.py`:

```python
import pytest

from graphiti_core.driver.postgres_age.spike import PostgresAgeSpike


@pytest.mark.asyncio
async def test_spike_helper_can_be_imported():
    helper = PostgresAgeSpike(dsn='postgresql://graphiti:graphiti@localhost:55432/graphiti')
    assert helper.graph_name == 'graphiti_spike'
```

- [x] **Step 2: Run import test and verify it fails**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_spike_helper_can_be_imported -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'graphiti_core.driver.postgres_age'`.

- [x] **Step 3: Add package marker**

Create `graphiti_core/driver/postgres_age/__init__.py`:

```python
"""PostgreSQL AGE + pgvector backend support."""
```

- [x] **Step 4: Add minimal helper**

Create `graphiti_core/driver/postgres_age/spike.py`:

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection, AsyncCursor, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector_async


class PostgresAgeSpike:
    def __init__(self, dsn: str, graph_name: str = 'graphiti_spike') -> None:
        self.dsn = dsn
        self.graph_name = graph_name
        self.pool: AsyncConnectionPool | None = None

    async def open(self) -> None:
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

    async def _setup_age_session(self, conn: AsyncConnection) -> None:
        await register_vector_async(conn)
        async with conn.cursor() as cur:
            await cur.execute("LOAD 'age'")
            await cur.execute('SET search_path = ag_catalog, "$user", public')

    async def execute_sql(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params or {})
                if cur.description is None:
                    return []
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def execute_cypher(self, cypher_query: str, columns: str) -> list[dict]:
        query = sql.SQL('SELECT * FROM cypher({}, $$ {} $$) AS ({})').format(
            sql.Literal(self.graph_name),
            sql.SQL(cypher_query),
            sql.SQL(columns),
        )
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    def decode_agtype_scalar(value: Any) -> Any:
        text = str(value)
        if text.endswith('::numeric'):
            text = text.removesuffix('::numeric')
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text.strip('"')
```

- [x] **Step 5: Run import test and verify it passes**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_spike_helper_can_be_imported -q
```

Expected: PASS.

- [x] **Step 6: Commit**

Run:

```bash
git add graphiti_core/driver/postgres_age/__init__.py graphiti_core/driver/postgres_age/spike.py tests/driver/test_postgres_age_spike.py
git commit -m "add postgres age spike helper"
```

## Task 3: Bootstrap Extensions And Canonical Schema

**Files:**
- Modify: `graphiti_core/driver/postgres_age/spike.py`
- Modify: `tests/driver/test_postgres_age_spike.py`

- [x] **Step 1: Add failing bootstrap test**

Append to `tests/driver/test_postgres_age_spike.py`:

```python
@pytest.mark.asyncio
async def test_bootstrap_creates_extensions_schema_and_graph():
    helper = PostgresAgeSpike(dsn='postgresql://graphiti:graphiti@localhost:55432/graphiti')
    await helper.open()
    try:
        await helper.bootstrap()
        rows = await helper.execute_sql(
            """
            SELECT extname
            FROM pg_extension
            WHERE extname IN ('age', 'vector', 'pg_trgm')
            ORDER BY extname
            """
        )
        assert [row['extname'] for row in rows] == ['age', 'pg_trgm', 'vector']
        tables = await helper.execute_sql(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('spike_entity_nodes', 'spike_entity_edges')
            ORDER BY table_name
            """
        )
        assert [row['table_name'] for row in tables] == [
            'spike_entity_edges',
            'spike_entity_nodes',
        ]
    finally:
        await helper.close()
```

- [x] **Step 2: Run bootstrap test and verify it fails**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_bootstrap_creates_extensions_schema_and_graph -q
```

Expected: FAIL with `AttributeError: 'PostgresAgeSpike' object has no attribute 'bootstrap'`.

- [x] **Step 3: Implement bootstrap**

Add this method to `PostgresAgeSpike` in `graphiti_core/driver/postgres_age/spike.py`:

```python
    async def bootstrap(self) -> None:
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute('CREATE EXTENSION IF NOT EXISTS age')
                await cur.execute('CREATE EXTENSION IF NOT EXISTS vector')
                await cur.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spike_entity_nodes (
                        uuid text PRIMARY KEY,
                        group_id text NOT NULL,
                        name text NOT NULL,
                        summary text NOT NULL,
                        labels text[] NOT NULL DEFAULT '{}',
                        attributes jsonb NOT NULL DEFAULT '{}',
                        name_embedding vector(3),
                        created_at timestamptz NOT NULL DEFAULT now(),
                        search_vector tsvector GENERATED ALWAYS AS (
                            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                            setweight(to_tsvector('simple', coalesce(summary, '')), 'B')
                        ) STORED
                    )
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spike_entity_edges (
                        uuid text PRIMARY KEY,
                        group_id text NOT NULL,
                        source_node_uuid text NOT NULL REFERENCES spike_entity_nodes(uuid)
                            ON DELETE CASCADE,
                        target_node_uuid text NOT NULL REFERENCES spike_entity_nodes(uuid)
                            ON DELETE CASCADE,
                        name text NOT NULL,
                        fact text NOT NULL,
                        fact_embedding vector(3),
                        created_at timestamptz NOT NULL DEFAULT now(),
                        search_vector tsvector GENERATED ALWAYS AS (
                            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                            setweight(to_tsvector('simple', coalesce(fact, '')), 'B')
                        ) STORED
                    )
                    """
                )
                await cur.execute(
                    'CREATE INDEX IF NOT EXISTS spike_entity_nodes_group_id_idx '
                    'ON spike_entity_nodes(group_id)'
                )
                await cur.execute(
                    'CREATE INDEX IF NOT EXISTS spike_entity_edges_group_id_idx '
                    'ON spike_entity_edges(group_id)'
                )
                await cur.execute(
                    'CREATE INDEX IF NOT EXISTS spike_entity_nodes_search_idx '
                    'ON spike_entity_nodes USING gin(search_vector)'
                )
                await cur.execute(
                    'CREATE INDEX IF NOT EXISTS spike_entity_edges_search_idx '
                    'ON spike_entity_edges USING gin(search_vector)'
                )
                await cur.execute(
                    'CREATE INDEX IF NOT EXISTS spike_entity_nodes_embedding_hnsw_idx '
                    'ON spike_entity_nodes USING hnsw (name_embedding vector_cosine_ops)'
                )
                await cur.execute(
                    'CREATE INDEX IF NOT EXISTS spike_entity_edges_embedding_hnsw_idx '
                    'ON spike_entity_edges USING hnsw (fact_embedding vector_cosine_ops)'
                )
                await cur.execute(
                    """
                    SELECT create_graph(%s)
                    WHERE NOT EXISTS (
                        SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s
                    )
                    """,
                    (self.graph_name, self.graph_name),
                )
            await conn.commit()
```

- [x] **Step 4: Run bootstrap test and verify it passes**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_bootstrap_creates_extensions_schema_and_graph -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add graphiti_core/driver/postgres_age/spike.py tests/driver/test_postgres_age_spike.py
git commit -m "bootstrap postgres age spike schema"
```

## Task 4: Save And Load Canonical Entity Nodes

**Files:**
- Modify: `graphiti_core/driver/postgres_age/spike.py`
- Modify: `tests/driver/test_postgres_age_spike.py`

- [x] **Step 1: Add failing save/load test**

Append to `tests/driver/test_postgres_age_spike.py`:

```python
@pytest.mark.asyncio
async def test_save_and_load_entity_node_from_canonical_table():
    helper = PostgresAgeSpike(dsn='postgresql://graphiti:graphiti@localhost:55432/graphiti')
    await helper.open()
    try:
        await helper.bootstrap()
        await helper.clear()
        await helper.save_entity_node(
            uuid='alice',
            group_id='main',
            name='Alice',
            summary='Alice likes graph databases',
            labels=['Person'],
            attributes={'role': 'engineer'},
            embedding=[0.1, 0.2, 0.3],
        )
        row = await helper.get_entity_node('alice')
        assert row['uuid'] == 'alice'
        assert row['name'] == 'Alice'
        assert row['labels'] == ['Person']
        assert row['attributes'] == {'role': 'engineer'}
    finally:
        await helper.close()
```

- [x] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_save_and_load_entity_node_from_canonical_table -q
```

Expected: FAIL with `AttributeError` for `clear` or `save_entity_node`.

- [x] **Step 3: Implement clear, save, and get**

Add these methods to `PostgresAgeSpike`:

```python
    async def clear(self) -> None:
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute('DELETE FROM spike_entity_edges')
                await cur.execute('DELETE FROM spike_entity_nodes')
                await cur.execute(
                    sql.SQL(
                        "SELECT * FROM cypher({}, $$ MATCH (n) DETACH DELETE n $$) AS (n agtype)"
                    ).format(sql.Literal(self.graph_name))
                )
            await conn.commit()

    async def save_entity_node(
        self,
        uuid: str,
        group_id: str,
        name: str,
        summary: str,
        labels: list[str],
        attributes: dict[str, Any],
        embedding: list[float],
    ) -> None:
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO spike_entity_nodes
                        (uuid, group_id, name, summary, labels, attributes, name_embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        group_id = EXCLUDED.group_id,
                        name = EXCLUDED.name,
                        summary = EXCLUDED.summary,
                        labels = EXCLUDED.labels,
                        attributes = EXCLUDED.attributes,
                        name_embedding = EXCLUDED.name_embedding
                    """,
                    (uuid, group_id, name, summary, labels, Jsonb(attributes), embedding),
                )
                await self._merge_entity_projection(cur, uuid, group_id, name, labels)
            await conn.commit()

    async def get_entity_node(self, uuid: str) -> dict[str, Any]:
        rows = await self.execute_sql(
            """
            SELECT uuid, group_id, name, summary, labels, attributes
            FROM spike_entity_nodes
            WHERE uuid = %(uuid)s
            """,
            {'uuid': uuid},
        )
        if not rows:
            raise KeyError(uuid)
        return rows[0]

    async def _merge_entity_projection(
        self,
        cur: AsyncCursor,
        uuid: str,
        group_id: str,
        name: str,
        labels: list[str],
    ) -> None:
        labels_json = json.dumps(labels)
        cypher_query = f"""
        MERGE (n:Entity {{uuid: {json.dumps(uuid)}}})
        SET n.group_id = {json.dumps(group_id)},
            n.name = {json.dumps(name)},
            n.node_kind = 'Entity',
            n.labels = {labels_json}
        RETURN n.uuid
        """
        query = sql.SQL('SELECT * FROM cypher({}, $$ {} $$) AS (uuid agtype)').format(
            sql.Literal(self.graph_name),
            sql.SQL(cypher_query),
        )
        await cur.execute(query)
```

- [x] **Step 4: Run test and verify it passes**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_save_and_load_entity_node_from_canonical_table -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add graphiti_core/driver/postgres_age/spike.py tests/driver/test_postgres_age_spike.py
git commit -m "save postgres age spike entity nodes"
```

## Task 5: Save Entity Edges And Run AGE BFS

**Files:**
- Modify: `graphiti_core/driver/postgres_age/spike.py`
- Modify: `tests/driver/test_postgres_age_spike.py`

- [x] **Step 1: Add failing edge and BFS test**

Append to `tests/driver/test_postgres_age_spike.py`:

```python
@pytest.mark.asyncio
async def test_save_entity_edge_and_bfs_through_age_projection():
    helper = PostgresAgeSpike(dsn='postgresql://graphiti:graphiti@localhost:55432/graphiti')
    await helper.open()
    try:
        await helper.bootstrap()
        await helper.clear()
        await helper.save_entity_node('alice', 'main', 'Alice', 'source', ['Person'], {}, [0.1, 0.2, 0.3])
        await helper.save_entity_node('bob', 'main', 'Bob', 'target', ['Person'], {}, [0.2, 0.3, 0.4])
        await helper.save_entity_edge(
            uuid='edge-1',
            group_id='main',
            source_node_uuid='alice',
            target_node_uuid='bob',
            name='LIKES',
            fact='Alice likes Bob',
            embedding=[0.1, 0.2, 0.3],
        )
        edge = await helper.get_entity_edge('edge-1')
        assert edge['source_node_uuid'] == 'alice'
        assert edge['target_node_uuid'] == 'bob'
        assert await helper.bfs_entity_uuids('alice', max_depth=1) == ['bob']
    finally:
        await helper.close()
```

- [x] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_save_entity_edge_and_bfs_through_age_projection -q
```

Expected: FAIL with `AttributeError` for `save_entity_edge`.

- [x] **Step 3: Implement edge save, edge get, and BFS**

Add these methods to `PostgresAgeSpike`:

```python
    async def save_entity_edge(
        self,
        uuid: str,
        group_id: str,
        source_node_uuid: str,
        target_node_uuid: str,
        name: str,
        fact: str,
        embedding: list[float],
    ) -> None:
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO spike_entity_edges
                        (uuid, group_id, source_node_uuid, target_node_uuid, name, fact, fact_embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        group_id = EXCLUDED.group_id,
                        source_node_uuid = EXCLUDED.source_node_uuid,
                        target_node_uuid = EXCLUDED.target_node_uuid,
                        name = EXCLUDED.name,
                        fact = EXCLUDED.fact,
                        fact_embedding = EXCLUDED.fact_embedding
                    """,
                    (uuid, group_id, source_node_uuid, target_node_uuid, name, fact, embedding),
                )
                await self._merge_edge_projection(
                    cur, uuid, group_id, source_node_uuid, target_node_uuid, name
                )
            await conn.commit()

    async def get_entity_edge(self, uuid: str) -> dict[str, Any]:
        rows = await self.execute_sql(
            """
            SELECT uuid, group_id, source_node_uuid, target_node_uuid, name, fact
            FROM spike_entity_edges
            WHERE uuid = %(uuid)s
            """,
            {'uuid': uuid},
        )
        if not rows:
            raise KeyError(uuid)
        return rows[0]

    async def _merge_edge_projection(
        self,
        cur: AsyncCursor,
        uuid: str,
        group_id: str,
        source_node_uuid: str,
        target_node_uuid: str,
        name: str,
    ) -> None:
        cypher_query = f"""
        MATCH (source:Entity {{uuid: {json.dumps(source_node_uuid)}}})
        MATCH (target:Entity {{uuid: {json.dumps(target_node_uuid)}}})
        MERGE (source)-[e:RELATES_TO {{uuid: {json.dumps(uuid)}}}]->(target)
        SET e.group_id = {json.dumps(group_id)},
            e.edge_kind = 'RELATES_TO',
            e.name = {json.dumps(name)}
        RETURN e.uuid
        """
        query = sql.SQL('SELECT * FROM cypher({}, $$ {} $$) AS (uuid agtype)').format(
            sql.Literal(self.graph_name),
            sql.SQL(cypher_query),
        )
        await cur.execute(query)

    async def bfs_entity_uuids(self, origin_uuid: str, max_depth: int = 1) -> list[str]:
        cypher_query = f"""
        MATCH (origin:Entity {{uuid: {json.dumps(origin_uuid)}}})-[:RELATES_TO*1..{max_depth}]->(n:Entity)
        RETURN n.uuid
        ORDER BY n.uuid
        """
        rows = await self.execute_cypher(cypher_query, 'uuid agtype')
        return [self.decode_agtype_scalar(row['uuid']) for row in rows]
```

- [x] **Step 4: Run test and verify it passes**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_save_entity_edge_and_bfs_through_age_projection -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add graphiti_core/driver/postgres_age/spike.py tests/driver/test_postgres_age_spike.py
git commit -m "validate postgres age spike projection bfs"
```

## Task 6: Validate pgvector And Full-Text Search

**Files:**
- Modify: `graphiti_core/driver/postgres_age/spike.py`
- Modify: `tests/driver/test_postgres_age_spike.py`

- [x] **Step 1: Add failing search test**

Append to `tests/driver/test_postgres_age_spike.py`:

```python
@pytest.mark.asyncio
async def test_vector_and_fulltext_search_use_canonical_tables():
    helper = PostgresAgeSpike(dsn='postgresql://graphiti:graphiti@localhost:55432/graphiti')
    await helper.open()
    try:
        await helper.bootstrap()
        await helper.clear()
        await helper.save_entity_node(
            'alice', 'main', 'Alice', 'Graph database expert', ['Person'], {}, [0.1, 0.2, 0.3]
        )
        await helper.save_entity_node(
            'charlie', 'main', 'Charlie', 'Unrelated baker', ['Person'], {}, [0.9, 0.1, 0.1]
        )
        assert await helper.vector_search_entity_uuids([0.1, 0.2, 0.3], limit=1) == ['alice']
        assert await helper.fulltext_search_entity_uuids('graph database', limit=2) == ['alice']
    finally:
        await helper.close()
```

- [x] **Step 2: Run search test and verify it fails**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_vector_and_fulltext_search_use_canonical_tables -q
```

Expected: FAIL with `AttributeError` for `vector_search_entity_uuids`.

- [x] **Step 3: Implement vector and full-text search**

Add these methods to `PostgresAgeSpike`:

```python
    async def vector_search_entity_uuids(self, embedding: list[float], limit: int) -> list[str]:
        rows = await self.execute_sql(
            """
            SELECT uuid
            FROM spike_entity_nodes
            WHERE name_embedding IS NOT NULL
            ORDER BY name_embedding <=> %(embedding)s::vector
            LIMIT %(limit)s
            """,
            {'embedding': embedding, 'limit': limit},
        )
        return [row['uuid'] for row in rows]

    async def fulltext_search_entity_uuids(self, query: str, limit: int) -> list[str]:
        rows = await self.execute_sql(
            """
            SELECT uuid
            FROM spike_entity_nodes
            WHERE search_vector @@ websearch_to_tsquery('simple', %(query)s)
            ORDER BY ts_rank(search_vector, websearch_to_tsquery('simple', %(query)s)) DESC, uuid
            LIMIT %(limit)s
            """,
            {'query': query, 'limit': limit},
        )
        return [row['uuid'] for row in rows]
```

- [x] **Step 4: Run search test and verify it passes**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_vector_and_fulltext_search_use_canonical_tables -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add graphiti_core/driver/postgres_age/spike.py tests/driver/test_postgres_age_spike.py
git commit -m "validate postgres age spike canonical search"
```

## Task 7: Validate Transaction Rollback

**Files:**
- Modify: `graphiti_core/driver/postgres_age/spike.py`
- Modify: `tests/driver/test_postgres_age_spike.py`

- [x] **Step 1: Add failing rollback test**

Append to `tests/driver/test_postgres_age_spike.py`:

```python
@pytest.mark.asyncio
async def test_failed_projection_write_rolls_back_canonical_write():
    helper = PostgresAgeSpike(dsn='postgresql://graphiti:graphiti@localhost:55432/graphiti')
    await helper.open()
    try:
        await helper.bootstrap()
        await helper.clear()
        with pytest.raises(RuntimeError):
            await helper.save_entity_node_then_fail_projection(
                uuid='rollback-node',
                group_id='main',
                name='Rollback',
                summary='Should not persist',
                labels=['FailureCase'],
                attributes={},
                embedding=[0.3, 0.2, 0.1],
            )
        rows = await helper.execute_sql(
            'SELECT uuid FROM spike_entity_nodes WHERE uuid = %(uuid)s',
            {'uuid': 'rollback-node'},
        )
        assert rows == []
    finally:
        await helper.close()
```

- [x] **Step 2: Run rollback test and verify it fails**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_failed_projection_write_rolls_back_canonical_write -q
```

Expected: FAIL with `AttributeError` for `save_entity_node_then_fail_projection`.

- [x] **Step 3: Implement rollback helper**

Add this method to `PostgresAgeSpike`:

```python
    async def save_entity_node_then_fail_projection(
        self,
        uuid: str,
        group_id: str,
        name: str,
        summary: str,
        labels: list[str],
        attributes: dict[str, Any],
        embedding: list[float],
    ) -> None:
        async with self.connection() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO spike_entity_nodes
                            (uuid, group_id, name, summary, labels, attributes, name_embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uuid,
                            group_id,
                            name,
                            summary,
                            labels,
                            Jsonb(attributes),
                            embedding,
                        ),
                    )
                    raise RuntimeError('forced projection failure')
            except Exception:
                await conn.rollback()
                raise
```

- [x] **Step 4: Run rollback test and verify it passes**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py::test_failed_projection_write_rolls_back_canonical_write -q
```

Expected: PASS.

- [x] **Step 5: Commit**

Run:

```bash
git add graphiti_core/driver/postgres_age/spike.py tests/driver/test_postgres_age_spike.py
git commit -m "validate postgres age spike rollback"
```

## Task 8: Document Spike Outcome And Run Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-05-25-postgres-age-pgvector-design.md`
- Modify: `docs/superpowers/plans/2026-05-25-postgres-age-pgvector-spike.md`

- [x] **Step 1: Run the full spike tests**

Run:

```bash
uv run pytest tests/driver/test_postgres_age_spike.py -q
```

Expected: all spike tests pass.

- [x] **Step 2: Run focused smoke tests**

Run:

```bash
uv run pytest tests/helpers_test.py tests/utils/search/test_search_security.py tests/llm_client/test_token_tracker.py tests/driver/test_postgres_age_spike.py -q
```

Expected: all selected tests pass.

- [x] **Step 3: Append spike outcome to the design doc**

Append this section to `docs/superpowers/specs/2026-05-25-postgres-age-pgvector-design.md`:

```markdown
## Spike Outcome

The spike validated that PostgreSQL canonical tables, pgvector similarity search,
PostgreSQL full-text search, and AGE traversal can run in one PostgreSQL service.
The full backend should keep AGE as a projection layer and use canonical tables
for CRUD and retrieval. Production implementation should replace spike-only
Cypher literal construction with a hardened query builder or prepared-statement
parameter strategy.
```

- [x] **Step 4: Mark this plan as completed**

Update each checklist item in this file from `[ ]` to `[x]` only after the
corresponding command or edit has completed.

- [x] **Step 5: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-05-25-postgres-age-pgvector-design.md docs/superpowers/plans/2026-05-25-postgres-age-pgvector-spike.md
git commit -m "document postgres age spike outcome"
```

## Final Verification

Run:

```bash
git status --short --branch
uv run pytest tests/helpers_test.py tests/utils/search/test_search_security.py tests/llm_client/test_token_tracker.py tests/driver/test_postgres_age_spike.py -q
```

Expected:

- Git status only shows the current branch and no unstaged changes.
- Focused smoke plus spike tests pass.

## Notes For The Full Backend Plan

The spike intentionally uses 3-dimensional vectors and spike-only table names.
The full implementation must make embedding dimensions configurable, integrate
with the existing `GraphDriver` operations interfaces, add MCP/server
configuration, and preserve old database providers.
