import { fetchFromBackend } from '@/lib/api-client';
import type { Document } from '@/lib/types';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const groupFilter = searchParams.get('group_id') || 'all';

    // 获取所有可用的 group 列表
    const groups = await fetchFromBackend<
      Array<{ id: string; name: string; count: number }>
    >('/rest/graph/groups');

    // 确定需要查询的 group_ids
    const groupIds =
      groupFilter === 'all' ? groups.map((g) => g.id || g.name) : [groupFilter];

    const docs: Document[] = [];

    for (const gid of groupIds) {
      try {
        const episodes: Array<{
          uuid: string;
          name: string;
          content: string;
          source_description: string;
          created_at: string;
          entity_edges?: string[];
        }> = await fetchFromBackend(
          `/episodes/${encodeURIComponent(gid)}?last_n=100`,
        );

        for (const ep of episodes || []) {
          docs.push({
            id: ep.uuid,
            name: ep.name || ep.source_description || 'Untitled',
            type: inferDocType(ep.name || ep.source_description || ''),
            status: 'completed' as const,
            entityCount: Array.isArray(ep.entity_edges) ? ep.entity_edges.length : 0,
            createdAt: ep.created_at || new Date().toISOString(),
            group_id: gid,
          });
        }
      } catch {
        // 某个 group 查询失败时跳过，不影响其他 group
      }
    }

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
