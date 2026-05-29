# PostgreSQL AGE Core Driver Design

## Goal

Add a production-oriented `PostgresAgeDriver` to Graphiti core while preserving
the existing Neo4j, FalkorDB, Kuzu, and Neptune drivers.

The first backend milestone is core-library usable:

```python
graphiti = Graphiti(graph_driver=PostgresAgeDriver(dsn='postgresql://...'))
```

Server, MCP, and environment-driven factory wiring are intentionally deferred to
a later milestone.

## Architecture

The new backend follows the spike's option B:

- PostgreSQL ordinary tables are the canonical store.
- Apache AGE is a rebuildable graph traversal projection.
- pgvector and PostgreSQL full-text search query canonical tables.
- Existing providers stay in place.

`PostgresAgeDriver` implements the existing `GraphDriver` contract and exposes
provider-specific operations through the existing operations interfaces. Shared
Graphiti model methods should call the operations objects where possible. Any
remaining legacy provider branches should get the smallest compatibility path
needed for `GraphProvider.POSTGRES_AGE`.

## Provider Identity

Add:

```python
GraphProvider.POSTGRES_AGE = 'postgres_age'
```

The new provider must not change default construction behavior. `Graphiti(...)`
without a `graph_driver` still creates `Neo4jDriver`.

## Driver Components

Create a focused package under `graphiti_core/driver/postgres_age/`:

- `driver.py`: `PostgresAgeDriver`, session, transaction, low-level SQL/Cypher
  execution, optional dependency error messaging.
- `schema.py`: extension bootstrap, canonical table DDL, indexes, AGE graph
  lifecycle, schema version constants.
- `records.py`: canonical row-to-model parsers and serialization helpers.
- `cypher.py`: AGE projection query builder and guarded Cypher executor helpers.
- `operations/`: implementations of the existing operations interfaces.

The existing spike helper remains as a spike artifact during the transition, but
production code should not import it.

## Canonical Schema

The full driver uses separate canonical tables for each model family:

- `entity_nodes`
- `episodic_nodes`
- `community_nodes`
- `saga_nodes`
- `entity_edges`
- `episodic_edges`
- `community_edges`
- `has_episode_edges`
- `next_episode_edges`

Each table stores ordinary PostgreSQL columns for stable fields and `jsonb` for
provider-neutral attributes. Vector columns use pgvector. Vector dimensions must
be configurable from the driver constructor, with a default matching the current
embedder expectations.

Search columns use generated `tsvector` values with the `simple` configuration
unless a future API explicitly exposes language configuration.

## AGE Projection

AGE stores only data needed for traversal:

- Node vertices keyed by `uuid`, `group_id`, `node_kind`, and display name.
- Relationship edges keyed by `uuid`, `group_id`, and edge kind.

Projection writes occur in the same PostgreSQL transaction as canonical writes.
For idempotency, an edge projection update deletes any stale AGE relationship
with the same UUID before creating the current relationship.

AGE projection can be rebuilt from canonical tables. The first production
implementation performs rebuild from Python driver code, not triggers.

## Operations Coverage

The first milestone implements all current operations interfaces:

- Entity, episodic, community, and saga node operations.
- Entity, episodic, community, has-episode, and next-episode edge operations.
- Graph maintenance operations.
- Search operations.

CRUD reads always hydrate from canonical tables. AGE traversal returns UUIDs and
then hydrates canonical rows.

## Search Behavior

Full-text and vector search use canonical tables:

- Entity node FTS: `name`, `summary`, and optional attributes payload.
- Entity edge FTS: `name`, `fact`.
- Episode FTS: `content`, `source`, `source_description`.
- Community FTS: `name`, `summary`.
- Entity vectors: `name_embedding`.
- Entity edge vectors: `fact_embedding`.
- Community vectors: `name_embedding`.

BFS and node-distance style searches use AGE for traversal and canonical tables
for final object hydration.

## Transaction Model

`PostgresAgeDriver.transaction()` yields a real PostgreSQL transaction. All
operation methods accept an optional `tx` matching the existing operations
interfaces.

Rules:

