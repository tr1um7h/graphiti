"""In-memory dict-backed graph driver for testing and lightweight usage."""

import logging
import math
from datetime import datetime
from typing import Any, cast

from graphiti_core.driver.driver import GraphDriver, GraphDriverSession, GraphProvider
from graphiti_core.driver.operations.entity_edge_ops import EntityEdgeOperations
from graphiti_core.driver.operations.entity_node_ops import EntityNodeOperations
from graphiti_core.driver.operations.episode_node_ops import EpisodeNodeOperations
from graphiti_core.driver.operations.episodic_edge_ops import EpisodicEdgeOperations
from graphiti_core.driver.operations.search_ops import SearchOperations
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.errors import EdgeNotFoundError, NodeNotFoundError
from graphiti_core.nodes import CommunityNode, EntityNode, EpisodeType, EpisodicNode
from graphiti_core.search.search_filters import SearchFilters
from graphiti_core.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_store(executor: QueryExecutor) -> dict[str, Any]:
    """Extract the in-memory store from a PydictDriver executor."""
    return cast(PydictDriver, executor)._store


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _match_text(text: str | None, query: str) -> bool:
    """Case-insensitive substring match."""
    if not text:
        return False
    q = query.lower().strip()
    return q in text.lower()


def _match_terms(text: str | None, query: str) -> bool:
    """Return True if ANY whitespace-delimited term in *query* appears in *text*."""
    if not text:
        return False
    text_lower = text.lower()
    return any(term and term in text_lower for term in query.lower().split())


def _apply_date_filters(
    value: datetime | None,
    filter_groups: list[list[Any]] | None,
) -> bool:
    """Evaluate OR-of-AND date filter groups against a single datetime value.

    Each inner list is a conjunction (AND); outer list is a disjunction (OR).
    """
    if not filter_groups:
        return True
    return any(all(_check_single_date_filter(value, f) for f in group) for group in filter_groups)


def _check_single_date_filter(value: datetime | None, date_filter: Any) -> bool:
    from graphiti_core.search.search_filters import ComparisonOperator

    op = date_filter.comparison_operator
    target = date_filter.date
    if op == ComparisonOperator.is_null:
        return value is None
    if op == ComparisonOperator.is_not_null:
        return value is not None
    if value is None or target is None:
        return False
    if op == ComparisonOperator.equals:
        return value == target
    if op == ComparisonOperator.not_equals:
        return value != target
    if op == ComparisonOperator.greater_than:
        return value > target
    if op == ComparisonOperator.less_than:
        return value < target
    if op == ComparisonOperator.greater_than_equal:
        return value >= target
    if op == ComparisonOperator.less_than_equal:
        return value <= target
    return True


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


