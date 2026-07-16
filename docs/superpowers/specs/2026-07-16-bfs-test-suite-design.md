# BFS 搜索测试套件设计文档

## 1. 背景与目标

Graphiti 当前的默认搜索配方（`COMBINED_HYBRID_SEARCH_RRF`）只启用 BM25 + 余弦相似度，不含 BFS。
`server/graph_service/routers/chat.py:22` 的 `CHAT_SEARCH_CONFIG` 同样如此。
项目内没有任何针对 BFS（`EdgeSearchMethod.bfs` / `NodeSearchMethod.bfs`）的测试覆盖。

**目标**：通过 pytest 集成测试，回答三个问题：

1. **正确性**：BFS 在显式起点、深度边界、limit、group 过滤、edge_types/日期过滤、方向性等契约上行为是否符合预期？
2. **价值**：在默认配方上追加 BFS，对多跳、邻居、稠密子图等查询能否提升召回？
3. **数据真实性**：返回的每条边/节点是否真的对应底层 graph 中存在的记录（而非表层 API 文本）？

不在本设计范围内的目标见 §8。

**测试规模**：23 个用例，覆盖 primitive 契约（12 个）+ A/B 差分价值（11 个）。

**Embedder 策略**（详见 §6）：**部分 mock、部分真实 OpenAI 调用**——
- 12 个 primitive + 7 个仅校验 presence/过滤器 的 A/B 测试用 `mock_embedder`（快、无网络、确定性）
- 4 个**语义类**A/B 测试（#13, #16, #17, #23）**必须**使用 real `OpenAIEmbedder`，因为它们的价值在于验证"BFS 救回 cosine 漏召的语义近邻"，mock 向量使 cosine 通路形同虚设，A/B 失去科学性

---

## 2. 测试架构

混合策略（Hybrid），分两个测试文件：

| 文件 | 数量 | 目的 | 默认配置 |
|------|------|------|---------|
| `tests/search/test_bfs_primitives_int.py` | 12 | BFS 原语契约 | `BFS_ONLY_CONFIG`（仅 BFS） |
| `tests/search/test_bfs_value_int.py` | 11 | A/B 差分，证明 BFS 价值 | `BASELINE_CONFIG` vs `WITH_BFS_CONFIG` |

**合计 23 个测试用例**，全部为集成测试（`_int` 后缀），需 Postgres AGE 运行于 `localhost:55432`；其中 4 个另需 `OPENAI_API_KEY`（详见 §6）。

### 2.1 三个 SearchConfig（定义在 `tests/search/conftest.py`）

```python
BASELINE_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bm25, EdgeSearchMethod.cosine_similarity],
        reranker=EdgeReranker.rrf,
        sim_min_score=0.2,
    ),
    limit=10,
)

WITH_BFS_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[
            EdgeSearchMethod.bm25,
            EdgeSearchMethod.cosine_similarity,
            EdgeSearchMethod.bfs,
        ],
        reranker=EdgeReranker.rrf,
        sim_min_score=0.2,
        bfs_max_depth=3,
    ),
    node_config=NodeSearchConfig(
        search_methods=[
            NodeSearchMethod.bm25,
            NodeSearchMethod.cosine_similarity,
            NodeSearchMethod.bfs,
        ],
        reranker=NodeReranker.rrf,
        sim_min_score=0.2,
        bfs_max_depth=3,
    ),
    limit=10,
)

BFS_ONLY_EDGE_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bfs],
        reranker=EdgeReranker.rrf,
    ),
    limit=10,
)

BFS_ONLY_NODE_CONFIG = SearchConfig(
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.bfs],
        reranker=NodeReranker.rrf,
    ),
    limit=10,
)
```

**reranker 选择理由**：全部使用 RRF，不使用 cross_encoder。原因：cross_encoder 会引入 rerank 模型变量，掩盖 BFS 本身的贡献；RRF 是纯排序算法，可隔离 BFS 效果。

### 2.2 运行方式

```bash
# 前置：启动 Postgres AGE（已在 docker-compose 中）
ENABLE_POSTGRES_AGE=1 \
POSTGRES_AGE_DSN='postgresql://graphiti:graphiti@localhost:55432/graphiti' \
pytest tests/search/ -v
```

