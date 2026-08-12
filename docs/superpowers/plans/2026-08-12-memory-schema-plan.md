# Memory Schema View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Memory Schema page (`/memory-schema`) that visualizes the ontology (entity types, attributes, relationships) as an interactive graph with a card-grid default state and a relationship-graph selected state.

**Architecture:** Backend extends `TypeDefinition` DTO with `source_types`/`target_types` and captures these during extraction. Frontend adds a new page with a Zustand store for ontology data, reusing Sigma.js for graph rendering and following existing patterns from the Graph view.

**Tech Stack:** Python/FastAPI (backend), Next.js App Router + React + TypeScript + Zustand + Sigma.js + Graphology (frontend)

---

## File Structure

### Backend (modify)

| File | Responsibility |
|------|---------------|
| `server/graph_service/dto/schemas.py` | Add `source_types`/`target_types` to `TypeDefinition` |
| `server/graph_service/routers/ingest.py` | Post-extraction type mapping collection |
| `server/graph_service/models.py` | Verify `build_extraction_params` passthrough |

### Frontend (create)

| File | Responsibility |
|------|---------------|
| `web_service/app/memory-schema/page.tsx` | Page entry (dynamic import, no SSR) |
| `web_service/app/memory-schema/memory-schema-client.tsx` | Main orchestrator component |
| `web_service/stores/ontology-store.ts` | Zustand store for ontology state |
| `web_service/components/memory-schema/ontology-selector.tsx` | Schema dropdown + "New" link |
| `web_service/components/memory-schema/default-view.tsx` | Card grid container |
| `web_service/components/memory-schema/entity-type-card.tsx` | Single type card with 4 columns |
| `web_service/components/memory-schema/selected-view.tsx` | Relationship graph + detail panel layout |
| `web_service/components/memory-schema/ontology-canvas.tsx` | Sigma.js renderer for ontology graph |
| `web_service/components/memory-schema/detail-panel.tsx` | Right-side 4-column detail |
| `web_service/components/memory-schema/layout-controls.tsx` | Zoom/fit/fullscreen controls |
| `web_service/components/memory-schema/legend.tsx` | Color legend for node types |

### Frontend (modify)

| File | Change |
|------|--------|
| `web_service/components/layout/sidebar.tsx` | Add Memory Schema nav item |
| `web_service/lib/types.ts` | Add ontology-related types |

---

## Phase 1: Backend - Data Model

### Task 1: Extend TypeDefinition DTO

**Files:**
- Modify: `server/graph_service/dto/schemas.py`

- [ ] **Step 1: Add `source_types`/`target_types` fields to `TypeDefinition`**

In `server/graph_service/dto/schemas.py`, change the `TypeDefinition` class:

```python
class TypeDefinition(BaseModel):
    name: str
    description: str = ''
    attributes: list[AttributeDefinition] = []
    source_types: list[str] = []
    target_types: list[str] = []
```

- [ ] **Step 2: Commit**

```bash
git add server/graph_service/dto/schemas.py
git commit -m "feat: add source_types/target_types to TypeDefinition DTO"
```

---

### Task 2: Verify build_extraction_params Passthrough

**Files:**
- Modify: `server/graph_service/models.py` (only if needed)

- [ ] **Step 1: Read `build_extraction_params` and verify `source_types`/`target_types` are included in JSONB serialization**

Read `server/graph_service/models.py` lines 167-197. The function builds entity/edge type models from the schema dict. Since `edge_types` items are passed through as-is dicts, and the schema is stored as JSONB, the new `source_types`/`target_types` fields are automatically included. Verify no changes are needed.

- [ ] **Step 2: Commit (if changes made)**

```bash
git add server/graph_service/models.py
git commit -m "feat: ensure build_extraction_params passes through source_types/target_types"
```

---

## Phase 2: Backend - Extraction Logic

### Task 3: Add Post-Extraction Type Mapping Collection

**Files:**
- Modify: `server/graph_service/routers/ingest.py`

- [ ] **Step 1: Add helper function `_update_schema_type_mapping`**

NOTE: Graphiti's `add_episode()` does not return the extracted nodes/edges directly. Use the DB query approach below to collect type mappings.

Add this function to `ingest.py` (after `_resolve_schema_params`):

```python
async def _update_schema_type_mapping(
    schema_id: int,
    nodes: list[dict],
    edges: list[dict],
) -> None:
    """Collect and save source/target entity type mappings for edge types.
    
    After extraction, inspect the saved edges to determine which entity
    types each relationship type connects. Merge-append into the schema's
    edge_types definition.
    """
    if schema_id is None:
        return

    from graph_service.config import get_settings
    from graph_service.models import get_schema, update_schema

    settings = get_settings()
    schema = await get_schema(settings.postgres_age_dsn, schema_id)
    if not schema:
        return

    # Build node_uuid -> labels map
    node_labels: dict[str, list[str]] = {}
    for node in nodes:
        node_uuid = node.get('uuid', node.get('id', ''))
        labels = node.get('labels', [])
        if isinstance(labels, str):
            labels = [labels] if labels else []
        node_labels[node_uuid] = labels

    # Collect type mappings per edge name
    type_mapping: dict[str, dict[str, set[str]]] = {}
    for edge in edges:
        edge_name = edge.get('name', 'UNKNOWN')
        source_uuid = edge.get('source_node_uuid', edge.get('source', ''))
        target_uuid = edge.get('target_node_uuid', edge.get('target', ''))
        
        if edge_name not in type_mapping:
            type_mapping[edge_name] = {'source': set(), 'target': set()}
        
        for label in node_labels.get(source_uuid, []):
            type_mapping[edge_name]['source'].add(label)
        for label in node_labels.get(target_uuid, []):
            type_mapping[edge_name]['target'].add(label)

    if not type_mapping:
        return

    # Merge-append into schema's edge_types
    edge_types = schema.get('edge_types', [])
    for et in edge_types:
        if not isinstance(et, dict):
            continue
        et_name = et.get('name', '')
        if et_name in type_mapping:
            existing_source = set(et.get('source_types', []))
            existing_target = set(et.get('target_types', []))
            et['source_types'] = sorted(existing_source | type_mapping[et_name]['source'])
            et['target_types'] = sorted(existing_target | type_mapping[et_name]['target'])

    # Persist updated schema
    data = {
        'name': schema['name'],
        'description': schema.get('description', ''),
        'entity_types': schema.get('entity_types', []),
        'edge_types': edge_types,
        'custom_instructions': schema.get('custom_instructions', ''),
    }
    await update_schema(settings.postgres_age_dsn, schema_id, data)
```

