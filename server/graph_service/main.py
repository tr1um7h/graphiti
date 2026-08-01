from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from graph_service.config import get_settings
from graph_service.middleware import TracingMiddleware
from graph_service.routers import chat, entities, graph, ingest, retrieve, schemas
from graph_service.zep_graphiti import initialize_graphiti


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await initialize_graphiti(settings)
    # Ensure extraction_schemas table exists
    from graph_service.models import init_schemas_table

    await init_schemas_table(settings.postgres_age_dsn)
    # 启动 AsyncWorker 以处理消息队列
    await ingest.async_worker.start()
    yield
    # Shutdown
    await ingest.async_worker.stop()
    # No need to close Graphiti here, as it's handled per-request


app = FastAPI(lifespan=lifespan)

# Tracing middleware must be added before routers so it wraps all requests.
app.add_middleware(TracingMiddleware)


# Register routers
app.include_router(retrieve.router)
app.include_router(ingest.router)
app.include_router(graph.router, prefix='/rest')
app.include_router(entities.router, prefix='/rest')
app.include_router(schemas.router, prefix='/rest')
app.include_router(chat.router)


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)
