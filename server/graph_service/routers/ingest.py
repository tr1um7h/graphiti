import asyncio
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from graphiti_core.nodes import EpisodeType  # type: ignore
from graphiti_core.utils.maintenance.graph_data_operations import clear_data  # type: ignore

from graph_service.dto import (
    AddEntityNodeRequest,
    AddEpisodeRequest,
    AddMessagesRequest,
    CommitMemoryRequest,
    Message,
    PreviewMemoryRequest,
    Result,
)
from graph_service.zep_graphiti import ZepGraphitiDep


async def _resolve_schema_params(schema_id: int | None):
    """Resolve a schema_id into Graphiti extraction parameters.

    Returns (entity_types, edge_types, custom_extraction_instructions).
    """
    if schema_id is None:
        return None, None, None

    from graph_service.config import get_settings
    from graph_service.models import build_extraction_params, get_schema

    settings = get_settings()
    schema = await get_schema(settings.postgres_age_dsn, schema_id)
    if not schema:
        return None, None, None

    return build_extraction_params(schema)


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
            }
            if self._current
            else None,
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
                print(
                    f'Got a job: (size of remaining queue: {self.queue.qsize()})',
                    flush=True,
                    file=sys.stderr,
                )
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
        from graph_service.config import get_settings
        from graph_service.zep_graphiti import _build_client

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


@router.post('/add-episode', status_code=status.HTTP_202_ACCEPTED)
async def add_episode(
    request: AddEpisodeRequest,
    graphiti: ZepGraphitiDep,
):
    """Submit raw content for extraction without chat-style role prefix."""

    async def episode_task():
        from graph_service.config import get_settings
        from graph_service.zep_graphiti import _build_client

        settings = get_settings()
        task_graphiti = _build_client(settings)
        try:
            print(f'  -> Calling add_episode for: {request.name}', flush=True, file=sys.stderr)
            entity_types, edge_types, custom_instructions = await _resolve_schema_params(
                request.schema_id
            )

            await task_graphiti.add_episode(
                name=request.name,
                episode_body=request.content,
                reference_time=datetime.now(timezone.utc),
                source=EpisodeType.text,
                source_description=request.source_description,
                group_id=request.group_id,
                entity_types=entity_types,
                edge_types=edge_types,
                custom_extraction_instructions=custom_instructions,
            )
            print(
                f'  \u2713 add_episode completed for: {request.name}', flush=True, file=sys.stderr
            )
        finally:
            if hasattr(task_graphiti, 'close'):
                await task_graphiti.close()

    info = JobInfo(name=request.name, group_id=request.group_id)
    async_worker.submit(partial(episode_task), info)

    return Result(message='Episode added to processing queue', success=True)


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


# ---------------------------------------------------------------------------
# Preview / Commit endpoints (two-step add memory)
# ---------------------------------------------------------------------------


@dataclass
class PreviewTask:
    """In-memory record for an async preview task."""

    task_id: str
    status: str = 'pending'
    stage: str | None = None
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PreviewStore:
    """In-memory cache for preview task results with 30-minute TTL."""

    def __init__(self, ttl_seconds: int = 1800):
        self._tasks: dict[str, PreviewTask] = {}
        self._ttl = ttl_seconds

    def create(self, task_id: str) -> PreviewTask:
        self._cleanup_expired()
        task = PreviewTask(task_id=task_id)
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> PreviewTask | None:
        self._cleanup_expired()
        return self._tasks.get(task_id)

    def _cleanup_expired(self):
        cutoff = datetime.now(timezone.utc).timestamp() - self._ttl
        expired = [tid for tid, t in self._tasks.items() if t.created_at.timestamp() < cutoff]
        for tid in expired:
            del self._tasks[tid]


preview_store = PreviewStore()


def _serialize_preview_result(result, uuid_map: dict[str, str]) -> dict:
    """Convert PreviewEpisodeResults to a JSON-serialisable dict."""
    episode = result.episode
    nodes = []
    for node in result.nodes:
        # A node is 'new' if its UUID was not remapped to a different existing UUID
        is_new = not any(v == node.uuid and k != node.uuid for k, v in uuid_map.items())
        nodes.append(
            {
                'uuid': node.uuid,
                'name': node.name,
                'labels': node.labels or [],
                'summary': node.summary or '',
                'group_id': node.group_id,
                'is_new': is_new,
            }
        )

    def _edge_to_dict(edge, node_name_map: dict[str, str]) -> dict:
        return {
            'uuid': edge.uuid,
            'name': edge.name or '',
            'fact': edge.fact or '',
            'source_node_uuid': edge.source_node_uuid,
            'source_node_name': node_name_map.get(edge.source_node_uuid, ''),
            'target_node_uuid': edge.target_node_uuid,
            'target_node_name': node_name_map.get(edge.target_node_uuid, ''),
            'valid_at': edge.valid_at.isoformat() if edge.valid_at else None,
            'invalid_at': edge.invalid_at.isoformat() if edge.invalid_at else None,
            'expired_at': edge.expired_at.isoformat() if edge.expired_at else None,
        }

    node_name_map = {n.uuid: n.name for n in result.nodes}
    edges = [_edge_to_dict(e, node_name_map) for e in result.edges]
    invalidated = [_edge_to_dict(e, node_name_map) for e in result.invalidated_edges]

    return {
        'episode': {
            'uuid': episode.uuid,
            'name': episode.name,
            'content': episode.content,
            'group_id': episode.group_id,
            'source': episode.source.value
            if hasattr(episode.source, 'value')
            else str(episode.source),
            'source_description': episode.source_description,
        },
        'nodes': nodes,
        'edges': edges,
        'invalidated_edges': invalidated,
    }


