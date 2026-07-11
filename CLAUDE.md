# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Graphiti is a Python framework for building temporally-aware knowledge graphs designed for AI agents. It enables real-time incremental updates to knowledge graphs without batch recomputation, making it suitable for dynamic environments.

Key features:

- Bi-temporal data model with explicit tracking of event occurrence times
- Hybrid retrieval combining semantic embeddings, keyword search (BM25), and graph traversal
- Support for custom entity definitions via Pydantic models
- Integration with Neo4j and FalkorDB as graph storage backends
- Optional OpenTelemetry distributed tracing support

## Development Commands

### Main Development Commands (run from project root)

```bash
# Install dependencies
uv sync --extra dev

# Format code (ruff import sorting + formatting)
make format

# Lint code (ruff + pyright type checking)
make lint

# Run tests
make test

# Run all checks (format, lint, test)
make check
```

### Server Development (run from server/ directory)

```bash
cd server/
# Install server dependencies
uv sync --extra dev

# Run server in development mode
uvicorn graph_service.main:app --reload

# Format, lint, test server code
make format
make lint
make test
```

### MCP Server Development (run from mcp_server/ directory)

```bash
cd mcp_server/
# Install MCP server dependencies
uv sync

# Run with Docker Compose
docker-compose up
```

## Code Architecture

### Core Library (`graphiti_core/`)

- **Main Entry Point**: `graphiti.py` - Contains the main `Graphiti` class that orchestrates all functionality
- **Graph Storage**: `driver/` - Database drivers for Neo4j and FalkorDB
- **LLM Integration**: `llm_client/` - Clients for OpenAI, Anthropic, Gemini, Groq
- **Embeddings**: `embedder/` - Embedding clients for various providers
- **Graph Elements**: `nodes.py`, `edges.py` - Core graph data structures
- **Search**: `search/` - Hybrid search implementation with configurable strategies
- **Prompts**: `prompts/` - LLM prompts for entity extraction, deduplication, summarization
- **Utilities**: `utils/` - Maintenance operations, bulk processing, datetime handling

### Server (`server/`)

- **FastAPI Service**: `graph_service/main.py` - REST API server
- **Routers**: `routers/` - API endpoints for ingestion and retrieval
- **DTOs**: `dto/` - Data transfer objects for API contracts

### MCP Server (`mcp_server/`)

- **MCP Implementation**: `graphiti_mcp_server.py` - Model Context Protocol server for AI assistants
- **Docker Support**: Containerized deployment with Neo4j

## Testing

- **Unit Tests**: `tests/` - Comprehensive test suite using pytest
- **Integration Tests**: Tests marked with `_int` suffix require database connections
- **Evaluation**: `tests/evals/` - End-to-end evaluation scripts

## Configuration

### Environment Variables

- `OPENAI_API_KEY` - Required for LLM inference and embeddings
- `USE_PARALLEL_RUNTIME` - Optional boolean for Neo4j parallel runtime (enterprise only)
- Provider-specific keys: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `VOYAGE_API_KEY`

### Database Setup

- **Neo4j**: Version 5.26+ required, available via Neo4j Desktop
  - Database name defaults to `neo4j` (hardcoded in Neo4jDriver)
  - Override by passing `database` parameter to driver constructor
- **FalkorDB**: Version 1.1.2+ as alternative backend
  - Database name defaults to `default_db` (hardcoded in FalkorDriver)
  - Override by passing `database` parameter to driver constructor

## Development Guidelines

### Code Style

- Use Ruff for formatting and linting (configured in pyproject.toml)
- Line length: 100 characters
- Quote style: single quotes
- Type checking with Pyright is enforced
- Main project uses `typeCheckingMode = "basic"`, server uses `typeCheckingMode = "standard"`

### Testing Requirements

- Run tests with `make test` or `pytest`
- Integration tests require database connections and are marked with `_int` suffix
- Use `pytest-xdist` for parallel test execution
- Run specific test files: `pytest tests/test_specific_file.py`
- Run specific test methods: `pytest tests/test_file.py::test_method_name`
- Run only integration tests: `pytest tests/ -k "_int"`
- Run only unit tests: `pytest tests/ -k "not _int"`

### LLM Provider Support

The codebase supports multiple LLM providers but works best with services supporting structured output (OpenAI, Gemini). Other providers may cause schema validation issues, especially with smaller models.

#### Current LLM Models (as of November 2025)

**OpenAI Models:**
- **GPT-5 Family** (Reasoning models, require temperature=0):
  - `gpt-5-mini` - Fast reasoning model
  - `gpt-5-nano` - Smallest reasoning model
