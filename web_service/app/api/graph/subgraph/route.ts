// app/api/graph/subgraph/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { GraphApiResponseSchema } from '@/lib/schemas';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const nodeId = searchParams.get('nodeId');
    if (!nodeId) {
      return Response.json({ error: 'nodeId is required' }, { status: 400 });
    }

    // Call Server's /rest/graph/entities/{node_id}/neighbors endpoint
    // which returns the center node + 1-hop neighbors + edges
    const neighborData = await fetchFromBackend(
      `/rest/graph/entities/${encodeURIComponent(nodeId)}/neighbors?depth=1`,
    );

    if (!neighborData) {
      return Response.json({ nodes: [], edges: [] });
    }

    // Transform the neighbors response into GraphApiResponse format.
    // Include the center node so it appears in the sub-graph.
    const rawData = neighborData as any;
    const center = rawData.center;
    const neighborNodes: any[] = rawData.nodes || [];
    const neighborEdges: any[] = rawData.edges || [];

    // Build the full node list: center + neighbors
    const allNodes = [
      ...(center
        ? [
            {
              id: center.id,
              label: center.labels?.[0] || 'Entity',
              type: center.labels?.[0] || 'Entity',
              attributes: {
                name: center.name,
                summary: center.summary,
                ...(center.attributes || {}),
              },
            },
          ]
        : []),
      ...neighborNodes.map((node: any) => ({
        id: node.id,
        label: node.labels?.[0] || 'Entity',
        type: node.labels?.[0] || 'Entity',
        attributes: {
          name: node.name,
          summary: node.summary,
          ...(node.attributes || {}),
        },
      })),
    ];

    const allEdges = neighborEdges.map((edge: any) => ({
      id: edge.id,
      source: edge.source_node_uuid || edge.source,
      target: edge.target_node_uuid || edge.target,
      label: edge.name,
      fact: edge.fact,
      validAt: edge.valid_at || null,
      invalidAt: edge.invalid_at || null,
    }));

    const transformedData = { nodes: allNodes, edges: allEdges };
    const validated = GraphApiResponseSchema.parse(transformedData);
    return Response.json(validated);
  } catch (error) {
    console.error('❌ Subgraph query error:', error);
    return Response.json({ nodes: [], edges: [] });
  }
}