- [ ] **Step 2: Call `_update_schema_type_mapping` in `add_episode` after extraction**

In the `episode_task()` function inside `add_episode`, after the `await task_graphiti.add_episode(...)` call succeeds, add:

```python
                # Collect type mapping for schema by querying recent edges
                try:
                    if request.schema_id:
                        driver = task_graphiti.driver
                        recent_edges, _, _ = await driver.execute_query(
                            """
                            SELECT e.name, e.source_node_uuid, e.target_node_uuid,
                                   s.labels as source_labels, t.labels as target_labels
                            FROM entity_edges e
                            JOIN entity_nodes s ON e.source_node_uuid = s.uuid
                            JOIN entity_nodes t ON e.target_node_uuid = t.uuid
                            WHERE e.group_id = %s
                            ORDER BY e.created_at DESC
                            LIMIT 100
                            """,
                            params=(request.group_id,),
                        )
                        edges_data = [
                            {
                                'name': r.get('name', 'UNKNOWN'),
                                'source_labels': r.get('source_labels', []),
                                'target_labels': r.get('target_labels', []),
                            }
                            for r in (recent_edges or [])
                        ]
                        await _update_schema_type_mapping_from_edges(request.schema_id, edges_data)
                except Exception as map_err:
                    print(f'⚠️ Type mapping update failed: {map_err}', flush=True, file=sys.stderr)
```

Also add this helper function (used by the above):

```python
async def _update_schema_type_mapping_from_edges(
    schema_id: int,
    edges_data: list[dict],
) -> None:
    """Collect type mappings from edge query results and update schema."""
    if schema_id is None or not edges_data:
        return

    from graph_service.config import get_settings
    from graph_service.models import get_schema, update_schema

    settings = get_settings()
    schema = await get_schema(settings.postgres_age_dsn, schema_id)
    if not schema:
        return

    type_mapping: dict[str, dict[str, set[str]]] = {}
    for edge in edges_data:
        edge_name = edge.get('name', 'UNKNOWN')
        if edge_name not in type_mapping:
            type_mapping[edge_name] = {'source': set(), 'target': set()}
        
        source_labels = edge.get('source_labels', [])
        target_labels = edge.get('target_labels', [])
        if isinstance(source_labels, str):
            source_labels = [source_labels] if source_labels else []
        if isinstance(target_labels, str):
            target_labels = [target_labels] if target_labels else []
        
        type_mapping[edge_name]['source'].update(source_labels)
        type_mapping[edge_name]['target'].update(target_labels)

    edge_types = schema.get('edge_types', [])
    for et in edge_types:
        if not isinstance(et, dict):
            continue
        et_name = et.get('name', '')
        if et_name in type_mapping:
            existing_source = set(et.get('source_types', []))
            existing_target = set(et.get('target_types', []))
            et['source_types'] = sorted(existing_source | type_mapping[et_name]['source'])
            et['target_types'] = sorted(existing_target | type_mapping[et_name]['target'])

    data = {
        'name': schema['name'],
        'description': schema.get('description', ''),
        'entity_types': schema.get('entity_types', []),
        'edge_types': edge_types,
        'custom_instructions': schema.get('custom_instructions', ''),
    }
    await update_schema(settings.postgres_age_dsn, schema_id, data)
```

- [ ] **Step 3: Commit**

```bash
git add server/graph_service/routers/ingest.py
git commit -m "feat: collect and save edge type mappings during extraction"
```

---

## Phase 3: Frontend - Core Infrastructure

### Task 4: Add Sidebar Navigation Item

**Files:**
- Modify: `web_service/components/layout/sidebar.tsx`

- [ ] **Step 1: Add `Brain` icon import and `Memory Schema` nav item**

In `web_service/components/layout/sidebar.tsx`:

1. Add `Brain` to the lucide imports:
```typescript
import {
  BarChart3,
  Brain,
  Network,
  FolderOpen,
  Menu,
  Settings2,
} from 'lucide-react';
```

2. Add the nav item between Graph and Knowledge:
```typescript
const navItems: NavItem[] = [
  {
    label: 'Overview',
    href: '/',
    icon: <BarChart3 className="h-4 w-4" />,
  },
  {
    label: 'Graph',
    href: '/graph',
    icon: <Network className="h-4 w-4" />,
  },
  {
    label: 'Memory Schema',
    href: '/memory-schema',
    icon: <Brain className="h-4 w-4" />,
  },
  {
    label: 'Knowledge',
    href: '/knowledge',
    icon: <FolderOpen className="h-4 w-4" />,
  },
  {
    label: 'Schemas',
    href: '/settings/schemas',
    icon: <Settings2 className="h-4 w-4" />,
  },
];
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/layout/sidebar.tsx
git commit -m "feat: add Memory Schema nav item to sidebar"
```

---

### Task 5: Add Ontology Types

**Files:**
- Modify: `web_service/lib/types.ts`

- [ ] **Step 1: Add ontology-related types**

Add to the end of `web_service/lib/types.ts`:

```typescript
// ─── Memory Schema Related ───

export interface AttributeDef {
  name: string;
  type: string;
  description: string;
}

export interface EntityTypeDefinition {
  name: string;
  description: string;
  attributes: AttributeDef[];
}

export interface EdgeTypeDefinition {
  name: string;
  description: string;
  attributes: AttributeDef[];
  source_types: string[];
  target_types: string[];
}

export interface ExtractionSchema {
  id: number;
  name: string;
  description: string;
  entity_types: EntityTypeDefinition[];
  edge_types: EdgeTypeDefinition[];
  custom_instructions: string;
}

export interface OntologyNode {
  id: string;        // type name (e.g., "Person")
  label: string;     // display name
  type: 'entity';
  attributes: AttributeDef[];
  description: string;
  episodes: EpisodeItem[];
  entities: EntityItem[];
  summaries: SummaryItem[];
}

export interface OntologyEdge {
  id: string;        // edge type name (e.g., "WORKS_AT")
  source: string;    // source entity type name
  target: string;    // target entity type name
  label: string;     // display name
  attributes: AttributeDef[];
  description: string;
}

export interface OntologyGraph {
  nodes: OntologyNode[];
  edges: OntologyEdge[];
  source: 'schema' | 'graph';
  schemaId?: number;
  schemaName?: string;
}

export interface EpisodeItem {
  id: string;
  name: string;
  content: string;
  created_at: string;
}

export interface EntityItem {
  id: string;
  name: string;
  summary: string;
}

export interface SummaryItem {
  id: string;
  content: string;
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/lib/types.ts
git commit -m "feat: add ontology types for Memory Schema view"
```

