import { fetchFromBackend } from '@/lib/api-client';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const result = await fetchFromBackend<{ task_id: string; status: string }>(
      '/preview-memory',
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    );
    return Response.json(result);
  } catch (error) {
    console.error('Preview API error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Preview failed' },
      { status: 500 },
    );
  }
}
