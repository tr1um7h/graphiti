# PostgreSQL AGE + pgvector Backend Design

## Status

Approved direction, pending implementation plan.

## Goal

Add a new optional Graphiti backend that uses ordinary PostgreSQL tables as the
canonical store, pgvector and PostgreSQL full-text search for retrieval, and
Apache AGE as a rebuildable graph traversal projection. Existing Neo4j,
FalkorDB, Kuzu, and Neptune drivers remain available and unchanged.

## Non-Goals

- Do not remove or rewrite existing database drivers.
- Do not make Apache AGE the canonical store.
- Do not rely on AGE `agtype` fields for vector or full-text indexing.
- Do not implement the full backend before a small spike validates AGE,
  pgvector, transaction, Docker, and result parsing behavior.

## Chosen Architecture

The backend has two PostgreSQL-backed layers:

1. Canonical relational tables.
   These tables are the source of truth for all Graphiti nodes, edges, metadata,
   attributes, embeddings, timestamps, and group partitions.

2. Apache AGE graph projection.
   The AGE graph stores the graph shape and a minimal set of traversal
   properties. It is updated in the same PostgreSQL transaction as canonical
   writes, but it can be dropped and rebuilt from canonical tables.

Search and CRUD read from canonical tables. Graph traversal reads from AGE and
then hydrates final UUIDs from canonical tables.

```text
Graphiti operation
  -> PostgresAgeDriver transaction
    -> write canonical table
    -> write AGE projection
    -> commit

CRUD/list/load embeddings
  -> canonical tables

Full-text/vector/hybrid search
  -> canonical tables + FTS + pgvector

BFS/path traversal
  -> AGE projection
  -> canonical hydration by UUID
```

## New Provider

Add a new provider without changing old providers:

- `GraphProvider.POSTGRES_AGE = 'postgres_age'`
- `graphiti_core/driver/postgres_age_driver.py`
- `graphiti_core/driver/postgres_age/operations/*`
- optional dependency group such as
  `postgres-age = ["psycopg[binary,pool]>=3", "pgvector>=0.3"]`

The driver should expose:

- async PostgreSQL connection pool
- `execute_query()` compatibility with the existing driver contract
- `execute_sql()` for ordinary SQL
- `execute_cypher()` for AGE `cypher(...)` calls
- real PostgreSQL transactions
- schema/bootstrap helpers
- `rebuild_age_projection(group_ids: list[str] | None = None)`

## Canonical Schema

Object tables:

- `entity_nodes`
  - `uuid text primary key`
  - `group_id text not null`
  - `name text not null`
  - `summary text not null`
  - `labels text[] not null default '{}'`
  - `attributes jsonb not null default '{}'`
  - `name_embedding vector`
  - `created_at timestamptz not null`

- `episodic_nodes`
  - `uuid text primary key`
  - `group_id text not null`
  - `name text not null`
  - `source text not null`
  - `source_description text not null`
  - `content text not null`
  - `entity_edges text[] not null default '{}'`
  - `episode_metadata jsonb`
  - `created_at timestamptz not null`
  - `valid_at timestamptz not null`

- `community_nodes`
  - `uuid text primary key`
  - `group_id text not null`
  - `name text not null`
  - `summary text not null`
  - `name_embedding vector`
  - `created_at timestamptz not null`

- `saga_nodes`
  - `uuid text primary key`
  - `group_id text not null`
  - `name text not null`
  - `summary text`
  - `first_episode_uuid text`
  - `last_episode_uuid text`
  - `last_summarized_at timestamptz`
  - `created_at timestamptz not null`

Edge tables:

- `entity_edges`
  - `uuid text primary key`
  - `group_id text not null`
  - `source_node_uuid text not null references entity_nodes(uuid)`
  - `target_node_uuid text not null references entity_nodes(uuid)`
  - `name text not null`
  - `fact text not null`
  - `fact_embedding vector`
  - `episodes text[] not null default '{}'`
  - `attributes jsonb not null default '{}'`
  - `created_at timestamptz not null`
  - `expired_at timestamptz`
  - `valid_at timestamptz`
  - `invalid_at timestamptz`
  - `reference_time timestamptz`

