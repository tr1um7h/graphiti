// lib/graph-layouts.ts
// 布局算法工具：直接调用 graphology 布局库对 Graph 实例设置坐标

import forceAtlas2 from 'graphology-layout-forceatlas2';
import circular from 'graphology-layout/circular';
import type Graph from 'graphology';

export type LayoutAlgorithm = 'forceatlas2' | 'circular';

/**
 * 根据节点数量计算合适的节点渲染大小
 * 节点越多，单个节点越小，避免重叠
 */
export function getNodeSize(nodeCount: number): number {
  if (nodeCount <= 20) return 12;
  if (nodeCount <= 50) return 10;
  if (nodeCount <= 100) return 8;
  if (nodeCount <= 200) return 6;
  if (nodeCount <= 500) return 4;
  return 3;
}

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
 * 将所有节点的坐标平移并以指定比例缩放，使图居中于原点附近。
 * 返回 BBox 供调用方计算相机参数。
 */
function normalizeGraph(graph: Graph): {
  centerX: number;
  centerY: number;
  width: number;
  height: number;
} {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;

  graph.forEachNode((node) => {
    const x = graph.getNodeAttribute(node, 'x') || 0;
    const y = graph.getNodeAttribute(node, 'y') || 0;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  });

  if (minX === Infinity) {
    return { centerX: 0, centerY: 0, width: 1, height: 1 };
  }

  // 平移到原点居中
  const offsetX = (minX + maxX) / 2;
  const offsetY = (minY + maxY) / 2;
  graph.forEachNode((node) => {
    graph.setNodeAttribute(node, 'x', (graph.getNodeAttribute(node, 'x') || 0) - offsetX);
    graph.setNodeAttribute(node, 'y', (graph.getNodeAttribute(node, 'y') || 0) - offsetY);
  });

  return {
    centerX: 0,
    centerY: 0,
    width: Math.max(maxX - minX, 1),
    height: Math.max(maxY - minY, 1),
  };
}

/**
 * 对 graphology Graph 实例应用指定布局算法（原地修改坐标）。
 * 布局完成后节点坐标会被归一化到以原点为中心。
 */
export function applyLayout(graph: Graph, algorithm: LayoutAlgorithm) {
  const nodeCount = graph.order;

  // 根据节点数设置节点渲染大小
  const size = getNodeSize(nodeCount);
  graph.forEachNode((node) => {
    graph.setNodeAttribute(node, 'size', size);
  });

  switch (algorithm) {
    case 'forceatlas2': {
      randomizePositions(graph);

      // 根据图规模调优 ForceAtlas2 参数
      const settings = forceAtlas2.inferSettings(graph);
      settings.slowDown = 10;
      settings.gravity = 1.2;
      settings.scalingRatio = Math.max(10, Math.min(100, 200 / Math.sqrt(nodeCount)));
      // 迭代次数：图越大越多，但上限 300 防止卡顿
      const iterations = Math.min(300, Math.max(80, nodeCount * 2));

      forceAtlas2.assign(graph, { iterations, settings });
      break;
    }
    case 'circular': {
      // scale 控制圆的半径，节点越多半径越大
      const scale = Math.max(5, Math.sqrt(nodeCount) * 1.5);
      circular.assign(graph, { scale });
      break;
    }
  }

  // 归一化坐标，让图居中于原点
  normalizeGraph(graph);
}
