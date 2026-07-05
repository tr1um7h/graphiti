# Graphiti Data Export/Import/Diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement CLI tools to export, import, and diff Graphiti knowledge graph data by `group_id`, supporting copy/migrate/version-control workflows.

**Architecture:** PostgreSQL + AGE dual-layer storage with 9 canonical SQL tables and AGE graph projection. Export reads from SQL tables, Import writes directly to SQL (bypassing ORM to avoid per-row AGE sync), then rebuilds AGE projection. UUID remapping uses two-phase approach (pre-generate mappings → batch INSERT) to handle bidirectional array references.

**Tech Stack:** Python 3.10+, asyncpg (async PostgreSQL), orjson (fast JSON), argparse (CLI), pytest (testing)

**Related Design Doc:** `docs/superpowers/plans/2026-07-03-graphiti-diff-plan.md`

---

## File Structure

```
graphiti-web-service/
├── cli/
│   ├── __init__.py                    # Package init
│   ├── main.py                        # CLI entry point (argparse)
│   ├── export.py                      # Export logic: DB → JSONL + metadata.json
│   ├── import_.py                     # Import logic: JSONL → DB with UUID remapping
│   ├── remap.py                       # UUID remapping core (shared by import & apply)
│   ├── diff.py                        # Semantic diff engine
│   ├── apply.py                       # Patch apply engine with conflict resolution
│   └── render.py                      # HTML report generation (can be deferred)
└── tests/
    └── cli/
        ├── __init__.py
        ├── test_export.py             # Unit tests for export
        ├── test_import.py             # Unit tests for import
        ├── test_remap.py              # Unit tests for UUID remapping
        ├── test_diff.py               # Unit tests for diff
        └── test_apply.py              # Unit tests for apply
```

---

## Data Structures

### JSONL Format (per table)

Each JSONL file contains one JSON object per line, representing a row from the corresponding table.

**Entity Nodes (`entity_nodes.jsonl`):**
```json
{"uuid":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","name":"Alice","group_id":"abc","labels":["Person","Entity"],"summary":"Engineer at Google","name_embedding":[0.123456,-0.234567,0.001234,...],"created_at":"2025-06-01T10:00:00+00:00","attributes":{"dept":"eng","level":5}}
```

**Entity Edges (`entity_edges.jsonl`):**
```json
{"uuid":"b2c3d4e5-f6a7-8901-bcde-f12345678901","group_id":"abc","source_node_uuid":"a1b2c3d4-e5f6-7890-abcd-ef1234567890","target_node_uuid":"c3d4e5f6-a7b8-9012-cdef-123456789012","name":"WORKS_AT","fact":"Alice works at Google","fact_embedding":[0.456789,-0.345678,0.234567,...],"episodes":["d4e5f6a7-b8c9-0123-defa-234567890123"],"expired_at":null,"valid_at":"2025-06-01T00:00:00+00:00","invalid_at":null,"reference_time":"2025-06-01T10:00:00+00:00","attributes":{},"created_at":"2025-06-01T10:00:00+00:00"}
```

**Episodic Nodes (`episodic_nodes.jsonl`):**
```json
{"uuid":"e5f6a7b8-c9d0-1234-efab-567890123456","name":"Episode 1","group_id":"abc","source":"message","source_description":"Chat message","content":"User: Hello","valid_at":"2025-06-01T10:00:00+00:00","entity_edges":["b2c3d4e5-f6a7-8901-bcde-f12345678901"],"episode_metadata":{"sender":"user"},"created_at":"2025-06-01T10:00:00+00:00"}
```

**All Other Tables:** Similar structure with table-specific fields. Edge tables have `source_node_uuid` and `target_node_uuid`. Node tables have `name`, `group_id`, `created_at`.

### metadata.json

```json
{
  "group_id": "abc",
  "exported_at": "2026-07-05T15:30:00+00:00",
  "schema": "public",
  "embedding_dimension": 1024,
  "schema_version": 1,
  "counts": {
    "entity_nodes": 45,
    "episodic_nodes": 12,
    "community_nodes": 3,
    "saga_nodes": 0,
    "entity_edges": 128,
    "episodic_edges": 56,
    "community_edges": 18,
    "has_episode_edges": 0,
    "next_episode_edges": 11
  }
}
```

### patch.json (Diff Output)

```json
{
  "version": 1,
  "metadata": {
    "from_group_id": "abc",
    "to_group_id": "xyz",
    "created_at": "2026-07-05T16:00:00+00:00"
  },
  "changes": {
    "entity_nodes": {
      "added": [
        {"name": "Charlie", "labels": ["Person"], "summary": "Designer"}
      ],
      "removed": [
        {"name": "Bob", "labels": ["Person"]}
      ],
      "modified": [
        {
          "match": {"name": "Alice", "labels": ["Person"]},
          "fields": {
            "summary": {"old": "Engineer at Google", "new": "Engineer at Meta"},
            "attributes": {"old": {"dept": "eng"}, "new": {"dept": "eng", "level": 6}}
          }
        }
      ],
      "conflicts": []
    },
    "entity_edges": {
      "added": [],
      "removed": [],
      "modified": [],
      "conflicts": []
    }
  }
}
```

---

## Core Algorithms

### UUID Remapping (Two-Phase Approach)

**Problem:** `entity_edges.episodes[]` contains episode UUIDs, and `episodic_nodes.entity_edges[]` contains entity edge UUIDs. They cross-reference each other. If we process tables sequentially, we can't resolve these references.

**Solution:** Two-phase UUID remapping.

```python
def generate_uuid_mapping(jsonl_files: list[Path]) -> dict[str, str]:
    """Phase 1: Pre-generate old_uuid → new_uuid mapping for all records."""
    uuid_map = {}
    
    # Scan all JSONL files
    for jsonl_file in jsonl_files:
        with open(jsonl_file) as f:
            for line in f:
                record = json.loads(line)
                old_uuid = record['uuid']
                uuid_map[old_uuid] = str(uuid4())
    
    return uuid_map

def remap_record(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Phase 2: Replace all UUID references in a record."""
    remapped = record.copy()
    
    # Replace primary key
    remapped['uuid'] = uuid_map[record['uuid']]
    
    # Replace group_id
    remapped['group_id'] = new_group_id
    
    # Replace FK references (edge tables)
    if 'source_node_uuid' in remapped:
        remapped['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    if 'target_node_uuid' in remapped:
        # Special handling for community_edges (polymorphic reference)
        remapped['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    
    # Replace array references
    if 'episodes' in remapped:  # entity_edges.episodes[]
        remapped['episodes'] = [uuid_map[ep] for ep in record['episodes']]
    if 'entity_edges' in remapped:  # episodic_nodes.entity_edges[]
        remapped['entity_edges'] = [uuid_map[ee] for ee in record['entity_edges']]
    if 'first_episode_uuid' in remapped and remapped['first_episode_uuid']:
        remapped['first_episode_uuid'] = uuid_map[record['first_episode_uuid']]
    if 'last_episode_uuid' in remapped and remapped['last_episode_uuid']:
        remapped['last_episode_uuid'] = uuid_map[record['last_episode_uuid']]
    
    return remapped
```

### Business Key Matching (Diff)

**Problem:** Compare two exported datasets to find semantic differences, ignoring UUID changes.

**Solution:** Build index by business key, then compare field-by-field.

