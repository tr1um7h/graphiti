'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';
import type { SchemaEdge } from '@/lib/types';

interface AggregatedEdge extends SchemaEdge {
  count: number;
}

const SAME_COLUMN_OFFSET = 16;
const STRUCTURAL_EDGE_LABELS = new Set(['is_part_of', 'is_a', 'has_member', 'MENTIONS']);

export function EdgeLines() {
  const svgRef = useRef<SVGSVGElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const schemaData = useOntologyStore((s) => s.schemaData);
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);

  const drawEdges = useCallback(() => {
    const svg = svgRef.current;
    const labelLayer = labelRef.current;
    if (!svg || !labelLayer || !schemaData || !focusedItemId) return;

    svg.innerHTML = '';
    labelLayer.innerHTML = '';

    const svgRect = svg.getBoundingClientRect();
    const scaleX = svgRect.width && svg.clientWidth ? svgRect.width / svg.clientWidth : 1;
    const scaleY = svgRect.height && svg.clientHeight ? svgRect.height / svg.clientHeight : 1;

    const relevantEdges = schemaData.edges.filter(
      (edge: SchemaEdge) => edge.source === focusedItemId || edge.target === focusedItemId
    );

    const aggregated = aggregateEdges(relevantEdges);

    // -- Pass 1: compute fan totals per item-side --
    const fanTotals = new Map<string, number>();
    for (const edge of aggregated) {
      const sourceCardEl = findCardElement(schemaData.columns, edge.source);
      const targetCardEl = findCardElement(schemaData.columns, edge.target);
      if (!sourceCardEl || !targetCardEl) continue;

      const srcCardRect = sourceCardEl.getBoundingClientRect();
      const tgtCardRect = targetCardEl.getBoundingClientRect();
      const sameColumn = Math.abs(srcCardRect.left - tgtCardRect.left) < 1;
      const fromRight = sameColumn ? false : srcCardRect.left > tgtCardRect.left;
      incrementFan(fanTotals, edge.source, sameColumn ? 'right' : fromRight ? 'left' : 'right');
      incrementFan(fanTotals, edge.target, sameColumn ? 'right' : fromRight ? 'right' : 'left');
    }

    // -- Pass 2: pair-based curvature separation --
    const pairTotals = new Map<string, number>();
    for (const edge of aggregated) {
      const pairKey = pairDirectionKey(edge.source, edge.target);
      pairTotals.set(pairKey, (pairTotals.get(pairKey) ?? 0) + 1);
    }
    const pairIndexes = new Map<string, number>();
    const fanIndexes = new Map<string, number>();

    // -- Pass 3: draw --
    aggregated.forEach((edge) => {
      const sourceCardEl = findCardElement(schemaData.columns, edge.source);
      const targetCardEl = findCardElement(schemaData.columns, edge.target);
      if (!sourceCardEl || !targetCardEl) return;

      const sourceItemEl = findItemElement(sourceCardEl, edge.source);
      const targetItemEl = findItemElement(targetCardEl, edge.target);
      if (!sourceItemEl || !targetItemEl) return;

      // Card rects for x (border edge), item rects for y (which item)
      const srcCardRect = sourceCardEl.getBoundingClientRect();
      const tgtCardRect = targetCardEl.getBoundingClientRect();
      const srcItemRect = sourceItemEl.getBoundingClientRect();
      const tgtItemRect = targetItemEl.getBoundingClientRect();

      const sameColumn = Math.abs(srcCardRect.left - tgtCardRect.left) < 1;
      const fromRight = sameColumn ? false : srcCardRect.left > tgtCardRect.left;
      const sourceSide = sameColumn ? 'right' : fromRight ? 'left' : 'right';
      const targetSide = sameColumn ? 'right' : fromRight ? 'right' : 'left';

      // x at card border edge, not item text edge
      const sourceEdgeX = sameColumn
        ? srcCardRect.right + SAME_COLUMN_OFFSET
        : fromRight
          ? srcCardRect.left
          : srcCardRect.right;
      const targetEdgeX = sameColumn
        ? tgtCardRect.right + SAME_COLUMN_OFFSET
        : fromRight
          ? tgtCardRect.right
          : tgtCardRect.left;

      const x1 = (sourceEdgeX - svgRect.left) / scaleX;
      const y1 =
        (getFanY(srcItemRect, edge.source, sourceSide, fanTotals, fanIndexes) - svgRect.top) /
        scaleY;
      const x2 = (targetEdgeX - svgRect.left) / scaleX;
      const y2 =
        (getFanY(tgtItemRect, edge.target, targetSide, fanTotals, fanIndexes) - svgRect.top) /
        scaleY;

      // Pair-based curvature offset to separate parallel edges
      const pairKey = pairDirectionKey(edge.source, edge.target);
      const pairTotal = pairTotals.get(pairKey) ?? 1;
      const pairIndex = pairIndexes.get(pairKey) ?? 0;
      pairIndexes.set(pairKey, pairIndex + 1);
      const pairOffset = pairTotal > 1 ? (pairIndex - (pairTotal - 1) / 2) * 14 : 0;

      const dx = sameColumn
        ? Math.max(40, Math.abs(y2 - y1) * 0.4 + SAME_COLUMN_OFFSET)
        : Math.max(40, Math.abs(x2 - x1) * 0.4);
      const direction = sameColumn || !fromRight ? 1 : -1;
      const d = `M ${x1} ${y1} C ${x1 + direction * dx} ${y1 + pairOffset}, ${
        x2 + direction * dx
      } ${y2 + pairOffset}, ${x2} ${y2}`;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', edge.color);
      path.setAttribute('stroke-width', '2');
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('class', 'edge-path');
      svg.appendChild(path);

      if (!STRUCTURAL_EDGE_LABELS.has(edge.label)) {
        const label = document.createElement('div');
        label.className =
          'absolute rounded border bg-background px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap pointer-events-none';
        label.style.left = `${(x1 + x2) / 2}px`;
        label.style.top = `${(y1 + y2) / 2}px`;
        label.style.transform = 'translate(-50%, -50%)';
        label.style.color = edge.color;
        label.style.borderColor = `${edge.color}66`;
        label.textContent = edge.count > 1 ? `${edge.label} x${edge.count}` : edge.label;
        labelLayer.appendChild(label);
      }
    });
  }, [schemaData, focusedItemId]);

  useEffect(() => {
    const timer = setTimeout(drawEdges, 100);
    const handleResize = () => drawEdges();
    window.addEventListener('resize', handleResize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', handleResize);
    };
  }, [drawEdges]);

  return (
    <>
      <svg
        ref={svgRef}
        className="absolute inset-0 w-full h-full z-[4] overflow-visible pointer-events-none"
      />
      <div
        ref={labelRef}
        className="absolute inset-0 z-[5] overflow-visible pointer-events-none"
      />
    </>
  );
}

