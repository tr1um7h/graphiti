# syntax=docker/dockerfile:1.9
#
# Graphiti FastAPI Server
# 基于 graphiti-base:py3.12 统一基础镜像（支持 PIP_INDEX_URL 离线构建）
#
# 内网构建示例:
#   docker buildx build --platform linux/amd64 \
#     --build-arg PIP_INDEX_URL=http://internal-pypi/simple \
#     --build-arg PIP_TRUSTED_HOST=internal-pypi \
#     --build-arg GRAPHITI_VERSION=0.29.1 \
#     --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
#     --build-arg VCS_REF=$(git rev-parse --short HEAD) \
#     -t graphiti-server:amd64 --load .

# 透传离线构建参数
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=

FROM graphiti-base:py3.12

# 透传 PIP_INDEX_URL/PIP_TRUSTED_HOST 给 uv（uv pip install 会自动读取 UV_INDEX_URL/UV_ALLOW_INSECURE_HOST）
ENV UV_INDEX_URL=${PIP_INDEX_URL} \
    UV_ALLOW_INSECURE_HOST=${PIP_TRUSTED_HOST} \
    UV_INDEX_STRATEGY=unsafe-best-match

# Inherit build arguments for labels
ARG GRAPHITI_VERSION
ARG BUILD_DATE
ARG VCS_REF

# OCI image annotations
LABEL org.opencontainers.image.title="Graphiti FastAPI Server" \
      org.opencontainers.image.description="FastAPI server for Graphiti temporal knowledge graphs" \
      org.opencontainers.image.version="${GRAPHITI_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Zep AI" \
      org.opencontainers.image.source="https://github.com/getzep/graphiti" \
      org.opencontainers.image.documentation="https://github.com/getzep/graphiti/tree/main/server" \
      io.graphiti.core.version="${GRAPHITI_VERSION}"

# Set up the server application first
WORKDIR /app
COPY ./server/pyproject.toml ./server/README.md ./
COPY ./server/graph_service ./graph_service
COPY ./pyproject.toml ./README.md ./graphiti_core/
COPY ./graphiti_core ./graphiti_core

# Install server dependencies
# 离线构建时，uv pip install 会自动使用 build-arg 传入的 PIP_INDEX_URL
RUN --mount=type=cache,target=/root/.cache/uv \
    rm -f uv.lock && \
    uv venv /app/.venv --clear && \
    . /app/.venv/bin/activate && \
    uv pip install --no-deps -e ./graphiti_core && \
    uv pip install pydantic psycopg[binary,pool] pgvector openai neo4j tenacity numpy python-dotenv posthog uvicorn fastapi httpx pydantic-settings sentence-transformers

# Change ownership to app user
RUN chown -R app:app /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER app

# Set port
ENV PORT=8000
EXPOSE $PORT

# Use venv python directly to avoid runtime build
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "graph_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