@router.post('/preview-memory', status_code=status.HTTP_202_ACCEPTED)
async def preview_memory(request: PreviewMemoryRequest):
    """Submit an async preview task that extracts entities and edges from content."""
    task_id = str(uuid4())
    task = preview_store.create(task_id)

    async def preview_task():
        from graph_service.config import get_settings
        from graph_service.zep_graphiti import _build_client

        settings = get_settings()
        task_graphiti = _build_client(settings)
        try:
            task.status = 'processing'

            try:
                source_type = EpisodeType[request.source.lower()]
            except (KeyError, AttributeError):
                source_type = EpisodeType.text

            entity_types, edge_types, custom_instructions = await _resolve_schema_params(
                request.schema_id
            )

            result = await task_graphiti.preview_episode(
                name=request.name or f'Preview: {request.content[:50]}',
                episode_body=request.content,
                source_description=request.source_description,
                reference_time=datetime.now(timezone.utc),
                source=source_type,
                group_id=request.group_id,
                entity_types=entity_types,
                edge_types=edge_types,
                custom_extraction_instructions=custom_instructions,
                stage_callback=lambda s: setattr(task, 'stage', s),
            )

            # We need the uuid_map to compute is_new; re-derive from result
            # The uuid_map is not directly available, so we approximate:
            # nodes that already exist in the graph will have been fetched by
            # resolve_extracted_nodes and keep their existing UUID.
            uuid_map = {n.uuid: n.uuid for n in result.nodes}

            task.result = _serialize_preview_result(result, uuid_map)
            task.status = 'completed'
            task.stage = 'done'
            print(f'  \u2713 preview task completed: {task_id}', flush=True, file=sys.stderr)
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            print(f'  \u2717 preview task failed [{task_id}]: {e}', flush=True, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
        finally:
            if hasattr(task_graphiti, 'close'):
                await task_graphiti.close()

    # Submit to the shared async worker
    info = JobInfo(name=f'preview-{task_id}', group_id=request.group_id)
    async_worker.submit(partial(preview_task), info)

    return {'task_id': task_id, 'status': 'pending'}


@router.get('/preview-memory/{task_id}', status_code=status.HTTP_200_OK)
async def get_preview_status(task_id: str):
    """Poll for the status and result of a preview task."""
    task = preview_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail='Preview task not found')

    response: dict = {
        'task_id': task.task_id,
        'status': task.status,
        'stage': task.stage,
        'error': task.error,
        'result': task.result,
    }
    return response


@router.post('/commit-memory', status_code=status.HTTP_200_OK)
async def commit_memory(
    request: CommitMemoryRequest,
    graphiti: ZepGraphitiDep,
):
    """Write user-confirmed entities and edges to the graph."""
    from graphiti_core.edges import EntityEdge  # type: ignore
    from graphiti_core.nodes import EntityNode, EpisodicNode  # type: ignore

    # Reconstruct EpisodicNode from preview data
    ep = request.episode
    episode = EpisodicNode(
        uuid=ep.uuid,
        name=ep.name,
        group_id=ep.group_id,
        labels=[],
        source=EpisodeType[ep.source] if ep.source in EpisodeType.__members__ else EpisodeType.text,
        content=ep.content,
        source_description=ep.source_description,
        created_at=datetime.now(timezone.utc),
        valid_at=datetime.now(timezone.utc),
    )

    # Reconstruct EntityNodes
    nodes: list[EntityNode] = []
    for nc in request.nodes:
        node = EntityNode(
            uuid=nc.uuid,
            name=nc.name,
            labels=nc.labels,
            group_id=request.group_id,
            summary=nc.summary,
        )
        nodes.append(node)

    # Reconstruct EntityEdges
    entity_edges: list[EntityEdge] = []
    now = datetime.now(timezone.utc)
    for ec in request.edges:
        edge = EntityEdge(
            uuid=ec.uuid,
            name=ec.name,
            fact=ec.fact,
            source_node_uuid=ec.source_node_uuid,
            target_node_uuid=ec.target_node_uuid,
            valid_at=ec.valid_at,
            invalid_at=ec.invalid_at,
            expired_at=ec.expired_at,
            group_id=request.group_id,
            created_at=now,
        )
        entity_edges.append(edge)

    try:
        await graphiti.commit_episode(
            episode=episode,
            nodes=nodes,
            entity_edges=entity_edges,
            group_id=request.group_id,
            update_communities=request.update_communities,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Commit failed: {e}') from e

    return Result(message='Committed to graph', success=True)