function aggregateEdges(edges: SchemaEdge[]): AggregatedEdge[] {
  const grouped = new Map<string, AggregatedEdge>();

  for (const edge of edges) {
    const key = `${edge.source}\u0000${edge.target}\u0000${edge.label}\u0000${edge.color}`;
    const existing = grouped.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      grouped.set(key, { ...edge, count: 1 });
    }
  }

  return Array.from(grouped.values());
}

function pairDirectionKey(a: string, b: string): string {
  return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
}

function incrementFan(map: Map<string, number>, itemId: string, side: 'left' | 'right') {
  const key = `${itemId}\u0000${side}`;
  map.set(key, (map.get(key) ?? 0) + 1);
}

function getFanY(
  rect: DOMRect,
  itemId: string,
  side: 'left' | 'right',
  totals: Map<string, number>,
  indexes: Map<string, number>
): number {
  const key = `${itemId}\u0000${side}`;
  const total = totals.get(key) ?? 1;
  const index = indexes.get(key) ?? 0;
  indexes.set(key, index + 1);

  const center = rect.top + rect.height / 2;
  if (total === 1) return center;

  // Spread symmetrically around item center with minimum spacing
  const minSpacing = 12;
  const naturalSpan = rect.height - 4;
  const span = Math.max(naturalSpan, (total - 1) * minSpacing);
  const step = span / (total - 1);
  return center - span / 2 + index * step;
}

function findCardElement(
  columns: { id: string; cards: { id: string; items: { id: string }[] }[] }[],
  itemId: string
): HTMLElement | null {
  for (const col of columns) {
    for (const card of col.cards) {
      if (card.items.some((item) => item.id === itemId)) {
        return document.getElementById(`card-${card.id}`);
      }
    }
  }
  return null;
}

function findItemElement(cardEl: HTMLElement, itemId: string): HTMLElement | null {
  return cardEl.querySelector(`[data-itemid="${itemId}"]`);
}
