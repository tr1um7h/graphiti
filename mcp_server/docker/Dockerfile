# syntax=docker/dockerfile:1
# Standalone Graphiti MCP Server Image
# Connects to external PostgreSQL AGE and embedding service.
# 基于 graphiti-base:py3.12 统一基础镜像
#
# Build options (via --build-arg):
#   PIP_INDEX_URL    - Internal pip mirror URL for offline/mirror builds (default: empty, uses astral.sh)
#   PIP_TRUSTED_HOST - Trusted host for pip mirror (default: empty)
#
# Online build (default):
#   docker buildx build --platform linux/amd64 \
#     -f mcp_server/docker/Dockerfile -t graphiti-mcp-server --load .
#
# Offline/mirror build:
#   docker buildx build --platform linux/amd64 \
#     --build-arg PIP_INDEX_URL=http://internal-mirror/simple \
#     --build-arg PIP_TRUSTED_HOST=internal-mirror \
#     -f mcp_server/docker/Dockerfile -t graphiti-mcp-server --load .

# 透传离线构建参数（base 镜像需要）
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=

FROM graphiti-base:py3.12

# 透传 PIP_INDEX_URL/PIP_TRUSTED_HOST 给 uv（uv pip install / uv sync 会自动读取）
ENV UV_INDEX_URL=${PIP_INDEX_URL} \
    UV_ALLOW_INSECURE_HOST=${PIP_TRUSTED_HOST} \
    UV_INDEX_STRATEGY=unsafe-best-match

# ============================================================
# uv 已由 base 镜像预装，这里仅配置业务相关环境变量
# ============================================================
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    MCP_SERVER_HOST="0.0.0.0" \
    PYTHONUNBUFFERED=1

# Set up MCP server directory
WORKDIR /app/mcp

# Copy project files for dependency installation
COPY mcp_server/pyproject.toml mcp_server/uv.lock ./

# Copy graphiti-core with all needed files
COPY pyproject.toml README.md ./graphiti_core/
COPY graphiti_core /app/mcp/graphiti_core

# Install graphiti-core from local path, then sync remaining dependencies
RUN uv venv /app/mcp/.venv && \
    . /app/mcp/.venv/bin/activate && \
    uv pip install --no-deps -e ./graphiti_core && \
    uv sync --no-group dev && \
    uv pip install "pgvector>=0.3.6" "psycopg[binary,pool]>=3.2.0"

# Set up environment to use the venv
ENV VIRTUAL_ENV=/app/mcp/.venv
ENV PATH="/app/mcp/.venv/bin:${PATH}"

# Store graphiti-core version
RUN echo "0.29.1-local" > /app/mcp/.graphiti-core-version

# Copy MCP server application code
COPY mcp_server/main.py ./
COPY mcp_server/src/ ./src/
COPY mcp_server/config/ ./config/

# Copy preflight check script and entrypoint
COPY mcp_server/scripts/preflight_check.py ./scripts/preflight_check.py
COPY mcp_server/scripts/entrypoint.sh ./scripts/entrypoint.sh
RUN chmod +x ./scripts/entrypoint.sh

# Create log directory
RUN mkdir -p /var/log/graphiti

# Add Docker labels with version information
ARG MCP_SERVER_VERSION=1.0.3
ARG BUILD_DATE
ARG VCS_REF
LABEL org.opencontainers.image.title="Graphiti MCP Server (Standalone)" \
      org.opencontainers.image.description="Standalone Graphiti MCP server for external PostgreSQL AGE" \
      org.opencontainers.image.version="${MCP_SERVER_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Zep AI" \
      org.opencontainers.image.source="https://github.com/zep-ai/graphiti" \
      graphiti.core.version="0.29.1-local"

# Expose MCP server port
EXPOSE 8000

# Health check - verify MCP server is responding
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint: run preflight checks first, then start MCP server
ENTRYPOINT ["/app/mcp/scripts/entrypoint.sh"]
