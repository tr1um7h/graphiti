// app/api/graph/stats/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { GraphStatsSchema } from '@/lib/schemas';
import type { GraphStats } from '@/lib/types';

interface SchemaResponse {
  nodeLabels: { label: string; count: number }[];
  relationshipTypes: { type: string; count: number }[];
}

export async function GET() {
  try {
    // 并行调用 stats 和 schema，合并返回
    const [statsData, schemaData] = await Promise.all([
      fetchFromBackend('/rest/graph/stats').catch(() => null),
      fetchFromBackend<SchemaResponse>('/rest/graph/schema').catch(() => null),
    ]);

    // 将 schema 中的 nodeLabels 映射为 nodeTypes，relationshipTypes 映射为 edgeTypes
    const nodeTypes = (schemaData?.nodeLabels || []).map((n) => ({
      type: n.label,
      count: n.count,
    }));
    const edgeTypes = (schemaData?.relationshipTypes || []).map((e) => ({
      type: e.type,
      count: e.count,
    }));

    const result: GraphStats = {
      totalNodes: (statsData as { totalNodes?: number })?.totalNodes ?? 0,
      totalEdges: (statsData as { totalEdges?: number })?.totalEdges ?? 0,
      totalDocuments: (statsData as { totalDocuments?: number })?.totalDocuments ?? 0,
      todayNewDocuments: (statsData as { todayNewDocuments?: number })?.todayNewDocuments ?? 0,
      nodeTypes,
      edgeTypes,
      todayNewNodes: (statsData as { todayNewNodes?: number })?.todayNewNodes ?? 0,
      todayNewEdges: (statsData as { todayNewEdges?: number })?.todayNewEdges ?? 0,
    };

    const validated = GraphStatsSchema.parse(result);
    return Response.json(validated);
  } catch (error) {
    console.error('Graph stats error:', error);
    return Response.json({
      totalNodes: 0,
      totalEdges: 0,
      nodeTypes: [],
      edgeTypes: [],
      todayNewNodes: 0,
      todayNewEdges: 0,
    });
  }
}
