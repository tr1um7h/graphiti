# syntax=docker/dockerfile:1.9
# Graphiti FastAPI Server
# 基于 graphiti-base:py3.12 统一基础镜像
#
# Build options (via --build-arg):
#   PIP_INDEX_URL    - Internal pip mirror URL for offline/mirror builds (default: empty, uses astral.sh)
#   PIP_TRUSTED_HOST - Trusted host for pip mirror (default: empty)

# 透传离线构建参数（base 镜像需要）
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=

FROM graphiti-base:py3.12

# Inherit build arguments for labels
ARG GRAPHITI_VERSION
ARG BUILD_DATE
ARG VCS_REF

# OCI image annotations
LABEL org.opencontainers.image.title="Graphiti FastAPI Server"
LABEL org.opencontainers.image.description="FastAPI server for Graphiti temporal knowledge graphs"
LABEL org.opencontainers.image.version="${GRAPHITI_VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.vendor="Zep AI"
LABEL org.opencontainers.image.source="https://github.com/getzep/graphiti"
LABEL org.opencontainers.image.documentation="https://github.com/getzep/graphiti/tree/main/server"
LABEL io.graphiti.core.version="${GRAPHITI_VERSION}"

# 透传 PIP_INDEX_URL/PIP_TRUSTED_HOST 给 uv（uv pip install / uv sync 会自动读取）
ENV UV_INDEX_URL=${PIP_INDEX_URL} \
    UV_ALLOW_INSECURE_HOST=${PIP_TRUSTED_HOST} \
    UV_INDEX_STRATEGY=unsafe-best-match

# Set up the server application
WORKDIR /app
COPY ./server/pyproject.toml ./server/README.md ./
COPY ./server/graph_service ./graph_service
COPY ./pyproject.toml ./README.md ./graphiti_core/
COPY ./graphiti_core ./graphiti_core

# Install server dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    rm -f uv.lock && \
    uv venv /app/.venv --clear && \
    . /app/.venv/bin/activate && \
    uv pip install --no-deps -e ./graphiti_core && \
   uv pip install pydantic psycopg[binary,pool] pgvector openai neo4j tenacity numpy python-dotenv uvicorn fastapi httpx pydantic-settings && \
    uv pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

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