---

## 3. 底层数据验证原则（核心）

**禁止**只断言表面字段（如 `"Alice" in [e.name for e in results]`）。
**必须**对返回的每条边/节点做以下至少一项深度校验：

### 3.1 字段全等校验

每条返回的边都对齐到 seed 时的 ground truth：

```python
SEED_EDGES = {
    'Alice_WORKS_AT_AcmeCorp': EntityEdge(
        uuid=uuid5(NAMESPACE, f'{group_id}:Alice:WORKS_AT:AcmeCorp'),
        source_node_uuid=SEED_NODES['Alice'].uuid,
        target_node_uuid=SEED_NODES['AcmeCorp'].uuid,
        name='WORKS_AT',
        fact='Alice works at AcmeCorp',
        group_id=group_id,
        created_at=FIXED_NOW,
        episodes=[],
    ),
    # ...
}

def assert_edge_matches_seed(returned: EntityEdge, expected_key: str):
    expected = SEED_EDGES[expected_key]
    assert returned.uuid == expected.uuid
    assert returned.source_node_uuid == expected.source_node_uuid
    assert returned.target_node_uuid == expected.target_node_uuid
    assert returned.name == expected.name
    assert returned.fact == expected.fact
    assert returned.group_id == expected.group_id
```

### 3.2 回查数据库校验

返回的 edge 必须在 DB 中真实存在且字段一致：

```python
async def assert_edge_in_db(driver, returned_uuid: str, expected_key: str):
    db_edge = await EntityEdge.get_by_uuid(driver, returned_uuid)
    assert db_edge is not None, f'edge {returned_uuid} not in DB'
    expected = SEED_EDGES[expected_key]
    assert db_edge.source_node_uuid == expected.source_node_uuid
    assert db_edge.target_node_uuid == expected.target_node_uuid
    assert db_edge.group_id == expected.group_id
```

### 3.3 反向校验

对于"不应出现"的断言，不仅要查返回列表，还要查 DB 中的真实关系：

```python
# 反例：仅断言返回列表中没有
assert 'SanFrancisco' not in [e.name for e in results.edges]  # ❌ 表面

# 正例：先查 DB 确认该边确实不属于本次 BFS 应到达的范围
sf_uuid = SEED_NODES['SanFrancisco'].uuid
reachable = await compute_bfs_reachable_uuids(driver, origin=alice_uuid, depth=1)
assert sf_uuid not in reachable  # ✓ 基于真实图拓扑
```

`compute_bfs_reachable_uuids` 是测试 helper：直接用 Cypher 跑一遍独立的最短路径查询，作为 reference 实现，与 `edge_bfs_search` 的输出对照（参考 oracle）。

### 3.4 每个测试的强制三段式

```python
async def test_xxx(driver, seeded_graph):
    # 1. Act: 调 search
    results = await driver.search_ops.edge_bfs_search(...)
    
    # 2. Assert-returned: 每条返回的边字段全等 + 回查 DB
    for edge in results:
        key = identify_seed_key(edge)  # 反查 SEED_EDGES
        await assert_edge_matches_seed(edge, key)
        await assert_edge_in_db(driver, edge.uuid, key)
    
    # 3. Assert-completeness: 对比 reference 实现，确认应到未到 / 不应到未到
    expected_uuids = await reference_bfs(driver, origin, depth)
    returned_uuids = {e.uuid for e in results}
    assert returned_uuids <= expected_uuids  # 不超出
    # 若测试目标是"完整召回"，再加：assert expected_uuids <= returned_uuids
```

---

## 4. Fixture 图拓扑

每次测试前由 `seed_bfs_graph(driver) -> dict[str, UUID]`（返回 name→uuid 映射）播种。

### 4.1 主组 `graphiti_test_group`

**Chain（深度测试，3 跳 4 边）**
```
Alice    --WORKS_AT-->    AcmeCorp
AcmeCorp --LOCATED_IN-->  SanFrancisco
SanFrancisco --IN_COUNTRY--> USA
```

