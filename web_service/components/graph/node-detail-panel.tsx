// components/graph/node-detail-panel.tsx
'use client';

import { useEffect, useState } from 'react';
import type { EntityDetail } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AlertTriangle, X, Expand, Loader2 } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface NodeDetailPanelProps {
  nodeId: string;
  onClose: () => void;
  onExpandNeighbors: (nodeId: string) => void;
}

export function NodeDetailPanel({ nodeId, onClose, onExpandNeighbors }: NodeDetailPanelProps) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [expanding, setExpanding] = useState(false);

  useEffect(() => {
    if (!nodeId) {
      setDetail(null);
      setError(false);
      return;
    }

    setLoading(true);
    setError(false);
    fetch(`/api/graph/entities/${nodeId}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`entity fetch failed: ${res.status}`);
        const data = await res.json();
        if (
          !data ||
          !Array.isArray(data.relationships) ||
          !Array.isArray(data.documents)
        ) {
          throw new Error('entity detail has unexpected shape');
        }
        return data as EntityDetail;
      })
      .then((data) => setDetail(data))
      .catch(() => {
        setDetail(null);
        setError(true);
      })
      .finally(() => setLoading(false));
  }, [nodeId]);

  const handleExpand = async () => {
    setExpanding(true);
    try {
      await onExpandNeighbors(nodeId);
    } finally {
      setExpanding(false);
    }
  };

  return (
    <div
      data-panel="true"
      className="w-80 border-l bg-background flex flex-col h-full"
    >
      {/* Header */}
      <div className="border-b px-4 py-3 flex items-center justify-between">
        <h3 className="font-semibold">实体详情</h3>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-6 text-center text-sm text-muted-foreground">
            <AlertTriangle className="h-6 w-6 text-destructive" />
            <p>无法加载该实体详情</p>
          </div>
        ) : detail ? (
          <div className="space-y-4">
            <div>
              <p className="text-lg font-semibold">{detail.name}</p>
              <Badge variant="secondary" className="mt-1">
                {detail.type}
              </Badge>
            </div>

            {detail.summary && (
              <p className="text-sm text-muted-foreground">{detail.summary}</p>
            )}

            {detail.relationships.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium">
                  关系 ({detail.relationships.length})
                </p>
                <ul className="space-y-1">
                  {detail.relationships.slice(0, 10).map((r) => (
                    <li
                      key={r.id}
                      className="text-sm text-muted-foreground truncate"
                    >
                      ├ {r.fact}
                    </li>
                  ))}
                  {detail.relationships.length > 10 && (
                    <li className="text-xs text-muted-foreground">
                      ...还有 {detail.relationships.length - 10} 个关系
                    </li>
                  )}
                </ul>
              </div>
            )}

            {detail.documents.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium">来源</p>
                <ul className="space-y-1">
                  {detail.documents.map((d) => (
                    <li
                      key={d.id}
                      className="text-sm text-muted-foreground truncate"
                    >
                      ├ {d.name}{' '}
                      <Badge variant="outline" className="text-xs">
                        {d.source}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : null}
      </div>

      {/* Footer - Expand button */}
      <div className="border-t p-4">
        <Button
          variant="outline"
          size="sm"
          onClick={handleExpand}
          disabled={expanding || loading}
          className="w-full"
        >
          {expanding ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Expand className="h-4 w-4 mr-2" />
          )}
          展开邻居节点
        </Button>
      </div>
    </div>
  );
}