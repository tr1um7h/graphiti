import { fetchFromBackend } from '@/lib/api-client';

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    await fetchFromBackend({ path: `/rest/documents/${encodeURIComponent(id)}`, method: 'DELETE' });
    return Response.json({ id, status: 'deleted' });
  } catch (error) {
    console.error('Document delete error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Delete failed' },
      { status: 500 },
    );
  }
}
