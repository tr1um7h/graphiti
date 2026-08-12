# Memory Schema View Design

## Context

Graphiti web service 已有 Graph 视图（`/graph`）用于可视化知识图谱的实体实例和关系。但缺少一个**从数据源到摘要的全链路视图**——即 episode → entity → type → community 的提取与聚合过程。

本设计新增 **Memory Schema** 视图，以**多列卡片 + SVG 连线**布局展示这条链路，类似 Cognee 的 Memory Schema 视图。用户选定 group_id 后，可以直观看到：

- 这个 group 里有哪些 episode（原始数据）
- 从 episode 中提取了哪些 entity，按什么 type 分类
- 这些 entity 聚合成了哪些 community（摘要）

> 设计稿参考：`~/Downloads/memory_schema.html`（Cognee 静态 mock，**不照搬其 5 列结构**）

---

## Column Design（4 列）

Graphiti 没有 Cognee 的 "chunk" 概念（episode 是原子单位），所以不加 CHUNKS 列，保持 4 列：

```
EPISODES ──→ ENTITIES ──→ TYPES
                 │
                 └──→ SUMMARIES
```

| 列 | 数据源 | 含义 | 卡片分组 | 卡片内 items | 颜色 |
|----|--------|------|---------|-------------|------|
| **EPISODES** | `episodic_nodes` | 原始输入数据 | 按 `source` 字段（text / message / ...） | episode 名称 | cyan |
| **ENTITIES** | `entity_nodes` | 提取出的实体 | 按 `labels`（每个 label 一张卡） | 实体名称 | green |
| **TYPES** | labels 聚合 | 实体类型定义 | **单张 ENTITYTYPE 卡** | 所有类型名 | purple |
| **SUMMARIES** | `community_nodes` | 社区级聚合摘要 | 单张 COMMUNITY 卡 | 社区名称 + summary 片段 | amber |

### 关键设计决策

**1. EPISODES 按 `source` 分组，不是每条一张卡**

3 条 text + 2 条 message → 2 张卡：`TEXT (3)` 和 `MESSAGE (2)`，卡内列出 episode 名称。不是 5 张各含 1 个 item 的卡片。

**2. ENTITIES 按 `labels` 分组，不是每个实体一张卡**

7 个 Animal + 6 个 Horse → 2 张卡：`ANIMAL (7)` 和 `HORSE (6)`，卡内列出实体名称。**多 label 实体在所有 label 下都出现**（实体有 `['Person','Employee']` → 同时出现在 Person 卡和 Employee 卡中）。

**`Entity` 是每个实体都会保留的基础标签，不作为常规分组**。只有没有其他具体 label 的实体才显示在 `ENTITY` 兜底卡中；已有具体分类的实体不要重复出现在 `ENTITY` 卡里。

**3. TYPES 是单张卡片，所有类型名为 items**

参照 demo 的 `ENTITYTYPE (13)` 卡。不是每个类型一张空卡。这样用户能看到所有类型一览，点击某个 type 可以跳转到 ENTITIES 列对应的 label 卡。

**4. SUMMARIES 来自 `community_nodes`，不是 `entity_nodes.summary`**

- `entity_nodes.summary` 只是实体的一个字段（周边关系描述），不是独立节点
- **`community_nodes`** 是独立节点，通过 `community_edges`（HAS_MEMBER）关联到实体，代表社区级聚合摘要
- 也有 `saga_nodes.summary`（跨 episode 摘要），但不在本视图范围内

---

## Data Flow（连线）

列与列之间的 SVG 贝塞尔曲线表示数据流向，标注关系类型和数量：

| 连线 | 来源 | 标签格式 | 说明 |
|------|------|---------|------|
| EPISODES → ENTITIES | `episodic_edges` | `is_part_of ×N` | episode 包含 N 个实体 |
| ENTITIES → TYPES | `labels` | `is_a ×N` | 该类型下有 N 个实体 |
| ENTITIES → SUMMARIES | `community_edges` | `has_member ×N` | 社区包含 N 个实体 |
| ENTITIES → ENTITIES | `entity_edges` | `<edge_name> ×N` | 同列连线，实体间关系（如 `won ×2`） |

连线颜色与目标列一致（episode→entity 用 green，entity→type 用 purple，entity→summary 用 amber）。

---

## Detail Panel

点击任意卡片内的 item 后，右侧滑入 Detail Panel，展示该节点的 connections。

**索引方式**：`details` 按**实体 UUID**（或 episode UUID / community UUID）索引，不按 label 名。这样 Panel 能通过 `focusedItemId` 直接定位。

**内容结构**（参照 demo）：

```
┌──────────────────────────┐
│ ‹ animal            ✕    │  ← 返回父级 + 关闭
│                          │
│ dog                      │  ← 节点名称
│ animal                   │  ← 节点类型
│                          │
│ CONNECTIONS              │
│ → animal                 │  ← forward tag（可点击跳转）
│ ← sherlock holmes        │  ← backward tag（可点击跳转）
│ "福尔摩斯向警长确认..."    │  ← quote（entity_edges.fact）
│ ← stable                 │  ← backward tag
└──────────────────────────┘
```

