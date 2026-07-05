# Graphiti 数据导出/导入/差异对比工具设计方案

> 日期：2026-07-03
> 状态：方案设计

---

## 1. 背景与动机

Graphiti 知识图谱的数据以 `group_id` 为分区存储，用户需要：

1. **导出**：将一个 `group_id` 的完整数据导出为可读、可版本控制的格式
2. **导入**：将导出的数据导入到另一个 `group_id`（复制/迁移），自动处理 UUID 重映射
3. **差异对比**：对比两个 `group_id` 之间的语义差异，效果类似 `git diff`

### 数据存储现状

`graphiti-web-service` 使用 PostgreSQL + AGE，数据存储在 9 张 canonical 表（`schema public` 或自定义 schema）中：

```sql
-- 9 张表 (graphiti_core/driver/postgres_age/types.py)
entity_nodes       -- 含 name_embedding(vector) + search_vector(tsvector GENERATED)
episodic_nodes     -- 含 search_vector(tsvector GENERATED)
community_nodes    -- 含 name_embedding(vector) + search_vector(tsvector GENERATED)
saga_nodes
entity_edges       -- 含 fact_embedding(vector) + search_vector(tsvector GENERATED)
episodic_edges     -- FK: source→episodic_nodes, target→entity_nodes
community_edges    -- FK: source→community_nodes
has_episode_edges  -- FK: source→saga_nodes, target→episodic_nodes
next_episode_edges -- FK: source→episodic_nodes, target→episodic_nodes
```

- `search_vector` 是 `GENERATED ALWAYS AS ... STORED` 列，不需要导出，导入后自动重建
- `name_embedding` / `fact_embedding` 是普通列，随数据一起导出
- 索引（B-Tree、GIN、HNSW）不存新数据，导入后通过 `create_canonical_indexes()` 重建

### 与上游 `../graphiti` 的架构差异

上游 `../graphiti` 使用 `age` 驱动，将 embedding 和 FTS 数据存储在 **7 张独立的 companion 表**中（如 `entity_name_embeddings`、`entity_fts` 等）。导出时需要同时导出 AGE 图数据 + 7 张 companion 表。

`graphiti-web-service` 的 `postgres_age` 驱动将所有数据整合在 9 张表中，导出更简洁。

---

## 2. 为什么不用 CSV

CSV 存在以下严重问题：

| 问题 | 影响 |
|---|---|
| `vector` 列序列化 | `[0.123, 0.456, ...]` 在 CSV 中导致引号转义地狱 |
| `jsonb` 列嵌套 | `{"key": "val"}` 中的引号和逗号破坏 CSV 解析 |
| `text[]` 数组列 | 数组格式复杂 |
| `tsvector` 列 | 不需要导出但 CSV 难以排除 |
| Git diff 可读性 | 单行几百字符，diff 输出不可读 |
| 排序不稳定 | 每次导出顺序可能不同，diff 产生假阳性 |

---

## 3. 存储格式：JSON Lines (.jsonl) + 业务主键排序

### 目录结构

```
exports/
└── <group_id>/
    ├── metadata.json            # 导出元信息
    ├── entity_nodes.jsonl       # 按 (name, labels) 排序
    ├── episodic_nodes.jsonl     # 按 (valid_at, content_hash) 排序
    ├── community_nodes.jsonl    # 按 (name) 排序
    ├── saga_nodes.jsonl         # 按 (name) 排序
    ├── entity_edges.jsonl       # 按 (src_name, tgt_name, name) 排序
    ├── episodic_edges.jsonl     # 按 (episode_content_hash, entity_name) 排序
    ├── community_edges.jsonl    # 按 (community_name, target_name) 排序
    ├── has_episode_edges.jsonl  # 按 (saga_name, episode_content_hash) 排序
    └── next_episode_edges.jsonl  # 按 (src_episode, tgt_episode) 排序
```

### JSONL 格式

每行一个 JSON 对象，一个文件对应一张表：

