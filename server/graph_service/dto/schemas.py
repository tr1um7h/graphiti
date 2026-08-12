from datetime import datetime

from pydantic import BaseModel, Field


class AttributeDefinition(BaseModel):
    name: str
    type: str = Field(default='str', description='Python type: str | int | float | bool')
    description: str = ''


class TypeDefinition(BaseModel):
    name: str
    description: str = ''
    attributes: list[AttributeDefinition] = []
    source_types: list[str] = []
    target_types: list[str] = []


class ExtractionSchemaCreate(BaseModel):
    name: str
    description: str = ''
    entity_types: list[TypeDefinition] = []
    edge_types: list[TypeDefinition] = []
    custom_instructions: str = ''


class ExtractionSchemaResponse(ExtractionSchemaCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class ExtractionSchemaListItem(BaseModel):
    id: int
    name: str
    description: str
    entity_type_count: int
    edge_type_count: int
