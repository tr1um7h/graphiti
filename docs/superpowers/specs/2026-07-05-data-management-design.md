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

**注意**: CLI 层 `import_group()` 无返回值，Web API 包装层需在导入成功后查询新 group 的表记录数，构造 `table_counts` 返回给前端。

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

> **⚠️ 性能注意**：Diff API 需要将两个 group 分别导出到临时目录（全部 9 张表的
> JSONL），再调用 `diff_groups()` 比较。对于数据量大的 group（数万条记录），
> 每次 diff 都会产生大量临时文件 I/O。当前设计未做缓存优化。
>
> 如后续出现性能瓶颈，可考虑直接查询数据库做 diff（跳过 JSONL 中间步骤），
> 或对同一 group 的导出结果做缓存复用。

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

> **⚠️ 设计隐患：preview 返回完整 patch 内容**
>
> 当 patch 文件较大（含大量 embedding 向量）时，全量返回给前端会导致：
> - 网络传输慢（可能数十 MB）
> - 前端内存压力大，浏览器可能卡死
> - 实际 UI 只需 summary 统计数据即可
>
> **建议**：preview API 只返回 `summary`（各表增删改统计），不返回完整 `patch`。
> 前端如需查看具体变更记录，可通过后续分页 API 按需加载。

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

**注意**: CLI 层 `apply_patch()` 返回 `{added, removed, modified, conflicts, dry_run}`，Web API 包装层负责添加 `success` 字段。错误时返回 `{"success": false, "error": "..."}`。

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
# Export: driver → JSONL files in output_dir
from cli.export import export_group_with_sorting
await export_group_with_sorting(driver, group_id, schema, output_dir)

# Import: JSONL files → database (creates new group)
from cli.import_ import import_group
await import_group(driver, input_dir, new_group_id, overwrite=False)

# Diff: compare two export directories → patch dict
from cli.diff import diff_groups
patch = diff_groups(left_dir, right_dir)  # returns dict, not writes file