```jsonl
{"uuid":"a1b2c3...","name":"Alice","group_id":"abc","labels":["Person"],"summary":"Engineer at Google","name_embedding":[0.12,0.34,0.056],"created_at":"2025-06-01T10:00:00Z","attributes":{"dept":"eng","level":5}}
{"uuid":"d4e5f6...","name":"Bob","group_id":"abc","labels":["Person"],"summary":"Designer","name_embedding":[0.78,0.91,0.023],"created_at":"2025-06-01T10:00:00Z","attributes":{}}
```

### 字段选择

| 导出 | 不导出 | 原因 |
|---|---|---|
| uuid, name, group_id, labels, summary, attributes | — | 核心数据 |
| name_embedding, fact_embedding | — | 向量数据，原样保留 |
| created_at, valid_at, expired_at 等 | — | 时间戳 |
| content, source, source_description | — | 文本数据 |
| episodes[], entity_edges[] | — | UUID 数组 |
| source_node_uuid, target_node_uuid | — | 边端点 |
| — | `search_vector` | GENERATED 列，导入时自动重建 |

### metadata.json

```json
{
  "group_id": "abc",
  "exported_at": "2026-07-03T15:30:00Z",
  "schema_version": 1,
  "counts": {
    "entity_nodes": 45,
    "episodic_nodes": 12,
    "community_nodes": 3,
    "saga_nodes": 0,
    "entity_edges": 128,
    "episodic_edges": 56,
    "community_edges": 18,
    "has_episode_edges": 0,
    "next_episode_edges": 11
  }
}
```

### 排序键（业务主键）

排序确保每次导出的 JSONL 行顺序一致，使得 git diff 稳定可靠：

| 表 | 排序键 |
|---|---|
| entity_nodes | (name, labels) |
| episodic_nodes | (valid_at, sha256(content)[:12]) |
| community_nodes | (name) |
| saga_nodes | (name) |
| entity_edges | (src_name, tgt_name, name) |
| episodic_edges | (episode_content_hash, entity_name) |
| community_edges | (community_name, target_name) |
| has_episode_edges | (saga_name, episode_content_hash) |
| next_episode_edges | (src_episode_content_hash, tgt_episode_content_hash) |

**注意**：边表中的 "name" 需要 JOIN 对应节点表来获取。导出时先导出节点表，构建 uuid→name 映射，然后导出边表时解析 UUID 为可读名称。

### 为什么 JSONL 优于 CSV

| 维度 | CSV | JSONL |
|---|---|---|
| vector 列 | `[0.1,0.2,...]` 引号地狱 | 原生 JSON 数组 |
| jsonb 列 | 嵌套引号转义噩梦 | 原生 JSON 对象 |
| text[] 列 | 复杂格式 | 原生 JSON 数组 |
| Git diff | 单行几百字符不可读 | `jq` 或 `git diff --word-diff` 可读 |
| 合并 | 无法合并 | 排序后 `git merge` 可行 |
| 解析 | 大量边界情况 | `json.loads(line)` |

---

## 4. 功能设计

### 4.1 导出命令

```bash
graphiti-cli export \
  --dsn "postgresql://..." \
  --schema public \
  --group-id abc \
  --output-dir exports/abc

# 输出
# exports/abc/
#   metadata.json
#   entity_nodes.jsonl
#   episodic_nodes.jsonl
#   ...
```

**流程**：

1. 连接数据库，对每张表执行 `SELECT * FROM {table} WHERE group_id = $1`
2. 对于边表，JOIN 节点表获取可读名称用于排序
3. 按业务主键排序
4. 排除 `search_vector` 列
5. 写入 JSONL 文件 + metadata.json

### 4.2 导入命令

```bash
graphiti-cli import \
  --dsn "postgresql://..." \
  --schema public \
  --input-dir exports/abc \
  --new-group-id xyz

# 导入完成后自动调用 create_canonical_indexes()
```

**流程**：

