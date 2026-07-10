# Chat Drawer 规范

**状态:** 草案
**日期:** 2026-07-10

## 目标

1. 全局 Chat 抽屉，跨所有页面（Graph / Documents / Overview）持久存在，用户无需离开当前视图即可对知识图谱数据提问。
2. Chat 与图画布共享屏幕空间 — 抽屉挤压布局，而非叠加覆盖。
3. 核心用例是**"验证数据抽取完整性"** — 用户导入文档后，打开 Chat，对已抽取的实体和关系进行提问。
4. Chat 上下文通用化：`context_id` + `context_type` 作为主轴，支持 group、node、edge、document 以及未来的任意实体类型。
5. **仅做会话内问答，无后端持久化**：消息仅存在于浏览器内存（Zustand store），刷新后丢失。不实现服务端会话存储、历史记录、图谱变更审计。

## 非目标

- 服务端会话存储与历史记录（本期不做）
- 后端 chat 接口与数据库表（本期不做，由前端直接调用现有检索接口 + LLM）
- 写操作（创建/更新/删除实体）
- 画布节点高亮（从 Chat 消息中的实体引用触发）
- MCP 集成
- 移动端适配

## 架构概览

```
┌──────┬──────────────────────────────────────┬───────────┐
│      │  Header（路由标题 + badge）             │           │
│Side  │──────────────────────────────────────│   Chat    │
│bar   │                                       │  Drawer   │
│48px  │         页面内容                       │  400px    │
│      │   （Graph 画布 / Documents / 等）       │  (全局)   │
│      │                                       │           │
└──────┴──────────────────────────────────────┴───────────┘
                                              ↑
                                        ChatFloatingButton
                                        （固定右下角）
```

三层结构：

```
RootLayout (layout.tsx)
  ├── Sidebar（已有，48px）
  ├── MainArea（Header + children）
  ├── ChatFloatingButton（新增，始终可见）
  └── ChatDrawer（新增，从右侧滑入，挤压 MainArea）

ChatDrawer
  ├── Header（标题、上下文 badge、新对话按钮、关闭）
  ├── MessageList（聊天气泡、markdown、加载指示器）
  ├── InputArea（输入框 + 发送）
```

## 数据模型

### 前端（TypeScript）

```ts
// ─── 上下文（通用化）───
interface ChatContext {
  context_id?: string;       // group_id、node_id、edge_id、document_id 等
  context_type?: string;     // 'group' | 'node' | 'edge' | 'document'
  context_name?: string;     // 仅用于展示
  // 可扩展
}

// ─── UI 中的 Chat 消息 ───
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  entityRefs?: EntityRef[];
}

interface EntityRef {
  id: string;
  name: string;
  type: string;
}
```

### 问答请求（轻量代理）

前端通过 Next.js BFF 转发问答请求。BFF 层仅做一层薄代理，调用 Python 后端已有的检索能力 + LLM：

```ts
interface ChatRequest {
  message: string;
  context: ChatContext;
  history: ChatMessage[];     // 当前会话内的历史消息，用于多轮对话
}

interface ChatResponse {
  answer: string;
  entityRefs?: EntityRef[];
}
```

## BFF 端点

仅一个轻量端点，无会话、无历史存储：

| 方法 | 路径 | 描述 |
|------|------|-------------|
| `POST` | `/api/chat` | 发送消息 + 上下文 + 会话内历史，返回 answer。无状态。 |

### Next.js BFF（`web_service/app/api/chat/route.ts`）

```ts
// POST /api/chat
// 接收 { message, context, history }，转发至 Python 后端，返回 { answer, entityRefs }
```

转发至 Python 后端已有的检索接口，由后端组装 prompt 调用 LLM 后返回结果。BFF 不做任何存储。

### Python 后端

**本期不新增接口和数据库表**。复用现有检索能力（`Graphiti.search()`），BFF 调用后端现有/新增的轻量问答内部方法：
1. 接收 `{ message, context, history }`
2. 根据 `context` 过滤检索范围，调用 `Graphiti.search()` 获取相关实体/事实
3. 组装 prompt（系统消息 + 检索结果 + 历史消息 + 用户问题）
4. 调用 LLM 生成回答
5. 返回 `{ answer, entityRefs }`

## 组件设计

### ChatFloatingButton（`components/chat/chat-floating-button.tsx`）

