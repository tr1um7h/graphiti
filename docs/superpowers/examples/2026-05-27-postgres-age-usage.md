# PostgresAgeDriver Usage Example

## Overview

`PostgresAgeDriver` is a Graphiti database driver that uses PostgreSQL as the canonical store with Apache AGE as a rebuildable graph projection, and pgvector for similarity search.

## Quick Start

### 1. Start PostgreSQL with AGE and pgvector

```bash
docker compose -f docker-compose.postgres-age.yml up -d postgres-age
```

### 2. Install the postgres-age extra

```bash
uv sync --extra postgres-age
# or
pip install graphiti-core[postgres-age]
```

### 3. Use the driver with Graphiti

```python
import os
from graphiti_core.driver.postgres_age import PostgresAgeDriver
from graphiti_core.graphiti import Graphiti
from graphiti_core.llm_client.anthropic_client import AnthropicClient
from graphiti_core.llm_client.config import LLMConfig

# Configure the driver
driver = PostgresAgeDriver(
    dsn=os.getenv('POSTGRES_AGE_DSN', 'postgresql://graphiti:graphiti@localhost:55432/graphiti'),
    graph_name='my_graph',           # AGE graph name
    embedding_dimension=384,         # match your embedder
)

# Create Graphiti instance
graphiti = Graphiti(
    graph_driver=driver,
    llm_client=AnthropicClient(LLMConfig(model='claude-sonnet-4-5-latest')),
    embedder=your_embedder,
)

# Build indices and start using
await driver.build_indices_and_constraints()

result = await graphiti.add_episode(
    name='My Episode',
    episode_body='Alice talked to Bob about the project.',
    source_description='meeting notes',
    reference_time=datetime.now(timezone.utc),
    group_id='my_group',
)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_AGE_DSN` | `postgresql://graphiti:graphiti@localhost:55432/graphiti` | PostgreSQL connection string |
| `ENABLE_POSTGRES_AGE` | (not set) | Set to enable PostgresAgeDriver in test helpers |

## Architecture

PostgresAgeDriver stores data in two layers:

1. **Canonical PostgreSQL tables** - The source of truth for all nodes, edges, embeddings, timestamps, and attributes.

2. **Apache AGE graph projection** - A rebuildable graph used for graph traversal queries (BFS, path finding).

Search operations (full-text, vector similarity) query canonical tables directly.

## Schema

The driver creates these canonical tables:

**Node tables:**
- `entity_nodes` - Entity nodes with embeddings
- `episodic_nodes` - Episode nodes
- `community_nodes` - Community nodes
- `saga_nodes` - Saga nodes

**Edge tables:**
- `entity_edges` - Entity-to-entity edges (RELATES_TO)
- `episodic_edges` - Episode-to-entity edges (MENTIONS)
- `community_edges` - Community-to-entity edges (HAS_MEMBER)
- `has_episode_edges` - Saga-to-episode edges (HAS_EPISODE)
- `next_episode_edges` - Episode-to-episode edges (NEXT_EPISODE)

## Testing with the PostgresAgeDriver

Enable the driver in test helpers:

```python
# In your test environment
import os
os.environ['ENABLE_POSTGRES_AGE'] = '1'
os.environ['POSTGRES_AGE_DSN'] = 'postgresql://graphiti:graphiti@localhost:55432/graphiti'

# Now drivers list will include POSTGRES_AGE
from tests.helpers_test import drivers, get_driver
driver = get_driver('postgres_age')
```

## Running Integration Tests

```bash
# With Postgres AGE enabled
export POSTGRES_AGE_DSN="postgresql://graphiti:graphiti@localhost:55432/graphiti"
export ENABLE_POSTGRES_AGE=1

# Run Postgres AGE integration tests
uv run pytest tests/driver/postgres_age/ -v -m integration
```

## Rebuilding the AGE Graph Projection

If the AGE graph gets out of sync, you can rebuild it:

```python
await driver.rebuild_projection()
```

To drop and recreate the AGE graph:

```python
await driver.drop_age_graph()
await driver.build_indices_and_constraints(delete_existing=True)
```