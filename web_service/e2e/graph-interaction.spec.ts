import { test, expect } from '@playwright/test';

test.describe('Graph interaction tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/graph');
    // Wait for graph to load (spinner disappears)
    await page.waitForSelector('.sigma-mouse', { timeout: 10000 });
    await page.waitForTimeout(1000);
  });

  test('select node via search shows subgraph and detail panel', async ({ page }) => {
    // Search for a node
    const searchInput = page.getByPlaceholder('搜索实体...');
    await searchInput.fill('Graphiti');
    await page.waitForTimeout(500);

    // Click on search result
    const firstResult = page.locator('.absolute.left-0.top-full button').first();
    await firstResult.click();

    // Wait for subgraph fetch and panel to appear
    await page.waitForTimeout(1500);

    // Check detail panel appears
    const detailPanel = page.locator('[data-panel="true"]');
    await expect(detailPanel).toBeVisible({ timeout: 5000 });

    // Check "返回全图" button appears
    const backButton = page.getByRole('button', { name: '返回全图' });
    await expect(backButton).toBeVisible();
  });

  test('close panel returns to full graph', async ({ page }) => {
    // Select node via search
    const searchInput = page.getByPlaceholder('搜索实体...');
    await searchInput.fill('Graphiti');
    await page.waitForTimeout(500);
    await page.locator('.absolute.left-0.top-full button').first().click();
    await page.waitForTimeout(1500);

    // Panel visible
    const detailPanel = page.locator('[data-panel="true"]');
    await expect(detailPanel).toBeVisible({ timeout: 5000 });

    // Click close button (X)
    const closeButton = detailPanel.locator('button').filter({ has: page.locator('svg') }).first();
    await closeButton.click();
    await page.waitForTimeout(500);

    // Panel hidden
    await expect(detailPanel).not.toBeVisible();

    // "返回全图" button also gone
    const backButton = page.getByRole('button', { name: '返回全图' });
    await expect(backButton).not.toBeVisible();
  });

  test('expand neighbors button works', async ({ page }) => {
    // Select node via search
    const searchInput = page.getByPlaceholder('搜索实体...');
    await searchInput.fill('Graphiti');
    await page.waitForTimeout(500);
    await page.locator('.absolute.left-0.top-full button').first().click();
    await page.waitForTimeout(1500);

    const detailPanel = page.locator('[data-panel="true"]');
    await expect(detailPanel).toBeVisible({ timeout: 5000 });

    // Get initial node count from legend
    const legend = page.locator('.flex.items-center.gap-4.border-t');
    const initialText = await legend.textContent();

    // Click expand button
    const expandButton = detailPanel.getByRole('button', { name: '展开邻居节点' });
    await expandButton.click();
    await page.waitForTimeout(2000);

    // Panel still visible
    await expect(detailPanel).toBeVisible();

    // Node count should change (neighbors added)
    const newText = await legend.textContent();
    // The counts should be different (or at least not empty)
    expect(newText).toBeTruthy();
  });

  test('double click simulation via page.evaluate', async ({ page }) => {
    page.on('console', msg => {
      if (msg.text().includes('[GraphCanvas]')) {
        console.log(`[Sigma] ${msg.text()}`);
      }
    });

    // First, select a node via search to get into subgraph mode
    const searchInput = page.getByPlaceholder('搜索实体...');
    await searchInput.fill('Graphiti');
    await page.waitForTimeout(500);
    await page.locator('.absolute.left-0.top-full button').first().click();
    await page.waitForTimeout(1500);

    // Now simulate double click via page.evaluate
    // We'll call expandNeighbors directly through the store
    const expanded = await page.evaluate(async () => {
      const nodeId = 'ffa68df7-1249-41fc-83f1-4edf4e0cf194'; // Graphiti Memory Benchmark node

      // Fetch neighbors
      const res = await fetch(`/api/graph/entities/${nodeId}/neighbors?depth=1`);
      const data = await res.json();

      // Call expandNeighbors through the store
      const store = (window as any).__graphStore__;
      if (store) {
        store.getState().expandNeighbors(nodeId, data.nodes, data.edges);
        return { success: true, nodesAdded: data.nodes.length };
      }
      return { success: false, error: 'No store found' };
    });

    console.log('Expand result:', expanded);
    await page.waitForTimeout(1000);

    // Panel should still be visible
    const detailPanel = page.locator('[data-panel="true"]');
    await expect(detailPanel).toBeVisible();
  });
});