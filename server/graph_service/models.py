"""Extraction schema persistence and dynamic Pydantic model generation.

Stores user-defined extraction schemas in PostgreSQL and converts them to
Pydantic BaseModel subclasses at runtime, compatible with Graphiti's
``entity_types`` / ``edge_types`` parameters.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

CREATE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS public.extraction_schemas (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL DEFAULT '',
    entity_types    JSONB NOT NULL DEFAULT '[]',
    edge_types      JSONB NOT NULL DEFAULT '[]',
    custom_instructions TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def init_schemas_table(dsn: str) -> None:
    """Create the extraction_schemas table if it does not exist."""
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute(CREATE_TABLE_DDL)
    logger.info('extraction_schemas table ensured')


async def list_schemas(dsn: str) -> list[dict[str, Any]]:
    async with (
        await psycopg.AsyncConnection.connect(dsn) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            SELECT id, name, description,
                   jsonb_array_length(entity_types) AS entity_type_count,
                   jsonb_array_length(edge_types)   AS edge_type_count,
                   created_at, updated_at
            FROM public.extraction_schemas
            ORDER BY id
            """
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_schema(dsn: str, schema_id: int) -> dict[str, Any] | None:
    async with (
        await psycopg.AsyncConnection.connect(dsn) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            'SELECT * FROM public.extraction_schemas WHERE id = %s',
            (schema_id,),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_schema(dsn: str, data: dict[str, Any]) -> dict[str, Any]:
    async with (
        await psycopg.AsyncConnection.connect(dsn) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            INSERT INTO public.extraction_schemas (name, description, entity_types, edge_types, custom_instructions)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                data['name'],
                data.get('description', ''),
                Jsonb(data.get('entity_types', [])),
                Jsonb(data.get('edge_types', [])),
                data.get('custom_instructions', ''),
            ),
        )
        row = await cur.fetchone()
    return dict(row) if row else {}


async def update_schema(dsn: str, schema_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    async with (
        await psycopg.AsyncConnection.connect(dsn) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            """
            UPDATE public.extraction_schemas
            SET name = %s,
                description = %s,
                entity_types = %s,
                edge_types = %s,
                custom_instructions = %s,
                updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (
                data['name'],
                data.get('description', ''),
                Jsonb(data.get('entity_types', [])),
                Jsonb(data.get('edge_types', [])),
                data.get('custom_instructions', ''),
                schema_id,
            ),
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def delete_schema(dsn: str, schema_id: int) -> bool:
    async with await psycopg.AsyncConnection.connect(dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            'DELETE FROM public.extraction_schemas WHERE id = %s',
            (schema_id,),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Dynamic Pydantic model generation
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type] = {'str': str, 'int': int, 'float': float, 'bool': bool}


def _build_model(name: str, description: str, attributes: list[dict] | None) -> type[BaseModel]:
    """Dynamically create a Pydantic model compatible with Graphiti's extraction.

    - ``description`` becomes ``__doc__`` → injected into LLM prompt.
    - ``attributes`` become ``model_fields`` → triggers ``extract_attributes``.
    """
    namespace: dict[str, Any] = {'__doc__': description}
    if attributes:
        annotations: dict[str, Any] = {}
        for attr in attributes:
            py_type = _TYPE_MAP.get(attr.get('type', 'str'), str)
            annotations[attr['name']] = py_type | None
            namespace[attr['name']] = Field(default=None, description=attr.get('description', ''))
        namespace['__annotations__'] = annotations
    return type(name, (BaseModel,), namespace)


def build_extraction_params(
    schema: dict[str, Any],
) -> tuple[
    dict[str, type[BaseModel]],  # entity_types
    dict[str, type[BaseModel]],  # edge_types
    str | None,  # custom_extraction_instructions
]:
    """Convert a persisted schema dict into Graphiti extraction parameters."""
    entity_types: dict[str, type[BaseModel]] = {}
    for et in schema.get('entity_types', []):
        # Handle both JSON-loaded dicts and raw strings
        if isinstance(et, str):
            continue
        entity_types[et['name']] = _build_model(
            et['name'],
            et.get('description', ''),
            et.get('attributes'),
        )

    edge_types: dict[str, type[BaseModel]] = {}
    for et in schema.get('edge_types', []):
        if isinstance(et, str):
            continue
        edge_types[et['name']] = _build_model(
            et['name'],
            et.get('description', ''),
            et.get('attributes'),
        )

    custom_instructions = schema.get('custom_instructions') or None
    return entity_types, edge_types, custom_instructions


# ---------------------------------------------------------------------------
# Built-in default entity types (used when no schema is selected)
# ---------------------------------------------------------------------------


class Person(BaseModel):
    """A Person represents a named or clearly identifiable individual."""


class Organization(BaseModel):
    """An Organization represents a company, institution, team, or association."""


class Location(BaseModel):
    """A Location represents a physical or virtual place."""


class Object(BaseModel):
    """An Object represents a physical item, tool, device, or possession."""


class Document(BaseModel):
    """A Document represents information content such as reports, articles, emails, videos, or podcasts."""


class Event(BaseModel):
    """An Event represents a named or time-bound occurrence."""


class Topic(BaseModel):
    """A Topic represents a subject, hobby, or knowledge domain."""


DEFAULT_ENTITY_TYPES: dict[str, type[BaseModel]] = {
    'Person': Person,
    'Organization': Organization,
    'Location': Location,
    'Object': Object,
    'Document': Document,
    'Event': Event,
    'Topic': Topic,
}
