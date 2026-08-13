'use client';

import { useRef, useState, useEffect } from 'react';
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';
import { Column } from './column';
import { EdgeLines } from './edge-lines';
import { BottomControls } from './bottom-controls';
import { Minimap } from './minimap';

export function Canvas() {
  const schemaData = useOntologyStore((s) => s.schemaData);
  const scale = useOntologyStore((s) => s.scale);
  const panX = useOntologyStore((s) => s.panX);
  const panY = useOntologyStore((s) => s.panY);
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const clearFocus = useOntologyStore((s) => s.clearFocus);
  const fitView = useOntologyStore((s) => s.fitView);
  const setPan = useOntologyStore((s) => s.setPan);
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originPanX: number;
    originPanY: number;
  } | null>(null);
  const didDragRef = useRef(false);

  // Auto-fit view when an item is focused
  useEffect(() => {
    if (focusedItemId) {
      // Small delay to let DOM settle after focus highlight renders
      const id = requestAnimationFrame(() => fitView());
      return () => cancelAnimationFrame(id);
    }
  }, [focusedItemId, fitView]);

  if (!schemaData) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        暂无数据
      </div>
    );
  }

  // Find focused item name for display
  const focusName = focusedItemId
    ? findItemLabel(schemaData.columns, focusedItemId)
    : null;

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || panStartRef.current) return;

    const target = e.target as HTMLElement;
   if (
     target.closest('[id^="card-"]') ||
     target.closest('.edge-path') ||
      target.closest('.bottom-controls') ||
      target.closest('[data-minimap]')
   ) {
     return;
   }

   panStartRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      originPanX: panX,
      originPanY: panY,
    };
    didDragRef.current = false;
    setIsPanning(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const start = panStartRef.current;
    if (!start) return;

    const dx = e.clientX - start.startX;
    const dy = e.clientY - start.startY;
    if (Math.abs(dx) + Math.abs(dy) > 3) {
      didDragRef.current = true;
    }
    setPan(start.originPanX + dx, start.originPanY + dy);
  };

  const handlePointerEnd = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!panStartRef.current) return;
    panStartRef.current = null;
    setIsPanning(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const handleCanvasClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (didDragRef.current) {
      didDragRef.current = false;
      e.stopPropagation();
      return;
    }

    const target = e.target as HTMLElement;
    if (
     !target.closest('[id^="card-"]') &&
     !target.closest('.edge-path') &&
      !target.closest('.bottom-controls') &&
      !target.closest('[data-minimap]')
   ) {
     clearFocus();
    }
  };

  return (
    <div
      data-memory-canvas-viewport
      className="relative flex-1 overflow-hidden bg-background"
      style={{
        backgroundImage: 'radial-gradient(circle, var(--border) 1px, transparent 1px)',
        backgroundSize: '22px 22px',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
      onClick={handleCanvasClick}
    >
      {/* Hint / Focus info */}
      {!focusedItemId ? (
        <div className="absolute top-4 left-7 text-sm text-muted-foreground/50 z-[4]">
          Click any item to trace its connections.
        </div>
      ) : (
        <div className="absolute top-4 left-7 text-sm z-[6] flex items-center gap-2.5">
          <span className="text-muted-foreground/50">
            Focused on <b className="font-semibold text-foreground">{focusName}</b>
          </span>
          <span
            className="text-[#3ecf8e] cursor-pointer hover:underline"
            onClick={clearFocus}
          >
            Clear focus
          </span>
        </div>
      )}

      {/* Scalable canvas */}
      <div
        data-memory-canvas-transform
        className={`absolute inset-0 cursor-grab touch-none select-none ${
          isPanning ? 'cursor-grabbing' : ''
        }`}
        style={{
          transform: `translate(${panX}px, ${panY}px) scale(${scale})`,
          transformOrigin: '0 0',
        }}
      >
        {/* Only draw edges when focused */}
        {focusedItemId && <EdgeLines />}
        <div
          data-memory-canvas-content
          className="relative z-[3] flex gap-20 py-10 px-7 h-full"
        >
          {schemaData.columns.map((col) => (
            <Column key={col.id} column={col} />
          ))}
        </div>
      </div>

      <BottomControls />
      <Minimap />
    </div>
  );
}

function findItemLabel(
  columns: { id: string; cards: { id: string; items: { id: string; label: string }[] }[] }[],
  itemId: string
): string | null {
  for (const col of columns) {
    for (const card of col.cards) {
      for (const item of card.items) {
        if (item.id === itemId) return item.label;
      }
    }
  }
  return null;
}