```
┌───┐
│ 💬 │  ← 56x56 圆形，阴影，主色调
└───┘
```

- Props：无（从 `useChatStore` 读取）
- 固定定位：`bottom-6 right-6`，z-50
- 点击 → `chatStore.toggle()`

### ChatDrawer（`components/chat/chat-drawer.tsx`）

```
┌─────────────────────────────┐
│ Chat                  🔄  ✕ │  ← Header（h-14，border-b）
│ 当前上下文: grp_abc           │  ← 上下文 badge 行
├─────────────────────────────┤
│                             │
│  ┌──────────────────────┐   │  ← AI 消息（左对齐）
│  │ AI: 根据当前图谱...    │   │     markdown 渲染
│  └──────────────────────┘   │
│                             │
│        ┌──────────────────┐ │  ← 用户消息（右对齐）
│        │ 张三有哪些关系？   │ │
│        └──────────────────┘ │
│                             │
│  ⬤ ⬤ ⬤（输入中指示器）       │  ← 加载状态
│                             │
├─────────────────────────────┤
│ [输入框................]  ↑ │  ← 输入区域（border-t，p-3）
└─────────────────────────────┘
```

- 由 `useChatStore().isOpen` 控制
- 宽度：`w-[400px]`，通过已有的 `components/ui/sheet.tsx` 中的 `Sheet` 组件渲染
- 抽屉不叠加 — 它作为 flex 行中的兄弟节点存在，主区域自然收缩
- Header 操作：
  - 🔄 新对话 → `chatStore.clearMessages()`
  - ✕ 关闭 → `chatStore.close()`

**状态：**

| 状态 | 行为 |
|------|------|
| 空（无消息） | 占位提示："向知识图谱提问，验证数据抽取是否完整..." |
| 加载中 | 用户发送消息后显示输入中指示器圆点，输入框禁用 |
| 有消息 | 可滚动消息列表，新消息自动滚动到底部 |
| 错误 | 内联错误横幅"请求失败，请重试"，附带重试按钮 |

### ChatMessage（`components/chat/chat-message.tsx`）

- 用户消息：右对齐，主色背景，白色文字
- AI 消息：左对齐，次要/柔和背景，markdown 通过 `react-markdown` + `remark-gfm` 渲染
- 实体引用（`entityRefs`）渲染为小型内联 badge（暂不可交互）

### ChatInput（`components/chat/chat-input.tsx`）

- 输入框自动调整高度（最小 1 行，最大 4 行）
- Enter 发送，Shift+Enter 换行
- 发送按钮（内容为空或加载中时禁用）
- 占位提示："向知识图谱提问..."

## Store 设计

### `stores/chat-store.ts`（Zustand）

```ts
interface ChatState {
  // ─── UI 状态 ───
  isOpen: boolean;

  // ─── 当前对话 ───
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;

  // ─── 上下文 ───
  context: ChatContext;      // { context_id, context_type, context_name }

  // ─── 操作 ───
  toggle: () => void;
  open: (ctx?: ChatContext) => void;
  close: () => void;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  setContext: (ctx: Partial<ChatContext>) => void;
  retry: () => Promise<void>;
}
```

关键约束：
- 消息仅存储在 Zustand 内存中，浏览器刷新后全部丢失。
- `sendMessage()` 将当前 `context` 和已有 `messages` 一并发送给后端。
- `clearMessages()` 清空消息列表，开始新一轮对话。
- `retry()` 移除最后一条 assistant 消息后重发最后一条 user 消息。

## 文件清单

### 新增文件（6 个）

| 文件 | 用途 |
|------|------|
| `web_service/stores/chat-store.ts` | 全局 Chat 状态（Zustand） |
| `web_service/components/chat/chat-drawer.tsx` | 主 Chat 抽屉（Sheet 包装） |
| `web_service/components/chat/chat-floating-button.tsx` | FAB 切换按钮 |
| `web_service/components/chat/chat-message.tsx` | 单条消息气泡，支持 markdown |
| `web_service/components/chat/chat-input.tsx` | 输入框 + 发送按钮 |
| `web_service/app/api/chat/route.ts` | BFF：POST /api/chat 薄代理 |

### 修改文件（5 个）