**Connection 数据来源**：

- **forward tag**：`entity_edges` 中 `source_node_uuid == 当前实体`，text = 目标实体名
- **backward tag**：`entity_edges` 中 `target_node_uuid == 当前实体`，text = 源实体名
- **quote**：`entity_edges.fact`，展示提取出该关系的原文事实
- **type tag**：实体自身的 `labels`（forward 指向类型名）

---

## Interaction Design

### Overview State（默认）

4 列卡片从左到右排列，每列有列标题，每张卡有颜色点 + 名称 + 计数 + 实例项。底部缩放控制。

**默认不显示任何连线**——画布只有卡片和 items，干净无干扰。连线只在 Focus State 下出现。

### Focus State（点击卡片项）

点击某个 item 后：

1. **高亮选中项**：绿色 outline
2. **只显示关联对象**：根据 `edges` 数据，计算与选中项直接相连的所有 items，这些 items 保持可见并高亮
3. **隐藏无关联项**：与选中项没有直接关系的 items **完全隐藏**（`display: none`），不是变暗——画面上只留下有意义的关联链路
4. **显示连线**：选中项与其关联项之间出现 SVG 贝塞尔曲线，标注关系类型（如 `is_a`、`has_member`、`won ×2`）
5. **Detail Panel 滑入**：右侧面板展示选中项的完整 connections（forward/backward tags + quotes）
6. **顶部提示**："Focused on xxx | Clear focus"

示例：点击 ENTITIES 列的 `dog` item：
- dog 高亮
- EPISODES 列：只显示包含 dog 的 episode items，其余隐藏
- TYPES 列：只显示 `animal`（dog 的 label），其余隐藏
- SUMMARIES 列：只显示 dog 所属的 community，其余隐藏
- ENTITIES 列：只显示与 dog 有 `entity_edges` 关系的实体，其余隐藏
- 连线从 dog 指向以上所有可见 items

### Detail Panel 内导航

Panel 内的 tag（如 `→ animal`、`← sherlock holmes`）可点击 → 切换 focus 到对应实体，画布联动刷新。

### Clear Focus

点击 "Clear focus" 或画布空白区域 → 隐藏所有连线 → 恢复所有 items 可见 → Detail Panel 滑出 → 回到 Overview。

---

## Visual Design

对齐 demo 的视觉风格，适配项目 Tailwind v4 + shadcn 设计令牌：

| 元素 | 颜色 |
|------|------|
| 背景 | `bg-background` + 点阵背景 |
| 卡片 | `bg-card` + `border-border` |
| EPISODES 强调色 | cyan |
| ENTITIES 强调色 | green |
| TYPES 强调色 | purple |
| SUMMARIES 强调色 | amber |
| Focus 高亮 | green outline |

### Zoom Controls

- **−**：缩小 0.1（最小 0.5）
- **+**：放大 0.1（最大 1.6）
- **Fit**：重置为 1.0
- CSS `transform: scale()` 作用于 canvas 容器

---

## API

`GET /rest/memory-schema?group_id=<id>`

一次性返回前端画布所需的全部结构化数据：

- **columns**：4 列数据，每列含若干卡片，每卡含若干 items
- **edges**：卡片间的连线（source card id、target card id、label、color）
- **details**：按 UUID 索引的 Detail Panel 数据
- **counts**：各列的卡片/项目计数

前端通过 BFF route（`/api/memory-schema`）代理调用，不做复杂重组——后端直接返回列结构，前端直接渲染。

---

## Verification

1. **后端**：`curl /rest/memory-schema?group_id=xxx | jq` 返回非空数据，4 列都有内容
2. **EPISODES**：按 source 分组，不是每条一张卡
3. **ENTITIES**：按 label 分组，多 label 实体出现在多张卡中，且 `Entity` 不作为常规分组
4. **TYPES**：单张卡片，所有类型名为可点击 items
5. **SUMMARIES**：来自 `community_nodes`，不是 entity 的 summary 字段
6. **默认无连线**：Overview 状态下画布只有卡片和 items，无 SVG 连线
7. **Focus 交互**：点击 item → 只显示关联项（无关联项隐藏）+ 连线 + 高亮 + Detail Panel 滑入
8. **Detail Panel**：按实体 UUID 查到 connections，tag 可点击跳转并联动画布
9. **Clear focus**：点击 Clear 或空白区域 → 隐藏连线 + 恢复所有 items → 回到 Overview
10. **空数据**：group_id 无数据时显示明确提示，不是空白页

---

## Entity Classification（实体分类补充设计）

### 背景

当前数据库中的实体普遍是 `['Entity']`，缺少 Person、Location、Organization、Object、Document、Event 等细粒度分类。根因不是实体模型没有分类字段，而是服务端在未选择 extraction schema 时没有向 LLM 注入具体 `entity_types`，导致提取流程只能使用默认的 `Entity` 类型。

