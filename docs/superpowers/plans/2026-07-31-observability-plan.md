# Graphiti 可观测性实施计划

> 关联设计文档：[2026-07-31-observability-design.md](../specs/2026-07-31-observability-design.md)
> 创建日期：2026-07-31
> 最后修订：2026-08-01

## Phase 1: 基础设施 (Week 1)
- [ ] 部署 GreptimeDB + Grafana
- [ ] 部署 OTLP Collector（使用 spec §8.2 已修复的配置），合并到主 `docker-compose.yml`
- [ ] 验证数据流：OTLP -> Collector -> GreptimeDB -> Grafana
- [ ] 用一个最小测试 trace 跑通 collector 采样/脱敏链路

> **GreptimeDB v1.1 trace 接入要点（已实测确认）：**
> - OTLP traces 请求必须携带 `x-greptime-pipeline-name: greptime_trace_v1`（或 `greptime_trace_v0`），否则返回 `Pipeline is required for this API.`
> - 该 header 只接受 GreptimeDB 内置 trace pipeline 名称；自定义 pipeline 返回 `Unsupported pipeline for trace`
> - `greptime_trace_v1` 自动创建 `opentelemetry_traces`、`opentelemetry_traces_services`、`opentelemetry_traces_operations` 三张表
> - logs handler 不接受 trace pipeline，因此 Collector 中 traces 与 metrics/logs 必须使用独立 exporter（见 spec §8.2）
> - Grafana 通过 MySQL 协议（`greptime:4002`）连接 GreptimeDB，因为官方 GreptimeDB 插件在当前镜像安装失败

## Phase 2: Tracing 接线与补全 (Week 2)

> 本阶段是整个可观测性能否产生数据的前提。

- [ ] **2.1 服务端 tracer 接入（关键前置）**
  - server bootstrap 初始化 `TracerProvider` + `OTLPSpanExporter`
  - 配置 `Resource`（`service.name=graphiti-server`, `deployment.environment`）；`service.version` 通过 `importlib.metadata` 读取包版本，fallback 到环境变量
  - **修改 `ZepGraphiti` 构造，传入 `tracer=` 和 `trace_span_prefix=`**（当前 zep_graphiti.py:189 未传，全部走 NoOpTracer）
  - **添加依赖**：core 的 `tracing` optional dep 增加 `opentelemetry-exporter-otlp>=1.20.0`；server `pyproject.toml` 直接加 `opentelemetry-api`、`opentelemetry-sdk`、`opentelemetry-exporter-otlp` 依赖
  - 验证：已有 span（add_episode / llm.generate 等）开始产生数据
- [ ] **2.2 语义属性常量集中化**
  - 创建 `graphiti_core/observability/attributes.py`（spec §3.2）
  - 已有 span 补充 attribute 赋值
- [ ] **2.3 删除 PostHog 遥测**
  - 删除 `graphiti_core/telemetry/` 目录（telemetry.py + __init__.py）
  - `graphiti.py`：移除 `from graphiti_core.telemetry import capture_event`、`_capture_initialization_telemetry()` 方法、`_get_provider_type()` 方法、以及 `__init__` 末尾的 `self._capture_initialization_telemetry()` 调用
  - `pyproject.toml`：移除 `"posthog>=3.0.0"` 依赖
  - `Dockerfile`：移除 `posthog` 安装
  - `server/graph_service/config.py`：移除 `graphiti_telemetry_enabled` 配置项（PostHog 专用，OTel 不需要）
  - `server/.env*`：如有 `GRAPHITI_TELEMETRY_ENABLED` 环境变量，移除
  - **刷新 lock 文件**：`uv lock`（core）+ `cd server && uv lock`（server）
- [ ] **2.4 Driver 层 tracer 集成（仅 postgres_age）**
  - `GraphDriver` ABC 增加 `tracer` 属性 + `set_tracer()` 方法（参照 llm_client 模式）
  - **仅 `PostgresAgeDriver`** 接入 `db.query` span（neo4j / falkordb / kuzu 为 follow-up）
  - span 记录 `db.system`、`db.row_count`；`db.query_type` 通过 helper 层标记传入：给 `execute_query` 增加可选参数 `query_type: str | None`，由 `fetch_records()` 传 `"read"`、`run_statement()` 传 `"write"`（各改一行），不做脆弱的 SQL 关键字检测
  - **不记录查询原文**（原文仅 DEBUG）
  - `Graphiti.__init__` 将 tracer 注入 driver（参照 llm_client 注入方式）
- [ ] **2.5 Core 层补齐未埋点 span**
  - `graphiti.search`（search + search_ 统一命名 + type 属性）
  - `graphiti.build_communities`
  - `graphiti.add_triplet`
  - `graphiti.summarize_saga`
  - `graphiti.remove_episode`
  - `graphiti.llm.embed`（包装器模式，见下）
  - **Embedder tracer 用包装器模式**（避免改 6 个 embedder 实现）：
    - 新建 `graphiti_core/observability/tracing_embedder.py`，实现 `EmbedderClient` 接口，内部持有真实 embedder + tracer，包装 `create()` / `create_batch()`
    - `Graphiti.__init__` 中 `self.embedder = TracingEmbedder(self.embedder, self.tracer)` 替代直接赋值
    - 6 个 embedder 实现（openai / azure_openai / gemini / voyage / bge_zh / sentence_transformers）**零改动**
    - 代码中无 `isinstance(embedder, ...)` 检查，包装完全安全
