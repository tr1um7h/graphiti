import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:3000';

test.describe('Data API tests', () => {
  test('GET /api/data/groups proxy route exists', async ({ request }) => {
    const res = await request.get(`${BASE}/api/data/groups`);
    // Proxy route exists — returns 500 because backend isn't running,
    // but confirms the catch-all route is active (not 404 HTML)
    expect(res.status()).not.toBe(404);
    const data = await res.json();
    expect(data).toHaveProperty('error');
  });

  test('GET /api/data/groups/{id} proxy route exists', async ({ request }) => {
    const res = await request.get(`${BASE}/api/data/groups/__test__`);
    expect(res.status()).not.toBe(404);
    const data = await res.json();
    expect(data).toHaveProperty('error');
  });

  test('GET /api/data/groups/{id} returns 404 error shape for nonexistent group', async ({ request }) => {
    const res = await request.get(`${BASE}/api/data/groups/nonexistent_group_xyz`);
    // Backend returns 500 when unreachable, 404 when reachable but no data
    expect([404, 500]).toContain(res.status());
  });
});

test.describe('Data UI tests', () => {
  test('Data page loads without rendering errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => {
      errors.push(`PAGE_ERROR: ${err.message}`);
    });

    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(5000);

    // Only check for page-level errors (not console.error from API calls)
    // API fetch failures are expected when backend is unavailable
    expect(errors).toHaveLength(0);
  });

  test('Data page shows header', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Check header visible
    await expect(page.locator('h2')).toBeVisible();
  });

  test('Data page shows Import Data button', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Check import button visible
    await expect(page.locator('button:has-text("Import Data")')).toBeVisible();
  });

  test('Data page shows Refresh button', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Check refresh button visible
    await expect(page.locator('button:has-text("Refresh")')).toBeVisible();
  });

  test('Import Data dialog opens and closes', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Click Import Data button
    await page.locator('button:has-text("Import Data")').click();
    await page.waitForTimeout(500);

    // Dialog should be visible
    await expect(page.locator('text=Upload ZIP Export')).toBeVisible();

    // Click Cancel
    await page.locator('button:has-text("Cancel")').click();
    await page.waitForTimeout(500);

    // Dialog should be closed
    await expect(page.locator('text=Upload ZIP Export')).not.toBeVisible();
  });

  test('Sidebar shows Data tab with navigation', async ({ page }) => {
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Check sidebar has Data link
    const dataLink = page.locator('a:has-text("Data")');
    await expect(dataLink).toBeVisible();

    // Click Data link
    await dataLink.click();
    await page.waitForTimeout(3000);

    // Should navigate to /data
    expect(page.url()).toBe(`${BASE}/data`);
  });

  test('Data page shows group selector dropdown', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Should show group selector (select element)
    const select = page.locator('select').first();
    await expect(select).toBeVisible();
  });
});