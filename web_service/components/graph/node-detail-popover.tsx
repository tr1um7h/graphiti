// components/graph/node-detail-popover.tsx
'use client';

import { useEffect, useState } from 'react';
import type { EntityDetail } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface NodeDetailPopoverProps {
  nodeId: string | null;
  x: number;
  y: number;
}

export function NodeDetailPopover({ nodeId, x, y }: NodeDetailPopoverProps) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

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

  // Compute position: show to the right of the click point,
  // but keep within the viewport.
  const left = nodeId ? Math.min(x + 16, window.innerWidth - 348) : 0;
  const top = nodeId ? Math.min(y + 16, window.innerHeight - 400) : 0;

  return (
    <div
      data-popover="true"
      style={{
        position: 'fixed',
        left,
        top,
        opacity: nodeId ? 1 : 0,
        pointerEvents: nodeId ? 'auto' : 'none',
        zIndex: 50,
      }}
      className="w-80 rounded-lg border bg-background shadow-xl transition-opacity duration-150"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="border-b px-4 py-3">
        <h3 className="font-semibold">实体详情</h3>
      </div>

      {/* Body */}
      <div className="max-h-[350px] overflow-y-auto p-4">
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
                <p className="mb-2 text-sm font-medium">关系</p>
                <ul className="space-y-1">
                  {detail.relationships.map((r) => (
                    <li
                      key={r.id}
                      className="text-sm text-muted-foreground"
                    >
                      ├ {r.fact}
                    </li>
                  ))}
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
                      className="text-sm text-muted-foreground"
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
    </div>
  );
}
