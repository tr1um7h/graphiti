import { fetchFromBackend } from '@/lib/api-client';
import type { MemorySchemaData } from '@/lib/types';

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const groupId = url.searchParams.get('group_id');
    const backendPath = groupId
      ? `/rest/memory-schema?group_id=${encodeURIComponent(groupId)}`
      : '/rest/memory-schema';
    const data = await fetchFromBackend(backendPath);
    return Response.json(data as MemorySchemaData);
  } catch (error) {
    console.error('Memory schema error:', error);
    return Response.json({
      columns: [
        { id: 'episodes', cards: [] },
        { id: 'entities', cards: [] },
        { id: 'types', cards: [] },
        { id: 'summaries', cards: [] },
      ],
      edges: [],
      details: {},
      group_id: null,
      counts: { episodes: 0, entities: 0, types: 0, summaries: 0 },
    });
  }
}