1. 读取 metadata.json 获取统计信息
2. 生成 UUID 映射表 `old_uuid → new_uuid`
3. 按节点表优先、边表其次的顺序导入
4. 对每条记录：替换 uuid、group_id、所有引用 UUID（source_node_uuid, target_node_uuid, episodes[], entity_edges[], first_episode_uuid, last_episode_uuid）
5. 批量 INSERT
6. 调用 `create_canonical_indexes()` 重建索引（`search_vector` 由数据库自动生成）

**UUID 重映射覆盖的 7 类引用**：

| # | 表.列 | 操作 |
|---|---|---|
| 1 | 所有 Node 表的主键 `uuid` | 替换 |
| 2 | 所有 Edge 表的主键 `uuid` | 替换 |
| 3 | Edge 表的 `source_node_uuid`, `target_node_uuid` | 查找映射替换 |
| 4 | `entity_edges.episodes[]` | 查找映射替换 |
| 5 | `episodic_nodes.entity_edges[]` | 查找映射替换 |
| 6 | `saga_nodes.first_episode_uuid`, `last_episode_uuid` | 查找映射替换 |
| 7 | 全部表的 `group_id` | 替换为新值 |

### 4.3 差异对比命令

```bash
graphiti-cli diff \
  --input-dir exports/abc \
  --input-dir exports/xyz \
  --output diff-output.html

# 或直接对比数据库中的两个 group_id
graphiti-cli diff \
  --dsn "postgresql://..." \
  --schema public \
  --from-group-id abc \
  --to-group-id xyz
```

**语义 diff 流程**：

1. 读取双方的 JSONL 文件（或从数据库直接加载）
2. 对每张表，按业务主键建立索引 `{business_key: row}`
3. 对比：
   - 左有右无 → removed
   - 左无右有 → added
   - 两边都有，字段有差异 → modified
   - 两边都有，完全相同 → unchanged
4. 忽略字段：`uuid`、`group_id`、引用的 UUID（期望变化）
5. 输出 HTML 报告（参考 `diff-viewer.html` 的设计）

**diff-viewer 设计要点**：

参考 `/diff-viewer.html`：
- 暗色终端主题
- 等宽字体
- 颜色编码：绿 + 红 - 黄 ~ 橙 !
- 5 种记录状态：unchanged / added / removed / modified / conflict
- 冲突采用 git merge conflict 格式（`<<<<<<<` / `=======` / `>>>>>>>`）
- 每张表可折叠
- 顶部统计栏 + 底部汇总表

### 4.4 Patch Apply 命令

`graphiti diff` 的 JSON 输出就是 patch 文件，`graphiti apply` 读取并执行变更。

**核心原则**：diff 的输出 = patch 的输入。

```
group_abc ──→ graphiti diff ──→ patch.json ──→ graphiti apply ──→ group_xyz
```

#### Patch 文件格式

```json
{
  "version": 1,
  "metadata": {
    "from_group_id": "abc",
    "created_at": "2026-07-04T10:00:00Z"
  },
  "changes": {
    "entity_nodes": {
      "added": [
        {
          "name": "Alice",
          "labels": ["Person"],
          "summary": "Data Scientist",
          "attributes": {"dept": "ds", "level": 4}
        }
      ],
      "removed": [
        {"name": "Bob", "labels": ["Person"]}
      ],
      "modified": [
        {
          "match": {"name": "John", "labels": ["Person"]},
          "fields": {
            "summary": {"old": "Engineer at Google", "new": "Engineer at Meta"}
          }
        }
      ],
      "conflicts": [
        {
          "match": {"name": "Sam", "labels": ["Person"]},
          "ours":   {"summary": "PM at Stripe", "labels": ["Person", "PM"]},
          "theirs": {"summary": "PM at Notion", "labels": ["Person"]}
        }
      ]
    },
    "entity_edges": {
      "added": [
        {
          "source": {"name": "John", "labels": ["Person"]},
          "target": {"name": "Meta", "labels": ["Organization"]},
          "name": "WORKS_AT",
          "fact": "John works at Meta since 2025"
        }
      ],
      "removed": [
        {
          "source": {"name": "Bob", "labels": ["Person"]},
          "target": {"name": "Mary", "labels": ["Person"]},
          "name": "KNOWS"
        }
      ],
      "modified": [],
      "conflicts": []
    }
  }
}
```

