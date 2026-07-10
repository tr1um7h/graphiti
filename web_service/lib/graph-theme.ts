// lib/graph-theme.ts

export const NODE_COLORS: Record<string, string> = {
  default: '#6366f1',
  Entity: '#6366f1',
  Preference: '#f59e0b',
  Procedure: '#10b981',
  Requirement: '#ef4444',
  Person: '#8b5cf6',
  Organization: '#3b82f6',
  Location: '#14b8a6',
  Event: '#f97316',
  Concept: '#ec4899',
};

export function getNodeColor(type?: string): string {
  if (!type) return NODE_COLORS.default;
  return NODE_COLORS[type] || NODE_COLORS.default;
}

export function getNodeSize(attributes?: Record<string, unknown>): number {
  if (!attributes) return 8;
  const count = Object.keys(attributes).length;
  return Math.max(6, Math.min(16, 6 + count * 0.5));
}