---

### Task 6: Create Ontology Store

**Files:**
- Create: `web_service/stores/ontology-store.ts`

- [ ] **Step 1: Write the store**

Create `web_service/stores/ontology-store.ts`:

```typescript
// stores/ontology-store.ts
import { create } from 'zustand';
import type { OntologyGraph, OntologyNode } from '@/lib/types';

interface OntologyState {
  // Data
  ontology: OntologyGraph | null;
  schemas: { id: number; name: string }[];
  selectedSchemaId: number | null;  // null = default ontology

  // UI State
  viewMode: 'default' | 'selected';
  selectedNodeId: string | null;

  // Loading
  loading: boolean;
  error: string | null;

  // Actions
  setSchemas: (schemas: { id: number; name: string }[]) => void;
  setSelectedSchemaId: (id: number | null) => void;
  setOntology: (ontology: OntologyGraph) => void;
  setSelectedNode: (nodeId: string | null) => void;
  setViewMode: (mode: 'default' | 'selected') => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  resetView: () => void;
}

export const useOntologyStore = create<OntologyState>((set) => ({
  ontology: null,
  schemas: [],
  selectedSchemaId: null,
  viewMode: 'default',
  selectedNodeId: null,
  loading: false,
  error: null,

  setSchemas: (schemas) => set({ schemas }),
  setSelectedSchemaId: (id) => set({ selectedSchemaId: id }),
  setOntology: (ontology) => set({ ontology }),
  setSelectedNode: (nodeId) => set({ selectedNodeId: nodeId }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  resetView: () => set({ viewMode: 'default', selectedNodeId: null }),
}));
```

- [ ] **Step 2: Commit**

```bash
git add web_service/stores/ontology-store.ts
git commit -m "feat: add Zustand store for ontology state"
```

---

### Task 7: Create Page Entry

**Files:**
- Create: `web_service/app/memory-schema/page.tsx`

- [ ] **Step 1: Write the page entry**

Create `web_service/app/memory-schema/page.tsx`:

```typescript
'use client';

import dynamic from 'next/dynamic';

const MemorySchemaClient = dynamic(() => import('./memory-schema-client'), {
  ssr: false,
});

export default function MemorySchemaPage() {
  return <MemorySchemaClient />;
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/app/memory-schema/page.tsx
git commit -m "feat: add Memory Schema page entry"
```

---

## Phase 4: Frontend - Components

### Task 8: Create Ontology Selector

**Files:**
- Create: `web_service/components/memory-schema/ontology-selector.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/ontology-selector.tsx`:

```typescript
'use client';

import { Brain } from 'lucide-react';
import { useOntologyStore } from '@/stores/ontology-store';

export function OntologySelector() {
  const schemas = useOntologyStore((s) => s.schemas);
  const selectedSchemaId = useOntologyStore((s) => s.selectedSchemaId);
  const setSelectedSchemaId = useOntologyStore((s) => s.setSelectedSchemaId);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value === 'default') {
      setSelectedSchemaId(null);
    } else {
      setSelectedSchemaId(Number(value));
    }
  };

  return (
    <div className="flex items-center gap-3">
      <select
        value={selectedSchemaId ?? 'default'}
        onChange={handleChange}
        className="flex h-9 w-[200px] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <option value="default">默认 Ontology</option>
        {schemas.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
      <a
        href="/settings/schemas/new"
        className="flex h-9 items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
      >
        <Brain className="h-4 w-4" />
        新建
      </a>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/ontology-selector.tsx
git commit -m "feat: add OntologySelector component"
```

---

### Task 9: Create Entity Type Card

**Files:**
- Create: `web_service/components/memory-schema/entity-type-card.tsx`

- [ ] **Step 1: Write the collapsible attribute column component**

Create `web_service/components/memory-schema/entity-type-card.tsx`:

```typescript
'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { EpisodeItem, EntityItem, SummaryItem, AttributeDef } from '@/lib/types';

const MAX_VISIBLE = 5;

interface AttributeColumnProps {
  title: string;
  count: number;
  items: React.ReactNode[];
}

function AttributeColumn({ title, count, items }: AttributeColumnProps) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = items.length > MAX_VISIBLE;
  const visibleItems = expanded ? items : items.slice(0, MAX_VISIBLE);

  return (
    <div className="flex flex-1 flex-col min-w-0 border-r last:border-r-0">
      <div className="border-b px-2 py-1 text-xs font-medium text-muted-foreground">
        {title} ({count})
      </div>
      <div className="flex-1 overflow-y-auto p-1 space-y-1">
        {visibleItems}
        {hasMore && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="w-full text-left px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground"
          >
            + {items.length - MAX_VISIBLE} more
          </button>
        )}
      </div>
    </div>
  );
}

interface EntityTypeCardProps {
  typeName: string;
  episodes: EpisodeItem[];
  entities: EntityItem[];
  types: AttributeDef[];
  summaries: SummaryItem[];
  color: string;
  onSelect: () => void;
}

export function EntityTypeCard({
  typeName,
  episodes,
  entities,
  types,
  summaries,
  color,
  onSelect,
}: EntityTypeCardProps) {
  return (
    <div
      className="rounded-lg border bg-card hover:border-primary/50 transition-colors cursor-pointer flex flex-col min-h-[200px]"
      onClick={onSelect}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <span
          className="h-3 w-3 rounded-full flex-shrink-0"
          style={{ backgroundColor: color }}
        />
        <span className="text-sm font-medium truncate">{typeName}</span>
      </div>

      {/* Four columns */}
      <div className="flex flex-1 min-h-0">
        <AttributeColumn
          title="Episodes"
          count={episodes.length}
          items={episodes.map((e) => (
            <div key={e.id} className="rounded border px-2 py-0.5 text-xs truncate">
              {e.name}
            </div>
          ))}
        />
        <AttributeColumn
          title="Entities"
          count={entities.length}
          items={entities.map((e) => (
            <div key={e.id} className="rounded border px-2 py-0.5 text-xs truncate">
              {e.name}
            </div>
          ))}
        />
        <AttributeColumn
          title="Types"
          count={types.length}
          items={types.map((t) => (
            <div key={t.name} className="rounded border px-2 py-0.5 text-xs truncate">
              {t.name}: {t.type}
            </div>
          ))}
        />
        <AttributeColumn
          title="Summaries"
          count={summaries.length}
          items={summaries.map((s) => (
            <div key={s.id} className="rounded border px-2 py-0.5 text-xs truncate">
              {s.content}
            </div>
          ))}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/entity-type-card.tsx
git commit -m "feat: add EntityTypeCard component with 4-column layout"
```