**反向链（方向性测试，证明 BFS 只走出边）**
```
SinkX --BELONGS_TO--> MidY --PART_OF--> TopZ
# TopZ 没有出边 → BFS from TopZ 必须返回空
```

**Star（邻居扩展测试）**
```
LeadBob --MANAGES--> EmpCarol
LeadBob --MANAGES--> EmpDave
LeadBob --MANAGES--> EmpEve
```

**Cluster A（3-clique，与其它子图不连通）**
```
NodeA1 --RELATED--> NodeA2 --RELATED--> NodeA3 --RELATED--> NodeA1
```

**Cluster B（3-clique，与 Cluster A 不连通）**
```
NodeB1 --RELATED--> NodeB2 --RELATED--> NodeB3 --RELATED--> NodeB1
```

**Clique Q（5-clique，稠密子图测试）**
```
Q1, Q2, Q3, Q4, Q5 之间两两 --LINKED--> 连接（共 10 条边）
```

**Temporal（时间过滤测试）**
```
OldEvent --OCCURRED_ON--> 2020-01-01  (valid_at=2020-01-01, expired_at=2020-12-31)
NewEvent --OCCURRED_ON--> 2025-01-01  (valid_at=2025-01-01, expired_at=None)
```

**Salary（语义漏召测试，#23 专用）**
```
Alice --HAS_SALARY--> SalaryNode   (SalaryNode.summary = "monthly compensation amount in USD")
```
注意：Alice 与 SalaryNode 在文本上 lexical gap 大（query "薪水数额" vs 节点名 "SalaryNode"），
正是用来验证 BFS 能否补偿真实 cosine 的语义漏召。

### 4.2 副组 `graphiti_test_group_2`

镜像 Chain + 反向链：
```
Alice2   --WORKS_AT-->    AcmeCorp2 --LOCATED_IN--> SanFrancisco2 --IN_COUNTRY--> USA2
SinkX2   --BELONGS_TO-->  MidY2     --PART_OF-->   TopZ2
```

### 4.3 UUID 确定性

所有节点用 `uuid.uuid5(uuid.NAMESPACE_DNS, f'{group_id}:{name}')` 生成。
所有边用 `uuid.uuid5(uuid.NAMESPACE_DNS, f'{group_id}:{src_name}:{edge_name}:{dst_name}')` 生成。
测试用 name 反查 UUID 做断言；seed 后返回 `{name: uuid}` 与 `{edge_key: uuid}` 两个映射。

---

## 5. 测试用例清单（23 个）

### 5.1 `test_bfs_primitives_int.py`（12 个，BFS 原语契约）

