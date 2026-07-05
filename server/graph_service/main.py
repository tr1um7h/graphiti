from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from graph_service.config import get_settings
from graph_service.routers import data, entities, graph, ingest, retrieve
from graph_service.zep_graphiti import initialize_graphiti


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await initialize_graphiti(settings)
    # 启动 AsyncWorker 以处理消息队列
    await ingest.async_worker.start()
    yield
    # Shutdown
    await ingest.async_worker.stop()
    # No need to close Graphiti here, as it's handled per-request


app = FastAPI(lifespan=lifespan)


# Register routers
app.include_router(retrieve.router)
app.include_router(ingest.router)
app.include_router(graph.router, prefix='/rest')
app.include_router(entities.router, prefix='/rest')
app.include_router(data.router, prefix='/rest')


@app.get('/healthcheck')
async def healthcheck():
    return JSONResponse(content={'status': 'healthy'}, status_code=200)
