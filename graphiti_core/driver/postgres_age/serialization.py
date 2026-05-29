from __future__ import annotations

from typing import Any

from graphiti_core.edges import (
    CommunityEdge,
    EntityEdge,
    EpisodicEdge,
    HasEpisodeEdge,
    NextEpisodeEdge,
)
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodicNode, SagaNode


def entity_node_to_row(node: EntityNode) -> dict[str, Any]:
    return {
        'uuid': node.uuid,
        'group_id': node.group_id,
        'name': node.name,
        'summary': node.summary,
        'labels': list(node.labels),
        'attributes': dict(node.attributes or {}),
        'name_embedding': node.name_embedding,
        'created_at': node.created_at,
    }


def episodic_node_to_row(node: EpisodicNode) -> dict[str, Any]:
    return {
        'uuid': node.uuid,
        'group_id': node.group_id,
        'name': node.name,
        'source': node.source.value,
        'source_description': node.source_description,
        'content': node.content,
        'valid_at': node.valid_at,
        'entity_edges': list(node.entity_edges),
        'episode_metadata': dict(node.episode_metadata) if node.episode_metadata else None,
        'created_at': node.created_at,
    }


def community_node_to_row(node: CommunityNode) -> dict[str, Any]:
    return {
        'uuid': node.uuid,
        'group_id': node.group_id,
        'name': node.name,
        'summary': node.summary,
        'name_embedding': node.name_embedding,
        'created_at': node.created_at,
    }


def saga_node_to_row(node: SagaNode) -> dict[str, Any]:
    return {
        'uuid': node.uuid,
        'group_id': node.group_id,
        'name': node.name,
        'summary': node.summary,
        'first_episode_uuid': node.first_episode_uuid,
        'last_episode_uuid': node.last_episode_uuid,
        'last_summarized_at': node.last_summarized_at,
        'last_summarized_episode_valid_at': node.last_summarized_episode_valid_at,
        'created_at': node.created_at,
    }


def entity_edge_to_row(edge: EntityEdge) -> dict[str, Any]:
    return {
        'uuid': edge.uuid,
        'group_id': edge.group_id,
        'source_node_uuid': edge.source_node_uuid,
        'target_node_uuid': edge.target_node_uuid,
        'name': edge.name,
        'fact': edge.fact,
        'fact_embedding': edge.fact_embedding,
        'episodes': list(edge.episodes),
        'expired_at': edge.expired_at,
        'valid_at': edge.valid_at,
        'invalid_at': edge.invalid_at,
        'reference_time': edge.reference_time,
        'attributes': dict(edge.attributes or {}),
        'created_at': edge.created_at,
    }


def episodic_edge_to_row(edge: EpisodicEdge) -> dict[str, Any]:
    return _simple_edge_to_row(edge)


def community_edge_to_row(edge: CommunityEdge) -> dict[str, Any]:
    return _simple_edge_to_row(edge)


def has_episode_edge_to_row(edge: HasEpisodeEdge) -> dict[str, Any]:
    return _simple_edge_to_row(edge)


def next_episode_edge_to_row(edge: NextEpisodeEdge) -> dict[str, Any]:
    return _simple_edge_to_row(edge)


def _simple_edge_to_row(edge: EpisodicEdge | CommunityEdge | HasEpisodeEdge | NextEpisodeEdge):
    return {
        'uuid': edge.uuid,
        'group_id': edge.group_id,
        'source_node_uuid': edge.source_node_uuid,
        'target_node_uuid': edge.target_node_uuid,
        'created_at': edge.created_at,
    }
