'use client';

import { useState, useEffect } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { getNodeColor } from '@/lib/graph-theme';
import type { EntityDetail } from '@/lib/types';

interface NodeDetailTabProps {
  nodeId: string | null;
  onNavigateToNode?: (id: string) => void;
}

export default function NodeDetailTab({
  nodeId,
  onNavigateToNode,
}: NodeDetailTabProps) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!nodeId) {
      setDetail(null);
      return;
    }

    setLoading(true);
    fetch(`/api/graph/entities/${nodeId}`)
      .then((res) => res.json())
      .then((data: EntityDetail) => setDetail(data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [nodeId]);

  if (!nodeId) {
    return (
      <div className="flex items-center justify-center p-6 text-sm text-muted-foreground">
        点击节点查看详情
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        加载失败，请重试。
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        {/* Header */}
        <div>
          <h3 className="text-lg font-semibold">{detail.name}</h3>
          <Badge
            variant="outline"
            style={{
              borderColor: getNodeColor(detail.type),
              color: getNodeColor(detail.type),
            }}
          >
            {detail.type}
          </Badge>
        </div>

        {/* Summary */}
        {detail.summary && (
          <div>
            <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              摘要
            </h4>
            <p className="text-sm leading-relaxed">{detail.summary}</p>
          </div>
        )}

        {/* Relationships */}
        {detail.relationships.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              关系 ({detail.relationships.length})
            </h4>
            <ul className="space-y-2">
              {detail.relationships.map((rel) => (
                <li
                  key={rel.id}
                  className="flex items-start gap-2 rounded-md bg-muted/30 px-2 py-1.5 text-sm"
                >
                  <span
                    className="mt-0.5 inline-block size-2 shrink-0 rounded-full"
                    style={{ backgroundColor: getNodeColor(rel.target_type) }}
                  />
                  <div className="min-w-0 flex-1">
                    <button
                      onClick={() => onNavigateToNode?.(rel.target_id)}
                      className="font-medium text-foreground hover:underline"
                    >
                      {rel.target_name}
                    </button>
                    <span className="mx-1 text-muted-foreground">
                      {rel.relationship_type}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {rel.fact}
                    </span>
                  </div>
                  <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Documents / Sources */}
        {(detail.documents.length > 0 || detail.episodes.length > 0) && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              来源
            </h4>
            <ul className="space-y-1">
              {detail.documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center gap-2 text-sm text-muted-foreground"
                >
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    文档
                  </span>
                  {doc.name}
                  <span className="text-xs">({doc.chunks_count} chunks)</span>
                </li>
              ))}
              {detail.episodes.map((ep) => (
                <li
                  key={ep.id}
                  className="flex items-center gap-2 text-sm text-muted-foreground"
                >
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    事件
                  </span>
                  {ep.content}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Timeline */}
        {detail.timeline.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              时间线
            </h4>
            <ul className="space-y-1 border-l-2 border-muted pl-3">
              {detail.timeline.map((entry, i) => (
                <li key={i} className="relative pb-2 text-sm">
                  <span
                    className={`absolute -left-[17px] top-1 size-2.5 rounded-full ${
                      entry.status === 'current'
                        ? 'bg-green-500'
                        : 'bg-muted-foreground'
                    }`}
                  />
                  <span className="text-muted-foreground">
                    {entry.valid_at}
                    {entry.invalid_at ? ` - ${entry.invalid_at}` : ' - 至今'}
                  </span>
                  <p>{entry.fact}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