**匹配规则**：`added` / `removed` 中的对象用业务主键定位。对于边，`source` / `target` 用所连接节点的业务主键来描述，apply 时解析为实际 UUID。

#### 三种 Apply 模式

```bash
# 模式 1: 新建目标 group（最常用）
# 复制 from_group_id 的数据 → 应用 patch → 写入 to_group_id
graphiti-cli apply patch.json --to-group-id xyz

# 模式 2: 原地修改（危险操作）
# 直接修改 from_group_id 的数据，不可逆
graphiti-cli apply patch.json --in-place

# 模式 3: Dry-run 验证
# 检查 patch 能否干净应用，报告冲突但不写入
graphiti-cli apply patch.json --dry-run
```

#### Apply 执行流程

```
1. 读取 patch.json
2. 连接数据库，加载 from_group_id 的全部数据
3. 生成新旧 UUID 映射表（新建目标 group 时）
4. 按顺序应用变更（每张表独立处理）：

   entity_nodes:
     removed  → 按 (name, labels) 匹配并标记删除
                级联标记：source/target 为被删节点的边也删除
     added    → 生成新 UUID，INSERT
     modified → 按 match 条件找到行，UPDATE fields 中的 new 值
     conflicts→ 按策略处理（见下文）

   entity_edges:
     removed  → 按 (source_name, target_name, edge_name) 匹配并删除
     added    → 解析 source/target 业务主键为实际 UUID，生成新 UUID，INSERT
     modified → 同上

   ... 其余表同理

5. 处理级联影响：
   - 实体被删除 → 所有引用该实体的边自动删除
   - 实体被删除 → community_edges 中指向该实体的行删除
   - Episode 被删除 → entity_edges.episodes[] 清理引用

6. 调用 create_canonical_indexes() 重建索引
```

#### 冲突处理策略

```bash
# 严格模式：有冲突就中止（默认）
graphiti-cli apply patch.json --strict
# → "Error: 2 conflicts found. Use --strategy or --interactive to resolve."

# 策略模式：自动选择
graphiti-cli apply patch.json --strategy ours
# → 冲突字段保留旧值

graphiti-cli apply patch.json --strategy theirs
# → 冲突字段使用新值

# 交互模式：逐条提示
graphiti-cli apply patch.json --interactive
# ! Sam (Person): summary conflict
#   (o) ours:   "PM at Stripe"
#   (t) theirs: "PM at Notion"
#   (s) skip:   leave unchanged
#   (m) manual: enter custom value
# > o
# ! "Product" Community: summary, members conflict
#   ...

# 部分应用：跳过冲突，应用其余
graphiti-cli apply patch.json --skip-conflicts
# → 应用所有非冲突变更，冲突项保持原状
```

这和 `git merge --strategy` / `git mergetool` 的交互逻辑一致。

#### 可逆性

```bash
# 生成反向 patch
graphiti-cli diff --from xyz --to abc --format json > reverse.patch.json

# 验证可逆性
graphiti-cli apply patch.json --to-group-id xyz
graphiti-cli apply reverse.patch.json --to-group-id abc2
graphiti-cli diff --db-group abc --db-group abc2
# → "No differences found."
```

#### 完整工作流示例

```bash
# 1. 从数据库导出基准
graphiti-cli export --group-id abc --output-dir data/abc

# 2A. 方式一：在 JSONL 中手工编辑，生成 patch
vim data/abc/entity_nodes.jsonl
graphiti-cli diff --from data/abc-orig --to data/abc --format json > changes.patch.json

# 2B. 方式二：直接从两个 group 生成 patch
graphiti-cli diff --db-group abc --db-group xyz --format json > changes.patch.json

# 3. 审查 patch（以 diff-viewer HTML 展示）
graphiti-cli diff --patch changes.patch.json --output review.html

# 4. Dry-run 验证
graphiti-cli apply changes.patch.json --to-group-id xyz --dry-run
# → "Patch applies cleanly. 5 added, 3 removed, 2 modified."

# 5. 正式应用
graphiti-cli apply changes.patch.json --to-group-id xyz

# 6. 验证
graphiti-cli diff --db-group abc --db-group xyz
# → "All expected changes applied. No unexpected differences."
```

