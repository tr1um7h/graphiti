"""Graph query, visualization, and group management routes"""

import functools
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from graph_service.dto import (
    GraphQueryRequest,
    GraphQueryResponse,
    GraphSchemaResponse,
    GraphSearchResult,
    GraphStatsResponse,
    SchemaNodeLabel,
    SchemaRelationshipType,
    TimelineItem,
)
from graph_service.zep_graphiti import ZepGraphitiDep

router = APIRouter()

# Canonical table names (9 tables: 4 node + 5 edge)
_ALL_TABLES = [
    'entity_nodes',
    'episodic_nodes',
    'community_nodes',
    'saga_nodes',
    'entity_edges',
    'episodic_edges',
    'community_edges',
    'has_episode_edges',
    'next_episode_edges',
]

# Node tables in dependency order (episodic_nodes before saga_nodes due to FK)
_NODE_TABLES = [
    'entity_nodes',
    'episodic_nodes',
    'community_nodes',
    'saga_nodes',
]

# Edge tables — all depend on already-copied nodes
_EDGE_TABLES = [
    'entity_edges',
    'episodic_edges',
    'community_edges',
    'has_episode_edges',
    'next_episode_edges',
]


class CloneGroupRequest(BaseModel):
    """Request body for group clone endpoint."""

    new_group_id: str


