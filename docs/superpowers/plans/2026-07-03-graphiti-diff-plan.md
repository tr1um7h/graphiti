# Graphiti 数据导出/导入/差异对比工具设计方案

> 日期：2026-07-03（更新 2026-07-05）
> 状态：方案设计（已基于代码库验证和补充）

---

## 1. 背景与动机

Graphiti 知识图谱的数据以 `group_id` 为分区存储，用户需要：

1. **导出**：将一个 `group_id` 的完整数据导出为可读、可版本控制的格式
2. **导入**：将导出的数据导入到另一个 `group_id`（复制/迁移），自动处理 UUID 重映射
3. **差异对比**：对比两个 `group_id` 之间的语义差异，效果类似 `git diff`

### 数据存储现状（已通过代码验证）

`graphiti-web-service` 使用 **PostgreSQL + AGE**（不是 Neo4j）。数据存储在两层中：

1. **SQL 表**（9 张 canonical 表，schema 可配置，默认 `public`）
2. **AGE 图投影**（从 SQL 表同步，用于 Cypher 查询）

```sql
-- 9 张 SQL 表 (graphiti_core/driver/postgres_age/types.py)
entity_nodes       -- 含 name_embedding(vector) + search_vector(tsvector GENERATED)
episodic_nodes     -- 含 search_vector(tsvector GENERATED)
community_nodes    -- 含 name_embedding(vector) + search_vector(tsvector GENERATED)
saga_nodes
entity_edges       -- 含 fact_embedding(vector) + search_vector(tsvector GENERATED)
episodic_edges     -- FK: source→episodic_nodes, target→entity_nodes
community_edges    -- FK: source→community_nodes, target→entity_nodes|community_nodes
has_episode_edges  -- FK: source→saga_nodes, target→episodic_nodes
next_episode_edges -- FK: source→episodic_nodes, target→episodic_nodes
```

完整的 DDL 见 `graphiti_core/driver/postgres_age/schema.py:104-296`。

**关键 FK 约束**：

```
entity_edges      → entity_nodes (ON DELETE CASCADE, 双向 FK)
episodic_edges    → episodic_nodes + entity_nodes (ON DELETE CASCADE)
community_edges   → community_nodes (ON DELETE CASCADE) + 逻辑引用 entity/community
has_episode_edges → saga_nodes + episodic_nodes (ON DELETE CASCADE)
next_episode_edges → episodic_nodes (双向 FK, ON DELETE CASCADE)
saga_nodes        → episodic_nodes (ON DELETE SET NULL)
```

**重要**：`community_edges.target_node_uuid` 没有 FK 约束，它可以指向 `entity_nodes.uuid` 或 `community_nodes.uuid`（多态引用）。UUID 重映射时两个映射表都要查。

