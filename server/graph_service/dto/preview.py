from datetime import datetime

from pydantic import BaseModel, Field

# --- Preview DTOs ---


class PreviewMemoryRequest(BaseModel):
    name: str = Field(default='', description='Name of the episode')
    content: str = Field(..., description='Text content to extract entities/edges from')
    group_id: str = Field(
        default='default', description='Group ID for the knowledge graph partition'
    )
    source: str = Field(default='text', description='Source type: text, json, or message')
    source_description: str = Field(default='', description='Description of the content source')
    schema_id: int | None = Field(default=None, description='Extraction schema ID')


class EpisodePreview(BaseModel):
    uuid: str
    name: str
    content: str
    group_id: str
    source: str
    source_description: str


class NodePreview(BaseModel):
    uuid: str
    name: str
    labels: list[str] = []
    summary: str = ''
    group_id: str = ''
    is_new: bool = True


class EdgePreview(BaseModel):
    uuid: str
    name: str = ''
    fact: str = ''
    source_node_uuid: str = ''
    source_node_name: str = ''
    target_node_uuid: str = ''
    target_node_name: str = ''
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    expired_at: datetime | None = None


class PreviewMemoryResponse(BaseModel):
    episode: EpisodePreview
    nodes: list[NodePreview]
    edges: list[EdgePreview]
    invalidated_edges: list[EdgePreview]


class PreviewTaskStatus(BaseModel):
    task_id: str
    status: str  # 'pending' | 'processing' | 'completed' | 'failed'
    stage: str | None = None
    error: str | None = None
    result: PreviewMemoryResponse | None = None


# --- Commit DTOs ---


class NodeConfirm(BaseModel):
    uuid: str
    name: str
    labels: list[str] = ['Entity']
    summary: str = ''


class EdgeConfirm(BaseModel):
    uuid: str
    name: str = ''
    fact: str = ''
    source_node_uuid: str
    target_node_uuid: str
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    expired_at: datetime | None = None


class CommitMemoryRequest(BaseModel):
    episode: EpisodePreview
    nodes: list[NodeConfirm]
    edges: list[EdgeConfirm]
    group_id: str = Field(
        default='default', description='Group ID for the knowledge graph partition'
    )
    update_communities: bool = Field(
        default=False, description='Whether to update community structure'
    )