---

### Task 10: Create Default View

**Files:**
- Create: `web_service/components/memory-schema/default-view.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/default-view.tsx`:

```typescript
'use client';

import { useOntologyStore } from '@/stores/ontology-store';
import { EntityTypeCard } from './entity-type-card';
import { getNodeColor } from '@/lib/graph-theme';

export function DefaultView() {
  const ontology = useOntologyStore((s) => s.ontology);
  const setSelectedNode = useOntologyStore((s) => s.setSelectedNode);
  const setViewMode = useOntologyStore((s) => s.setViewMode);

  if (!ontology) return null;

  const handleSelectNode = (nodeId: string) => {
    setSelectedNode(nodeId);
    setViewMode('selected');
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4">
      {ontology.nodes.map((node) => (
        <EntityTypeCard
          key={node.id}
          typeName={node.label}
          episodes={node.episodes}
          entities={node.entities}
          types={node.attributes}
          summaries={node.summaries}
          color={getNodeColor(node.id)}
          onSelect={() => handleSelectNode(node.id)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/default-view.tsx
git commit -m "feat: add DefaultView card grid component"
```

---

### Task 11: Create Ontology Canvas (Sigma.js)

**Files:**
- Create: `web_service/components/memory-schema/ontology-canvas.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/ontology-canvas.tsx`:

```typescript
'use client';

import { useEffect, useRef, useCallback } from 'react';
import Sigma from 'sigma';
import Graph from 'graphology';
import { useOntologyStore } from '@/stores/ontology-store';
import { getNodeColor } from '@/lib/graph-theme';
import { applyLayout } from '@/lib/graph-layouts';

export function OntologyCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const ontology = useOntologyStore((s) => s.ontology);
  const selectedNodeId = useOntologyStore((s) => s.selectedNodeId);
  const setSelectedNode = useOntologyStore((s) => s.setSelectedNode);

  // Build graph from ontology data
  const buildGraph = useCallback(() => {
    if (!ontology || !selectedNodeId) return null;

    const graph = new Graph({ multi: true });

    // Find connected nodes (selected + direct neighbors)
    const connectedNodeIds = new Set<string>([selectedNodeId]);
    ontology.edges.forEach((edge) => {
      if (edge.source === selectedNodeId) connectedNodeIds.add(edge.target);
      if (edge.target === selectedNodeId) connectedNodeIds.add(edge.source);
    });

    // Add nodes
    ontology.nodes.forEach((node) => {
      if (connectedNodeIds.has(node.id)) {
        graph.addNode(node.id, {
          x: Math.random() * 500,
          y: Math.random() * 500,
          label: node.label,
          color: getNodeColor(node.id),
          size: node.id === selectedNodeId ? 15 : 10,
          nodeType: node.id,
          type: 'circle',
        });
      }
    });

    // Add edges (only between connected nodes)
    ontology.edges.forEach((edge) => {
      if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
        graph.addEdge(edge.source, edge.target, {
          label: edge.label,
          color: '#94a3b8',
          size: 2,
        });
      }
    });

    // Apply ForceAtlas2 layout
    applyLayout(graph, 'forceatlas2');

    return graph;
  }, [ontology, selectedNodeId]);

  // Initialize and manage Sigma instance
  useEffect(() => {
    if (!containerRef.current || !ontology || !selectedNodeId) return;

    const graph = buildGraph();
    if (!graph) return;

    // Destroy previous instance
    if (sigmaRef.current) {
      sigmaRef.current.kill();
    }

    const sigma = new Sigma(graph, containerRef.current, {
      renderEdgeLabels: true,
      defaultEdgeType: 'arrow',
      labelFont: 'Inter, system-ui, sans-serif',
      labelSize: 12,
      labelRenderedSizeThreshold: 4,
      minCameraRatio: 0.1,
      maxCameraRatio: 10,
    });

    sigmaRef.current = sigma;

    // Click handler
    sigma.on('clickNode', ({ node }) => {
      setSelectedNode(node);
    });

    sigma.on('clickStage', () => {
      // Keep current selection
    });

    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [ontology, selectedNodeId, buildGraph, setSelectedNode]);

  if (!selectedNodeId) return null;

  return (
    <div ref={containerRef} className="flex-1" />
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/ontology-canvas.tsx
git commit -m "feat: add OntologyCanvas Sigma.js renderer"
```

---

### Task 12: Create Detail Panel

**Files:**
- Create: `web_service/components/memory-schema/detail-panel.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/detail-panel.tsx`:

