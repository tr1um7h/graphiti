import { fetchFromBackend } from '@/lib/api-client';
import type { Document } from '@/lib/types';

interface Episode {
  uuid: string;
  name: string;
  group_id: string;
  content: string;
  source_description: string;
  created_at: string;
  entity_edges: string[];
}

interface FactResult {
  uuid: string;
  fact: string;
  valid_at: string | null;
  invalid_at: string | null;
  source_node_uuid: string;
  target_node_uuid: string;
}

// GET /api/documents/[id] — 获取文档详情（episode 内容 + 提取的事实）
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    // 先获取所有 group，逐个查找 episode
    const groups = await fetchFromBackend<
      Array<{ id: string; name: string; count: number }>
    >('/rest/graph/groups');

    let targetEpisode: Episode | null = null;

    for (const g of groups) {
      try {
        const episodes: Episode[] = await fetchFromBackend(
          `/episodes/${encodeURIComponent(g.id || g.name)}?last_n=100`,
        );
        const found = (episodes || []).find((ep) => ep.uuid === id);
        if (found) {
          targetEpisode = found;
          break;
        }
      } catch {
        // skip
      }
    }

    if (!targetEpisode) {
      return Response.json({ error: 'Document not found' }, { status: 404 });
    }

    // 获取该 episode 关联的实体边（事实）
    let facts: FactResult[] = [];
    if (targetEpisode.entity_edges && targetEpisode.entity_edges.length > 0) {
      const factPromises = targetEpisode.entity_edges.map((edgeUuid) =>
        fetchFromBackend<FactResult>(`/entity-edge/${encodeURIComponent(edgeUuid)}`).catch(
          () => null,
        ),
      );
      const results = await Promise.all(factPromises);
      facts = results.filter((r): r is FactResult => r !== null);
    }

    const doc: Document & { content: string; facts: FactResult[] } = {
      id: targetEpisode.uuid,
      name: targetEpisode.name || targetEpisode.source_description || 'Untitled',
      type: inferDocType(targetEpisode.name || targetEpisode.source_description || ''),
      status: 'completed' as const,
      entityCount: targetEpisode.entity_edges?.length || 0,
      createdAt: targetEpisode.created_at || new Date().toISOString(),
      group_id: targetEpisode.group_id,
      content: targetEpisode.content || '',
      facts,
    };

    return Response.json(doc);
  } catch (error) {
    console.error('Document detail error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch' },
      { status: 500 },
    );
  }
}

// DELETE /api/documents/[id] — 删除文档（episode）
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    // 后端端点为 /episode/{uuid}（ingest.router 无 /rest 前缀）
    await fetchFromBackend({ path: `/episode/${encodeURIComponent(id)}`, method: 'DELETE' });
    return Response.json({ id, status: 'deleted' });
  } catch (error) {
    console.error('Document delete error:', error);
    return Response.json(
      { error: error instanceof Error ? error.message : 'Delete failed' },
      { status: 500 },
    );
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
