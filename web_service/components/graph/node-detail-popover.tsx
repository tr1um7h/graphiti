// components/graph/node-detail-popover.tsx
// Floating entity detail popover anchored to a node's screen position.
// Shows entity name, type badge, and summary — no relationships or documents.
'use client';

import { useEffect, useState } from 'react';
import type { EntityDetail } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, MessageCircle, X } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { useChatStore } from '@/stores/chat-store';

interface NodeDetailPopoverProps {
  nodeId: string;
  x: number;
  y: number;
  onClose: () => void;
}

export function NodeDetailPopover({ nodeId, x, y, onClose }: NodeDetailPopoverProps) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    setDetail(null);

    fetch(`/api/graph/entities/${encodeURIComponent(nodeId)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`entity fetch failed: ${res.status}`);
        return (await res.json()) as EntityDetail;
      })
      .then(setDetail)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [nodeId]);

  // Position: right-below the node, clamped to viewport.
  // Popover width ≈ 280px, max height ≈ 320px.
  const POPUP_W = 288;
  const POPUP_H = 340;
  const OFFSET = 16;

  let left = x + OFFSET;
  let top = y + OFFSET;

  // Flip to left side if too close to right edge
  if (left + POPUP_W > window.innerWidth - 8) {
    left = x - POPUP_W - OFFSET;
  }
  // Flip above if too close to bottom
  if (top + POPUP_H > window.innerHeight - 8) {
    top = y - POPUP_H - OFFSET;
  }
  // Final clamp
  left = Math.max(8, Math.min(left, window.innerWidth - POPUP_W - 8));
  top = Math.max(8, Math.min(top, window.innerHeight - POPUP_H - 8));

  return (
    <div
      data-popover="true"
      style={{
        position: 'fixed',
        left,
        top,
        zIndex: 50,
        width: POPUP_W,
      }}
      className="rounded-lg border bg-background shadow-xl"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <h3 className="text-sm font-semibold">实体详情</h3>
        <button
          onClick={onClose}
          className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="max-h-[280px] overflow-y-auto p-4">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-4 text-center text-sm text-muted-foreground">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <p>无法加载实体详情</p>
          </div>
        ) : detail ? (
          <div className="space-y-2">
            <p className="text-base font-semibold leading-tight">{detail.name}</p>
            <Badge variant="secondary" className="text-xs">
              {detail.type}
            </Badge>
            {detail.summary && (
              <p className="text-sm leading-relaxed text-muted-foreground">
                {detail.summary}
              </p>
            )}
            <button
              onClick={() => {
                useChatStore.getState().open({
                  context_id: detail.id,
                  context_type: 'node',
                  context_name: detail.name,
                });
              }}
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <MessageCircle className="h-3.5 w-3.5" />
              对此节点询问 AI
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
