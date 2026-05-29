"""
Embedding Service — OpenAI-compatible embedding API powered by sentence-transformers.

Provides POST /v1/embeddings endpoint that matches the OpenAI API format,
allowing graph server and mcp-server to use OpenAIEmbedder with a custom base_url.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Configuration from environment
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
EMBEDDING_DIM = int(os.getenv('EMBEDDING_DIM', '384'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '4'))

# Global model reference (loaded at startup)
_model = None
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def _get_model():
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info(f'Loading embedding model: {EMBEDDING_MODEL} (device=cpu)')
        start = time.time()
        _model = SentenceTransformer(EMBEDDING_MODEL, device='cpu')
        logger.info(f'Model loaded in {time.time() - start:.1f}s, dim={EMBEDDING_DIM}')
    return _model


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load model at startup to avoid first-request latency."""
    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _get_model)
    yield
    # Shutdown
    _executor.shutdown(wait=False)


app = FastAPI(
    title='Graphiti Embedding Service',
    description='OpenAI-compatible embedding API powered by sentence-transformers',
    version='1.0.0',
    lifespan=lifespan,
)


# --- Request / Response models ---


class EmbeddingRequest(BaseModel):
    input: str | list[str]
    model: str = Field(default=EMBEDDING_MODEL)
    encoding_format: str = Field(default='float')


class EmbeddingObject(BaseModel):
    object: str = 'embedding'
    embedding: list[float]
    index: int


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: str = 'list'
    data: list[EmbeddingObject]
    model: str = EMBEDDING_MODEL
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)


# --- Endpoints ---


@app.post('/v1/embeddings', response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest):
    """Create embeddings for the given input text(s)."""
    try:
        import asyncio

        # Normalize input to list
        inputs = request.input if isinstance(request.input, list) else [request.input]

        if not inputs:
            raise HTTPException(status_code=400, detail='input must not be empty')

        # Run encoding in thread pool
        loop = asyncio.get_event_loop()
        model = _get_model()
        encode_fn = partial(model.encode, show_progress_bar=False)
        embeddings = await loop.run_in_executor(_executor, encode_fn, inputs)

        # Build response
        data = []
        for i, emb in enumerate(embeddings):
            vec = emb.tolist()[:EMBEDDING_DIM] if hasattr(emb, 'tolist') else list(emb)[:EMBEDDING_DIM]
            data.append(EmbeddingObject(embedding=vec, index=i))

        return EmbeddingResponse(data=data, model=EMBEDDING_MODEL)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception('Embedding error')
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/healthcheck')
async def healthcheck():
    model_loaded = _model is not None
    status = 'healthy' if model_loaded else 'loading'
    return JSONResponse(
        content={
            'status': status,
            'model': EMBEDDING_MODEL,
            'dimension': EMBEDDING_DIM,
        },
        status_code=200,
    )


@app.get('/health')
async def health():
    """Alias for Docker health checks that probe /health."""
    return await healthcheck()
