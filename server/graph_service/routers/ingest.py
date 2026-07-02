import asyncio
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial

from fastapi import APIRouter, status
from graphiti_core.nodes import EpisodeType  # type: ignore
from graphiti_core.utils.maintenance.graph_data_operations import clear_data  # type: ignore

from graph_service.dto import AddEntityNodeRequest, AddMessagesRequest, Message, Result
from graph_service.zep_graphiti import ZepGraphitiDep


@dataclass
class JobInfo:
    """Metadata for a queued or in-progress job."""
    name: str
    group_id: str
    status: str = 'pending'  # 'pending' | 'processing' | 'completed' | 'failed'
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None


class AsyncWorker:
    """Async job queue that tracks job metadata for status queries."""

    def __init__(self):
        self.queue: asyncio.Queue[tuple[partial, JobInfo]] = asyncio.Queue()
        self.task = None
        # All jobs since startup (including completed/failed) — capped to last 100
        self._jobs: list[JobInfo] = []
        self._current: JobInfo | None = None

    @property
    def pending(self) -> list[JobInfo]:
        return [j for j in self._jobs if j.status in ('pending', 'processing')]

    def get_status(self) -> dict:
        return {
            'current': {
                'name': self._current.name,
                'group_id': self._current.group_id,
                'status': self._current.status,
                'submitted_at': self._current.submitted_at,
            } if self._current else None,
            'queue_size': self.queue.qsize(),
            'pending': [
                {
                    'name': j.name,
                    'group_id': j.group_id,
                    'status': j.status,
                    'submitted_at': j.submitted_at,
                }
                for j in self.pending
            ],
        }

    async def worker(self):
        while True:
            try:
                print(f'Got a job: (size of remaining queue: {self.queue.qsize()})', flush=True, file=sys.stderr)
                job_fn, job_info = await self.queue.get()
                job_info.status = 'processing'
                self._current = job_info
                print(f'Processing job: {job_info.name}...', flush=True, file=sys.stderr)
                try:
                    await job_fn()
                    job_info.status = 'completed'
                    print(f'Job completed: {job_info.name}', flush=True, file=sys.stderr)
                except Exception as e:
                    job_info.status = 'failed'
                    job_info.error = str(e)
                    print(f'❌ Job failed [{job_info.name}]: {e}', flush=True, file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                finally:
                    self._current = None
                    self._trim()
            except asyncio.CancelledError:
                break

    def _trim(self):
        """Keep only the most recent 100 job records."""
        if len(self._jobs) > 100:
            self._jobs = self._jobs[-100:]

    async def start(self):
        self.task = asyncio.create_task(self.worker())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await self.task
        while not self.queue.empty():
            self.queue.get_nowait()

    def submit(self, job_fn: partial, info: JobInfo):
        self._jobs.append(info)
        self.queue.put_nowait((job_fn, info))


# 公开的 AsyncWorker 实例，供 main.py lifespan 使用
async_worker = AsyncWorker()


router = APIRouter()


@router.post('/messages', status_code=status.HTTP_202_ACCEPTED)
async def add_messages(
    request: AddMessagesRequest,
    graphiti: ZepGraphitiDep,
):
    group_id = request.group_id

    async def add_messages_task(m: Message):
        from graph_service.zep_graphiti import _build_client
        from graph_service.config import get_settings
        settings = get_settings()

        task_graphiti = _build_client(settings)
        try:
            print(f'  → Calling add_episode for: {m.name}', flush=True, file=sys.stderr)
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
            if hasattr(task_graphiti, 'close'):
                await task_graphiti.close()

    for m in request.messages:
        info = JobInfo(name=m.name, group_id=group_id)
        async_worker.submit(partial(add_messages_task, m), info)

    return Result(message='Messages added to processing queue', success=True)


@router.get('/queue/status', status_code=status.HTTP_200_OK)
async def get_queue_status():
    """Return pending and in-progress jobs for the documents page to display."""
    return async_worker.get_status()


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
