"""One-off script to backfill entity type labels for existing nodes.

Nodes that currently have only ``['Entity']`` as labels are classified
using an LLM into one of the DEFAULT_ENTITY_TYPES (Person, Organization,
Location, Object, Document, Event, Topic).

Usage:
    # Dry-run: show what would change without writing
    python -m graph_service.scripts.backfill_entity_types --dry-run --limit 10

    # Execute: update labels in the database
    python -m graph_service.scripts.backfill_entity_types --group-id my-group --limit 100

    # Use a specific schema instead of default types
    python -m graph_service.scripts.backfill_entity_types --schema-id 5 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Classification prompt
# ---------------------------------------------------------------------------

_CLASSIFICATION_PROMPT = """Given the following entity, classify it into exactly ONE of these types:

- Person: A named or clearly identifiable individual
- Organization: A company, institution, team, or association
- Location: A physical or virtual place
- Object: A physical item, tool, device, or possession
- Document: Information content such as reports, articles, emails, videos, or podcasts
- Event: A named or time-bound occurrence
- Topic: A subject, hobby, or knowledge domain

Entity name: {name}
Entity summary: {summary}

Respond with ONLY the type name (e.g., "Person"). If unsure, pick the closest match."""

# Batch version for efficiency
_BATCH_CLASSIFICATION_PROMPT = """Given the following entities, classify each into exactly ONE of these types:

- Person: A named or clearly identifiable individual
- Organization: A company, institution, team, or association
- Location: A physical or virtual place
- Object: A physical item, tool, device, or possession
- Document: Information content such as reports, articles, emails, videos, or podcasts
- Event: A named or time-bound occurrence
- Topic: A subject, hobby, or knowledge domain

Entities:
{entities}

Respond with a JSON array of type names in the same order, e.g.:
["Person", "Organization", "Location"]

If unsure about an entity, pick the closest match."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Backfill entity type labels for nodes with only [Entity] label'
    )
    parser.add_argument(
        '--group-id',
        type=str,
        default=None,
        help='Filter by group_id (optional)',
    )
    parser.add_argument(
        '--schema-id',
        type=int,
        default=None,
        help='Use a custom schema for classification instead of default types',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum number of entities to process (default: 100)',
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of entities per LLM batch call (default: 10)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without writing to DB',
    )
    parser.add_argument(
        '--dsn',
        type=str,
        default=None,
        help='PostgreSQL DSN (defaults to POSTGRES_AGE_DSN env var)',
    )
    return parser.parse_args()


async def _get_entities_to_classify(dsn: str, group_id: str | None, limit: int) -> list[dict]:
    """Fetch entities that have only ['Entity'] as labels."""
    import psycopg
    from psycopg.rows import dict_row

    query = """
        SELECT uuid, name, summary, attributes
        FROM public.entity_nodes
        WHERE labels = ARRAY['Entity']::text[]
          OR labels = ARRAY['Entity']
        {group_filter}
        ORDER BY created_at DESC
        LIMIT %s
    """.format(
        group_filter="AND group_id = %s" if group_id else ""
    )

    params: list[Any] = []
    if group_id:
        params.append(group_id)
    params.append(limit)

    async with (
        await psycopg.AsyncConnection.connect(dsn) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(query, params)
        rows = await cur.fetchall()

    return [dict(r) for r in rows]


async def _classify_batch(
    llm_client: Any,
    entities: list[dict],
) -> list[str]:
    """Classify a batch of entities using LLM."""
    entity_descriptions = []
    for i, ent in enumerate(entities):
        name = ent.get('name', 'Unknown')
        summary = ent.get('summary', '(no summary)')
        entity_descriptions.append(f'{i + 1}. Name: {name}\n   Summary: {summary}')

    prompt = _BATCH_CLASSIFICATION_PROMPT.format(entities='\n'.join(entity_descriptions))

    try:
        response = await llm_client.chat.completions.create(
            model=os.getenv('BACKFILL_MODEL', os.getenv('OPENAI_MODEL_NAME', 'gpt-4.1-mini')),
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0,
            response_format={'type': 'json_object'},
        )
        content = response.choices[0].message.content
        data = json.loads(content)

        # Handle both array and {"types": [...]} formats
        if isinstance(data, list):
            types = data
        elif isinstance(data, dict):
            # Try common keys
            types = data.get('types') or data.get('classifications') or list(data.values())[0]
            if isinstance(types, dict):
                types = list(types.values())
        else:
            types = ['Entity'] * len(entities)

        # Pad or trim to match entity count
        while len(types) < len(entities):
            types.append('Entity')
        return types[: len(entities)]

    except Exception as e:
        print(f'  ⚠️ Batch classification failed: {e}', file=sys.stderr)
        return ['Entity'] * len(entities)


async def _update_entity_labels(dsn: str, uuid: str, new_labels: list[str]) -> None:
    """Update an entity node's labels."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute(
            'UPDATE public.entity_nodes SET labels = %s WHERE uuid = %s',
            (new_labels, uuid),
        )


async def main() -> None:
    args = _parse_args()

    dsn = args.dsn or os.getenv('POSTGRES_AGE_DSN')
    if not dsn:
        print('ERROR: --dsn or POSTGRES_AGE_DSN env var required', file=sys.stderr)
        sys.exit(1)

    # Fetch entities to classify
    print(f'🔍 Finding entities with only [Entity] label...', file=sys.stderr)
    entities = await _get_entities_to_classify(dsn, args.group_id, args.limit)
    print(f'📊 Found {len(entities)} entities to classify', file=sys.stderr)

    if not entities:
        print('✅ No entities need backfill.')
        return

    if args.dry_run:
        print(f'\n🔎 DRY RUN — no changes will be made\n', file=sys.stderr)

    # Build LLM client
    try:
        from openai import AsyncOpenAI

        llm_client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    except ImportError:
        print('ERROR: openai package required. Install with: pip install openai', file=sys.stderr)
        sys.exit(1)

    # Process in batches
    total_updated = 0
    total_skipped = 0
    batch_size = max(1, args.batch_size)

    for i in range(0, len(entities), batch_size):
        batch = entities[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(entities) + batch_size - 1) // batch_size

        print(
            f'  📦 Batch {batch_num}/{total_batches} ({len(batch)} entities)...',
            file=sys.stderr,
        )

        classifications = await _classify_batch(llm_client, batch)

        for ent, classification in zip(batch, classifications):
            uuid = ent['uuid']
            name = ent.get('name', 'Unknown')

            # Validate classification
            valid_types = {
                'Person', 'Organization', 'Location', 'Object',
                'Document', 'Event', 'Topic',
            }
            if classification not in valid_types:
                classification = 'Entity'

            new_labels = ['Entity', classification] if classification != 'Entity' else ['Entity']

            if args.dry_run:
                print(f'    [{uuid[:8]}] "{name}" → {classification}')
                if classification != 'Entity':
                    total_updated += 1
                else:
                    total_skipped += 1
            else:
                await _update_entity_labels(dsn, uuid, new_labels)
                total_updated += 1
                print(f'    ✓ [{uuid[:8]}] "{name}" → {classification}', file=sys.stderr)

    # Summary
    action = 'Would update' if args.dry_run else 'Updated'
    print(
        f'\n📋 Summary: {action} {total_updated} entities, '
        f'{total_skipped} unchanged (dry-run)',
        file=sys.stderr,
    )

    if args.dry_run:
        print('\nTo apply changes, run without --dry-run', file=sys.stderr)


if __name__ == '__main__':
    asyncio.run(main())
