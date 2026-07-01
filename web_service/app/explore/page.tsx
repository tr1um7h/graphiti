'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, GitBranch, GitCommit } from 'lucide-react';
import EntitySelector from '@/components/explore/entity-selector';
import RingControl from '@/components/explore/ring-control';
import RadialGraph from '@/components/explore/radial-graph';
import PathBreadcrumb from '@/components/explore/path-breadcrumb';
import RightPanel from '@/components/explore/right-panel';
import { toRadialTree, collectVisibleIds, type RadialNode } from '@/lib/radial-utils';
import type { NeighborsResponse, GraphApiResponse } from '@/lib/types';

interface PathItem {
  id: string;
  name: string;
  type: string;
}

export default function ExplorePage() {
  // Center entity state — initialized from first entity in the graph
  const [centerId, setCenterId] = useState<string | null>(null);
  const [centerName, setCenterName] = useState<string>('');
  const [centerType, setCenterType] = useState<string>('');

  // Exploration state
  const [depth, setDepth] = useState<1 | 2>(1);
  const [radialData, setRadialData] = useState<RadialNode | null>(null);
  const [path, setPath] = useState<PathItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);

  // Selection state
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeName, setHoveredNodeName] = useState<string | null>(null);

  // Visible nodes for chat context
  const visibleNodeIds = radialData ? collectVisibleIds(radialData, depth) : [];

  // Load initial entity on mount
  useEffect(() => {
    async function loadInitial() {
      try {
        const res = await fetch('/api/graph/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ limit: 10 }),
        });
        const data: GraphApiResponse = await res.json();
        if (data.nodes.length > 0) {
          const first = data.nodes[0];
          const name = (first.attributes?.name as string) || first.id;
          setCenterId(first.id);
          setCenterName(name);
          setCenterType(first.type);
          setPath([{ id: first.id, name, type: first.type }]);
        }
      } catch (err) {
        console.error('Failed to load initial entity:', err);
      } finally {
        setInitializing(false);
      }
    }
    loadInitial();
  }, []);

  // Fetch neighbors when center or depth changes
  useEffect(() => {
    if (!centerId) return;

    setLoading(true);
    fetch(`/api/graph/entities/${centerId}/neighbors?depth=${depth}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: NeighborsResponse) => {
        if (data.center) {
          const tree = toRadialTree(data);
          setRadialData(tree);
          setCenterName(data.center.name);
          setCenterType(data.center.type);
        } else {
          setRadialData(null);
        }
      })
      .catch((err) => {
        console.error('Failed to load neighbors:', err);
        setRadialData(null);
      })
      .finally(() => setLoading(false));
  }, [centerId, depth]);

  // Handle entity selection from search
  const handleEntitySelect = useCallback(
    (id: string, name: string, type: string) => {
      setCenterId(id);
      setCenterName(name);
      setCenterType(type);
      setSelectedNodeId(null);
      setPath((prev) => [...prev, { id, name, type }]);
    },
    [],
  );

  // Handle node click in radial graph — navigate to that node
  const handleNodeClick = useCallback(
    (node: RadialNode) => {
      if (node.id === centerId) return;
      setCenterId(node.id);
      setCenterName(node.name);
      setCenterType(node.type);
      setSelectedNodeId(node.id);
      setPath((prev) => [...prev, { id: node.id, name: node.name, type: node.type }]);
    },
    [centerId],
  );

  // Handle node hover
  const handleNodeHover = useCallback((node: RadialNode | null) => {
    setHoveredNodeName(node?.name ?? null);
  }, []);

  // Navigate back via breadcrumb
  const handleBreadcrumbNavigate = useCallback(
    (index: number) => {
      const target = path[index];
      if (!target) return;

      setCenterId(target.id);
      setCenterName(target.name);
      setCenterType(target.type);
      setSelectedNodeId(null);
      setPath((prev) => prev.slice(0, index + 1));
    },
    [path],
  );

  // Navigate to node from detail panel
  const handleNavigateToNode = useCallback(
    (id: string) => {
      setCenterId(id);
      setSelectedNodeId(id);
      setPath((prev) => [...prev, { id, name: id, type: '' }]);
    },
    [],
  );

  // Highlight nodes from chat
  const handleHighlightNodes = useCallback((_nodeIds: string[]) => {
    // Future: implement highlight animation on radial graph
  }, []);

  if (initializing) {
    return (
      <div className="flex h-[calc(100vh-4rem)] items-center justify-center">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Top toolbar */}
      <div className="flex items-center gap-4 border-b px-4 py-2">
        <EntitySelector onSelect={handleEntitySelect} />
        <RingControl depth={depth} onChange={setDepth} />
        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <GitBranch className="size-3.5" />
          <span>{path.length} 步</span>
          {radialData && (
            <>
              <span className="text-border">|</span>
              <GitCommit className="size-3.5" />
              <span>{radialData.children.length} 关系</span>
            </>
          )}
          {hoveredNodeName && (
            <>
              <span className="text-border">|</span>
              <span className="text-foreground">{hoveredNodeName}</span>
            </>
          )}
        </div>
      </div>

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Radial graph */}
        <div className="relative flex-1 overflow-hidden bg-background">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/60">
              <Loader2 className="size-8 animate-spin text-muted-foreground" />
            </div>
          )}
          {radialData ? (
            <div className="flex h-full items-center justify-center">
              <RadialGraph
                data={radialData}
                width={700}
                height={700}
                onNodeClick={handleNodeClick}
                onNodeHover={handleNodeHover}
              />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              {!loading && !centerId && '选择一个实体开始探索'}
              {!loading && centerId && '该实体暂无关系数据'}
            </div>
          )}
        </div>

        {/* Right: Detail panel */}
        <div className="w-80 shrink-0 border-l">
          <RightPanel
            selectedNodeId={selectedNodeId}
            centerEntityId={centerId || ''}
            centerEntityName={centerName}
            visibleNodeIds={visibleNodeIds}
            onNavigateToNode={handleNavigateToNode}
            onHighlightNodes={handleHighlightNodes}
          />
        </div>
      </div>

      {/* Bottom bar: stats + breadcrumb */}
      <div className="flex items-center justify-between border-t px-4 py-2">
        <PathBreadcrumb path={path} onNavigate={handleBreadcrumbNavigate} />
        <div className="text-xs text-muted-foreground">
          中心: {centerName} ({centerType}) | 深度: {depth}环 | 可见节点:{' '}
          {visibleNodeIds.length}
        </div>
      </div>
    </div>
  );
}
