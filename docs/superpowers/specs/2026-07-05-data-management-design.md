# Data Tab 数据管理功能设计文档

## 1. 概述

在 Web UI 中新增 "Data" Tab，提供完整的数据管理功能：
- **导出数据**：导出指定 group_id 的完整 JSONL 数据包
- **导入数据**：导入 JSONL 数据包，创建新的 group_id
- **生成 Diff**：比较两个 group_id 的数据差异
- **导入 Patch**：导入 diff 生成的 patch 文件
- **应用 Patch**：将 patch 应用到目标 group_id（支持策略选择和预览确认）

---

## 2. 用户界面设计

### 2.1 Tab 结构

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Data Management                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [源 group_id ▼ (可选)]  [目标 group_id ▼ (可选)]    [刷新]             │
│                                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  [状态区域 - 根据选择动态变化]                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 三种状态

#### 状态 1：未选择 group_id

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Groups Overview                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  group_A          │ 1,234 nodes │ 5,678 edges │ 2024-01-15      │  │
│  │  group_B          │   567 nodes │ 1,234 edges │ 2024-01-14      │  │
│  │  default          │    89 nodes │   123 edges │ 2024-01-10      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  [导入 Data]                                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**操作**：
- 点击 group 行 → 选中该 group，进入状态 2
- 点击 [导入 Data] → 弹出导入对话框

#### 状态 2：选择了一个 group_id

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Group: group_A                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─ Data Summary ────────────────────────────────────────────────────┐  │
│  │  Table              │ Records  │ Size     │ Actions              │  │
│  │  ─────────────────────────────────────────────────────────────    │  │
│  │  entity_nodes       │    1,234 │ 2.3 MB   │ [展开 ▼]             │  │
│  │  episodic_nodes     │      567 │ 1.1 MB   │ [展开 ▼]             │  │
│  │  community_nodes    │       23 │  45 KB   │ [展开 ▼]             │  │
│  │  saga_nodes         │       12 │  23 KB   │ [展开 ▼]             │  │
│  │  entity_edges       │    5,678 │ 4.5 MB   │ [展开 ▼]             │  │
│  │  episodic_edges     │    1,234 │ 1.0 MB   │ [展开 ▼]             │  │
│  │  community_edges    │       45 │  34 KB   │ [展开 ▼]             │  │
│  │  has_episode_edges  │      123 │  89 KB   │ [展开 ▼]             │  │
│  │  next_episode_edges │      234 │ 178 KB   │ [展开 ▼]             │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  [导出 Data]  [导入 Patch]                                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**操作**：
- 点击 [展开 ▼] → 展开该表的 JSONL 数据（分页展示，语法高亮）
- 点击 [导出 Data] → 下载 JSONL 导出包（zip）
- 点击 [导入 Patch] → 弹出 patch 导入对话框

#### 状态 3：选择了两个 group_id（Diff 模式）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Diff: group_A ↔ group_B                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─ Diff Summary ────────────────────────────────────────────────────┐  │
│  │  Table              │ Added │ Removed │ Modified │ Conflicts     │  │
│  │  ─────────────────────────────────────────────────────────────    │  │
│  │  entity_nodes       │    12 │       3 │        5 │           0   │  │
│  │  episodic_nodes     │     5 │       0 │        2 │           0   │  │
│  │  entity_edges       │    23 │       7 │        0 │           0   │  │
│  │  ...                │   ... │     ... │      ... │         ...   │  │
│  │  ─────────────────────────────────────────────────────────────    │  │
│  │  Total              │    45 │      12 │        9 │           0   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  [导出 Diff]                                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**操作**：
- 点击 [导出 Diff] → 下载 patch.json 文件

---

### 2.3 对话框设计

#### 导入 Data 对话框

