from __future__ import annotations

from collections import defaultdict
from typing import Any, TypeVar, cast

from graphiti_core.driver.graph_operations.graph_operations import GraphOperationsInterface
from graphiti_core.driver.search_interface.search_interface import SearchInterface
from graphiti_core.edges import (
    CommunityEdge,
    EntityEdge,
    EpisodicEdge,
    HasEpisodeEdge,
    NextEpisodeEdge,
)
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodicNode, SagaNode

T = TypeVar('T')


class PostgresAgeGraphOperationsInterface(GraphOperationsInterface):
    async def node_save(self, node: Any, driver: Any) -> None:
        await driver.entity_node_ops.save(driver, _model(EntityNode, node))

    async def node_delete(self, node: Any, driver: Any) -> None:
        if isinstance(node, EpisodicNode):
            await driver.episode_node_ops.delete(driver, node)
            return
        if isinstance(node, CommunityNode):
            await driver.community_node_ops.delete(driver, node)
            return
        if isinstance(node, SagaNode):
            await driver.saga_node_ops.delete(driver, node)
            return
        await driver.entity_node_ops.delete(driver, _model(EntityNode, node))

    async def node_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        nodes: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.entity_node_ops.save_bulk(
            driver, [_model(EntityNode, node) for node in nodes], transaction, batch_size
        )

    async def node_delete_by_group_id(
        self, _cls: Any, driver: Any, group_id: str, batch_size: int = 100
    ) -> None:
        if _cls is EpisodicNode:
            await driver.episode_node_ops.delete_by_group_id(driver, group_id, batch_size=batch_size)
            return
        if _cls is CommunityNode:
            await driver.community_node_ops.delete_by_group_id(
                driver, group_id, batch_size=batch_size
            )
            return
        if _cls is SagaNode:
            await driver.saga_node_ops.delete_by_group_id(driver, group_id, batch_size=batch_size)
            return
        await driver.entity_node_ops.delete_by_group_id(driver, group_id, batch_size=batch_size)

    async def node_delete_by_uuids(
        self,
        _cls: Any,
        driver: Any,
        uuids: list[str],
        group_id: str | None = None,
        batch_size: int = 100,
    ) -> None:
        if _cls is EpisodicNode:
            await driver.episode_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)
            return
        if _cls is CommunityNode:
            await driver.community_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)
            return
        if _cls is SagaNode:
            await driver.saga_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)
            return
        await driver.entity_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)

    async def node_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.entity_node_ops.get_by_uuid(driver, uuid)

    async def node_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str], group_id: str | None = None
    ) -> list[Any]:
        nodes = await driver.entity_node_ops.get_by_uuids(driver, uuids)
        if group_id is None:
            return nodes
        return [node for node in nodes if node.group_id == group_id]

    async def node_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.entity_node_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def node_load_embeddings(self, node: Any, driver: Any) -> None:
        await driver.entity_node_ops.load_embeddings(driver, _model(EntityNode, node))

    async def node_load_embeddings_bulk(
        self, driver: Any, nodes: list[Any], batch_size: int = 100
    ) -> dict[str, list[float]]:
        typed_nodes = [_model(EntityNode, node) for node in nodes]
        await driver.entity_node_ops.load_embeddings_bulk(driver, typed_nodes, batch_size)
        return {node.uuid: node.name_embedding for node in typed_nodes if node.name_embedding is not None}

    async def episodic_node_save(self, node: Any, driver: Any) -> None:
        await driver.episode_node_ops.save(driver, _model(EpisodicNode, node))

    async def episodic_node_delete(self, node: Any, driver: Any) -> None:
        await driver.episode_node_ops.delete(driver, _model(EpisodicNode, node))

    async def episodic_node_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        nodes: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.episode_node_ops.save_bulk(
            driver, [_model(EpisodicNode, node) for node in nodes], transaction, batch_size
        )

    async def episodic_edge_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        episodic_edges: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.episodic_edge_ops.save_bulk(
            driver,
            [_model(EpisodicEdge, edge) for edge in episodic_edges],
            transaction,
            batch_size,
        )

    async def episodic_node_delete_by_group_id(
        self, _cls: Any, driver: Any, group_id: str, batch_size: int = 100
    ) -> None:
        await driver.episode_node_ops.delete_by_group_id(driver, group_id, batch_size=batch_size)

    async def episodic_node_delete_by_uuids(
        self,
        _cls: Any,
        driver: Any,
        uuids: list[str],
        group_id: str | None = None,
        batch_size: int = 100,
    ) -> None:
        await driver.episode_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)

    async def episodic_node_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.episode_node_ops.get_by_uuid(driver, uuid)

    async def episodic_node_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str]
    ) -> list[Any]:
        return await driver.episode_node_ops.get_by_uuids(driver, uuids)

    async def episodic_node_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.episode_node_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def retrieve_episodes(
        self,
        driver: Any,
        reference_time: Any,
        last_n: int = 3,
        group_ids: list[str] | None = None,
        source: Any | None = None,
        saga: str | None = None,
    ) -> list[Any]:
        return await driver.episode_node_ops.retrieve_episodes(
            driver, reference_time, last_n, group_ids, source, saga
        )

    async def community_node_save(self, node: Any, driver: Any) -> None:
        await driver.community_node_ops.save(driver, _model(CommunityNode, node))

    async def community_node_delete(self, node: Any, driver: Any) -> None:
        await driver.community_node_ops.delete(driver, _model(CommunityNode, node))

    async def community_node_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        nodes: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.community_node_ops.save_bulk(
            driver, [_model(CommunityNode, node) for node in nodes], transaction, batch_size
        )

    async def community_node_delete_by_group_id(
        self, _cls: Any, driver: Any, group_id: str, batch_size: int = 100
    ) -> None:
        await driver.community_node_ops.delete_by_group_id(driver, group_id, batch_size=batch_size)

    async def community_node_delete_by_uuids(
        self,
        _cls: Any,
        driver: Any,
        uuids: list[str],
        group_id: str | None = None,
        batch_size: int = 100,
    ) -> None:
        await driver.community_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)

    async def community_node_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.community_node_ops.get_by_uuid(driver, uuid)

    async def community_node_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str]
    ) -> list[Any]:
        return await driver.community_node_ops.get_by_uuids(driver, uuids)

    async def community_node_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.community_node_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def saga_node_save(self, node: Any, driver: Any) -> None:
        await driver.saga_node_ops.save(driver, _model(SagaNode, node))

    async def saga_node_delete(self, node: Any, driver: Any) -> None:
        await driver.saga_node_ops.delete(driver, _model(SagaNode, node))

    async def saga_node_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        nodes: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.saga_node_ops.save_bulk(
            driver, [_model(SagaNode, node) for node in nodes], transaction, batch_size
        )

    async def saga_node_delete_by_group_id(
        self, _cls: Any, driver: Any, group_id: str, batch_size: int = 100
    ) -> None:
        await driver.saga_node_ops.delete_by_group_id(driver, group_id, batch_size=batch_size)

    async def saga_node_delete_by_uuids(
        self,
        _cls: Any,
        driver: Any,
        uuids: list[str],
        group_id: str | None = None,
        batch_size: int = 100,
    ) -> None:
        await driver.saga_node_ops.delete_by_uuids(driver, uuids, batch_size=batch_size)

    async def saga_node_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.saga_node_ops.get_by_uuid(driver, uuid)

    async def saga_node_get_by_uuids(self, _cls: Any, driver: Any, uuids: list[str]) -> list[Any]:
        return await driver.saga_node_ops.get_by_uuids(driver, uuids)

    async def saga_node_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.saga_node_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def saga_get_previous_episode_uuid(
        self, driver: Any, saga_uuid: str, current_episode_uuid: str
    ) -> str | None:
        return await driver.saga_node_ops.get_previous_episode_uuid(
            driver, saga_uuid, current_episode_uuid
        )

    async def saga_get_episode_contents(
        self, driver: Any, saga_uuid: str, since: Any | None = None, limit: int = 200
    ) -> list[tuple[str, Any]]:
        return await driver.saga_node_ops.get_episode_contents(driver, saga_uuid, since, limit)

    async def edge_save(self, edge: Any, driver: Any) -> None:
        await driver.entity_edge_ops.save(driver, _model(EntityEdge, edge))

    async def edge_delete(self, edge: Any, driver: Any) -> None:
        if isinstance(edge, EpisodicEdge):
            await driver.episodic_edge_ops.delete(driver, edge)
            return
        if isinstance(edge, CommunityEdge):
            await driver.community_edge_ops.delete(driver, edge)
            return
        if isinstance(edge, HasEpisodeEdge):
            await driver.has_episode_edge_ops.delete(driver, edge)
            return
        if isinstance(edge, NextEpisodeEdge):
            await driver.next_episode_edge_ops.delete(driver, edge)
            return
        await driver.entity_edge_ops.delete(driver, _model(EntityEdge, edge))

    async def edge_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        edges: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.entity_edge_ops.save_bulk(
            driver, [_model(EntityEdge, edge) for edge in edges], transaction, batch_size
        )

    async def edge_delete_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str], group_id: str | None = None
    ) -> None:
        if _cls is EpisodicEdge:
            await driver.episodic_edge_ops.delete_by_uuids(driver, uuids)
            return
        if _cls is CommunityEdge:
            await driver.community_edge_ops.delete_by_uuids(driver, uuids)
            return
        if _cls is HasEpisodeEdge:
            await driver.has_episode_edge_ops.delete_by_uuids(driver, uuids)
            return
        if _cls is NextEpisodeEdge:
            await driver.next_episode_edge_ops.delete_by_uuids(driver, uuids)
            return
        await driver.entity_edge_ops.delete_by_uuids(driver, uuids)

    async def edge_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.entity_edge_ops.get_by_uuid(driver, uuid)

    async def edge_get_by_uuids(self, _cls: Any, driver: Any, uuids: list[str]) -> list[Any]:
        return await driver.entity_edge_ops.get_by_uuids(driver, uuids)

    async def edge_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.entity_edge_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def edge_load_embeddings(self, edge: Any, driver: Any) -> None:
        await driver.entity_edge_ops.load_embeddings(driver, _model(EntityEdge, edge))

    async def edge_load_embeddings_bulk(
        self, driver: Any, edges: list[Any], batch_size: int = 100
    ) -> dict[str, list[float]]:
        typed_edges = [_model(EntityEdge, edge) for edge in edges]
        await driver.entity_edge_ops.load_embeddings_bulk(driver, typed_edges, batch_size)
        return {edge.uuid: edge.fact_embedding for edge in typed_edges if edge.fact_embedding is not None}

    async def episodic_edge_save(self, edge: Any, driver: Any) -> None:
        await driver.episodic_edge_ops.save(driver, _model(EpisodicEdge, edge))

    async def episodic_edge_delete(self, edge: Any, driver: Any) -> None:
        await driver.episodic_edge_ops.delete(driver, _model(EpisodicEdge, edge))

    async def episodic_edge_delete_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str], group_id: str | None = None
    ) -> None:
        await driver.episodic_edge_ops.delete_by_uuids(driver, uuids)

    async def episodic_edge_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.episodic_edge_ops.get_by_uuid(driver, uuid)

    async def episodic_edge_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str]
    ) -> list[Any]:
        return await driver.episodic_edge_ops.get_by_uuids(driver, uuids)

    async def episodic_edge_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.episodic_edge_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def community_edge_save(self, edge: Any, driver: Any) -> None:
        await driver.community_edge_ops.save(driver, _model(CommunityEdge, edge))

    async def community_edge_delete(self, edge: Any, driver: Any) -> None:
        await driver.community_edge_ops.delete(driver, _model(CommunityEdge, edge))

    async def community_edge_delete_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str], group_id: str | None = None
    ) -> None:
        await driver.community_edge_ops.delete_by_uuids(driver, uuids)

    async def community_edge_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.community_edge_ops.get_by_uuid(driver, uuid)

    async def community_edge_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str]
    ) -> list[Any]:
        return await driver.community_edge_ops.get_by_uuids(driver, uuids)

    async def community_edge_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.community_edge_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def has_episode_edge_save(self, edge: Any, driver: Any) -> None:
        await driver.has_episode_edge_ops.save(driver, _model(HasEpisodeEdge, edge))

    async def has_episode_edge_delete(self, edge: Any, driver: Any) -> None:
        await driver.has_episode_edge_ops.delete(driver, _model(HasEpisodeEdge, edge))

    async def has_episode_edge_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        edges: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.has_episode_edge_ops.save_bulk(
            driver, [_model(HasEpisodeEdge, edge) for edge in edges], transaction, batch_size
        )

    async def has_episode_edge_delete_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str], group_id: str | None = None
    ) -> None:
        await driver.has_episode_edge_ops.delete_by_uuids(driver, uuids)

    async def has_episode_edge_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.has_episode_edge_ops.get_by_uuid(driver, uuid)

    async def has_episode_edge_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str]
    ) -> list[Any]:
        return await driver.has_episode_edge_ops.get_by_uuids(driver, uuids)

    async def has_episode_edge_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.has_episode_edge_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def next_episode_edge_save(self, edge: Any, driver: Any) -> None:
        await driver.next_episode_edge_ops.save(driver, _model(NextEpisodeEdge, edge))

    async def next_episode_edge_delete(self, edge: Any, driver: Any) -> None:
        await driver.next_episode_edge_ops.delete(driver, _model(NextEpisodeEdge, edge))

    async def next_episode_edge_save_bulk(
        self,
        _cls: Any,
        driver: Any,
        transaction: Any,
        edges: list[Any],
        batch_size: int = 100,
    ) -> None:
        await driver.next_episode_edge_ops.save_bulk(
            driver, [_model(NextEpisodeEdge, edge) for edge in edges], transaction, batch_size
        )

    async def next_episode_edge_delete_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str], group_id: str | None = None
    ) -> None:
        await driver.next_episode_edge_ops.delete_by_uuids(driver, uuids)

    async def next_episode_edge_get_by_uuid(self, _cls: Any, driver: Any, uuid: str) -> Any:
        return await driver.next_episode_edge_ops.get_by_uuid(driver, uuid)

    async def next_episode_edge_get_by_uuids(
        self, _cls: Any, driver: Any, uuids: list[str]
    ) -> list[Any]:
        return await driver.next_episode_edge_ops.get_by_uuids(driver, uuids)

    async def next_episode_edge_get_by_group_ids(
        self,
        _cls: Any,
        driver: Any,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[Any]:
        return await driver.next_episode_edge_ops.get_by_group_ids(driver, group_ids, limit, uuid_cursor)

    async def get_mentioned_nodes(self, driver: Any, episodes: list[Any]) -> list[Any]:
        return await driver.graph_ops.get_mentioned_nodes(driver, episodes)

    async def get_communities_by_nodes(self, driver: Any, nodes: list[Any]) -> list[Any]:
        return await driver.graph_ops.get_communities_by_nodes(driver, nodes)

    async def clear_data(self, driver: Any, group_ids: list[str] | None = None) -> None:
        await driver.graph_ops.clear_data(driver, group_ids)

    async def get_community_clusters(
        self, driver: Any, group_ids: list[str] | None
    ) -> list[list[Any]]:
        return await driver.graph_ops.get_community_clusters(driver, group_ids)

    async def remove_communities(self, driver: Any) -> None:
        await driver.graph_ops.remove_communities(driver)

    async def determine_entity_community(self, driver: Any, entity: Any) -> tuple[Any | None, bool]:
        return await driver.graph_ops.determine_entity_community(driver, entity)

    async def episodic_node_get_by_entity_node_uuid(
        self, _cls: Any, driver: Any, entity_node_uuid: str
    ) -> list[Any]:
        return await driver.episode_node_ops.get_by_entity_node_uuid(driver, entity_node_uuid)

    async def community_node_load_name_embedding(self, node: Any, driver: Any) -> None:
        await driver.community_node_ops.load_name_embedding(driver, _model(CommunityNode, node))

    async def edge_get_between_nodes(
        self, _cls: Any, driver: Any, source_node_uuid: str, target_node_uuid: str
    ) -> list[Any]:
        return await driver.entity_edge_ops.get_between_nodes(
            driver, source_node_uuid, target_node_uuid
        )

    async def edge_get_by_node_uuid(self, _cls: Any, driver: Any, node_uuid: str) -> list[Any]:
        return await driver.entity_edge_ops.get_by_node_uuid(driver, node_uuid)


class PostgresAgeSearchInterface(SearchInterface):
    async def edge_fulltext_search(
        self,
        driver: Any,
        query: str,
        search_filter: Any,
        group_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await driver.search_ops.edge_fulltext_search(
            driver, query, search_filter, group_ids, limit
        )

    async def edge_similarity_search(
        self,
        driver: Any,
        search_vector: list[float],
        source_node_uuid: str | None,
        target_node_uuid: str | None,
        search_filter: Any,
        group_ids: list[str] | None = None,
        limit: int = 100,
        min_score: float = 0.7,
    ) -> list[Any]:
        return await driver.search_ops.edge_similarity_search(
            driver,
            search_vector,
            source_node_uuid,
            target_node_uuid,
            search_filter,
            group_ids,
            limit,
            min_score,
        )

    async def node_fulltext_search(
        self,
        driver: Any,
        query: str,
        search_filter: Any,
        group_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await driver.search_ops.node_fulltext_search(
            driver, query, search_filter, group_ids, limit
        )

    async def node_similarity_search(
        self,
        driver: Any,
        search_vector: list[float],
        search_filter: Any,
        group_ids: list[str] | None = None,
        limit: int = 100,
        min_score: float = 0.7,
    ) -> list[Any]:
        return await driver.search_ops.node_similarity_search(
            driver, search_vector, search_filter, group_ids, limit, min_score
        )

    async def episode_fulltext_search(
        self,
        driver: Any,
        query: str,
        search_filter: Any,
        group_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await driver.search_ops.episode_fulltext_search(
            driver, query, search_filter, group_ids, limit
        )

    async def edge_bfs_search(
        self,
        driver: Any,
        bfs_origin_node_uuids: list[str] | None,
        bfs_max_depth: int,
        search_filter: Any,
        group_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await driver.search_ops.edge_bfs_search(
            driver, bfs_origin_node_uuids or [], bfs_max_depth, search_filter, group_ids, limit
        )

    async def node_bfs_search(
        self,
        driver: Any,
        bfs_origin_node_uuids: list[str] | None,
        search_filter: Any,
        bfs_max_depth: int,
        group_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await driver.search_ops.node_bfs_search(
            driver, bfs_origin_node_uuids or [], search_filter, bfs_max_depth, group_ids, limit
        )

    async def community_fulltext_search(
        self,
        driver: Any,
        query: str,
        group_ids: list[str] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        return await driver.search_ops.community_fulltext_search(driver, query, group_ids, limit)

    async def community_similarity_search(
        self,
        driver: Any,
        search_vector: list[float],
        group_ids: list[str] | None = None,
        limit: int = 100,
        min_score: float = 0.6,
    ) -> list[Any]:
        return await driver.search_ops.community_similarity_search(
            driver, search_vector, group_ids, limit, min_score
        )

    async def get_embeddings_for_communities(
        self, driver: Any, communities: list[Any]
    ) -> dict[str, list[float]]:
        typed = [_model(CommunityNode, community) for community in communities]
        result: dict[str, list[float]] = {}
        for community in typed:
            await driver.community_node_ops.load_name_embedding(driver, community)
            if community.name_embedding is not None:
                result[community.uuid] = community.name_embedding
        return result

    async def node_distance_reranker(
        self,
        driver: Any,
        node_uuids: list[str],
        center_node_uuid: str,
        min_score: float = 0,
    ) -> tuple[list[str], list[float]]:
        if not node_uuids:
            return [], []
        records, _, _ = await driver.execute_query(
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
            SELECT requested.uuid,
                   CASE
                    WHEN coalesce(distances.distance, 1000000) = 0 THEN 10.0
                    WHEN distances.distance IS NULL THEN 0.0
                    ELSE 1.0 / distances.distance
                   END AS score
            FROM unnest(%(node_uuids)s::text[]) WITH ORDINALITY AS requested(uuid, ordinal)
            LEFT JOIN distances ON distances.uuid = requested.uuid
            WHERE CASE
                    WHEN coalesce(distances.distance, 1000000) = 0 THEN 10.0
                    WHEN distances.distance IS NULL THEN 0.0
                    ELSE 1.0 / distances.distance
                  END >= %(min_score)s
            ORDER BY coalesce(distances.distance, 1000000), requested.ordinal
            """,
            params={
                'node_uuids': node_uuids,
                'center_node_uuid': center_node_uuid,
                'min_score': min_score,
            },
            routing_='r',
        )
        return [row['uuid'] for row in records], [row['score'] for row in records]

    async def episode_mentions_reranker(
        self,
        driver: Any,
        node_uuids: list[list[str]],
        min_score: float = 0,
    ) -> tuple[list[str], list[float]]:
        sorted_uuids, _ = _rrf(node_uuids)
        if not sorted_uuids:
            return [], []
        records, _, _ = await driver.execute_query(
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
            SELECT uuid, mention_count AS score
            FROM mention_counts
            WHERE mention_count >= %(min_score)s
            ORDER BY mention_count DESC, ordinal
            """,
            params={'node_uuids': sorted_uuids, 'min_score': min_score},
            routing_='r',
        )
        return [row['uuid'] for row in records], [row['score'] for row in records]

    def build_node_search_filters(self, search_filters: Any) -> Any:
        return driverless_search_ops().build_node_search_filters(search_filters)

    def build_edge_search_filters(self, search_filters: Any) -> Any:
        return driverless_search_ops().build_edge_search_filters(search_filters)


def _model(model: type[T], value: Any) -> T:
    if isinstance(value, model):
        return value
    model_with_validate = cast(Any, model)
    if hasattr(model_with_validate, 'model_validate'):
        return cast(T, model_with_validate.model_validate(value))
    return model(**value)


def _rrf(results: list[list[str]], rank_const: int = 1, min_score: float = 0) -> tuple[list[str], list[float]]:
    scores: dict[str, float] = defaultdict(float)
    for result in results:
        for index, uuid in enumerate(result):
            scores[uuid] += 1 / (index + rank_const)
    scored_uuids = sorted(scores.items(), reverse=True, key=lambda item: item[1])
    return [uuid for uuid, score in scored_uuids if score >= min_score], [
        score for _, score in scored_uuids if score >= min_score
    ]


def driverless_search_ops():
    from graphiti_core.driver.postgres_age.operations.search_ops import PostgresAgeSearchOperations

    return PostgresAgeSearchOperations()