| 文件 | 变更 |
|------|------|
| `web_service/app/layout.tsx` | 在 `<main>` 之外挂载 ChatDrawer + ChatFloatingButton |
| `web_service/app/graph/graph-client.tsx` | 同步 `ChatContext` → `chatStore.setContext()`，为节点/边接入"Ask AI" |
| `web_service/components/graph/node-detail-popover.tsx` | 添加"对此节点询问 AI"按钮 |
| `web_service/lib/types.ts` | 添加 Chat 类型（ChatContext、ChatMessage、EntityRef 等） |
| `server/graph_service/main.py` | 新增轻量内部问答方法（复用现有检索 + LLM，不含持久化） |

## 交互流程

### 流程一：基本问答

```
1. 用户在 Graph 页面，选择 group "grp_abc"
2. 点击 FAB → 抽屉打开，上下文 badge 显示"当前上下文: grp_abc"
3. 输入"图中张三有多少关系？" → 回车
4. 加载指示器出现，输入框禁用
5. AI 以 markdown 格式回复，列出关系
6. 用户追问："有没有遗漏的关系？"（历史消息随请求一并发送，实现多轮对话）
7. AI 回复缺口分析
8. 用户关闭抽屉 → 返回完整画布视图
```

### 流程二：图谱元素 → Chat

```
1. 用户点击画布上的节点 → popover 打开
2. 用户点击 popover 中的"对此节点询问 AI"按钮
3. Chat 抽屉打开，上下文设为 { context_id: node.id, context_type: 'node', context_name: node.name }
4. 输入框预填"分析一下 [节点名称] 这个实体"
5. 用户按 Enter 发送
```

边 popover 和文档列表行同理，context_type 分别设为 'edge' 或 'document'。

### 流程三：新对话

```
1. 用户已有多轮对话
2. 用户点击 Chat header 中的 🔄 按钮
3. 消息清空，开始新一轮对话（无持久化，旧消息不可恢复）
```

## 边界情况

| 情况 | 处理方式 |
|------|----------|
| 后端返回错误 | 显示内联错误横幅"请求失败，请重试"，附带重试按钮 |
| 用户发送空消息 | 发送按钮保持禁用，不发起请求 |
| AI 回复非常长 | 消息列表设置 `max-h` 约束，可滚动 |
| 发送时网络超时 | 30 秒后中止，显示错误，用户可重试 |
| 对话中途切换上下文 | 新消息使用当前上下文发送，历史消息保留原有上下文 |
| 浏览器刷新 | 所有内存状态丢失，Chat 全新开始 |
| 无选中上下文 | 上下文 badge 显示"当前上下文: 无"，Chat 正常工作 |

## 验证

### 手动测试清单

1. **FAB + 抽屉开关**：点击 FAB → 抽屉从右侧滑入，主区域宽度减小（检查 DOM，确认无叠加）。点击关闭 → 抽屉滑出，主区域恢复全宽。
2. **跨页面持久**：在 Graph 页面打开 Chat → 导航到 Documents → Chat 保持打开且消息不变。导航到 Overview → 同样。
3. **上下文同步**：在 Graph 页面切换 group 下拉 → Chat header 中上下文 badge 更新。点击节点 → "Ask AI"将 context_type 设为 'node' 并传入节点 id。
4. **基本问答**：输入问题 → 回车发送 → 加载指示器出现 → AI 回复正确渲染（含 markdown）。
5. **多轮对话**：连续追问 → 验证 AI 能结合上下文回答（历史消息正确传递）。
6. **新对话**：对话数轮 → 点击 🔄 → 消息清空。
7. **错误处理**：停止 Python 后端 → 发送消息 → 验证错误横幅出现。重启后端 → 点击重试 → 验证正常。
8. **从节点 popover 询问 AI**：点击画布节点 → popover 出现 → 点击"Ask AI" → Chat 打开，上下文正确。

---

## 搜索优化规范

**状态:** 规划中
**日期:** 2026-07-10

### 现状问题

Chat 搜索使用 `EDGE_HYBRID_SEARCH_RRF` 配置，组合了两种搜索方式：

| 搜索方式 | 实现 | 问题 |
|----------|------|------|
| **BM25 (fulltext)** | `websearch_to_tsquery('simple', query)` | `simple` 配置不做中文分词，中文句子变成单个 token，匹配不上 |
| **cosine_similarity** | MiniLM embedding 向量余弦 | MiniLM 对中文语义匹配弱，中英混合 query 与纯英文存储文本距离远 |

