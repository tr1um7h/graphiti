// app/api/graph/timeline/route.ts

import { fetchFromBackend } from '@/lib/api-client';
import { z } from 'zod';

// Timeline item schema
const TimelineItemSchema = z.object({
  type: z.string(),
  description: z.string(),
  source: z.string(),
  time: z.string(),
});

const TimelineResponseSchema = z.array(TimelineItemSchema);

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get('limit') || '10';

  try {
    // 调用 Server 的 /rest/graph/timeline 端点获取真实活动时间线
    const data = await fetchFromBackend(`/rest/graph/timeline?limit=${limit}`);
    
    if (!data) {
      return Response.json([]);
    }
    
    // 验证并返回数据
    const validated = TimelineResponseSchema.parse(data);
    return Response.json(validated);
  } catch (error) {
    console.error('Timeline error:', error);
    return Response.json([]);
  }
}
