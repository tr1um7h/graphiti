import { test, expect } from '@playwright/test';

const BASE = 'http://localhost:3000';

test('Chat returns real LLM-powered answers from the knowledge graph', async ({ request, page }) => {
  // Test the API directly
  const res = await request.post(`${BASE}/api/explore/chat`, {
    data: {
      message: 'cc能吃辣椒吗',
      centerEntityId: '',
      visibleNodeIds: [],
    },
  });
  expect(res.ok()).toBeTruthy();
  const data = await res.json();
  expect(data.answer).toBeTruthy();
  expect(data.answer.length).toBeGreaterThan(10);
  // Should NOT contain the old mock text
  expect(data.answer).not.toContain('模拟回复');
  expect(data.answer).not.toContain('模拟');
  // Should contain actual graph content
  expect(data.answer).toContain('cc');
  console.log(`Chat answer: ${data.answer.substring(0, 100)}...`);
  console.log(`Highlight nodes: ${data.highlightNodes?.length ?? 0}`);
});

test('Chat with entity-specific question returns relevant nodes', async ({ request }) => {
  const res = await request.post(`${BASE}/api/explore/chat`, {
    data: {
      message: '星辰科技有哪些人？',
      centerEntityId: '',
      visibleNodeIds: [],
    },
  });
  expect(res.ok()).toBeTruthy();
  const data = await res.json();
  expect(data.answer).toContain('星辰科技');
  expect(data.highlightNodes).toBeDefined();
  expect(data.highlightNodes.length).toBeGreaterThan(0);
  console.log(`Entity question answer: ${data.answer.substring(0, 100)}...`);
});
