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
  source: 'graphiti';
}

export interface DocumentRef {
  id: string;
  name: string;
  chunks_count: number;
  source: 'graphiti';
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
  createdAt: string;
  group_id: string;
}

// ─── Graph API Response ───

export interface GraphApiResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─── Chat Related ───

export interface ChatContext {
  context_id?: string;       // group_id, node_id, edge_id, document_id
  context_type?: string;     // 'group' | 'node' | 'edge' | 'document'
  context_name?: string;     // for display only
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export interface ChatRequest {
  message: string;
  context: ChatContext;
  history: ChatMessage[];
}

export interface ChatResponse {
  answer: string;
}
