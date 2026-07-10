import { fetchFromBackend } from '@/lib/api-client';

export async function POST(request: Request) {
  try {
    const { name, content, group_id, source, schema_id } = await request.json();

    const result = await fetchFromBackend<{ message: string; success: boolean }>(
      '/add-episode',
      {
        method: 'POST',
        body: JSON.stringify({
          name: name || content.slice(0, 50),
          content,
          group_id,
          source_description: source || 'text',
          schema_id: schema_id ?? null,
        }),
      },
    );
    return Response.json(result);
  } catch (error) {
    console.error('Generate API error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Generate failed' },
      { status: 500 },
    );
  }
}