- **GPT-4.1 Family** (Standard models):
  - `gpt-4.1` - Full capability model
  - `gpt-4.1-mini` - Efficient model for most tasks
  - `gpt-4.1-nano` - Lightweight model
- **Legacy Models** (Still supported):
  - `gpt-4o` - Previous generation flagship
  - `gpt-4o-mini` - Previous generation efficient

**Anthropic Models:**
- **Claude 4.5 Family** (Latest):
  - `claude-sonnet-4-5-latest` - Flagship model, auto-updates
  - `claude-sonnet-4-5-20250929` - Pinned Sonnet version from September 2025
  - `claude-haiku-4-5-latest` - Fast model, auto-updates
- **Claude 3.7 Family**:
  - `claude-3-7-sonnet-latest` - Auto-updates
  - `claude-3-7-sonnet-20250219` - Pinned version from February 2025
- **Claude 3.5 Family**:
  - `claude-3-5-sonnet-latest` - Auto-updates
  - `claude-3-5-sonnet-20241022` - Pinned version from October 2024
  - `claude-3-5-haiku-latest` - Fast model

**Google Gemini Models:**
- **Gemini 2.5 Family** (Latest):
  - `gemini-2.5-pro` - Flagship reasoning and multimodal
  - `gemini-2.5-flash` - Fast, efficient
- **Gemini 2.0 Family**:
  - `gemini-2.0-flash` - Experimental fast model
- **Gemini 1.5 Family** (Stable):
  - `gemini-1.5-pro` - Production-stable flagship
  - `gemini-1.5-flash` - Production-stable efficient

**Note**: Model names like `gpt-5-mini`, `gpt-4.1`, and `gpt-4.1-mini` used in this codebase are valid OpenAI model identifiers. The GPT-5 family are reasoning models that require `temperature=0` (automatically handled in the code).

### MCP Server Usage Guidelines

When working with the MCP server, follow the patterns established in `mcp_server/cursor_rules.md`:

- Always search for existing knowledge before adding new information
- Use specific entity type filters (`Preference`, `Procedure`, `Requirement`)
- Store new information immediately using `add_memory`
- Follow discovered procedures and respect established preferences

## Deployment

### Architecture

- **开发机**: Apple Silicon (arm64)
- **生产环境**: amd64 (linux/amd64)
- 本地 `docker compose up` 构建的是 arm64 镜像，仅供开发调试
- 生产部署必须使用 `docker buildx` 构建 amd64 镜像

### 构建 amd64 镜像（生产部署）

所有镜像都基于对应的 base 镜像。构建顺序：先 base，再业务镜像。

```bash
# 1. 基础镜像（仅在依赖变更时需要重建）
docker buildx build --platform linux/amd64 \
  -f Dockerfile.base -t graphiti-base:py3.12-amd64 --load .

docker buildx build --platform linux/amd64 \
  -f web_service/Dockerfile.base -t graphiti-web-base:node20-amd64 --load web_service/

# 2. 业务镜像（每次代码变更后重建）
# Server
docker buildx build --platform linux/amd64 \
  --build-arg BASE_IMAGE=graphiti-base:py3.12-amd64 \
  -f Dockerfile -t graphiti-server:amd64 --load .

# Web Service
docker buildx build --platform linux/amd64 \
  --build-arg BASE_IMAGE=graphiti-web-base:node20-amd64 \
  -f web_service/Dockerfile -t graphiti-web-service:amd64 --load web_service/

# MCP Server
docker buildx build --platform linux/amd64 \
  -f mcp_server/docker/Dockerfile -t graphiti-mcp-server:amd64 --load .
```

### 本地开发（arm64，无需指定 platform）

```bash
# 构建 base 镜像（首次或依赖变更时）
docker build -f Dockerfile.base -t graphiti-base:py3.12 .
docker build -f web_service/Dockerfile.base -t graphiti-web-base:node20 web_service/

# 启动服务
docker compose --profile all up -d          # 全部启动
docker compose --profile web-service up -d  # 仅 web-service
```

### 镜像标签约定

| 标签 | 架构 | 用途 |
|------|------|------|
| `:latest` | 本地开发机架构（arm64） | 本地开发调试 |
| `:amd64` | linux/amd64 | 生产环境部署 |
| `:py3.12` / `:node20` | 本地架构（arm64） | 本地开发基础镜像 |
| `:py3.12-amd64` / `:node20-amd64` | linux/amd64 | 生产构建基础镜像 |

### 验证镜像架构

```bash
docker inspect <image>:<tag> --format '{{.Architecture}}'
```