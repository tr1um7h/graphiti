import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:3000';

function collectErrors(page: import('@playwright/test').Page, errors: string[]) {
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => {
    errors.push(`PAGE_ERROR: ${err.message}`);
  });
}

function realErrors(errors: string[]) {
  return errors.filter(
    (e) => !e.includes('favicon') && !e.includes('404') && !e.includes('width') && !e.includes('height')
  );
}

test.describe('Fix verification: Graph edges', () => {
  test('Graph page should display edges after fix', async ({ page }) => {
    const errors: string[] = [];
    collectErrors(page, errors);

    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(5000);

    // Check API response has edges
    const apiEdges = await page.evaluate(async () => {
      const res = await fetch('/api/graph/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: 500 }),
      });
      const data = await res.json();
      return data.edges?.length ?? 0;
    });
    console.log(`API edges: ${apiEdges}`);
    expect(apiEdges).toBeGreaterThan(0);

    // Check legend bar shows non-zero edge count
    const bodyText = await page.textContent('body');
    const edgeMatch = bodyText?.match(/边[:\s]*(\d+)/);
    const edgeCount = edgeMatch ? parseInt(edgeMatch[1]) : 0;
    console.log(`Legend edge count: ${edgeCount}`);
    expect(edgeCount).toBeGreaterThan(0);

    // Take screenshot for visual verification
    await page.screenshot({ path: 'test-results/graph-with-edges.png', fullPage: true });

    const filtered = realErrors(errors);
    if (filtered.length > 0) console.log('ERRORS:', filtered);
    expect(filtered).toHaveLength(0);
  });

  test('Graph stats API reports edges', async ({ request }) => {
    const res = await request.get(`${BASE}/api/graph/stats`);
    const data = await res.json();
    console.log(`Stats: ${data.totalNodes} nodes, ${data.totalEdges} edges`);
    expect(data.totalNodes).toBeGreaterThan(0);
    expect(data.totalEdges).toBeGreaterThan(0);
  });
});

test.describe('Fix verification: Documents upload', () => {
  test('Documents page renders with existing documents', async ({ page }) => {
    const errors: string[] = [];
    collectErrors(page, errors);

    await page.goto(`${BASE}/documents`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    const bodyText = await page.textContent('body');
    expect(bodyText).toContain('documents total');

    const tableRows = page.locator('table tbody tr');
    const rowCount = await tableRows.count();
    console.log(`Document rows: ${rowCount}`);
    expect(rowCount).toBeGreaterThan(0);

    const filtered = realErrors(errors);
    if (filtered.length > 0) console.log('ERRORS:', filtered);
    expect(filtered).toHaveLength(0);
  });

  test('Uploaded document appears in the table after processing', async ({ page }) => {
    // Backend commits the doc asynchronously (~5s+); this verifies the page
    // polls until the new doc lands and the row resolves to "已处理".
    test.setTimeout(120000);

    const filename = `e2e-upload-${Date.now()}.md`;
    const content = `# E2E 测试文档\n\n王五是测试公司的创始人，用于验证上传后文档能自动显示在列表中。\n`;

    await page.goto(`${BASE}/documents`, { waitUntil: 'networkidle', timeout: 15000 });
    await expect(page.locator('body')).toContainText('documents total');

    // Open the upload dialog and drop a markdown file via the hidden input
    await page.getByRole('button', { name: 'Upload', exact: true }).click();
    await page.setInputFiles('input[type="file"]', {
      name: filename,
      mimeType: 'text/markdown',
      buffer: Buffer.from(content, 'utf-8'),
    });

    // Optimistic placeholder (🔄 处理中) should appear almost immediately
    const row = page.locator('table tbody tr', { hasText: filename });
    await expect(row).toBeVisible({ timeout: 15000 });

    // ...then resolve to ✅ 已处理 once the backend commits and polling catches it
    await expect(row).toContainText('已处理', { timeout: 90000 });

    console.log(`Verified document landed: ${filename}`);
    await page.screenshot({ path: 'test-results/documents-upload.png', fullPage: true });
  });

  test('Delete button removes the document from the table', async ({ page }) => {
    test.setTimeout(120000);

    const filename = `e2e-delete-${Date.now()}.md`;
    const content = `# E2E 删除测试\n\n用于验证删除按钮能移除文档。\n`;

    await page.goto(`${BASE}/documents`, { waitUntil: 'networkidle', timeout: 15000 });

    // Upload and wait until it resolves to completed
    await page.getByRole('button', { name: 'Upload', exact: true }).click();
    await page.setInputFiles('input[type="file"]', {
      name: filename,
      mimeType: 'text/markdown',
      buffer: Buffer.from(content, 'utf-8'),
    });
    const row = page.locator('table tbody tr', { hasText: filename });
    await expect(row).toBeVisible({ timeout: 15000 });
    await expect(row).toContainText('已处理', { timeout: 90000 });

    // Close the upload dialog so the table (and its delete button) is interactive
    await page.keyboard.press('Escape');
    await expect(page.locator('input[type="file"]')).toBeHidden({ timeout: 5000 });

    // Accept the window.confirm, then click that row's delete button
    page.on('dialog', (d) => d.accept());
    await row.getByRole('button', { name: `Delete ${filename}` }).click();

    // Row disappears optimistically
    await expect(row).toHaveCount(0, { timeout: 15000 });

    // ...and is actually gone from the backend (delete + cleanup is async)
    await page.waitForFunction(async (name) => {
      const res = await fetch('/api/documents', { cache: 'no-store' });
      const docs = await res.json();
      return !docs.some((d: { name: string }) => d.name === name);
    }, filename, { timeout: 20000 });

    console.log(`Verified document deleted: ${filename}`);
  });
});
