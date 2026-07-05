import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:3000';

test.describe('Data API tests', () => {
  test('GET /api/data/groups returns array', async ({ request }) => {
    const res = await request.get(`${BASE}/api/data/groups`);
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('GET /api/data/groups/{id} returns group detail', async ({ request }) => {
    // First get groups to find a valid group_id
    const groupsRes = await request.get(`${BASE}/api/data/groups`);
    const groups = await groupsRes.json();

    if (groups.length > 0) {
      const groupId = groups[0].group_id;
      const res = await request.get(`/api/data/groups/${groupId}`);
      expect(res.ok()).toBeTruthy();
      const data = await res.json();
      expect(data.group_id).toBe(groupId);
      expect(data.table_counts).toBeTruthy();
    }
  });

  test('GET /api/data/groups/{id} returns 404 for nonexistent group', async ({ request }) => {
    const res = await request.get(`${BASE}/api/data/groups/nonexistent_group_xyz`);
    expect(res.status()).toBe(404);
  });

  test('POST /api/data/patch/preview validates patch structure', async ({ request }) => {
    // Test with invalid patch (missing version)
    const invalidPatch = {
      metadata: { from_group_id: 'a' },
      changes: {},
    };

    const formData = new FormData();
    formData.append('file', new Blob([JSON.stringify(invalidPatch)], { type: 'application/json' }));

    const res = await request.post(`${BASE}/api/data/patch/preview`, {
      multipart: { file: JSON.stringify(invalidPatch) },
    });

    // Should fail validation
    expect(res.status()).toBe(400);
  });

  test('GET /api/data/diff requires both groups', async ({ request }) => {
    const res = await request.get(`${BASE}/api/data/diff?left=group_a`);
    // Should fail because right is missing or group doesn't exist
    expect(res.status()).toBeGreaterThanOrEqual(400);
  });
});

test.describe('Data UI tests', () => {
  test('Data page loads without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    page.on('pageerror', (err) => {
      errors.push(`PAGE_ERROR: ${err.message}`);
    });

    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Page should load without console errors
    const realErrors = errors.filter(
      (e) =>
        !e.includes('favicon') &&
        !e.includes('404') &&
        !e.includes('Failed to load resource')
    );

    if (realErrors.length > 0) {
      console.log('DATA PAGE ERRORS:', realErrors);
    }
    expect(realErrors).toHaveLength(0);
  });

  test('Data page shows header and import button', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Check header
    await expect(page.locator('h2:has-text("Data Management")')).toBeVisible();

    // Check import button
    await expect(page.locator('button:has-text("Import Data")')).toBeVisible();
  });

  test('Data page shows groups table', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Should show groups table or empty state
    const hasTable = await page.locator('table').isVisible();
    const hasEmptyState = await page.locator('text=No groups found').isVisible();

    expect(hasTable || hasEmptyState).toBeTruthy();
  });

  test('Data page shows group selector after selecting a group', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Check if there are any groups
    const firstRow = page.locator('tbody tr').first();
    const hasRows = await firstRow.isVisible();

    if (hasRows) {
      // Click on first group
      await firstRow.click();
      await page.waitForTimeout(500);

      // Should show group selector for diff
      await expect(page.locator('select').nth(1)).toBeVisible();
    }
  });

  test('Import Data dialog opens and closes', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

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

  test('Sidebar shows Data tab', async ({ page }) => {
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    // Check sidebar has Data link
    const dataLink = page.locator('a:has-text("Data")');
    await expect(dataLink).toBeVisible();

    // Click Data link
    await dataLink.click();
    await page.waitForTimeout(2000);

    // Should navigate to /data
    expect(page.url()).toBe(`${BASE}/data`);
  });

  test('Group detail view shows export button', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Check if there are any groups
    const firstRow = page.locator('tbody tr').first();
    const hasRows = await firstRow.isVisible();

    if (hasRows) {
      // Click on first group to select it
      await firstRow.click();
      await page.waitForTimeout(1000);

      // Should show Export button
      await expect(page.locator('button:has-text("Export Data")')).toBeVisible();
    }
  });

  test('Diff view shows when two groups selected', async ({ page }) => {
    await page.goto(`${BASE}/data`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    // Check if there are at least 2 groups
    const rowCount = await page.locator('tbody tr').count();

    if (rowCount >= 2) {
      // Click on first group
      await page.locator('tbody tr').nth(0).click();
      await page.waitForTimeout(500);

      // Select second group from dropdown
      const secondSelect = page.locator('select').nth(1);
      const options = await secondSelect.locator('option').all();
      if (options.length > 1) {
        // Select the first non-empty option
        await secondSelect.selectOption({ index: 1 });
        await page.waitForTimeout(2000);

        // Should show diff view
        await expect(page.locator('text=Diff:')).toBeVisible();
      }
    }
  });
});
