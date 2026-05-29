from __future__ import annotations

from graphiti_core.driver.operations.next_episode_edge_ops import NextEpisodeEdgeOperations
from graphiti_core.driver.postgres_age.operations._edge_base import (
    PostgresAgeSimpleEdgeOperations,
)
from graphiti_core.driver.postgres_age.records import next_episode_edge_from_row
from graphiti_core.driver.postgres_age.serialization import next_episode_edge_to_row
from graphiti_core.edges import NextEpisodeEdge


class PostgresAgeNextEpisodeEdgeOperations(
    PostgresAgeSimpleEdgeOperations[NextEpisodeEdge], NextEpisodeEdgeOperations
):
    table_name = 'next_episode_edges'
    edge_type = 'NEXT_EPISODE'
    source_label = 'Episodic'
    target_label = 'Episodic'

    def edge_to_row(self, edge: NextEpisodeEdge):
        return next_episode_edge_to_row(edge)

    def edge_from_row(self, row):
        return next_episode_edge_from_row(row)
