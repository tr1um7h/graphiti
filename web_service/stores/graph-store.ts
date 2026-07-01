// stores/graph-store.ts

import { create } from 'zustand';
import Graph from 'graphology';
import type { GraphApiResponse, GraphNode, GraphEdge } from '@/lib/types';
import { buildGraph, addNeighborNodes } from '@/lib/graph-utils';

interface GraphState {
  // fullGraph holds the complete dataset for the current group.
  // It is preserved so we can quickly toggle between full view and
  // focused sub-graph view without a round-trip to the server.
  fullGraph: Graph | null;
  // graph is what Sigma actually renders. When the user searches and
  // focuses on a node, graph becomes a sub-graph; resetFocus restores
  // it from fullGraph.
  graph: Graph | null;
  centerNode: string | null;
  hoveredNode: string | null;
  hiddenTypes: Set<string>;
  layoutAlgorithm: 'forceatlas2' | 'circular';
  isLayoutRunning: boolean;
  nodeCount: number;
  edgeCount: number;

  loadGraph: (data: GraphApiResponse) => void;
  focusNode: (nodeId: string, subGraphData: GraphApiResponse) => void;
  resetFocus: () => void;
  setHoveredNode: (id: string | null) => void;
  expandNeighbors: (
    nodeId: string,
    nodes: GraphNode[],
    edges: GraphEdge[],
  ) => void;
  toggleType: (type: string) => void;
  setLayoutAlgorithm: (algorithm: GraphState['layoutAlgorithm']) => void;
  setLayoutRunning: (running: boolean) => void;
}

export const useGraphStore = create<GraphState>((set, get) => ({
  fullGraph: null,
  graph: null,
  centerNode: null,
  hoveredNode: null,
  hiddenTypes: new Set(),
  layoutAlgorithm: 'forceatlas2',
  isLayoutRunning: false,
  nodeCount: 0,
  edgeCount: 0,

  loadGraph: (data: GraphApiResponse) => {
    const graph = buildGraph(data);
    set({
      graph,
      fullGraph: graph,          // keep a reference for resetFocus
      nodeCount: data.nodes.length,
      edgeCount: data.edges.length,
      centerNode: null,
      hoveredNode: null,
    });
  },

  focusNode: (nodeId: string, subGraphData: GraphApiResponse) => {
    const subGraph = buildGraph(subGraphData);
    set({
      graph: subGraph,
      centerNode: nodeId,
      nodeCount: subGraphData.nodes.length,
      edgeCount: subGraphData.edges.length,
      hoveredNode: null,
    });
  },

  resetFocus: () => {
    const { fullGraph } = get();
    if (!fullGraph) return;
    set({
      graph: fullGraph,
      centerNode: null,
      nodeCount: fullGraph.order,
      edgeCount: fullGraph.size,
      hoveredNode: null,
    });
  },

  setHoveredNode: (id: string | null) => {
    set({ hoveredNode: id });
  },

  expandNeighbors: (
    nodeId: string,
    nodes: GraphNode[],
    edges: GraphEdge[],
  ) => {
    const { graph } = get();
    if (!graph) return;
    addNeighborNodes(graph, nodes, edges, nodeId);
    set({
      nodeCount: graph.order,
      edgeCount: graph.size,
    });
  },

  toggleType: (type: string) => {
    const { hiddenTypes, graph } = get();
    const newHidden = new Set(hiddenTypes);
    if (newHidden.has(type)) {
      newHidden.delete(type);
    } else {
      newHidden.add(type);
    }
    set({ hiddenTypes: newHidden });

    if (graph) {
      graph.forEachNode((node) => {
        const nodeType = graph.getNodeAttribute(node, 'nodeType') as string;
        graph.setNodeAttribute(node, 'hidden', newHidden.has(nodeType));
      });
    }
  },

  setLayoutAlgorithm: (algorithm) => {
    set({ layoutAlgorithm: algorithm });
  },

  setLayoutRunning: (running: boolean) => {
    set({ isLayoutRunning: running });
  },
}));