| # | 测试函数 | 拓扑 | 断言（含数据验证） |
|---|---------|------|------|
| 1 | `test_bfs_explicit_origin_returns_direct_neighbors` | Star | origin=LeadBob, depth=1 → 返回 3 条 MANAGES 边；每条边 `source==LeadBob_uuid`、`target∈{Carol,Dave,Eve}_uuid`、`group_id==G1`；DB 回查一致 |
| 2 | `test_bfs_depth_3_traverses_full_chain` | Chain | origin=Alice, depth=3 → 返回 WORKS_AT + LOCATED_IN + IN_COUNTRY 共 3 条边；按 source_uuid 排序后深度依次为 0/1/2 |
| 3 | `test_bfs_depth_1_excludes_far_nodes` | Chain | origin=Alice, depth=1 → 仅 WORKS_AT；reference oracle 确认 LOCATED_IN / IN_COUNTRY 不在 1 跳可达集 |
| 4 | `test_bfs_empty_origin_returns_empty` | 任意 | `bfs_origin_node_uuids=[]` → 返回空列表；不抛错 |
| 5 | `test_bfs_none_origin_returns_empty` | 任意 | `bfs_origin_node_uuids=None` → 返回空列表（`search_ops.py:194` 早退） |
| 6 | `test_bfs_depth_0_raises_value_error` | 任意 | `max_depth=0` → 抛 `ValueError('max_depth must be between 1 and 5')`（`search_ops.py:531`） |
| 7 | `test_bfs_depth_6_raises_value_error` | 任意 | `max_depth=6` → 抛 `ValueError` |
| 8 | `test_bfs_directed_no_outgoing_returns_empty` | 反向链 | origin=TopZ（无出边）, depth=3 → 返回空；证明 BFS 是 directed（仅出边扩展） |
| 9 | `test_bfs_directed_reverse_traversal_excluded` | Chain | origin=AcmeCorp, depth=2 → 仅返回 LOCATED_IN (AcmeCorp→SF)；WORKS_AT (Alice→AcmeCorp) **不**在结果中（BFS 不做反向遍历）；reference oracle 确认 Alice 不可达 |
| 10 | `test_bfs_respects_group_filter_walk_only` | Chain ×2 group | origin=Alice (G1), depth=3, group_ids=[G1] → 返回边数=3；reference oracle 确认 G2 的 4 条边均不在 G1 内 BFS 的可达集 |
| 11 | `test_bfs_honors_edge_types_filter` | Chain + Star | origin=Alice, depth=3, `edge_types=['WORKS_AT']` → 仅返回 WORKS_AT 边；MANAGES/LOCATED_IN 被过滤 |
| 12 | `test_bfs_node_search_excludes_origin` | Chain | `BFS_ONLY_NODE_CONFIG`, origin=Alice, depth=3 → 返回 AcmeCorp/SF/USA 节点；**Alice 自身的 uuid 不在结果中**（对照 `node_bfs` 过滤 `walk.depth > 0` 与 `edge_bfs` 过滤 `walk.depth < max_depth` 的语义差异） |

### 5.2 `test_bfs_value_int.py`（11 个，A/B 差分）

每个测试对同一查询分别用 `BASELINE_CONFIG` 和 `WITH_BFS_CONFIG` 跑一次，断言差分。
**Embedder 列**：M = `mock_embedder`；**R = real `OpenAIEmbedder`**（需 `OPENAI_API_KEY`）。

| # | 测试函数 | Embedder | 查询 | 断言（含数据验证） |
|---|---------|---------|------|------|
| 13 | `test_bfs_recall_multi_hop_chain` | **R** | `"Alice 工作公司所在城市"` | WITH_BFS 返回的边含 LOCATED_IN (AcmeCorp→SF) 和 IN_COUNTRY (SF→USA)；BASELINE 不含；DB 回查确认这两条边的 source/target uuid 正确 |
| 14 | `test_bfs_recall_indirect_teammates` | M | `"LeadBob 的下属"` | WITH_BFS 返回 ≥3 条 MANAGES 边（target 覆盖 Carol/Dave/Eve）；BASELINE 返回 ≤1 |
| 15 | `test_bfs_does_not_cross_disconnected_clusters` | M | `"NodeA1 相关节点"` | WITH_BFS 结果中无 NodeB* 相关边；reference oracle 确认 Cluster A → Cluster B 无路径 |
| 16 | `test_bfs_recall_synonym_query` | **R** | `"Alice 的雇主"`（"雇主"不在节点文本中） | WITH_BFS 经 Alice 邻居扩展找到 AcmeCorp；BASELINE 在真实 cosine 下也未命中（验证 BFS 补偿了 cosine 的词汇差距）；DB 回查 WORKS_AT 边的 target==AcmeCorp_uuid |
| 17 | `test_bfs_recall_dense_cluster` | **R** | `"Q1"`（只命中 Q1 节点文本） | WITH_BFS 返回 Q1 的 4 条 LINKED 出边（target∈{Q2,Q3,Q4,Q5}）；BASELINE 在真实 cosine 下仅返回 Q1 自身相关边 |
| 18 | `test_bfs_auto_origin_fallback` | M | 链式查询，不传 origin | WITH_BFS 边数 > BASELINE 边数（验证 `search.py:332-353` 自动扩展路径） |
| 19 | `test_bfs_depth_3_vs_depth_1_recall_gap` | M | 链式查询 | 同为 WITH_BFS 配方，depth=3 能召回 USA；depth=1 不能 |
| 20 | `test_bfs_does_not_leak_across_groups_in_recipe` | M | 多组图，`group_ids=[G1]` | 完整 WITH_BFS 配方跑下来，结果中零条 G2 事实；每条返回边的 `group_id == G1` |
| 21 | `test_bfs_recall_with_temporal_filter` | M | `"OCCURRED_ON"` + `SearchFilters(valid_at=[[DateFilter(date=2022-01-01, comparison_operator=ComparisonOperator.greater_than)]])` | WITH_BFS 仅返回 NewEvent 边；OldEvent 边的 DB 真实 `valid_at=2020-01-01`，被过滤掉 |
| 22 | `test_bfs_multi_origin_convergence_dedup` | M | origin=[Alice, AcmeCorp] (chain) | depth=2 → 结果中 LOCATED_IN (AcmeCorp→SF) 只出现一次（SQL `DISTINCT` 生效）；每条边 uuid 唯一 |
| 23 | `test_bfs_recovers_semantic_miss` | **R** | `"Alice 的薪水数额"`（fixture 里 Alice 的邻居 SalaryNode 持有薪水边，但 query 词与节点文本 lexical gap 大） | BASELINE (real cosine) 在 `sim_min_score=0.4` 下漏召 SalaryNode 相关边；WITH_BFS 经 Alice→SalaryNode 一跳召回；DB 回查 salary 边的 source/target 真实存在 |

