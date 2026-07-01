// app/api/graph/stats/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { GraphStatsSchema } from '@/lib/schemas';
import type { GraphStats } from '@/lib/types';

export async function GET() {
  try {
    // 调用 Server 的 /rest/graph/stats 端点获取真实统计数据
    const stats = await fetchFromBackend('/rest/graph/stats');
    
    if (!stats) {
      // 如果获取失败，返回默认统计数据
      return Response.json({
        totalNodes: 0,
        totalEdges: 0,
        totalDocuments: 0,
        totalConversations: 0,
        todayNewNodes: 0,
        todayNewEdges: 0,
        todayNewDocuments: 0,
        todayNewConversations: 0,
        nodeTypes: [],
        edgeTypes: [],
      });
    }
    
    // 转换 Server 返回的数据格式为前端期望的格式
    const validated = GraphStatsSchema.parse({
      totalNodes: (stats as any).totalNodes || 0,
      totalEdges: (stats as any).totalEdges || 0,
      nodeTypes: [], // Server 目前没有返回 nodeTypes
      edgeTypes: [], // Server 目前没有返回 edgeTypes
      todayNewNodes: (stats as any).todayNewNodes || 0,
      todayNewEdges: (stats as any).todayNewEdges || 0,
    });
    
    return Response.json(validated);
  } catch (error) {
    console.error('Graph stats error:', error);
    return Response.json(
      { error: 'Failed to fetch graph stats' },
      { status: 500 },
    );
  }
}
