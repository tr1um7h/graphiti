// app/graph/graph-client.tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { GraphCanvas } from '@/components/graph/graph-canvas';
import { GraphControls } from '@/components/graph/graph-controls';
import { GraphLegend } from '@/components/graph/graph-legend';
import { NodeDetailPanel } from '@/components/graph/node-detail-panel';
import { GraphSearch } from '@/components/graph/graph-search';
import { useGraphStore } from '@/stores/graph-store';
import type { GraphApiResponse } from '@/lib/types';

interface Group {
  id: string;
  name: string;
  count: number;
}

export default function GraphPageClient() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>('all');

  // Selected node for right panel (null = panel hidden)
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  // Whether a focus is active (from search or node click)
  const centerNode = useGraphStore((s) => s.centerNode);

  // Load group list
  useEffect(() => {
    fetch('/api/graph/groups')
      .then((res) => res.json())
      .then((data) => setGroups(data))
      .catch((err) => console.error('Failed to load groups:', err));
  }, []);

  // Focus on a node: fetch subgraph and show right panel
  const focusOnNode = useCallback(async (nodeId: string) => {
    try {
      const res = await fetch(
        `/api/graph/subgraph?nodeId=${encodeURIComponent(nodeId)}`,
      );
      const data: GraphApiResponse = await res.json();
      useGraphStore.getState().focusNode(nodeId, data);
      setSelectedNode(nodeId);
    } catch (err) {
      console.error('Failed to fetch subgraph:', err);
    }
  }, []);

  // Search result selected → focus on node
  const handleSearchSelect = useCallback(async (nodeId: string) => {
    await focusOnNode(nodeId);
  }, [focusOnNode]);

  // Node clicked in canvas → focus on node
  const handleNodeClick = useCallback(async (nodeId: string) => {
    await focusOnNode(nodeId);
  }, [focusOnNode]);

  // Group changed → reload graph
  const handleGroupChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const groupId = e.target.value;
    setSelectedGroup(groupId);
    setSelectedNode(null);
    useGraphStore.getState().resetFocus();
  };

  // Background clicked → close panel and reset focus
  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
    useGraphStore.getState().resetFocus();
  }, []);

  // Close panel → reset focus
  const handleClosePanel = useCallback(() => {
    setSelectedNode(null);
    useGraphStore.getState().resetFocus();
  }, []);

  // Expand neighbors (from panel button)
  const handleExpandNeighbors = useCallback(async (nodeId: string) => {
    try {
      const res = await fetch(
        `/api/graph/entities/${nodeId}/neighbors?depth=1`,
      );
      const data = await res.json();
      useGraphStore.getState().expandNeighbors(nodeId, data.nodes, data.edges);
    } catch (err) {
      console.error('Failed to expand neighbors:', err);
    }
  }, []);

  // Clear search focus → restore full graph
  const handleClearFocus = useCallback(() => {
    setSelectedNode(null);
    useGraphStore.getState().resetFocus();
  }, []);

  const groupId = selectedGroup === 'all' ? undefined : selectedGroup;

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b px-4 py-2">
        <GraphSearch groupId={groupId} onSelect={handleSearchSelect} />
        {centerNode && (
          <button
            onClick={handleClearFocus}
            className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
          >
            返回全图
          </button>
        )}
        <div className="flex-1" />
        <select
          value={selectedGroup}
          onChange={handleGroupChange}
          className="flex h-9 w-[200px] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <option value="all">所有分组</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name} ({group.count})
            </option>
          ))}
        </select>
        <GraphControls />
      </div>

      {/* Main area — Canvas left, Panel right */}
      <div className="relative flex-1 overflow-hidden flex">
        {/* Canvas area */}
        <div className="flex-1 relative">
          <GraphCanvas
            groupId={groupId}
            onNodeClick={handleNodeClick}
            onBackgroundClick={handleBackgroundClick}
          />
        </div>

        {/* Right panel (conditional) */}
        {selectedNode && (
          <NodeDetailPanel
            nodeId={selectedNode}
            onClose={handleClosePanel}
            onExpandNeighbors={handleExpandNeighbors}
          />
        )}
      </div>

      {/* Legend bar */}
      <GraphLegend />
    </div>
  );
}