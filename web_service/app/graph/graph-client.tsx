// app/graph/graph-client.tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { GraphCanvas } from '@/components/graph/graph-canvas';
import { GraphControls } from '@/components/graph/graph-controls';
import { GraphLegend } from '@/components/graph/graph-legend';
import { NodeDetailPopover } from '@/components/graph/node-detail-popover';
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

  // Popover state: which node is focused and where to position the popover
  const [popover, setPopover] = useState<{
    nodeId: string;
    x: number;
    y: number;
  } | null>(null);

  // Whether a search-driven focus is active (to show "clear" button)
  const centerNode = useGraphStore((s) => s.centerNode);

  // Load group list
  useEffect(() => {
    fetch('/api/graph/groups')
      .then((res) => res.json())
      .then((data) => setGroups(data))
      .catch((err) => console.error('Failed to load groups:', err));
  }, []);

  // Search result selected → fetch subgraph and focus
  const handleSearchSelect = useCallback(async (nodeId: string) => {
    try {
      const res = await fetch(
        `/api/graph/subgraph?nodeId=${encodeURIComponent(nodeId)}`,
      );
      const data: GraphApiResponse = await res.json();
      useGraphStore.getState().focusNode(nodeId, data);
      // Close any open popover
      setPopover(null);
    } catch (err) {
      console.error('Failed to fetch subgraph:', err);
    }
  }, []);

  // Group changed → GraphCanvas will reload via groupId prop
  const handleGroupChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const groupId = e.target.value;
    setSelectedGroup(groupId);
    setPopover(null);
  };

  // Node clicked in canvas → show popover
  const handleNodeClick = useCallback(
    (nodeId: string, screenX: number, screenY: number) => {
      setPopover({ nodeId, x: screenX, y: screenY });
    },
    [],
  );

  // Background clicked → close popover
  const handleBackgroundClick = useCallback(() => {
    setPopover(null);
  }, []);

  // Global click listener: close popover when clicking outside.
  // IMPORTANT: ignore clicks on the Sigma canvas — those are handled by
  // sigma.on('clickNode') / sigma.on('clickStage') respectively.
  // Without this, the document-level handler would run AFTER clickNode
  // and immediately close the popover that clickNode just opened.
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (!popover) return;
      const target = e.target as HTMLElement;
      // If the click is inside the popover, ignore
      if (target.closest('[data-popover="true"]')) return;
      // If the click is on the Sigma canvas, let Sigma events handle it
      if (target.closest('canvas') || target.tagName === 'CANVAS') return;
      setPopover(null);
    };
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [popover]);

  // Clear search focus → restore full graph
  const handleClearFocus = useCallback(() => {
    useGraphStore.getState().resetFocus();
    setPopover(null);
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
            清除搜索
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

      {/* Main area — Sigma canvas fills the entire space */}
      <div className="relative flex-1 overflow-hidden">
        <GraphCanvas
          groupId={groupId}
          onNodeClick={handleNodeClick}
          onBackgroundClick={handleBackgroundClick}
        />
        <NodeDetailPopover
          nodeId={popover?.nodeId ?? null}
          x={popover?.x ?? 0}
          y={popover?.y ?? 0}
        />
      </div>

      {/* Legend bar */}
      <GraphLegend />
    </div>
  );
}
