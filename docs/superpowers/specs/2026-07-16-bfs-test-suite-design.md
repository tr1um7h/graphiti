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

**测试规模**：22 个用例，覆盖 primitive 契约（12 个）+ A/B 差分价值（10 个）。

---

## 2. 测试架构

混合策略（Hybrid），分两个测试文件：

| 文件 | 数量 | 目的 | 默认配置 |
|------|------|------|---------|
| `tests/search/test_bfs_primitives_int.py` | 12 | BFS 原语契约 | `BFS_ONLY_CONFIG`（仅 BFS） |
| `tests/search/test_bfs_value_int.py` | 10 | A/B 差分，证明 BFS 价值 | `BASELINE_CONFIG` vs `WITH_BFS_CONFIG` |

**合计 22 个测试用例**，全部为集成测试（`_int` 后缀），需 Postgres AGE 运行于 `localhost:55432`。

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

## 5. 测试用例清单（22 个）

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

### 5.2 `test_bfs_value_int.py`（10 个，A/B 差分）

每个测试对同一查询分别用 `BASELINE_CONFIG` 和 `WITH_BFS_CONFIG` 跑一次，断言差分。

| # | 测试函数 | 查询 | 断言（含数据验证） |
|---|---------|------|------|
| 13 | `test_bfs_recall_multi_hop_chain` | `"Alice 工作公司所在城市"` | WITH_BFS 返回的边含 LOCATED_IN (AcmeCorp→SF) 和 IN_COUNTRY (SF→USA)；BASELINE 不含；DB 回查确认这两条边的 source/target uuid 正确 |
| 14 | `test_bfs_recall_indirect_teammates` | `"LeadBob 的下属"` | WITH_BFS 返回 ≥3 条 MANAGES 边（target 覆盖 Carol/Dave/Eve）；BASELINE 返回 ≤1 |
| 15 | `test_bfs_does_not_cross_disconnected_clusters` | `"NodeA1 相关节点"` | WITH_BFS 结果中无 NodeB* 相关边；reference oracle 确认 Cluster A → Cluster B 无路径 |
| 16 | `test_bfs_recall_synonym_query` | `"Alice 的雇主"`（"雇主"不在节点文本中） | WITH_BFS 经 Alice 邻居扩展找到 AcmeCorp；BASELINE 未命中；DB 回查 WORKS_AT 边的 target==AcmeCorp_uuid |
| 17 | `test_bfs_recall_dense_cluster` | `"Q1"`（只命中 Q1 节点文本） | WITH_BFS 返回 Q1 的 4 条 LINKED 出边（target∈{Q2,Q3,Q4,Q5}）；BASELINE 返回 ≤1 |
| 18 | `test_bfs_auto_origin_fallback` | 链式查询，不传 origin | WITH_BFS 边数 > BASELINE 边数（验证 `search.py:332-353` 自动扩展路径） |
| 19 | `test_bfs_depth_3_vs_depth_1_recall_gap` | 链式查询 | 同为 WITH_BFS 配方，depth=3 能召回 USA；depth=1 不能 |
| 20 | `test_bfs_does_not_leak_across_groups_in_recipe` | 多组图，`group_ids=[G1]` | 完整 WITH_BFS 配方跑下来，结果中零条 G2 事实；每条返回边的 `group_id == G1` |
| 21 | `test_bfs_recall_with_temporal_filter` | `"OCCURRED_ON"` + `SearchFilters(valid_at=[[DateFilter(date=2022-01-01, comparison_operator=ComparisonOperator.greater_than)]])` | WITH_BFS 仅返回 NewEvent 边；OldEvent 边的 DB 真实 `valid_at=2020-01-01`，被过滤掉 |
| 22 | `test_bfs_multi_origin_convergence_dedup` | origin=[Alice, AcmeCorp] (chain) | depth=2 → 结果中 LOCATED_IN (AcmeCorp→SF) 只出现一次（SQL `DISTINCT` 生效）；每条边 uuid 唯一 |

---

## 6. Mock 使用清单