```
┌─────────────────────────────────────────────────────────────────────────┐
│  导入 Data                                                       [×]   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  上传 JSONL 导出包 (zip):                                               │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  [选择文件]  或拖拽文件到此处                                       │  │
│  │                                                                   │  │
│  │  📦 data_export_20240115.zip                                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  新 Group ID:                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  my_new_group                                                     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ☐ 覆盖已存在的 group (如果 Group ID 已存在)                             │
│                                                                         │
│  文件内容预览:                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Metadata 摘要:                                                    │  │
│  │    group_id:     old_group                                        │  │
│  │    exported_at:  2024-01-15T10:30:00Z                             │  │
│  │    total:        9 tables                                         │  │
│  │                                                                   │  │
│  │  ─────────────────────────────────────────────────────────────    │  │
│  │                                                                   │  │
│  │  表数据 (默认折叠，点击展开):                                       │  │
│  │    entity_nodes ........... 1,234 records  [展开 ▲]               │  │
│  │      显示前 50 条 (分页) ...                                      │  │
│  │    episodic_nodes .........   567 records  [展开 ▼]               │  │
│  │    community_nodes ........    23 records  [展开 ▼]               │  │
│  │    saga_nodes .............    12 records  [展开 ▼]               │  │
│  │    entity_edges ........... 5,678 records  [展开 ▼]               │  │
│  │    ...                                                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│                                          [取消]  [确认导入]             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 导入 Patch 对话框

```
┌─────────────────────────────────────────────────────────────────────────┐
│  导入 Patch                                                      [×]   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  上传 Patch 文件:                                                       │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  [选择文件]  或拖拽文件到此处                                       │  │
│  │                                                                   │  │
│  │  📄 patch.json                                                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  Patch 预览:                                                            │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Metadata:                                                        │  │
│  │    From: group_A                                                  │  │
│  │    To:   group_B                                                  │  │
│  │    Created: 2024-01-15T10:30:00Z                                  │  │
│  │                                                                   │  │
│  │  Changes:                                                         │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │ entity_nodes                                                │  │  │
│  │  │   [+] Added:   12 records                                  │  │  │
│  │  │   [-] Removed:  3 records                                  │  │  │
│  │  │   [~] Modified: 5 records                                  │  │  │
│  │  │   [!] Conflicts: 0                                         │  │  │
│  │  ├─────────────────────────────────────────────────────────────┤  │  │
│  │  │ entity_edges                                                │  │  │
│  │  │   [+] Added:   23 records                                  │  │  │
│  │  │   [-] Removed:  7 records                                  │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  │                                                                   │  │
│  │  [展开详情 ▼]                                                     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  源 Group ID (from):                                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  group_A  (默认取 patch.metadata.from_group_id，可手动修改)         │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  应用到 Group (to):                                                      │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  group_B  ▼                                                       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  冲突策略:                                                              │
│  ( ) Ours    - 保留目标 group 的数据，跳过冲突                           │
│  ( ) Theirs  - 使用 patch 中的数据，覆盖冲突                             │
│  (•) Skip    - 跳过整个有冲突的表                                        │
│                                                                         │
│  ☐ Dry Run (仅预览，不实际执行)                                          │
│                                                                         │
│                                          [取消]  [确认应用]             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Dry Run 结果对话框

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Dry Run 结果                                                    [×]   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  模拟执行结果:                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Added:      45 records                                          │  │
│  │  Removed:    12 records                                          │  │
│  │  Modified:    9 records                                          │  │
│  │  Conflicts:   2 records                                          │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ⚠️ 检测到 2 个冲突，策略 "skip" 将跳过这些表。                          │
│                                                                         │
│  是否继续实际执行？                                                      │
│                                                                         │
│                                          [取消]  [确认执行]             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 后端 API 设计

### 3.1 新增 Router

新增 `server/graph_service/routers/data.py`，注册到 `main.py`：

```python
app.include_router(data.router, prefix='/rest')
```

**注意**：使用 `/rest/data` 前缀，与现有 `/rest/graph` 区分，避免命名冲突。

### 3.2 API 端点

#### 3.2.1 获取 Groups 统计

```
GET /rest/data/groups

Response:
[
  {
    "group_id": "group_A",
    "created_at": "2024-01-15T10:30:00Z",
    "node_count": 1234,
    "edge_count": 5678,
    "table_counts": {
      "entity_nodes": 1234,
      "episodic_nodes": 567,
      ...
    }
  },
  ...
]
```

#### 3.2.2 获取 Group 数据详情

```
GET /rest/data/groups/{group_id}?table={table_name}&page={page}&size={size}

Response:
{
  "group_id": "group_A",
  "table": "entity_nodes",
  "page": 1,
  "size": 100,
  "total": 1234,
  "records": [
    {"uuid": "...", "name": "Alice", "labels": ["Person"], ...},
    ...
  ]
}
```

#### 3.2.3 导出 Group 数据

```
GET /rest/data/groups/{group_id}/export

Response: application/zip
Content-Disposition: attachment; filename="{group_id}_export_{timestamp}.zip"

ZIP 内容:
├── metadata.json
├── entity_nodes.jsonl
├── episodic_nodes.jsonl
├── community_nodes.jsonl
├── saga_nodes.jsonl
├── entity_edges.jsonl
├── episodic_edges.jsonl
├── community_edges.jsonl
├── has_episode_edges.jsonl
└── next_episode_edges.jsonl
```

#### 3.2.4 导入 Group 数据

```
POST /rest/data/import
Content-Type: multipart/form-data

Form Data:
- file: <zip file>
- new_group_id: "my_new_group"
- overwrite: false

Response:
{
  "success": true,
  "group_id": "my_new_group",
  "message": "Imported successfully",
  "table_counts": {
    "entity_nodes": 1234,
    ...
  }
}
```

