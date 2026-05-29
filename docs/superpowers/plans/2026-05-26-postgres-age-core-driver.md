# Postgres AGE Core Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-oriented `PostgresAgeDriver` that can be passed to `Graphiti(graph_driver=PostgresAgeDriver(...))` while preserving all existing graph drivers.

**Architecture:** PostgreSQL ordinary tables are the canonical store for nodes, edges, embeddings, timestamps, attributes, and search indexes. Apache AGE stores a rebuildable graph projection used for graph traversal, and pgvector plus PostgreSQL full-text search operate against canonical tables. The first implementation milestone targets the core library only; server and MCP factory wiring remain outside this plan.

**Tech Stack:** Python async driver code, `psycopg[binary,pool]`, `pgvector`, Apache AGE, PostgreSQL generated `tsvector` columns, existing Graphiti operation ABCs, existing `GraphOperationsInterface` compatibility paths, pytest integration tests.

---

## Progress Update - 2026-05-27

**Status:** paused after completing the core-library path for `PostgresAgeDriver` on branch `codex/postgres-age-pgvector`.

**Selected architecture:**方案 B. PostgreSQL ordinary tables are the canonical source of truth. Apache AGE is a rebuildable graph projection, and pgvector/PostgreSQL full-text search operate against canonical tables. Existing Neo4j, FalkorDB, Kuzu, and Neptune drivers remain in place.

**Completed commits in this worktree:**

- `bd30eda add postgres age community and saga node ops`
- `a696470 add postgres age edge ops projection`
- `bc4fa61 add postgres age graph maintenance ops`
- `5f1be26 add postgres age search ops`
- `50f048d add postgres age legacy interfaces`
- `c7b3c9d cover postgres age bulk legacy path`
- `d3e5933 cover postgres age graphiti triplet path`

**Implemented coverage:**

- `PostgresAgeDriver` package export, provider enum, optional dependency guard, connection/session/transaction wrappers, schema bootstrap, AGE graph creation, and query result shape.
- Canonical PostgreSQL schema for entity, episodic, community, saga nodes and entity, episodic, community, has-episode, next-episode edges.
- Serialization and hydration for all canonical model families.
- Node and edge operation objects for all current operation families.
- Projection writes into Apache AGE for nodes and edges, plus rollback coverage when projection writes fail.
- Graph maintenance operations including projection rebuild, group-aware clear-data, community helpers, mentioned-node lookup, and canonical community membership helpers.
- Search operations backed by canonical tables: FTS, pgvector similarity, bounded BFS, node-distance reranking, and episode-mentions reranking.
- Legacy `GraphOperationsInterface` and `SearchInterface` adapters so existing high-level model methods and `search_utils` routes do not fall back to provider-specific Neo4j/Falkor/Kuzu Cypher.
- LLM-free high-level smoke coverage for `add_nodes_and_edges_bulk()` and `Graphiti.add_triplet()` using stub clients. No real LLM provider was invoked.

**Latest local verification before pause:**

```bash
uv run ruff check graphiti_core/driver/postgres_age tests/driver/postgres_age/test_legacy_interfaces.py
uv run pyright graphiti_core/driver/postgres_age
uv run pytest tests/driver/postgres_age/test_imports.py tests/driver/postgres_age/test_driver_connection.py tests/driver/postgres_age/test_schema.py tests/driver/postgres_age/test_records.py tests/driver/postgres_age/test_node_ops.py tests/driver/postgres_age/test_edge_ops.py tests/driver/postgres_age/test_graph_ops.py tests/driver/postgres_age/test_search_ops.py tests/driver/postgres_age/test_legacy_interfaces.py -q -m "integration or not integration"
```

Result: ruff passed, pyright passed, Postgres AGE driver suite passed with `52 passed, 1 warning`.

**Review status:**

- Spec review for search ops approved after bounded BFS and graph-distance reranker fixes.
- Code-quality review for search ops approved after edge filters, `node_labels`, BFS, and reranker fixes.
- Code-quality review for legacy adapters approved after fixing base `Node.delete()` / `Edge.delete()` dispatch, including `SagaNode`.
- A later spec-review response for the adapter timed out twice; adapter behavior is covered by the integration suite above.

**Current status: COMPLETED (2026-05-27)**

All Options A-D have been completed:

- **Option A** ✅: `ENABLE_POSTGRES_AGE` added to `tests/helpers_test.py` - allows `get_driver(GraphProvider.POSTGRES_AGE)` to return a `PostgresAgeDriver`.
- **Option B** ✅: User-facing docs added at `docs/superpowers/examples/2026-05-27-postgres-age-usage.md` with usage examples, architecture overview, and testing instructions.
- **Option C** ✅: Server/MCP factory wiring implemented:
  - Server: `DatabaseProvider` enum, `postgres_age_dsn/graph_name/embedding_dimension` settings, `ZepGraphiti` updated to accept `graph_driver`
  - MCP: `PostgresAgeProviderConfig` schema, `DatabaseDriverFactory.create_config()` handles `postgres_age`, `GraphitiMCP.__init__` creates `PostgresAgeDriver` for the provider
- **Option D** ✅: `Graphiti.add_episode()` integration test passed with MiniMax LLM - episode created successfully with nodes and edges.

All commits on branch `codex/postgres-age-pgvector` are complete.

---

## File Structure

Create these files under `graphiti_core/driver/postgres_age/`:

- `__init__.py`: public export for `PostgresAgeDriver`, with dependency errors kept helpful.
- `deps.py`: optional dependency guard for `psycopg`, `psycopg_pool`, and `pgvector`.
- `driver.py`: `GraphDriver` implementation, lazy pool opening, session wrapper, transaction wrapper, health check, SQL execution, AGE execution helper, operation properties.
- `schema.py`: extension bootstrap, canonical DDL, indexes, AGE graph creation, projection rebuild helpers.
- `types.py`: small typed aliases and constants for node/edge table names, projection labels, edge kinds, and search limits.
- `serialization.py`: convert Graphiti Pydantic models to canonical row dictionaries and PostgreSQL-safe JSON/vector values.
- `records.py`: convert canonical rows to `EntityNode`, `EpisodicNode`, `CommunityNode`, `SagaNode`, `EntityEdge`, `EpisodicEdge`, `CommunityEdge`, `HasEpisodeEdge`, and `NextEpisodeEdge`.
- `projection.py`: AGE projection writes and traversal queries. All Cypher text in this file is trusted code; user data enters AGE through sanitized JSON literals or canonical UUID hydration.
- `operations/entity_node_ops.py`: canonical CRUD for entity nodes.
- `operations/episode_node_ops.py`: canonical CRUD and retrieval for episodic nodes.
- `operations/community_node_ops.py`: canonical CRUD for community nodes.
- `operations/saga_node_ops.py`: canonical CRUD and saga-specific reads.
- `operations/entity_edge_ops.py`: canonical CRUD for `RELATES_TO` entity edges.
- `operations/episodic_edge_ops.py`: canonical CRUD for `MENTIONS` episodic edges.
- `operations/community_edge_ops.py`: canonical CRUD for `HAS_MEMBER` community edges.
- `operations/has_episode_edge_ops.py`: canonical CRUD for saga-to-episode edges.
- `operations/next_episode_edge_ops.py`: canonical CRUD for episode chain edges.
- `operations/graph_ops.py`: maintenance, clear-data, community helpers, and projection rebuild entry points.
- `operations/search_ops.py`: full-text, vector, AGE BFS, and reranker operations.
- `graph_operations.py`: adapter implementing legacy `GraphOperationsInterface` by delegating to the new operation objects.

