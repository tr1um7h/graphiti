# BFS 搜索测试套件设计文档

## 1. 背景与目标

Graphiti 当前的默认搜索配方（`COMBINED_HYBRID_SEARCH_RRF`）只启用 BM25 + 余弦相似度，不含 BFS。
`server/graph_service/routers/chat.py:22` 的 `CHAT_SEARCH_CONFIG` 同样如此。
项目内没有任何针对 BFS（`EdgeSearchMethod.bfs` / `NodeSearchMethod.bfs`）的测试覆盖。

**目标**：通过 pytest 集成测试，回答两个问题：

1. **正确性**：BFS 在显式起点（`bfs_origin_node_uuids`）、深度、limit、group 过滤、去重等契约上行为是否符合预期？
2. **价值**：在默认配方上追加 BFS，对多跳、邻居、稠密子图等查询能否提升召回？

不在本设计范围内的目标见 §6。

---

## 2. 测试架构

混合策略（Hybrid），分两个测试文件：

| 文件 | 数量 | 目的 | 默认配置 |
|------|------|------|---------|
| `tests/search/test_bfs_primitives_int.py` | 7 | BFS 原语契约 | `BFS_ONLY_CONFIG`（仅 BFS） |
| `tests/search/test_bfs_value_int.py` | 8 | A/B 差分，证明 BFS 价值 | `BASELINE_CONFIG` vs `WITH_BFS_CONFIG` |

**合计 15 个测试用例**，全部为集成测试（`_int` 后缀），需 Postgres AGE 运行于 `localhost:55432`。

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
    limit=10,
)

BFS_ONLY_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bfs],
        reranker=EdgeReranker.rrf,
    ),
    limit=10,
)
```

**reranker 选择理由**：全部使用 RRF，不使用 cross_encoder。原因：cross_encoder 会引入 rerank 模型变量，掩盖 BFS 本身的贡献；RRF 是纯排序算法，可隔离 BFS 效果。

### 2.2 复用既有基础设施

- `graph_driver` fixture（来自 `conftest.py:136`）—— 按 provider 参数化，测试前自动 `clear_data([group_id, group_id_2])`
- `mock_embedder`（来自 `tests/helpers_test.py:185`）—— 确定性向量字典
- mock LLM、mock cross-encoder —— 参照 `tests/test_add_triplet.py:32-62` 模式

**不调用任何真实模型**。A/B 测试只断言召回（presence/absence），不断言相似度排名，因此 mock embedder 的"无意义"向量不影响结论。

### 2.3 mock_embedder 扩展

A/B 测试中的查询字符串需要进入 `embeddings` 字典，否则 `mock_embedder.create()` 会 KeyError。
方案：在 `tests/search/conftest.py` 中通过 `monkeypatch` 给 `tests.helpers_test.embeddings` 追加测试专用的查询键（如 `"Alice 工作公司所在城市"`、`"LeadBob 的下属"` 等），映射到随机但确定的 384 维向量。

### 2.4 运行方式

```bash
# 前置：启动 Postgres AGE（已在 docker-compose 中）
ENABLE_POSTGRES_AGE=1 \
POSTGRES_AGE_DSN='postgresql://graphiti:graphiti@localhost:55432/graphiti' \
pytest tests/search/ -v
```

---

## 3. Fixture 图拓扑

每次测试前由 `seed_bfs_graph(driver) -> dict[str, str]`（返回 name→uuid 映射）播种。

### 3.1 主组 `graphiti_test_group`

**Chain（深度测试）**
```
Alice    --WORKS_AT-->    AcmeCorp
AcmeCorp --LOCATED_IN-->  SanFrancisco
SanFrancisco --IN_COUNTRY--> USA
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

### 3.2 副组 `graphiti_test_group_2`

仅镜像 Chain：
```
Alice2   --WORKS_AT-->    AcmeCorp2
AcmeCorp2 --LOCATED_IN--> SanFrancisco2
SanFrancisco2 --IN_COUNTRY--> USA2
```

### 3.3 UUID 确定性

所有节点用 `uuid.uuid5(uuid.NAMESPACE_DNS, f'{group_id}:{name}')` 生成，测试可用 name 反查 UUID 做断言。

---

## 4. 测试用例清单

### 4.1 `test_bfs_primitives_int.py`（7 个，BFS 原语）

| # | 测试函数 | 拓扑 | 断言 |
|---|---------|------|------|
| 1 | `test_bfs_explicit_origin_returns_direct_neighbors` | Star | `bfs_origin_node_uuids=[LeadBob]`, depth=1 → 结果正好包含 Carol/Dave/Eve 三条 MANAGES 边 |
| 2 | `test_bfs_depth_3_traverses_chain` | Chain | origin=Alice, depth=3 → 包含 AcmeCorp、SanFrancisco、USA 相关边 |
| 3 | `test_bfs_depth_1_excludes_far_nodes` | Chain | origin=Alice, depth=1 → USA 相关边不在结果中 |
| 4 | `test_bfs_empty_origin_returns_empty` | 任意 | `bfs_origin_node_uuids=[]` → 边结果为空列表 |
| 5 | `test_bfs_respects_group_filter` | Chain ×2 | 在 G1 内 origin=Alice → 结果中无任何 G2 UUID |
| 6 | `test_bfs_honors_limit` | Star + Clique Q | limit=3, origin=LeadBob+Q1 → 返回边数 ≤ 3 |
| 7 | `test_bfs_dedups_uuids` | Star | origin=[LeadBob, LeadBob]（重复）→ 结果 UUID 唯一 |

