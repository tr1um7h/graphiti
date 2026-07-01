import { fetchFromBackend } from '@/lib/api-client';
import type { Document } from '@/lib/types';

export async function GET() {
  try {
    // Server 没有 /rest/documents/list 端点，使用 /episodes/{group_id} 获取片段列表
    // 这里使用默认的 'default' group_id
    const episodes: Array<{
      uuid: string;
      name: string;
      content: string;
      source_description: string;
      created_at: string;
    }> = await fetchFromBackend('/episodes/default?last_n=100');

    const docs: Document[] = (episodes || []).map((ep) => ({
      id: ep.uuid,
      name: ep.name || ep.source_description || 'Untitled',
      type: inferDocType(ep.name || ep.source_description || ''),
      status: 'completed' as const,
      entityCount: 0,
      createdAt: ep.created_at || new Date().toISOString(),
      dataset: 'default',
    }));

    return Response.json(docs);
  } catch {
    // Backend not available — return empty list gracefully
    return Response.json([]);
  }
}

function inferDocType(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.pdf')) return 'PDF';
  if (lower.endsWith('.docx')) return 'DOCX';
  if (lower.endsWith('.md')) return 'MD';
  if (lower.startsWith('http')) return 'URL';
  return 'TXT';
}
