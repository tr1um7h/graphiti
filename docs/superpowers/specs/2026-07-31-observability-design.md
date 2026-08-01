# Graphiti 可观测性设计

> 状态：草案 v2（经架构评审修订）
> 创建日期：2026-07-31
> 最后修订：2026-08-01
> 作者：Claude + User

## 1. 概述

### 1.1 目标

为 Graphiti 建立完整的可观测性体系，支持：
- **业务分析**：用户使用模式、功能热度、LLM token 消耗分析
- **性能优化**：识别慢查询、优化瓶颈，为火焰图做准备

### 1.2 范围与关键决策

| 维度 | 选择 | 说明 |
|------|------|------|
| 主要场景 | 业务分析 + 性能优化 | — |
| 监控范围 | 全链路追踪 + metrics 低基数 | metrics 严格遵循低基数原则（见 §5.4） |
| 指标持久化 | GreptimeDB 统一存储 | metrics + traces + logs 暂全部落 GreptimeDB |
| Trace 后端 | GreptimeDB（当前唯一 trace 后端） | Trace Explorer 以 SQL 查询 `opentelemetry_traces` 表为主；Jaeger/Tempo 不作为默认依赖，如需原生瀑布图可按计划文档附录配置（见 §11.4） |
| 火焰图 | 按需触发 profiling（类似 pprof） | 生产环境需鉴权（见 §7） |
| 用户维度 | 预留 `user_id`（默认 `anonymous`），当前只有 `group_id` | `user_id` 仅出现在 traces/logs 的 span attributes，**不进入 metrics 标签** |
| 与现有代码关系 | 扩展现有 `tracer.py` 抽象 | 不另起炉灶（见 §2.3） |

### 1.3 技术栈

| 组件 | 技术选型 |
|------|----------|
| 前端 OTEL | @opentelemetry/web（Phase 6 可选，非首要） |
| 后端 OTEL | opentelemetry-sdk (Python) |
| Collector | otelcol-contrib |
| 存储 | GreptimeDB v1.1+ |
| 可视化 | Grafana v11+ |
| 部署 | Docker Compose |

> **组件边界（当前已确认）**：架构只依赖 GreptimeDB + OTLP Collector + Grafana。Jaeger、Tempo、Loki 均不是必需组件：
> - GreptimeDB 通过 OTLP 同时接收 traces、metrics、logs
> - traces 写入依赖 GreptimeDB 内置 pipeline `greptime_trace_v1`（见 §8.2）
> - logs 在 Phase 4 直接使用 GreptimeDB 的 OTLP logs 端点，不需要 Loki
> - 如未来需要原生瀑布图/依赖拓扑体验，再按计划文档附录 A 追加 Jaeger 或 Tempo

---

## 2. 架构设计

### 2.1 组件架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Web (Next.js)  │     │ Server (Python) │     │ graphiti-core   │
│  OTEL SDK (JS)  │────▶│ OTEL SDK (Py)   │────▶│ Tracer 抽象层   │
│  (Phase 6 可选) │     │ 新增 tracer 接线 │     │ (已有，需扩展)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                     ┌─────────────────────┐
                     │   OTLP Collector    │
                     │  (采样、脱敏、路由)   │
                     └─────────────────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │    GreptimeDB       │
                     │  (metrics + traces  │
                     │   + logs)           │
                     └─────────────────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │      Grafana        │
                     │  (查询、Dashboard)   │
                     └─────────────────────┘
```

### 2.2 数据流

```
请求入口
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend Span（Phase 6 可选）                                │
│ - span_name: web.request                                     │
│ - attributes: user_id=anonymous, route=/api/chat            │
└─────────────────────────────────────────────────────────────┘
    │ Header: traceparent
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Server Span (FastAPI middleware)                             │
│ - span_name: http.server.request                             │
│ - attributes: http.method=POST, http.route=/chat            │
└─────────────────────────────────────────────────────────────┘
    │ Context propagation
    ▼
