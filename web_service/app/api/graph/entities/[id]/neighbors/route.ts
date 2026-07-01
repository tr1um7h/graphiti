// app/api/graph/entities/[id]/neighbors/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { NeighborsResponseSchema } from '@/lib/schemas';
import type { NeighborsResponse } from '@/lib/types';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  const _depth = parseInt(searchParams.get('depth') || '1');

  try {
    const data = await fetchFromBackend<NeighborsResponse>({
      path: `/rest/graph/entities/${encodeURIComponent(id)}/neighbors`,
      schema: NeighborsResponseSchema,
    });
    return Response.json(data);
  } catch (error) {
    console.error('Entity neighbors error:', error);
    return Response.json({ center: null, nodes: [], edges: [] });
  }
}