def _graph_endpoint(func: Callable) -> Callable:
    """Decorator that wraps graph API endpoints with standard error handling.

    Catches all unhandled exceptions, logs them with a traceback, and
    re-raises as HTTP 500.  HTTPException instances pass through unchanged.
    Non-Response return values are serialized via JSONResponse with a
    ``default=str`` fallback for complex types (numpy arrays, UUIDs, etc.).
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            result = await func(*args, **kwargs)
            if isinstance(result, JSONResponse):
                return result
            return JSONResponse(content=json.loads(json.dumps(result, default=str)))
        except HTTPException:
            raise
        except Exception as e:
            import traceback

            print(f'Error in {func.__name__}: {e}', flush=True)
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e)) from None

    return wrapper


def _get_schema(driver: Any) -> str:
    """Get schema from driver (works with PostgresAgeDriver)."""
    return getattr(driver, 'schema', 'public')  # type: ignore[attr-defined]


@router.get('/graph/stats', status_code=status.HTTP_200_OK)
async def get_graph_stats(graphiti: ZepGraphitiDep):
    """
    Get graph statistics.

    Returns counts of nodes, edges, documents, and conversations,
    including today's new additions.
    """
    try:
        driver = graphiti.driver
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # 使用 SQL 查询（AGE 底层是 SQL 表）
        # Get all entity nodes
        nodes_result, _, _ = await driver.execute_query(
            'SELECT COUNT(*) as count FROM entity_nodes'
        )
        total_nodes = nodes_result[0]['count'] if nodes_result else 0

        # Get all entity edges
        edges_result, _, _ = await driver.execute_query(
            'SELECT COUNT(*) as count FROM entity_edges'
        )
        total_edges = edges_result[0]['count'] if edges_result else 0

        # Get documents (EpisodicNode with source='text' or 'message')
        docs_result, _, _ = await driver.execute_query(
            "SELECT COUNT(*) as count FROM episodic_nodes WHERE source IN ('text', 'message')"
        )
        total_documents = docs_result[0]['count'] if docs_result else 0

        # Get conversations (subset of EpisodicNode)
        total_conversations = total_documents

        # Calculate today's additions
        today_nodes, _, _ = await driver.execute_query(
            'SELECT COUNT(*) as count FROM entity_nodes WHERE created_at >= %s',
            params=(today_start,),
        )
        today_new_nodes = today_nodes[0]['count'] if today_nodes else 0

        today_edges, _, _ = await driver.execute_query(
            'SELECT COUNT(*) as count FROM entity_edges WHERE created_at >= %s',
            params=(today_start,),
        )
        today_new_edges = today_edges[0]['count'] if today_edges else 0

        today_docs, _, _ = await driver.execute_query(
            "SELECT COUNT(*) as count FROM episodic_nodes WHERE source IN ('text', 'message') AND created_at >= %s",
            params=(today_start,),
        )
        today_new_documents = today_docs[0]['count'] if today_docs else 0

        return GraphStatsResponse(
            totalNodes=total_nodes,
            totalEdges=total_edges,
            totalDocuments=total_documents,
            totalConversations=total_conversations,
            todayNewNodes=today_new_nodes,
            todayNewEdges=today_new_edges,
            todayNewDocuments=today_new_documents,
            todayNewConversations=today_new_documents,
        )
    except Exception as e:
        import traceback

        print(f'❌ Error in get_graph_stats: {e}', flush=True)
        traceback.print_exc()
        return GraphStatsResponse()


@router.get('/graph/groups', status_code=status.HTTP_200_OK)
async def get_graph_groups(graphiti: ZepGraphitiDep):
    """
    Get all available group IDs.

    Returns list of group IDs with node counts.
    """
    try:
        driver = graphiti.driver

        results, _, _ = await driver.execute_query(
            """
            SELECT group_id, COUNT(*) as count
            FROM episodic_nodes
            GROUP BY group_id
            ORDER BY count DESC
            """
        )

        groups = []
        for record in results or []:
            groups.append(
                {
                    'id': record.get('group_id', ''),
                    'name': record.get('group_id', ''),
                    'count': record.get('count', 0),
                }
            )

        return groups
    except Exception as e:
        print(f'❌ Error in get_graph_groups: {e}', flush=True)
        import traceback

        traceback.print_exc()
        return []


@router.post('/graph/query', status_code=status.HTTP_200_OK)
async def query_graph(request: GraphQueryRequest, graphiti: ZepGraphitiDep):
    """
    Query graph data for visualization.

    Returns nodes and edges for graph visualization.
    """
    try:
        driver = graphiti.driver

        # Query nodes - 使用 SQL
        group_filter = ''
        params: dict = {'limit': request.limit}

        if request.group_ids:
            group_filter = 'AND group_id = ANY(%(group_ids)s)'
            params['group_ids'] = request.group_ids

        nodes_result, _, _ = await driver.execute_query(
            f"""
            SELECT uuid, name, labels, summary, attributes
            FROM entity_nodes
            WHERE 1=1 {group_filter}
            LIMIT %(limit)s
            """,
            params=params,
        )

        nodes = []
        for record in nodes_result or []:
            labels = record.get('labels', [])
            if isinstance(labels, str):
                labels = [labels] if labels else []

            nodes.append(
                {
                    'id': record.get('uuid', ''),
                    'name': record.get('name', ''),
                    'labels': labels,
                    'summary': record.get('summary', ''),
                    'attributes': record.get('attributes', {}) or {},
                }
            )

        # Query edges
        node_uuids = [n['id'] for n in nodes]
        edges = []

        if node_uuids:
            edges_result, _, _ = await driver.execute_query(
                """
                SELECT e.uuid, e.name, e.fact, e.created_at,
                       e.source_node_uuid, e.target_node_uuid
                FROM entity_edges e
                WHERE e.source_node_uuid = ANY(%(node_uuids)s) 
                   OR e.target_node_uuid = ANY(%(node_uuids)s)
                LIMIT 2000
                """,
                params={'node_uuids': node_uuids},
            )

            for record in edges_result or []:
                edges.append(
                    {
                        'id': record.get('uuid', ''),
                        'source_node_uuid': record.get('source_node_uuid', ''),
                        'target_node_uuid': record.get('target_node_uuid', ''),
                        'name': record.get('name', ''),
                        'fact': record.get('fact', ''),
                        'created_at': record.get('created_at', datetime.now(timezone.utc)),
                    }
                )

        return GraphQueryResponse(nodes=nodes, edges=edges)
    except Exception as e:
        import traceback

        print(f'❌ Error in query_graph: {e}', flush=True)
        traceback.print_exc()
        return GraphQueryResponse(nodes=[], edges=[])


@router.get('/graph/search', status_code=status.HTTP_200_OK)
async def search_graph(q: str, graphiti: ZepGraphitiDep):
    """
    Search for entities in the graph by name.

    Returns matching entities based on name matching.
    """
    if not q:
        return []

    try:
        # 直接搜索节点，而不是边
        # 使用 SQL LIKE 查询模糊匹配节点名称
        pattern = f'%{q}%'
        print(f'🔍 Searching nodes with pattern: {pattern}', flush=True)

        results, _, _ = await graphiti.driver.execute_query(
            """
            SELECT uuid, name, labels, summary, attributes
            FROM entity_nodes
            WHERE name ILIKE %s
            LIMIT 20
            """,
            params=(pattern,),
        )

        print(f'📊 Found {len(results or [])} nodes', flush=True)

        # 转换为前端期望的格式
        entities = []
        for record in results or []:
            labels = record.get('labels', [])
            if isinstance(labels, str):
                labels = [labels] if labels else []

            entities.append(
                {
                    'id': record.get('uuid', ''),
                    'name': record.get('name', ''),
                    'type': labels[0] if labels else 'Entity',
                }
            )

        return entities
    except Exception as e:
        print(f'❌ Error in search_graph: {e}', flush=True)
        import traceback

        traceback.print_exc()
        return []


@router.get('/graph/schema', status_code=status.HTTP_200_OK)
async def get_graph_schema(graphiti: ZepGraphitiDep):
    """
    Get graph schema information.

    Returns node labels and relationship types with their counts.
    """
    try:
        driver = graphiti.driver

        # Query node count
        nodes_result, _, _ = await driver.execute_query(
            'SELECT COUNT(*) as count FROM entity_nodes'
        )
        total_nodes = nodes_result[0]['count'] if nodes_result else 0

        node_labels = [SchemaNodeLabel(label='Entity', count=total_nodes)]

        # Query relationship types
        edges_result, _, _ = await driver.execute_query(
            """
            SELECT name as type, COUNT(*) as count
            FROM entity_edges
            GROUP BY name
            ORDER BY count DESC
            """
        )

        relationship_types = []
        for record in edges_result or []:
            relationship_types.append(
                SchemaRelationshipType(
                    type=record.get('type', 'UNKNOWN'), count=record.get('count', 0)
                )
            )

        return GraphSchemaResponse(nodeLabels=node_labels, relationshipTypes=relationship_types)
    except Exception as e:
        import traceback

        print(f'❌ Error in get_graph_schema: {e}', flush=True)
        traceback.print_exc()
        return GraphSchemaResponse(nodeLabels=[], relationshipTypes=[])


@router.get('/graph/timeline', status_code=status.HTTP_200_OK)
async def get_graph_timeline(graphiti: ZepGraphitiDep, limit: int = 20):
    """
    Get recent activity timeline.

    Returns recent episodes and their associated activities.
    """
    try:
        driver = graphiti.driver

        # Get recent episodes - 使用 SQL
        episodes_result, _, _ = await driver.execute_query(
            """
            SELECT uuid, name, source, source_description, content,
                   created_at, entity_edges
            FROM episodic_nodes
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params=(limit,),
        )

        timeline = []
        for record in episodes_result or []:
            source = record.get('source', 'text')
            entity_edges = record.get('entity_edges', [])
            if isinstance(entity_edges, str):
                entity_edges = [entity_edges] if entity_edges else []

            # Determine activity type and description
            if source in ['text', 'message']:
                activity_type = 'document' if source == 'text' else 'episode'
                description = f'{record.get("name", "Untitled")} ({len(entity_edges)} edges)'
                source_info = record.get('source_description', '')
            else:
                activity_type = 'episode'
                description = record.get('name', 'Untitled')
                source_info = record.get('source_description', '')

            created_at = record.get('created_at', datetime.now(timezone.utc))
            if isinstance(created_at, str):
                time_str = created_at
            else:
                time_str = created_at.isoformat()

            timeline.append(
                TimelineItem(
                    type=activity_type, description=description, source=source_info, time=time_str
                )
            )

        return timeline
    except Exception as e:
        import traceback

        print(f'❌ Error in get_graph_timeline: {e}', flush=True)
        traceback.print_exc()
        return []