---

## 6. Embedder 与 Mock 策略

**核心原则**：embedder 按测试目的**显式拆分**——primitive 与 presence-only 类用 mock，语义类用 real。其余依赖（LLM、cross-encoder）一律 mock。

### 6.1 测试 × Embedder 矩阵

| 测试编号 | Embedder | 测试目的 | 为什么这个选择 |
|---------|---------|---------|--------------|
| #1–#12 (primitives) | `mock_embedder` | BFS 契约（深度/limit/方向/过滤器） | BFS-only 配置不触发 cosine；即使触发，断言只看 presence 与字段，与向量语义无关 |
| #13 多跳链 | **real** | 验证 BFS 补回多跳语义链路 | query 是自然语言中文，cosine 通路必须用真实向量才能反映"BASELINE 是否真能命中"——否则 mock 下 BASELINE 漏召只是随机 |
| #14 indirect teammates | `mock_embedder` | 验证 BFS 扩展邻居 | 只校验 MANAGES 边的 presence + target_uuid，与语义无关 |
| #15 跨 cluster 隔离 | `mock_embedder` | 验证 BFS 不跨界 | 只校验 NodeB* 不出现 |
| #16 同义词 query | **real** | 验证 BFS 补偿 cosine 词汇差距 | "雇主" vs "WORKS_AT" 的语义匹配是测试核心；mock 下 cosine 失效，"BASELINE 漏召"无意义 |
| #17 dense cluster | **real** | 验证 BFS 扩展稠密子图 | "Q1" 与 Q2..Q5 的语义相关性需要真实向量；mock 下结果随机 |
| #18 auto-origin fallback | `mock_embedder` | 验证自动 origin 路径 | 只看边数差 |
| #19 depth 3 vs 1 | `mock_embedder` | 验证深度边界 | 只看 presence |
| #20 跨 group 隔离 | `mock_embedder` | 验证 group filter | 只看 group_id |
| #21 时间过滤 | `mock_embedder` | 验证 valid_at filter | 只看时间字段 |
| #22 多 origin 去重 | `mock_embedder` | 验证 SQL DISTINCT | 只看 uuid 唯一性 |
| #23 语义漏召补偿 | **real** | 验证 BFS 救回 cosine 漏召 | 测试**核心**就是真实 cosine 漏召 + BFS 补回；mock 直接毁掉测试 |

**统计**：23 个测试中，**19 个用 mock_embedder，4 个用 real `OpenAIEmbedder`**（#13, #16, #17, #23）。

### 6.2 Mock 清单（除 embedder 外）

