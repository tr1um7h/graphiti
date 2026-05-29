from __future__ import annotations

CANONICAL_TABLES: tuple[str, ...] = (
    'next_episode_edges',
    'has_episode_edges',
    'community_edges',
    'episodic_edges',
    'entity_edges',
    'saga_nodes',
    'community_nodes',
    'episodic_nodes',
    'entity_nodes',
)

NODE_TABLES: tuple[str, ...] = (
    'entity_nodes',
    'episodic_nodes',
    'community_nodes',
    'saga_nodes',
)

EDGE_TABLES: tuple[str, ...] = (
    'entity_edges',
    'episodic_edges',
    'community_edges',
    'has_episode_edges',
    'next_episode_edges',
)

B_TREE_INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    ('entity_nodes_group_id_idx', 'entity_nodes', 'group_id'),
    ('entity_nodes_name_idx', 'entity_nodes', 'name'),
    ('entity_nodes_created_at_idx', 'entity_nodes', 'created_at'),
    ('episodic_nodes_group_id_idx', 'episodic_nodes', 'group_id'),
    ('episodic_nodes_created_at_idx', 'episodic_nodes', 'created_at'),
    ('episodic_nodes_valid_at_idx', 'episodic_nodes', 'valid_at'),
    ('community_nodes_group_id_idx', 'community_nodes', 'group_id'),
    ('saga_nodes_group_id_idx', 'saga_nodes', 'group_id'),
    ('saga_nodes_name_idx', 'saga_nodes', 'name'),
    ('entity_edges_group_id_idx', 'entity_edges', 'group_id'),
    ('entity_edges_source_node_uuid_idx', 'entity_edges', 'source_node_uuid'),
    ('entity_edges_target_node_uuid_idx', 'entity_edges', 'target_node_uuid'),
    ('entity_edges_name_idx', 'entity_edges', 'name'),
    ('entity_edges_created_at_idx', 'entity_edges', 'created_at'),
    ('entity_edges_expired_at_idx', 'entity_edges', 'expired_at'),
    ('entity_edges_valid_at_idx', 'entity_edges', 'valid_at'),
    ('entity_edges_invalid_at_idx', 'entity_edges', 'invalid_at'),
    ('episodic_edges_group_id_idx', 'episodic_edges', 'group_id'),
    ('episodic_edges_source_node_uuid_idx', 'episodic_edges', 'source_node_uuid'),
    ('episodic_edges_target_node_uuid_idx', 'episodic_edges', 'target_node_uuid'),
    ('community_edges_group_id_idx', 'community_edges', 'group_id'),
    ('community_edges_source_node_uuid_idx', 'community_edges', 'source_node_uuid'),
    ('community_edges_target_node_uuid_idx', 'community_edges', 'target_node_uuid'),
    ('has_episode_edges_group_id_idx', 'has_episode_edges', 'group_id'),
    ('has_episode_edges_source_node_uuid_idx', 'has_episode_edges', 'source_node_uuid'),
    ('has_episode_edges_target_node_uuid_idx', 'has_episode_edges', 'target_node_uuid'),
    ('next_episode_edges_group_id_idx', 'next_episode_edges', 'group_id'),
    ('next_episode_edges_source_node_uuid_idx', 'next_episode_edges', 'source_node_uuid'),
    ('next_episode_edges_target_node_uuid_idx', 'next_episode_edges', 'target_node_uuid'),
)

GIN_INDEX_SPECS: tuple[tuple[str, str], ...] = (
    ('entity_nodes_search_vector_idx', 'entity_nodes'),
    ('episodic_nodes_search_vector_idx', 'episodic_nodes'),
    ('community_nodes_search_vector_idx', 'community_nodes'),
    ('entity_edges_search_vector_idx', 'entity_edges'),
)

HNSW_INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    ('entity_nodes_name_embedding_hnsw_idx', 'entity_nodes', 'name_embedding'),
    ('community_nodes_name_embedding_hnsw_idx', 'community_nodes', 'name_embedding'),
    ('entity_edges_fact_embedding_hnsw_idx', 'entity_edges', 'fact_embedding'),
)

INDEX_NAMES: tuple[str, ...] = tuple(
    index_name
    for index_name, *_rest in B_TREE_INDEX_SPECS + GIN_INDEX_SPECS + HNSW_INDEX_SPECS
)

VECTOR_COLUMNS: tuple[tuple[str, str], ...] = (
    ('entity_nodes', 'name_embedding'),
    ('community_nodes', 'name_embedding'),
    ('entity_edges', 'fact_embedding'),
)
