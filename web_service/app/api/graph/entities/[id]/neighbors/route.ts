// app/api/graph/entities/[id]/neighbors/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import type { NeighborsResponse } from '@/lib/types';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  const depth = parseInt(searchParams.get('depth') || '1');

  try {
    // Backend returns nodes/edges in snake_case format that doesn't match
    // GraphNodeSchema/GraphEdgeSchema directly. Transform to our expected shape
    // (same logic as subgraph/route.ts).
    const rawData = await fetchFromBackend<any>(
      `/rest/graph/entities/${encodeURIComponent(id)}/neighbors?depth=${depth}`,
    );

    if (!rawData) {
      return Response.json({ center: null, nodes: [], edges: [] });
    }

    const center = rawData.center;
    const neighborNodes: any[] = rawData.nodes || [];
    const neighborEdges: any[] = rawData.edges || [];

    const nodes = neighborNodes.map((node: any) => ({
      id: node.id,
      label: node.labels?.[0] || 'Entity',
      type: node.labels?.[0] || 'Entity',
      attributes: {
        name: node.name,
        summary: node.summary,
        ...(node.attributes || {}),
      },
    }));

    const edges = neighborEdges.map((edge: any) => ({
      id: edge.id,
      source: edge.source_node_uuid || edge.source,
      target: edge.target_node_uuid || edge.target,
      label: edge.name,
      fact: edge.fact,
      validAt: edge.valid_at || null,
      invalidAt: edge.invalid_at || null,
    }));

    return Response.json({ center, nodes, edges });
  } catch (error) {
    console.error('Entity neighbors error:', error);
    return Response.json({ center: null, nodes: [], edges: [] });
  }
}
