import { fetchFromBackend } from '@/lib/api-client';
import type { Document } from '@/lib/types';

interface QueueJob {
  name: string;
  group_id: string;
  status: string;
  submitted_at: string;
}

interface QueueStatus {
  current: QueueJob | null;
  queue_size: number;
  pending: QueueJob[];
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const groupFilter = searchParams.get('group_id') || 'all';

    // 并行获取：已完成的 episodes + 队列中的 pending/processing 任务
    const [groups, queueStatus] = await Promise.all([
      fetchFromBackend<
        Array<{ id: string; name: string; count: number }>
      >('/rest/graph/groups'),
      fetchFromBackend<QueueStatus>('/queue/status').catch(() => null),
    ]);

    // 确定需要查询的 group_ids
    const groupIds =
      groupFilter === 'all' ? groups.map((g) => g.id || g.name) : [groupFilter];

    const docs: Document[] = [];

    // 1. 获取已完成的 episodes
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

    // 2. 合并队列中 pending/processing 的任务（尚未写入数据库的文档）
    if (queueStatus) {
      const pendingJobs: QueueJob[] = [
        ...(queueStatus.current ? [queueStatus.current] : []),
        ...queueStatus.pending,
      ];

      for (const job of pendingJobs) {
        // 按 group 过滤
        if (groupFilter !== 'all' && job.group_id !== groupFilter) continue;
        // 避免重复（已完成但 episode 尚未刷新出来的情况）
        if (docs.some((d) => d.name === job.name)) continue;

        docs.push({
          id: `pending-${job.name}`,
          name: job.name,
          type: inferDocType(job.name),
          status: job.status === 'processing' ? 'processing' : 'pending',
          entityCount: 0,
          createdAt: job.submitted_at,
          group_id: job.group_id,
        });
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