class PydictDriver(GraphDriver):
    """Pure-Python, in-memory graph driver backed by nested dicts.

    Intended for unit tests, prototyping, or scenarios where a real database is
    not available.  All data lives in ``self._store`` and is lost when the
    driver is garbage-collected.
    """

    provider: GraphProvider = GraphProvider.PYDICT
    aoss_client: None = None

    def __init__(
        self,
        db: str = ':memory:',
        max_concurrent_queries: int = 1,
    ):
        super().__init__()
        self.db = db  # kept for interface compatibility; unused

        # The canonical in-memory store.
        self._store: dict[str, Any] = {
            # nodes keyed by uuid
            'entities': {},  # uuid -> EntityNode
            'episodes': {},  # uuid -> EpisodicNode
            'communities': {},  # uuid -> CommunityNode
            # edges keyed by uuid
            'entity_edges': {},  # uuid -> EntityEdge
            'episodic_edges': {},  # uuid -> EpisodicEdge
            # secondary indices
            'entity_by_group': {},  # group_id -> set[uuid]
            'episode_by_group': {},  # group_id -> set[uuid]
            'community_by_group': {},  # group_id -> set[uuid]
            'entity_edge_by_group': {},  # group_id -> set[uuid]
            'episodic_edge_by_group': {},  # group_id -> set[uuid]
            # episode -> mentioned entity uuids
            'episode_mentions': {},  # episode_uuid -> list[entity_uuid]
            # entity uuid -> episodic edge uuids that reference it
            'entity_episodic_edges': {},  # entity_uuid -> set[edge_uuid]
        }

        # Instantiate operations
        self._entity_node_ops = PyDictEntityNodeOperations()
        self._episode_node_ops = PyDictEpisodeNodeOperations()
        self._entity_edge_ops = PyDictEntityEdgeOperations()
        self._episodic_edge_ops = PyDictEpisodicEdgeOperations()
        self._search_ops = PyDictSearchOperations()

    # --- Operations properties ------------------------------------------------

    @property
    def entity_node_ops(self) -> EntityNodeOperations:
        return self._entity_node_ops

    @property
    def episode_node_ops(self) -> EpisodeNodeOperations:
        return self._episode_node_ops

    @property
    def entity_edge_ops(self) -> EntityEdgeOperations:
        return self._entity_edge_ops

    @property
    def episodic_edge_ops(self) -> EpisodicEdgeOperations:
        return self._episodic_edge_ops

    @property
    def search_ops(self) -> SearchOperations:
        return self._search_ops

    # --- QueryExecutor interface ----------------------------------------------

    async def execute_query(self, cypher_query_: str, **kwargs: Any) -> tuple[list[dict], int, int]:
        # PydictDriver bypasses Cypher entirely; operations go through the
        # *Ops classes which manipulate ``_store`` directly.
        return ([], 0, 0)

    def session(self, _database: str | None = None) -> GraphDriverSession:
        return PyDictDriverSession(self)

    async def close(self) -> None:
        pass

    def delete_all_indexes(self, database_: str) -> None:  # noqa: ARG002
        pass

    async def build_indices_and_constraints(self, delete_existing: bool = False) -> None:  # noqa: ARG002
        pass

    # --- High-level convenience API -------------------------------------------

    async def add_memory(
        self,
        name: str,
        relation: str,
        target_name: str,
        *,
        target_type: str = 'Entity',
        group_id: str = 'default',
    ) -> None:
        """Store a simple (subject, relation, object) triplet.

        Example::

            await driver.add_memory('alice', 'works_at', 'paic', target_type='company')
        """
        logger.info(
            '[PyDict] add_memory: name=%s, relation=%s, target=%s (type=%s, group=%s)',
            name,
            relation,
            target_name,
            target_type,
            group_id,
        )

        now = utc_now()

        # --- source entity node ---
        source = EntityNode(
            name=name,
            group_id=group_id,
            created_at=now,
        )

        # --- target entity node ---
        target_labels = [target_type] if target_type and target_type != 'Entity' else []
        target = EntityNode(
            name=target_name,
            labels=target_labels,
            group_id=group_id,
            created_at=now,
        )

        # --- relationship edge ---
        edge = EntityEdge(
            name=relation,
            fact=f'{name} {relation} {target_name}',
            source_node_uuid=source.uuid,
            target_node_uuid=target.uuid,
            group_id=group_id,
            created_at=now,
        )

        # --- episode recording the fact ---
        episode = EpisodicNode(
            name=f'{name} {relation} {target_name}',
            group_id=group_id,
            source=EpisodeType.text,
            source_description='add_memory',
            content=f'{name} {relation} {target_name}',
            valid_at=now,
            created_at=now,
            entity_edges=[edge.uuid],
        )

        # --- episodic edges (MENTIONS) ---
        mention_source = EpisodicEdge(
            source_node_uuid=episode.uuid,
            target_node_uuid=source.uuid,
            group_id=group_id,
            created_at=now,
        )
        mention_target = EpisodicEdge(
            source_node_uuid=episode.uuid,
            target_node_uuid=target.uuid,
            group_id=group_id,
            created_at=now,
        )

        # --- persist via *Ops ---
        await self.entity_node_ops.save(self, source)
        await self.entity_node_ops.save(self, target)
        await self.entity_edge_ops.save(self, edge)
        await self.episode_node_ops.save(self, episode)
        await self.episodic_edge_ops.save(self, mention_source)
        await self.episodic_edge_ops.save(self, mention_target)

        logger.info(
            '[PyDict] add_memory done: source=%s, target=%s, edge=%s, episode=%s',
            source.uuid[:8],
            target.uuid[:8],
            edge.uuid[:8],
            episode.uuid[:8],
        )

    async def search(
        self,
        query: str,
        *,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search stored memories by fulltext match.

        Returns a dict with keys ``nodes``, ``edges``, ``episodes``.

        Example::

            result = await driver.search('which company does alice work at?')
            for edge in result['edges']:
                print(edge.fact)
        """
        logger.info('[PyDict] search: query=%r, group_ids=%s, limit=%d', query, group_ids, limit)

        sf = SearchFilters()

        nodes = await self.search_ops.node_fulltext_search(
            self,
            query,
            sf,
            group_ids=group_ids,
            limit=limit,
        )
        edges = await self.search_ops.edge_fulltext_search(
            self,
            query,
            sf,
            group_ids=group_ids,
            limit=limit,
        )
        episodes = await self.search_ops.episode_fulltext_search(
            self,
            query,
            sf,
            group_ids=group_ids,
            limit=limit,
        )

        logger.info(
            '[PyDict] search results: %d nodes, %d edges, %d episodes',
            len(nodes),
            len(edges),
            len(episodes),
        )

        return {
            'nodes': nodes,
            'edges': edges,
            'episodes': episodes,
        }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class PyDictDriverSession(GraphDriverSession):
    provider = GraphProvider.PYDICT

    def __init__(self, driver: PydictDriver):
        self.driver = driver

    async def __aenter__(self) -> 'PyDictDriverSession':
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        pass

    async def close(self) -> None:
        pass

    async def execute_write(self, func, *args, **kwargs):  # noqa: ANN001
        return await func(self, *args, **kwargs)

    async def run(self, query: str | list, **kwargs: Any) -> Any:
        if isinstance(query, list):
            for cypher, params in query:
                await self.driver.execute_query(cypher, **params)
        else:
            await self.driver.execute_query(query, **kwargs)


# ---------------------------------------------------------------------------
# PyDictEntityNodeOperations
# ---------------------------------------------------------------------------


class PyDictEntityNodeOperations(EntityNodeOperations):
    """CRUD for ``EntityNode`` objects backed by an in-memory dict."""

    async def save(
        self,
        executor: QueryExecutor,
        node: EntityNode,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['entities'][node.uuid] = node
        store.setdefault('entity_by_group', {}).setdefault(node.group_id, set()).add(node.uuid)
        logger.debug('Saved EntityNode: %s', node.uuid)

    async def save_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[EntityNode],
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for node in nodes:
            store['entities'][node.uuid] = node
            store.setdefault('entity_by_group', {}).setdefault(node.group_id, set()).add(node.uuid)

    async def delete(
        self,
        executor: QueryExecutor,
        node: EntityNode,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['entities'].pop(node.uuid, None)
        group_set = store.get('entity_by_group', {}).get(node.group_id)
        if group_set is not None:
            group_set.discard(node.uuid)
        logger.debug('Deleted EntityNode: %s', node.uuid)

    async def delete_by_group_id(
        self,
        executor: QueryExecutor,
        group_id: str,
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        uuids = list(store.get('entity_by_group', {}).get(group_id, set()))
        for uuid in uuids:
            store['entities'].pop(uuid, None)
        store.get('entity_by_group', {}).pop(group_id, None)

    async def delete_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for uuid in uuids:
            node = store['entities'].pop(uuid, None)
            if node is not None:
                group_set = store.get('entity_by_group', {}).get(node.group_id)
                if group_set is not None:
                    group_set.discard(uuid)

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EntityNode:
        store = _get_store(executor)
        node = store['entities'].get(uuid)
        if node is None:
            raise NodeNotFoundError(uuid)
        return node

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EntityNode]:
        store = _get_store(executor)
        return [store['entities'][u] for u in uuids if u in store['entities']]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EntityNode]:
        store = _get_store(executor)
        results: list[EntityNode] = []
        for gid in group_ids:
            for uuid in store.get('entity_by_group', {}).get(gid, set()):
                node = store['entities'].get(uuid)
                if node is None:
                    continue
                if uuid_cursor is not None and uuid >= uuid_cursor:
                    continue
                results.append(node)
        results.sort(key=lambda n: n.uuid, reverse=True)
        if limit is not None:
            results = results[:limit]
        return results

    async def get_by_group_id(
        self,
        executor: QueryExecutor,
        group_id: str,
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EntityNode]:
        return await self.get_by_group_ids(executor, [group_id], limit, uuid_cursor)

    async def load_embeddings_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[EntityNode],
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for node in nodes:
            stored = store['entities'].get(node.uuid)
            if stored is not None:
                node.name_embedding = stored.name_embedding

    async def load_embeddings(
        self,
        executor: QueryExecutor,
        node: EntityNode,
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        stored = store['entities'].get(node.uuid)
        if stored is None:
            raise NodeNotFoundError(node.uuid)
        node.name_embedding = stored.name_embedding


# ---------------------------------------------------------------------------
# PyDictEpisodeNodeOperations
# ---------------------------------------------------------------------------


class PyDictEpisodeNodeOperations(EpisodeNodeOperations):
    """CRUD for ``EpisodicNode`` objects backed by an in-memory dict."""

    async def save(
        self,
        executor: QueryExecutor,
        node: EpisodicNode,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['episodes'][node.uuid] = node
        store.setdefault('episode_by_group', {}).setdefault(node.group_id, set()).add(node.uuid)
        logger.debug('Saved EpisodicNode: %s', node.uuid)

    async def save_bulk(
        self,
        executor: QueryExecutor,
        nodes: list[EpisodicNode],
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for node in nodes:
            store['episodes'][node.uuid] = node
            store.setdefault('episode_by_group', {}).setdefault(node.group_id, set()).add(node.uuid)

    async def delete(
        self,
        executor: QueryExecutor,
        node: EpisodicNode,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['episodes'].pop(node.uuid, None)
        group_set = store.get('episode_by_group', {}).get(node.group_id)
        if group_set is not None:
            group_set.discard(node.uuid)
        store.get('episode_mentions', {}).pop(node.uuid, None)
        logger.debug('Deleted EpisodicNode: %s', node.uuid)

    async def delete_by_group_id(
        self,
        executor: QueryExecutor,
        group_id: str,
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        uuids = list(store.get('episode_by_group', {}).get(group_id, set()))
        for uuid in uuids:
            store['episodes'].pop(uuid, None)
        store.get('episode_by_group', {}).pop(group_id, None)

    async def delete_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for uuid in uuids:
            node = store['episodes'].pop(uuid, None)
            if node is not None:
                group_set = store.get('episode_by_group', {}).get(node.group_id)
                if group_set is not None:
                    group_set.discard(uuid)
                store.get('episode_mentions', {}).pop(uuid, None)

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EpisodicNode:
        store = _get_store(executor)
        node = store['episodes'].get(uuid)
        if node is None:
            raise NodeNotFoundError(uuid)
        return node

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EpisodicNode]:
        store = _get_store(executor)
        return [store['episodes'][u] for u in uuids if u in store['episodes']]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EpisodicNode]:
        store = _get_store(executor)
        results: list[EpisodicNode] = []
        for gid in group_ids:
            for uuid in store.get('episode_by_group', {}).get(gid, set()):
                node = store['episodes'].get(uuid)
                if node is None:
                    continue
                if uuid_cursor is not None and uuid >= uuid_cursor:
                    continue
                results.append(node)
        results.sort(key=lambda n: n.uuid, reverse=True)
        if limit is not None:
            results = results[:limit]
        return results

    async def get_by_entity_node_uuid(
        self,
        executor: QueryExecutor,
        entity_node_uuid: str,
    ) -> list[EpisodicNode]:
        store = _get_store(executor)
        episode_uuids: list[str] = []
        for ep_uuid, mentions in store.get('episode_mentions', {}).items():
            if entity_node_uuid in mentions:
                episode_uuids.append(ep_uuid)
        return [store['episodes'][u] for u in episode_uuids if u in store['episodes']]

    async def retrieve_episodes(
        self,
        executor: QueryExecutor,
        entity_node_uuid: str,
    ) -> list[EpisodicNode]:
        return await self.get_by_entity_node_uuid(executor, entity_node_uuid)


# ---------------------------------------------------------------------------
# PyDictEntityEdgeOperations
# ---------------------------------------------------------------------------


class PyDictEntityEdgeOperations(EntityEdgeOperations):
    """CRUD for ``EntityEdge`` objects backed by an in-memory dict."""

    async def save(
        self,
        executor: QueryExecutor,
        edge: EntityEdge,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['entity_edges'][edge.uuid] = edge
        store.setdefault('entity_edge_by_group', {}).setdefault(edge.group_id, set()).add(edge.uuid)
        # Index by source/target for get_by_node_uuid
        store.setdefault('entity_edge_by_node', {}).setdefault(edge.source_node_uuid, set()).add(
            edge.uuid
        )
        store['entity_edge_by_node'].setdefault(edge.target_node_uuid, set()).add(edge.uuid)
        logger.debug('Saved EntityEdge: %s', edge.uuid)

    async def save_bulk(
        self,
        executor: QueryExecutor,
        edges: list[EntityEdge],
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for edge in edges:
            store['entity_edges'][edge.uuid] = edge
            store.setdefault('entity_edge_by_group', {}).setdefault(edge.group_id, set()).add(
                edge.uuid
            )
            store.setdefault('entity_edge_by_node', {}).setdefault(
                edge.source_node_uuid, set()
            ).add(edge.uuid)
            store['entity_edge_by_node'].setdefault(edge.target_node_uuid, set()).add(edge.uuid)

    async def delete(
        self,
        executor: QueryExecutor,
        edge: EntityEdge,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['entity_edges'].pop(edge.uuid, None)
        group_set = store.get('entity_edge_by_group', {}).get(edge.group_id)
        if group_set is not None:
            group_set.discard(edge.uuid)
        for node_uuid in (edge.source_node_uuid, edge.target_node_uuid):
            node_set = store.get('entity_edge_by_node', {}).get(node_uuid)
            if node_set is not None:
                node_set.discard(edge.uuid)
        logger.debug('Deleted EntityEdge: %s', edge.uuid)

    async def delete_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for uuid in uuids:
            edge = store['entity_edges'].pop(uuid, None)
            if edge is not None:
                group_set = store.get('entity_edge_by_group', {}).get(edge.group_id)
                if group_set is not None:
                    group_set.discard(uuid)
                for node_uuid in (edge.source_node_uuid, edge.target_node_uuid):
                    node_set = store.get('entity_edge_by_node', {}).get(node_uuid)
                    if node_set is not None:
                        node_set.discard(uuid)

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EntityEdge:
        store = _get_store(executor)
        edge = store['entity_edges'].get(uuid)
        if edge is None:
            raise EdgeNotFoundError(uuid)
        return edge

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EntityEdge]:
        store = _get_store(executor)
        return [store['entity_edges'][u] for u in uuids if u in store['entity_edges']]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EntityEdge]:
        store = _get_store(executor)
        results: list[EntityEdge] = []
        for gid in group_ids:
            for uuid in store.get('entity_edge_by_group', {}).get(gid, set()):
                edge = store['entity_edges'].get(uuid)
                if edge is None:
                    continue
                if uuid_cursor is not None and uuid >= uuid_cursor:
                    continue
                results.append(edge)
        results.sort(key=lambda e: e.uuid, reverse=True)
        if limit is not None:
            results = results[:limit]
        return results

    async def get_between_nodes(
        self,
        executor: QueryExecutor,
        source_node_uuid: str,
        target_node_uuid: str,
    ) -> list[EntityEdge]:
        store = _get_store(executor)
        source_edges = store.get('entity_edge_by_node', {}).get(source_node_uuid, set())
        target_edges = store.get('entity_edge_by_node', {}).get(target_node_uuid, set())
        common = source_edges & target_edges
        return [
            store['entity_edges'][u]
            for u in common
            if u in store['entity_edges']
            and store['entity_edges'][u].source_node_uuid == source_node_uuid
            and store['entity_edges'][u].target_node_uuid == target_node_uuid
        ]

    async def get_by_node_uuid(
        self,
        executor: QueryExecutor,
        node_uuid: str,
    ) -> list[EntityEdge]:
        store = _get_store(executor)
        edge_uuids = store.get('entity_edge_by_node', {}).get(node_uuid, set())
        return [store['entity_edges'][u] for u in edge_uuids if u in store['entity_edges']]

    async def load_embeddings(
        self,
        executor: QueryExecutor,
        edge: EntityEdge,
    ) -> None:
        store = _get_store(executor)
        stored = store['entity_edges'].get(edge.uuid)
        if stored is None:
            raise EdgeNotFoundError(edge.uuid)
        edge.fact_embedding = stored.fact_embedding

    async def load_embeddings_bulk(
        self,
        executor: QueryExecutor,
        edges: list[EntityEdge],
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for edge in edges:
            stored = store['entity_edges'].get(edge.uuid)
            if stored is not None:
                edge.fact_embedding = stored.fact_embedding


# ---------------------------------------------------------------------------
# PyDictEpisodicEdgeOperations
# ---------------------------------------------------------------------------


class PyDictEpisodicEdgeOperations(EpisodicEdgeOperations):
    """CRUD for ``EpisodicEdge`` (MENTIONS) objects backed by an in-memory dict."""

    async def save(
        self,
        executor: QueryExecutor,
        edge: EpisodicEdge,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['episodic_edges'][edge.uuid] = edge
        store.setdefault('episodic_edge_by_group', {}).setdefault(edge.group_id, set()).add(
            edge.uuid
        )
        # Maintain episode -> mentioned entity index
        store.setdefault('episode_mentions', {}).setdefault(edge.source_node_uuid, [])
        mentions = store['episode_mentions'][edge.source_node_uuid]
        if edge.target_node_uuid not in mentions:
            mentions.append(edge.target_node_uuid)
        # Maintain entity -> episodic edge index
        store.setdefault('entity_episodic_edges', {}).setdefault(edge.target_node_uuid, set()).add(
            edge.uuid
        )
        logger.debug('Saved EpisodicEdge: %s', edge.uuid)

    async def save_bulk(
        self,
        executor: QueryExecutor,
        edges: list[EpisodicEdge],
        tx: Transaction | None = None,  # noqa: ARG002
        batch_size: int = 100,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for edge in edges:
            store['episodic_edges'][edge.uuid] = edge
            store.setdefault('episodic_edge_by_group', {}).setdefault(edge.group_id, set()).add(
                edge.uuid
            )
            mentions = store.setdefault('episode_mentions', {}).setdefault(
                edge.source_node_uuid, []
            )
            if edge.target_node_uuid not in mentions:
                mentions.append(edge.target_node_uuid)
            store.setdefault('entity_episodic_edges', {}).setdefault(
                edge.target_node_uuid, set()
            ).add(edge.uuid)

    async def delete(
        self,
        executor: QueryExecutor,
        edge: EpisodicEdge,
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        store['episodic_edges'].pop(edge.uuid, None)
        group_set = store.get('episodic_edge_by_group', {}).get(edge.group_id)
        if group_set is not None:
            group_set.discard(edge.uuid)
        # Clean episode mention index
        mentions = store.get('episode_mentions', {}).get(edge.source_node_uuid, [])
        if edge.target_node_uuid in mentions:
            mentions.remove(edge.target_node_uuid)
        entity_set = store.get('entity_episodic_edges', {}).get(edge.target_node_uuid)
        if entity_set is not None:
            entity_set.discard(edge.uuid)
        logger.debug('Deleted EpisodicEdge: %s', edge.uuid)

    async def delete_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
        tx: Transaction | None = None,  # noqa: ARG002
    ) -> None:
        store = _get_store(executor)
        for uuid in uuids:
            edge = store['episodic_edges'].pop(uuid, None)
            if edge is None:
                continue
            group_set = store.get('episodic_edge_by_group', {}).get(edge.group_id)
            if group_set is not None:
                group_set.discard(uuid)
            mentions = store.get('episode_mentions', {}).get(edge.source_node_uuid, [])
            if edge.target_node_uuid in mentions:
                mentions.remove(edge.target_node_uuid)
            entity_set = store.get('entity_episodic_edges', {}).get(edge.target_node_uuid)
            if entity_set is not None:
                entity_set.discard(uuid)

    async def get_by_uuid(
        self,
        executor: QueryExecutor,
        uuid: str,
    ) -> EpisodicEdge:
        store = _get_store(executor)
        edge = store['episodic_edges'].get(uuid)
        if edge is None:
            raise EdgeNotFoundError(uuid)
        return edge

    async def get_by_uuids(
        self,
        executor: QueryExecutor,
        uuids: list[str],
    ) -> list[EpisodicEdge]:
        store = _get_store(executor)
        return [store['episodic_edges'][u] for u in uuids if u in store['episodic_edges']]

    async def get_by_group_ids(
        self,
        executor: QueryExecutor,
        group_ids: list[str],
        limit: int | None = None,
        uuid_cursor: str | None = None,
    ) -> list[EpisodicEdge]:
        store = _get_store(executor)
        results: list[EpisodicEdge] = []
        for gid in group_ids:
            for uuid in store.get('episodic_edge_by_group', {}).get(gid, set()):
                edge = store['episodic_edges'].get(uuid)
                if edge is None:
                    continue
                if uuid_cursor is not None and uuid >= uuid_cursor:
                    continue
                results.append(edge)
        results.sort(key=lambda e: e.uuid, reverse=True)
        if limit is not None:
            results = results[:limit]
        return results


# ---------------------------------------------------------------------------
# PyDictSearchOperations
# ---------------------------------------------------------------------------


class PyDictSearchOperations(SearchOperations):
    """In-memory search operations using brute-force string matching and
    cosine similarity over stored embedding vectors.
    """

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _filter_entity_nodes(
        nodes: list[EntityNode],
        search_filter: SearchFilters | None,
        group_ids: list[str] | None,
    ) -> list[EntityNode]:
        if search_filter is None:
            # Only apply group filter
            if group_ids is None:
                return nodes
            return [n for n in nodes if n.group_id in group_ids]
        results: list[EntityNode] = []
        for node in nodes:
            if group_ids is not None and node.group_id not in group_ids:
                continue
            if search_filter.node_labels and not any(
                lbl in node.labels for lbl in search_filter.node_labels
            ):
                continue
            if not _apply_date_filters(node.created_at, search_filter.created_at):
                continue
            # EntityNode does not carry valid_at/invalid_at/expired_at;
            # those date filters simply do not apply.
            results.append(node)
        return results

    @staticmethod
    def _filter_entity_edges(
        edges: list[EntityEdge],
        search_filter: SearchFilters | None,
        group_ids: list[str] | None,
    ) -> list[EntityEdge]:
        if search_filter is None:
            if group_ids is None:
                return edges
            return [e for e in edges if e.group_id in group_ids]
        results: list[EntityEdge] = []
        for edge in edges:
            if group_ids is not None and edge.group_id not in group_ids:
                continue
            if search_filter.edge_types and edge.name not in search_filter.edge_types:
                continue
            if search_filter.edge_uuids and edge.uuid not in search_filter.edge_uuids:
                continue
            if not _apply_date_filters(edge.valid_at, search_filter.valid_at):
                continue
            if not _apply_date_filters(edge.invalid_at, search_filter.invalid_at):
                continue
            if not _apply_date_filters(edge.expired_at, search_filter.expired_at):
                continue
            if not _apply_date_filters(edge.created_at, search_filter.created_at):
                continue
            results.append(edge)
        return results

    # -- Node search ----------------------------------------------------------

    async def node_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityNode]:
        logger.info('[PyDict] node_fulltext_search: query=%r, group_ids=%s', query, group_ids)
        store = _get_store(executor)
        candidates = [
            node
            for node in store['entities'].values()
            if _match_terms(node.name, query) or _match_terms(node.summary, query)
        ]
        filtered = self._filter_entity_nodes(candidates, search_filter, group_ids)
        results = filtered[:limit]
        logger.info(
            '[PyDict] node_fulltext_search: %d candidates, %d returned',
            len(candidates),
            len(results),
        )
        return results

    async def node_similarity_search(
        self,
        executor: QueryExecutor,
        search_vector: list[float],
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> list[EntityNode]:
        store = _get_store(executor)
        scored: list[tuple[float, EntityNode]] = []
        for node in store['entities'].values():
            if node.name_embedding is None:
                continue
            score = _cosine_similarity(search_vector, node.name_embedding)
            if score >= min_score:
                scored.append((score, node))
        scored.sort(key=lambda t: t[0], reverse=True)
        candidates = [n for _, n in scored]
        filtered = self._filter_entity_nodes(candidates, search_filter, group_ids)
        return filtered[:limit]

    async def node_bfs_search(
        self,
        executor: QueryExecutor,
        origin_uuids: list[str],
        search_filter: SearchFilters,
        max_depth: int,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityNode]:
        if not origin_uuids or max_depth < 1:
            return []
        store = _get_store(executor)
        visited: set[str] = set()
        frontier: set[str] = set(origin_uuids)
        results: list[EntityNode] = []

        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for node_uuid in frontier:
                if node_uuid in visited:
                    continue
                visited.add(node_uuid)
                for edge_uuid in store.get('entity_edge_by_node', {}).get(node_uuid, set()):
                    edge = store['entity_edges'].get(edge_uuid)
                    if edge is None:
                        continue
                    neighbor = (
                        edge.target_node_uuid
                        if edge.source_node_uuid == node_uuid
                        else edge.source_node_uuid
                    )
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
                        node = store['entities'].get(neighbor)
                        if node is not None and node not in results:
                            results.append(node)
                            if len(results) >= limit:
                                break
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
            frontier = next_frontier

        filtered = self._filter_entity_nodes(results, search_filter, group_ids)
        return filtered[:limit]

    # -- Edge search ----------------------------------------------------------

    async def edge_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityEdge]:
        logger.info('[PyDict] edge_fulltext_search: query=%r, group_ids=%s', query, group_ids)
        store = _get_store(executor)
        candidates = [
            edge
            for edge in store['entity_edges'].values()
            if _match_terms(edge.name, query) or _match_terms(edge.fact, query)
        ]
        filtered = self._filter_entity_edges(candidates, search_filter, group_ids)
        results = filtered[:limit]
        logger.info(
            '[PyDict] edge_fulltext_search: %d candidates, %d returned',
            len(candidates),
            len(results),
        )
        return results

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
        store = _get_store(executor)
        scored: list[tuple[float, EntityEdge]] = []
        for edge in store['entity_edges'].values():
            if edge.fact_embedding is None:
                continue
            if source_node_uuid and edge.source_node_uuid != source_node_uuid:
                continue
            if target_node_uuid and edge.target_node_uuid != target_node_uuid:
                continue
            score = _cosine_similarity(search_vector, edge.fact_embedding)
            if score >= min_score:
                scored.append((score, edge))
        scored.sort(key=lambda t: t[0], reverse=True)
        candidates = [e for _, e in scored]
        filtered = self._filter_entity_edges(candidates, search_filter, group_ids)
        return filtered[:limit]

    async def edge_bfs_search(
        self,
        executor: QueryExecutor,
        origin_uuids: list[str],
        max_depth: int,
        search_filter: SearchFilters,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EntityEdge]:
        if not origin_uuids:
            return []
        store = _get_store(executor)
        visited_nodes: set[str] = set()
        frontier: set[str] = set(origin_uuids)
        results: list[EntityEdge] = []

        for _ in range(max_depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for node_uuid in frontier:
                if node_uuid in visited_nodes:
                    continue
                visited_nodes.add(node_uuid)
                for edge_uuid in store.get('entity_edge_by_node', {}).get(node_uuid, set()):
                    edge = store['entity_edges'].get(edge_uuid)
                    if edge is None:
                        continue
                    if edge not in results:
                        results.append(edge)
                        if len(results) >= limit:
                            break
                    neighbor = (
                        edge.target_node_uuid
                        if edge.source_node_uuid == node_uuid
                        else edge.source_node_uuid
                    )
                    next_frontier.add(neighbor)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
            frontier = next_frontier

        filtered = self._filter_entity_edges(results, search_filter, group_ids)
        return filtered[:limit]

    # -- Episode search -------------------------------------------------------

    async def episode_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        search_filter: SearchFilters,  # noqa: ARG002
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[EpisodicNode]:
        logger.info('[PyDict] episode_fulltext_search: query=%r, group_ids=%s', query, group_ids)
        store = _get_store(executor)
        results: list[EpisodicNode] = []
        for episode in store['episodes'].values():
            if group_ids is not None and episode.group_id not in group_ids:
                continue
            if _match_terms(episode.content, query):
                results.append(episode)
                if len(results) >= limit:
                    break
        logger.info('[PyDict] episode_fulltext_search: %d results', len(results))
        return results

    # -- Community search -----------------------------------------------------

    async def community_fulltext_search(
        self,
        executor: QueryExecutor,
        query: str,
        group_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[CommunityNode]:
        store = _get_store(executor)
        results: list[CommunityNode] = []
        for node in store.get('communities', {}).values():
            if group_ids is not None and node.group_id not in group_ids:
                continue
            if _match_terms(node.name, query) or _match_terms(node.summary, query):
                results.append(node)
                if len(results) >= limit:
                    break
        return results

    async def community_similarity_search(
        self,
        executor: QueryExecutor,
        search_vector: list[float],
        group_ids: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.6,
    ) -> list[CommunityNode]:
        store = _get_store(executor)
        scored: list[tuple[float, CommunityNode]] = []
        for node in store.get('communities', {}).values():
            if node.name_embedding is None:
                continue
            if group_ids is not None and node.group_id not in group_ids:
                continue
            score = _cosine_similarity(search_vector, node.name_embedding)
            if score >= min_score:
                scored.append((score, node))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [n for _, n in scored[:limit]]

    # -- Rerankers ------------------------------------------------------------

    async def node_distance_reranker(
        self,
        executor: QueryExecutor,
        node_uuids: list[str],
        center_node_uuid: str,
        min_score: float = 0,
    ) -> list[EntityNode]:
        """Rerank by BFS distance from *center_node_uuid*.

        Nodes directly connected to the center get score=1; others get
        score=0 (treated as infinity distance).  The center itself is placed
        first with a boosted score.
        """
        store = _get_store(executor)
        filtered_uuids = [u for u in node_uuids if u != center_node_uuid]

        # BFS from center to find connected nodes
        connected: set[str] = set()
        frontier: set[str] = {center_node_uuid}
        visited: set[str] = {center_node_uuid}
        for _ in range(2):  # limit BFS depth to 2 for efficiency
            if not frontier:
                break
            next_frontier: set[str] = set()
            for uuid in frontier:
                for edge_uuid in store.get('entity_edge_by_node', {}).get(uuid, set()):
                    edge = store['entity_edges'].get(edge_uuid)
                    if edge is None:
                        continue
                    neighbor = (
                        edge.target_node_uuid
                        if edge.source_node_uuid == uuid
                        else edge.source_node_uuid
                    )
                    if neighbor not in visited:
                        visited.add(neighbor)
                        connected.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier

        # Build ordered list: center first, then connected, then unconnected
        ordered: list[str] = []
        if center_node_uuid in node_uuids:
            ordered.append(center_node_uuid)
        ordered.extend(u for u in filtered_uuids if u in connected)
        ordered.extend(u for u in filtered_uuids if u not in connected)

        nodes = [store['entities'][u] for u in ordered if u in store.get('entities', {})]
        return nodes

    async def episode_mentions_reranker(
        self,
        executor: QueryExecutor,
        node_uuids: list[str],
        min_score: float = 0,
    ) -> list[EntityNode]:
        """Rerank nodes by the number of episodes that mention them (descending)."""
        store = _get_store(executor)
        mention_counts: dict[str, int] = {}
        for ep_mentions in store.get('episode_mentions', {}).values():
            for entity_uuid in ep_mentions:
                if entity_uuid in node_uuids:
                    mention_counts[entity_uuid] = mention_counts.get(entity_uuid, 0) + 1

        scored = [(mention_counts.get(u, 0), u) for u in node_uuids]
        # Sort descending by count; nodes with 0 mentions go last
        scored.sort(key=lambda t: t[0], reverse=True)

        filtered = [u for count, u in scored if count >= min_score]
        return [store['entities'][u] for u in filtered if u in store.get('entities', {})]

    # -- Filter builders ------------------------------------------------------

    def build_node_search_filters(self, search_filters: SearchFilters) -> Any:
        return {'filters': search_filters}

    def build_edge_search_filters(self, search_filters: SearchFilters) -> Any:
        return {'filters': search_filters}

    # -- Fulltext query builder -----------------------------------------------

    def build_fulltext_query(
        self,
        query: str,
        group_ids: list[str] | None = None,  # noqa: ARG002
        max_query_length: int = 8000,
    ) -> str:
        if len(query) > max_query_length:
            return ''
        return query
