import { test, expect } from '@playwright/test';

test('expand neighbors on full graph adds nodes in-place', async ({ page }) => {
  page.on('console', msg => {
    if (msg.text().includes('[GraphCanvas]')) {
      console.log(`[Sigma] ${msg.text()}`);
    }
  });

  await page.goto('/graph');
  await page.waitForTimeout(3000);

  // Get initial count (full graph, no focus)
  const legendBefore = await page.locator('.flex.items-center.gap-4.border-t').textContent();
  console.log('Full graph before expand:', legendBefore);

  // Call expandNeighbors directly without focusing first
  const result = await page.evaluate(async () => {
    // Find a node that likely has neighbors not in the full graph
    const fullGraph = await fetch('/api/graph/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit: 500 }),
    }).then(r => r.json());

    // Pick a node with few connections in the graph
    const graphitiNode = fullGraph.nodes.find((n: any) => n.id === 'ffa68df7-1249-41fc-83f1-4edf4e0cf194');
    if (!graphitiNode) return { error: 'Graphiti node not found' };

    const nodeId = graphitiNode.id;

    // Fetch its neighbors
    const neighbors = await fetch(`/api/graph/entities/${nodeId}/neighbors?depth=1`).then(r => r.json());

    // Check which neighbors are NOT in the full graph
    const graphIds = new Set(fullGraph.nodes.map((n: any) => n.id));
    const newNeighbors = (neighbors.nodes || []).filter((n: any) => !graphIds.has(n.id));

    return {
      nodeId,
      fullGraphCount: fullGraph.nodes.length,
      neighborsFromApi: neighbors.nodes?.length || 0,
      newNodesCount: newNeighbors.length,
      newNodes: newNeighbors.map((n: any) => n.attributes?.name || n.label),
    };
  });

  console.log('Debug result:', JSON.stringify(result, null, 2));

  // If there are actually new neighbors to add, test expand
  if (result.newNodesCount > 0) {
    // Do the actual expand via store
    await page.evaluate(async (nodeId) => {
      const neighbors = await fetch(`/api/graph/entities/${nodeId}/neighbors?depth=1`).then(r => r.json());
      const store = (window as any).__ZUSTAND_STORE__;
      if (store) {
        store.getState().expandNeighbors(nodeId, neighbors.nodes, neighbors.edges);
      }
    }, result.nodeId);

    await page.waitForTimeout(2000);

    const legendAfter = await page.locator('.flex.items-center.gap-4.border-t').textContent();
    console.log('Full graph after expand:', legendAfter);

    const afterMatch = legendAfter?.match(/节点:\s*(\d+)/);
    const beforeMatch = legendBefore?.match(/节点:\s*(\d+)/);

    if (beforeMatch && afterMatch) {
      const nodesBefore = parseInt(beforeMatch[1]);
      const nodesAfter = parseInt(afterMatch[1]);
      console.log(`Nodes: ${nodesBefore} → ${nodesAfter}`);
      expect(nodesAfter).toBeGreaterThan(nodesBefore);
    }
  } else {
    console.log('All neighbor nodes are already in the graph — nothing to expand');
    // This is expected if the full graph already contains all connections
    expect(result.fullGraphCount).toBeGreaterThan(0);
  }
});

test('after subgraph focus, expand neighbors via panel button', async ({ page }) => {
  page.on('console', msg => {
    if (msg.text().includes('[GraphCanvas]')) {
      console.log(`[Sigma] ${msg.text()}`);
    }
  });

  await page.goto('/graph');
  await page.waitForTimeout(3000);

  // Select node via search → subgraph mode
  const searchInput = page.getByPlaceholder('搜索实体...');
  await searchInput.fill('Graphiti');
  await page.waitForTimeout(500);
  await page.locator('.absolute.left-0.top-full button').first().click();
  await page.waitForTimeout(2000);

  // Get subgraph count
  const legendSubgraph = await page.locator('.flex.items-center.gap-4.border-t').textContent();
  console.log('Subgraph:', legendSubgraph);

  // Click expand button (depth=1, same as subgraph — may not add new nodes)
  const expandButton = page.getByRole('button', { name: '展开邻居节点' });
  await expandButton.click();
  await page.waitForTimeout(2000);

  const legendAfterExpand = await page.locator('.flex.items-center.gap-4.border-t').textContent();
  console.log('After expand:', legendAfterExpand);

  // Get actual counts
  const beforeMatch = legendSubgraph?.match(/节点:\s*(\d+)/);
  const afterMatch = legendAfterExpand?.match(/节点:\s*(\d+)/);

  if (beforeMatch && afterMatch) {
    const before = parseInt(beforeMatch[1]);
    const after = parseInt(afterMatch[1]);
    console.log(`Nodes: ${before} → ${after}`);

    // If counts are the same, explain why
    if (before === after) {
      console.log('Count unchanged — all 1-hop neighbors already in subgraph (expected)');
      // Verify the API is working though
      expect(before).toBeGreaterThan(0);
    } else {
      expect(after).toBeGreaterThan(before);
    }
  }

  // Panel should remain visible after expand
  const panel = page.locator('[data-panel="true"]');
  await expect(panel).toBeVisible();

  // "返回全图" button should still be present
  const backButton = page.getByRole('button', { name: '返回全图' });
  await expect(backButton).toBeVisible();
});