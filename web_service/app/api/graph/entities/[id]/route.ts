// app/api/graph/entities/[id]/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { EntityDetailSchema } from '@/lib/schemas';
import type { EntityDetail } from '@/lib/types';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const data = await fetchFromBackend<any>(`/rest/graph/entities/${encodeURIComponent(id)}`);
    
    if (!data) {
      return Response.json({ error: 'Entity not found' }, { status: 404 });
    }
    
    // 转换 Server 返回的数据格式为前端期望的 EntityDetail 格式
    const transformedData = {
      id: data.id,
      name: data.name,
      type: data.labels?.[0] || 'Entity',
      summary: data.summary || '',
      attributes: data.attributes || {},
      relationships: [],
      documents: [],
      episodes: [],
      timeline: [],
    };
    
    // 验证并返回数据
    const validated = EntityDetailSchema.parse(transformedData);
    return Response.json(validated);
  } catch (error) {
    console.error('Entity detail error:', error);
    return Response.json({ error: 'Entity not found' }, { status: 404 });
  }
}