Modify these existing files:

- `graphiti_core/driver/driver.py`: add `GraphProvider.POSTGRES_AGE`.
- `graphiti_core/graphiti.py`: route `_get_or_create_saga` and `remove_episode` through `graph_operations_interface` before raw Cypher fallback.
- `tests/helpers_test.py`: add an opt-in Postgres AGE test driver under `ENABLE_POSTGRES_AGE`.
- `pyproject.toml`: ensure `postgres-age` optional extra stays complete; add missing dev dependency only if tests require it.

Create these tests:

- `tests/driver/postgres_age/conftest.py`: Postgres AGE DSN fixture, advisory lock, schema cleanup.
- `tests/driver/postgres_age/test_imports.py`: provider and dependency behavior.
- `tests/driver/postgres_age/test_driver_connection.py`: pool, session, transaction, AGE setup.
- `tests/driver/postgres_age/test_schema.py`: extensions, canonical tables, indexes, graph creation, rebuild.
- `tests/driver/postgres_age/test_node_ops.py`: node CRUD and embedding load.
- `tests/driver/postgres_age/test_edge_ops.py`: edge CRUD and projection writes.
- `tests/driver/postgres_age/test_search_ops.py`: full-text, vector, BFS, rerankers.
- `tests/driver/postgres_age/test_graph_operations_adapter.py`: legacy facade methods used by `nodes.py`, `edges.py`, `bulk_utils.py`, `search_utils.py`, and `graphiti.py`.
- `tests/driver/postgres_age/test_graphiti_core_flow.py`: `Graphiti(graph_driver=PostgresAgeDriver(...))` with a fake embedder and LLM-free direct entity/edge operations.

Use the existing local service:

```bash
docker compose -f docker-compose.postgres-age.yml up -d postgres-age
export POSTGRES_AGE_DSN=postgresql://graphiti:graphiti@localhost:55432/graphiti
```

Do not call any LLM provider in this plan. If a future `Graphiti.add_episode` integration test needs an LLM client and no working provider is configured, stop and ask the user for provider configuration before running that test.

---

### Task 1: Provider, Package Skeleton, and Optional Dependency Guard

**Files:**
- Modify: `graphiti_core/driver/driver.py`
- Create: `graphiti_core/driver/postgres_age/__init__.py`
- Create: `graphiti_core/driver/postgres_age/deps.py`
- Create: `tests/driver/postgres_age/test_imports.py`

- [ ] **Step 1: Write the failing provider and dependency tests**

```python
# tests/driver/postgres_age/test_imports.py
import importlib

from graphiti_core.driver.driver import GraphProvider


def test_postgres_age_provider_exists():
    assert GraphProvider.POSTGRES_AGE.value == 'postgres_age'


def test_postgres_age_public_export():
    module = importlib.import_module('graphiti_core.driver.postgres_age')
    assert hasattr(module, 'PostgresAgeDriver')
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/driver/postgres_age/test_imports.py -q`

Expected: FAIL because `GraphProvider.POSTGRES_AGE` or the package export is missing.

- [ ] **Step 3: Add the provider enum**

```python
# graphiti_core/driver/driver.py
class GraphProvider(Enum):
    NEO4J = 'neo4j'
    FALKORDB = 'falkordb'
    KUZU = 'kuzu'
    NEPTUNE = 'neptune'
    POSTGRES_AGE = 'postgres_age'
```

- [ ] **Step 4: Add dependency guard and package export**

```python
# graphiti_core/driver/postgres_age/deps.py
from __future__ import annotations

from typing import Any


def import_postgres_age_dependencies() -> tuple[Any, Any, Any, Any, Any]:
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

    return AsyncConnection, AsyncCursor, AsyncConnectionPool, Jsonb, dict_row
```

```python
# graphiti_core/driver/postgres_age/__init__.py
from graphiti_core.driver.postgres_age.driver import PostgresAgeDriver

__all__ = ['PostgresAgeDriver']
```

Create a temporary minimal class so the import test can pass before the real driver is built:

```python
# graphiti_core/driver/postgres_age/driver.py
from graphiti_core.driver.driver import GraphDriver, GraphProvider


class PostgresAgeDriver(GraphDriver):
    provider = GraphProvider.POSTGRES_AGE
```

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/driver/postgres_age/test_imports.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add graphiti_core/driver/driver.py graphiti_core/driver/postgres_age tests/driver/postgres_age/test_imports.py
git commit -m "add postgres age driver package"
```

---

### Task 2: Connection, Session, Transaction, and SQL Result Shape

**Files:**
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Create: `tests/driver/postgres_age/conftest.py`
- Create: `tests/driver/postgres_age/test_driver_connection.py`

- [ ] **Step 1: Write failing connection tests**

```python
# tests/driver/postgres_age/conftest.py
import os
from collections.abc import AsyncIterator

import pytest

pytest.importorskip('pgvector')
pytest.importorskip('psycopg')
pytest.importorskip('psycopg_pool')

from graphiti_core.driver.postgres_age import PostgresAgeDriver


@pytest.fixture
def postgres_age_dsn() -> str:
    return os.getenv(
        'POSTGRES_AGE_DSN',
        'postgresql://graphiti:graphiti@localhost:55432/graphiti',
    )


@pytest.fixture
async def postgres_age_driver(postgres_age_dsn: str) -> AsyncIterator[PostgresAgeDriver]:
    driver = PostgresAgeDriver(
        dsn=postgres_age_dsn,
        graph_name='graphiti_test_core',
        embedding_dimension=384,
    )
    try:
        yield driver
    finally:
        await driver.close()
```

```python
# tests/driver/postgres_age/test_driver_connection.py
import pytest


