import { fetchFromBackend } from '@/lib/api-client';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const result = await fetchFromBackend<{ message: string; success: boolean }>(
      '/commit-memory',
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    );
    return Response.json(result);
  } catch (error) {
    console.error('Commit API error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Commit failed' },
      { status: 500 },
    );
  }
}