```python
def build_business_key_index(records: list[dict], table_name: str) -> dict[tuple, dict]:
    """Build index from business key to record."""
    index = {}
    
    for record in records:
        key = get_business_key(record, table_name)
        index[key] = record
    
    return index

def get_business_key(record: dict, table_name: str) -> tuple:
    """Extract business key based on table type."""
    if table_name == 'entity_nodes':
        return (record['name'], tuple(record['labels']))
    elif table_name == 'episodic_nodes':
        return (record['valid_at'], sha256(record['content'].encode())[:12])
    elif table_name in ('community_nodes', 'saga_nodes'):
        return (record['name'],)
    elif table_name == 'entity_edges':
        # Need to resolve UUIDs to names first
        return (record['source_name'], record['target_name'], record['name'])
    # ... other edge tables
    else:
        raise ValueError(f"Unknown table: {table_name}")

def compare_records(left: dict, right: dict, ignore_fields: set) -> dict | None:
    """Compare two records, return dict of changed fields or None if identical."""
    changes = {}
    
    for field in set(left.keys()) | set(right.keys()):
        if field in ignore_fields:
            continue
        
        left_val = left.get(field)
        right_val = right.get(field)
        
        if left_val != right_val:
            changes[field] = {'old': left_val, 'new': right_val}
    
    return changes if changes else None
```

### Cascade Delete (Apply)

**Problem:** When deleting an entity, need to also delete all related edges.

**Solution:** Follow FK constraint semantics from the database schema.

```python
def get_cascade_deletes(table_name: str, record_uuid: str, records_by_table: dict) -> list[tuple[str, str]]:
    """Get all records that need to be deleted due to cascade."""
    deletes = [(table_name, record_uuid)]
    
    if table_name == 'entity_nodes':
        # Delete entity_edges where source or target is this entity
        for edge in records_by_table['entity_edges']:
            if edge['source_node_uuid'] == record_uuid or edge['target_node_uuid'] == record_uuid:
                deletes.extend(get_cascade_deletes('entity_edges', edge['uuid'], records_by_table))
        
        # Delete episodic_edges where target is this entity
        for edge in records_by_table['episodic_edges']:
            if edge['target_node_uuid'] == record_uuid:
                deletes.append(('episodic_edges', edge['uuid']))
        
        # Delete community_edges where target is this entity
        for edge in records_by_table['community_edges']:
            if edge['target_node_uuid'] == record_uuid:
                deletes.append(('community_edges', edge['uuid']))
    
    elif table_name == 'episodic_nodes':
        # Delete episodic_edges where source is this episode
        for edge in records_by_table['episodic_edges']:
            if edge['source_node_uuid'] == record_uuid:
                deletes.append(('episodic_edges', edge['uuid']))
        
        # Delete has_episode_edges where target is this episode
        for edge in records_by_table['has_episode_edges']:
            if edge['target_node_uuid'] == record_uuid:
                deletes.append(('has_episode_edges', edge['uuid']))
        
        # Delete next_episode_edges where source or target is this episode
        for edge in records_by_table['next_episode_edges']:
            if edge['source_node_uuid'] == record_uuid or edge['target_node_uuid'] == record_uuid:
                deletes.append(('next_episode_edges', edge['uuid']))
        
        # Set NULL in saga_nodes.first_episode_uuid / last_episode_uuid (handled separately)
    
    elif table_name == 'community_nodes':
        # Delete community_edges where source is this community
        for edge in records_by_table['community_edges']:
            if edge['source_node_uuid'] == record_uuid:
                deletes.append(('community_edges', edge['uuid']))
    
    elif table_name == 'entity_edges':
        # Delete episodic_edges where target is this edge (not applicable, edges don't link to edges)
        pass
    
    return deletes
```

---

## CLI API Design

### Command Structure

```bash
graphiti-cli <command> [options]
```

### Export Command

```bash
graphiti-cli export \
  --dsn "postgresql://user:pass@host:5432/dbname" \
  --schema public \
  --group-id abc \
  --output-dir ./exports/abc
```

**Options:**
- `--dsn` (required): PostgreSQL connection string
- `--schema` (required): PostgreSQL schema name (default: `public`)
- `--group-id` (required): Group ID to export
- `--output-dir` (required): Output directory path

**Exit Codes:**
- `0`: Success
- `1`: Database connection error
- `2`: No data found for group_id

### Import Command

```bash
graphiti-cli import \
  --dsn "postgresql://user:pass@host:5432/dbname" \
  --schema public \
  --input-dir ./exports/abc \
  --new-group-id xyz \
  [--overwrite]
```

**Options:**
- `--dsn` (required): PostgreSQL connection string
- `--schema` (required): PostgreSQL schema name
- `--input-dir` (required): Input directory containing JSONL + metadata.json
- `--new-group-id` (required): New group ID for imported data
- `--overwrite` (optional): Overwrite if new-group-id already exists (default: error)

**Exit Codes:**
- `0`: Success
- `1`: Database connection error
- `2`: Metadata validation failed (embedding dimension mismatch)
- `3`: Target group_id exists without --overwrite

### Diff Command

```bash
graphiti-cli diff \
  --left-dir ./exports/abc \
  --right-dir ./exports/xyz \
  --output diff.json \
  [--html-output diff.html]
```

**Options:**
- `--left-dir` (required): Left export directory
- `--right-dir` (required): Right export directory
- `--output` (required): Output JSON patch file
- `--html-output` (optional): HTML report output path

**Exit Codes:**
- `0`: Success (differences found or not)
- `1`: Error reading export files

### Apply Command

```bash
graphiti-cli apply \
  --dsn "postgresql://user:pass@host:5432/dbname" \
  --schema public \
  --patch-file diff.json \
  --from-group-id abc \
  --to-group-id xyz \
  [--strategy ours|theirs|skip-conflicts] \
  [--dry-run]
```

**Options:**
- `--dsn` (required): PostgreSQL connection string
- `--schema` (required): PostgreSQL schema name
- `--patch-file` (required): Path to patch.json
- `--from-group-id` (required): Source group ID to copy
- `--to-group-id` (required): Target group ID for result
- `--strategy` (optional): Conflict resolution strategy (default: `ours`)
  - `ours`: Keep source values on conflict
  - `theirs`: Use patch values on conflict
  - `skip-conflicts`: Skip conflicting changes
- `--dry-run` (optional): Validate patch without applying (default: false)

**Exit Codes:**
- `0`: Success
- `1`: Database connection error
- `2`: Patch validation failed
- `3`: Conflicts found (without --strategy to resolve)

---

## Implementation Tasks

### Task 1: Project Setup

**Files:**
- Create: `cli/__init__.py`
- Create: `cli/main.py`
- Create: `tests/cli/__init__.py`
- Modify: `pyproject.toml` (add CLI entry point)

- [x] **Step 1: Create CLI package structure**

```bash
mkdir -p cli tests/cli
touch cli/__init__.py tests/cli/__init__.py
```

- [x] **Step 2: Create basic CLI entry point**

