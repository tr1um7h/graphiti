// lib/schemas.ts
// Runtime validation schemas for backend (/rest/graph/*) responses.
//
// types.ts declares what we *expect*; these schemas check what we *actually
// receive* at the fetch boundary (lib/api-client.ts). Without them, a malformed
// or error payload (e.g. { error: ... } returned with HTTP 200, or shape drift
// after a backend change) is silently cast to <T> and can crash a consumer
// downstream (the NotFoundGraphError / TypeError class of bugs).
//
// Shapes mirror the Python serializers in mcp_server/src/rest_routes.py
// (_node_to_dict / _edge_to_dict / entity_detail / entity_neighbors / graph_*).

import { z } from 'zod';

// --- Graph node / edge (from _node_to_dict / _edge_to_dict) ---

export const GraphNodeSchema = z.object({
  id: z.string(),
  // _node_to_dict always sends the literal 'Entity' here; the real display
  // name lives in attributes.name. Validated as plain string (not refined)
  // so the vestigial value doesn't false-positive.
  label: z.string(),
  type: z.string(),
  attributes: z.record(z.string(), z.unknown()),
});

export const GraphEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  label: z.string(),
  fact: z.string(),
  // Backend sends camelCase (edge.valid_at -> 'validAt'), matching types.ts.
  validAt: z.string().optional().nullable(),
  invalidAt: z.string().optional().nullable(),
});

export const GraphApiResponseSchema = z.object({
  nodes: z.array(GraphNodeSchema),
  edges: z.array(GraphEdgeSchema),
});

// --- Entity detail (from entity_detail / entity_neighbors handlers) ---

export const RelationshipSchema = z.object({
  id: z.string(),
  target_id: z.string(),
  target_name: z.string(),
  target_type: z.string(),
  relationship_type: z.string(),
  fact: z.string(),
  valid_at: z.string().nullable(),
  invalid_at: z.string().nullable(),
  source: z.string(),
});

export const DocumentRefSchema = z.object({
  id: z.string(),
  name: z.string(),
  chunks_count: z.number(),
  source: z.string(),
});

export const EpisodeSchema = z.object({
  id: z.string(),
  content: z.string(),
  created_at: z.string().nullable(),
  source: z.string(),
});

export const TimelineEntrySchema = z.object({
  fact: z.string(),
  valid_at: z.string(),
  invalid_at: z.string().nullable(),
  status: z.string(),
});

export const EntityDetailSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.string(),
  summary: z.string(),
  attributes: z.record(z.string(), z.unknown()),
  // relationships/documents are the crash-relevant fields (consumers read
  // .length), so they MUST validate as arrays — this is the line that stops
  // an { error } payload from sneaking through as EntityDetail.
  relationships: z.array(RelationshipSchema),
  documents: z.array(DocumentRefSchema),
  episodes: z.array(EpisodeSchema),
  timeline: z.array(TimelineEntrySchema),
});

// neighbors handler returns center separately; nodes does NOT include center.
// center may be a partial entity (neighbors endpoint doesn't return full detail).
export const NeighborsResponseSchema = z.object({
  center: z
    .object({
      id: z.string(),
      name: z.string().optional(),
      summary: z.string().optional(),
      labels: z.array(z.string()).optional(),
      attributes: z.record(z.string(), z.unknown()).optional(),
    })
    .nullable()
    .optional(),
  nodes: z.array(GraphNodeSchema),
  edges: z.array(GraphEdgeSchema),
});

// --- Search results (from graph_search handler) ---

export const GraphSearchResultSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.string(),
});
export const GraphSearchResponseSchema = z.array(GraphSearchResultSchema);

// --- Stats (from graph_stats handler) ---

export const GraphStatsSchema = z.object({
  totalNodes: z.number(),
  totalEdges: z.number(),
  totalDocuments: z.number().optional(),
  todayNewDocuments: z.number().optional(),
  nodeTypes: z.array(z.object({ type: z.string(), count: z.number() })),
  edgeTypes: z.array(z.object({ type: z.string(), count: z.number() })),
  todayNewNodes: z.number(),
  todayNewEdges: z.number(),
});