| Mock 对象 | 来源 | 用于何处 | 不调用原因 |
|----------|------|---------|-----------|
| Mock LLM client | `Mock(spec=LLMClient)`（参照 `tests/test_add_triplet.py:32-51`） | 仅用于实例化 `Graphiti`（构造函数必填参数） | 测试用 `EntityNode.save()` / `EntityEdge.save()` 直接写图，绕过 `add_episode` / `extract_entities` / `summarize` |
| Mock cross-encoder | `Mock(spec=CrossEncoderClient)`（参照 `tests/test_add_triplet.py:54-62`） | 仅用于实例化 `Graphiti` | 所有测试用 RRF reranker（纯算法），不触发 `cross_encoder.rank()` |

### 6.3 Real `OpenAIEmbedder` 接入

4 个语义类测试（#13, #16, #17, #23）需在 fixture 中构造真实 embedder：

```python
# tests/search/conftest.py
import os
import pytest
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

@pytest.fixture
def real_embedder():
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip('OPENAI_API_KEY not set; skipping real-embedder BFS tests')
    return OpenAIEmbedder(config=OpenAIEmbedderConfig(embedding_dim=384))
```

**关键约束**：
- 真实 embedder fixture **只**赋给 #13/#16/#17/#23 对应的 `Graphiti` 实例；其余 19 个测试继续用 `mock_embedder`
- seed 阶段也跟着切换：用 real embedder 测的 4 个 case，节点的 `name_embedding` 与边的 `fact_embedding` 必须用 real embedder 生成（保证 cosine 索引里的向量与 query 向量在同一语义空间）；mock 测的 case 用 mock embedder 生成 seed 向量
- 真实 embedder 默认模型 `text-embedding-3-small`，维度 384（与 Postgres AGE fixture 配置一致）
- 单次测试约增加 100–300 ms（embed query + seed embeddings），4 个测试合计 < 2 秒

### 6.4 mock_embedder 字典扩展（不污染共享文件）

`tests/search/conftest.py` 用 fixture 局部扩展，不修改 `tests/helpers_test.py`：

```python
import tests.helpers_test as helpers

EXTRA_EMBEDDINGS = {
    "LeadBob 的下属":         [0.2] * 384,
    "NodeA1 相关节点":        [0.4] * 384,
    "OCCURRED_ON":            [0.6] * 384,
    # mock 测试用的查询字符串；语义类测试的 query 不在此列（它们走 real embedder）
}

@pytest.fixture(autouse=True)
def extend_embedder():
    saved = dict(helpers.embeddings)
    helpers.embeddings.update(EXTRA_EMBEDDINGS)
    try:
        yield
    finally:
        helpers.embeddings.clear()
        helpers.embeddings.update(saved)
```

### 6.5 真实组件（不 mock）

| 组件 | 真实性 | 说明 |
|------|-------|------|
| `graph_driver` (PostgresAgeDriver) | **真实** | 连接 `localhost:55432` 的 Postgres AGE |
| `EntityNode.save()` / `EntityEdge.save()` | **真实** | 写入真实 DB |
| BFS / BM25 / cosine 的 SQL 查询 | **真实** | 跑在真实 Postgres 上 |
| `OpenAIEmbedder`（仅 #13/#16/#17/#23） | **真实** | 调 OpenAI `text-embedding-3-small` |
| `EntityEdge.get_by_uuid()` 回查 | **真实** | 用作数据验证 oracle |

### 6.6 外部服务依赖

- ❌ 不调任何 LLM API（OpenAI chat / Anthropic / Gemini）
- ❌ 不调 OpenAI rerank API
- ✅ 19 个测试仅依赖本地 Postgres AGE
- ✅ 4 个语义类测试额外依赖 `OPENAI_API_KEY`（缺失时 `pytest.skip`，不报错）

---

## 7. 实现注意事项

### 7.1 测试入口 API

统一使用 `Graphiti.search_()`（`graphiti.py:1875`）—— 它已暴露 `config`、`group_ids`、`bfs_origin_node_uuids`、`center_node_uuid`、`search_filter` 全部参数，转发到 `graphiti_core.search.search.search()`。