- `episodic_edges`
  - `uuid text primary key`
  - `group_id text not null`
  - `source_node_uuid text not null references episodic_nodes(uuid)`
  - `target_node_uuid text not null references entity_nodes(uuid)`
  - `created_at timestamptz not null`

- `community_edges`
  - `uuid text primary key`
  - `group_id text not null`
  - `source_node_uuid text not null references community_nodes(uuid)`
  - `target_node_uuid text not null`
  - `target_node_kind text not null`
  - `created_at timestamptz not null`

- `has_episode_edges`
  - `uuid text primary key`
  - `group_id text not null`
  - `source_node_uuid text not null references saga_nodes(uuid)`
  - `target_node_uuid text not null references episodic_nodes(uuid)`
  - `created_at timestamptz not null`

- `next_episode_edges`
  - `uuid text primary key`
  - `group_id text not null`
  - `source_node_uuid text not null references episodic_nodes(uuid)`
  - `target_node_uuid text not null references episodic_nodes(uuid)`
  - `created_at timestamptz not null`

Indexes:

- B-tree on `uuid`, `group_id`, time fields, and source/target UUID columns.
- GIN on `labels` and `attributes`.
- pgvector HNSW or IVFFlat on `name_embedding` and `fact_embedding`.
- PostgreSQL full-text GIN indexes on generated or expression `tsvector`
  fields for entity name/summary, edge name/fact, episode content/source fields,
  and community name/summary.

The first implementation should prefer HNSW for pgvector because it does not
require a separate training phase.

## AGE Projection

AGE graph nodes contain only fields needed for traversal and simple filtering:

- `uuid`
- `group_id`
- `node_kind`
- `name` where useful
- `labels` for entity nodes
- `source` and `valid_at` for episodic nodes

AGE relationships contain:

- `uuid`
- `group_id`
- `edge_kind`
- `created_at`

Projection labels mirror Graphiti concepts:

- Nodes: `Entity`, `Episodic`, `Community`, `Saga`
- Edges: `RELATES_TO`, `MENTIONS`, `HAS_MEMBER`, `HAS_EPISODE`,
  `NEXT_EPISODE`

Projection write order:

1. Upsert canonical row.
2. Upsert AGE node or relationship.
3. Commit both in the same PostgreSQL transaction.

Delete order:

1. Delete AGE projection edge/node.
2. Delete canonical row.
3. Commit.

This keeps AGE rebuildable while still giving normal writes atomic behavior.

## Rebuild Strategy

Add `rebuild_age_projection(group_ids: list[str] | None = None)`.

The method should:

1. Clear the selected AGE projection scope.
2. Read canonical nodes in batches.
3. Recreate AGE nodes.
4. Read canonical edges in batches.
5. Recreate AGE relationships.
6. Compare canonical and AGE counts for the selected scope.

The first version should implement rebuild from Python driver code. Database
triggers are intentionally out of scope until the Python implementation is
stable and well-tested.

## CRUD Behavior

All CRUD operations should use canonical tables for reads.

- `save`: upsert canonical, then AGE projection.
- `save_bulk`: batch write canonical data, then batch sync projection.
- `get_by_uuid`, `get_by_uuids`, `get_by_group_ids`: read canonical tables.
- `load_embeddings`: read canonical vector columns.
- `delete`: remove projection, then canonical row.
- `clear_data`: clear projection and canonical data in one transaction.

This keeps PostgreSQL result parsing ordinary and prevents AGE `agtype` from
leaking into `record_parsers`.

## Search Behavior

Search should be implemented through `driver.search_ops` so existing providers
do not need behavior changes.

Full-text search:

- Entity: `entity_nodes.name`, `entity_nodes.summary`, optionally `group_id`
- Edge: `entity_edges.name`, `entity_edges.fact`, optionally `group_id`
- Episode: `episodic_nodes.content`, `source`, `source_description`
- Community: `community_nodes.name`, `community_nodes.summary`

Vector search:

- Entity: `entity_nodes.name_embedding`
- Edge: `entity_edges.fact_embedding`
- Community: `community_nodes.name_embedding`

BFS and path traversal:

- Run AGE traversal query.
- Return UUIDs.
- Hydrate full objects from canonical tables.