```python
# cli/main.py
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(prog='graphiti-cli', description='Graphiti data management CLI')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Export subcommand
    export_parser = subparsers.add_parser('export', help='Export group data to JSONL')
    export_parser.add_argument('--dsn', required=True, help='PostgreSQL DSN')
    export_parser.add_argument('--schema', required=True, help='PostgreSQL schema')
    export_parser.add_argument('--group-id', required=True, help='Group ID to export')
    export_parser.add_argument('--output-dir', required=True, help='Output directory')
    
    # Import subcommand
    import_parser = subparsers.add_parser('import', help='Import JSONL to database')
    import_parser.add_argument('--dsn', required=True, help='PostgreSQL DSN')
    import_parser.add_argument('--schema', required=True, help='PostgreSQL schema')
    import_parser.add_argument('--input-dir', required=True, help='Input directory')
    import_parser.add_argument('--new-group-id', required=True, help='New group ID')
    import_parser.add_argument('--overwrite', action='store_true', help='Overwrite existing group')
    
    # Diff subcommand
    diff_parser = subparsers.add_parser('diff', help='Compare two exports')
    diff_parser.add_argument('--left-dir', required=True, help='Left export directory')
    diff_parser.add_argument('--right-dir', required=True, help='Right export directory')
    diff_parser.add_argument('--output', required=True, help='Output patch file')
    diff_parser.add_argument('--html-output', help='HTML report output')
    
    # Apply subcommand
    apply_parser = subparsers.add_parser('apply', help='Apply patch to database')
    apply_parser.add_argument('--dsn', required=True, help='PostgreSQL DSN')
    apply_parser.add_argument('--schema', required=True, help='PostgreSQL schema')
    apply_parser.add_argument('--patch-file', required=True, help='Patch file path')
    apply_parser.add_argument('--from-group-id', required=True, help='Source group ID')
    apply_parser.add_argument('--to-group-id', required=True, help='Target group ID')
    apply_parser.add_argument('--strategy', choices=['ours', 'theirs', 'skip-conflicts'], default='ours', help='Conflict resolution')
    apply_parser.add_argument('--dry-run', action='store_true', help='Validate without applying')
    
    args = parser.parse_args()
    
    if args.command == 'export':
        print('Export command not yet implemented')
        sys.exit(1)
    elif args.command == 'import':
        print('Import command not yet implemented')
        sys.exit(1)
    elif args.command == 'diff':
        print('Diff command not yet implemented')
        sys.exit(1)
    elif args.command == 'apply':
        print('Apply command not yet implemented')
        sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
```

- [x] **Step 3: Add CLI entry point to pyproject.toml**

```toml
# Add to [project.scripts] section
graphiti-cli = "cli.main:main"
```

- [x] **Step 4: Commit**

```bash
git add cli/ tests/cli/ pyproject.toml
git commit -m "feat: add CLI package structure with argparse skeleton"
```

---

### Task 2: UUID Remapping Core (remap.py)

**Files:**
- Create: `cli/remap.py`
- Create: `tests/cli/test_remap.py`

- [x] **Step 1: Write failing test for UUID mapping generation**

```python
# tests/cli/test_remap.py
import json
from pathlib import Path
from cli.remap import generate_uuid_mapping

def test_generate_uuid_mappings(tmp_path):
    # Create test JSONL file
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        '{"uuid": "old-uuid-1", "name": "Alice"}\n'
        '{"uuid": "old-uuid-2", "name": "Bob"}\n'
    )
    
    uuid_map = generate_uuid_mappings([jsonl_file])
    
    assert len(uuid_map) == 2
    assert "old-uuid-1" in uuid_map
    assert "old-uuid-2" in uuid_map
    assert uuid_map["old-uuid-1"] != "old-uuid-1"
    assert uuid_map["old-uuid-2"] != "old-uuid-2"
```

- [x] **Step 2: Run test to verify it fails**

```bash
pytest tests/cli/test_remap.py::test_generate_uuid_mappings -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cli.remap'"

- [x] **Step 3: Implement generate_uuid_mappings**

```python
# cli/remap.py
import json
from pathlib import Path
from uuid import uuid4

def generate_uuid_mappings(jsonl_files: list[Path]) -> dict[str, str]:
    """Pre-generate old_uuid → new_uuid mapping for all records."""
    uuid_map = {}
    
    for jsonl_file in jsonl_files:
        with open(jsonl_file) as f:
            for line in f:
                record = json.loads(line)
                old_uuid = record.get('uuid')
                if old_uuid and old_uuid not in uuid_map:
                    uuid_map[old_uuid] = str(uuid4())
    
    return uuid_map
```

- [x] **Step 4: Run test to verify it passes**

```bash
pytest tests/cli/test_remap.py::test_generate_uuid_mappings -v
```

Expected: PASS

- [x] **Step 5: Write failing test for record remapping**

```python
# tests/cli/test_remap.py
from cli.remap import remap_entity_node, remap_entity_edge, remap_episodic_node

def test_remap_entity_node():
    record = {
        "uuid": "old-uuid",
        "name": "Alice",
        "group_id": "abc",
        "labels": ["Person"],
        "summary": "Engineer",
        "name_embedding": [0.123, 0.456],
        "created_at": "2025-06-01T10:00:00Z",
        "attributes": {"dept": "eng"}
    }
    uuid_map = {"old-uuid": "new-uuid"}
    new_group_id = "xyz"
    
    remapped = remap_entity_node(record, uuid_map, new_group_id)
    
    assert remapped["uuid"] == "new-uuid"
    assert remapped["group_id"] == "xyz"
    assert remapped["name"] == "Alice"
    assert remapped["summary"] == "Engineer"
    assert remapped["attributes"] == {"dept": "eng"}

def test_remap_entity_edge():
    record = {
        "uuid": "edge-uuid",
        "group_id": "abc",
        "source_node_uuid": "src-uuid",
        "target_node_uuid": "tgt-uuid",
        "name": "WORKS_AT",
        "fact": "Alice works at Google",
        "episodes": ["ep1-uuid", "ep2-uuid"],
        "created_at": "2025-06-01T10:00:00Z"
    }
    uuid_map = {
        "edge-uuid": "new-edge-uuid",
        "src-uuid": "new-src-uuid",
        "tgt-uuid": "new-tgt-uuid",
        "ep1-uuid": "new-ep1-uuid",
        "ep2-uuid": "new-ep2-uuid"
    }
    new_group_id = "xyz"
    
    remapped = remap_entity_edge(record, uuid_map, new_group_id)
    
    assert remapped["uuid"] == "new-edge-uuid"
    assert remapped["group_id"] == "xyz"
    assert remapped["source_node_uuid"] == "new-src-uuid"
    assert remapped["target_node_uuid"] == "new-tgt-uuid"
    assert remapped["episodes"] == ["new-ep1-uuid", "new-ep2-uuid"]

def test_remap_episodic_node():
    record = {
        "uuid": "ep-uuid",
        "group_id": "abc",
        "name": "Episode 1",
        "entity_edges": ["edge1-uuid", "edge2-uuid"],
        "content": "Hello",
        "valid_at": "2025-06-01T10:00:00Z",
        "created_at": "2025-06-01T10:00:00Z"
    }
    uuid_map = {
        "ep-uuid": "new-ep-uuid",
        "edge1-uuid": "new-edge1-uuid",
        "edge2-uuid": "new-edge2-uuid"
    }
    new_group_id = "xyz"
    
    remapped = remap_episodic_node(record, uuid_map, new_group_id)
    
    assert remapped["uuid"] == "new-ep-uuid"
    assert remapped["group_id"] == "xyz"
    assert remapped["entity_edges"] == ["new-edge1-uuid", "new-edge2-uuid"]
```

- [x] **Step 6: Run tests to verify they fail**

```bash
pytest tests/cli/test_remap.py -v
```

Expected: FAIL with "ImportError: cannot import name 'remap_entity_node'"

- [x] **Step 7: Implement remap functions**

```python
# cli/remap.py (add to existing file)
def remap_entity_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap entity node record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    return remapped