# Apply: patch dict → database
from cli.apply import apply_patch
result = await apply_patch(driver, patch, from_group_id, to_group_id, strategy='ours', dry_run=False)
# Or from file:
from cli.apply import apply_patch_from_file
result = await apply_patch_from_file(driver, patch_file, from_group_id, to_group_id, strategy, dry_run)
```

**注意**：`import_group` 没有 `schema` 参数（从 `driver.schema` 读取）。`apply_patch` 接收 `patch` 字典（非文件路径），如需从文件加载请使用 `apply_patch_from_file`。

### 5.2 临时文件处理

- 导出时：在服务器 `/tmp` 创建临时目录，生成 JSONL 文件，打包为 zip 后返回，然后清理
- 导入时：接收上传的 zip 文件，解压到临时目录，处理后清理

### 5.3 导出数据格式说明

导出的 JSONL 文件中，边表（entity_edges, episodic_edges 等）包含额外的解析字段：
- `source_name` / `target_name` — 解析后的节点名称（用于跨组 diff）
- `source_content` / `target_content` — episodic 节点的内容摘要

这些字段在导入时会被自动过滤（不写入数据库），仅用于 diff 业务键匹配。

> **✅ 已修复（commit `cc92ad0`）**：边表 export 查询已添加 JOIN 解析语义标识字段，
> `diff.py` 和 `apply.py` 的业务键已改为基于语义字段匹配。详情见 Section 10.1。

---

## 6. 测试策略

### 6.1 后端测试

新增 `server/tests/test_data_api.py`：

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

**冲突策略语义说明**：`ours`/`theirs` 遵循 Git merge 约定：
- **Ours** — 保留目标 group（to_group_id）的现有数据，跳过冲突项的修改
- **Theirs** — 使用 patch 中来源 group（from_group_id）的数据覆盖冲突项
- **Skip** — 跳过整个有冲突的表，不修改任何记录

> **⚠️ 已知问题：代码中策略语义反转（实际无影响）+ 计数 bug**
>
> **策略反转**：`cli/apply.py:246` 中 `if strategy == 'theirs' and match_key in conflict_keys: continue`
> 错误地将 theirs 当作"保留目标"处理——theirs 跳过冲突（实际是 ours 语义），ours 不跳过（实际是 theirs 语义）。
>
> **但实际影响为零**：`cli/diff.py:_diff_table()` 中 `conflicts` 永远初始化为 `[]` 且从不填充，
> diff 输出永远不含冲突记录。apply 阶段的 `conflict_keys` 始终是空集，策略分支代码路径永远不会被触发。
>
> **额外 bug — modified 计数错误**：`apply.py:266` 的 `result['modified'] += 1` 在 `if match_key in target_index:` 块**外面**。
> 当 patch 引用 target 中不存在的记录时，不会执行 UPDATE，但计数仍然 +1，导致报告数字虚高。
>
> **修正方案**：
> 1. 将 line 246 的 `'theirs'` 改为 `'ours'`（或等将来实现真正的冲突检测后再改）
> 2. 将 `result['modified'] += 1` 移入 `if match_key in target_index:` 块内
>
> 详见 Section 10.2。

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

---

## 10. 已知问题与修正方案

> 本节记录设计评审中发现的 CLI 代码与设计不符的问题。
> 这些问题属于底层 `cli/` 模块的 bug，需要在 Web API 实现前修复。

### 10.1 ✅ 已修复：边表 Diff 业务键使用 UUID（跨组匹配失效）

**影响范围**：`cli/diff.py`、`cli/apply.py`、`cli/export.py`

**现状**：
- ✅ **已修复**（commit [`cc92ad0`](https://github.com/tr1um7h/graphiti-web-service/commit/cc92ad0)）
- 每个边表查询已添加 JOIN 解析语义标识字段（source_name, target_name, source_content_hash, target_content_hash）
- `diff.py:get_business_key()` 和 `extract_match_fields()`：每个边表独立分支，使用语义字段而非 UUID
- `apply.py` 同步更新为语义字段匹配
- 导入时新增的语义字段通过 `_JOIN_ALIAS_FIELDS` 自动过滤，不尝试写入数据库
- CLI E2E 测试已覆盖跨组 diff 场景

### 10.2 🟡 部分修复：ours/theirs 策略语义反转 + 冲突永不产生 + modified 计数 bug

**影响范围**：`cli/apply.py`、`cli/diff.py`

**发现 3 个关联问题：**

#### 问题 A：策略语义反转（已修复）

`apply.py` 中冲突检查现在正确使用 `strategy == 'ours'`（非 'theirs'）跳过冲突。详见实际代码 line 329。

#### 问题 B：diff_groups() 永远不产生冲突（未修复）

`cli/diff.py:_diff_table()` 中 `conflicts` 初始化为空列表且从未填充。diff 输出从不包含冲突记录，apply 阶段的 `conflict_keys` 始终是空集，策略分支代码路径永远不会被触发。这意味着：

- 冲突策略选择 UI（ours/theirs/skip-conflicts）是 **纯粹的 dead feature** — 无论如何选，行为都一样
- 真正的冲突检测（target 数据自 diff 创建后被修改）未实现 — apply_patch 无条件信任 patch 内容做 UPDATE，不验证 target 当前状态

#### 问题 C：modified 计数 bug（已修复）

`result['modified'] += 1` 现在正确位于 `if match_key in target_index:` 和 `if set_clauses:` 块内部（line 349），只有当实际执行了 UPDATE 时才计数。

### 10.3 🟡 重要：Diff API 性能——大 group 需要完整导出

**影响范围**：`GET /rest/data/diff`

**现状**：Diff API 需要将两个 group 分别导出到临时目录（全部 9 张表 JSONL），再调用 `diff_groups()` 比较。`diff_groups()` 的核心逻辑是纯内存业务键匹配，中间 JSONL 文件只是数据载体。对于数据量大的 group（数万条记录），每次 diff 都会产生不必要的磁盘 I/O。

**短期方案**：在 API 文档中说明性能限制，设置合理超时。

**长期方案**：`diff_groups()` 改为接受 `list[dict]` 参数（而非文件路径），API 层直接查询数据库将结果传入，跳过 JSONL 文件中间步骤。

### 10.4 🟡 重要：Patch Preview 返回完整 patch 内容

**影响范围**：`POST /rest/data/patch/preview`

**现状**：preview API 返回 `"patch": { ... full patch content ... }`，当 patch 文件较大（含大量 embedding 向量）时：
- 网络传输慢（可能数十 MB）
- 前端内存压力大，浏览器可能卡死
- 实际 UI 只需 summary 统计数据即可

**额外问题**：当前缺少 patch 内容的 **schema 验证**。`diff_groups()` 输出格式是隐式的（无 JSON Schema 定义），如果用户上传格式错误的 JSON，`apply_patch` 会在运行时崩溃（KeyError/TypeError）而非给出清晰的 400 错误。

**修正方案**：
1. preview API 只返回 `summary`（各表增删改计数），不返回完整 `patch`
2. 增加 patch `version` 字段校验和基本结构 schema 验证（至少检查 `metadata`、`changes` 字段存在且类型正确）
3. 前端如需查看具体变更记录，可通过后续分页 API 按需加载

### 10.5 🟡 轻微：导入操作无返回值

**影响范围**：`cli/import_.py:import_group()`

**现状**：`import_group()` 返回 `None`，API 层需要导入后再查询数据库获取 `table_counts`。

**影响**：仅多一次查询，不影响正确性。优先级低于 10.1-10.4。

**建议**：后续可考虑让 `import_group()` 返回 `dict[str, int]`（各表插入计数），减少额外查询。

---

## 11. 实现后补充说明

> 本节记录设计文档定稿后，在实现过程中新增的功能和修正。

### 11.1 新增功能：Group 删除

**不在原始设计范围内**，但在 Phase 1-2 实现完成后追加。

| 层级 | 变更 | 文件 |
|------|------|------|
| 后端 API | 新增 `DELETE /rest/data/groups/{group_id}` | `server/graph_service/routers/data.py` |
| 前端代理 | 新增 `DELETE` 方法路由 | `web_service/app/api/data/[...path]/route.ts` |
| 前端 UI | 删除按钮 + 确认对话框 + loading 状态 | `web_service/components/data/groups-table.tsx` |

删除逻辑：
- 前端弹出 `confirm()` 确认对话框
- 调用 `DELETE /api/data/groups/{group_id}`
- 成功后在 `data-client.tsx` 清除被删除 group 的选择状态
- 刷新 group 列表

### 11.2 CLI 导出生产环境硬化

**`cli/export.py`** 新增 3 项修复：

1. **`_JOIN_ALIAS_FIELDS`** — 边表 JOIN 查询产生的语义别名列（`source_name`, `target_name`, `source_content_hash`, `target_content_hash`）不属于数据库 schema，需要从 JSONL 输出中过滤，否则 import INSERT 会因"列不存在"报错
2. **`_json_safe()`** — 递归转换 numpy 类型（`float32`、`int64` 等）为 Python 原生类型。`json.dumps` 在某些平台上拒绝序列化 numpy 标量
3. **`_NumpyEncoder`** — 兜底的 JSON 编码器，处理 json.dumps 默认行为之外的 numpy 类型

### 11.3 CLI 导入生产环境硬化

**`cli/import_.py`** 新增 `_jsonify_values()`：将 Python `dict` 值序列化为 JSON 字符串，适配 psycopg jsonb 列。列表值保持原样（由 ARRAY 列和 pgvector 原生处理）。

### 11.4 Dockerfile 修复

- 新增 `UV_NO_INSTALLER_METADATA=1` 环境变量（uv 兼容性）
- 新增 `COPY ./cli ./cli`（运行时缺少 cli 模块导致 import 错误）
- 新增 `python-multipart` 依赖（FastAPI 文件上传端点必需）

### 11.5 前端修复

- **React key warning**：`group-detail.tsx` 中 `<></>` 改为 `<Fragment key={tableName}>`
- **侧边栏响应式**：`sidebar.tsx` 中 `lg:hidden` 改为 `md:hidden`（改善平板支持）
- **操作图标**：View 按钮使用 Eye icon，删除按钮使用 Trash2 icon + `text-destructive`

### 11.6 服务器测试路径

设计文档原定 `tests/server/test_data_api.py`，实际实现位于 `server/tests/test_data_api.py`（与 server package co-locate 的项目惯例一致）。