现有代码已经具备分类基础：

- `EntityNode.labels` 保存实体类型，Postgres AGE 写入时保留 `Entity` 并合并其他 labels
- `ExtractedEntity.entity_type_id` 已要求 LLM 输出类型 ID
- `_build_entity_types_context()` 会根据 `entity_types` 生成类型列表
- `_create_entity_nodes()` 会把分类写为 `['Entity', '<specific_type>']`
- `extraction_schemas.entity_types` JSONB 已支持自定义实体类型
- Memory Schema 的 ENTITIES 列已按 labels 分组

### 设计决策

1. **不新增 `entity_nodes.entity_type` 列**。`labels` 是实体类型的唯一事实来源；新增列会引入双写、迁移和跨数据库驱动同步成本。
2. **不修改 `extraction_schemas` 表结构**。现有 `entity_types` / `edge_types` / `custom_instructions` 已满足需求。
3. **不修改 LLM 输出 schema**。`ExtractedEntity.entity_type_id` 已存在，只需传入类型定义。
4. **LLM 自动分类为主，手动修正为辅**。提取时由 LLM 给出一个主类型；用户可在节点编辑中手动补充或修正 labels。
5. **未选择 schema 时注入内置默认分类**；选择自定义 schema 时优先使用自定义 `entity_types`。
6. **`Entity` 是兜底类型**。Memory Schema 不把它作为常规卡片，只有无具体分类的实体才显示在 `ENTITY` 卡中。

### 默认分类

建议内置以下通用分类：

| 类型 | 定义 | 典型示例 |
|------|------|---------|
| `Person` | 可明确指代的个人 | Jordan Lee、Nisha、Dr. Amara Osei |
| `Organization` | 公司、机构、团队、协会 | Acme Corp、Lockheed Martin、AAN |
| `Location` | 物理或虚拟地点 | Denver、Riverside Park、Belmont Arts Center |
| `Object` | 物理物品、工具、设备、所有物 | Gamecube、Ford Mustang、wool coat |
| `Document` | 文章、报告、邮件、视频、播客等信息内容 | Q3 report、API design doc |
| `Event` | 有名称或时间边界的事件 | product launch、onboarding session |
| `Topic` | 主题、爱好、知识领域 | road cycling、ceramics、machine learning |
| `Entity` | 兜底，仅无法归入上述类型时使用 | 其他可唯一识别的具体实体 |

`Project`、`Product`、`Preference` 等更适合作为领域自定义类型，不放进通用默认集，避免分类过散导致 LLM 误判。

### 提取链路

1. `server/graph_service/routers/ingest.py::_resolve_schema_params(None)` 返回内置 `DEFAULT_ENTITY_TYPES`，而不是 `(None, None, None)`。
2. 用户选择自定义 schema 时，仍从 `extraction_schemas` 读取并构建 Pydantic `entity_types`。
3. Graphiti 将默认类型或自定义类型注入 `entity_types_context`，LLM 为每个实体输出 `entity_type_id`。
4. `_create_entity_nodes()` 写入 `labels = ['Entity', '<specific_type>']`。
5. 去重/合并逻辑已支持从泛化节点提升到具体类型，无需额外改造。

### 前端与 API

- `GET /rest/memory-schema` 继续按 labels 分组，但过滤掉常规 `Entity` 标签。
- 只有 `labels == ['Entity']` 的节点进入 `ENTITY` 兜底卡。
- TYPES 列不展示 `Entity`，避免类型列表被基础标签占满。
- 节点编辑入口保留 labels 修改能力；后续可将逗号文本升级为分类选择器。

### 存量数据回填

存量 `['Entity']` 数据需要一次性回填：

1. 读取存量节点 `name`、`summary`、`attributes`。
2. 使用 LLM 按默认分类或所选 schema 输出具体类型。
3. 保留节点 UUID、embedding、关系和原始 summary，仅更新 `labels`。
4. 回填后可重新生成 Memory Schema 卡片分组。

回填应作为一次性维护任务，不随每次提取自动执行。

### 实施范围

- `server/graph_service/models.py`：新增 `DEFAULT_ENTITY_TYPES`
- `server/graph_service/routers/ingest.py`：`_resolve_schema_params()` 使用默认类型
- `server/graph_service/routers/graph.py`：Memory Schema 过滤 `Entity` 常规分组
- `web_service/components/ingest/node-edit-dialog.tsx`：可选升级为类型选择器
- 新增/补充测试：默认 schema 注入、提取 labels、Memory Schema 分组

### 验证

1. `schema_id=None` 时提取出的实体 labels 包含具体类型，不再全部是 `['Entity']`
2. 自定义 schema 优先于内置默认分类
3. Memory Schema 按 Person / Organization / Location / Object / Document / Event / Topic 生成多张卡
4. `['Entity', 'Person']` 只出现在 PERSON 卡，不重复出现在 ENTITY 卡
5. 仅有 `['Entity']` 的存量节点出现在 ENTITY 兜底卡
