# syntax=docker/dockerfile:1.9
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Graphiti Embedding Service"
LABEL org.opencontainers.image.description="OpenAI-compatible embedding API powered by sentence-transformers"

# Install uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Create non-root user
RUN groupadd -r app && useradd -r -d /app -g app app

WORKDIR /app

# Install dependencies: CPU-only PyTorch + sentence-transformers + FastAPI
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv --clear && \
    . /app/.venv/bin/activate && \
    uv pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    uv pip install sentence-transformers fastapi uvicorn

# Copy application code
COPY main.py .

# Change ownership
RUN chown -R app:app /app

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

USER app

ENV PORT=8080
EXPOSE $PORT

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