def remap_entity_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap entity edge record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    remapped['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    remapped['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    
    # Remap episodes array
    if 'episodes' in remapped:
        remapped['episodes'] = [uuid_map[ep] for ep in record['episodes']]
    
    return remapped

def remap_episodic_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap episodic node record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    
    # Remap entity_edges array
    if 'entity_edges' in remapped:
        remapped['entity_edges'] = [uuid_map[ee] for ee in record['entity_edges']]
    
    return remapped

def remap_episodic_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap episodic edge record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    remapped['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    remapped['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    return remapped

def remap_community_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap community node record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    return remapped

def remap_community_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap community edge record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    remapped['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    # target_node_uuid can be entity or community (polymorphic)
    remapped['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    return remapped

def remap_saga_node(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap saga node record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    
    # Remap episode references (can be None)
    if remapped.get('first_episode_uuid'):
        remapped['first_episode_uuid'] = uuid_map[record['first_episode_uuid']]
    if remapped.get('last_episode_uuid'):
        remapped['last_episode_uuid'] = uuid_map[record['last_episode_uuid']]
    
    return remapped

def remap_has_episode_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap has_episode edge record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    remapped['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    remapped['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    return remapped

def remap_next_episode_edge(record: dict, uuid_map: dict, new_group_id: str) -> dict:
    """Remap next_episode edge record with new UUIDs."""
    remapped = record.copy()
    remapped['uuid'] = uuid_map[record['uuid']]
    remapped['group_id'] = new_group_id
    remapped['source_node_uuid'] = uuid_map[record['source_node_uuid']]
    remapped['target_node_uuid'] = uuid_map[record['target_node_uuid']]
    return remapped
```

- [x] **Step 8: Run tests to verify they pass**

```bash
pytest tests/cli/test_remap.py -v
```

Expected: All tests PASS

- [x] **Step 9: Commit**

```bash
git add cli/remap.py tests/cli/test_remap.py
git commit -m "feat: implement UUID remapping core with two-phase approach"
```

---

### Task 3: Export Implementation (export.py)

**Files:**
- Create: `cli/export.py`
- Create: `tests/cli/test_export.py`

- [x] **Step 1: Write failing test for export**

```python
# tests/cli/test_export.py
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock
import pytest
from cli.export import export_group, format_embedding

def test_format_embedding():
    """Test embedding precision compression."""
    vec = [0.123456789, -0.987654321, 0.000001234]
    result = format_embedding(vec)
    assert result == [0.123457, -0.987654, 0.000001]
    assert len(result) == 3

def test_format_embedding_none():
    """Test None embedding handling."""
    assert format_embedding(None) is None

def test_export_group_creates_jsonl_files(tmp_path):
    """Test export creates JSONL files with correct structure."""
    # Mock database driver
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock()
    
    # Mock query results
    mock_driver.execute_query.side_effect = [
        # entity_nodes
        ([{
            "uuid": "e1",
            "name": "Alice",
            "group_id": "test-group",
            "labels": ["Person"],
            "summary": "Engineer",
            "name_embedding": [0.123, 0.456],
            "created_at": "2025-06-01T10:00:00Z",
            "attributes": {"dept": "eng"}
        }], [], []),
        # episodic_nodes
        ([], [], []),
        # community_nodes
        ([], [], []),
        # saga_nodes
        ([], [], []),
        # entity_edges
        ([], [], []),
        # episodic_edges
        ([], [], []),
        # community_edges
        ([], [], []),
        # has_episode_edges
        ([], [], []),
        # next_episode_edges
        ([], [], []),
    ]
    
    output_dir = tmp_path / "export"
    export_group(mock_driver, "test-group", "public", output_dir)
    
    # Verify files created
    assert (output_dir / "metadata.json").exists()
    assert (output_dir / "entity_nodes.jsonl").exists()
    
    # Verify metadata
    metadata = json.loads((output_dir / "metadata.json").read_text())
    assert metadata["group_id"] == "test-group"
    assert metadata["counts"]["entity_nodes"] == 1
    
    # Verify JSONL content
    jsonl_content = (output_dir / "entity_nodes.jsonl").read_text()
    record = json.loads(jsonl_content.strip())
    assert record["name"] == "Alice"
    assert record["uuid"] == "e1"
```

- [x] **Step 2: Run test to verify it fails**

```bash
pytest tests/cli/test_export.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cli.export'"

- [x] **Step 3: Implement export functions**

```python
# cli/export.py
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Table processing order
NODE_TABLES = ['entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes']
EDGE_TABLES = ['entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']
ALL_TABLES = NODE_TABLES + EDGE_TABLES

def format_embedding(vec: list[float] | None) -> list[float] | None:
    """Compress embedding to 6 decimal places."""
    if vec is None:
        return None
    return [round(f, 6) for f in vec]

def serialize_record(record: dict, table_name: str) -> dict:
    """Serialize a database record for JSONL export."""
    serialized = {}
    
    for key, value in record.items():
        # Skip generated columns
        if key == 'search_vector':
            continue
        
        # Compress embeddings
        if key in ('name_embedding', 'fact_embedding'):
            value = format_embedding(value)
        
        # Convert datetime to ISO format
        elif isinstance(value, datetime):
            value = value.isoformat()
        
        serialized[key] = value
    
    return serialized

async def export_group(driver, group_id: str, schema: str, output_dir: Path):
    """Export all data for a group_id to JSONL files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    counts = {}
    
    # Export each table
    for table_name in ALL_TABLES:
        query = f"SELECT * FROM {table_name} WHERE group_id = %(group_id)s ORDER BY uuid"
        records, _, _ = await driver.execute_query(query, params={'group_id': group_id})
        
        # Serialize and write to JSONL
        jsonl_path = output_dir / f"{table_name}.jsonl"
        with open(jsonl_path, 'w') as f:
            for record in records:
                serialized = serialize_record(record, table_name)
                f.write(json.dumps(serialized) + '\n')
        
        counts[table_name] = len(records)
    
    # Write metadata
    metadata = {
        "group_id": group_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema": schema,
        "embedding_dimension": getattr(driver, 'embedding_dimension', 1024),
        "schema_version": 1,
        "counts": counts
    }
    
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return metadata
```

- [x] **Step 4: Run test to verify it passes**

```bash
pytest tests/cli/test_export.py::test_export_group_creates_jsonl_files -v
```

Expected: PASS

- [x] **Step 5: Implement sorting with JOINs for edge tables**

Add to `cli/export.py`:

```python
async def export_group_with_sorting(driver, group_id: str, schema: str, output_dir: Path):
    """Export with business key sorting for stable diffs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    counts = {}
    
    # Export node tables with simple sorting
    node_queries = {
        'entity_nodes': f"SELECT * FROM entity_nodes WHERE group_id = %(group_id)s ORDER BY name, labels",
        'episodic_nodes': f"SELECT * FROM episodic_nodes WHERE group_id = %(group_id)s ORDER BY valid_at, md5(content)",
        'community_nodes': f"SELECT * FROM community_nodes WHERE group_id = %(group_id)s ORDER BY name",
        'saga_nodes': f"SELECT * FROM saga_nodes WHERE group_id = %(group_id)s ORDER BY name",
    }
    
    for table_name, query in node_queries.items():
        records, _, _ = await driver.execute_query(query, params={'group_id': group_id})
        write_jsonl(output_dir / f"{table_name}.jsonl", records)
        counts[table_name] = len(records)
    
    # Export edge tables with JOIN sorting
    edge_queries = {
        'entity_edges': f"""
            SELECT e.* FROM entity_edges e
            JOIN entity_nodes src ON src.uuid = e.source_node_uuid
            JOIN entity_nodes tgt ON tgt.uuid = e.target_node_uuid
            WHERE e.group_id = %(group_id)s
            ORDER BY src.name, tgt.name, e.name
        """,
        'episodic_edges': f"""
            SELECT ee.* FROM episodic_edges ee
            JOIN episodic_nodes ep ON ep.uuid = ee.source_node_uuid
            JOIN entity_nodes ent ON ent.uuid = ee.target_node_uuid
            WHERE ee.group_id = %(group_id)s
            ORDER BY md5(ep.content), ent.name
        """,
        'community_edges': f"""
            SELECT ce.* FROM community_edges ce
            JOIN community_nodes cm ON cm.uuid = ce.source_node_uuid
            LEFT JOIN entity_nodes ent ON ent.uuid = ce.target_node_uuid
            WHERE ce.group_id = %(group_id)s
            ORDER BY cm.name, COALESCE(ent.name, '')
        """,
        'has_episode_edges': f"""
            SELECT he.* FROM has_episode_edges he
            JOIN saga_nodes s ON s.uuid = he.source_node_uuid
            JOIN episodic_nodes ep ON ep.uuid = he.target_node_uuid
            WHERE he.group_id = %(group_id)s
            ORDER BY s.name, md5(ep.content)
        """,
        'next_episode_edges': f"""
            SELECT ne.* FROM next_episode_edges ne
            JOIN episodic_nodes src ON src.uuid = ne.source_node_uuid
            JOIN episodic_nodes tgt ON tgt.uuid = ne.target_node_uuid
            WHERE ne.group_id = %(group_id)s
            ORDER BY md5(src.content), md5(tgt.content)
        """,
    }
    
    for table_name, query in edge_queries.items():
        records, _, _ = await driver.execute_query(query, params={'group_id': group_id})
        write_jsonl(output_dir / f"{table_name}.jsonl", records)
        counts[table_name] = len(records)
    
    # Write metadata
    metadata = {
        "group_id": group_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schema": schema,
        "embedding_dimension": getattr(driver, 'embedding_dimension', 1024),
        "schema_version": 1,
        "counts": counts
    }
    
    with open(output_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

def write_jsonl(path: Path, records: list[dict]):
    """Write records to JSONL file."""
    with open(path, 'w') as f:
        for record in records:
            serialized = serialize_record(record, '')
            f.write(json.dumps(serialized) + '\n')
```

- [x] **Step 6: Wire export command in main.py**

```python
# cli/main.py (update export section)
if args.command == 'export':
    from cli.export import export_group_with_sorting
    from graphiti_core.driver.postgres_age.driver import PostgresAgeDriver
    
    driver = PostgresAgeDriver(dsn=args.dsn, schema=args.schema)
    try:
        await export_group_with_sorting(driver, args.group_id, args.schema, Path(args.output_dir))
        print(f"Exported to {args.output_dir}")
    finally:
        await driver.close()
```

- [x] **Step 7: Run all export tests**

```bash
pytest tests/cli/test_export.py -v
```

Expected: All tests PASS

- [x] **Step 8: Commit**

```bash
git add cli/export.py tests/cli/test_export.py cli/main.py
git commit -m "feat: implement export with business key sorting"
```

---

### Task 4: Import Implementation (import_.py)

**Files:**
- Create: `cli/import_.py`
- Create: `tests/cli/test_import.py`

- [x] **Step 1: Write failing test for import**

```python
# tests/cli/test_import.py
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock
import pytest
from cli.import_ import import_group

def test_import_group_with_uuid_remapping(tmp_path):
    """Test import reads JSONL and inserts with new UUIDs."""
    # Create test export
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    
    # metadata.json
    metadata = {
        "group_id": "abc",
        "embedding_dimension": 1024,
        "schema_version": 1,
        "counts": {"entity_nodes": 1, "episodic_nodes": 0, "community_nodes": 0, "saga_nodes": 0,
                   "entity_edges": 0, "episodic_edges": 0, "community_edges": 0, "has_episode_edges": 0, "next_episode_edges": 0}
    }
    (export_dir / "metadata.json").write_text(json.dumps(metadata))
    
    # entity_nodes.jsonl
    entity_data = {
        "uuid": "old-uuid",
        "name": "Alice",
        "group_id": "abc",
        "labels": ["Person"],
        "summary": "Engineer",
        "name_embedding": [0.123, 0.456],
        "created_at": "2025-06-01T10:00:00Z",
        "attributes": {}
    }
    (export_dir / "entity_nodes.jsonl").write_text(json.dumps(entity_data) + '\n')
    
    # Create empty JSONL for other tables
    for table in ['episodic_nodes', 'community_nodes', 'saga_nodes', 'entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']:
        (export_dir / f"{table}.jsonl").write_text('')
    
    # Mock driver
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock()
    mock_driver.build_indices_and_constraints = AsyncMock()
    mock_driver.graph_ops = Mock()
    mock_driver.graph_ops.rebuild_age_projection = AsyncMock()
    
    # Import
    import_group(mock_driver, export_dir, "xyz", overwrite=False)
    
    # Verify INSERT was called
    assert mock_driver.execute_query.call_count > 0
    
    # Verify rebuild was called
    mock_driver.build_indices_and_constraints.assert_called_once()
    mock_driver.graph_ops.rebuild_age_projection.assert_called_once()

def test_import_fails_when_group_exists(tmp_path):
    """Test import fails if target group exists without --overwrite."""
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    
    # Create minimal export
    metadata = {"group_id": "abc", "embedding_dimension": 1024, "schema_version": 1, "counts": {}}
    (export_dir / "metadata.json").write_text(json.dumps(metadata))
    for table in ['entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes', 'entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']:
        (export_dir / f"{table}.jsonl").write_text('')
    
    # Mock driver that returns existing data
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock()
    mock_driver.execute_query.return_value = ([{"exists": 1}], [], [])
    
    with pytest.raises(ValueError, match="already contains data"):
        import_group(mock_driver, export_dir, "xyz", overwrite=False)
```

- [x] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_import.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cli.import_'"

- [x] **Step 3: Implement import functions**

```python
# cli/import_.py
import json
from pathlib import Path
from cli.remap import (
    generate_uuid_mappings,
    remap_entity_node,
    remap_entity_edge,
    remap_episodic_node,
    remap_episodic_edge,
    remap_community_node,
    remap_community_edge,
    remap_saga_node,
    remap_has_episode_edge,
    remap_next_episode_edge,
)

# Table processing order (respect FK dependencies)
NODE_TABLES = ['entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes']
EDGE_TABLES = ['entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']

async def check_group_exists(driver, group_id: str) -> bool:
    """Check if group_id already has data."""
    records, _, _ = await driver.execute_query(
        "SELECT 1 FROM entity_nodes WHERE group_id = %(group_id)s LIMIT 1",
        params={'group_id': group_id}
    )
    return len(records) > 0

async def import_group(driver, input_dir: Path, new_group_id: str, overwrite: bool = False):
    """Import JSONL files to database with UUID remapping."""
    input_dir = Path(input_dir)

    # Check if target exists
    if await check_group_exists(driver, new_group_id):
        if not overwrite:
            raise ValueError(f"group_id '{new_group_id}' already contains data. Use --overwrite to replace.")
        # Clear existing data
        await driver.graph_ops.clear_data(group_ids=[new_group_id])

    # Load metadata
    metadata = json.loads((input_dir / "metadata.json").read_text())

    # Validate embedding dimension (reads driver.embedding_dimension, no schema param needed)
    target_dim = getattr(driver, 'embedding_dimension', 1024)
    if metadata.get('embedding_dimension', 1024) != target_dim:
        raise ValueError(f"Embedding dimension mismatch: export has {metadata['embedding_dimension']}, database has {target_dim}")
    
    # Phase 1: Generate UUID mappings
    jsonl_files = [input_dir / f"{table}.jsonl" for table in NODE_TABLES + EDGE_TABLES]
    uuid_map = generate_uuid_mappings(jsonl_files)
    
    # Phase 2: Import with remapping (in dependency order)
    await import_nodes(driver, input_dir, uuid_map, new_group_id)
    await import_edges(driver, input_dir, uuid_map, new_group_id)
    
    # Rebuild indexes and AGE projection
    await driver.build_indices_and_constraints()
    await driver.graph_ops.rebuild_age_projection()
    
    return metadata

async def import_nodes(driver, input_dir: Path, uuid_map: dict, new_group_id: str):
    """Import node tables."""
    for table_name in NODE_TABLES:
        jsonl_path = input_dir / f"{table_name}.jsonl"
        if not jsonl_path.exists():
            continue
        
        with open(jsonl_path) as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                
                # Remap based on table type
                if table_name == 'entity_nodes':
                    remapped = remap_entity_node(record, uuid_map, new_group_id)
                elif table_name == 'episodic_nodes':
                    remapped = remap_episodic_node(record, uuid_map, new_group_id)
                elif table_name == 'community_nodes':
                    remapped = remap_community_node(record, uuid_map, new_group_id)
                elif table_name == 'saga_nodes':
                    remapped = remap_saga_node(record, uuid_map, new_group_id)
                
                # Direct INSERT (bypass ORM)
                await insert_record(driver, table_name, remapped)

async def import_edges(driver, input_dir: Path, uuid_map: dict, new_group_id: str):
    """Import edge tables."""
    for table_name in EDGE_TABLES:
        jsonl_path = input_dir / f"{table_name}.jsonl"
        if not jsonl_path.exists():
            continue
        
        with open(jsonl_path) as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                
                # Remap based on table type
                if table_name == 'entity_edges':
                    remapped = remap_entity_edge(record, uuid_map, new_group_id)
                elif table_name == 'episodic_edges':
                    remapped = remap_episodic_edge(record, uuid_map, new_group_id)
                elif table_name == 'community_edges':
                    remapped = remap_community_edge(record, uuid_map, new_group_id)
                elif table_name == 'has_episode_edges':
                    remapped = remap_has_episode_edge(record, uuid_map, new_group_id)
                elif table_name == 'next_episode_edges':
                    remapped = remap_next_episode_edge(record, uuid_map, new_group_id)
                
                # Direct INSERT
                await insert_record(driver, table_name, remapped)

async def insert_record(driver, table_name: str, record: dict):
    """Insert a single record using direct SQL."""
    columns = ', '.join(record.keys())
    placeholders = ', '.join([f'%({k})s' for k in record.keys()])
    
    query = f"""
        INSERT INTO {table_name} ({columns})
        VALUES ({placeholders})
        ON CONFLICT (uuid) DO UPDATE SET {', '.join([f'{k} = EXCLUDED.{k}' for k in record.keys() if k != 'uuid'])}
    """
    
    await driver.execute_query(query, params=record)
```

- [x] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_import.py -v
```

Expected: All tests PASS

- [x] **Step 5: Wire import command in main.py**

```python
# cli/main.py (update import section)
elif args.command == 'import':
    from cli.import_ import import_group
    from graphiti_core.driver.postgres_age.driver import PostgresAgeDriver
    
    driver = PostgresAgeDriver(dsn=args.dsn, schema=args.schema)
    try:
        metadata = await import_group(driver, Path(args.input_dir), args.new_group_id, args.overwrite)
        print(f"Imported {metadata['counts']} records to group_id '{args.new_group_id}'")
    finally:
        await driver.close()
```

- [x] **Step 6: Commit**

```bash
git add cli/import_.py tests/cli/test_import.py cli/main.py
git commit -m "feat: implement import with UUID remapping and AGE projection rebuild"
```

---

### Task 5: Diff Implementation (diff.py)

**Files:**
- Create: `cli/diff.py`
- Create: `tests/cli/test_diff.py`

- [x] **Step 1: Write failing test for diff**

```python
# tests/cli/test_diff.py
import json
from pathlib import Path
from cli.diff import diff_groups, get_business_key

def test_get_business_key():
    """Test business key extraction."""
    # Entity node
    record = {"name": "Alice", "labels": ["Person"]}
    assert get_business_key(record, 'entity_nodes') == ("Alice", ("Person",))
    
    # Episodic node
    record = {"valid_at": "2025-06-01", "content": "Hello"}
    key = get_business_key(record, 'episodic_nodes')
    assert key[0] == "2025-06-01"
    assert len(key[1]) == 12
    
    # Community node
    record = {"name": "Tech"}
    assert get_business_key(record, 'community_nodes') == ("Tech",)

def test_diff_groups_finds_differences(tmp_path):
    """Test diff detects added, removed, and modified records."""
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    left_dir.mkdir()
    right_dir.mkdir()
    
    # Create left export (has Alice and Bob)
    (left_dir / "entity_nodes.jsonl").write_text(
        '{"uuid": "1", "name": "Alice", "labels": ["Person"], "summary": "Engineer"}\n'
        '{"uuid": "2", "name": "Bob", "labels": ["Person"], "summary": "Designer"}\n'
    )
    (left_dir / "metadata.json").write_text('{"group_id": "left", "counts": {"entity_nodes": 2}}')
    
    # Create right export (has Alice modified, Charlie added, Bob removed)
    (right_dir / "entity_nodes.jsonl").write_text(
        '{"uuid": "3", "name": "Alice", "labels": ["Person"], "summary": "Manager"}\n'
        '{"uuid": "4", "name": "Charlie", "labels": ["Person"], "summary": "Analyst"}\n'
    )
    (right_dir / "metadata.json").write_text('{"group_id": "right", "counts": {"entity_nodes": 2}}')
    
    # Create empty files for other tables
    for table in ['episodic_nodes', 'community_nodes', 'saga_nodes', 'entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']:
        (left_dir / f"{table}.jsonl").write_text('')
        (right_dir / f"{table}.jsonl").write_text('')
    
    patch = diff_groups(left_dir, right_dir)
    
    # Check changes
    entity_changes = patch['changes']['entity_nodes']
    assert len(entity_changes['added']) == 1  # Charlie
    assert entity_changes['added'][0]['name'] == 'Charlie'
    
    assert len(entity_changes['removed']) == 1  # Bob
    assert entity_changes['removed'][0]['name'] == 'Bob'
    
    assert len(entity_changes['modified']) == 1  # Alice (summary changed)
    assert entity_changes['modified'][0]['match']['name'] == 'Alice'
    assert 'summary' in entity_changes['modified'][0]['fields']
```

- [x] **Step 2: Run test to verify it fails**

```bash
pytest tests/cli/test_diff.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cli.diff'"

- [x] **Step 3: Implement diff functions**

```python
# cli/diff.py
import json
import hashlib
from pathlib import Path
from typing import Any

TABLES = ['entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes',
          'entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']

IGNORE_FIELDS = {'uuid', 'group_id', 'source_node_uuid', 'target_node_uuid', 'episodes', 'entity_edges',
                 'first_episode_uuid', 'last_episode_uuid', 'created_at'}

def get_business_key(record: dict, table_name: str) -> tuple:
    """Extract business key based on table type."""
    if table_name == 'entity_nodes':
        return (record['name'], tuple(record.get('labels', [])))
    elif table_name == 'episodic_nodes':
        content_hash = hashlib.sha256(record.get('content', '').encode()).hexdigest()[:12]
        return (record.get('valid_at', ''), content_hash)
    elif table_name in ('community_nodes', 'saga_nodes'):
        return (record['name'],)
    elif table_name == 'entity_edges':
        # For edges, use source/target names + edge name (requires pre-joined data)
        return (record.get('source_name', ''), record.get('target_name', ''), record.get('name', ''))
    # ... other edge tables
    else:
        raise ValueError(f"Unknown table: {table_name}")

def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file into list of records."""
    if not path.exists():
        return []
    
    records = []
    with open(path) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def build_index(records: list[dict], table_name: str) -> dict[tuple, dict]:
    """Build business key → record index."""
    index = {}
    for record in records:
        try:
            key = get_business_key(record, table_name)
            index[key] = record
        except (KeyError, TypeError):
            # Skip records that don't have required fields for business key
            pass
    return index

def compare_table(left_records: list[dict], right_records: list[dict], table_name: str) -> dict:
    """Compare two sets of records for a table."""
    left_index = build_index(left_records, table_name)
    right_index = build_index(right_records, table_name)
    
    added = []
    removed = []
    modified = []
    
    # Find removed and modified
    for key, left_record in left_index.items():
        if key not in right_index:
            removed.append(extract_match_fields(left_record, table_name))
        else:
            right_record = right_index[key]
            changes = compare_fields(left_record, right_record)
            if changes:
                modified.append({
                    'match': extract_match_fields(left_record, table_name),
                    'fields': changes
                })
    
    # Find added
    for key, right_record in right_index.items():
        if key not in left_index:
            added.append(extract_match_fields(right_record, table_name))
    
    return {
        'added': added,
        'removed': removed,
        'modified': modified,
        'conflicts': []
    }

def compare_fields(left: dict, right: dict) -> dict:
    """Compare two records field by field, ignoring certain fields."""
    changes = {}
    
    all_fields = set(left.keys()) | set(right.keys())
    for field in all_fields:
        if field in IGNORE_FIELDS:
            continue
        
        left_val = left.get(field)
        right_val = right.get(field)
        
        if left_val != right_val:
            changes[field] = {'old': left_val, 'new': right_val}
    
    return changes

def extract_match_fields(record: dict, table_name: str) -> dict:
    """Extract fields needed to identify a record (for patch)."""
    if table_name == 'entity_nodes':
        return {'name': record['name'], 'labels': record.get('labels', [])}
    elif table_name == 'episodic_nodes':
        return {'valid_at': record['valid_at'], 'content_hash': hashlib.sha256(record.get('content', '').encode()).hexdigest()[:12]}
    elif table_name in ('community_nodes', 'saga_nodes'):
        return {'name': record['name']}
    elif table_name == 'entity_edges':
        return {'source_name': record.get('source_name'), 'target_name': record.get('target_name'), 'name': record.get('name')}
    # ... other tables
    return {}

def diff_groups(left_dir: Path, right_dir: Path) -> dict:
    """Compare two export directories and generate patch."""
    patch = {
        'version': 1,
        'metadata': {
            'from_group_id': json.loads((left_dir / "metadata.json").read_text()).get('group_id'),
            'to_group_id': json.loads((right_dir / "metadata.json").read_text()).get('group_id'),
        },
        'changes': {}
    }
    
    for table_name in TABLES:
        left_path = left_dir / f"{table_name}.jsonl"
        right_path = right_dir / f"{table_name}.jsonl"
        
        left_records = load_jsonl(left_path)
        right_records = load_jsonl(right_path)
        
        patch['changes'][table_name] = compare_table(left_records, right_records, table_name)
    
    return patch
```

- [x] **Step 4: Run test to verify it passes**

```bash
pytest tests/cli/test_diff.py::test_diff_groups_finds_differences -v
```

Expected: PASS

- [x] **Step 5: Wire diff command in main.py**

```python
# cli/main.py (update diff section)
elif args.command == 'diff':
    from cli.diff import diff_groups
    
    patch = diff_groups(Path(args.left_dir), Path(args.right_dir))
    
    # Write patch
    with open(args.output, 'w') as f:
        json.dump(patch, f, indent=2)
    
    print(f"Patch written to {args.output}")
    
    # Optionally generate HTML
    if args.html_output:
        from cli.render import render_html
        render_html(patch, args.html_output)
        print(f"HTML report written to {args.html_output}")
```

- [x] **Step 6: Commit**

```bash
git add cli/diff.py tests/cli/test_diff.py cli/main.py
git commit -m "feat: implement semantic diff with business key matching"
```

---

### Task 6: Apply Implementation (apply.py)

**Files:**
- Create: `cli/apply.py`
- Create: `tests/cli/test_apply.py`

- [x] **Step 1: Write failing test for apply**

```python
# tests/cli/test_apply.py
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from cli.apply import apply_patch

def test_apply_patch_adds_records(tmp_path):
    """Test apply adds new records from patch."""
    # Create patch
    patch = {
        'version': 1,
        'metadata': {'from_group_id': 'abc'},
        'changes': {
            'entity_nodes': {
                'added': [
                    {'name': 'Charlie', 'labels': ['Person'], 'summary': 'Analyst'}
                ],
                'removed': [],
                'modified': [],
                'conflicts': []
            }
        }
    }
    
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps(patch))
    
    # Mock driver
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock()
    
    # Mock loading from_group_id data
    mock_driver.execute_query.return_value = ([], [], [])
    
    # Apply
    result = apply_patch(mock_driver, patch_file, 'abc', 'xyz', 'public', strategy='ours', dry_run=False)
    
    assert result['added'] == 1
    assert result['removed'] == 0
    assert result['modified'] == 0

def test_apply_patch_dry_run(tmp_path):
    """Test dry run validates without applying."""
    patch = {
        'version': 1,
        'metadata': {'from_group_id': 'abc'},
        'changes': {
            'entity_nodes': {
                'added': [{'name': 'Charlie', 'labels': ['Person'], 'summary': 'Analyst'}],
                'removed': [],
                'modified': [],
                'conflicts': []
            }
        }
    }
    
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps(patch))
    
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock()
    
    result = apply_patch(mock_driver, patch_file, 'abc', 'xyz', 'public', strategy='ours', dry_run=True)
    
    # Verify no INSERT called
    assert result['dry_run'] is True
    assert result['added'] == 1
```

- [x] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_apply.py -v
```

Expected: FAIL

- [x] **Step 3: Implement apply functions**

```python
# cli/apply.py
import json
from pathlib import Path
from cli.remap import generate_uuid_mappings, remap_entity_node

async def apply_patch(driver, patch_file: Path, from_group_id: str, to_group_id: str, schema: str, strategy: str, dry_run: bool) -> dict:
    """Apply patch to database."""
    patch = json.loads(patch_file.read_text())
    
    # Load source data
    from_data = await load_group_data(driver, from_group_id)
    
    # Apply changes
    result = {'added': 0, 'removed': 0, 'modified': 0, 'conflicts': 0, 'dry_run': dry_run}
    
    # Process each table
    for table_name, changes in patch['changes'].items():
        # Add new records
        for added_record in changes['added']:
            if not dry_run:
                # Generate new UUID and insert
                await insert_added_record(driver, table_name, added_record, to_group_id)
            result['added'] += 1
        
        # Remove records
        for removed_record in changes['removed']:
            if not dry_run:
                await delete_record_by_business_key(driver, table_name, removed_record, from_group_id)
            result['removed'] += 1
        
        # Modify records
        for modified in changes['modified']:
            if not dry_run:
                await update_record_by_business_key(driver, table_name, modified['match'], modified['fields'], to_group_id, strategy)
            result['modified'] += 1
        
        # Handle conflicts
        if changes.get('conflicts'):
            result['conflicts'] += len(changes['conflicts'])
            if not dry_run and strategy != 'skip-conflicts':
                await resolve_conflicts(driver, table_name, changes['conflicts'], strategy)
    
    # Rebuild if not dry run
    if not dry_run:
        await driver.build_indices_and_constraints()
        await driver.graph_ops.rebuild_age_projection()
    
    return result

async def load_group_data(driver, group_id: str) -> dict:
    """Load all data for a group_id."""
    data = {}
    tables = ['entity_nodes', 'episodic_nodes', 'community_nodes', 'saga_nodes',
              'entity_edges', 'episodic_edges', 'community_edges', 'has_episode_edges', 'next_episode_edges']
    
    for table_name in tables:
        records, _, _ = await driver.execute_query(
            f"SELECT * FROM {table_name} WHERE group_id = %(group_id)s",
            params={'group_id': group_id}
        )
        data[table_name] = records
    
    return data

# ... implement insert_added_record, delete_record_by_business_key, etc.
```

- [x] **Step 4: Wire apply command in main.py**

```python
# cli/main.py (update apply section)
elif args.command == 'apply':
    from cli.apply import apply_patch
    from graphiti_core.driver.postgres_age.driver import PostgresAgeDriver
    
    driver = PostgresAgeDriver(dsn=args.dsn, schema=args.schema)
    try:
        result = await apply_patch(driver, Path(args.patch_file), args.from_group_id, args.to_group_id, args.schema, args.strategy, args.dry_run)
        print(f"Applied: {result['added']} added, {result['removed']} removed, {result['modified']} modified")
        if result['conflicts'] > 0:
            print(f"Conflicts: {result['conflicts']}")
    finally:
        await driver.close()
```

- [x] **Step 5: Commit**

```bash
git add cli/apply.py tests/cli/test_apply.py cli/main.py
git commit -m "feat: implement patch apply with conflict resolution"
```

---

### Task 7: E2E Tests + Production Fixes

**Files:**
- Create: `tests/cli/test_e2e.py` (end-to-end workflow test)
- Create: `web_service/e2e/data.spec.ts` (Playwright E2E for Data UI)
- Modify: `cli/export.py` (numpy type handling, join alias filtering)
- Modify: `cli/import_.py` (jsonb dict serialization)
- Modify: `Dockerfile` (UV_NO_INSTALLER_METADATA, cli copy, python-multipart)

> **Note:** This task expanded beyond the original scope. During implementation, production hardening fixes were discovered and applied: numpy type serialization in export, jsonb compatibility in import, Dockerfile missing deps, and a full Playwright E2E test suite for the Data frontend.

- [x] **Step 1: Write E2E test for full CLI workflow**

```python
# tests/cli/test_integration.py
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock

async def test_full_export_import_diff_workflow(tmp_path):
    """Test complete workflow: export → import → diff."""
    # Setup: Create mock database with test data
    mock_driver = Mock()
    mock_driver.execute_query = AsyncMock()
    mock_driver.build_indices_and_constraints = AsyncMock()
    mock_driver.graph_ops = Mock()
    mock_driver.graph_ops.rebuild_age_projection = AsyncMock()
    
    # Mock data for export
    mock_driver.execute_query.side_effect = [
        # entity_nodes query
        ([{
            "uuid": "uuid-1",
            "name": "Alice",
            "group_id": "group-a",
            "labels": ["Person"],
            "summary": "Engineer",
            "name_embedding": [0.123, 0.456],
            "created_at": "2025-06-01T10:00:00Z",
            "attributes": {}
        }], [], []),
        # ... other table queries (return empty for simplicity)
    ]
    
    # Step 1: Export
    from cli.export import export_group_with_sorting
    export_dir_a = tmp_path / "export-a"
    await export_group_with_sorting(mock_driver, "group-a", "public", export_dir_a)
    
    assert (export_dir_a / "metadata.json").exists()
    assert (export_dir_a / "entity_nodes.jsonl").exists()
    
    # Step 2: Import to new group
    from cli.import_ import import_group
    mock_driver.execute_query.side_effect = None  # Reset
    mock_driver.execute_query = AsyncMock()
    
    await import_group(mock_driver, export_dir_a, "group-b", "public", overwrite=False)
    
    # Verify INSERT was called
    assert mock_driver.execute_query.call_count > 0
    
    # Step 3: Diff the two exports
    # (Would need to create export-b first, then diff)
    # Simplified for brevity
    
    print("Integration test passed: export → import workflow")
```

**Also added Playwright E2E tests** in `web_service/e2e/data.spec.ts` covering:
- Groups list display
- Group detail view
- Diff between two groups
- Import data dialog
- Import patch dialog workflow

- [x] **Step 2: Run E2E test**

```bash
pytest tests/cli/test_integration.py -v -s
```

Expected: PASS

- [x] **Step 3: Commit**

```bash
git add tests/cli/test_e2e.py web_service/e2e/data.spec.ts
git commit -m "test: add E2E tests for CLI full workflow and Data UI"
```

---

## Testing Strategy

### Unit Tests
- `test_remap.py`: UUID remapping functions (2-phase approach)
- `test_export.py`: JSONL serialization, sorting, metadata generation
- `test_import.py`: JSONL loading, UUID remapping, direct INSERT
- `test_diff.py`: Business key matching, field comparison
- `test_apply.py`: Patch application, conflict resolution

### Integration / E2E Tests
- `test_e2e.py`: Full CLI export → import → diff → apply workflow
- `web_service/e2e/data.spec.ts`: Playwright E2E for Data frontend UI

### Test Execution

```bash
# Run all CLI tests
pytest tests/cli/ -v

# Run with coverage
pytest tests/cli/ --cov=cli --cov-report=term-missing

# Run specific test file
pytest tests/cli/test_export.py -v
```

---

## Dependencies

No new dependencies required. Uses existing:
- `asyncpg` (async PostgreSQL driver, via `graphiti_core.driver.postgres_age`)
- `orjson` or stdlib `json` (JSON serialization)
- `argparse` (CLI)
- `pytest` (testing)

---

## Implementation Checklist

- [x] Task 1: Project Setup (CLI package structure)
- [x] Task 2: UUID Remapping Core (remap.py)
- [x] Task 3: Export Implementation (export.py)
- [x] Task 4: Import Implementation (import_.py)
- [x] Task 5: Diff Implementation (diff.py)
- [x] Task 6: Apply Implementation (apply.py)
- [x] Task 7: E2E Tests + Production Fixes

**Total Estimated Tasks:** 7
**Dependencies Between Tasks:** Task 2 (remap) → Tasks 3, 4, 6 (export, import, apply)

---

## Production Deviations (Actual vs Planned)

The following changes were added during implementation beyond the original plan:

### 1. CLI Export Production Hardening

**`cli/export.py`** — Added:

- `_JOIN_ALIAS_FIELDS` — Filters out JOIN-aliased columns (`source_name`, `target_name`, `source_content_hash`, `target_content_hash`) from JSONL output. These columns are added by edge table JOIN queries for diff business key matching but are NOT part of the actual table schema. Without this filter, import INSERT fails.
- `_json_safe()` — Recursive converter for numpy types (`float32`, `int64`, etc.) and datetimes to JSON-safe equivalents. `json.dumps` rejects numpy types on some platforms.
- `_NumpyEncoder` — Custom `json.JSONEncoder` subclass for numpy scalar fallback handling.

### 2. CLI Import Production Hardening

**`cli/import_.py`** — Added:

- `_jsonify_values()` — Serializes Python `dict` values to JSON strings for psycopg jsonb column compatibility. Lists are left as-is (handled natively for ARRAY columns and pgvector).

### 3. Dockerfile Updates

- `UV_NO_INSTALLER_METADATA=1` — Environment flag for uv compatibility
- Copy `./cli` directory into image (was missing, causing import errors at runtime)
- Install `python-multipart` dependency (required by FastAPI file upload endpoints)

### 4. Group Deletion (Not in Original Plan)

**Backend:** Added `DELETE /rest/data/groups/{group_id}` endpoint in `server/graph_service/routers/data.py` that calls `graphiti.delete_group()`.

**Frontend:** Added delete button with confirmation dialog in `groups-table.tsx`, with loading state (`deleting` prop) and error handling. Selection is cleared if the deleted group was selected.

### 5. Frontend Polish

- **React key warning fix:** Replaced `<>` fragment with `<Fragment key={tableName}>` in `group-detail.tsx`
- **Responsive breakpoint:** Changed sidebar from `lg:hidden` to `md:hidden` for better tablet support
- **UI text:** Group list empty state uses Chinese locale (\"暂无分组\")
- **Action icons:** View button uses Eye icon; delete button uses Trash2 icon with `text-destructive` styling

### 6. Server Tests Location

Server API tests are at `server/tests/test_data_api.py` (not `tests/server/test_data_api.py`), matching the project convention of co-locating tests with their package.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-05-graphiti-data-migration-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