---

## 5. 完整 UUID 依赖图

```
entity_nodes.uuid
├── entity_edges.source_node_uuid          ← FK
├── entity_edges.target_node_uuid          ← FK
└── episodic_edges.target_node_uuid        ← FK

episodic_nodes.uuid
├── episodic_edges.source_node_uuid        ← FK
├── has_episode_edges.target_node_uuid     ← FK
├── next_episode_edges.source_node_uuid    ← FK
├── next_episode_edges.target_node_uuid    ← FK
├── saga_nodes.first_episode_uuid          ← 逻辑引用
├── saga_nodes.last_episode_uuid           ← 逻辑引用
└── entity_edges.episodes[]                ← 数组内的 UUID

entity_edges.uuid                          ← PK
└── episodic_nodes.entity_edges[]          ← 数组内的 UUID

community_nodes.uuid
├── community_edges.source_node_uuid       ← FK
└── community_edges.target_node_uuid       ← 逻辑引用

saga_nodes.uuid
└── has_episode_edges.source_node_uuid     ← FK
```

---

## 6. Git 集成工作流

JSONL + 业务主键排序使得 git diff / merge 开箱即用：

```bash
# 导出两个版本
graphiti-cli export --group-id abc --output-dir data/abc
graphiti-cli export --group-id xyz --output-dir data/xyz

# 提交到 Git
git add data/
git commit -m "graph data snapshot"

# 查看差异（语义 diff）
graphiti-cli diff --from-group-id abc --to-group-id xyz > diff.html

# 或 原生 git diff（查看原始 JSONL 行级差异）
git diff --word-diff data/

# 合并两个分支的修改
git merge feature-branch
graphiti-cli import --input-dir data/abc --new-group-id merged
```

**合并场景**：
- 如果两个人同时修改了同一 entity 的不同字段（如 A 改了 summary，B 改了 attributes），git merge 自动合并
- 如果两人修改了同一字段，git 会产生冲突标记，用户在 diff-viewer 中看到 `! conflict` 提示
- 合并后需要验证数据完整性（所有引用 UUID 是否有效）

---

## 7. 文件结构规划

```
graphiti-web-service/
├── cli/
│   ├── __init__.py
│   ├── main.py              # CLI 入口 (argparse)
│   ├── export.py            # 导出逻辑
│   ├── import_.py           # 导入逻辑 (+ UUID 重映射)
│   ├── diff.py              # 语义 diff 引擎
│   ├── apply.py             # Patch apply 引擎 (+ 冲突处理)
│   └── render.py            # HTML 渲染
├── tests/
│   ├── test_export.py
│   ├── test_import.py
│   ├── test_diff.py
│   └── test_apply.py
├── diff-viewer.html          # 静态示例（已创建）
└── docs/
    └── 26-07-03-graphiti-diff-plan.md  # 本文档
```

### 依赖

```
httpx, asyncpg, orjson  (已有)
```

无需新增依赖，JSON 序列化使用 stdlib json 或 orjson，HTML 渲染为纯字符串模板。

---

## 8. 待决策事项

1. **向量导出格式**：`name_embedding` 以 float 数组导出还是 base64 编码？数组可读性好但体积大
2. **边表排序**：边表排序需要 JOIN 节点表获取名称，是否在导出阶段做 JOIN 还是导出后由 CLI 解析？
3. **增量导出**：是否需要支持 "仅导出变更"（基于时间戳）？
4. **Patch 粒度**：patch 文件是一张大 JSON 还是 9 个文件各一张（类似 JSONL 目录结构）？
5. **级联删除策略**：apply 时删除一个实体，是否自动级联删除关联边？还是报错要求用户显式处理？
6. **事务边界**：apply 的所有操作是否在一个事务中？大数据量时是否需要分批提交？