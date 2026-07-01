"""Graph query and visualization routes"""

from datetime import datetime, timezone

from fastapi import APIRouter, status

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
            "SELECT COUNT(*) as count FROM entity_nodes"
        )
        total_nodes = nodes_result[0]['count'] if nodes_result else 0
        
        # Get all entity edges
        edges_result, _, _ = await driver.execute_query(
            "SELECT COUNT(*) as count FROM entity_edges"
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
            "SELECT COUNT(*) as count FROM entity_nodes WHERE created_at >= %s",
            params=(today_start,)
        )
        today_new_nodes = today_nodes[0]['count'] if today_nodes else 0
        
        today_edges, _, _ = await driver.execute_query(
            "SELECT COUNT(*) as count FROM entity_edges WHERE created_at >= %s",
            params=(today_start,)
        )
        today_new_edges = today_edges[0]['count'] if today_edges else 0
        
        today_docs, _, _ = await driver.execute_query(
            "SELECT COUNT(*) as count FROM episodic_nodes WHERE source IN ('text', 'message') AND created_at >= %s",
            params=(today_start,)
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
            FROM entity_nodes
            GROUP BY group_id
            ORDER BY count DESC
            """
        )
        
        groups = []
        for record in results or []:
            groups.append({
                'id': record.get('group_id', ''),
                'name': record.get('group_id', ''),
                'count': record.get('count', 0)
            })
        
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
            params=params
        )
        
        nodes = []
        for record in nodes_result or []:
            labels = record.get('labels', [])
            if isinstance(labels, str):
                labels = [labels] if labels else []
            
            nodes.append({
                'id': record.get('uuid', ''),
                'name': record.get('name', ''),
                'labels': labels,
                'summary': record.get('summary', ''),
                'attributes': record.get('attributes', {}) or {}
            })
        
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
                params={'node_uuids': node_uuids}
            )
            
            for record in edges_result or []:
                edges.append({
                    'id': record.get('uuid', ''),
                    'source_node_uuid': record.get('source_node_uuid', ''),
                    'target_node_uuid': record.get('target_node_uuid', ''),
                    'name': record.get('name', ''),
                    'fact': record.get('fact', ''),
                    'created_at': record.get('created_at', datetime.now(timezone.utc))
                })
        
        return GraphQueryResponse(nodes=nodes, edges=edges)
    except Exception as e:
        import traceback
        print(f'❌ Error in query_graph: {e}', flush=True)
        traceback.print_exc()
        return GraphQueryResponse(nodes=[], edges=[])


@router.get('/graph/entities/{node_id}/subgraph', status_code=status.HTTP_200_OK)
async def get_entity_subgraph(node_id: str, graphiti: ZepGraphitiDep):
    """
    Get a subgraph centered on a specific node.
    
    Returns the node, its 1-hop neighbors, and all connecting edges.
    """
    try:
        driver = graphiti.driver
        
        # 1. Query all edges connected to this node
        edges_result, _, _ = await driver.execute_query(
            """
            SELECT uuid, name, fact, source_node_uuid, target_node_uuid
            FROM entity_edges
            WHERE source_node_uuid = %s OR target_node_uuid = %s
            LIMIT 500
            """,
            params=(node_id, node_id)
        )
        
        # 2. Collect all involved node UUIDs
        all_node_ids = {node_id}
        edges = []
        for record in edges_result or []:
            src = record.get('source_node_uuid', '')
            tgt = record.get('target_node_uuid', '')
            all_node_ids.add(src)
            all_node_ids.add(tgt)
            edges.append({
                'id': record.get('uuid', ''),
                'source_node_uuid': src,
                'target_node_uuid': tgt,
                'name': record.get('name', ''),
                'fact': record.get('fact', ''),
            })
        
        # 3. Batch query all involved nodes
        node_ids_list = list(all_node_ids)
        nodes = []
        if node_ids_list:
            nodes_result, _, _ = await driver.execute_query(
                """
                SELECT uuid, name, labels, summary, attributes
                FROM entity_nodes
                WHERE uuid = ANY(%s)
                """,
                params=(node_ids_list,)
            )
            for record in nodes_result or []:
                labels = record.get('labels', [])
                if isinstance(labels, str):
                    labels = [labels] if labels else []
                nodes.append({
                    'id': record.get('uuid', ''),
                    'name': record.get('name', ''),
                    'labels': labels,
                    'summary': record.get('summary', ''),
                    'attributes': record.get('attributes', {}) or {}
                })
        
        return GraphQueryResponse(nodes=nodes, edges=edges)
    except Exception as e:
        import traceback
        print(f'❌ Error in get_entity_subgraph: {e}', flush=True)
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
            params=(pattern,)
        )
        
        print(f'📊 Found {len(results or [])} nodes', flush=True)
        
        # 转换为前端期望的格式
        entities = []
        for record in results or []:
            labels = record.get('labels', [])
            if isinstance(labels, str):
                labels = [labels] if labels else []
            
            entities.append({
                'id': record.get('uuid', ''),
                'name': record.get('name', ''),
                'type': labels[0] if labels else 'Entity'
            })
        
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
            "SELECT COUNT(*) as count FROM entity_nodes"
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
                    type=record.get('type', 'UNKNOWN'),
                    count=record.get('count', 0)
                )
            )
        
        return GraphSchemaResponse(
            nodeLabels=node_labels,
            relationshipTypes=relationship_types
        )
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
            params=(limit,)
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
                description = f"{record.get('name', 'Untitled')} ({len(entity_edges)} edges)"
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
                    type=activity_type,
                    description=description,
                    source=source_info,
                    time=time_str
                )
            )
        
        return timeline
    except Exception as e:
        import traceback
        print(f'❌ Error in get_graph_timeline: {e}', flush=True)
        traceback.print_exc()
        return []