```typescript
'use client';

import { useOntologyStore } from '@/stores/ontology-store';

export function DetailPanel() {
  const ontology = useOntologyStore((s) => s.ontology);
  const selectedNodeId = useOntologyStore((s) => s.selectedNodeId);

  if (!ontology || !selectedNodeId) return null;

  const selectedNode = ontology.nodes.find((n) => n.id === selectedNodeId);
  if (!selectedNode) return null;

  // Find connected nodes
  const connectedEdges = ontology.edges.filter(
    (e) => e.source === selectedNodeId || e.target === selectedNodeId,
  );
  const connectedNodeIds = new Set<string>();
  connectedEdges.forEach((e) => {
    if (e.source !== selectedNodeId) connectedNodeIds.add(e.source);
    if (e.target !== selectedNodeId) connectedNodeIds.add(e.target);
  });
  const connectedNodes = ontology.nodes.filter((n) => connectedNodeIds.has(n.id));

  return (
    <div className="w-80 border-l bg-background overflow-y-auto flex flex-col">
      {/* Selected node header */}
      <div className="border-b px-4 py-3">
        <h3 className="text-sm font-medium">{selectedNode.label}</h3>
        {selectedNode.description && (
          <p className="text-xs text-muted-foreground mt-1">{selectedNode.description}</p>
        )}
      </div>

      {/* Four columns for selected node */}
      <div className="flex flex-col gap-3 p-3">
        <DetailColumn title={`Episodes (${selectedNode.episodes.length})`}>
          {selectedNode.episodes.slice(0, 5).map((e) => (
            <div key={e.id} className="rounded border px-2 py-0.5 text-xs truncate">
              {e.name}
            </div>
          ))}
        </DetailColumn>

        <DetailColumn title={`Entities (${selectedNode.entities.length})`}>
          {selectedNode.entities.slice(0, 5).map((e) => (
            <div key={e.id} className="rounded border px-2 py-0.5 text-xs truncate">
              {e.name}
            </div>
          ))}
        </DetailColumn>

        <DetailColumn title={`Types (${selectedNode.attributes.length})`}>
          {selectedNode.attributes.map((a) => (
            <div key={a.name} className="rounded border px-2 py-0.5 text-xs truncate">
              {a.name}: {a.type}
            </div>
          ))}
        </DetailColumn>

        <DetailColumn title={`Summaries (${selectedNode.summaries.length})`}>
          {selectedNode.summaries.slice(0, 5).map((s) => (
            <div key={s.id} className="rounded border px-2 py-0.5 text-xs truncate">
              {s.content}
            </div>
          ))}
        </DetailColumn>
      </div>

      {/* Connected nodes */}
      {connectedNodes.length > 0 && (
        <div className="border-t p-3">
          <h4 className="text-xs font-medium text-muted-foreground mb-2">Connections</h4>
          <div className="space-y-2">
            {connectedNodes.map((node) => {
              const edge = connectedEdges.find(
                (e) => e.source === node.id || e.target === node.id,
              );
              return (
                <div key={node.id} className="rounded border p-2">
                  <div className="text-xs font-medium">{node.label}</div>
                  {edge && (
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {edge.label}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function DetailColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground mb-1">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/detail-panel.tsx
git commit -m "feat: add DetailPanel component for selected ontology node"
```

---

### Task 13: Create Layout Controls

**Files:**
- Create: `web_service/components/memory-schema/layout-controls.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/layout-controls.tsx`:

```typescript
'use client';

import { Button } from '@/components/ui/button';
import { Maximize, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import { useRef } from 'react';
import type Sigma from 'sigma';

interface LayoutControlsProps {
  getSigma: () => Sigma | null;
}

export function LayoutControls({ getSigma }: LayoutControlsProps) {
  const sigmaRef = useRef<Sigma | null>(null);

  const handleZoom = () => {
    const sigma = getSigma();
    if (!sigma) return;
    sigma.getCamera().animatedZoom({ duration: 200 });
  };

  const handleUnzoom = () => {
    const sigma = getSigma();
    if (!sigma) return;
    sigma.getCamera().animatedUnzoom({ duration: 200 });
  };

  const handleFit = () => {
    const sigma = getSigma();
    if (!sigma) return;
    sigma.getCamera().animate({ x: 0.5, y: 0.5, ratio: 1 }, { duration: 200 });
  };

  const handleFullscreen = () => {
    document.documentElement.requestFullscreen?.();
  };

  return (
    <div className="flex items-center gap-1">
      <Button variant="outline" size="icon-sm" onClick={handleZoom} aria-label="Zoom in">
        <ZoomIn className="h-4 w-4" />
      </Button>
      <Button variant="outline" size="icon-sm" onClick={handleUnzoom} aria-label="Zoom out">
        <ZoomOut className="h-4 w-4" />
      </Button>
      <Button variant="outline" size="icon-sm" onClick={handleFit} aria-label="Fit to screen">
        <RotateCcw className="h-4 w-4" />
      </Button>
      <Button variant="outline" size="icon-sm" onClick={handleFullscreen} aria-label="Fullscreen">
        <Maximize className="h-4 w-4" />
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/layout-controls.tsx
git commit -m "feat: add LayoutControls component for ontology graph"
```

---

### Task 14: Create Legend

**Files:**
- Create: `web_service/components/memory-schema/legend.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/legend.tsx`:

```typescript
'use client';

import { useOntologyStore } from '@/stores/ontology-store';
import { getNodeColor } from '@/lib/graph-theme';

export function Legend() {
  const ontology = useOntologyStore((s) => s.ontology);

  if (!ontology) return null;

  return (
    <div className="flex items-center gap-3 border-t px-4 py-2">
      <span className="text-xs text-muted-foreground">
        节点: {ontology.nodes.length} | 边: {ontology.edges.length}
      </span>
      <div className="flex-1" />
      <div className="flex items-center gap-2">
        {ontology.nodes.slice(0, 8).map((node) => (
          <div key={node.id} className="flex items-center gap-1">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: getNodeColor(node.id) }}
            />
            <span className="text-xs text-muted-foreground">{node.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/legend.tsx
git commit -m "feat: add Legend component for ontology view"
```

---

### Task 15: Create Selected View

**Files:**
- Create: `web_service/components/memory-schema/selected-view.tsx`

- [ ] **Step 1: Write the component**

Create `web_service/components/memory-schema/selected-view.tsx`:

```typescript
'use client';

import { useRef } from 'react';
import type Sigma from 'sigma';
import { useOntologyStore } from '@/stores/ontology-store';
import { OntologyCanvas } from './ontology-canvas';
import { DetailPanel } from './detail-panel';
import { LayoutControls } from './layout-controls';

export function SelectedView() {
  const sigmaRef = useRef<Sigma | null>(null);
  const resetView = useOntologyStore((s) => s.resetView);

  const getSigma = () => sigmaRef.current;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <button
          onClick={resetView}
          className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
        >
          ← 返回全图
        </button>
        <div className="flex-1" />
        <LayoutControls getSigma={getSigma} />
      </div>

      {/* Main area */}
      <div className="flex flex-1 min-h-0">
        <OntologyCanvas />
        <DetailPanel />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/components/memory-schema/selected-view.tsx
git commit -m "feat: add SelectedView component with graph and detail panel"
```