#### 3.2.5 获取 Diff

```
GET /rest/data/diff?left=group_A&right=group_B

Response:
{
  "version": 1,
  "metadata": {
    "from_group_id": "group_A",
    "to_group_id": "group_B",
    "created_at": "2024-01-15T10:30:00Z"
  },
  "changes": {
    "entity_nodes": {
      "added": [...],
      "removed": [...],
      "modified": [...],
      "conflicts": []
    },
    ...
  }
}
```

#### 3.2.6 导出 Diff

```
GET /rest/data/diff/export?left=group_A&right=group_B

Response: application/json
Content-Disposition: attachment; filename="diff_group_A_vs_group_B_{timestamp}.json"
```

#### 3.2.7 预览 Patch

```
POST /rest/data/patch/preview
Content-Type: multipart/form-data

Form Data:
- file: <patch.json file>

Response:
{
  "version": 1,
  "metadata": {
    "from_group_id": "group_A",
    "to_group_id": "group_B",
    "created_at": "2024-01-15T10:30:00Z"
  },
  "summary": {
    "entity_nodes": {
      "added": 12,
      "removed": 3,
      "modified": 5,
      "conflicts": 0
    },
    ...
  },
  "patch": { ... full patch content ... }
}
```

#### 3.2.8 应用 Patch

```
POST /rest/data/patch/apply
Content-Type: application/json

Request:
{
  "patch": { ... patch content ... },
  "from_group_id": "group_A",  // 默认取 patch.metadata.from_group_id，允许用户修改
  "to_group_id": "group_B",
  "strategy": "ours",  // "ours" | "theirs" | "skip-conflicts"
  "dry_run": false
}

Response:
{
  "success": true,
  "dry_run": false,
  "added": 45,
  "removed": 12,
  "modified": 9,
  "conflicts": 2
}
```

**注意**: `from_group_id` 后端默认取 patch 中的值，前端允许用户在对话框中覆盖。

---

## 4. 前端实现

### 4.1 文件结构

```
web_service/
├── app/
│   └── data/
│       ├── page.tsx          # Data Tab 入口
│       └── data-client.tsx   # 客户端组件
├── components/
│   └── data/
│       ├── groups-table.tsx      # Groups 列表表格
│       ├── group-detail.tsx      # Group 详情展示
│       ├── diff-view.tsx         # Diff 展示
│       ├── import-data-dialog.tsx
│       ├── import-patch-dialog.tsx
│       └── dry-run-dialog.tsx
├── hooks/
│   └── use-data-api.ts       # Data API hooks
└── lib/
    └── data-types.ts         # Data types
```

### 4.2 核心组件

#### data-client.tsx

```typescript
export default function DataPageClient() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedGroup1, setSelectedGroup1] = useState<string | null>(null);
  const [selectedGroup2, setSelectedGroup2] = useState<string | null>(null);
  const [mode, setMode] = useState<'list' | 'single' | 'diff'>('list');
  
  // 根据选择状态切换模式
  useEffect(() => {
    if (!selectedGroup1) setMode('list');
    else if (!selectedGroup2) setMode('single');
    else setMode('diff');
  }, [selectedGroup1, selectedGroup2]);

  return (
    <div>
      {/* Group 选择器 */}
      <GroupSelector
        groups={groups}
        selected1={selectedGroup1}
        selected2={selectedGroup2}
        onSelect1={setSelectedGroup1}
        onSelect2={setSelectedGroup2}
      />
      
      {/* 根据模式渲染不同内容 */}
      {mode === 'list' && <GroupsTable groups={groups} />}
      {mode === 'single' && <GroupDetail groupId={selectedGroup1!} />}
      {mode === 'diff' && <DiffView left={selectedGroup1!} right={selectedGroup2!} />}
    </div>
  );
}
```

---

## 5. 实现复用 CLI 模块

### 5.1 后端复用

后端 API 实现应复用 `cli/` 目录下的核心逻辑：

```python
# 导出
from cli.export import export_group_with_sorting

# 导入
from cli.import_ import import_group

# Diff
from cli.diff import diff_groups

# Apply
from cli.apply import apply_patch
```

### 5.2 临时文件处理

- 导出时：在服务器 `/tmp` 创建临时目录，生成 JSONL 文件，打包为 zip 后返回，然后清理
- 导入时：接收上传的 zip 文件，解压到临时目录，处理后清理

---

## 6. 测试策略

### 6.1 后端测试

新增 `tests/server/test_data_api.py`：

