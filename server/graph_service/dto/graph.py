"""DTOs for graph query operations"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GraphStatsResponse(BaseModel):
    """Response model for graph statistics"""
    totalNodes: int = Field(default=0, description='Total number of entity nodes')
    totalEdges: int = Field(default=0, description='Total number of entity edges')
    totalDocuments: int = Field(default=0, description='Total number of documents')
    totalConversations: int = Field(default=0, description='Total number of conversations')
    todayNewNodes: int = Field(default=0, description='New nodes today')
    todayNewEdges: int = Field(default=0, description='New edges today')
    todayNewDocuments: int = Field(default=0, description='New documents today')
    todayNewConversations: int = Field(default=0, description='New conversations today')


class GraphNode(BaseModel):
    """Graph node representation"""
    id: str = Field(..., description='Node UUID')
    name: str = Field(..., description='Node name')
    labels: list[str] = Field(default_factory=list, description='Node labels')
    summary: str = Field(default='', description='Node summary')
    attributes: dict[str, Any] = Field(default_factory=dict, description='Node attributes')


class GraphEdge(BaseModel):
    """Graph edge representation"""
    id: str = Field(..., description='Edge UUID')
    source_node_uuid: str = Field(..., description='Source node UUID')
    target_node_uuid: str = Field(..., description='Target node UUID')
    name: str = Field(..., description='Edge type/name')
    fact: str = Field(default='', description='Fact description')
    created_at: datetime = Field(..., description='Creation timestamp')


class GraphQueryRequest(BaseModel):
    """Request model for graph query"""
    limit: int = Field(default=500, description='Maximum number of nodes to return')
    group_ids: list[str] | None = Field(default=None, description='Filter by group IDs')
    entity_types: list[str] | None = Field(default=None, description='Filter by entity types')


class GraphQueryResponse(BaseModel):
    """Response model for graph query"""
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphSearchResult(BaseModel):
    """Search result item"""
    id: str = Field(..., description='Entity UUID')
    name: str = Field(..., description='Entity name')
    type: str = Field(default='', description='Entity type/label')


class SchemaNodeLabel(BaseModel):
    """Schema node label with count"""
    label: str = Field(..., description='Node label')
    count: int = Field(..., description='Number of nodes with this label')


class SchemaRelationshipType(BaseModel):
    """Schema relationship type with count"""
    type: str = Field(..., description='Relationship type')
    count: int = Field(..., description='Number of edges with this type')


class GraphSchemaResponse(BaseModel):
    """Response model for graph schema"""
    nodeLabels: list[SchemaNodeLabel] = Field(default_factory=list)
    relationshipTypes: list[SchemaRelationshipType] = Field(default_factory=list)


class TimelineItem(BaseModel):
    """Timeline activity item"""
    type: str = Field(..., description='Activity type: entity, relationship, document, episode')
    description: str = Field(..., description='Activity description')
    source: str = Field(default='', description='Source information')
    time: str = Field(..., description='ISO format timestamp')


class EntityDetailResponse(BaseModel):
    """Entity detail response"""
    id: str = Field(..., description='Entity UUID')
    name: str = Field(..., description='Entity name')
    labels: list[str] = Field(default_factory=list, description='Entity labels')
    summary: str = Field(default='', description='Entity summary')
    created_at: datetime = Field(..., description='Creation timestamp')
    group_id: str = Field(..., description='Group ID')
    attributes: dict[str, Any] = Field(default_factory=dict, description='Entity attributes')


class NeighborsResponse(BaseModel):
    """Entity neighbors response"""
    center: GraphNode | None = Field(default=None, description='Center entity')
    nodes: list[GraphNode] = Field(default_factory=list, description='Neighbor nodes')
    edges: list[GraphEdge] = Field(default_factory=list, description='Connecting edges')