# ---------------------------------------------------------------------------
# POST /graph/groups/{group_id}/clone — clone a group at the DB level
# ---------------------------------------------------------------------------
@router.post('/graph/groups/{group_id}/clone', status_code=status.HTTP_201_CREATED)
@_graph_endpoint
async def clone_group(
    group_id: str,
    body: CloneGroupRequest,
    graphiti: ZepGraphitiDep = ...,  # type: ignore[assignment]
):
    """
    Clone a group by copying all its data to a new group_id at the database level.

    - All 9 tables are copied (4 node + 5 edge).
    - New UUIDs are generated; foreign keys between tables are remapped.
    - The AGE graph projection is rebuilt automatically after the copy.
    """
    new_group_id = body.new_group_id.strip()
    if not new_group_id:
        raise HTTPException(status_code=400, detail='new_group_id must not be empty')

    driver = graphiti.driver
    schema = _get_schema(driver)

    # 1. Verify source group exists
    check_result, _, _ = await driver.execute_query(
        f'SELECT COUNT(*) as count FROM {schema}.entity_nodes WHERE group_id = %(group_id)s',
        params={'group_id': group_id},
    )
    if not check_result or check_result[0].get('count', 0) == 0:
        raise HTTPException(status_code=404, detail=f"Source group '{group_id}' not found or empty")

    # 2. Check target group doesn't already exist
    target_check, _, _ = await driver.execute_query(
        f'SELECT COUNT(*) as count FROM {schema}.entity_nodes WHERE group_id = %(group_id)s',
        params={'group_id': new_group_id},
    )
    if target_check and target_check[0].get('count', 0) > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Target group '{new_group_id}' already contains data. Choose a different name.",
        )

    # 3. Global UUID map: old_uuid -> new_uuid (shared across all node tables)
    uuid_map: dict[str, str] = {}

    # Helper: convert non-JSON-safe values for psycopg INSERT
    def _safe_value(v: Any) -> Any:
        if isinstance(v, dict):
            return json.dumps(v)
        if isinstance(v, list):
            return [json.dumps(item) if isinstance(item, dict) else item for item in v]
        if isinstance(v, datetime):
            return v  # psycopg handles datetime natively
        return v

    # 4. Copy node tables in dependency order
    for table_name in _NODE_TABLES:
        rows, _, _ = await driver.execute_query(
            f'SELECT * FROM {schema}.{table_name} WHERE group_id = %(group_id)s ORDER BY uuid',
            params={'group_id': group_id},
        )
        if not rows:
            continue

        for row in rows:
            old_uuid = str(row['uuid'])
            new_uuid = str(uuid4())
            uuid_map[old_uuid] = new_uuid

            # Build column list, skipping GENERATED columns
            cols = []
            vals = {}
            for k, v in row.items():
                if k == 'search_vector':
                    continue
                if k == 'uuid':
                    cols.append(k)
                    vals[k] = new_uuid
                elif k == 'group_id':
                    cols.append(k)
                    vals[k] = new_group_id
                else:
                    cols.append(k)
                    vals[k] = _safe_value(v)

            cols_str = ', '.join(cols)
            placeholders = ', '.join(f'%({c})s' for c in cols)
            await driver.execute_query(
                f'INSERT INTO {schema}.{table_name} ({cols_str}) VALUES ({placeholders})',
                params=vals,
            )

    # 5. Copy edge tables, remapping source/target node UUIDs
    for table_name in _EDGE_TABLES:
        rows, _, _ = await driver.execute_query(
            f'SELECT * FROM {schema}.{table_name} WHERE group_id = %(group_id)s ORDER BY uuid',
            params={'group_id': group_id},
        )
        if not rows:
            continue

        for row in rows:
            cols = []
            vals = {}
            for k, v in row.items():
                if k == 'search_vector':
                    continue
                if k == 'uuid':
                    cols.append(k)
                    vals[k] = str(uuid4())
                elif k == 'group_id':
                    cols.append(k)
                    vals[k] = new_group_id
                elif k in ('source_node_uuid', 'target_node_uuid'):
                    cols.append(k)
                    vals[k] = uuid_map.get(str(v), str(v))
                else:
                    cols.append(k)
                    vals[k] = _safe_value(v)

            cols_str = ', '.join(cols)
            placeholders = ', '.join(f'%({c})s' for c in cols)
            await driver.execute_query(
                f'INSERT INTO {schema}.{table_name} ({cols_str}) VALUES ({placeholders})',
                params=vals,
            )

    # 6. Rebuild AGE graph projection (includes all groups)
    await driver.graph_ops.rebuild_age_projection(driver)

    # 7. Build table counts for response
    table_counts: dict[str, int] = {}
    for table_name in _ALL_TABLES:
        count_result, _, _ = await driver.execute_query(
            f'SELECT COUNT(*) as count FROM {schema}.{table_name} WHERE group_id = %(group_id)s',
            params={'group_id': new_group_id},
        )
        table_counts[table_name] = count_result[0].get('count', 0) if count_result else 0

    return {
        'success': True,
        'source': group_id,
        'target': new_group_id,
        'table_counts': table_counts,
    }
