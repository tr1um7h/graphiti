import { chromium } from 'playwright';

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  
  await page.goto('http://localhost:3000/graph', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/tmp/graph-view.png', fullPage: false });
  
  const memoryBtn = page.getByRole('button', { name: 'Memory' });
  await memoryBtn.click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: '/tmp/memory-view.png', fullPage: false });
  
  console.log('Console errors:', errors);
  await browser.close();
}

main().catch(console.error);