**典型失败 case**：用户用中文问 "有Sigma.js实体吗？它和Next.js是什么关系？" → embedding 距离远搜不到 → fulltext 又因中文不分词搜不到 → 返回空结果。

当前临时方案：Chat router 里做了英文关键词 fallback（从 query 中提取 `[A-Za-z][\w.\-]+` 模式的词重新搜索），但不够优雅。

### 优化方案

#### 方案 A：BGE-large-zh + COMBINED 搜索（推荐，中等改动）

**嵌入模型替换**：MiniLM (384d, 英文为主) → BGE-large-zh (1024d, 中文为主)

- BGE-large-zh 对中文语义理解远强于 MiniLM，中英混合 query 也能较好匹配
- 需要重建 minilm Docker 镜像（预下载 BGE-large-zh 模型）
- 需要清库重建向量索引（维度从 384 变为 1024）
- `.env` 更新：`EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5`, `EMBEDDER_PROVIDER=openai`, `POSTGRES_AGE_EMBEDDING_DIMENSION=1024`

**Chat 搜索配置升级**：`EDGE_HYBRID_SEARCH_RRF` → `COMBINED_HYBRID_SEARCH_RRF`

- 当前只搜 edge（事实关系），改为同时搜 edge + node + episode + community
- 搜索范围更广，即使 edge 没命中，node 名字可能命中
- 改动只在 `server/graph_service/routers/chat.py` 的 `graphiti.search()` 调用改为 `graphiti._search()` 并传入 COMBINED 配置

**优点**：
- 中文语义匹配大幅提升
- 搜索覆盖面更广
- 不需要修改 PostgreSQL 扩展

**缺点**：
- 需要重建数据和索引
- BGE-large-zh 模型更大（~1.3GB），启动慢
- 1024 维向量存储空间翻倍

#### 方案 B：BGE-large-zh + jieba/zhparser 中文分词（彻底，大改动）

在方案 A 基础上，进一步解决 PostgreSQL fulltext search 的中文分词问题。

**选项 B1：zhparser 扩展**

- PostgreSQL 扩展，基于 Simple Chinese Word Segmentation (scws)
- 安装：`CREATE EXTENSION zhparser;`
- 配置：`CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser); ALTER TEXT SEARCH CONFIGURATION chinese ADD MAPPING FOR n,v,a,i,e,l WITH simple;`
- 需修改所有 `websearch_to_tsquery('simple', ...)` → `websearch_to_tsquery('chinese', ...)`
- 需重建所有 tsvector 索引和列

**选项 B2：应用层 jieba 分词**

- 不改 PostgreSQL 配置，在 Python 写入时用 jieba 分词，空格连接后存入 tsvector
- 搜索时也用 jieba 分词，空格连接后传入 `websearch_to_tsquery('simple', ...)`
- 改动集中在 `graphiti_core/driver/postgres_age/` 的写入和搜索代码
- 无需安装 PG 扩展，更易部署

**优点**：
- 中文 fulltext search 完全生效
- BM25 和 semantic 双通道都能命中中文 query
- 最彻底的解决方案

**缺点**：
- 改动大（涉及 core 搜索层）
- 方案 B1 需要自定义 PG 镜像安装 zhparser
- 方案 B2 需要在嵌入层加 jieba 依赖
- 需要重建全库索引

#### 方案 C：仅改 Chat 搜索配置（最小改动）

不换嵌入模型，只改 Chat 的搜索策略：

- 用 `COMBINED_HYBRID_SEARCH_RRF`（搜 edge+node+episode+community）
- 保留英文关键词 fallback
- 降低 cosine similarity 的 `min_score` 阈值

**优点**：无需重建索引，改动最小

**缺点**：中文语义匹配弱的根本问题未解决，改善有限

### 推荐路线

```
Phase 1 (当前)     → 方案 C：Chat 搜索配置优化 + 关键词 fallback
Phase 2 (短期)     → 方案 A：BGE-large-zh + COMBINED 搜索
Phase 3 (中期)     → 方案 B2：应用层 jieba 分词
```

Phase 1 已完成。Phase 2 和 Phase 3 按需推进，每次升级需清库重建索引。