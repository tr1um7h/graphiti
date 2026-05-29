from __future__ import annotations

from graphiti_core.driver.operations.community_edge_ops import CommunityEdgeOperations
from graphiti_core.driver.postgres_age.operations._edge_base import (
    PostgresAgeSimpleEdgeOperations,
)
from graphiti_core.driver.postgres_age.operations._helpers import run_age_cypher
from graphiti_core.driver.postgres_age.projection import (
    edge_delete_projection_cypher,
    edge_projection_cypher,
)
from graphiti_core.driver.postgres_age.records import community_edge_from_row
from graphiti_core.driver.postgres_age.serialization import community_edge_to_row
from graphiti_core.driver.query_executor import QueryExecutor, Transaction
from graphiti_core.edges import CommunityEdge
from graphiti_core.errors import NodeNotFoundError


class PostgresAgeCommunityEdgeOperations(
    PostgresAgeSimpleEdgeOperations[CommunityEdge], CommunityEdgeOperations
):
    table_name = 'community_edges'
    edge_type = 'HAS_MEMBER'
    source_label = 'Community'
    target_label = 'Entity'

    def edge_to_row(self, edge: CommunityEdge):
        return community_edge_to_row(edge)

    def edge_from_row(self, row):
        return community_edge_from_row(row)

    async def _save_projection(
        self,
        executor: QueryExecutor,
        tx: Transaction | None,
        edge: CommunityEdge,
    ) -> None:
        target_label = await self._target_label(executor, tx, edge.target_node_uuid)
        await run_age_cypher(
            executor,
            tx,
            edge_delete_projection_cypher(self.edge_type, edge.uuid),
        )
        await run_age_cypher(
            executor,
            tx,
            edge_projection_cypher(
                self.edge_type,
                self.source_label,
                target_label,
                edge.uuid,
                edge.group_id,
                edge.source_node_uuid,
                edge.target_node_uuid,
            ),
        )

    async def _target_label(
        self,
        executor: QueryExecutor,
        tx: Transaction | None,
        target_node_uuid: str,
    ) -> str:
        query = """
        SELECT EXISTS(
            SELECT 1 FROM community_nodes WHERE uuid = %(target_node_uuid)s
        ) AS is_community,
        EXISTS(
            SELECT 1 FROM entity_nodes WHERE uuid = %(target_node_uuid)s
        ) AS is_entity
        """
        if tx is not None:
            records, _, _ = await tx.run(query, params={'target_node_uuid': target_node_uuid})
        else:
            records, _, _ = await executor.execute_query(
                query,
                params={'target_node_uuid': target_node_uuid},
                routing_='r',
            )
        if records and records[0]['is_community']:
            return 'Community'
        if records and records[0]['is_entity']:
            return 'Entity'
        raise NodeNotFoundError(target_node_uuid)
