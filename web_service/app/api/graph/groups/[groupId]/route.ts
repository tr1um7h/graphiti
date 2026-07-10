import { fetchFromBackend } from '@/lib/api-client';

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ groupId: string }> },
) {
  const { groupId } = await params;
  try {
    const result = await fetchFromBackend<{ message: string; success: boolean }>(
      `/group/${encodeURIComponent(groupId)}`,
      { method: 'DELETE' },
    );
    return Response.json(result);
  } catch (error) {
    console.error('Delete group error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Delete group failed' },
      { status: 500 },
    );
  }
}
