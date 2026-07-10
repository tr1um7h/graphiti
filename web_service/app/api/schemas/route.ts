import { fetchFromBackend } from '@/lib/api-client';

export async function GET() {
  try {
    const data = await fetchFromBackend('/rest/schemas');
    return Response.json(data);
  } catch (error) {
    console.error('Schemas list error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Failed to list schemas' },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const data = await fetchFromBackend('/rest/schemas', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return Response.json(data);
  } catch (error) {
    console.error('Schema create error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Failed to create schema' },
      { status: 500 },
    );
  }
}
