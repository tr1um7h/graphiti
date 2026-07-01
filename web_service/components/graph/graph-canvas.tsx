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
  onNodeClick?: (nodeId: string, screenX: number, screenY: number) => void;
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

  // Subscribe to graph data AND layout algorithm
  const graph = useGraphStore((s) => s.graph);
  const layoutAlgorithm = useGraphStore((s) => s.layoutAlgorithm);
  const [loading, setLoading] = useState(true);

  // Keep the latest callbacks in refs so the Sigma init effect
  // (which only depends on `graph`) always has fresh values
  // without needing to re-create Sigma.
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

  // Initialize Sigma renderer — only re-run when graph changes
  useEffect(() => {
    if (!containerRef.current || !graph) return;

    // Clean up previous instance
    if (sigmaRef.current) {
      sigmaRef.current.kill();
      sigmaRef.current = null;
    }

    // Apply initial layout before rendering
    const currentLayout = useGraphStore.getState().layoutAlgorithm;
    applyLayout(graph, currentLayout);

    const sigma = new Sigma(graph, containerRef.current, {
      renderEdgeLabels: graph.order < 2000,
      defaultEdgeType: 'arrow',
      labelFont: 'Inter, system-ui, sans-serif',
      labelSize: 12,
      labelRenderedSizeThreshold: 6,
      minCameraRatio: 0.1,
      maxCameraRatio: 10,
    });

    // Click node → notify parent with screen coordinates
    // IMPORTANT: call preventSigmaDefault() to stop clickStage from also firing,
    // which would immediately close the popover.
    sigma.on('clickNode', ({ node, event, preventSigmaDefault }) => {
      preventSigmaDefault();
      const container = containerRef.current;
      if (!container) return;
      // Sigma v3 provides event.x / event.y as viewport coordinates
      // relative to the canvas. We add the container's page offset.
      const rect = container.getBoundingClientRect();
      const screenX = rect.left + (event.x ?? 0);
      const screenY = rect.top + (event.y ?? 0);
      onNodeClickRef.current?.(node, screenX, screenY);
    });

    // Double click → expand neighbors
    sigma.on('doubleClickNode', async ({ node }) => {
      try {
        const res = await fetch(
          `/api/graph/entities/${node}/neighbors?depth=1`,
        );
        const data = await res.json();
        useGraphStore
          .getState()
          .expandNeighbors(node, data.nodes, data.edges);
      } catch (err) {
        console.error('Failed to expand neighbors:', err);
      }
    });

    // Hover → highlight
    sigma.on('enterNode', ({ node }) => {
      useGraphStore.getState().setHoveredNode(node);
    });
    sigma.on('leaveNode', () => {
      useGraphStore.getState().setHoveredNode(null);
    });

    // Click background → deselect
    sigma.on('clickStage', () => {
      onBackgroundClickRef.current?.();
    });

    sigmaRef.current = sigma;

    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph]); // <-- only depends on graph

  // Re-apply layout when layoutAlgorithm changes (without recreating Sigma)
  useEffect(() => {
    if (!graph || !sigmaRef.current) return;
    applyLayout(graph, layoutAlgorithm);
    sigmaRef.current.refresh();
    // Reset camera to center the graph after layout change
    sigmaRef.current.getCamera().setState({ x: 0.5, y: 0.5, ratio: 1, angle: 0 });
  }, [layoutAlgorithm, graph]);

  // Auto-center camera after initial graph load
  useEffect(() => {
    if (!graph || !sigmaRef.current) return;
    sigmaRef.current.getCamera().setState({ x: 0.5, y: 0.5, ratio: 1, angle: 0 });
  }, [graph]);

  if (loading) {
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
