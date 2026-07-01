// app/api/explore/chat/route.ts
// BFF route — forwards chat requests to the Python backend

import { fetchFromBackend } from '@/lib/api-client';
import type { ExploreChatRequest, ExploreChatResponse } from '@/lib/types';

export async function POST(request: Request) {
  try {
    const body: ExploreChatRequest = await request.json();

    const data = await fetchFromBackend<ExploreChatResponse>({
      path: '/rest/explore/chat',
      method: 'POST',
      body: JSON.stringify({
        message: body.message,
        centerEntityId: body.centerEntityId,
        visibleNodeIds: body.visibleNodeIds,
      }),
    });

    return Response.json(data);
  } catch (error) {
    console.error('Explore chat error:', error);
    const message = error instanceof Error ? error.message : 'Chat request failed';
    return Response.json(
      { answer: `请求出错: ${message}`, sources: [] },
      { status: 500 },
    );
  }
}
