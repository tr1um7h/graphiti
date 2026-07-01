// app/api/graph/query/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { GraphApiResponseSchema } from '@/lib/schemas';
import type { GraphApiResponse } from '@/lib/types';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    console.log('🔍 Graph query POST - calling backend with:', body);
    
    // 调用 Server 的 /rest/graph/query 端点获取图谱数据
    const graphData = await fetchFromBackend('/rest/graph/query', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    
    console.log('📊 Graph data from backend:', JSON.stringify(graphData).substring(0, 100));
    
    if (!graphData) {
      console.log('⚠️ No graph data returned');
      return Response.json({ nodes: [], edges: [] });
    }
    
    // 转换 Server 返回的数据格式为前端期望的格式
    const rawData = graphData as any;
    const transformedData = {
      nodes: (rawData.nodes || []).map((node: any) => ({
        id: node.id,
        label: node.labels?.[0] || 'Entity',
        type: node.labels?.[0] || 'Entity',
        attributes: {
          name: node.name,
          summary: node.summary,
          ...(node.attributes || {}),
        },
      })),
      edges: (rawData.edges || []).map((edge: any) => ({
        id: edge.id,
        source: edge.source_node_uuid,
        target: edge.target_node_uuid,
        label: edge.name,
        fact: edge.fact,
        validAt: edge.valid_at || null,
        invalidAt: edge.invalid_at || null,
      })),
    };
    
    console.log(`✅ Transformed: ${transformedData.nodes.length} nodes, ${transformedData.edges.length} edges`);
    
    // 验证并返回图谱数据
    const validated = GraphApiResponseSchema.parse(transformedData);
    console.log(`✅ Returning ${validated.nodes.length} nodes, ${validated.edges.length} edges`);
    return Response.json(validated);
  } catch (error) {
    console.error('❌ Graph query error:', error);
    return Response.json({ nodes: [], edges: [] });
  }
}

export async function GET() {
  try {
    console.log('🔍 Graph query GET - calling backend...');
    // 调用 Server 的 /rest/graph/query 端点获取图谱数据
    const graphData = await fetchFromBackend('/rest/graph/query', {
      method: 'POST',
      body: JSON.stringify({ limit: 100 }),
    });
    
    console.log('📊 Graph data from backend:', JSON.stringify(graphData).substring(0, 100));
    
    if (!graphData) {
      console.log('⚠️ No graph data returned');
      return Response.json({ nodes: [], edges: [] });
    }
    
    // 验证并返回图谱数据
    const validated = GraphApiResponseSchema.parse(graphData);
    console.log(`✅ Returning ${validated.nodes.length} nodes, ${validated.edges.length} edges`);
    return Response.json(validated);
  } catch (error) {
    console.error('❌ Graph query error:', error);
    return Response.json({ nodes: [], edges: [] });
  }
}
