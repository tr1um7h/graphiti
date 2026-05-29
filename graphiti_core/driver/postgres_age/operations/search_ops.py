from __future__ import annotations

from typing import Any

from graphiti_core.driver.operations.search_ops import SearchOperations
from graphiti_core.driver.postgres_age.records import (
    community_node_from_row,
    entity_edge_from_row,
    entity_node_from_row,
    episodic_node_from_row,
)
from graphiti_core.driver.query_executor import QueryExecutor
from graphiti_core.edges import EntityEdge
from graphiti_core.helpers import validate_group_ids, validate_node_labels
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodicNode
from graphiti_core.search.search_filters import SearchFilters


class PostgresAgeSearchOperations(SearchOperations):
    async def node_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityNode]:
        where, params = _node_filters(search_filter, group_ids)
        params.update({'query': query, 'limit': limit})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM entity_nodes
            WHERE search_vector @@ websearch_to_tsquery('simple', %(query)s)
            {where}
            ORDER BY ts_rank(search_vector, websearch_to_tsquery('simple', %(query)s)) DESC,
                     uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def node_similarity_search(
        self,
        executor: QueryExecutor,
        search_vector: list[float],
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> list[EntityNode]:
        where, params = _node_filters(search_filter, group_ids, prefix='AND')
        params.update({'search_vector': search_vector, 'limit': limit, 'min_score': min_score})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *, 1 - (name_embedding <=> %(search_vector)s::vector) AS score
            FROM entity_nodes
            WHERE name_embedding IS NOT NULL
            {where}
              AND 1 - (name_embedding <=> %(search_vector)s::vector) > %(min_score)s
            ORDER BY name_embedding <=> %(search_vector)s::vector, uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def node_bfs_search(
        self,
        executor: QueryExecutor,
        origin_uuids: list[str],
        search_filter: SearchFilters,
        max_depth: int,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityNode]:
        _validate_bfs_depth(max_depth)
        if not origin_uuids:
            return []
        where, params = _node_filters(search_filter, group_ids, alias='n', prefix='AND')
        params.update(
            {
                'origin_uuids': origin_uuids,
                'max_depth': max_depth,
                'limit': limit,
                'walk_group_ids': group_ids,
            }
        )
        records, _, _ = await executor.execute_query(
            f"""
            WITH RECURSIVE walk(uuid, depth) AS (
                SELECT unnest(%(origin_uuids)s::text[]) AS uuid, 0 AS depth
                UNION
                SELECT adjacency.target_node_uuid, walk.depth + 1
                FROM walk
                JOIN (
                    SELECT source_node_uuid, target_node_uuid, group_id
                    FROM episodic_edges
                    UNION ALL
                    SELECT source_node_uuid, target_node_uuid, group_id
                    FROM entity_edges
                ) adjacency ON adjacency.source_node_uuid = walk.uuid
                WHERE walk.depth < %(max_depth)s
                  AND (
                    %(walk_group_ids)s::text[] IS NULL
                    OR adjacency.group_id = ANY(%(walk_group_ids)s::text[])
                  )
            )
            SELECT DISTINCT n.*
            FROM entity_nodes n
            JOIN walk ON walk.uuid = n.uuid
            WHERE walk.depth > 0
            {where}
            ORDER BY n.uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def edge_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityEdge]:
        where, params = _edge_filters(search_filter, group_ids)
        params.update({'query': query, 'limit': limit})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM entity_edges
            WHERE search_vector @@ websearch_to_tsquery('simple', %(query)s)
            {where}
            ORDER BY ts_rank(search_vector, websearch_to_tsquery('simple', %(query)s)) DESC,
                     uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def edge_similarity_search(
        self,
        executor: QueryExecutor,
        search_vector: list[float],
        source_node_uuid: str | None,
        target_node_uuid: str | None,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> list[EntityEdge]:
        where, params = _edge_filters(search_filter, group_ids, prefix='AND')
        if source_node_uuid is not None:
            where += ' AND source_node_uuid = %(source_node_uuid)s'
            params['source_node_uuid'] = source_node_uuid
        if target_node_uuid is not None:
            where += ' AND target_node_uuid = %(target_node_uuid)s'
            params['target_node_uuid'] = target_node_uuid
        params.update({'search_vector': search_vector, 'limit': limit, 'min_score': min_score})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *, 1 - (fact_embedding <=> %(search_vector)s::vector) AS score
            FROM entity_edges
            WHERE fact_embedding IS NOT NULL
            {where}
              AND 1 - (fact_embedding <=> %(search_vector)s::vector) > %(min_score)s
            ORDER BY fact_embedding <=> %(search_vector)s::vector, uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def edge_bfs_search(
        self,
        executor: QueryExecutor,
        origin_uuids: list[str],
        max_depth: int,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityEdge]:
        _validate_bfs_depth(max_depth)
        if not origin_uuids:
            return []
        where, params = _edge_filters(search_filter, group_ids, alias='e', prefix='AND')
        params.update(
            {
                'origin_uuids': origin_uuids,
                'max_depth': max_depth,
                'limit': limit,
                'walk_group_ids': group_ids,
            }
        )
        records, _, _ = await executor.execute_query(
            f"""
            WITH RECURSIVE walk(uuid, depth) AS (
                SELECT unnest(%(origin_uuids)s::text[]) AS uuid, 0 AS depth
                UNION
                SELECT adjacency.target_node_uuid, walk.depth + 1
                FROM walk
                JOIN (
                    SELECT source_node_uuid, target_node_uuid, group_id
                    FROM episodic_edges
                    UNION ALL
                    SELECT source_node_uuid, target_node_uuid, group_id
                    FROM entity_edges
                ) adjacency ON adjacency.source_node_uuid = walk.uuid
                WHERE walk.depth < %(max_depth)s
                  AND (
                    %(walk_group_ids)s::text[] IS NULL
                    OR adjacency.group_id = ANY(%(walk_group_ids)s::text[])
                  )
            )
            SELECT DISTINCT e.*
            FROM entity_edges e
            JOIN walk ON walk.uuid = e.source_node_uuid
            WHERE walk.depth < %(max_depth)s
            {where}
            ORDER BY e.uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [entity_edge_from_row(row) for row in records]

    async def episode_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EpisodicNode]:
        where, params = _group_filter(group_ids)
        params.update({'query': query, 'limit': limit})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM episodic_nodes
            WHERE search_vector @@ websearch_to_tsquery('simple', %(query)s)
            {where}
            ORDER BY ts_rank(search_vector, websearch_to_tsquery('simple', %(query)s)) DESC,
                     uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [episodic_node_from_row(row) for row in records]

    async def community_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[CommunityNode]:
        where, params = _group_filter(group_ids)
        params.update({'query': query, 'limit': limit})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *
            FROM community_nodes
            WHERE search_vector @@ websearch_to_tsquery('simple', %(query)s)
            {where}
            ORDER BY ts_rank(search_vector, websearch_to_tsquery('simple', %(query)s)) DESC,
                     uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [community_node_from_row(row) for row in records]

    async def community_similarity_search(
        self,
        executor: QueryExecutor,
        search_vector: list[float],
        group_ids: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> list[CommunityNode]:
        where, params = _group_filter(group_ids, prefix='AND')
        params.update({'search_vector': search_vector, 'limit': limit, 'min_score': min_score})
        records, _, _ = await executor.execute_query(
            f"""
            SELECT *, 1 - (name_embedding <=> %(search_vector)s::vector) AS score
            FROM community_nodes
            WHERE name_embedding IS NOT NULL
            {where}
              AND 1 - (name_embedding <=> %(search_vector)s::vector) > %(min_score)s
            ORDER BY name_embedding <=> %(search_vector)s::vector, uuid
            LIMIT %(limit)s
            """,
            params=params,
            routing_='r',
        )
        return [community_node_from_row(row) for row in records]

    async def node_distance_reranker(
        self,
        executor: QueryExecutor,
        node_uuids: list[str],
        center_node_uuid: str,
        min_score: float = 0,
    ) -> list[EntityNode]:
        if not node_uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            WITH RECURSIVE walk(uuid, distance) AS (
                SELECT %(center_node_uuid)s::text, 0
                UNION
                SELECT adjacency.node_uuid, walk.distance + 1
                FROM walk
                JOIN (
                    SELECT source_node_uuid AS source_uuid, target_node_uuid AS node_uuid
                    FROM entity_edges
                    UNION ALL
                    SELECT target_node_uuid AS source_uuid, source_node_uuid AS node_uuid
                    FROM entity_edges
                ) adjacency ON adjacency.source_uuid = walk.uuid
                WHERE walk.distance < 5
            ),
            distances AS (
                SELECT uuid, min(distance) AS distance
                FROM walk
                GROUP BY uuid
            )
            SELECT n.*, coalesce(d.distance, 1000000) AS distance
            FROM entity_nodes n
            LEFT JOIN distances d ON d.uuid = n.uuid
            WHERE n.uuid = ANY(%(node_uuids)s)
              AND CASE
                    WHEN coalesce(d.distance, 1000000) = 0 THEN 10.0
                    WHEN d.distance IS NULL THEN 0.0
                    ELSE 1.0 / d.distance
                  END >= %(min_score)s
            ORDER BY coalesce(d.distance, 1000000), n.uuid
            """,
            params={
                'node_uuids': node_uuids,
                'center_node_uuid': center_node_uuid,
                'min_score': min_score,
            },
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    async def episode_mentions_reranker(
        self,
        executor: QueryExecutor,
        node_uuids: list[str],
        min_score: float = 0,
    ) -> list[EntityNode]:
        if not node_uuids:
            return []
        records, _, _ = await executor.execute_query(
            """
            WITH requested AS (
                SELECT uuid, ordinal
                FROM unnest(%(node_uuids)s::text[]) WITH ORDINALITY AS requested(uuid, ordinal)
            ),
            mention_counts AS (
                SELECT requested.uuid, requested.ordinal, count(e.uuid) AS mention_count
                FROM requested
                LEFT JOIN episodic_edges e ON e.target_node_uuid = requested.uuid
                GROUP BY requested.uuid, requested.ordinal
            )
            SELECT n.*, mention_counts.mention_count
            FROM mention_counts
            JOIN entity_nodes n ON n.uuid = mention_counts.uuid
            WHERE mention_counts.mention_count >= %(min_score)s
            ORDER BY mention_counts.mention_count DESC, mention_counts.ordinal
            """,
            params={'node_uuids': node_uuids, 'min_score': min_score},
            routing_='r',
        )
        return [entity_node_from_row(row) for row in records]

    def build_node_search_filters(self, search_filters: SearchFilters) -> Any:
        return _node_filters(search_filters, None)

    def build_edge_search_filters(self, search_filters: SearchFilters) -> Any:
        return _edge_filters(search_filters, None)

    def build_fulltext_query(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_query_length: int = 8000,
    ) -> str:
        validate_group_ids(group_ids)
        if len(query.split()) + len(group_ids or []) >= max_query_length:
            return ''
        return query


def _group_filter(
    group_ids: list[str] | None,
    alias: str | None = None,
    prefix: str = 'AND',
) -> tuple[str, dict[str, Any]]:
    validate_group_ids(group_ids)
    if group_ids is None:
        return '', {}
    column = f'{alias}.group_id' if alias else 'group_id'
    return f' {prefix} {column} = ANY(%(group_ids)s)', {'group_ids': group_ids}


def _node_filters(
    filters: SearchFilters,
    group_ids: list[str] | None,
    alias: str | None = None,
    prefix: str = 'AND',
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    group_clause, group_params = _group_filter(group_ids, alias=alias, prefix='')
    if group_clause:
        clauses.append(group_clause.strip())
        params.update(group_params)
    if filters.node_labels:
        validate_node_labels(filters.node_labels)
        column = f'{alias}.labels' if alias else 'labels'
        clauses.append(f'{column} @> %(node_labels)s::text[]')
        params['node_labels'] = filters.node_labels
    return _where_fragment(clauses, prefix), params


def _edge_filters(
    filters: SearchFilters,
    group_ids: list[str] | None,
    alias: str | None = None,
    prefix: str = 'AND',
) -> tuple[str, dict[str, Any]]:
    if filters.property_filters:
        raise NotImplementedError('PostgresAgeSearchOperations does not support property_filters')
    clauses: list[str] = []
    params: dict[str, Any] = {}
    group_clause, group_params = _group_filter(group_ids, alias=alias, prefix='')
    if group_clause:
        clauses.append(group_clause.strip())
        params.update(group_params)
    if filters.edge_types:
        column = f'{alias}.name' if alias else 'name'
        clauses.append(f'{column} = ANY(%(edge_types)s)')
        params['edge_types'] = filters.edge_types
    if filters.edge_uuids:
        column = f'{alias}.uuid' if alias else 'uuid'
        clauses.append(f'{column} = ANY(%(edge_uuids)s)')
        params['edge_uuids'] = filters.edge_uuids
    if filters.node_labels:
        validate_node_labels(filters.node_labels)
        source_column = f'{alias}.source_node_uuid' if alias else 'source_node_uuid'
        target_column = f'{alias}.target_node_uuid' if alias else 'target_node_uuid'
        clauses.append(
            f"""
            EXISTS (
                SELECT 1
                FROM entity_nodes source_node
                WHERE source_node.uuid = {source_column}
                  AND source_node.labels @> %(node_labels)s::text[]
            )
            AND EXISTS (
                SELECT 1
                FROM entity_nodes target_node
                WHERE target_node.uuid = {target_column}
                  AND target_node.labels @> %(node_labels)s::text[]
            )
            """
        )
        params['node_labels'] = filters.node_labels
    for column_name, filter_groups in (
        ('valid_at', filters.valid_at),
        ('invalid_at', filters.invalid_at),
        ('created_at', filters.created_at),
        ('expired_at', filters.expired_at),
    ):
        date_clause = _date_filter_clause(alias, column_name, filter_groups, params)
        if date_clause:
            clauses.append(date_clause)
    return _where_fragment(clauses, prefix), params


def _where_fragment(clauses: list[str], prefix: str) -> str:
    if not clauses:
        return ''
    return f' {prefix} ' + ' AND '.join(clauses) if prefix else ' AND '.join(clauses)


def _date_filter_clause(
    alias: str | None,
    column_name: str,
    filter_groups: Any,
    params: dict[str, Any],
) -> str:
    if not filter_groups:
        return ''
    column = f'{alias}.{column_name}' if alias else column_name
    or_clauses: list[str] = []
    for group_index, and_group in enumerate(filter_groups):
        and_clauses: list[str] = []
        for filter_index, date_filter in enumerate(and_group):
            operator = date_filter.comparison_operator
            if operator.value in {'IS NULL', 'IS NOT NULL'}:
                and_clauses.append(f'{column} {operator.value}')
                continue
            param_name = f'{column_name}_{group_index}_{filter_index}'
            and_clauses.append(f'{column} {operator.value} %({param_name})s')
            params[param_name] = date_filter.date
        if and_clauses:
            or_clauses.append('(' + ' AND '.join(and_clauses) + ')')
    if not or_clauses:
        return ''
    return '(' + ' OR '.join(or_clauses) + ')'


def _validate_bfs_depth(max_depth: int) -> None:
    if type(max_depth) is not int or not 1 <= max_depth <= 5:
        raise ValueError('max_depth must be between 1 and 5')