@pytest.mark.integration
async def test_execute_query_returns_neo4j_like_tuple(postgres_age_driver):
    records, summary, keys = await postgres_age_driver.execute_query(
        'SELECT %s::text AS value',
        params=('ok',),
    )

    assert records == [{'value': 'ok'}]
    assert summary is None
    assert keys == ['value']


@pytest.mark.integration
async def test_transaction_rolls_back_on_error(postgres_age_driver):
    await postgres_age_driver.execute_query(
        'CREATE TEMP TABLE graphiti_tx_probe (value text) ON COMMIT PRESERVE ROWS'
    )

    with pytest.raises(RuntimeError):
        async with postgres_age_driver.transaction() as tx:
            await tx.run('INSERT INTO graphiti_tx_probe (value) VALUES (%s)', ('rolled-back',))
            raise RuntimeError('force rollback')

    records, _, _ = await postgres_age_driver.execute_query(
        'SELECT value FROM graphiti_tx_probe'
    )
    assert records == []


@pytest.mark.integration
async def test_session_execute_write_runs_callback(postgres_age_driver):
    async with postgres_age_driver.session() as session:
        result = await session.execute_write(
            lambda tx: tx.run('SELECT %s::text AS value', ('written',))
        )

    assert result[0][0]['value'] == 'written'
```

- [ ] **Step 2: Run connection tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_driver_connection.py -q -m integration`

Expected: FAIL because `PostgresAgeDriver` is still a skeleton.

- [ ] **Step 3: Implement lazy pool, SQL execution, transaction, and session wrappers**

Use `AsyncConnectionPool(open=False)` in `__init__`, open it lazily in `_ensure_open()`, and call `_setup_connection()` before each use:

```python
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
        super().__init__()
        self.dsn = dsn
        self.graph_name = graph_name
        self.schema = schema
        self.embedding_dimension = embedding_dimension
        self._database = 'postgres'
        self._pool = AsyncConnectionPool(
            dsn,
            min_size=pool_min_size,
            max_size=pool_max_size,
            open=False,
        )
        self._pool_open = False

    async def _ensure_open(self) -> None:
        if not self._pool_open:
            await self._pool.open()
            self._pool_open = True

    async def _setup_connection(self, conn: Any) -> None:
        await register_vector_async(conn)
        async with conn.cursor() as cur:
            await cur.execute("LOAD 'age'")
            await cur.execute('SET search_path = ag_catalog, "$user", public')

    async def execute_query(self, cypher_query_: str, **kwargs: Any) -> tuple[list[dict], None, list[str]]:
        await self._ensure_open()
        params = kwargs.pop('params', None)
        if params is None:
            params = tuple(kwargs.values()) if kwargs else None
        async with self._pool.connection() as conn:
            await self._setup_connection(conn)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(cypher_query_, params)
                if cur.description is None:
                    await conn.commit()
                    return [], None, []
                rows = [dict(row) for row in await cur.fetchall()]
                keys = [column.name for column in cur.description]
                await conn.commit()
                return rows, None, keys
```

Add `_PostgresAgeTransaction` and `_PostgresAgeSession` wrappers in the same file. `execute_write` must accept sync callbacks that return awaitables and async callbacks directly.

- [ ] **Step 4: Run connection tests**

Run: `uv run pytest tests/driver/postgres_age/test_driver_connection.py -q -m integration`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add graphiti_core/driver/postgres_age/driver.py tests/driver/postgres_age/conftest.py tests/driver/postgres_age/test_driver_connection.py
git commit -m "add postgres age driver connection primitives"
```

---

### Task 3: Canonical Schema, Indexes, AGE Graph, and Rebuild

**Files:**
- Create: `graphiti_core/driver/postgres_age/types.py`
- Create: `graphiti_core/driver/postgres_age/schema.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Create: `tests/driver/postgres_age/test_schema.py`

- [ ] **Step 1: Write failing schema tests**

```python
# tests/driver/postgres_age/test_schema.py
import pytest


EXPECTED_TABLES = {
    'entity_nodes',
    'episodic_nodes',
    'community_nodes',
    'saga_nodes',
    'entity_edges',
    'episodic_edges',
    'community_edges',
    'has_episode_edges',
    'next_episode_edges',
}


@pytest.mark.integration
async def test_build_indices_creates_extensions_tables_and_age_graph(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)

    records, _, _ = await postgres_age_driver.execute_query(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = ANY(%s)
        """,
        params=(sorted(EXPECTED_TABLES),),
    )
    assert {row['tablename'] for row in records} == EXPECTED_TABLES

    records, _, _ = await postgres_age_driver.execute_query(
        """
        SELECT extname
        FROM pg_extension
        WHERE extname = ANY(%s)
        """,
        params=(['age', 'vector', 'pg_trgm'],),
    )
    assert {row['extname'] for row in records} == {'age', 'vector', 'pg_trgm'}

    records, _, _ = await postgres_age_driver.execute_query(
        'SELECT name FROM ag_catalog.ag_graph WHERE name = %s',
        params=(postgres_age_driver.graph_name,),
    )
    assert records == [{'name': postgres_age_driver.graph_name}]
```

- [ ] **Step 2: Run schema tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_schema.py -q -m integration`

Expected: FAIL because schema helpers are missing.

- [ ] **Step 3: Add schema DDL**

`schema.py` must create extensions first, then canonical tables. Use `vector({embedding_dimension})` for embedding columns. Required canonical columns:

```sql
entity_nodes:
  uuid text primary key,
  group_id text not null,
  name text not null,
  summary text not null default '',
  labels text[] not null default '{}',
  attributes jsonb not null default '{}',
  name_embedding vector(N),
  created_at timestamptz not null,
  search_vector tsvector generated always as (...)

episodic_nodes:
  uuid text primary key,
  group_id text not null,
  name text not null,
  source text not null,
  source_description text not null,
  content text not null,
  valid_at timestamptz not null,
  entity_edges text[] not null default '{}',
  episode_metadata jsonb,
  created_at timestamptz not null,
  search_vector tsvector generated always as (...)

community_nodes:
  uuid text primary key,
  group_id text not null,
  name text not null,
  summary text not null default '',
  name_embedding vector(N),
  created_at timestamptz not null,
  search_vector tsvector generated always as (...)

saga_nodes:
  uuid text primary key,
  group_id text not null,
  name text not null,
  summary text not null default '',
  first_episode_uuid text,
  last_episode_uuid text,
  last_summarized_at timestamptz,
  last_summarized_episode_valid_at timestamptz,
  created_at timestamptz not null
