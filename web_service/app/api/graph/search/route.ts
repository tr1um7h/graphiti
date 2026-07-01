// app/api/graph/search/route.ts

import { fetchFromBackend } from '@/lib/api-client';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get('q') || '';

  if (!q) return Response.json([]);

  try {
    // 使用 fetchFromBackend 调用 Server 的 search API
    const data = await fetchFromBackend<any[]>(`/rest/graph/search?q=${encodeURIComponent(q)}`);
    console.log(`🔍 Search results for "${q}":`, data.length, 'items');
    return Response.json(data);
  } catch (error) {
    console.error('Graph search error:', error);
    return Response.json([]);
  }
}
