'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useOntologyStore } from '@/stores/ontology-store';
import type { SchemaEdge } from '@/lib/types';

export function EdgeLines() {
  const svgRef = useRef<SVGSVGElement>(null);
  const schemaData = useOntologyStore((s) => s.schemaData);
  const focusedItemId = useOntologyStore((s) => s.focusedItemId);
  const relatedItemIds = useOntologyStore((s) => s.relatedItemIds);

  const drawEdges = useCallback(() => {
    const svg = svgRef.current;
    if (!svg || !schemaData || !focusedItemId) return;

    svg.innerHTML = '';

    const canvas = svg.parentElement;
    if (!canvas) return;
    const wrapRect = canvas.getBoundingClientRect();

    const relevantEdges = schemaData.edges.filter(
      (edge: SchemaEdge) => edge.source === focusedItemId || edge.target === focusedItemId
    );

    for (const edge of relevantEdges) {
      const sourceCardEl = findCardElement(schemaData.columns, edge.source);
      const targetCardEl = findCardElement(schemaData.columns, edge.target);
      if (!sourceCardEl || !targetCardEl) continue;

      const sourceItemEl = findItemElement(sourceCardEl, edge.source);
      const targetItemEl = findItemElement(targetCardEl, edge.target);
      if (!sourceItemEl || !targetItemEl) continue;

      const a = sourceItemEl.getBoundingClientRect();
      const b = targetItemEl.getBoundingClientRect();

      const x1 = a.left + a.width / 2 - wrapRect.left;
      const y1 = a.top + a.height / 2 - wrapRect.top;
      const x2 = b.left + b.width / 2 - wrapRect.left;
      const y2 = b.top + b.height / 2 - wrapRect.top;

      const dx = Math.abs(x2 - x1) * 0.65;
      const d = `M ${x1} ${y1} C ${x1 + (x2 > x1 ? dx : -dx)} ${y1}, ${x2 + (x2 > x1 ? -dx : dx)} ${y2}, ${x2} ${y2}`;

      // Define the path for textPath reference
      const pathId = `edge-path-${edge.source}-${edge.target}`;

      // Invisible path for textPath
      const pathDef = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      pathDef.setAttribute('id', pathId);
      pathDef.setAttribute('d', d);
      pathDef.setAttribute('fill', 'none');
      svg.appendChild(pathDef);

      // Visible edge path
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', edge.color);
      path.setAttribute('stroke-width', '2');
      path.setAttribute('class', 'edge-path');
      path.style.filter = 'drop-shadow(0 0 4px currentColor)';
      svg.appendChild(path);

      // Label on the bezier curve using textPath
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('class', 'edge-label');
      text.setAttribute('font-size', '13');
      text.setAttribute('font-weight', '700');
      text.setAttribute('paint-order', 'stroke fill');
      text.setAttribute('stroke', '#ffffff');
      text.setAttribute('stroke-width', '4');
      text.setAttribute('stroke-linejoin', 'round');
      text.setAttribute('fill', '#1a1a2e');

      const textPath = document.createElementNS('http://www.w3.org/2000/svg', 'textPath');
      textPath.setAttribute('href', `#${pathId}`);
      textPath.setAttribute('startOffset', '50%');
      textPath.setAttribute('text-anchor', 'middle');
      textPath.textContent = edge.label;

      text.appendChild(textPath);
      svg.appendChild(text);
    }
  }, [schemaData, focusedItemId, relatedItemIds]);

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
    <svg ref={svgRef} className="absolute inset-0 w-full h-full z-[1] overflow-visible pointer-events-none" />
  );
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