**原则**：除 Mock 表中列出的项，其余都是真实组件。

| Mock 对象 | 来源 | 用于何处 | 不调用原因 / 影响评估 |
|----------|------|---------|---------------------|
| `mock_embedder` | `tests/helpers_test.py:185`（已有，共享） | (a) seed 阶段：`node.generate_name_embedding(mock_embedder)`、`edge.generate_embedding(mock_embedder)`；(b) A/B 测试中 cosine 路径会调用 `embedder.create(query)` | (a) 必须 mock，否则真实调 OpenAI；(b) 向量是字典里的随机 384 维值，cosine 分数无意义。**正因如此，A/B 测试只断言召回（presence/absence），不断言排名**。 |
| Mock LLM client | `Mock(spec=LLMClient)`（参照 `tests/test_add_triplet.py:32-51`） | 仅用于实例化 `Graphiti`（构造函数必填参数） | 测试用 `EntityNode.save()` / `EntityEdge.save()` 直接写图，绕过 `add_episode` / `extract_entities` / `summarize` 等 LLM 调用路径 |
| Mock cross-encoder | `Mock(spec=CrossEncoderClient)`（参照 `tests/test_add_triplet.py:54-62`） | 仅用于实例化 `Graphiti` | 所有测试用 RRF reranker（纯算法），不触发 `cross_encoder.rank()` |

### 6.1 mock_embedder 字典扩展（不污染共享文件）

`tests/search/conftest.py` 用 fixture 局部扩展，不修改 `tests/helpers_test.py`：

```python
import tests.helpers_test as helpers

EXTRA_EMBEDDINGS = {
    "Alice 工作公司所在城市": [0.1] * 384,
    "LeadBob 的下属":         [0.2] * 384,
    "Alice 的雇主":           [0.3] * 384,
    "NodeA1 相关节点":        [0.4] * 384,
    "Q1":                     [0.5] * 384,
    # ... 其它查询字符串
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

### 6.2 真实组件（不 mock）

| 组件 | 真实性 | 说明 |
|------|-------|------|
| `graph_driver` (PostgresAgeDriver) | **真实** | 连接 `localhost:55432` 的 Postgres AGE |
| `EntityNode.save()` / `EntityEdge.save()` | **真实** | 写入真实 DB |
| BFS / BM25 / cosine 的 SQL/Cypher 查询 | **真实** | 跑在真实 Postgres 上 |
| `EntityEdge.get_by_uuid()` 回查 | **真实** | 用作数据验证 oracle |

### 6.3 不依赖的外部服务

- ❌ 不调 OpenAI / Anthropic / Gemini API
- ❌ 不调 OpenAI rerank API
- ❌ 不调任何 embedding API
- ✅ 仅依赖本地 Postgres AGE

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
- **episodic_edges 中转 BFS**：fixture 不含 episode 节点；测试 22 用例不覆盖"通过 episode 跨跳"路径，留待后续
- **property_filters**：Postgres AGE 实现抛 `NotImplementedError`（`search_ops.py:449`），不测
- **`_entity_link_search` 对比**：`chat.py:87` 的手工实体链接是不同机制，单独评估
- **真实 LLM 写入路径**：fixture 用 `EntityNode.save()` 直接写入，不走 `add_episode`
- **其它 driver（Neo4j / FalkorDB / Kuzu）**：只跑 Postgres AGE

---

## 9. 成功标准

- 22 个测试全部在 `ENABLE_POSTGRES_AGE=1 pytest tests/search/ -v` 下通过
- 关闭 Postgres 时，测试被正确 skip（而非报错）—— 复用 `pytest.importorskip('psycopg')` 模式
- 测试运行时间 < 60 秒（无真实模型调用，但 seed 多次 + DB 回查）
- `test_bfs_value_int.py` 的 10 个 A/B 测试中，至少 7 个能展示 WITH_BFS 严格优于 BASELINE 的召回差分（剩余允许"持平"）
- 每个测试都满足 §3.4 的三段式：act → assert-returned (字段全等 + DB 回查) → assert-completeness (reference oracle 对照)
