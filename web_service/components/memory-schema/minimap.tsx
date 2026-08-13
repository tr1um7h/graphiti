'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';

const MINIMAP_SIZE = 168;
const MINIMAP_PADDING = 8;

interface MiniCard {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
}

interface Bounds {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface ViewState {
  x: number;
  y: number;
  w: number;
  h: number;
}

const EMPTY_BOUNDS: Bounds = { left: 0, top: 0, width: 1, height: 1 };

export function Minimap() {
  const containerRef = useRef<HTMLDivElement>(null);
  const pointerDownRef = useRef(false);
  const [dragging, setDragging] = useState(false);

  const scale = useOntologyStore((s) => s.scale);
  const panX = useOntologyStore((s) => s.panX);
  const panY = useOntologyStore((s) => s.panY);
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const schemaData = useOntologyStore((s) => s.schemaData);
  const setPan = useOntologyStore((s) => s.setPan);

  const [cards, setCards] = useState<MiniCard[]>([]);
  const [bounds, setBounds] = useState<Bounds>(EMPTY_BOUNDS);
  const [view, setView] = useState<ViewState>({ x: 0, y: 0, w: 0, h: 0 });

  // Measure cards in content-space coordinates
  const measure = useCallback(() => {
    const viewport = document.querySelector<HTMLElement>('[data-memory-canvas-viewport]');
    if (!viewport || !schemaData) return;

    const vpRect = viewport.getBoundingClientRect();
    const cardEls = Array.from(
      viewport.querySelectorAll<HTMLElement>('[data-memory-card]:not(.hidden)')
    );
    if (cardEls.length === 0) {
      setCards([]);
      return;
    }

    const rects: MiniCard[] = [];
    let minL = Infinity, minT = Infinity, maxR = -Infinity, maxB = -Infinity;

    for (const el of cardEls) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;

      const cx = (r.left - vpRect.left - panX) / scale;
      const cy = (r.top - vpRect.top - panY) / scale;
      const cw = r.width / scale;
      const ch = r.height / scale;
      const color = el.getAttribute('data-card-color') || '#94a3b8';

      rects.push({ x: cx, y: cy, w: cw, h: ch, color });
      minL = Math.min(minL, cx);
      minT = Math.min(minT, cy);
      maxR = Math.max(maxR, cx + cw);
      maxB = Math.max(maxB, cy + ch);
    }

    if (rects.length === 0) return;

    setBounds({
      left: minL,
      top: minT,
      width: Math.max(1, maxR - minL),
      height: Math.max(1, maxB - minT),
    });
    setCards(rects);
    setView({
      x: -panX / scale,
      y: -panY / scale,
      w: vpRect.width / scale,
      h: vpRect.height / scale,
    });
  }, [scale, panX, panY, schemaData]);

  // Re-measure on relevant state changes (deferred for DOM settle)
  useEffect(() => {
    const t = setTimeout(measure, 120);
    return () => clearTimeout(t);
  }, [measure, focusedItemId]);

  const contentSize = Math.max(bounds.width, bounds.height);
  const minimapScale = (MINIMAP_SIZE - MINIMAP_PADDING * 2) / contentSize;

  const mx = (cx: number) => MINIMAP_PADDING + (cx - bounds.left) * minimapScale;
  const my = (cy: number) => MINIMAP_PADDING + (cy - bounds.top) * minimapScale;

  // Pan canvas so that the content point under the cursor is centered
  const navigateTo = useCallback(
    (clientX: number, clientY: number) => {
      const viewport = document.querySelector<HTMLElement>('[data-memory-canvas-viewport]');
      if (!viewport) return;
      const vpRect = viewport.getBoundingClientRect();
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;

      const px = clientX - rect.left;
      const py = clientY - rect.top;
      const cx = (px - MINIMAP_PADDING) / minimapScale + bounds.left;
      const cy = (py - MINIMAP_PADDING) / minimapScale + bounds.top;

      setPan(vpRect.width / 2 - cx * scale, vpRect.height / 2 - cy * scale);
    },
    [minimapScale, bounds, scale, setPan]
  );

  if (!schemaData) return null;

  return (
   <div
     ref={containerRef}
      data-minimap
     className="absolute right-7 bottom-6 z-[5] touch-none select-none rounded-xl border bg-background/85 backdrop-blur-sm shadow-sm"
      style={{ width: MINIMAP_SIZE, height: MINIMAP_SIZE, cursor: dragging ? 'grabbing' : 'grab' }}
      onPointerDown={(e) => {
        pointerDownRef.current = true;
        setDragging(true);
        e.currentTarget.setPointerCapture(e.pointerId);
        navigateTo(e.clientX, e.clientY);
      }}
      onPointerMove={(e) => {
        if (pointerDownRef.current) navigateTo(e.clientX, e.clientY);
      }}
      onPointerUp={(e) => {
        pointerDownRef.current = false;
        setDragging(false);
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      }}
      onPointerCancel={(e) => {
        pointerDownRef.current = false;
        setDragging(false);
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      }}
    >
      <svg width={MINIMAP_SIZE} height={MINIMAP_SIZE} className="block">
        {cards.map((c, i) => (
          <rect
            key={i}
            x={mx(c.x)}
            y={my(c.y)}
            width={Math.max(2, c.w * minimapScale)}
            height={Math.max(2, c.h * minimapScale)}
            rx={2}
            fill={c.color}
            opacity={0.65}
          />
        ))}
        {/* Viewport indicator */}
        <rect
          x={mx(view.x)}
          y={my(view.y)}
          width={Math.max(2, view.w * minimapScale)}
          height={Math.max(2, view.h * minimapScale)}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeDasharray="3 2"
          className="text-foreground"
          opacity={0.5}
        />
      </svg>
    </div>
  );
}
