// app/graph/graph-client.tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { GraphCanvas } from '@/components/graph/graph-canvas';
import { GraphControls } from '@/components/graph/graph-controls';
import { GraphLegend } from '@/components/graph/graph-legend';
import { GraphSearch } from '@/components/graph/graph-search';
import { MemoryView } from '@/components/memory-schema/memory-view';
import { useGraphStore } from '@/stores/graph-store';
import { useChatStore } from '@/stores/chat-store';
import type { GraphApiResponse } from '@/lib/types';

interface Group {
  id: string;
  name: string;
  count: number;
}

export default function GraphPageClient() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>('');
  const [viewMode, setViewMode] = useState<'graph' | 'memory'>('graph');

  // Whether a search-driven focus is active (to show "clear" button)
  const centerNode = useGraphStore((s) => s.centerNode);

  // Clear chat context when leaving the graph page so that group_id
  // is NOT carried to other pages (Zustand state persists across navigations).
  useEffect(() => {
    return () => {
      useChatStore.getState().clearContext();
    };
  }, []);

  // Load group list
  useEffect(() => {
    fetch('/api/graph/groups')
      .then((res) => res.json())
      .then((data) => {
        setGroups(data);
        // Auto-select first group if available
        if (data.length > 0 && !selectedGroup) {
          const first = data[0];
          setSelectedGroup(first.id);
          useChatStore.getState().setContext({
            context_id: first.id,
            context_type: 'group',
            context_name: first.name,
          });
        }
      })
      .catch((err) => console.error('Failed to load groups:', err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Focus on a node from search: fetch subgraph and focus view
  const handleSearchSelect = useCallback(async (nodeId: string) => {
    try {
      const res = await fetch(
        `/api/graph/subgraph?nodeId=${encodeURIComponent(nodeId)}`,
      );
      const data: GraphApiResponse = await res.json();
      useGraphStore.getState().focusNode(nodeId, data);
    } catch (err) {
      console.error('Failed to fetch subgraph:', err);
    }
  }, []);

  // Group changed → reload graph
  const handleGroupChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const groupId = e.target.value;
    const group = groups.find((g) => g.id === groupId);
    setSelectedGroup(groupId);
    useGraphStore.getState().resetFocus();
    // Sync context to Chat
    useChatStore.getState().setContext({
      context_id: groupId,
      context_type: 'group',
      context_name: group?.name || groupId,
    });
  };

  // Clear search focus → restore full graph
  const handleClearFocus = useCallback(() => {
    useGraphStore.getState().resetFocus();
  }, []);

  const groupId = selectedGroup || undefined;

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b px-4 py-2">
        {/* View mode switcher */}
        <div className="flex items-center rounded-lg border overflow-hidden">
          <button
            onClick={() => setViewMode('graph')}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              viewMode === 'graph'
                ? 'bg-accent text-foreground'
                : 'text-muted-foreground hover:bg-accent/50'
            }`}
          >
            Graph
          </button>
          <button
            onClick={() => setViewMode('memory')}
            className={`px-3 py-1.5 text-xs font-medium border-l transition-colors ${
              viewMode === 'memory'
                ? 'bg-accent text-foreground'
                : 'text-muted-foreground hover:bg-accent/50'
            }`}
          >
            Memory
          </button>
       </div>

        {viewMode === 'graph' && (
          <>
            <GraphSearch groupId={groupId} onSelect={handleSearchSelect} />
            {centerNode && (
              <button
                onClick={handleClearFocus}
                className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent"
              >
                返回全图
              </button>
            )}
          </>
        )}
        <div className="flex-1" />
        <select
          value={selectedGroup}
          onChange={handleGroupChange}
          className="flex h-9 w-[200px] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>
        {viewMode === 'graph' && <GraphControls />}
      </div>

      {/* Main area — Canvas left, Panel right */}
      <div className="relative flex-1 overflow-hidden flex">
        {/* Canvas area — popover is managed inside GraphCanvas */}
        <div className="flex-1 relative">
          {!selectedGroup && groups.length === 0 ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              暂无分组数据
            </div>
          ) : (
            viewMode === 'graph' ? (
              <GraphCanvas groupId={groupId} />
            ) : (
              <MemoryView groupId={groupId} />
            )
          )}
        </div>
      </div>

      {/* Legend bar — only for graph view */}
      {viewMode === 'graph' && <GraphLegend />}
    </div>
  );
}
