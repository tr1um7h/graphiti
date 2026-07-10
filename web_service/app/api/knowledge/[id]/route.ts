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
  name: string;
  fact: string;
  valid_at: string | null;
  invalid_at: string | null;
  created_at: string;
  source_node_uuid: string;
  target_node_uuid: string;
}

interface EntityNode {
  id: string;
  name: string;
  labels: string[];
  summary: string;
  group_id: string;
}

// GET /api/knowledge/[id] — 获取知识详情（episode 内容 + 提取的实体与关系）
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

    // 收集所有关联的实体节点 UUID，批量获取节点详情
    const nodeUuids = new Set<string>();
    for (const f of facts) {
      if (f.source_node_uuid) nodeUuids.add(f.source_node_uuid);
      if (f.target_node_uuid) nodeUuids.add(f.target_node_uuid);
    }

    const entityMap = new Map<string, EntityNode>();
    await Promise.all(
      [...nodeUuids].map(async (nodeUuid) => {
        try {
          const node = await fetchFromBackend<EntityNode>(
            `/rest/graph/entities/${encodeURIComponent(nodeUuid)}`,
          );
          if (node && node.id) entityMap.set(node.id, node);
        } catch {
          // skip missing nodes
        }
      }),
    );

    const doc: Document & {
      content: string;
      facts: FactResult[];
      entities: EntityNode[];
    } = {
      id: targetEpisode.uuid,
      name: targetEpisode.name || targetEpisode.source_description || 'Untitled',
      type: inferDocType(targetEpisode.name || targetEpisode.source_description || ''),
      status: 'completed' as const,
      createdAt: targetEpisode.created_at || new Date().toISOString(),
      group_id: targetEpisode.group_id,
      content: targetEpisode.content || '',
      facts,
      entities: [...entityMap.values()],
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

// DELETE /api/knowledge/[id] — 删除知识（episode）
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    // 后端端点为 /episode/{uuid}（ingest.router 无 /rest 前缀）
    await fetchFromBackend(`/episode/${encodeURIComponent(id)}`, { method: 'DELETE' });
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