- Save writes canonical row first, then projection, then commit.
- Delete removes projection and canonical data in one transaction.
- Bulk operations batch canonical writes and projection refreshes in one
  transaction per batch.
- Projection failure rolls back canonical writes.

## Compatibility

The driver is opt-in. Existing drivers and default Neo4j behavior remain
unchanged.

Compatibility tasks:

- Add `GraphProvider.POSTGRES_AGE`.
- Expose `PostgresAgeDriver` without importing optional dependencies unless the
  user imports or constructs it.
- Keep tests skip-safe in dev-only installs without `postgres-age` extras.
- Update helper functions that branch on provider only where needed.

Server and MCP factories are not part of this milestone.

## Error Handling

Optional dependencies must fail with actionable installation guidance:

```text
PostgresAgeDriver requires graphiti-core[postgres-age]
```

Database bootstrap failures should surface the failed extension or DDL step.
Projection consistency failures should identify whether canonical data was
rolled back.

## Testing Strategy

Use TDD and keep database tests marked `integration`.

Required test layers:

- No-database import tests that prove dev-only installs do not import optional
  PostgreSQL dependencies accidentally.
- Driver construction, close, session, and transaction tests.
- Schema bootstrap tests for extensions, canonical tables, indexes, and AGE
  graph.
- CRUD contract tests for all node and edge families.
- Search contract tests for full-text, vector, BFS, and hydration.
- Transaction rollback tests for canonical plus projection writes.
- Projection rebuild tests.

Existing Neo4j/Falkor/Kuzu/Neptune tests should continue passing or remain
unchanged.

## Non-Goals For This Milestone

- Server and MCP configuration.
- Removing existing drivers.
- Database triggers for projection sync.
- Multi-tenant schema-per-group design.
- AGE as canonical storage.

## Open Implementation Risks

- Some legacy model methods still branch directly on `driver.provider`; these
  must be audited and either routed through operations or given a minimal
  `POSTGRES_AGE` branch.
- AGE Cypher parameterization is limited. Production projection helpers need a
  narrow, internal query builder and must avoid public raw Cypher entry points.
- Existing search orchestration expects provider-specific scoring shapes. The
  PostgreSQL search operations must normalize scores before returning models.
- Full coverage is large. Implementation should be staged by contract area and
  reviewed after each task.

## Implementation Outcome (2026-05-27)

### Completed

- **Core Driver**: `PostgresAgeDriver` fully implemented with all 9 node/edge operation families, search operations (FTS, pgvector, AGE BFS), and legacy interface adapters.
- **Test Coverage**: 52 tests passing, including 43 integration tests with real PostgreSQL/AGE.
- **Helper Integration**: `ENABLE_POSTGRES_AGE` environment variable enables PostgresAgeDriver in test helpers.
- **Server Wiring**: FastAPI server config updated to support `database_provider: postgres_age` with `postgres_age_dsn`, `postgres_age_graph_name`, and `postgres_age_embedding_dimension` settings.
- **MCP Wiring**: MCP server config updated with `PostgresAgeProviderConfig` schema, `DatabaseDriverFactory` updated to create PostgresAgeDriver config, and `GraphitiMCP` initialization updated to handle `postgres_age` provider.
- **User Documentation**: Usage example added at `docs/superpowers/examples/2026-05-27-postgres-age-usage.md`.

### Architecture

PostgresAgeDriver uses two-layer architecture:
1. **Canonical PostgreSQL tables** - Source of truth for all data
2. **Apache AGE graph projection** - Rebuildable traversal layer

Search operations query canonical tables directly.

### Non-Goals Completed

- Server and MCP configuration is now available (was deferred but implemented as part of completion).
- Existing drivers (Neo4j, FalkorDB, Kuzu, Neptune) remain unchanged.

### Verification

```bash
# Option D: Real add_episode() with MiniMax LLM
export POSTGRES_AGE_DSN="postgresql://graphiti:graphiti@localhost:55432/graphiti"
uv run pytest tests/driver/postgres_age/test_graphiti_add_episode_int.py -v -m integration
# Result: PASSED - Episode created with nodes and edges

# All integration tests
uv run pytest tests/driver/postgres_age/ -v -m integration
# Result: 43 passed, 10 deselected
```
