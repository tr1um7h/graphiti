// app/api/graph/groups/route.ts

import { fetchFromBackend } from '@/lib/api-client';

export async function GET() {
  try {
    // 调用 Server 的 /rest/graph/groups 端点获取分组列表
    const data = await fetchFromBackend<any[]>('/rest/graph/groups');
    return Response.json(data);
  } catch (error) {
    console.error('Groups error:', error);
    return Response.json([]);
  }
}
