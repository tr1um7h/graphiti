from __future__ import annotations

from graphiti_core.driver.operations.has_episode_edge_ops import HasEpisodeEdgeOperations
from graphiti_core.driver.postgres_age.operations._edge_base import (
    PostgresAgeSimpleEdgeOperations,
)
from graphiti_core.driver.postgres_age.records import has_episode_edge_from_row
from graphiti_core.driver.postgres_age.serialization import has_episode_edge_to_row
from graphiti_core.edges import HasEpisodeEdge


class PostgresAgeHasEpisodeEdgeOperations(
    PostgresAgeSimpleEdgeOperations[HasEpisodeEdge], HasEpisodeEdgeOperations
):
    table_name = 'has_episode_edges'
    edge_type = 'HAS_EPISODE'
    source_label = 'Saga'
    target_label = 'Episodic'

    def edge_to_row(self, edge: HasEpisodeEdge):
        return has_episode_edge_to_row(edge)

    def edge_from_row(self, row):
        return has_episode_edge_from_row(row)