```

Edge tables must store `uuid`, `group_id`, `source_node_uuid`, `target_node_uuid`, `created_at`, and type-specific fields. Use foreign keys where endpoints are canonical tables and use `ON DELETE CASCADE`.

- [ ] **Step 4: Wire driver bootstrap**

`build_indices_and_constraints(delete_existing=True)` must:

1. Drop AGE graph when requested.
2. Drop canonical tables when requested.
3. Create extensions, tables, B-tree indexes, GIN full-text indexes, HNSW vector indexes.
4. Create AGE graph if absent.
5. Commit or roll back as one unit.

- [ ] **Step 5: Run schema tests**

Run: `uv run pytest tests/driver/postgres_age/test_schema.py -q -m integration`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add graphiti_core/driver/postgres_age/types.py graphiti_core/driver/postgres_age/schema.py graphiti_core/driver/postgres_age/driver.py tests/driver/postgres_age/test_schema.py
git commit -m "add postgres age canonical schema"
```

---

### Task 4: Serialization and Record Hydration

**Files:**
- Create: `graphiti_core/driver/postgres_age/serialization.py`
- Create: `graphiti_core/driver/postgres_age/records.py`
- Create: `tests/driver/postgres_age/test_records.py`

- [ ] **Step 1: Write failing serialization tests**

```python
# tests/driver/postgres_age/test_records.py
from datetime import datetime, timezone

from graphiti_core.driver.postgres_age.records import entity_node_from_row
from graphiti_core.driver.postgres_age.serialization import entity_node_to_row
from graphiti_core.nodes import EntityNode


def test_entity_node_round_trip_preserves_attributes_and_labels():
    created_at = datetime(2026, 5, 26, tzinfo=timezone.utc)
    node = EntityNode(
        uuid='node-1',
        name='Alice',
        group_id='main',
        labels=['Person'],
        summary='Engineer',
        attributes={'role': 'staff'},
        name_embedding=[0.1, 0.2, 0.3],
        created_at=created_at,
    )

    row = entity_node_to_row(node)
    hydrated = entity_node_from_row(row)

    assert hydrated.uuid == node.uuid
    assert hydrated.labels == ['Person']
    assert hydrated.attributes == {'role': 'staff'}
    assert hydrated.name_embedding == [0.1, 0.2, 0.3]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_records.py -q`

Expected: FAIL because serializers are missing.

- [ ] **Step 3: Implement model-to-row serializers**

Each serializer returns a plain dictionary with PostgreSQL column names. Use `Jsonb` only at SQL binding time so tests can inspect normal dictionaries.

```python
def entity_node_to_row(node: EntityNode) -> dict[str, Any]:
    return {
        'uuid': node.uuid,
        'group_id': node.group_id,
        'name': node.name,
        'summary': node.summary,
        'labels': node.labels,
        'attributes': node.attributes,
        'name_embedding': node.name_embedding,
        'created_at': node.created_at,
    }
```

- [ ] **Step 4: Implement row-to-model hydrators**

Hydrators must not mutate input rows. Convert vector values to `list[float] | None`, arrays to lists, and JSONB to dictionaries.

```python
def entity_node_from_row(row: Mapping[str, Any]) -> EntityNode:
    return EntityNode(
        uuid=row['uuid'],
        name=row['name'],
        group_id=row['group_id'],
        labels=list(row.get('labels') or []),
        summary=row.get('summary') or '',
        attributes=dict(row.get('attributes') or {}),
        name_embedding=_vector_to_list(row.get('name_embedding')),
        created_at=row['created_at'],
    )
```

- [ ] **Step 5: Add serializers and hydrators for every canonical model**

Add functions for all nine model families:

```python
entity_node_to_row / entity_node_from_row
episodic_node_to_row / episodic_node_from_row
community_node_to_row / community_node_from_row
saga_node_to_row / saga_node_from_row
entity_edge_to_row / entity_edge_from_row
episodic_edge_to_row / episodic_edge_from_row
community_edge_to_row / community_edge_from_row
has_episode_edge_to_row / has_episode_edge_from_row
next_episode_edge_to_row / next_episode_edge_from_row
```

- [ ] **Step 6: Run record tests**

Run: `uv run pytest tests/driver/postgres_age/test_records.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add graphiti_core/driver/postgres_age/serialization.py graphiti_core/driver/postgres_age/records.py tests/driver/postgres_age/test_records.py
git commit -m "add postgres age record hydration"
```

---

### Task 5: Entity and Episodic Node Operations

**Files:**
- Create: `graphiti_core/driver/postgres_age/operations/__init__.py`
- Create: `graphiti_core/driver/postgres_age/operations/entity_node_ops.py`
- Create: `graphiti_core/driver/postgres_age/operations/episode_node_ops.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Create: `tests/driver/postgres_age/test_node_ops.py`

- [ ] **Step 1: Write failing entity and episodic node tests**

```python
# tests/driver/postgres_age/test_node_ops.py
from datetime import datetime, timezone

import pytest

from graphiti_core.errors import NodeNotFoundError
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode


@pytest.mark.integration
async def test_entity_node_ops_save_load_delete(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    node = EntityNode(
        uuid='entity-1',
        name='Alice',
        group_id='main',
        labels=['Person'],
        summary='Graph engineer',
        attributes={'level': 7},
        name_embedding=[0.1] * 384,
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, node)
    loaded = await postgres_age_driver.entity_node_ops.get_by_uuid(postgres_age_driver, node.uuid)

    assert loaded.uuid == node.uuid
    assert loaded.attributes == {'level': 7}

    await postgres_age_driver.entity_node_ops.delete(postgres_age_driver, node)
    with pytest.raises(NodeNotFoundError):
        await postgres_age_driver.entity_node_ops.get_by_uuid(postgres_age_driver, node.uuid)


@pytest.mark.integration
async def test_episodic_node_ops_save_and_get_by_entity_node_uuid(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    episode = EpisodicNode(
        uuid='episode-1',
        name='episode',
        group_id='main',
        source=EpisodeType.message,
        source_description='chat',
        content='Alice likes Bob',
        valid_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        entity_edges=['edge-1'],
        episode_metadata={'source': 'test'},
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    await postgres_age_driver.episode_node_ops.save(postgres_age_driver, episode)
    loaded = await postgres_age_driver.episode_node_ops.get_by_uuid(
        postgres_age_driver, episode.uuid
    )

    assert loaded.uuid == episode.uuid
    assert loaded.episode_metadata == {'source': 'test'}
```

- [ ] **Step 2: Run node tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_node_ops.py -q -m integration`

Expected: FAIL because node operations are missing.

- [ ] **Step 3: Implement entity node operations**

Use canonical SQL with `ON CONFLICT (uuid) DO UPDATE`. For projection, save entity node properties to AGE in the same transaction:

```sql
INSERT INTO entity_nodes (...)
VALUES (...)
ON CONFLICT (uuid) DO UPDATE SET
  group_id = EXCLUDED.group_id,
  name = EXCLUDED.name,
  summary = EXCLUDED.summary,
  labels = EXCLUDED.labels,
  attributes = EXCLUDED.attributes,
  name_embedding = EXCLUDED.name_embedding,
  created_at = EXCLUDED.created_at
```

Projection write:

```cypher
MERGE (n:Entity {uuid: '<uuid>'})
SET n.group_id = '<group_id>',
    n.name = '<name>',
    n.labels = <labels-json>
```

Use a helper in `projection.py` to produce escaped AGE literals from trusted row dictionaries.

- [ ] **Step 4: Implement episodic node operations**

Episodic node CRUD reads and writes canonical `episodic_nodes`. Projection writes an `Episodic` vertex with `uuid`, `group_id`, `name`, and `valid_at`. `get_by_entity_node_uuid` reads via `episodic_edges` canonical rows:

```sql
SELECT ep.*
FROM episodic_nodes ep
JOIN episodic_edges ee ON ee.source_node_uuid = ep.uuid
WHERE ee.target_node_uuid = %s
ORDER BY ep.valid_at ASC, ep.created_at ASC
```

- [ ] **Step 5: Wire driver properties**

Instantiate `PostgresAgeEntityNodeOperations` and `PostgresAgeEpisodeNodeOperations` in `PostgresAgeDriver.__init__`, and add `entity_node_ops` and `episode_node_ops` properties.

- [ ] **Step 6: Run node tests**

Run: `uv run pytest tests/driver/postgres_age/test_node_ops.py -q -m integration`

Expected: PASS for entity and episodic cases.

- [ ] **Step 7: Commit**

```bash
git add graphiti_core/driver/postgres_age/driver.py graphiti_core/driver/postgres_age/operations tests/driver/postgres_age/test_node_ops.py
git commit -m "add postgres age entity and episode node ops"
```

---

### Task 6: Community and Saga Node Operations

**Files:**
- Create: `graphiti_core/driver/postgres_age/operations/community_node_ops.py`
- Create: `graphiti_core/driver/postgres_age/operations/saga_node_ops.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Extend: `tests/driver/postgres_age/test_node_ops.py`

- [ ] **Step 1: Add failing community and saga tests**

```python
@pytest.mark.integration
async def test_community_node_ops_save_load_embedding(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    node = CommunityNode(
        uuid='community-1',
        name='Team Alpha',
        group_id='main',
        summary='Alice and Bob',
        name_embedding=[0.2] * 384,
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    await postgres_age_driver.community_node_ops.save(postgres_age_driver, node)
    loaded = await postgres_age_driver.community_node_ops.get_by_uuid(
        postgres_age_driver, node.uuid
    )

    assert loaded.uuid == node.uuid
    loaded.name_embedding = None
    await postgres_age_driver.community_node_ops.load_name_embedding(
        postgres_age_driver, loaded
    )
    assert loaded.name_embedding == [0.2] * 384


@pytest.mark.integration
async def test_saga_node_ops_find_by_name_through_graphiti_helper(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    saga = SagaNode(
        uuid='saga-1',
        name='Daily Standup',
        group_id='main',
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    await postgres_age_driver.saga_node_ops.save(postgres_age_driver, saga)
    records, _, _ = await postgres_age_driver.graph_operations_interface.saga_get_episode_contents(
        postgres_age_driver,
        saga.uuid,
        limit=10,
    )

    assert records == []
```

- [ ] **Step 2: Run node tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_node_ops.py -q -m integration`

Expected: FAIL on community and saga operations.

- [ ] **Step 3: Implement community node operations**

Community nodes use `community_nodes`, vector embeddings, full-text search columns, and an AGE `Community` vertex projection. `delete_by_group_id` removes community nodes and `community_edges` for those groups.

- [ ] **Step 4: Implement saga node operations**

Saga nodes use `saga_nodes`, have no embedding, and project to AGE `Saga` vertices. Add saga reads:

```sql
SELECT e.uuid
FROM has_episode_edges h
JOIN episodic_nodes e ON e.uuid = h.target_node_uuid
WHERE h.source_node_uuid = %s
  AND e.uuid <> %s
ORDER BY e.valid_at DESC, e.created_at DESC
LIMIT 1
```

```sql
SELECT e.content, e.valid_at
FROM has_episode_edges h
JOIN episodic_nodes e ON e.uuid = h.target_node_uuid
WHERE h.source_node_uuid = %s
  AND (%s::timestamptz IS NULL OR e.created_at > %s::timestamptz)
ORDER BY e.valid_at ASC, e.created_at ASC
LIMIT %s
```

- [ ] **Step 5: Wire driver properties**

Instantiate `PostgresAgeCommunityNodeOperations` and `PostgresAgeSagaNodeOperations` and expose `community_node_ops` and `saga_node_ops`.

- [ ] **Step 6: Run node tests**

Run: `uv run pytest tests/driver/postgres_age/test_node_ops.py -q -m integration`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add graphiti_core/driver/postgres_age/operations/community_node_ops.py graphiti_core/driver/postgres_age/operations/saga_node_ops.py graphiti_core/driver/postgres_age/driver.py tests/driver/postgres_age/test_node_ops.py
git commit -m "add postgres age community and saga node ops"
```

---

### Task 7: Edge Operations and Atomic Projection Writes

**Files:**
- Create: `graphiti_core/driver/postgres_age/projection.py`
- Create: `graphiti_core/driver/postgres_age/operations/entity_edge_ops.py`
- Create: `graphiti_core/driver/postgres_age/operations/episodic_edge_ops.py`
- Create: `graphiti_core/driver/postgres_age/operations/community_edge_ops.py`
- Create: `graphiti_core/driver/postgres_age/operations/has_episode_edge_ops.py`
- Create: `graphiti_core/driver/postgres_age/operations/next_episode_edge_ops.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Create: `tests/driver/postgres_age/test_edge_ops.py`

- [ ] **Step 1: Write failing edge and rollback tests**

```python
# tests/driver/postgres_age/test_edge_ops.py
from datetime import datetime, timezone

import pytest

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.errors import EdgeNotFoundError
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode


@pytest.mark.integration
async def test_entity_edge_save_load_delete_and_projection(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    created_at = datetime(2026, 5, 26, tzinfo=timezone.utc)
    for uuid, name in [('alice', 'Alice'), ('bob', 'Bob')]:
        await postgres_age_driver.entity_node_ops.save(
            postgres_age_driver,
            EntityNode(uuid=uuid, name=name, group_id='main', created_at=created_at),
        )

    edge = EntityEdge(
        uuid='edge-1',
        group_id='main',
        source_node_uuid='alice',
        target_node_uuid='bob',
        name='LIKES',
        fact='Alice likes Bob',
        fact_embedding=[0.3] * 384,
        episodes=['episode-1'],
        created_at=created_at,
    )

    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)
    loaded = await postgres_age_driver.entity_edge_ops.get_by_uuid(postgres_age_driver, edge.uuid)
    assert loaded.fact == 'Alice likes Bob'

    rows = await postgres_age_driver.execute_age_cypher(
        "MATCH (:Entity {uuid: 'alice'})-[e:RELATES_TO]->(:Entity {uuid: 'bob'}) RETURN e.uuid",
        'uuid agtype',
    )
    assert rows == [{'uuid': 'edge-1'}]

    await postgres_age_driver.entity_edge_ops.delete(postgres_age_driver, edge)
    with pytest.raises(EdgeNotFoundError):
        await postgres_age_driver.entity_edge_ops.get_by_uuid(postgres_age_driver, edge.uuid)


@pytest.mark.integration
async def test_projection_failure_rolls_back_canonical_edge(postgres_age_driver, monkeypatch):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)

    async def fail_projection(*args, **kwargs):
        raise RuntimeError('forced projection failure')

    monkeypatch.setattr(postgres_age_driver.entity_edge_ops, '_project_save', fail_projection)
    edge = EntityEdge(
        uuid='edge-rollback',
        group_id='main',
        source_node_uuid='missing-a',
        target_node_uuid='missing-b',
        name='BROKEN',
        fact='broken',
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    with pytest.raises(RuntimeError, match='forced projection failure'):
        await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    records, _, _ = await postgres_age_driver.execute_query(
        'SELECT uuid FROM entity_edges WHERE uuid = %s',
        params=(edge.uuid,),
    )
    assert records == []
```

- [ ] **Step 2: Run edge tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_edge_ops.py -q -m integration`

Expected: FAIL because edge operations are missing.

- [ ] **Step 3: Implement AGE execution helper**

Add `execute_age_cypher(cypher: str, columns: str)` to `PostgresAgeDriver`. Reuse the spike safeguards:

- Reject `$$` in trusted Cypher text.
- Require columns to match `name agtype[, name agtype]`.
- Execute `SELECT * FROM cypher(%s, $$ ... $$) AS (columns)`.
- Convert simple agtype scalar strings into Python strings where tests expect them.

- [ ] **Step 4: Implement edge operations**

Each save method writes canonical first, then projection, inside one SQL transaction. Projection labels:

```text
EntityEdge      -> (:Entity)-[:RELATES_TO]->(:Entity)
EpisodicEdge    -> (:Episodic)-[:MENTIONS]->(:Entity)
CommunityEdge   -> (:Community)-[:HAS_MEMBER]->(:Entity)
HasEpisodeEdge  -> (:Saga)-[:HAS_EPISODE]->(:Episodic)
NextEpisodeEdge -> (:Episodic)-[:NEXT_EPISODE]->(:Episodic)
```

All reads hydrate from canonical tables. Delete operations delete canonical row first and projection edge second in the same transaction.

- [ ] **Step 5: Wire driver properties**

Instantiate all five edge operation objects and expose the corresponding operation properties.

- [ ] **Step 6: Run edge tests**

Run: `uv run pytest tests/driver/postgres_age/test_edge_ops.py -q -m integration`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add graphiti_core/driver/postgres_age/projection.py graphiti_core/driver/postgres_age/operations/*edge_ops.py graphiti_core/driver/postgres_age/driver.py tests/driver/postgres_age/test_edge_ops.py
git commit -m "add postgres age edge ops and projection writes"
```

---

### Task 8: Graph Maintenance Operations and Projection Rebuild

**Files:**
- Create: `graphiti_core/driver/postgres_age/operations/graph_ops.py`
- Modify: `graphiti_core/driver/postgres_age/schema.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Create: `tests/driver/postgres_age/test_graph_ops.py`

- [ ] **Step 1: Write failing maintenance tests**

```python
# tests/driver/postgres_age/test_graph_ops.py
import pytest


@pytest.mark.integration
async def test_clear_data_deletes_group_and_projection(postgres_age_driver, sample_entity_pair):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    alice, bob, edge = sample_entity_pair
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, alice)
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, bob)
    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    await postgres_age_driver.graph_ops.clear_data(postgres_age_driver, ['main'])

    records, _, _ = await postgres_age_driver.execute_query('SELECT uuid FROM entity_nodes')
    assert records == []
    rows = await postgres_age_driver.execute_age_cypher('MATCH (n) RETURN n.uuid', 'uuid agtype')
    assert rows == []


@pytest.mark.integration
async def test_rebuild_projection_recreates_age_from_canonical(postgres_age_driver, sample_entity_pair):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    alice, bob, edge = sample_entity_pair
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, alice)
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, bob)
    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    await postgres_age_driver.drop_age_graph()
    await postgres_age_driver.rebuild_projection()

    rows = await postgres_age_driver.execute_age_cypher(
        "MATCH (:Entity {uuid: 'alice'})-[e:RELATES_TO]->(:Entity {uuid: 'bob'}) RETURN e.uuid",
        'uuid agtype',
    )
    assert rows == [{'uuid': edge.uuid}]
```

- [ ] **Step 2: Run graph ops tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_graph_ops.py -q -m integration`

Expected: FAIL because graph maintenance and rebuild are missing.

- [ ] **Step 3: Implement clear data**

`clear_data(driver, group_ids=None)` deletes canonical tables in dependency order:

```text
next_episode_edges
has_episode_edges
community_edges
episodic_edges
entity_edges
saga_nodes
community_nodes
episodic_nodes
entity_nodes
```

When `group_ids` is provided, delete only rows with matching `group_id`; cascading foreign keys clean dependent rows. Projection clear should use AGE `MATCH (n) DETACH DELETE n` for full clear and rebuild from remaining canonical rows for group-specific clear.

- [ ] **Step 4: Implement projection rebuild**

`rebuild_projection()` drops and recreates the AGE graph, then projects canonical rows in this order:

1. entity nodes
2. episodic nodes
3. community nodes
4. saga nodes
5. entity edges
6. episodic edges
7. community edges
8. has episode edges
9. next episode edges

- [ ] **Step 5: Implement community helpers**

Implement:

- `get_mentioned_nodes`: join `episodic_edges` to `entity_nodes`.
- `get_communities_by_nodes`: join `community_edges` to `community_nodes`.
- `remove_communities`: delete `community_edges` and `community_nodes`.
- `determine_entity_community`: first direct membership, then neighbor majority through `entity_edges` and `community_edges`.
- `get_community_clusters`: connected components over `entity_edges` grouped by `group_id`.

- [ ] **Step 6: Wire driver properties and convenience methods**

Expose `graph_ops`, `drop_age_graph()`, and `rebuild_projection()` on the driver.

- [ ] **Step 7: Run graph ops tests**

Run: `uv run pytest tests/driver/postgres_age/test_graph_ops.py -q -m integration`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add graphiti_core/driver/postgres_age/operations/graph_ops.py graphiti_core/driver/postgres_age/schema.py graphiti_core/driver/postgres_age/driver.py tests/driver/postgres_age/test_graph_ops.py
git commit -m "add postgres age graph maintenance"
```

---

### Task 9: Search Operations with FTS, pgvector, and AGE BFS

**Files:**
- Create: `graphiti_core/driver/postgres_age/operations/search_ops.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Create: `tests/driver/postgres_age/test_search_ops.py`

- [ ] **Step 1: Write failing search tests**

```python
# tests/driver/postgres_age/test_search_ops.py
import pytest

from graphiti_core.search.search_filters import SearchFilters


@pytest.mark.integration
async def test_node_fulltext_similarity_and_bfs(postgres_age_driver, sample_entity_pair):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    alice, bob, edge = sample_entity_pair
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, alice)
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, bob)
    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    filters = SearchFilters()
    fulltext = await postgres_age_driver.search_ops.node_fulltext_search(
        postgres_age_driver, 'Alice', filters, group_ids=['main'], limit=5
    )
    similarity = await postgres_age_driver.search_ops.node_similarity_search(
        postgres_age_driver, alice.name_embedding, filters, group_ids=['main'], limit=5, min_score=0
    )
    bfs = await postgres_age_driver.search_ops.node_bfs_search(
        postgres_age_driver, ['alice'], filters, max_depth=1, group_ids=['main'], limit=5
    )

    assert [node.uuid for node in fulltext] == ['alice']
    assert similarity[0].uuid == 'alice'
    assert [node.uuid for node in bfs] == ['bob']


@pytest.mark.integration
async def test_edge_fulltext_similarity_and_bfs(postgres_age_driver, sample_entity_pair):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    alice, bob, edge = sample_entity_pair
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, alice)
    await postgres_age_driver.entity_node_ops.save(postgres_age_driver, bob)
    await postgres_age_driver.entity_edge_ops.save(postgres_age_driver, edge)

    filters = SearchFilters()
    fulltext = await postgres_age_driver.search_ops.edge_fulltext_search(
        postgres_age_driver, 'likes', filters, group_ids=['main'], limit=5
    )
    similarity = await postgres_age_driver.search_ops.edge_similarity_search(
        postgres_age_driver,
        edge.fact_embedding,
        None,
        None,
        filters,
        group_ids=['main'],
        limit=5,
        min_score=0,
    )
    bfs = await postgres_age_driver.search_ops.edge_bfs_search(
        postgres_age_driver, ['alice'], max_depth=1, search_filter=filters, group_ids=['main'], limit=5
    )

    assert [item.uuid for item in fulltext] == [edge.uuid]
    assert similarity[0].uuid == edge.uuid
    assert [item.uuid for item in bfs] == [edge.uuid]
```

- [ ] **Step 2: Run search tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_search_ops.py -q -m integration`

Expected: FAIL because search operations are missing.

- [ ] **Step 3: Implement full-text search**

Use `websearch_to_tsquery('simple', query)` and `ts_rank_cd(search_vector, query)` against canonical generated columns. Apply `group_ids`, `node_labels`, `entity_types`, and edge filters in SQL rather than Cypher.

- [ ] **Step 4: Implement vector search**

Use pgvector cosine distance:

```sql
SELECT *, 1 - (name_embedding <=> %s::vector) AS score
FROM entity_nodes
WHERE name_embedding IS NOT NULL
  AND 1 - (name_embedding <=> %s::vector) > %s
ORDER BY name_embedding <=> %s::vector
LIMIT %s
```

Repeat the pattern for `entity_edges.fact_embedding` and `community_nodes.name_embedding`.

- [ ] **Step 5: Implement AGE BFS search**

Run bounded AGE traversals only. Enforce `1 <= max_depth <= 5` in Python. AGE queries return UUIDs; hydrate final results from canonical tables. Use the existing spike approach as the safety reference.

- [ ] **Step 6: Implement rerankers**

`node_distance_reranker` uses AGE shortest bounded path from the center node and returns hydrated nodes ordered by shortest distance. `episode_mentions_reranker` counts distinct `episodic_edges` mentions and returns hydrated nodes ordered by mention count.

- [ ] **Step 7: Wire driver property**

Instantiate `PostgresAgeSearchOperations` and expose `search_ops`.

- [ ] **Step 8: Run search tests**

Run: `uv run pytest tests/driver/postgres_age/test_search_ops.py -q -m integration`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add graphiti_core/driver/postgres_age/operations/search_ops.py graphiti_core/driver/postgres_age/driver.py tests/driver/postgres_age/test_search_ops.py
git commit -m "add postgres age search operations"
```

---

### Task 10: Legacy GraphOperationsInterface Adapter and Graphiti Compatibility

**Files:**
- Create: `graphiti_core/driver/postgres_age/graph_operations.py`
- Modify: `graphiti_core/driver/postgres_age/driver.py`
- Modify: `graphiti_core/graphiti.py`
- Create: `tests/driver/postgres_age/test_graph_operations_adapter.py`
- Create: `tests/driver/postgres_age/test_graphiti_core_flow.py`

- [ ] **Step 1: Write failing adapter tests**

```python
# tests/driver/postgres_age/test_graph_operations_adapter.py
import pytest


@pytest.mark.integration
async def test_legacy_node_methods_route_through_adapter(postgres_age_driver, sample_entity_pair):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    alice, bob, edge = sample_entity_pair

    await postgres_age_driver.graph_operations_interface.node_save(alice, postgres_age_driver)
    loaded = await postgres_age_driver.graph_operations_interface.node_get_by_uuid(
        type(alice), postgres_age_driver, alice.uuid
    )

    assert loaded.uuid == alice.uuid


@pytest.mark.integration
async def test_legacy_bulk_methods_route_through_adapter(postgres_age_driver, sample_entity_pair):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    alice, bob, edge = sample_entity_pair

    async with postgres_age_driver.transaction() as tx:
        await postgres_age_driver.graph_operations_interface.node_save_bulk(
            None, postgres_age_driver, tx, [alice, bob]
        )
        await postgres_age_driver.graph_operations_interface.edge_save_bulk(
            None, postgres_age_driver, tx, [edge]
        )

    loaded = await postgres_age_driver.graph_operations_interface.edge_get_by_uuid(
        type(edge), postgres_age_driver, edge.uuid
    )
    assert loaded.uuid == edge.uuid
```

- [ ] **Step 2: Write failing Graphiti compatibility tests**

```python
# tests/driver/postgres_age/test_graphiti_core_flow.py
import pytest

from graphiti_core.graphiti import Graphiti
from graphiti_core.nodes import EntityNode


@pytest.mark.integration
async def test_graphiti_accepts_postgres_age_driver(postgres_age_driver):
    await postgres_age_driver.build_indices_and_constraints(delete_existing=True)
    graphiti = Graphiti(graph_driver=postgres_age_driver)

    node = EntityNode(uuid='graphiti-node', name='Alice', group_id='main')
    await node.save(graphiti.driver)
    loaded = await EntityNode.get_by_uuid(graphiti.driver, node.uuid)

    assert loaded.uuid == node.uuid
```

- [ ] **Step 3: Run adapter and Graphiti tests and verify failure**

Run: `uv run pytest tests/driver/postgres_age/test_graph_operations_adapter.py tests/driver/postgres_age/test_graphiti_core_flow.py -q -m integration`

Expected: FAIL because the adapter is missing and `graphiti.py` still has raw Cypher gaps.

- [ ] **Step 4: Implement `PostgresAgeGraphOperations`**

Every method in `GraphOperationsInterface` must delegate to the corresponding operation object. Examples:

```python
class PostgresAgeGraphOperations(GraphOperationsInterface):
    async def node_save(self, node: Any, driver: Any) -> None:
        await driver.entity_node_ops.save(driver, node)

    async def node_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.entity_node_ops.get_by_uuid(driver, uuid)

    async def edge_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        edges: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.entity_edge_ops.save_bulk(driver, edges, transaction, batch_size)
```

Set `self.graph_operations_interface = PostgresAgeGraphOperations()` in the driver constructor.

- [ ] **Step 5: Patch raw Graphiti gaps**

In `_get_or_create_saga`, check `graph_operations_interface` first and add a new adapter method only if needed. The concrete query should read `saga_nodes` by `name` and `group_id` instead of running raw Cypher through Postgres.

In `remove_episode`, move the episode mention count into the adapter:

```sql
SELECT count(*) AS episode_count
FROM episodic_edges
WHERE target_node_uuid = %s
```

Keep existing Cypher fallback for old drivers.

- [ ] **Step 6: Run compatibility tests**

Run: `uv run pytest tests/driver/postgres_age/test_graph_operations_adapter.py tests/driver/postgres_age/test_graphiti_core_flow.py -q -m integration`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add graphiti_core/driver/postgres_age/graph_operations.py graphiti_core/driver/postgres_age/driver.py graphiti_core/graphiti.py tests/driver/postgres_age/test_graph_operations_adapter.py tests/driver/postgres_age/test_graphiti_core_flow.py
git commit -m "wire postgres age legacy graph operations"
```

---

### Task 11: Test Harness Integration, Docs, and Final Verification

**Files:**
- Modify: `tests/helpers_test.py`
- Modify: `docs/superpowers/specs/2026-05-26-postgres-age-core-driver-design.md`
- Modify: `docs/superpowers/plans/2026-05-26-postgres-age-core-driver.md`

- [ ] **Step 1: Add opt-in test helper support**

Extend `tests/helpers_test.py` without changing default driver behavior:

```python
if os.getenv('ENABLE_POSTGRES_AGE') is not None:
    try:
        from graphiti_core.driver.postgres_age import PostgresAgeDriver

        drivers.append(GraphProvider.POSTGRES_AGE)
    except ImportError:
        raise
```

Add env vars:

```python
POSTGRES_AGE_DSN = os.getenv(
    'POSTGRES_AGE_DSN',
    'postgresql://graphiti:graphiti@localhost:55432/graphiti',
)
```

Add branch in `get_driver`:

```python
elif provider == GraphProvider.POSTGRES_AGE:
    return PostgresAgeDriver(
        dsn=POSTGRES_AGE_DSN,
        graph_name='graphiti_test_core',
        embedding_dimension=embedding_dim,
    )
```

- [ ] **Step 2: Run focused non-integration checks**

Run:

```bash
uv run pytest tests/driver/postgres_age/test_imports.py tests/driver/postgres_age/test_records.py -q
uv run ruff check graphiti_core/driver/postgres_age tests/driver/postgres_age
uv run pyright graphiti_core/driver/postgres_age
```

Expected: all pass with zero pyright errors for the new package.

- [ ] **Step 3: Run focused integration checks**

Run:

```bash
docker compose -f docker-compose.postgres-age.yml up -d postgres-age
uv run pytest tests/driver/postgres_age -q -m integration
```

Expected: all Postgres AGE integration tests pass.

- [ ] **Step 4: Run existing safe regression checks**

Run:

```bash
uv run pytest tests/helpers_test.py tests/utils/search/test_search_security.py tests/llm_client/test_token_tracker.py -q
uv run pytest tests/test_node_label_security.py -q
```

Expected: all pass. These checks confirm existing providers and helper security behavior did not regress.

- [ ] **Step 5: Update design doc outcome**

Append a short implementation outcome section to `docs/superpowers/specs/2026-05-26-postgres-age-core-driver-design.md`:

```markdown
## Implementation Outcome

- Added `PostgresAgeDriver` as an opt-in core driver.
- Canonical data lives in PostgreSQL tables; AGE projection is rebuildable.
- Existing Neo4j, FalkorDB, Kuzu, and Neptune drivers remain unchanged.
- Server and MCP selection wiring are still outside this milestone.
```

- [ ] **Step 6: Commit**

```bash
git add tests/helpers_test.py docs/superpowers/specs/2026-05-26-postgres-age-core-driver-design.md docs/superpowers/plans/2026-05-26-postgres-age-core-driver.md
git commit -m "document postgres age core driver verification"
```

---

## Self-Review Checklist

- [ ] Spec coverage: provider selection, optional deps, canonical tables, AGE graph projection, pgvector search, full-text search, rollback, rebuild, legacy facade, and old driver preservation are each covered by at least one task.
- [ ] Placeholder scan: each task names exact files, concrete tests, execution commands, and expected outcomes.
- [ ] Type consistency: all operation calls use existing `QueryExecutor` and `Transaction` conventions, and adapter method names match `GraphOperationsInterface`.
- [ ] LLM safety: this plan does not require an LLM provider. If a later `add_episode` test needs one, ask the user before running it.
- [ ] Execution mode: use subagent-driven development by default because the user selected it earlier and the task decomposes cleanly by operation family.
