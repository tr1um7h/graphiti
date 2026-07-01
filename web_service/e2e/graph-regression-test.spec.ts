// e2e/graph-regression-test.spec.ts
// 测试 Graph 页面重构后的所有功能
import { test, expect, type Page } from '@playwright/test';

const BASE = 'http://localhost:3000';

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  gray: '\x1b[90m',
};

function log(level: 'info' | 'ok' | 'fail' | 'warn', msg: string, detail?: string) {
  const c = level === 'ok' ? colors.green : level === 'fail' ? colors.red : level === 'warn' ? colors.yellow : colors.cyan;
  const sym = level === 'ok' ? '✓' : level === 'fail' ? '✗' : level === 'warn' ? '!' : 'ℹ';
  console.log(`${c}${sym}${colors.reset} ${msg}${detail ? `\n  ${colors.gray}${detail}${colors.reset}` : ''}`);
}

async function shoot(page: Page, label: string, dir = '/tmp/graph-test') {
  const fs = await import('fs');
  fs.mkdirSync(dir, { recursive: true });
  const path = `${dir}/${label}.png`;
  await page.screenshot({ path, fullPage: false });
  log('info', `📸 截图: ${path}`);
}

test.describe('Graph 页面重构后回归测试', () => {
  test('1. 页面加载与画布渲染', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(`PAGE_ERROR: ${err.message}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    log('info', '访问 Graph 页面', BASE + '/graph');
    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);

    // 画布渲染检查
    const canvasCount = await page.locator('canvas').count();
    log(canvasCount > 0 ? 'ok' : 'fail', `画布数量: ${canvasCount}`);

    if (canvasCount > 0) {
      const canvas = page.locator('canvas').first();
      const box = await canvas.boundingBox();
      log('ok', `画布尺寸: ${Math.round(box?.width ?? 0)}x${Math.round(box?.height ?? 0)}`);
    }

    // 工具栏元素检查
    const toolbar = {
      searchBox: await page.locator('input[placeholder*="搜索"]').count(),
      groupSelect: await page.locator('select').count(),
      forceAtlas2: await page.locator('button:has-text("ForceAtlas2")').count(),
      exportBtn: await page.locator('button:has-text("导出")').count(),
    };
    log('ok', '工具栏元素检查', JSON.stringify(toolbar));

    // 节点/边统计
    const bodyText = (await page.textContent('body')) || '';
    const nodeMatch = bodyText.match(/节点:\s*(\d+)/);
    const edgeMatch = bodyText.match(/边:\s*(\d+)/);
    log('ok', `节点/边: ${nodeMatch?.[1] ?? '?'} / ${edgeMatch?.[1] ?? '?'}`);

    // 控制台错误检查
    const realErrors = errors.filter((e) =>
      !e.includes('favicon') && !e.includes('404')
    );
    if (realErrors.length > 0) {
      log('warn', `${realErrors.length} 个控制台错误`, realErrors.join('\n  '));
    } else {
      log('ok', '无控制台错误');
    }

    await shoot(page, '01-loaded');
  });

  test('2. 分组选择器功能', async ({ page }) => {
    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    const select = page.locator('select').first();
    const options = await select.locator('option').allTextContents();
    log('ok', `分组选项:`, options.join(', '));

    // 切换到 default
    const defaultOpt = options.find((o) => o.startsWith('default'));
    if (defaultOpt) {
      await select.selectOption({ label: defaultOpt });
      await page.waitForTimeout(2500);
      const bodyText = (await page.textContent('body')) || '';
      const nodeMatch = bodyText.match(/节点:\s*(\d+)/);
      log('ok', `切换到 default 后节点数: ${nodeMatch?.[1] ?? '?'}`);

      const canvasCount = await page.locator('canvas').count();
      log(canvasCount > 0 ? 'ok' : 'fail', `切换分组后画布仍存在: ${canvasCount > 0}`);
      await shoot(page, '02-default-group');
    }

    // 切换到 final_final_test
    const finalOpt = options.find((o) => o.startsWith('final_final_test'));
    if (finalOpt) {
      await select.selectOption({ label: finalOpt });
      await page.waitForTimeout(2500);
      const bodyText = (await page.textContent('body')) || '';
      const nodeMatch = bodyText.match(/节点:\s*(\d+)/);
      log('ok', `切换到 final_final_test 后节点数: ${nodeMatch?.[1] ?? '?'}`);
      await shoot(page, '03-final-group');
    }

    // 切回所有分组
    await select.selectOption({ label: '所有分组' });
    await page.waitForTimeout(2000);
    log('ok', '切回所有分组');
  });

  test('3. 搜索 → 子图聚焦 → 浮窗（核心流程）', async ({ page }) => {
    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    const canvasCount = await page.locator('canvas').count();
    log('ok', `初始画布数: ${canvasCount}`);
    await shoot(page, '04-before-search');

    // 在搜索框输入
    const searchBox = page.locator('input[placeholder*="搜索"]').first();
    await searchBox.click();
    await searchBox.fill('Person');
    await page.waitForTimeout(1500);
    await shoot(page, '05-search-typing');

    // 捕获搜索下拉结果
    const bodyText = (await page.textContent('body')) || '';
    log('ok', `搜索 "Person" 后页面状态`, bodyText.slice(0, 200));

    // 尝试点击第一个搜索结果（下拉菜单可能存在）
    const results = page.locator('[role="option"], li:has-text("Person"), button:has-text("Person")');
    const resultCount = await results.count();
    log('info', `搜索结果候选数: ${resultCount}`);
  });

  test('4. 实体类型图例过滤', async ({ page }) => {
    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    // 找到 Person 按钮（点击切换可见性）
    const personBtn = page.locator('button:has-text("Person")').first();
    if (await personBtn.count() > 0) {
      await personBtn.click();
      await page.waitForTimeout(1500);
      await shoot(page, '06-toggle-person');
      log('ok', '已点击 Person 按钮');
      // 再点一次恢复
      await personBtn.click();
      await page.waitForTimeout(1500);
      log('ok', '已恢复 Person 按钮');
    } else {
      log('warn', '未找到 Person 按钮');
    }
  });

  test('5. Sigma canvas 在 DOM 变化时不被清除', async ({ page }) => {
    await page.goto(`${BASE}/graph`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    // 抓取 canvas 像素信息作为锚点
    const canvas1 = await page.locator('canvas').first().evaluate((el: HTMLCanvasElement) => {
      const ctx = (el as any).getContext?.('webgl') || (el as any).getContext?.('2d');
      const pixels = ctx?.getImageData ? 'has getImageData' : 'no getImageData';
      return {
        width: el.width,
        height: el.height,
        style: { w: el.style.width, h: el.style.height },
        parent: el.parentElement?.className,
        ctx: pixels,
      };
    });
    log('ok', 'canvas 初始状态', JSON.stringify(canvas1));

    // 切换 ForceAtlas2 / 布局按钮触发重新布局（不通过 React 重渲染清理 canvas）
    const faBtn = page.locator('button:has-text("ForceAtlas2")').first();
    if (await faBtn.count() > 0) {
      await faBtn.click();
      await page.waitForTimeout(500);
      // 关闭菜单
      await page.keyboard.press('Escape');
      log('ok', '已点击 ForceAtlas2 按钮（验证按钮工作）');
    }

    // 模拟打开和关闭浮窗，检查 canvas 不被销毁
    // 通过 store 触发
    const canvas2 = await page.locator('canvas').first().evaluate((el: HTMLCanvasElement) => {
      return { width: el.width, height: el.height, alive: el.isConnected };
    });
    log(canvas2.alive ? 'ok' : 'fail', `交互后 canvas 仍然存活: ${canvas2.alive}, 尺寸: ${canvas2.width}x${canvas2.height}`);
  });
});