**现有代码已具备的能力**：
- `*_to_row` / `*_from_row` 序列化函数（`serialization.py` + `records.py`）
- `get_by_group_ids` 按 group_id 查询所有表的所有数据
- `save` / `save_bulk` INSERT 带 `ON CONFLICT (uuid) DO UPDATE`
- `create_canonical_indexes()` 重建所有索引（B-Tree、GIN、HNSW）
- `rebuild_age_projection()` 从 SQL 表同步 AGE 图投影
- `delete_by_group_id` 级联清理

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
{"uuid":"a1b2c3...","name":"Alice","group_id":"abc","labels":["Person"],"summary":"Engineer at Google","name_embedding":[0.123456,-0.234567,0.001234],"created_at":"2025-06-01T10:00:00Z","attributes":{"dept":"eng","level":5}}
{"uuid":"d4e5f6...","name":"Bob","group_id":"abc","labels":["Person"],"summary":"Designer","name_embedding":[0.789012,-0.910123,0.023456],"created_at":"2025-06-01T10:00:00Z","attributes":{}}
```

### 向量列的导出格式

pgvector 内部存储为 **float32**（单精度，约 6 位有效数字）。导出时用 `round(f, 6)` 压缩精度：

- 当前默认 1024 维（BGE-large-zh-v1.5，配置 `server/graph_service/config.py:48`）
- 每向量约 8 KB（JSON float 数组），全精度约 15 KB
- 6 位小数完全覆盖 float32 精度，多出的位数是噪声
- 不用 base64：虽然更小（~5.5 KB），但丧失可读性，`git diff` 看到乱码，违背 JSONL 可 diff 的初衷

体积估算（1024-dim，6 位小数）：

| 数据规模 | 向量总量 | 向量数据体积 |
|---|---|---|
| 1 万实体 + 1 万边 | 2 万 | ~160 MB |
| 10 万实体 + 10 万边 | 20 万 | ~1.6 GB |

### 字段选择

| 导出 | 不导出 | 原因 |
|---|---|---|
| uuid, name, group_id, labels, summary, attributes | — | 核心数据 |
| name_embedding, fact_embedding | — | 向量数据，`round(f, 6)` 原样保留 |
| created_at, valid_at, expired_at 等 | — | 时间戳，保持原值不修改 |
| content, source, source_description | — | 文本数据 |
| episodes[], entity_edges[] | — | UUID 数组 |
| source_node_uuid, target_node_uuid | — | 边端点 |
| — | `search_vector` | GENERATED 列，导入时自动重建 |

### metadata.json

```json
{
  "group_id": "abc",
  "exported_at": "2026-07-03T15:30:00Z",
  "schema": "public",
  "embedding_dimension": 1024,
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

**边表需要 JOIN 节点表获取名称用于排序。** 导出时先导出节点表，构建 uuid→name 映射后在内存中排序；或者导出边表时直接 JOIN 数据库查询。**推荐在数据库层 JOIN 排序**，一次查询搞定：

```sql
SELECT e.*
FROM entity_edges e
JOIN entity_nodes src ON src.uuid = e.source_node_uuid
JOIN entity_nodes tgt ON tgt.uuid = e.target_node_uuid
WHERE e.group_id = %s
ORDER BY src.name, tgt.name, e.name
```

---

## 4. 功能设计

### 4.1 导出命令

```bash
graphiti-cli export \
  --dsn "postgresql://..." \
  --schema public \
  --group-id abc \
  --output-dir exports/abc
```

**流程**：

1. 连接数据库，设置 `search_path` 到目标 schema
2. 按节点表优先、边表其次的顺序处理
3. 对于边表，JOIN 节点表获取可读名称用于排序（SQL 层完成）
4. 按业务主键排序
5. 排除 `search_vector` 列；向量列做 `round(f, 6)` 压缩
6. 写入 JSONL 文件 + metadata.json

### 4.2 导入命令

```bash
graphiti-cli import \
  --dsn "postgresql://..." \
  --schema public \
  --input-dir exports/abc \
  --new-group-id xyz

# 导入完成后自动调用 create_canonical_indexes() + rebuild_age_projection()
```

**流程**：

1. 读取 metadata.json 获取统计信息和 embedding 维度（校验与目标数据库一致）
2. **Phase 1：预生成 UUID 映射表** — 为所有 JSONL 中出现的 uuid 生成 `old_uuid → new_uuid` 映射（包括节点和边的 uuid）
3. **Phase 2：按依赖顺序批量 INSERT**
   - 节点表优先（4 张）：`entity_nodes` → `episodic_nodes` → `community_nodes` → `saga_nodes`
   - 边表其次（5 张）：`entity_edges` → `episodic_edges` → `community_edges` → `has_episode_edges` → `next_episode_edges`
   - 对每条记录：替换 uuid、group_id、所有引用 UUID
4. 调用 `create_canonical_indexes()` 重建索引（`search_vector` 由数据库自动生成）
5. 调用 `rebuild_age_projection()` 同步 AGE 图投影

**为什么用两阶段（预生成映射 + 批量 INSERT）而不是逐个表处理？**
因为 `entity_edges.episodes[]` 和 `episodic_nodes.entity_edges[]` 双向引用彼此的 UUID。如果逐表 INSERT，写 entity_edges 时 edge UUID 已经确定了但 episodic_nodes 还没写，episodes[] 引用就会出错。预先生成所有映射表保证 INSERT 时所有引用都有新 UUID 可用。

**Import 完成后必须做的两件事**：

1. `create_canonical_indexes()` — B-Tree、GIN（全文搜索）、HNSW（向量）索引。`search_vector` 在 INSERT 时自动生成。
2. `rebuild_age_projection()` — 从 9 张 SQL 表全量重建 AGE 图（`graphiti_core/driver/postgres_age/operations/graph_ops.py:221-233`）。不清除 AGE 投影的话，Cypher 查询看不到新数据。

### UUID 重映射覆盖的 7 类引用

| # | 表.列 | 操作 |
|---|---|---|
| 1 | 所有 Node 表的主键 `uuid` | 替换 |
| 2 | 所有 Edge 表的主键 `uuid` | 替换 |
| 3 | Edge 表的 `source_node_uuid`, `target_node_uuid` | 查找映射替换 |
| 4 | `entity_edges.episodes[]` | 查找映射替换（引用 edge uuids） |
| 5 | `episodic_nodes.entity_edges[]` | 查找映射替换（引用 node uuids） |
| 6 | `saga_nodes.first_episode_uuid`, `last_episode_uuid` | 查找映射替换 |
| 7 | 全部表的 `group_id` | 替换为新值 |

**`community_edges.target_node_uuid` 特殊处理**：该列无 FK 约束，可指向 `entity_nodes.uuid` 或 `community_nodes.uuid`。UUID 重映射时**两个映射表依次查找**，命中任意一个即可。

**不修改的列**：
- `created_at`、`valid_at`、`expired_at`、`invalid_at`、`reference_time` 等时间戳 — 保持原值
- `name_embedding`、`fact_embedding` — 保持原值，向量语义在新 group 中仍然有效
- `attributes`、`episode_metadata`（jsonb）— 保持原值
- `summary`、`content`、`fact`、`name` 等文本列 — 保持原值

### 4.3 差异对比命令

（同原方案，略）

### 4.4 Patch Apply 命令

（同原方案，略）

---

## 5. AGE 图投影同步（Plan 补充）

**导出层面**：只操作 SQL 表即可。AGE 投影不直接参与导出流程。

**导入层面**：导入 SQL 表完成后必须同步 AGE 投影，因为后续 Cypher 查询依赖它。流程：

```
INSERT 9 张 SQL 表 → create_canonical_indexes() → rebuild_age_projection()
```

`rebuild_age_projection()` 的内部逻辑（`graph_ops.py:225-233`）：

```sql
-- 1. 清理悬垂的 community_edges（source 不存在于 community_nodes）
DELETE FROM community_edges WHERE ...

-- 2. 清除所有 AGE 投影
MATCH (n) DETACH DELETE n

-- 3. 从 4 张节点表重建投影
-- entity_nodes  → CREATE (:Entity {uuid, group_id, name})
-- episodic_nodes → CREATE (:Episodic {uuid, group_id, name})
-- community_nodes → CREATE (:Community {uuid, group_id, name})
-- saga_nodes     → CREATE (:Saga {uuid, group_id, name})

-- 4. 从 5 张边表重建投影
-- entity_edges      → CREATE (a)-[:RELATES_TO {uuid, group_id, name}]->(b)
-- episodic_edges    → CREATE (:Episodic)-[:MENTIONS]->(:Entity)
-- community_edges   → CREATE (:Community)-[:HAS_MEMBER]->(:Community|Entity)
-- has_episode_edges → CREATE (:Saga)-[:HAS_EPISODE]->(:Episodic)
-- next_episode_edges → CREATE (:Episodic)-[:NEXT_EPISODE]->(:Episodic)
```

---

## 6. 完整 UUID 依赖图

```
entity_nodes.uuid
├── entity_edges.source_node_uuid          ← FK (CASCADE)
├── entity_edges.target_node_uuid          ← FK (CASCADE)
└── episodic_edges.target_node_uuid        ← FK (CASCADE)

episodic_nodes.uuid
├── episodic_edges.source_node_uuid        ← FK (CASCADE)
├── has_episode_edges.target_node_uuid     ← FK (CASCADE)
├── next_episode_edges.source_node_uuid    ← FK (CASCADE)
├── next_episode_edges.target_node_uuid    ← FK (CASCADE)
├── saga_nodes.first_episode_uuid          ← FK (SET NULL)
├── saga_nodes.last_episode_uuid           ← FK (SET NULL)
└── entity_edges.episodes[]                ← text[], 引用 entity_edges.uuid

entity_edges.uuid                          ← PK
└── episodic_nodes.entity_edges[]          ← text[], 引用 entity_edges.uuid

community_nodes.uuid
├── community_edges.source_node_uuid       ← FK (CASCADE)
└── community_edges.target_node_uuid       ← 多态引用 (entity or community, 无 FK)

saga_nodes.uuid
└── has_episode_edges.source_node_uuid     ← FK (CASCADE)
```

**注意**：`entity_edges.episodes[]` 和 `episodic_nodes.entity_edges[]` 是双向 text[] 数组，内容都是 UUID，需要两阶段重映射保证一致性。

---

## 7. Git 集成工作流

（同原方案，略）

---

## 8. 文件结构规划

```
graphiti-web-service/
├── cli/
│   ├── __init__.py
│   ├── main.py              # CLI 入口 (argparse)
│   ├── export.py            # 导出逻辑
│   ├── import_.py           # 导入逻辑 (+ UUID 重映射)
│   ├── diff.py              # 语义 diff 引擎
│   ├── apply.py             # Patch apply 引擎 (+ 冲突处理)
│   ├── render.py            # HTML 渲染
│   └── remap.py             # UUID 重映射核心逻辑
├── tests/
│   ├── test_export.py
│   ├── test_import.py
│   ├── test_diff.py
│   └── test_apply.py
├── diff-viewer.html          # 静态示例（已创建）
└── docs/
    └── 2026-07-03-graphiti-diff-plan.md  # 本文档
```

### 依赖

```
httpx, asyncpg, orjson  (已有)
```

无需新增依赖，JSON 序列化使用 stdlib json 或 orjson，HTML 渲染为纯字符串模板。

---

## 9. 已决策事项

### 9.1 向量导出格式

**决策：float 数组，`round(f, 6)` 压缩精度**

- pgvector 内部 float32，6 位小数完全覆盖精度
- JSONL 原生数组格式，`git diff` 可读
- 不使用 base64（虽然体积小 30%，但丧失可读性，违背 JSONL 可 diff 的初衷）

### 9.2 边表排序

**决策：导出阶段在数据库层 JOIN 排序**

SQL 查询直接 JOIN 节点表获取名称，一次查询完成排序，无需导出后二次解析。

### 9.3 增量导出

**决策：暂不支持，先做全量导出**

全量导出优先交付。增量导出（基于时间戳）作为后续迭代。

### 9.4 Patch 粒度

**决策：单文件大 JSON**

单个 `patch.json` 包含所有 9 张表的变更。理由：
- 三向合并（ours/theirs/base）只需一个文件
- `apply` 命令的事务边界清晰（要么全成功，要么全回滚）
- 跨表级联操作（删除实体 → 删除边）在一个文件中表达更自然

### 9.5 级联删除策略

**决策：自动级联删除，严格遵循 FK 约束语义**

- 删除 entity_node → 自动删除其 entity_edges（FK CASCADE）、episodic_edges（FK CASCADE）、community_edges（手动清理）
- 删除 episodic_node → 自动删除其 episodic_edges、has_episode_edges、next_episode_edges（FK CASCADE），saga_nodes 引用置 NULL（FK SET NULL）
- 删除 community_node → 自动删除其 community_edges（FK CASCADE）
- 和数据库已有的 FK 约束保持一致

### 9.6 事务边界

**决策：全量数据在单个事务中导入**

PostgreSQL transaction 保证 ACID。中等规模（<10万节点）直接单事务；超大规模可以分批 subtransaction 但需要处理中途失败的回滚。默认单事务，后续按需加分批选项。

### 9.7 配置参数

**`--schema` 参数必需。** 当前 driver 支持自定义 schema（`PostgresAgeDriver.schema`），同一 PostgreSQL 数据库可以有多个独立的 schema，每个 schema 有独立的 9 张 canonical 表 + AGE graph。导出/导入必须指定 schema。

### 9.8 目标 group_id 已存在时的行为

**决策：报错并要求手动指定 `--overwrite`**

```bash
graphiti-cli import ... --new-group-id xyz             # xyz 已有数据 → 报错退出
graphiti-cli import ... --new-group-id xyz --overwrite  # xyz 已有数据 → 先清空再导入
```

实现：导入前先 `SELECT 1 FROM entity_nodes WHERE group_id = $1 LIMIT 1`，有结果则：
- 无 `--overwrite` → 报错 `"group_id 'xyz' already contains data. Use --overwrite to replace."`
- 有 `--overwrite` → 调用 `driver.graph_ops.clear_data(group_ids=[new_group_id])` 清空目标 group

### 9.9 Import SQL 策略

**决策：绕过 ORM 方法，直接执行原始 SQL INSERT**

原因：
- 现有 `EntityNode.save()` 等方法除了写入 SQL 表，还同步 AGE 投影（如 `entity_edge_ops.py:63` 的 `_save_projection`），逐行同步投影在大批量导入中极其低效
- Import 的目标是一次性写入 SQL 表，最后批量重建 AGE 投影

做法：
- `export.py` 利用现有的 `get_by_group_ids` 和 `*_from_row` 读取数据
- `import.py` 绕过 `save()` 方法，直接用 `execute_query` 执行 `INSERT INTO ... VALUES (...)` 或 `execute_values` 批量插入
- 保留 `ON CONFLICT (uuid) DO UPDATE` 语义以保证幂等性
- 所有 INSERT 完成后，调用 `create_canonical_indexes()` + `rebuild_age_projection()`

---

## 10. 实现顺序建议

| 优先级 | 模块 | 说明 |
|---|---|---|
| 1 | `export.py` | 复杂度最低，利用现有 `*_to_row` 序列化 + `get_by_group_ids` |
| 2 | `import.py` | UUID 重映射 + 批量 INSERT + index + projection rebuild |
| 3 | `remap.py` | 从 import.py 抽出的重映射核心，供 apply.py 复用 |
| 4 | `diff.py` | 业务主键匹配 + 字段级 diff |
| 5 | `apply.py` | 最复杂：级联删除、冲突处理、三向合并策略 |
| 6 | `render.py` | HTML 报告（可延后） |