```python
class TestExportAPI:
    async def test_export_group_returns_zip()
    async def test_export_nonexistent_group_returns_404()

class TestImportAPI:
    async def test_import_valid_zip_creates_group()
    async def test_import_with_overwrite_replaces_group()
    async def test_import_duplicate_without_overwrite_returns_409()

class TestDiffAPI:
    async def test_diff_returns_patch()
    async def test_diff_nonexistent_group_returns_404()

class TestPatchAPI:
    async def test_preview_patch_returns_summary()
    async def test_apply_patch_modifies_data()
    async def test_apply_patch_dry_run_no_changes()
    async def test_apply_patch_strategies()
```

### 6.2 前端测试

新增 `web_service/e2e/data.spec.ts`：

```typescript
test('should display groups list', async ({ page }) => {
  await page.goto('/data');
  await expect(page.getByTestId('groups-table')).toBeVisible();
});

test('should export group data', async ({ page }) => {
  await page.goto('/data');
  await page.click('[data-group-id="group_A"]');
  await page.click('text=导出 Data');
  // Verify download
});

test('should show diff between two groups', async ({ page }) => {
  await page.goto('/data');
  await page.selectOption('#source-group', 'group_A');
  await page.selectOption('#target-group', 'group_B');
  await expect(page.getByTestId('diff-summary')).toBeVisible();
});

test('should import patch with confirmation', async ({ page }) => {
  await page.goto('/data');
  await page.click('[data-group-id="group_A"]');
  await page.click('text=导入 Patch');
  await page.setInputFiles('input[type="file"]', 'patch.json');
  // Verify patch preview
  await page.click('text=确认应用');
});
```

---

## 7. 任务分解

### Phase 1: 后端 API（server/graph_service/routers/data.py）

1. 新增 router + Groups 统计 API（`GET /rest/data/groups`）
2. Group 数据详情 API（分页，`GET /rest/data/groups/{group_id}`）
3. 导出 API（`GET /rest/data/groups/{group_id}/export`，复用 cli.export）
4. 导入 API（`POST /rest/data/import`，multipart zip，复用 cli.import_）
5. Diff API（`GET /rest/data/diff?left=&right=`，复用 cli.diff）
6. Diff 导出 API（`GET /rest/data/diff/export?left=&right=`）
7. Patch 预览 API（`POST /rest/data/patch/preview`）
8. Patch 应用 API（`POST /rest/data/patch/apply`，复用 cli.apply）

### Phase 2: 前端 UI（web_service/）

9. 新增 Data Tab 入口页面（`app/data/page.tsx`）
10. Data 客户端组件（`app/data/data-client.tsx`，三种模式切换）
11. Groups 列表组件（状态1：无选择时展示）
12. Group 详情组件（状态2：单 group 时展示，统计 + 按需展开 JSONL）
13. Diff 视图组件（状态3：两个 group 时展示 diff 摘要）
14. 导入 Data 对话框（metadata 摘要 + 表数据折叠/展开 + 新 group_id 输入）
15. 导入 Patch 对话框（patch 预览 + from_group_id 覆盖 + to_group_id + 策略选择 + dry-run）
16. Dry Run 结果对话框

### Phase 3: 清理

17. 移除 documents 页面的 Import 按钮

### Phase 4: 测试

18. 后端 API 单元测试（`tests/server/test_data_api.py`）
19. 前端 E2E 测试（`web_service/e2e/data.spec.ts`）

---

## 8. 技术决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 导出格式 | ZIP (JSONL + metadata) | 与 CLI 兼容，支持 diff/import |
| 导入方式 | 前端上传 | 灵活，不依赖服务器路径 |
| JSONL 展示 | 统计摘要 + 按需展开 | 性能考虑，避免大量数据渲染 |
| Diff 模式 | 选择两个 group | 明确的操作语义 |
| Patch 应用 | 必须预览确认 | 安全性，防止误操作 |
| 冲突策略 | 用户选择 | 灵活性 |
| 临时文件 | /tmp + 自动清理 | 安全、整洁 |

---

## 9. 确认项汇总

- [x] Tab 名称确认为 **"Data"**
- [x] 导出文件名格式：`{group_id}_export_{timestamp}.zip`
- [x] Patch 文件名格式：`diff_{left}_vs_{right}_{timestamp}.json`
- [x] 文件大小限制：**500MB** 上限
- [x] API 前缀：`/rest/data`（独立 router，避免与 `/rest/graph` 冲突）
- [x] HTTP 方法：导出和 Diff 用 `GET`（幂等无副作用），导入和应用用 `POST`
- [x] from_group_id：默认取 patch.metadata.from_group_id，前端允许用户覆盖
- [x] 导入 Data 对话框：metadata 摘要展示，表数据默认折叠按需展开
- [x] 导入 Patch 对话框：必须展示 patch 预览 + 用户手动确认
