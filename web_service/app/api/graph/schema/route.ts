// app/api/graph/schema/route.ts

import { fetchFromBackend } from '@/lib/api-client';

interface SchemaResponse {
  nodeLabels: { label: string; count: number }[];
  relationshipTypes: { type: string; count: number }[];
}

export async function GET() {
  try {
    const data = await fetchFromBackend<SchemaResponse>('/rest/graph/schema');
    return Response.json(data);
  } catch (error) {
    console.error('Graph schema error:', error);
    return Response.json({
      nodeLabels: [],
      relationshipTypes: [],
    });
  }
}
