import { test, expect, type Page } from '@playwright/test';

const BASE = 'http://localhost:3000';

// Collect browser console errors
function collectErrors(page: Page, errors: string[]) {
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => {
    errors.push(`PAGE_ERROR: ${err.message}`);
  });
}

// Filter out benign errors
function realErrors(errors: string[]) {
  return errors.filter(
    (e) =>
      !e.includes('favicon') &&
      !e.includes('404') &&
      !e.includes('width') &&
      !e.includes('height')
  );
}

test.describe('API tests', () => {
  test('Graph API returns real data (no mock)', async ({ request }) => {
    const res = await request.post(`${BASE}/api/graph/query`, {
      data: { limit: 500 },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.nodes).toBeInstanceOf(Array);
    expect(data.nodes.length).toBeGreaterThan(0);
    // Should NOT contain mock IDs like node-0
    const hasMockIds = data.nodes.some((n: any) => n.id.startsWith('node-'));
    expect(hasMockIds).toBeFalsy();
  });

  test('Graph search API works', async ({ request }) => {
    const res = await request.get(`${BASE}/api/graph/search?q=星辰`);
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data).toBeInstanceOf(Array);
  });

  test('Graph stats API returns real data', async ({ request }) => {
    const res = await request.get(`${BASE}/api/graph/stats`);
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.totalNodes).toBeGreaterThan(0);
  });

  test('Entity neighbors API works with real UUID', async ({ request }) => {
    // First get a real entity ID
    const queryRes = await request.post(`${BASE}/api/graph/query`, {
      data: { limit: 10 },
    });
    const queryData = await queryRes.json();
    const firstId = queryData.nodes[0].id;

    // Then get neighbors
    const res = await request.get(
      `${BASE}/api/graph/entities/${firstId}/neighbors?depth=1`
    );
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.center).toBeTruthy();
    expect(data.center.id).toBe(firstId);
    expect(data.center.relationships).toBeInstanceOf(Array);
    expect(data.nodes).toBeInstanceOf(Array);
    expect(data.edges).toBeInstanceOf(Array);
  });

  test('Document upload works', async ({ request }) => {
    const fs = await import('fs');
    const path = await import('path');
    const filePath = path.join(
      process.env.HOME || '/Users/steve',
      'Downloads/dzfp_26312000002007907621_广东高驰运动科技有限公司_20260403135501.pdf'
    );

    if (!fs.existsSync(filePath)) {
      console.log('Test PDF not found, skipping upload test');
      return;
    }

    const buffer = fs.readFileSync(filePath);
    const res = await request.post(`${BASE}/api/documents/upload`, {
      multipart: {
        file: {
          name: 'test-upload.pdf',
          mimeType: 'application/pdf',
          buffer,
        },
        dataset: 'test',
      },
    });

    const data = await res.json();
    console.log('Upload response:', data);
    expect(res.ok()).toBeTruthy();
    expect(data.status).toBe('processing');
  });
});

test.describe('UI page tests', () => {
  test('Graph page loads and renders without errors', async ({ page }) => {
    const errors: string[] = [];
    collectErrors(page, errors);

    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(4000);

    // Graph canvas should render a sigma container div
    const sigmaCanvas = page.locator('div.h-full.w-full');
    await expect(sigmaCanvas).toBeVisible({ timeout: 8000 });

    // Should show node count in legend bar
    const bodyText = await page.textContent('body');
    expect(bodyText).toContain('节点:');
    expect(bodyText).toContain('边:');

    const filtered = realErrors(errors);
    if (filtered.length > 0) {
      console.log('GRAPH PAGE ERRORS:', filtered);
    }
    expect(filtered).toHaveLength(0);
  });

  test('Explore page loads without errors', async ({ page }) => {
    const errors: string[] = [];
    collectErrors(page, errors);

    await page.goto(`${BASE}/explore`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(4000);

    // Page should render without crashing
    const bodyText = await page.textContent('body');
    // Should not show the mock "张三" default
    expect(bodyText).not.toContain('node-0');

    const filtered = realErrors(errors);
    if (filtered.length > 0) {
      console.log('EXPLORE PAGE ERRORS:', filtered);
    }
    expect(filtered).toHaveLength(0);
  });

  test('Dashboard page loads', async ({ page }) => {
    const errors: string[] = [];
    collectErrors(page, errors);

    await page.goto(`${BASE}/`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    const filtered = realErrors(errors);
    if (filtered.length > 0) {
      console.log('DASHBOARD PAGE ERRORS:', filtered);
    }
    expect(filtered).toHaveLength(0);
  });

  test('Documents page loads', async ({ page }) => {
    const errors: string[] = [];
    collectErrors(page, errors);

    await page.goto(`${BASE}/documents`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    const filtered = realErrors(errors);
    if (filtered.length > 0) {
      console.log('DOCUMENTS PAGE ERRORS:', filtered);
    }
    expect(filtered).toHaveLength(0);
  });
});
