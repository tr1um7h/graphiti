import { fetchFromBackend } from '@/lib/api-client';

interface PreviewTaskStatus {
  task_id: string;
  status: string;
  stage: string | null;
  error: string | null;
  result: unknown;
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ taskId: string }> },
) {
  try {
    const { taskId } = await params;
    const result = await fetchFromBackend<PreviewTaskStatus>(
      `/preview-memory/${encodeURIComponent(taskId)}`,
      { method: 'GET' },
    );
    return Response.json(result);
  } catch (error) {
    console.error('Preview poll error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Poll failed' },
      { status: 500 },
    );
  }
}