---

### Task 16: Create Main Client Component

**Files:**
- Create: `web_service/app/memory-schema/memory-schema-client.tsx`

- [ ] **Step 1: Write the main component**

Create `web_service/app/memory-schema/memory-schema-client.tsx`:

```typescript
'use client';

import { useCallback, useEffect, useState } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';
import { OntologySelector } from '@/components/memory-schema/ontology-selector';
import { DefaultView } from '@/components/memory-schema/default-view';
import { SelectedView } from '@/components/memory-schema/selected-view';
import { Legend } from '@/components/memory-schema/legend';
import type {
  ExtractionSchema,
  OntologyGraph,
  OntologyNode,
  OntologyEdge,
  EpisodeItem,
  EntityItem,
  SummaryItem,
} from '@/lib/types';

export default function MemorySchemaClient() {
  const viewMode = useOntologyStore((s) => s.viewMode);
  const setSchemas = useOntologyStore((s) => s.setSchemas);
  const selectedSchemaId = useOntologyStore((s) => s.selectedSchemaId);
  const setSelectedSchemaId = useOntologyStore((s) => s.setSelectedSchemaId);
  const setOntology = useOntologyStore((s) => s.setOntology);
  const setLoading = useOntologyStore((s) => s.setLoading);
  const setError = useOntologyStore((s) => s.setError);
  const ontology = useOntologyStore((s) => s.ontology);

  // Fetch schema list on mount
  useEffect(() => {
    fetch('/api/schemas')
      .then((res) => (res.ok ? res.json() : []))
      .then((data: { id: number; name: string }[]) => {
        setSchemas(data);
      })
      .catch((err) => console.error('Failed to load schemas:', err));
  }, [setSchemas]);

  // Fetch ontology data when schema selection changes
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function loadOntology() {
      try {
        if (selectedSchemaId !== null) {
          // Custom schema: fetch schema definition + graph data
          const [schemaRes, graphRes] = await Promise.all([
            fetch(`/api/schemas/${selectedSchemaId}`),
            fetch('/api/graph/query', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ limit: 500 }),
            }),
          ]);

          if (!schemaRes.ok) throw new Error('Failed to fetch schema');
          const schema: ExtractionSchema = await schemaRes.json();
          const graphData = await graphRes.json();

          if (cancelled) return;
          const ontology = buildOntologyFromSchema(schema, graphData);
          setOntology(ontology);
        } else {
          // Default ontology: build from graph data
          const [graphRes, timelineRes] = await Promise.all([
            fetch('/api/graph/query', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ limit: 500 }),
            }),
            fetch('/api/graph/timeline'),
          ]);

          const graphData = await graphRes.json();
          const timeline = await timelineRes.json();

          if (cancelled) return;
          const ontology = buildOntologyFromGraph(graphData, timeline);
          setOntology(ontology);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load ontology');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadOntology();
    return () => {
      cancelled = true;
    };
  }, [selectedSchemaId, setOntology, setLoading, setError]);

  const loading = useOntologyStore((s) => s.loading);
  const error = useOntologyStore((s) => s.error);

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b px-4 py-2">
        <OntologySelector />
        <div className="flex-1" />
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          加载中...
        </div>
      ) : error ? (
        <div className="flex flex-1 items-center justify-center text-destructive">
          {error}
        </div>
      ) : (
        <>
          {viewMode === 'default' ? <DefaultView /> : <SelectedView />}
          <Legend />
        </>
      )}
    </div>
  );
}

// ─── Data transformation helpers ───

function buildOntologyFromSchema(
  schema: ExtractionSchema,
  graphData: { nodes: any[]; edges: any[] },
): OntologyGraph {
  // Build entity instances map: type -> entities
  const entitiesByType = new Map<string, EntityItem[]>();
  const summariesByType = new Map<string, SummaryItem[]>();
  
  for (const node of graphData.nodes || []) {
    const labels = node.labels || [];
    const type = labels[0] || 'Entity';
    
    if (!entitiesByType.has(type)) {
      entitiesByType.set(type, []);
      summariesByType.set(type, []);
    }
    
    entitiesByType.get(type)!.push({
      id: node.id,
      name: node.name || '',
      summary: node.summary || '',
    });
    
    if (node.summary) {
      summariesByType.get(type)!.push({
        id: node.id,
        content: node.summary,
      });
    }
  }

  // Build ontology nodes from schema entity_types
  const nodes: OntologyNode[] = schema.entity_types.map((et) => ({
    id: et.name,
    label: et.name,
    type: 'entity',
    attributes: et.attributes,
    description: et.description,
    episodes: [],  // Episodes not available from schema alone
    entities: entitiesByType.get(et.name) || [],
    summaries: summariesByType.get(et.name) || [],
  }));

  // Build ontology edges from schema edge_types
  const edges: OntologyEdge[] = schema.edge_types.map((et) => ({
    id: et.name,
    source: et.source_types?.[0] || '',
    target: et.target_types?.[0] || '',
    label: et.name,
    attributes: et.attributes,
    description: et.description,
  }));

  return { nodes, edges, source: 'schema', schemaId: schema.id, schemaName: schema.name };
}

function buildOntologyFromGraph(
  graphData: { nodes: any[]; edges: any[] },
  timeline: any[],
): OntologyGraph {
  // Group nodes by label
  const entitiesByType = new Map<string, EntityItem[]>();
  const summariesByType = new Map<string, SummaryItem[]>();
  const episodesByType = new Map<string, EpisodeItem[]>();

  for (const node of graphData.nodes || []) {
    const labels = node.labels || [];
    const type = labels[0] || 'Entity';
    
    if (!entitiesByType.has(type)) {
      entitiesByType.set(type, []);
      summariesByType.set(type, []);
    }
    
    entitiesByType.get(type)!.push({
      id: node.id,
      name: node.name || '',
      summary: node.summary || '',
    });
    
    if (node.summary) {
      summariesByType.get(type)!.push({
        id: node.id,
        content: node.summary,
      });
    }
  }

  // Group episodes by connected entity type via entity_edges
  // The timeline returns episode metadata; we need episodic_edges to link episodes to entities
  // For the default ontology, fetch episodic_edges to map episodes → entities → types
  // This requires an additional API call or including episode-entity links in the timeline response
  // Simplified approach: skip episodes in default ontology (leave empty) if data not available
  // TODO: Enhance timeline endpoint to include entity_labels per episode

  // Infer type attributes from entity_nodes
  const typesByType = new Map<string, Set<string>>();
  for (const node of graphData.nodes || []) {
    const labels = node.labels || [];
    const type = labels[0] || 'Entity';
    if (!typesByType.has(type)) {
      typesByType.set(type, new Set());
    }
    const attrs = node.attributes || {};
    Object.keys(attrs).forEach((key) => typesByType.get(type)!.add(key));
  }

  // Build ontology nodes
  const nodes: OntologyNode[] = Array.from(entitiesByType.keys()).map((type) => {
    const attrNames = Array.from(typesByType.get(type) || []);
    return {
      id: type,
      label: type,
      type: 'entity',
      attributes: attrNames.map((name) => ({ name, type: 'str', description: '' })),
      description: '',
      episodes: episodesByType.get(type) || [],
      entities: entitiesByType.get(type) || [],
      summaries: summariesByType.get(type) || [],
    };
  });

  // Build ontology edges from actual graph edges
  const edgeTypeMap = new Map<string, { source: Set<string>; target: Set<string> }>();
  for (const edge of graphData.edges || []) {
    const edgeName = edge.label || edge.name || 'UNKNOWN';
    if (!edgeTypeMap.has(edgeName)) {
      edgeTypeMap.set(edgeName, { source: new Set(), target: new Set() });
    }
    // Find source/target node types
    const sourceNode = (graphData.nodes || []).find((n: any) => n.id === edge.source);
    const targetNode = (graphData.nodes || []).find((n: any) => n.id === edge.target);
    if (sourceNode) {
      const sourceType = sourceNode.labels?.[0] || 'Entity';
      edgeTypeMap.get(edgeName)!.source.add(sourceType);
    }
    if (targetNode) {
      const targetType = targetNode.labels?.[0] || 'Entity';
      edgeTypeMap.get(edgeName)!.target.add(targetType);
    }
  }

  const edges: OntologyEdge[] = Array.from(edgeTypeMap.entries()).map(
    ([name, { source, target }]) => ({
      id: name,
      source: Array.from(source)[0] || '',
      target: Array.from(target)[0] || '',
      label: name,
      attributes: [],
      description: '',
    }),
  );

  return { nodes, edges, source: 'graph' };
}
```

