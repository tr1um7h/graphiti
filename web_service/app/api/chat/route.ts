// app/api/chat/route.ts
import { fetchFromBackend } from '@/lib/api-client';
import type { ChatRequest, ChatResponse } from '@/lib/types';

export async function POST(request: Request) {
  try {
    const body: ChatRequest = await request.json();

    const data = await fetchFromBackend<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    return Response.json(data);
  } catch (error) {
    console.error('Chat BFF error:', error);
    return Response.json(
      { answer: '抱歉，请求失败，请稍后重试。' },
      { status: 500 },
    );
  }
}