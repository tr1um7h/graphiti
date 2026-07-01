'use client';

import { useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
import type { RadialNode } from '@/lib/radial-utils';
import { getNodeColor } from '@/lib/graph-theme';

interface RadialGraphProps {
  data: RadialNode;
  width?: number;
  height?: number;
  onNodeClick?: (node: RadialNode) => void;
  onNodeHover?: (node: RadialNode | null) => void;
}

/** Safely read layout coordinates (d3 sets them after treeLayout()) */
function gx(node: d3.HierarchyNode<RadialNode>): number {
  return (node as unknown as { x: number }).x ?? 0;
}
function gy(node: d3.HierarchyNode<RadialNode>): number {
  return (node as unknown as { y: number }).y ?? 0;
}

export default function RadialGraph({
  data,
  width = 800,
  height = 800,
  onNodeClick,
  onNodeHover,
}: RadialGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const drawGraph = useCallback(() => {
    if (!svgRef.current || !data) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const radius = Math.min(width, height) / 2 - 80;

    // Create hierarchy & radial tree layout
    const root = d3.hierarchy<RadialNode>(data);
    d3
      .tree<RadialNode>()
      .size([2 * Math.PI, radius])
      .separation((a, b) => (a.parent === b.parent ? 1 : 2) / a.depth)
      (root);

    const g = svg
      .append('g')
      .attr('transform', `translate(${width / 2},${height / 2})`);

    const tooltip = tooltipRef.current;

    // ── Links (curved radial lines) ──
    const links = root.links();

    g.selectAll('.link')
      .data(links)
      .join('path')
      .attr('class', 'link')
      .attr(
        'd',
        (d) =>
          `M${radialPoint(gx(d.source), gy(d.source))}` +
          `C${radialPoint(gx(d.source), (gy(d.source) + gy(d.target)) / 2)}` +
          ` ${radialPoint(gx(d.target), (gy(d.source) + gy(d.target)) / 2)}` +
          ` ${radialPoint(gx(d.target), gy(d.target))}`,
      )
      .attr('fill', 'none')
      .attr('stroke', '#475569')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1.5);

    // ── Edge labels ──
    g.selectAll('.edge-label')
      .data(links.filter((l) => l.target.data.edgeLabel))
      .join('text')
      .attr('class', 'edge-label')
      .attr('transform', (d) => {
        const tx = gx(d.target);
        const ty = gy(d.target);
        const sy = gy(d.source);
        return (
          `rotate(${(tx * 180) / Math.PI - 90}) ` +
          `translate(${(sy + ty) / 2},-6) ` +
          `${tx >= Math.PI ? 'rotate(180)' : ''}`
        );
      })
      .attr('text-anchor', 'middle')
      .attr('fill', '#94a3b8')
      .attr('font-size', '10px')
      .text((d) => d.target.data.edgeLabel || '');

    // ── Nodes ──
    const descendants = root.descendants();
    const nodeGroup = g
      .selectAll('.node')
      .data(descendants)
      .join('g')
      .attr('class', 'node')
      .attr('transform', (d) => {
        const nx = gx(d);
        const ny = gy(d);
        return `rotate(${(nx * 180) / Math.PI - 90}) translate(${ny},0)`;
      });

    nodeGroup
      .append('circle')
      .attr('r', (d) => (d.depth === 0 ? 12 : 8))
      .attr('fill', (d) => getNodeColor(d.data.type))
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('click', (_event, d) => {
        onNodeClick?.(d.data);
      })
      .on('mouseenter', (event, d) => {
        d3.select(event.currentTarget)
          .transition()
          .duration(150)
          .attr('r', d.depth === 0 ? 16 : 12)
          .attr('stroke-width', 3)
          .attr('stroke', '#ffffff');

        if (tooltip) {
          tooltip.style.display = 'block';
          tooltip.style.left = `${event.pageX + 12}px`;
          tooltip.style.top = `${event.pageY - 12}px`;
          tooltip.innerHTML = `<strong>${d.data.name}</strong><br/><span style="color:#94a3b8">${d.data.type}</span>`;
        }

        onNodeHover?.(d.data);
      })
      .on('mouseleave', (event, d) => {
        d3.select(event.currentTarget)
          .transition()
          .duration(150)
          .attr('r', d.depth === 0 ? 12 : 8)
          .attr('stroke-width', 2)
          .attr('stroke', '#1e293b');

        if (tooltip) {
          tooltip.style.display = 'none';
        }

        onNodeHover?.(null);
      });

    // ── Node labels ──
    nodeGroup
      .append('text')
      .attr('dy', '0.31em')
      .attr('x', (d) => (gx(d) < Math.PI === !d.children ? 14 : -14))
      .attr('text-anchor', (d) =>
        gx(d) < Math.PI === !d.children ? 'start' : 'end',
      )
      .attr('transform', (d) => (gx(d) >= Math.PI ? 'rotate(180)' : null))
      .attr('fill', '#e2e8f0')
      .attr('font-size', '12px')
      .attr('font-weight', (d) => (d.depth === 0 ? 'bold' : 'normal'))
      .text((d) => d.data.name);
  }, [data, width, height, onNodeClick, onNodeHover]);

  useEffect(() => {
    drawGraph();
  }, [drawGraph]);

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block"
      />
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute z-50 hidden rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-md"
      />
    </div>
  );
}

/** Convert polar (angle, radius) to cartesian for SVG path data */
function radialPoint(angle: number, radius: number): string {
  return `${radius * Math.cos(angle - Math.PI / 2)},${radius * Math.sin(angle - Math.PI / 2)}`;
}
