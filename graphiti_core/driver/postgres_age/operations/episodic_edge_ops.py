from __future__ import annotations

from graphiti_core.driver.operations.episodic_edge_ops import EpisodicEdgeOperations
from graphiti_core.driver.postgres_age.operations._edge_base import (
    PostgresAgeSimpleEdgeOperations,
)
from graphiti_core.driver.postgres_age.records import episodic_edge_from_row
from graphiti_core.driver.postgres_age.serialization import episodic_edge_to_row
from graphiti_core.edges import EpisodicEdge


class PostgresAgeEpisodicEdgeOperations(
    PostgresAgeSimpleEdgeOperations[EpisodicEdge], EpisodicEdgeOperations
):
    table_name = 'episodic_edges'
    edge_type = 'MENTIONS'
    source_label = 'Episodic'
    target_label = 'Entity'

    def edge_to_row(self, edge: EpisodicEdge):
        return episodic_edge_to_row(edge)

    def edge_from_row(self, row):
        return episodic_edge_from_row(row)