### 4.2 `test_bfs_value_int.py`（8 个，A/B 差分）

每个测试对同一查询分别用 `BASELINE_CONFIG` 和 `WITH_BFS_CONFIG` 跑一次，断言差分。

| # | 测试函数 | 查询 | 断言 |
|---|---------|------|------|
| 8 | `test_bfs_recall_multi_hop_chain` | `"Alice 工作公司所在城市"` | WITH_BFS 返回的边含 SanFrancisco / USA；BASELINE 不含 |
| 9 | `test_bfs_recall_indirect_teammates` | `"LeadBob 的下属"` | WITH_BFS 返回 ≥3 条 MANAGES 边；BASELINE 返回 ≤1 |
| 10 | `test_bfs_does_not_cross_disconnected_clusters` | `"NodeA1 相关节点"` | WITH_BFS 结果中无 NodeB* 相关边 |
| 11 | `test_bfs_recall_synonym_query` | `"Alice 的雇主"`（"雇主"不在节点文本中） | WITH_BFS 经 Alice 邻居扩展找到 AcmeCorp；BASELINE 未命中 |
| 12 | `test_bfs_recall_dense_cluster` | `"Q1"`（只命中 Q1 节点文本） | WITH_BFS 返回 5 个 Q 节点相关边；BASELINE 返回 1 |
| 13 | `test_bfs_auto_origin_fallback` | 链式查询，不传 origin | WITH_BFS 边数 > BASELINE 边数（验证 `search.py:332-353` 自动扩展路径） |
| 14 | `test_bfs_depth_3_vs_depth_1_recall_gap` | 链式查询 | 同为 WITH_BFS 配方，depth=3 能召回 USA；depth=1 不能 |
| 15 | `test_bfs_does_not_leak_across_groups_in_recipe` | 多组图，`group_ids=[G1]` | 完整配方跑下来，结果中零条 G2 事实 |

---

## 5. 实现注意事项

### 5.1 测试入口 API

统一使用 `Graphiti.search_()`（`graphiti.py:1875`）—— 它已暴露 `config`、`group_ids`、`bfs_origin_node_uuids`、`center_node_uuid`、`search_filter` 全部参数，转发到 `graphiti_core.search.search.search()`。无需手工构造 `GraphitiClients`。

```python
results = await graphiti.search_(
    query="Alice 工作公司所在城市",
    config=WITH_BFS_CONFIG,
    group_ids=[group_id],
    bfs_origin_node_uuids=[alice_uuid],   # 仅 primitive 测试显式传
)
# results.edges / results.nodes / results.episodes / results.communities
```

### 5.2 mock_embedder 的扩展方式

不要修改 `tests/helpers_test.py`（共享文件，影响其它测试）。在 `tests/search/conftest.py` 中：

```python
import tests.helpers_test as helpers

EXTRA_EMBEDDINGS = {
    "Alice 工作公司所在城市": [...384-dim random...],
    "LeadBob 的下属": [...],
    # ...
}

@pytest.fixture(autouse=True)
def extend_embedder():
    saved = dict(helpers.embeddings)
    helpers.embeddings.update(EXTRA_EMBEDDINGS)
    yield
    helpers.embeddings.clear()
    helpers.embeddings.update(saved)
```

### 5.3 seed 辅助函数

`seed_bfs_graph(driver)` 内部用 `EntityNode.save(driver)` 和 `EntityEdge.save(driver)`，不走 LLM 抽取。
节点 `name_embedding` 与边 `fact_embedding` 在 save 前用 `mock_embedder` 生成。

### 5.4 已知边界

- Postgres AGE 的 BFS 实现（`edge_bfs_search` / `node_bfs_search` 在 `search_utils.py`）使用 Cypher 变量路径 `(n)-[*1..{depth}]-(m)`。如果 Postgres AGE 对变长路径的支持有差异，测试会暴露。
- `MAX_SEARCH_DEPTH=3` 是 `search_utils.py:67` 的默认值，本设计的深度相关测试用 1 和 3，不测超过 3 的情况。

---

## 6. 不在范围内

- **性能基准**：不测 BFS 延迟/吞吐
- **cross_encoder 配方**：不测 `COMBINED_HYBRID_SEARCH_CROSS_ENCODER`（隔离变量）
- **Node-search BFS**：`node_search` 的 BFS 代码路径与 edge 对称，可在后续追加
- **`_entity_link_search` 对比**：`chat.py:87` 的手工实体链接是不同机制，单独评估
- **真实 LLM 写入路径**：fixture 用 `EntityNode.save()` 直接写入，不走 `add_episode`

---

## 7. 成功标准

- 15 个测试全部在 `ENABLE_POSTGRES_AGE=1 pytest tests/search/ -v` 下通过
- 关闭 Postgres 时，测试被正确 skip（而非报错）
- 测试运行时间 < 30 秒（无真实模型调用）
- `test_bfs_value_int.py` 的 8 个 A/B 测试中，至少 6 个能展示 WITH_BFS 严格优于 BASELINE 的召回差分（剩余 2 个允许"持平"，反映 BFS 不是万能）
