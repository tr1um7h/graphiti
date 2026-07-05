// components/graph/graph-canvas.tsx
'use client';

import { useEffect, useRef, useState } from 'react';
import Sigma from 'sigma';
import { useGraphStore } from '@/stores/graph-store';
import type { GraphApiResponse } from '@/lib/types';
import { applyLayout } from '@/lib/graph-layouts';

interface GraphCanvasProps {
  className?: string;
  groupId?: string;
  onNodeClick?: (nodeId: string) => void;
  onBackgroundClick?: () => void;
}

export function GraphCanvas({
  className,
  groupId,
  onNodeClick,
  onBackgroundClick,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  // Click detection state (component-level refs)
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastClickNodeRef = useRef<string | null>(null);

  // Subscribe to graph data AND layout algorithm
  const graph = useGraphStore((s) => s.graph);
  const layoutAlgorithm = useGraphStore((s) => s.layoutAlgorithm);
  const [loading, setLoading] = useState(true);

  // Keep the latest callbacks in refs
  const onNodeClickRef = useRef(onNodeClick);
  const onBackgroundClickRef = useRef(onBackgroundClick);
  onNodeClickRef.current = onNodeClick;
  onBackgroundClickRef.current = onBackgroundClick;

  // Load graph data when groupId changes
  useEffect(() => {
    async function loadGraph() {
      try {
        setLoading(true);
        const body: any = { limit: 500 };
        if (groupId) {
          body.group_ids = [groupId];
        }
        const res = await fetch('/api/graph/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data: GraphApiResponse = await res.json();
        useGraphStore.getState().loadGraph(data);
      } catch (err) {
        console.error('Failed to load graph:', err);
      } finally {
        setLoading(false);
      }
    }
    loadGraph();
  }, [groupId]);

  // Initialize Sigma when graph instance changes
  // - focusNode replaces graph → triggers rebuild (correct: shows new subgraph)
  // - expandNeighbors modifies graph → reference unchanged, Sigma auto-updates via graphology events
  useEffect(() => {
    if (!containerRef.current || !graph) return;

    console.log('[GraphCanvas] Initializing Sigma with graph:', graph.order, 'nodes');

    // Clean up previous Sigma instance
    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }

    // Clear pending click timer
    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
    lastClickNodeRef.current = null;

    // Apply initial layout
    applyLayout(graph, layoutAlgorithm);

    const sigma = new Sigma(graph, containerRef.current, {
      renderEdgeLabels: graph.order < 2000,
      defaultEdgeType: 'arrow',
      labelFont: 'Inter, system-ui, sans-serif',
      labelSize: 12,
      labelRenderedSizeThreshold: 6,
      minCameraRatio: 0.1,
      maxCameraRatio: 10,
    });

    sigmaRef.current = sigma;

    // --- Event handlers ---
    sigma.on('doubleClickNode', ({ node }) => {
      console.log('[GraphCanvas] Double click - expanding neighbors on current graph');
      // Cancel any pending single-click timer
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      lastClickNodeRef.current = null;

      fetch(`/api/graph/entities/${node}/neighbors?depth=1`)
        .then((res) => res.json())
        .then((data) => {
          console.log('[GraphCanvas] Adding', data.nodes?.length, 'neighbors to current graph');
          useGraphStore.getState().expandNeighbors(node, data.nodes, data.edges);
        })
        .catch((err) => console.error('[GraphCanvas] Expand failed:', err));
    });

    sigma.on('clickNode', ({ node }) => {
      // Single click: use timer to distinguish from double click.
      // If doubleClickNode fires within the window, it cancels the timer.
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
      }

      lastClickNodeRef.current = node;

      clickTimerRef.current = setTimeout(() => {
        if (lastClickNodeRef.current === node) {
          console.log('[GraphCanvas] Single click confirmed - focusing subgraph');
          onNodeClickRef.current?.(node);
          lastClickNodeRef.current = null;
        }
      }, 300);
    });

    sigma.on('enterNode', ({ node }) => {
      useGraphStore.getState().setHoveredNode(node);
    });

    sigma.on('leaveNode', () => {
      useGraphStore.getState().setHoveredNode(null);
    });

    sigma.on('clickStage', () => {
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      lastClickNodeRef.current = null;
      onBackgroundClickRef.current?.();
    });

    return () => {
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
    };
  }, [graph]); // Re-run when graph instance is replaced (loadGraph/focusNode)

  // Re-apply layout when layoutAlgorithm changes
  useEffect(() => {
    if (!graph || !sigmaRef.current) return;
    applyLayout(graph, layoutAlgorithm);
    sigmaRef.current.refresh();
  }, [layoutAlgorithm]);

  if (loading || !graph) {
    return (
      <div className="flex h-full items-center justify-center bg-muted/30">
        <div className="text-center">
          <div className="mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">加载图谱中...</p>
        </div>
      </div>
    );
  }

  return <div ref={containerRef} className={className || 'h-full w-full'} />;
}