Hybrid search should reuse existing high-level orchestration where possible.
The new backend supplies provider-specific retrieval primitives.

## Compatibility Plan

Existing drivers remain in place. The new backend should minimize changes to
shared provider branches by implementing the operations interfaces completely.

Where older model methods still bypass operations and call `driver.provider`
directly, add the smallest compatibility path needed for `POSTGRES_AGE`, or
route the call through the appropriate operations object.

## Spike-First Path

The implementation begins with a focused spike on branch
`codex/postgres-age-pgvector` in an isolated worktree:

1. Bootstrap PostgreSQL with AGE, pgvector, and pg_trgm.
2. Create one canonical entity table and one canonical edge table.
3. Create an AGE graph projection.
4. Implement a small async driver helper for SQL and AGE `cypher(...)`.
5. Save and load one `EntityNode`.
6. Save and load one `EntityEdge`.
7. Run one pgvector similarity query.
8. Run one AGE BFS query.
9. Verify transaction rollback prevents partial canonical/projection writes.
10. Document which helper APIs and query patterns should be kept for the full
    implementation.

Only after the spike passes should the full driver implementation plan be
written.

## Test Strategy

Baseline status before design:

- `make install` passed in the isolated worktree.
- Full `make test` was not a clean baseline in this environment. It ran for
  several minutes, emitted multiple errors, and had to be stopped.
- Focused smoke tests passed:
  `uv run pytest tests/helpers_test.py tests/utils/search/test_search_security.py tests/llm_client/test_token_tracker.py -q`
  produced `25 passed, 1 warning`.

Spike tests:

- Extension/bootstrap test for AGE, pgvector, and pg_trgm.
- SQL helper test for canonical table writes.
- AGE helper test for projection writes and reads.
- Transaction rollback test.
- pgvector similarity smoke test.
- AGE BFS smoke test.

Full backend tests:

- Reuse node and edge integration contract tests.
- Add search contract tests for full-text, vector, hybrid, and BFS behavior.
- Add rebuild projection tests.
- Add MCP/server configuration tests.
- Add Docker compose coverage for the PostgreSQL AGE + pgvector service.

## Open Questions

- Which PostgreSQL image should be used for CI: a custom image with AGE and
  pgvector preinstalled, or an existing community image?
- Which embedding dimension should schema bootstrap assume when creating vector
  columns, and should it be configurable per driver instance?
- How strict should AGE projection consistency checks be after each bulk write:
  always count, debug-only count, or explicit validation command only?

## Approved Decisions

- Use ordinary PostgreSQL tables as canonical storage.
- Use AGE only as a rebuildable graph projection.
- Use pgvector and PostgreSQL full-text search on canonical tables.
- Keep old drivers.
- Develop on an isolated branch/worktree.
- Start with the spike-first path before full backend implementation.

## Spike Outcome

The spike validated that PostgreSQL canonical tables, pgvector similarity search,
PostgreSQL full-text search, and AGE traversal can run in one PostgreSQL service.
The full backend should keep AGE as a projection layer and use canonical tables
for CRUD and retrieval.

Validated behaviors:

- Bootstrap creates AGE, pgvector, pg_trgm, canonical node and edge tables,
  generated `tsvector` columns, vector indexes, and an AGE graph.
- Entity and edge writes upsert canonical PostgreSQL rows and then refresh AGE
  projection data in the same transaction.
- AGE BFS traverses the projection and returns UUIDs that can be hydrated from
  canonical tables.
- pgvector and full-text search query canonical tables directly and still work
  after the AGE graph projection is dropped.
- A projection failure rolls back the canonical write when both actions share
  the same transaction body.

Implementation notes for the full backend:

- Replace spike-only Cypher literal construction with a hardened query builder
  or prepared-statement parameter strategy wherever AGE allows it.
- Make vector dimensions configurable instead of using the spike's `vector(3)`.
- Keep integration tests marked as `integration`; shared spike database tests
  used a PostgreSQL advisory lock to avoid xdist races on fixed canonical table
  names.
- Keep projection refresh idempotent: edge endpoint updates must delete stale AGE
  relationships for the same UUID before creating the current relationship.
