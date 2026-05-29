from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from graphiti_core.edges import (
    CommunityEdge,
    EntityEdge,
    EpisodicEdge,
    HasEpisodeEdge,
    NextEpisodeEdge,
)
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode, SagaNode


def entity_node_from_row(row: Mapping[str, Any]) -> EntityNode:
    return EntityNode(
        uuid=row['uuid'],
        name=row['name'],
        group_id=row['group_id'],
        labels=list(row.get('labels') or []),
        summary=row.get('summary') or '',
        attributes=dict(row.get('attributes') or {}),
        name_embedding=_vector_to_list(row.get('name_embedding')),
        created_at=row['created_at'],
    )


def episodic_node_from_row(row: Mapping[str, Any]) -> EpisodicNode:
    return EpisodicNode(
        uuid=row['uuid'],
        name=row['name'],
        group_id=row['group_id'],
        source=EpisodeType.from_str(row['source']),
        source_description=row['source_description'],
        content=row['content'],
        valid_at=row['valid_at'],
        entity_edges=list(row.get('entity_edges') or []),
        episode_metadata=dict(row['episode_metadata']) if row.get('episode_metadata') else None,
        created_at=row['created_at'],
    )


def community_node_from_row(row: Mapping[str, Any]) -> CommunityNode:
    return CommunityNode(
        uuid=row['uuid'],
        name=row['name'],
        group_id=row['group_id'],
        summary=row.get('summary') or '',
        name_embedding=_vector_to_list(row.get('name_embedding')),
        created_at=row['created_at'],
    )


def saga_node_from_row(row: Mapping[str, Any]) -> SagaNode:
    return SagaNode(
        uuid=row['uuid'],
        name=row['name'],
        group_id=row['group_id'],
        summary=row.get('summary') or '',
        first_episode_uuid=row.get('first_episode_uuid'),
        last_episode_uuid=row.get('last_episode_uuid'),
        last_summarized_at=row.get('last_summarized_at'),
        last_summarized_episode_valid_at=row.get('last_summarized_episode_valid_at'),
        created_at=row['created_at'],
    )


def entity_edge_from_row(row: Mapping[str, Any]) -> EntityEdge:
    return EntityEdge(
        uuid=row['uuid'],
        group_id=row['group_id'],
        source_node_uuid=row['source_node_uuid'],
        target_node_uuid=row['target_node_uuid'],
        name=row['name'],
        fact=row['fact'],
        fact_embedding=_vector_to_list(row.get('fact_embedding')),
        episodes=list(row.get('episodes') or []),
        expired_at=row.get('expired_at'),
        valid_at=row.get('valid_at'),
        invalid_at=row.get('invalid_at'),
        reference_time=row.get('reference_time'),
        attributes=dict(row.get('attributes') or {}),
        created_at=row['created_at'],
    )


def episodic_edge_from_row(row: Mapping[str, Any]) -> EpisodicEdge:
    return EpisodicEdge(**_simple_edge_kwargs(row))


def community_edge_from_row(row: Mapping[str, Any]) -> CommunityEdge:
    return CommunityEdge(**_simple_edge_kwargs(row))


def has_episode_edge_from_row(row: Mapping[str, Any]) -> HasEpisodeEdge:
    return HasEpisodeEdge(**_simple_edge_kwargs(row))


def next_episode_edge_from_row(row: Mapping[str, Any]) -> NextEpisodeEdge:
    return NextEpisodeEdge(**_simple_edge_kwargs(row))


def _simple_edge_kwargs(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'uuid': row['uuid'],
        'group_id': row['group_id'],
        'source_node_uuid': row['source_node_uuid'],
        'target_node_uuid': row['target_node_uuid'],
        'created_at': row['created_at'],
    }


def _vector_to_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [float(item) for item in value]
    return [float(item) for item in value]
