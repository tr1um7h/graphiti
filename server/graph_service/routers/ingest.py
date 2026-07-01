import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from functools import partial

from fastapi import APIRouter, FastAPI, status
from graphiti_core.nodes import EpisodeType  # type: ignore
from graphiti_core.utils.maintenance.graph_data_operations import clear_data  # type: ignore

from graph_service.dto import AddEntityNodeRequest, AddMessagesRequest, Message, Result
from graph_service.zep_graphiti import ZepGraphitiDep


class AsyncWorker:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.task = None

    async def worker(self):
        while True:
            try:
                print(f'Got a job: (size of remaining queue: {self.queue.qsize()})', flush=True, file=sys.stderr)
                job = await self.queue.get()
                print(f'Processing job...', flush=True, file=sys.stderr)
                await job()
                print(f'Job completed', flush=True, file=sys.stderr)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f'❌ Job failed with error: {e}', flush=True, file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

    async def start(self):
        self.task = asyncio.create_task(self.worker())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await self.task
        while not self.queue.empty():
            self.queue.get_nowait()


# 公开的 AsyncWorker 实例，供 main.py lifespan 使用
async_worker = AsyncWorker()


router = APIRouter()


@router.post('/messages', status_code=status.HTTP_202_ACCEPTED)
async def add_messages(
    request: AddMessagesRequest,
    graphiti: ZepGraphitiDep,
):
    # 保存必要的参数，避免闭包引用已清理的 graphiti
    group_id = request.group_id
    
    async def add_messages_task(m: Message):
        # 为每个后台任务创建新的 graphiti 实例
        from graph_service.zep_graphiti import ZepGraphiti, _create_llm_client, _create_embedder
        from graph_service.config import get_settings
        settings = get_settings()
        
        # 创建 LLM client 和 embedder
        llm_client = _create_llm_client(settings)
        embedder = _create_embedder(settings)
        
        task_graphiti = ZepGraphiti(
            graph_driver=None,  # 会使用默认驱动
            llm_client=llm_client,
            embedder=embedder,
        )
        try:
            print(f'  → Calling add_episode for: {m.name}', flush=True, file=sys.stderr)
            # 不传 uuid，让 add_episode 自动生成
            await task_graphiti.add_episode(
                name=m.name,
                episode_body=f'{m.role or ""}({m.role_type}): {m.content}',
                reference_time=m.timestamp,
                source=EpisodeType.message,
                source_description=m.source_description,
                group_id=group_id,
            )
            print(f'  ✓ add_episode completed for: {m.name}', flush=True, file=sys.stderr)
        finally:
            # 清理资源
            if hasattr(task_graphiti, 'close'):
                await task_graphiti.close()

    for m in request.messages:
        await async_worker.queue.put(partial(add_messages_task, m))

    return Result(message='Messages added to processing queue', success=True)


@router.post('/entity-node', status_code=status.HTTP_201_CREATED)
async def add_entity_node(
    request: AddEntityNodeRequest,
    graphiti: ZepGraphitiDep,
):
    node = await graphiti.save_entity_node(
        uuid=request.uuid,
        group_id=request.group_id,
        name=request.name,
        summary=request.summary,
    )
    return node


@router.delete('/entity-edge/{uuid}', status_code=status.HTTP_200_OK)
async def delete_entity_edge(uuid: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_entity_edge(uuid)
    return Result(message='Entity Edge deleted', success=True)


@router.delete('/group/{group_id}', status_code=status.HTTP_200_OK)
async def delete_group(group_id: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_group(group_id)
    return Result(message='Group deleted', success=True)


@router.delete('/episode/{uuid}', status_code=status.HTTP_200_OK)
async def delete_episode(uuid: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_episodic_node(uuid)
    return Result(message='Episode deleted', success=True)


@router.post('/clear', status_code=status.HTTP_200_OK)
async def clear(
    graphiti: ZepGraphitiDep,
):
    await clear_data(graphiti.driver)
    await graphiti.build_indices_and_constraints()
    return Result(message='Graph cleared', success=True)