```python
results = await graphiti.search_(
    query="Alice 工作公司所在城市",
    config=WITH_BFS_CONFIG,
    group_ids=[group_id],
    bfs_origin_node_uuids=[alice_uuid],   # primitive 测试显式传
)
# results.edges / results.nodes / results.episodes / results.communities
```

如需直接测 Postgres AGE 的 BFS 实现（绕过 search.py 调度），用：
```python
await driver.search_ops.edge_bfs_search(
    executor=driver, origin_uuids=[...], max_depth=3,
    search_filter=SearchFilters(), group_ids=[group_id], limit=10,
)
```

### 7.2 reference oracle helper

`tests/search/helpers.py` 中提供独立实现的 BFS 参考，作为对照：

```python
async def reference_bfs_reachable_edges(
    driver, origin_uuids: list[str], max_depth: int, group_ids: list[str] | None
) -> set[str]:
    """独立 Cypher 实现，作为 edge_bfs_search 的对照 oracle。
    有意写得比实现更直白，避免与被测代码同源。"""
    # 用 ag_catalog.cypher 跑等价的变长路径查询
    # 返回可达边的 uuid 集合
```

oracle 与被测实现共用 SQL 并不违反原则——它是 Postgres AGE 自己的 Cypher 路径语义，与 Python 实现 `edge_bfs_search` 是两套独立代码路径。

### 7.3 seed 辅助函数

`seed_bfs_graph(driver)` 内部用 `EntityNode.save(driver)` 和 `EntityEdge.save(driver)`，**不走** LLM 抽取。节点 `name_embedding` 与边 `fact_embedding` 在 save 前用 `mock_embedder` 生成。

### 7.4 已知边界

- `_validate_bfs_depth`（`search_ops.py:531`）只允许 `1 ≤ depth ≤ 5`
- BFS 是 **directed**：仅沿 `source → target` 方向扩展 walk
- BFS 同时 walk `entity_edges` 和 `episodic_edges`（后者用于 episode 中转，本套测试不覆盖 episodic 路径——见 §8）
- `edge_bfs` 最终过滤 `walk.depth < max_depth`（含 origin 出边）；`node_bfs` 过滤 `walk.depth > 0`（不含 origin）
- `walk_group_ids` 不仅过滤最终结果，也限制 walk 本身（`search_ops.py:220-223`）—— 组隔离在 walk 层就生效

---

## 8. 不在范围内

- **性能基准**：不测 BFS 延迟/吞吐
- **cross_encoder 配方**：不测 `COMBINED_HYBRID_SEARCH_CROSS_ENCODER`（隔离变量）
- **episodic_edges 中转 BFS**：fixture 不含 episode 节点；测试 23 用例不覆盖"通过 episode 跨跳"路径，留待后续
- **property_filters**：Postgres AGE 实现抛 `NotImplementedError`（`search_ops.py:449`），不测
- **`_entity_link_search` 对比**：`chat.py:87` 的手工实体链接是不同机制，单独评估
- **真实 LLM 写入路径**：fixture 用 `EntityNode.save()` 直接写入，不走 `add_episode`
- **其它 driver（Neo4j / FalkorDB / Kuzu）**：只跑 Postgres AGE

---

## 9. 成功标准

- 23 个测试全部在 `ENABLE_POSTGRES_AGE=1 OPENAI_API_KEY=sk-... pytest tests/search/ -v` 下通过
- 关闭 Postgres 时，全部测试被正确 skip（而非报错）—— 复用 `pytest.importorskip('psycopg')` 模式
- 缺失 `OPENAI_API_KEY` 时，**4 个 real-embedder 测试（#13/#16/#17/#23）被 skip**，其余 19 个照常通过——验证 mock/real 两条路径独立可跑
- 测试运行时间：mock-only 测试 < 60 秒；4 个 real 测试合计 < 5 秒（含 OpenAI 往返）
- `test_bfs_value_int.py` 的 11 个 A/B 测试中，至少 8 个能展示 WITH_BFS 严格优于 BASELINE 的召回差分（剩余允许"持平"）
- 每个测试都满足 §3.4 的三段式：act → assert-returned (字段全等 + DB 回查) → assert-completeness (reference oracle 对照)
