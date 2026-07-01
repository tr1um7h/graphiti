// lib/graph-layouts.ts
// 布局算法工具：直接调用 graphology 布局库对 Graph 实例设置坐标

import forceAtlas2 from 'graphology-layout-forceatlas2';
import circular from 'graphology-layout/circular';
import type Graph from 'graphology';

export type LayoutAlgorithm = 'forceatlas2' | 'circular';

/**
 * 给所有节点设置随机初始坐标（ForceAtlas2 要求节点有 x/y 才能运行）
 */
function randomizePositions(graph: Graph) {
  graph.forEachNode((node) => {
    if (graph.getNodeAttribute(node, 'x') == null) {
      graph.setNodeAttribute(node, 'x', Math.random() * 100);
    }
    if (graph.getNodeAttribute(node, 'y') == null) {
      graph.setNodeAttribute(node, 'y', Math.random() * 100);
    }
  });
}

/**
 * 对 graphology Graph 实例应用指定布局算法（原地修改坐标）。
 */
export function applyLayout(graph: Graph, algorithm: LayoutAlgorithm) {
  switch (algorithm) {
    case 'forceatlas2': {
      randomizePositions(graph);
      forceAtlas2.assign(graph, { iterations: 100 });
      break;
    }
    case 'circular': {
      circular.assign(graph, { scale: 10 });
      break;
    }
  }
}
