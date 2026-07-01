"""Entity detail and neighbors routes"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from graph_service.dto import (
    EntityDetailResponse,
    GraphEdge,
    GraphNode,
    NeighborsResponse,
)
from graph_service.zep_graphiti import ZepGraphitiDep

router = APIRouter()


@router.get('/graph/entities/{entity_id}', status_code=status.HTTP_200_OK)
async def get_entity_detail(entity_id: str, graphiti: ZepGraphitiDep):
    """
    Get detailed information about a specific entity.
    
    Returns entity name, labels, summary, attributes, and metadata.
    """
    try:
        from graphiti_core.nodes import EntityNode
        
        # Get entity node by UUID
        entity = await EntityNode.get_by_uuid(graphiti.driver, entity_id)
        
        # Parse labels
        labels = entity.labels or []
        if isinstance(labels, str):
            labels = [labels] if labels else []
        
        return EntityDetailResponse(
            id=entity.uuid,
            name=entity.name,
            labels=labels,
            summary=entity.summary or '',
            created_at=entity.created_at,
            group_id=entity.group_id,
            attributes=entity.attributes or {}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f'Entity not found: {str(e)}')


@router.get('/graph/entities/{entity_id}/neighbors', status_code=status.HTTP_200_OK)
async def get_entity_neighbors(entity_id: str, graphiti: ZepGraphitiDep, depth: int = 1):
    """
    Get neighboring entities and connecting edges.
    
    Returns the center entity, its neighbors, and the edges connecting them.
    Supports multi-hop traversal via depth parameter.
    """
    try:
        from graphiti_core.nodes import EntityNode
        
        # Get center entity
        center_entity = await EntityNode.get_by_uuid(graphiti.driver, entity_id)
        
        center_labels = center_entity.labels or []
        if isinstance(center_labels, str):
            center_labels = [center_labels] if center_labels else []
        
        center_node = GraphNode(
            id=center_entity.uuid,
            name=center_entity.name,
            labels=center_labels,
            summary=center_entity.summary or '',
            attributes=center_entity.attributes or {}
        )
        
        # Query neighbors using SQL (PostgreSQL AGE stores data in relational tables)
        # entity_edges and entity_nodes are the relational projection tables
        if depth == 1:
            # Direct neighbors: get all edges connected to the center node
            neighbors_result = await graphiti.driver.execute_query(
                """
                SELECT
                    n.uuid AS uuid, n.name AS name,
                    n.summary AS summary, n.attributes AS attributes,
                    e.uuid AS edge_uuid, e.name AS edge_name,
                    e.fact AS edge_fact, e.created_at AS edge_created_at,
                    e.source_node_uuid AS source_uuid,
                    e.target_node_uuid AS target_uuid
                FROM entity_edges e
                JOIN entity_nodes n ON (
                    (n.uuid = e.target_node_uuid AND e.source_node_uuid = %s)
                    OR
                    (n.uuid = e.source_node_uuid AND e.target_node_uuid = %s)
                )
                WHERE n.uuid != %s
                LIMIT 500
                """,
                params=(entity_id, entity_id, entity_id),
            )
        else:
            # Multi-hop neighbors (depth 2+): recursive CTE
            neighbors_result = await graphiti.driver.execute_query(
                """
                WITH RECURSIVE neighbor_chain AS (
                    SELECT
                        e.target_node_uuid AS neighbor_uuid,
                        e.uuid AS edge_uuid, e.name AS edge_name,
                        e.fact AS edge_fact, e.created_at AS edge_created_at,
                        e.source_node_uuid AS source_uuid,
                        e.target_node_uuid AS target_uuid,
                        1 AS hop
                    FROM entity_edges e
                    WHERE e.source_node_uuid = %s
                    UNION
                    SELECT
                        e2.target_node_uuid AS neighbor_uuid,
                        e2.uuid AS edge_uuid, e2.name AS edge_name,
                        e2.fact AS edge_fact, e2.created_at AS edge_created_at,
                        e2.source_node_uuid AS source_uuid,
                        e2.target_node_uuid AS target_uuid,
                        nc.hop + 1
                    FROM neighbor_chain nc
                    JOIN entity_edges e2 ON e2.source_node_uuid = nc.neighbor_uuid
                    WHERE nc.hop < %s
                )
                SELECT
                    n.uuid AS uuid, n.name AS name,
                    n.summary AS summary, n.attributes AS attributes,
                    nc.edge_uuid, nc.edge_name,
                    nc.edge_fact, nc.edge_created_at,
                    nc.source_uuid, nc.target_uuid
                FROM neighbor_chain nc
                JOIN entity_nodes n ON n.uuid = nc.neighbor_uuid
                WHERE n.uuid != %s
                LIMIT 1000
                """,
                params=(entity_id, depth, entity_id),
            )
        
        # Process results — execute_query returns (records, _, _) tuple
        neighbors_records, _, _ = neighbors_result
        nodes = {}
        edges = []
        
        for record in neighbors_records or []:
            data = record if isinstance(record, dict) else (record[0] if isinstance(record, (tuple, list)) else record)
            
            # Add neighbor node
            neighbor_uuid = data.get('uuid', '')
            if neighbor_uuid and neighbor_uuid not in nodes and neighbor_uuid != entity_id:
                labels = data.get('labels', [])
                if isinstance(labels, str):
                    labels = [labels] if labels else []
                
                nodes[neighbor_uuid] = GraphNode(
                    id=neighbor_uuid,
                    name=data.get('name', ''),
                    labels=labels,
                    summary=data.get('summary', ''),
                    attributes=data.get('attributes', {}) or {}
                )
            
            # Add edge
            edge_uuid = data.get('edge_uuid', '')
            if edge_uuid:
                edges.append(
                    GraphEdge(
                        id=edge_uuid,
                        source_node_uuid=data.get('source_uuid', ''),
                        target_node_uuid=data.get('target_uuid', ''),
                        name=data.get('edge_name', ''),
                        fact=data.get('edge_fact', ''),
                        created_at=data.get('edge_created_at', datetime.now(timezone.utc))
                    )
                )
        
        return NeighborsResponse(
            center=center_node,
            nodes=list(nodes.values()),
            edges=edges
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f'Entity not found: {str(e)}')