- [ ] **2.6 FastAPI middleware**
  - 添加 `http.server.request` span（自动 span + 手动 attribute）
  - 用 **OTel Baggage API** 传播 `group_id` / `user_id`：middleware 中 `baggage.set()` + `context.attach()`，下游 span 按需从 baggage 读取写入 attributes
  - `user_id` 只存在于 traces（span attributes），**不进入 metrics 标签**
  - `group_id` 同时出现在 metrics 标签和 traces，但 **group 数量超过 20 时从 metrics 移除，仅保留在 traces**
- [ ] **验证全链路 trace**：一个完整 add_episode 请求的 web -> server -> core -> llm -> db 链路

## Phase 3: Metrics 集成 (Week 3)
- [ ] 定义 OTel 指标（spec §5.1，严格遵循低基数原则）：用 OTel metrics API（`Meter` + instrument）+ `OTLPMetricExporter`，**不使用 prometheus_client**，不暴露 `/metrics` 端点（spec §5.3）
- [ ] graphiti-core: 添加 metrics 埋点
- [ ] Server: API 级别 metrics
- [ ] 创建 Grafana Dashboard

## Phase 4: Logs 集成 (Week 4)
- [ ] 配置结构化日志
- [ ] 注入 trace_id
- [ ] 日志级别策略
- [ ] 日志 Dashboard

## Phase 5: Profiling (Week 5)
- [ ] 添加 profiling API 端点（含鉴权，spec §7.2）
- [ ] 集成 py-spy
- [ ] 火焰图生成和存储

## Phase 6: 前端 RUM（可选，暂不排期）
- [ ] 评估前端追踪对"业务分析 + 性能优化"目标的实际价值
  - 核心瓶颈在 LLM 和 DB，不在前端渲染
  - 前端 span 主要用于会话级用户行为分析
- [ ] 如确认有价值：集成 @opentelemetry/web
- [ ] 添加 web.request span + traceparent 传播

## Follow-up（暂不排期）

- neo4j / falkordb / kuzu driver 接入 `db.query` span
- 用户认证接入后，`user_id` 从 traces 聚合改为实时查询
- **group_id 基数迁移**：当 group 数量超过 20 时，将 metrics 中的 `group_id` 标签移除，仅保留在 traces 的 span attributes
- observability compose 合并到主 `docker-compose.yml` 后，用 `profiles` 隔离（`--profile observability`）

## 附录 A：Jaeger 参考配置（可选，非默认依赖）

当前生产链路只依赖 GreptimeDB + OTLP Collector + Grafana，不需要 Jaeger。以下配置保留为未来需要原生瀑布图/依赖拓扑时的参考，不纳入默认 `observability` profile。

### A.1 添加 Jaeger 服务

在主 `docker-compose.yml` 增加独立服务（建议使用独立 profile，例如 `jaeger`）：

```yaml
  # ===== Jaeger（可选 trace 后端，默认不启动） =====
  jaeger:
    profiles: ["jaeger"]
    image: jaegertracing/all-in-one:1.60
    container_name: graphiti-jaeger
    environment:
      - COLLECTOR_OTLP_ENABLED=true
      - COLLECTOR_OTLP_GRPC_HOST_PORT=:4317
    ports:
      - "16686:16686"   # Jaeger UI
      - "14250:14250"   # gRPC ingest
    networks:
      - observability
    restart: unless-stopped
```

启动命令：

```bash
docker compose --profile observability --profile jaeger up -d
```

### A.2 Collector 增加 Jaeger exporter

在 `observability/otel-config.yaml` 的 `exporters` 增加：

```yaml
exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true
```

traces pipeline 双写（Jaeger 只做可视化，GreptimeDB 继续做统一存储）：

```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, attributes/sanitize, batch]
      exporters: [otlphttp/greptime_traces, otlp/jaeger]
```

### A.3 Grafana 增加 Jaeger 数据源

在 `observability/grafana-datasources/datasources.yaml` 增加：

```yaml
datasources:
  - name: Jaeger
    uid: jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
    isDefault: false
    editable: true
```

### A.4 恢复默认（移除 Jaeger）

```bash
docker compose --profile jaeger down
```

同时从 `otel-config.yaml` 移除 `otlp/jaeger` exporter（traces pipeline 恢复只导出 `otlphttp/greptime_traces`），并从 Grafana datasource 移除 Jaeger 配置。

### A.5 Tempo 对照

如需 Tempo，思路与 Jaeger 相同：

- compose 增加 `tempo` 服务（`tempo:2.x`，默认 OTLP gRPC `4317`）
- Collector 增加 `otlp/tempo` exporter
- Grafana 增加 `tempo` 类型数据源
- traces pipeline 双写或切换，GreptimeDB 仍负责 metrics/logs
