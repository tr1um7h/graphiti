// lib/types.ts
// Global TypeScript type definitions for the knowledge graph platform

// ─── Graph Related ───

export interface GraphNode {
  id: string;
  label: string;
  type: string; // Person, Company, Project, Fund, Organization, etc.
  attributes: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string; // relationship type
  fact: string; // natural language description
  validAt: string | null;
  invalidAt: string | null;
}

export interface GraphStats {
  totalNodes: number;
  totalEdges: number;
  totalDocuments?: number;
  todayNewDocuments?: number;
  nodeTypes: { type: string; count: number }[];
  edgeTypes: { type: string; count: number }[];
  todayNewNodes: number;
  todayNewEdges: number;
}

export interface Relationship {
  id: string;
  target_id: string;
  target_name: string;
  target_type: string;
  relationship_type: string;
  fact: string;
  valid_at: string | null;
  invalid_at: string | null;
  source: 'graphiti' | 'cognee';
}

export interface DocumentRef {
  id: string;
  name: string;
  chunks_count: number;
  source: 'graphiti' | 'cognee';
}

export interface Episode {
  id: string;
  content: string;
  created_at: string;
  source: 'graphiti';
}

export interface TimelineEntry {
  fact: string;
  valid_at: string;
  invalid_at: string | null;
  status: 'current' | 'expired';
}

export interface Source {
  id: string;
  type: 'document' | 'episode';
  name: string;
  detail?: string;
  source: 'graphiti' | 'cognee';
}

export interface EntityDetail {
  id: string;
  name: string;
  type: string;
  summary: string;
  attributes: Record<string, unknown>;
  relationships: Relationship[];
  documents: DocumentRef[];
  episodes: Episode[];
  timeline: TimelineEntry[];
}

export interface NeighborsResponse {
  center: EntityDetail;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─── Document Related ───

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface Document {
  id: string;
  name: string;
  type: string; // PDF, DOCX, TXT, URL...
  status: DocumentStatus;
  entityCount: number;
  createdAt: string;
  group_id: string;
}

// ─── Explore Chat ───

export interface ExploreChatRequest {
  message: string;
  centerEntityId: string;
  visibleNodeIds: string[];
  sessionId?: string;
}

export interface ExploreChatResponse {
  answer: string;
  sources: Source[];
  highlightNodes?: string[];
  switchCenter?: string;
  switchDepth?: 1 | 2;
}

// ─── Search / Filter ───

export interface SearchParams {
  q: string;
  type?: string;
  limit?: number;
}

export interface TimeRange {
  start: Date;
  end: Date;
}

// ─── Graph API Response ───

export interface GraphApiResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─── Upload Response ───

export interface UploadResponse {
  id: string;
  name: string;
  status: DocumentStatus;
  group_id: string;
}

// ─── Data Management ───

export interface GroupStats {
  group_id: string;
  created_at: string | null;
  node_count: number;
  edge_count: number;
  table_counts: Record<string, number>;
}

export interface GroupDetail {
  group_id: string;
  table: string | null;
  page: number;
  size: number;
  total: number;
  table_counts: Record<string, number>;
  records: Record<string, unknown>[];
}

export interface PatchSummary {
  added: number;
  removed: number;
  modified: number;
  conflicts: number;
}

export interface PatchPreview {
  version: number;
  metadata: {
    from_group_id?: string;
    to_group_id?: string;
    created_at?: string;
  };
  summary: Record<string, PatchSummary>;
}

export interface PatchApplyResult {
  success: boolean;
  dry_run: boolean;
  added: number;
  removed: number;
  modified: number;
  conflicts: number;
}

export type ConflictStrategy = 'ours' | 'theirs' | 'skip-conflicts';