- [ ] **Step 2: Commit**

```bash
git add web_service/app/memory-schema/memory-schema-client.tsx
git commit -m "feat: add MemorySchemaClient main component with data fetching"
```

---

## Phase 5: Integration & Polish

### Task 17: Add BFF Route for Schema Detail

**Files:**
- Modify: `web_service/app/api/schemas/[id]/route.ts` (or create if not exists)

- [ ] **Step 1: Verify the existing schema detail route works**

Read `web_service/app/api/schemas/[id]/route.ts`. It should already proxy to `GET /rest/schemas/{id}`. If the route exists and returns the full schema with entity_types/edge_types, no changes needed.

If changes are needed, ensure the route returns the full schema including the new `source_types`/`target_types` fields.

- [ ] **Step 2: Commit (if changes made)**

```bash
git add web_service/app/api/schemas/[id]/route.ts
git commit -m "feat: ensure schema detail route returns source_types/target_types"
```

---

### Task 18: Verify End-to-End

- [ ] **Step 1: Start the server**

```bash
cd server && uvicorn graph_service.main:app --reload
```

- [ ] **Step 2: Start the frontend**

```bash
cd web_service && npm run dev
```

- [ ] **Step 3: Navigate to `/memory-schema`**

Verify:
- Default view shows entity type cards with 4 columns
- Each column shows count and caps at 5 items with "+ N more"
- Clicking a card switches to selected view with graph + detail panel
- Selector switches between custom schemas and default ontology
- Layout controls (zoom/fit/fullscreen) work in selected view
- Back button returns to default view

- [ ] **Step 4: Test backend type mapping**

Create a test schema, ingest data with it, then verify:
```bash
curl http://localhost:8000/rest/schemas/{id} | jq '.edge_types'
```
Should show `source_types` and `target_types` populated.

---

## Verification Checklist

- [ ] Sidebar shows "Memory Schema" nav item
- [ ] `/memory-schema` page loads with card grid default view
- [ ] Each entity type card has 4 columns: Episodes, Entities, Types, Summaries
- [ ] Each column shows count in header
- [ ] Items capped at 5, with "+ N more" expand button
- [ ] Clicking a card shows relationship graph + right detail panel
- [ ] Detail panel shows 4-column detail for selected type
- [ ] Layout controls (zoom/fit/fullscreen) work
- [ ] Legend shows node/edge counts and color legend
- [ ] Ontology selector switches between schemas and default
- [ ] "+ 新建" links to `/settings/schemas/new`
- [ ] Backend saves `source_types`/`target_types` during extraction
- [ ] Old schemas without new fields still work (backward compatible)

---

## Entity Classification Implementation Plan

> 对应设计：`docs/superpowers/specs/2026-08-12-memory-schema-design.md` 的 Entity Classification 补充设计。

**Goal:** 让未选择自定义 schema 的实体提取默认产出 Person、Organization、Location、Object、Document、Event、Topic 等具体 labels，并让 Memory Schema 按这些具体类型分组展示。

**Feasibility:** 改动整体容易实现，核心链路已经存在，不需要数据库迁移，也不需要改 LLM 输出 schema。主要工作量集中在“默认类型注入”和“Memory Schema 对 `Entity` 的过滤”。真正需要额外控制风险的是存量数据回填和 LLM 分类质量。

### 实现任务

#### Task 1: 新增内置默认实体类型

**Files:**
- Modify: `server/graph_service/models.py`

**Step 1: 新增 `DEFAULT_ENTITY_TYPES`**