┌─────────────────────────────────────────────────────────────┐
│ graphiti-core Spans（基于现有 tracer.py 扩展）                │
│ ├── graphiti.add_episode                                     │
│ │   ├── graphiti.llm.generate (model, tokens)               │
│ │   └── graphiti.db.query (query_type, row_count)           │
│ ├── graphiti.add_episode_bulk                                │
│ ├── graphiti.preview_episode                                 │
│ ├── graphiti.commit_episode                                  │
│ ├── graphiti.build_communities                               │
│ │   ├── graphiti.llm.generate (community_summary)           │
│ │   └── graphiti.db.query (write communities)               │
│ ├── graphiti.search (type 属性区分检索模式)                   │
│ │   ├── graphiti.db.query                                    │
│ │   └── graphiti.llm.embed                                   │
│ ├── graphiti.add_triplet                                     │
│ └── graphiti.summarize_saga                                  │
└─────────────────────────────────────────────────────────────┘
    │ OTLP (http://collector:4318/v1/traces)
    ▼
┌─────────────────────────────────────────────────────────────┐
│ OTLP Collector                                               │
│ - 尾部采样: 错误 100%, 慢链路 100%, 正常 10%                   │
│ - 脱敏: API Key, Password, Authorization, db.query 原文       │
│ - 批量导出到 GreptimeDB                                       │
└─────────────────────────────────────────────────────────────┘
    │ OTLP (http://greptime:4000/v1/otlp，trace 带 pipeline header)
    ▼
┌─────────────────────────────────────────────────────────────┐
│ GreptimeDB                                                   │
│ - traces: 内置 greptime_trace_v1 pipeline，自动建表            │
│ - metrics: OTLP 存储（Phase 3）                               │
│ - logs: OTLP 存储（Phase 4），不需要 Loki                      │
│ - 归档: 本地文件 → 预留 MinIO 切换                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 现有可观测性现状与对齐策略

Graphiti 已内置一套 OpenTelemetry 追踪抽象，本设计基于它**扩展**，而非另建体系。

**现有抽象层 `graphiti_core/tracer.py`：**

| 类 | 作用 |
|----|------|
| `Tracer` / `TracerSpan`（ABC） | 追踪器与 span 的抽象接口 |
| `NoOpTracer` / `NoOpSpan` | 零开销空实现，OTel 未安装或未注入 tracer 时使用 |
| `OpenTelemetryTracer` / `OpenTelemetrySpan` | OTel 包装器，支持可配置 span 名称前缀 |
| `create_tracer(otel_tracer, span_prefix)` | 工厂函数，`otel_tracer=None` 时返回 NoOpTracer |

`Graphiti.__init__` 通过 `tracer` 参数 + `trace_span_prefix` 参数（默认 `graphiti`）接入，调用 `create_tracer()` 后同步注入 `llm_client.set_tracer()`。

**Span 覆盖现状（截至评审时）：**

| Span | 状态 | 位置 |
|------|------|------|
| `graphiti.add_episode` | 已埋点 | graphiti.py:1126 |
| `graphiti.preview_episode` | 已埋点 | graphiti.py:1310 |
| `graphiti.commit_episode` | 已埋点 | graphiti.py:1441 |
| `graphiti.add_episode_bulk` | 已埋点 | graphiti.py:1568 |
| `graphiti.llm.generate` | 已埋点（所有 LLM client） | llm_client/*.py |
| `graphiti.search` | 未埋点 | graphiti.py:1800 |
| `graphiti.build_communities` | 未埋点 | graphiti.py:1763 |
| `graphiti.add_triplet` | 未埋点 | graphiti.py:1918 |
| `graphiti.summarize_saga` | 未埋点 | graphiti.py:480 |
| `graphiti.remove_episode` | 未埋点 | graphiti.py:2038 |
| `graphiti.llm.embed` | 未埋点 | embedder 层（包装器模式 `TracingEmbedder`，不改 6 个实现） |
| `graphiti.db.query` | 未埋点 | driver 层（仅 postgres_age 优先接入，其余 follow-up） |

**关键现状：服务端 `ZepGraphiti` 构造时未传 `tracer` 参数**（zep_graphiti.py:189），因此上述已埋 span 在生产环境全部走 `NoOpTracer`，不产生任何数据。**服务端 tracer 接线是 Phase 2 的第一优先级前置任务。**

**PostHog 遥测删除：** 现有 `graphiti_core/telemetry/` 模块是 PostHog 产品分析（匿名使用统计，上报到 `us.i.posthog.com`）。本设计决定**完全删除该模块及 `posthog` 依赖**，`Graphiti._capture_initialization_telemetry()` 及 `_get_provider_type()` 一并移除，初始化信息改由 OTel span 属性记录。删除后 `observability/` 成为唯一遥测模块，不再有命名歧义。

**对齐策略：**

1. 语义属性常量集中放置（建议 `graphiti_core/observability/attributes.py`），所有 span 复用同一套常量，不与 `tracer.py` 的抽象类冲突
2. metrics 为全新模块（现有代码无 metrics 埋点）
3. 服务端 bootstrap 初始化 `TracerProvider` + OTLP exporter，并把 tracer 传给 `ZepGraphiti`（Phase 2.1）
4. `GraphDriver` ABC 增加 tracer 支持，**当前仅 postgres_age 实现接入** `db.query` span；neo4j / falkordb / kuzu 作为 follow-up（Phase 2.4）
5. 补齐 core 层未埋点方法：search / build_communities / add_triplet / summarize_saga / remove_episode / llm.embed（Phase 2.5）
8. **Embedder tracer 用包装器模式**：新建 `TracingEmbedder`（实现 `EmbedderClient` 接口，内部持有真实 embedder + tracer），`Graphiti.__init__` 中用 `TracingEmbedder(self.embedder, self.tracer)` 包装；6 个 embedder 实现零改动（Phase 2.5）
6. **删除 PostHog**：移除 `graphiti_core/telemetry/` 目录、`posthog>=3.0.0` 依赖（pyproject.toml）、Dockerfile 中的 `posthog` 安装；`graphiti.py` 中删除 `capture_event` import、`_capture_initialization_telemetry()`、`_get_provider_type()`（Phase 2.3）
7. **`observability/` 成为唯一遥测模块**：PostHog 删除后 `telemetry/` 目录可安全移除，不再存在命名歧义

---

## 3. 语义属性定义

### 3.1 标准属性（遵循 OTEL 语义约定）

| 属性 | 说明 | 示例值 |
|------|------|--------|
| `service.name` | 服务名 | `graphiti-server`, `graphiti-core` |
| `service.version` | 版本 | `0.29.1` |
| `deployment.environment` | 环境 | `development`, `production` |

### 3.2 Graphiti 自定义属性

```python
# graphiti_core/observability/attributes.py
# 所有 span 复用本文件常量，与 tracer.py 抽象层配合使用

# ===== Episode 相关 =====
GRAPHITI_EPISODE_NAME = "graphiti.episode.name"
GRAPHITI_EPISODE_SOURCE = "graphiti.episode.source"  # "message", "text", "json"
GRAPHITI_EPISODE_SOURCE_DESC = "graphiti.episode.source_description"

# ===== Search 相关 =====
# search() 和 search_() 共用 graphiti.search span，用 type 属性区分
GRAPHITI_SEARCH_TYPE = "graphiti.search.type"  # "node", "edge", "mmr", "bfs", "hybrid", "semantic"
GRAPHITI_SEARCH_LIMIT = "graphiti.search.limit"
GRAPHITI_SEARCH_RESULT_COUNT = "graphiti.search.result_count"
GRAPHITI_SEARCH_DURATION_MS = "graphiti.search.duration_ms"

# ===== LLM 相关 =====
GRAPHITI_LLM_MODEL = "graphiti.llm.model"
GRAPHITI_LLM_PROVIDER = "graphiti.llm.provider"  # "openai", "anthropic", "gemini"
GRAPHITI_LLM_TOKENS_IN = "graphiti.llm.tokens_in"
GRAPHITI_LLM_TOKENS_OUT = "graphiti.llm.tokens_out"
GRAPHITI_LLM_LATENCY_MS = "graphiti.llm.latency_ms"
GRAPHITI_LLM_PROMPT_NAME = "graphiti.llm.prompt_name"  # "extract", "summarize", "dedupe"

# ===== 数据库相关 =====
GRAPHITI_DB_SYSTEM = "graphiti.db.system"  # "postgres_age", "neo4j", "falkordb", "kuzu"
GRAPHITI_DB_QUERY_TYPE = "graphiti.db.query_type"  # "read", "write"
GRAPHITI_DB_ROW_COUNT = "graphiti.db.row_count"
GRAPHITI_DB_LATENCY_MS = "graphiti.db.latency_ms"
GRAPHITI_DB_QUERY_TEMPLATE_HASH = "graphiti.db.query_template_hash"  # 查询模板哈希，低基数

# 注意：原始查询语句 graphiti.db.query 仅在 DEBUG 级别 / 开发环境记录。
# 生产环境不存储，原因：
#   1. PII 泄露风险——Graphiti 查询常嵌入 episode 内容片段（用户对话、文档）
#   2. 基数膨胀——每条查询原文不同，作为 span attribute 会导致存储爆炸
# Collector 在 attributes processor 中删除该字段（见 §8.2）。
# 开发环境可通过 debug exporter 查看原文，不经生产 pipeline。

# ===== 用户/租户 =====
GRAPHITI_USER_ID = "graphiti.user.id"  # 默认 "anonymous"，仅出现在 traces/logs，不进 metrics
GRAPHITI_GROUP_ID = "graphiti.group.id"

# ===== 会话 =====
GRAPHITI_SESSION_ID = "graphiti.session.id"
```

---

## 4. Traces 设计

### 4.1 Span 层级

```
web.request (Frontend, Phase 6 可选)
  │
  └─ http.server.request (FastAPI middleware)
       │
       ├─ graphiti.add_episode
       │    ├─ graphiti.llm.generate (prompt: extract)
       │    ├─ graphiti.llm.embed
       │    └─ graphiti.db.query (query_type: write)
       │
       ├─ graphiti.add_episode_bulk
       │    └─ graphiti.add_episode (N times)
       │
       ├─ graphiti.preview_episode
       │    ├─ graphiti.llm.generate (prompt: extract)
       │    └─ graphiti.db.query (query_type: read)
       │
       ├─ graphiti.commit_episode
       │    └─ graphiti.db.query (query_type: write)
       │
       ├─ graphiti.build_communities
       │    ├─ graphiti.llm.generate (prompt: community_summary)
       │    ├─ graphiti.llm.embed (community name)
       │    └─ graphiti.db.query (query_type: write)
       │
       ├─ graphiti.search
       │    ├─ graphiti.db.query (bm25)
       │    ├─ graphiti.db.query (vector)
       │    └─ graphiti.llm.embed (query embedding)
       │    # search() 与 search_() 共用此 span，
       │    # 用 graphiti.search.type 属性区分检索模式
       │
       ├─ graphiti.add_triplet
       │    ├─ graphiti.llm.generate (prompt: dedupe)
       │    └─ graphiti.db.query (query_type: write)
       │
       └─ graphiti.summarize_saga
            └─ graphiti.llm.generate (prompt: summarize)
```

### 4.2 关键 Span 定义

| Span 名称 | 层级 | 关键属性 |
|-----------|------|----------|
| `web.request` | Frontend | `user_id`, `route`, `http.method` |
| `http.server.request` | Server | `http.route`, `http.status_code` |
| **Episode 操作** |||
| `graphiti.add_episode` | Core | `episode.name`, `episode.source`, `group_id` |
| `graphiti.add_episode_bulk` | Core | `episode.count`, `group_id` |
| `graphiti.preview_episode` | Core | `episode.name`, `group_id` |
| `graphiti.commit_episode` | Core | `episode.uuid`, `group_id` |
| `graphiti.remove_episode` | Core | `episode.uuid` |
| **Search 操作** |||
| `graphiti.search` | Core | `search.type`, `search.limit`, `group_id`（统一命名） |
| **Community 操作** |||
| `graphiti.build_communities` | Core | `group_id` |
| **Triplet 操作** |||
| `graphiti.add_triplet` | Core | `source_node`, `target_node`, `edge_name` |
| **Saga 操作** |||
| `graphiti.summarize_saga` | Core | `saga_id` |
| **LLM 子操作** |||
| `graphiti.llm.generate` | Core | `llm.model`, `llm.tokens_in`, `llm.tokens_out`, `llm.prompt_name` |
| `graphiti.llm.embed` | Core | `llm.model`, `embedding.dimension` |
| **DB 子操作** |||
| `graphiti.db.query` | Core | `db.system`, `db.query_type`, `db.row_count` |

> `db.query_type` 通过 helper 层标记传入：`execute_query` 增加可选参数 `query_type: str | None`，由 postgres_age 的 `fetch_records()` 传 `"read"`、`run_statement()` 传 `"write"`（各改一行）。不做 SQL 关键字检测——读写语义由调用方明确给出，更准确且不脆弱。

> 注：`search()` 和 `search_()` 是两个公开方法，但 emit 同一个 span 名 `graphiti.search`，通过 `graphiti.search.type` 属性区分检索模式（hybrid / node / edge / mmr / bfs 等）。避免出现 `graphiti.search_` 这种带下划线的 span 名造成困惑。

### 4.3 错误追踪

- 所有 Span 失败时设置 `status = ERROR`
- 记录 `error.type` 和 `error.message`
- 异常栈记录到 Span Event

### 4.4 Context 传播

`group_id` 和 `user_id` 需要从 FastAPI 请求层传播到 core 深处的 span（如 `llm.generate`、`db.query`）。使用 **OTel Baggage API** 实现进程内传播：

1. **FastAPI middleware** 中从请求提取 `group_id` / `user_id`，通过 `baggage.set_baggage()` + `context.attach()` 注入 context
2. **下游 span** 按需从 baggage 读取，写入自己的 span attributes（不影响 metrics 标签）
3. **Baggage 不产生存储**——它只是进程内键值对传递机制；只有 span 主动读取 baggage 值并写入 attribute 时才会落库到 traces 表

> `user_id` 通过 baggage 传播但只存在于 traces，不进入 metrics 标签（见 §5.4）。当前默认 `anonymous`，接入用户认证后替换为真实 ID。

---

## 5. Metrics 设计

### 5.1 指标分类

> **基数原则：所有 metrics 标签仅使用低基数值。** `user_id`、`episode.name`、查询原文等高基数值**不进入 metrics**，仅出现在 traces/logs 的 span attributes。"按用户"维度（如 token 消耗 Top 10）从 traces 的 span attributes 聚合，不依赖 metrics。

| 类别 | 指标 | 类型 | 标签 |
|------|------|------|------|
| **API 调用** | `graphiti_api_requests_total` | Counter | `method`, `route`, `status_code` |
| | `graphiti_api_request_duration_ms` | Histogram | `method`, `route` |
| **Episode** | `graphiti_episode_add_total` | Counter | `source`, `group_id` |
| | `graphiti_episode_add_duration_ms` | Histogram | `source` |
| | `graphiti_episode_bulk_add_total` | Counter | `group_id` |
| | `graphiti_episode_preview_total` | Counter | `group_id` |
| | `graphiti_episode_commit_total` | Counter | `group_id` |
| | `graphiti_episode_remove_total` | Counter | `group_id` |
| **Search** | `graphiti_search_total` | Counter | `type`, `group_id` |
| | `graphiti_search_duration_ms` | Histogram | `type` |
| | `graphiti_search_result_count` | Histogram | `type` |
| **Community** | `graphiti_community_build_total` | Counter | `group_id` |
| | `graphiti_community_build_duration_ms` | Histogram | `group_id` |
| | `graphiti_community_count` | Gauge | `group_id` |
| **Triplet** | `graphiti_triplet_add_total` | Counter | `group_id` |
| | `graphiti_triplet_add_duration_ms` | Histogram | `group_id` |
| **Saga** | `graphiti_saga_summarize_total` | Counter | `group_id` |
| | `graphiti_saga_summarize_duration_ms` | Histogram | |
| **LLM** | `graphiti_llm_calls_total` | Counter | `model`, `provider`, `prompt_name` |
| | `graphiti_llm_tokens_total` | Counter | `model`, `provider`, `direction` (in/out) |
| | `graphiti_llm_latency_ms` | Histogram | `model`, `provider` |
| | `graphiti_llm_errors_total` | Counter | `model`, `provider`, `error_type` |
| **DB** | `graphiti_db_query_total` | Counter | `system`, `query_type` |
| | `graphiti_db_query_duration_ms` | Histogram | `system`, `query_type` |
| | `graphiti_db_connections_active` | Gauge | `system` |

> `group_id` 作为当前租户维度保留在 metrics 中，但 **group 数量超过 20 时从 metrics 移除**，仅保留在 traces 聚合，避免时间序列膨胀。

### 5.2 Histogram Bucket 配置

```python
# Duration buckets (ms)
DURATION_BUCKETS = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]

# LLM latency buckets (ms)
LLM_LATENCY_BUCKETS = [10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000]
```

### 5.3 指标导出方式

通过 OTLP Collector 导出到 GreptimeDB，而非直接暴露 `/metrics` 端点：

```yaml
# Collector 配置
exporters:
  # traces 必须使用 GreptimeDB 内置 trace pipeline
  otlphttp/greptime_traces:
    endpoint: http://greptime:4000/v1/otlp
    headers:
      X-Greptime-Database: public
      x-greptime-pipeline-name: greptime_trace_v1

  # metrics/logs 不能复用 trace pipeline header
  otlphttp/greptime_other:
    endpoint: http://greptime:4000/v1/otlp
    headers:
      X-Greptime-Database: public
```

> **关键约束**：GreptimeDB v1.1 的 OTLP traces 端点要求请求头携带内置 pipeline 名称。只有 `greptime_trace_v0` / `greptime_trace_v1` 两个内置 trace pipeline 可用；自定义 pipeline 会被拒绝并返回 `Unsupported pipeline for trace`。同时 logs handler 不接受 trace pipeline，因此 traces 与 metrics/logs 必须使用独立的 exporter，避免把 `x-greptime-pipeline-name: greptime_trace_v1` 带到 logs 请求上。

### 5.4 标签基数原则

| 标签 | 基数 | 是否进 metrics | 说明 |
|------|------|---------------|------|
| `method`, `status_code` | 极低（有限枚举） | 是 | — |
| `route` | 低 | 是 | API 路径模板，非实际 URL |
| `source`, `type`, `query_type`, `direction` | 低（有限枚举） | 是 | — |
| `model`, `provider`, `prompt_name` | 低（十级） | 是 | — |
| `group_id` | 中 | 是（暂留） | group 数 <= 20 时可接受；超过则移至 traces |
| `user_id` | **高** | **否** | 仅 traces/logs 的 span attributes |
| `episode.name`, `session.id` | **高** | **否** | 仅 traces/logs |
| 查询原文 (`db.query`) | **极高** | **否** | 仅 DEBUG / 开发环境 |

**"按用户"维度的分析**（如 token 消耗 Top 10 用户、用户调用量排行）从 traces 表的 span attributes 聚合查询，不在 metrics 中实现。

---

## 6. Logs 设计

### 6.1 结构化日志格式

```json
{
  "timestamp": "2026-07-31T10:00:00.000Z",
  "level": "INFO",
  "message": "Episode added successfully",
  "service": "graphiti-server",
  "trace_id": "abc123",
  "span_id": "def456",
  "attributes": {
    "graphiti.episode.name": "doc-001",
    "graphiti.group.id": "group-1",
    "graphiti.user.id": "anonymous"
  }
}
```

### 6.2 日志级别策略

| 级别 | 场景 | 示例 |
|------|------|------|
| `ERROR` | 异常、失败 | LLM 调用失败、DB 连接断开 |
| `WARN` | 超时、重试、降级 | LLM 超时重试、搜索无结果 |
| `INFO` | 关键操作完成 | Episode 添加完成、Search 完成 |
| `DEBUG` | 详细调试信息 | DB 查询语句、LLM prompt（生产环境关闭） |

### 6.3 日志注入 trace_id

使用 OTEL Logs Bridge API 自动注入 `trace_id` 和 `span_id`：

```python
# Python 日志配置
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggingHandler
import logging

handler = LoggingHandler()
logging.basicConfig(level=logging.INFO, handlers=[handler])
```

---

## 7. Profiling 设计（按需触发）

### 7.1 实现方案

通过 FastAPI 端点暴露 profiling 控制接口：

```
POST /debug/profile/start?type=cpu&duration=30s
GET  /debug/profile/status
GET  /debug/profile/download/<profile_id>
POST /debug/profile/stop
```

### 7.2 安全要求（生产环境必须鉴权）

Profiling 端点暴露 CPU profiling 接口，未授权访问存在 DoS 和信息泄露风险（火焰图可泄露内存中的数据结构、调用栈细节）。**必须满足以下之一：**

- **方案 A（推荐）**：通过环境变量 `PROFILE_ADMIN_TOKEN` 配置 admin token，所有 `/debug/profile/*` 请求校验 `X-Profile-Token` header，不匹配返回 403
- **方案 B**：仅在 `deployment.environment != production` 时注册 profiling 路由，生产环境不暴露端点

### 7.3 技术选型

| 方案 | 优点 | 缺点 |
|------|------|------|
| **py-spy** | 无侵入，支持生产环境 | 需要 root 权限 |
| **austin** | 无侵入，支持多语言 | 输出格式需转换 |
| **cProfile + viz** | Python 原生 | 需要代码侵入 |

**推荐**：`py-spy top --pid <pid> --output profile.svg` 生成火焰图

### 7.4 火焰图存储

- 生成后存储在 `/var/lib/graphiti/profiles/<profile_id>.svg`
- 通过 API 返回 SVG 内容或下载链接
- 可选：上传到 MinIO 做长期存储

---

## 8. 部署架构

### 8.1 Docker Compose 配置

```yaml
# 主 docker-compose.yml 中的可观测性服务片段（当前已合并到主 compose）
# 使用 profiles 隔离：docker compose --profile observability up

  # ===== OpenTelemetry Collector =====
  otel-collector:
    profiles: ["observability", "all"]
    image: otel/opentelemetry-collector-contrib:0.104.0
    container_name: graphiti-otel-collector
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./observability/otel-config.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    depends_on:
      - greptime
    networks:
      - observability
    restart: unless-stopped

  # ===== GreptimeDB（traces + metrics + logs 统一存储） =====
  greptime:
    profiles: ["observability", "all"]
    image: greptime/greptimedb:v1.1.0
    container_name: graphiti-greptime
    command: ["standalone", "start", "--http-addr=0.0.0.0:4000", "--grpc-bind-addr=0.0.0.0:4001"]
    volumes:
      - greptime-data:/tmp/greptimedb
    ports:
      - "4000:4000"   # HTTP API
      - "4001:4001"   # gRPC
      - "4002:4002"   # MySQL
    networks:
      - observability
    restart: unless-stopped

  # ===== Grafana =====
  grafana:
    profiles: ["observability", "all"]
    image: grafana/grafana:11.1.0
    container_name: graphiti-grafana
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    volumes:
      - ./observability/grafana-dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./observability/grafana-datasources:/etc/grafana/provisioning/datasources:ro
    ports:
      - "3001:3000"   # 3000 已被 web-service 占用，使用 3001
    depends_on:
      - greptime
    networks:
      - observability
    restart: unless-stopped

volumes:
  mcp_logs:
  greptime-data:

networks:
  observability:
```

> 注：
> - 已移除废弃的 `version: '3.8'` 字段，现代 Compose 忽略该字段。
> - Grafana 端口使用 `3001:3000`，因为主 compose 的 `web-service` 已占用 3000。
> - server 服务需同时加入 `default` 和 `observability` 网络，才能通过 `otel-collector:4318` 上报。
> - 生产环境应关闭 Grafana 匿名 Admin（`GF_AUTH_ANONYMOUS_ENABLED=false`）并配置真实认证。
> - Jaeger/Tempo/Loki 不在此清单中；如需原生 trace 瀑布图，参考计划文档附录 A 追加 Jaeger。

### 8.2 OTLP Collector 配置（已修复采样/脱敏/排序问题）

```yaml
# observability/otel-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    limit_mib: 512
    check_interval: 1s

  # ──────────────────────────────────────────────
  # 尾部采样：先收集完整 trace 再决策
  # 注意：tail_sampling 必须在 batch 之前运行，
  #       否则 batch 会打碎 trace 导致无法做整体决策
  # ──────────────────────────────────────────────
  tail_sampling:
    decision_wait: 30s        # LLM 链路较长（add_episode 可达 10-60s），
                              # 5s 会截断未完成的 trace，提至 30s
    num_traces: 50000
    expected_new_traces_per_sec: 100
    policies:
      # 错误链路 100% 采样
      - name: errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      # 慢链路 100% 采样（> 5s），用于性能瓶颈定位
      - name: slow
        type: latency
        latency:
          threshold_ms: 5000
      # 正常请求 10% 采样（兜底策略，防止成功 trace 被全量丢弃）
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 10

  # ──────────────────────────────────────────────
  # 脱敏：必须在采样之后、导出之前删除敏感属性
  # ──────────────────────────────────────────────
  attributes/sanitize:
    actions:
      - key: api_key
        action: delete
      - key: password
        action: delete
      - key: authorization
        action: delete
      - key: graphiti.db.query          # 生产环境删除原始查询语句（PII 风险）
        action: delete
      - key: graphiti.llm.prompt        # 如记录了完整 prompt，同样删除
        action: delete

  batch:
    timeout: 5s
    send_batch_size: 1024

exporters:
  # traces 必须使用 GreptimeDB 内置 trace pipeline
  otlphttp/greptime_traces:
    endpoint: http://greptime:4000/v1/otlp
    headers:
      X-Greptime-Database: public
      x-greptime-pipeline-name: greptime_trace_v1

  # metrics/logs 不能复用 trace pipeline header
  otlphttp/greptime_other:
    endpoint: http://greptime:4000/v1/otlp
    headers:
      X-Greptime-Database: public

  # Debug 输出（仅开发调试，生产环境移除）
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      # 处理器顺序：限流 → 尾部采样 → 脱敏 → 批量
      processors: [memory_limiter, tail_sampling, attributes/sanitize, batch]
      exporters: [otlphttp/greptime_traces, debug]
    metrics:
      receivers: [otlp]
      # metrics 不走 tail_sampling（无 trace 概念），但需脱敏
      processors: [memory_limiter, attributes/sanitize, batch]
      exporters: [otlphttp/greptime_other]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, attributes/sanitize, batch]
      exporters: [otlphttp/greptime_other]
```

**GreptimeDB v1.1 trace pipeline 约束（实测确认）：**

1. OTLP traces 端点 `/v1/otlp/v1/traces` 必须携带 `x-greptime-pipeline-name`，否则返回 `Pipeline is required for this API.`
2. 该 header 只接受 GreptimeDB 内置名称：`greptime_trace_v0` 或 `greptime_trace_v1`。自定义 pipeline 会返回 `Unsupported pipeline for trace`
3. `greptime_trace_v1` 会自动创建 `opentelemetry_traces`、`opentelemetry_traces_services`、`opentelemetry_traces_operations` 三张表，并按 span attribute 动态扩展 `span_attributes.*` / `resource_attributes.*` 列
4. logs handler 不接受 trace pipeline，因此 traces 与 metrics/logs 必须使用独立 exporter，避免把 trace pipeline header 带到 logs 请求

**相对 v1 的修复点：**

1. 移除了未接入 pipeline 的 `probabilistic_sampler`（与 tail_sampling 冲突），改用 tail_sampling 内的 `baseline` 策略实现 10% 采样
2. tail_sampling 补充兜底策略——原配置只有 errors 策略，不匹配任何策略的 trace 会被全量丢弃，实际效果是"错误 100%、正常 0%"
3. 新增 `slow` 策略（延迟 > 5s 100% 采样），直接服务"性能优化"目标
4. `decision_wait` 从 5s 提至 30s，适配 LLM 长链路
5. `attributes/sanitize` 脱敏处理器接入所有 pipeline，并新增删除 `graphiti.db.query` 原文
6. 处理器顺序修正为 `memory_limiter → tail_sampling → attributes/sanitize → batch`（原配置 batch 在 tail_sampling 之前会打碎 trace）

### 8.3 GreptimeDB 归档配置

```toml
# observability/greptime-config.toml

[storage]
type = "File"
data_dir = "/tmp/greptimedb/data"

[wal]
dir = "/tmp/greptimedb/wal"
file_size = "256MB"
```

> 当前 standalone 模式使用最小化配置，数据通过 Docker volume `greptime-data` 持久化。后续需要本地归档或 MinIO 切换时，再按以下模板扩展：

```toml
# 本地归档（预留 MinIO 切换）
[[storage.procedure]]
name = "data_compaction"
schedule = "0 0 2 * * *"  # 每天凌晨 2 点
options = { target_file_size = "256MB" }

# 预留 S3/MinIO 配置
# [storage.remote_backend]
# type = "S3"
# bucket = "graphiti-metrics"
# root = "/data"
# endpoint = "http://minio:9000"
```

---

## 9. Grafana Dashboard 设计

### 9.1 Dashboard 列表

| Dashboard | 用途 | 面板 |
|-----------|------|------|
| **Request Overview** | API 调用监控 | QPS、延迟 P99、错误率、按 route 分组 |
| **Episode Operations** | Episode 操作分析 | 添加趋势、Preview/Commit 比例、Bulk 批量大小分布 |
| **Search Analytics** | 搜索分析 | 搜索热度、延迟分布、结果数分布、按 type 分组 |
| **Community Analytics** | 社区分析 | 构建频率、社区数量、构建耗时 |
| **LLM Observability** | 大模型调用分析 | Token 消耗、延迟分布、模型分布、按 prompt_name 分组 |
| **Database Performance** | 数据库性能 | Query 延迟、连接数、慢查询 Top 10 |
| **Tenant Metrics** | 租户分析 | Group 活跃度、各 group 调用量对比 |
| **Trace Explorer** | 链路追踪 | 按 trace_id 查询、错误链路、慢链路 Top |

> **Grafana 数据源（当前已配置）**：GreptimeDB 通过 MySQL 协议接入（`greptime:4002`，database `public`），因为官方 GreptimeDB Grafana 插件在当前镜像上安装失败。Trace Explorer 基于 SQL 查询 `opentelemetry_traces` 表，**非 Tempo/Jaeger 式原生瀑布图浏览器**。如需原生 trace 浏览，参见 §11.4 及计划文档附录 A。

### 9.2 关键查询示例

```sql
-- 最近 50 条 spans（实际 schema，实测可用）
SELECT
  trace_id,
  span_id,
  span_name,
  service_name,
  span_status_code,
  duration_nano / 1000000 AS duration_ms,
  timestamp
FROM opentelemetry_traces
ORDER BY timestamp DESC
LIMIT 50;

-- 慢链路 Top 10（来自 traces 表）
SELECT
  trace_id,
  span_name,
  service_name,
  duration_nano / 1000000 AS duration_ms
FROM opentelemetry_traces
WHERE duration_nano / 1000000 > 1000
ORDER BY duration_nano DESC
LIMIT 10;

-- 错误链路 Top 10
SELECT
  trace_id,
  span_name,
  service_name,
  span_status_message,
  timestamp
FROM opentelemetry_traces
WHERE span_status_code = 'STATUS_CODE_ERROR'
ORDER BY timestamp DESC
LIMIT 10;

-- 按 span 名聚合的调用量（用于业务热度分析）
SELECT
  span_name,
  service_name,
  COUNT(*) AS calls
FROM opentelemetry_traces
WHERE timestamp > now() - INTERVAL '1h'
GROUP BY span_name, service_name
ORDER BY calls DESC;

-- API 请求 QPS（Phase 3 metrics 落地后，使用 graphiti_api_requests_total）
-- LLM Token 消耗（Phase 3 metrics 落地后，使用 graphiti_llm_tokens_total）
```

> 注：`greptime_trace_v1` 会自动把 span attributes 展开为 `span_attributes.<key>` 列、resource attributes 展开为 `resource_attributes.<key>` 列。例如 `span_attributes.http.method`、`resource_attributes.service.version` 均可直接参与 WHERE / GROUP BY。

---

## 10. 实施计划

具体实施步骤、Phase 分解、文件级修改清单见独立计划文档：

> [2026-07-31-observability-plan.md](../plans/2026-07-31-observability-plan.md)

## 11. 后续扩展
---

### 11.1 用户体系接入
- 当添加用户认证后，修改 `user_id` 从 `anonymous` 到实际用户 ID
- `user_id` 仅在 traces/logs 中出现，**不加入 metrics 标签**
- 添加用户级分析（基于 traces 聚合）和配额监控

### 11.2 MinIO 归档切换
- 修改 `greptime-config.toml` 的 `storage.remote_backend`
- 历史数据迁移到 MinIO

### 11.3 告警规则
- 配置 Grafana Alerting
- 错误率 > 1% 告警
- LLM 延迟 P99 > 10s 告警
- DB 连接池耗尽告警

### 11.4 可选：追加 Jaeger/Tempo 获得原生瀑布图

当前架构只依赖 GreptimeDB + OTLP Collector + Grafana，默认不需要 Jaeger、Tempo、Loki。GreptimeDB 已通过内置 `greptime_trace_v1` pipeline 存储 traces，SQL 查询 `opentelemetry_traces` 表可以满足 Trace Explorer 的基础需求。

**何时追加：**
- SQL 查询排障效率不足，需要 span 下钻、依赖拓扑、原生瀑布图
- 团队需要按服务依赖关系做跨服务链路分析
- trace 数据量增长后，希望把 trace 查询压力从 GreptimeDB metrics 侧分离

**追加方式：** 按计划文档附录 A 的 Jaeger 参考配置，在 `docker-compose.yml` 增加 `jaeger` 服务、在 Collector 的 traces pipeline 增加 `otlp/jaeger` exporter（可双写或切换）、在 Grafana 增加 Jaeger 数据源。Tempo 的接入方式与 Jaeger 类似，使用 `otlp/tempo` exporter 即可。
