import { fetchFromBackend } from '@/lib/api-client';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const data = await fetchFromBackend(`/rest/schemas/${encodeURIComponent(id)}`);
    return Response.json(data);
  } catch (error) {
    console.error('Schema get error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Schema not found' },
      { status: 404 },
    );
  }
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body = await request.json();
    const data = await fetchFromBackend(`/rest/schemas/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
    return Response.json(data);
  } catch (error) {
    console.error('Schema update error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Failed to update schema' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const data = await fetchFromBackend(`/rest/schemas/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    return Response.json(data);
  } catch (error) {
    console.error('Schema delete error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Failed to delete schema' },
      { status: 500 },
    );
  }
}