在 `server/graph_service/models.py` 中定义一组 Pydantic 模型，docstring 作为 LLM 分类描述。`Entity` 不需要加入，因为 Graphiti 的 `_build_entity_types_context()` 始终会把 `Entity` 作为 id 0 保留。

```python
class Person(BaseModel):
    """A Person represents a named or clearly identifiable individual."""


class Organization(BaseModel):
    """An Organization represents a company, institution, team, or association."""


class Location(BaseModel):
    """A Location represents a physical or virtual place."""


class Object(BaseModel):
    """An Object represents a physical item, tool, device, or possession."""


class Document(BaseModel):
    """A Document represents information content such as reports, articles, emails, videos, or podcasts."""


class Event(BaseModel):
    """An Event represents a named or time-bound occurrence."""


class Topic(BaseModel):
    """A Topic represents a subject, hobby, or knowledge domain."""


DEFAULT_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    'Person': Person,
    'Organization': Organization,
    'Location': Location,
    'Object': Object,
    'Document': Document,
    'Event': Event,
    'Topic': Topic,
}
```

v1 默认类型不配置 attributes，避免触发额外 attribute extraction；分类描述放在 docstring 即可。

**Step 2: Commit**

```bash
git add server/graph_service/models.py
git commit -m "feat: add default entity types for extraction"
```

---

#### Task 2: 未选择 schema 时注入默认分类

**Files:**
- Modify: `server/graph_service/routers/ingest.py`

**Step 1: 修改 `_resolve_schema_params()`**

当 `schema_id is None` 时返回默认类型；当用户选择了 schema 但 `entity_types` 为空时也回退到默认类型，避免再次出现全部 `['Entity']` 的结果。

```python
async def _resolve_schema_params(schema_id: int | None):
    if schema_id is None:
        return DEFAULT_ENTITY_TYPES, None, None

    from graph_service.config import get_settings
    from graph_service.models import build_extraction_params, get_schema

    settings = get_settings()
    schema = await get_schema(settings.postgres_age_dsn, schema_id)
    if not schema:
        return DEFAULT_ENTITY_TYPES, None, None

    entity_types, edge_types, custom_instructions = build_extraction_params(schema)
    if not entity_types:
        entity_types = DEFAULT_ENTITY_TYPES

    return entity_types, edge_types, custom_instructions
```

该 helper 同时覆盖 `add_episode` 和 `preview_memory`，无需在每条 ingestion 路由重复改动。

**Step 2: Commit**

```bash
git add server/graph_service/routers/ingest.py
git commit -m "feat: inject default entity types when schema is empty"
```

---

#### Task 3: Memory Schema 按具体类型分组

**Files:**
- Modify: `server/graph_service/routers/graph.py`

**Step 1: 过滤 `Entity` 常规分组**

在 `GET /rest/memory-schema` 的实体卡片构建逻辑中，改为读取完整 `labels` 后在 Python 内分组：

- 每个实体的具体 labels = `labels - {'Entity'}`
- 有具体 labels 的实体只进入对应具体类型卡
- 没有具体 labels 的实体进入 `ENTITY` 兜底卡
- TYPES 列只列出具体 labels，不列出 `Entity`
- Detail Panel 仍可保留完整 labels 作为 type tag

这样 `['Entity', 'Person']` 只出现在 PERSON 卡，`['Entity']` 出现在 ENTITY 兜底卡。

**Step 2: Commit**

```bash
git add server/graph_service/routers/graph.py
git commit -m "feat: group memory schema entities by specific labels"
```

---

#### Task 4: 节点编辑入口支持类型选择

**Files:**
- Modify: `web_service/components/ingest/node-edit-dialog.tsx`

**Step 1: 将 labels 输入从自由文本升级为可选项**

保留手动输入能力，但提供默认类型候选，降低用户手写 typo 概率。可选实现，不阻塞核心分类链路。

**Step 2: Commit**

```bash
git add web_service/components/ingest/node-edit-dialog.tsx
git commit -m "feat: add entity type suggestions to node edit dialog"
```

---

#### Task 5: 存量数据回填（独立任务）

**Files:**
- Create: `server/graph_service/scripts/backfill_entity_types.py`（如不存在 scripts 目录则创建）

**Step 1: 实现一次性回填脚本**

1. 查询 `labels = ['Entity']` 的实体。
2. 按批读取 `name`、`summary`、`attributes`。
3. 调用 LLM，使用 `DEFAULT_ENTITY_TYPES` 或指定 schema 分类。
4. 保留 UUID、embedding、关系、summary，只更新 `labels`。
5. 支持 `--group-id`、`--schema-id`、`--limit`、`--dry-run`。

回填脚本不接入常规 extraction 流程，由运维或开发显式执行。

**Step 2: Commit**

```bash
git add server/graph_service/scripts/backfill_entity_types.py
git commit -m "feat: add one-off entity type backfill script"
```

---

#### Task 6: 测试与验证

**Files:**
- Create: `server/tests/test_entity_classification.py`

**Step 1: 添加单元测试**

- `schema_id=None` 时返回 `DEFAULT_ENTITY_TYPES`
- schema 存在但 `entity_types=[]` 时回退默认类型
- 自定义 schema 优先于默认类型
- Memory Schema 分组逻辑对 `['Entity', 'Person']` 只生成 PERSON 卡
- 仅有 `['Entity']` 的节点生成 ENTITY 兜底卡

**Step 2: 端到端验证**

- 无 schema 导入一段含人物、组织、地点的内容
- 查询 `entity_nodes.labels`，确认不再全部是 `['Entity']`
- 打开 `/memory-schema`，确认出现多张具体类型卡
- 确认没有重复的 ENTITY 卡

**Step 3: Commit**

```bash
git add server/tests/test_entity_classification.py
git commit -m "test: cover default entity type injection and grouping"
```

---

### 验收清单

- [ ] 无 schema 时提取节点包含具体 labels
- [ ] 自定义 schema 优先于默认分类
- [ ] 空 schema 回退到默认分类
- [ ] Memory Schema 按具体类型生成多张卡
- [ ] `Entity` 不作为常规分组，仅作为兜底卡
- [ ] 存量数据回填脚本支持 dry-run 和批量执行
- [ ] 相关单元测试通过
