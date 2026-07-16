# tests/search/seed.py
"""Deterministic fixture graph for BFS tests.

Topology (per spec §4):
- Chain: Alice→AcmeCorp→SanFrancisco→USA (G1) and mirror in G2
- Reverse chain: SinkX→MidY→TopZ (G1, G2 mirror) — TopZ has no outgoing edges
- Star: LeadBob→{EmpCarol, EmpDave, EmpEve}
- Cluster A (3-clique): NodeA1↔NodeA2↔NodeA3
- Cluster B (3-clique): NodeB1↔NodeB2↔NodeB3
- Clique Q (5-clique): Q1..Q5 fully connected
- Temporal: OldEvent (2020), NewEvent (2025)
- Salary (semantic miss #23): Alice→SalaryNode
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.nodes import EntityNode

NAMESPACE = uuid.UUID('6c7f4f1c-2b8a-4d32-9c1a-3f4e5d6b7a8c')
FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def make_uuid(group_id: str, *parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, ':'.join([group_id, *parts])))


@dataclass
class BFSGraphContext:
    group_id: str
    group_id_2: str
    nodes: dict[str, str] = field(default_factory=dict)        # name -> uuid (G1)
    nodes_g2: dict[str, str] = field(default_factory=dict)     # name -> uuid (G2 mirror)
    edges: dict[str, EntityEdge] = field(default_factory=dict)  # edge_key -> seed EntityEdge
    created_at: datetime = FIXED_NOW


def _node(name: str, group_id: str, labels: list[str], summary: str = '') -> EntityNode:
    return EntityNode(
        uuid=make_uuid(group_id, name),
        name=name,
        group_id=group_id,
        labels=labels,
        created_at=FIXED_NOW,
        summary=summary or name,
        attributes={},
    )


def _edge(
    src_name: str,
    edge_name: str,
    dst_name: str,
    group_id: str,
    fact: str | None = None,
    valid_at: datetime | None = None,
    expired_at: datetime | None = None,
) -> EntityEdge:
    src_uuid = make_uuid(group_id, src_name)
    dst_uuid = make_uuid(group_id, dst_name)
    return EntityEdge(
        uuid=make_uuid(group_id, src_name, edge_name, dst_name),
        source_node_uuid=src_uuid,
        target_node_uuid=dst_uuid,
        name=edge_name,
        fact=fact or f'{src_name} {edge_name} {dst_name}',
        group_id=group_id,
        created_at=FIXED_NOW,
        valid_at=valid_at or FIXED_NOW,
        expired_at=expired_at,
        episodes=[],
    )


async def _save_node(driver: GraphDriver, embedder: EmbedderClient, node: EntityNode):
    await node.generate_name_embedding(embedder)
    await node.save(driver)


async def _save_edge(driver: GraphDriver, embedder: EmbedderClient, edge: EntityEdge):
    await edge.generate_embedding(embedder)
    await edge.save(driver)


async def seed_bfs_graph(
    driver: GraphDriver,
    embedder: EmbedderClient,
    group_id: str,
    group_id_2: str,
) -> BFSGraphContext:
    """Seed all BFS fixture topologies in both groups. Returns context with UUID maps."""
    ctx = BFSGraphContext(group_id=group_id, group_id_2=group_id_2)

    # ---- G1 nodes ----
    g1_node_specs = [
        # Chain
        ('Alice', ['Person']), ('AcmeCorp', ['Company']),
        ('SanFrancisco', ['City']), ('USA', ['Country']),
        # Reverse chain
        ('SinkX', ['Concept']), ('MidY', ['Concept']), ('TopZ', ['Concept']),
        # Star
        ('LeadBob', ['Person']), ('EmpCarol', ['Person']),
        ('EmpDave', ['Person']), ('EmpEve', ['Person']),
        # Cluster A
        ('NodeA1', ['Concept']), ('NodeA2', ['Concept']), ('NodeA3', ['Concept']),
        # Cluster B
        ('NodeB1', ['Concept']), ('NodeB2', ['Concept']), ('NodeB3', ['Concept']),
        # Clique Q
        ('Q1', ['Concept']), ('Q2', ['Concept']), ('Q3', ['Concept']),
        ('Q4', ['Concept']), ('Q5', ['Concept']),
        # Temporal
        ('OldEvent', ['Event']), ('NewEvent', ['Event']),
        ('2020Anchor', ['Date']), ('2025Anchor', ['Date']),
        # Salary
        ('SalaryNode', ['Concept'], 'monthly compensation amount in USD'),
    ]
    g1_nodes: dict[str, EntityNode] = {}
    for spec in g1_node_specs:
        name = spec[0]
        labels = spec[1]
        summary = spec[2] if len(spec) > 2 else ''
        node = _node(name, group_id, labels, summary)
        g1_nodes[name] = node
        ctx.nodes[name] = node.uuid
        await _save_node(driver, embedder, node)

    # ---- G1 edges ----
    g1_edges: list[EntityEdge] = [
        # Chain
        _edge('Alice', 'WORKS_AT', 'AcmeCorp', group_id),
        _edge('AcmeCorp', 'LOCATED_IN', 'SanFrancisco', group_id),
        _edge('SanFrancisco', 'IN_COUNTRY', 'USA', group_id),
        # Reverse chain (SinkX→MidY→TopZ; TopZ has no outgoing)
        _edge('SinkX', 'BELONGS_TO', 'MidY', group_id),
        _edge('MidY', 'PART_OF', 'TopZ', group_id),
        # Star
        _edge('LeadBob', 'MANAGES', 'EmpCarol', group_id),
        _edge('LeadBob', 'MANAGES', 'EmpDave', group_id),
        _edge('LeadBob', 'MANAGES', 'EmpEve', group_id),
        # Cluster A (3-clique)
        _edge('NodeA1', 'RELATED', 'NodeA2', group_id),
        _edge('NodeA2', 'RELATED', 'NodeA3', group_id),
        _edge('NodeA3', 'RELATED', 'NodeA1', group_id),
        # Cluster B (3-clique)
        _edge('NodeB1', 'RELATED', 'NodeB2', group_id),
        _edge('NodeB2', 'RELATED', 'NodeB3', group_id),
        _edge('NodeB3', 'RELATED', 'NodeB1', group_id),
        # Temporal
        _edge(
            'OldEvent', 'OCCURRED_ON', '2020Anchor', group_id,
            valid_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expired_at=datetime(2020, 12, 31, tzinfo=timezone.utc),
        ),
        _edge(
            'NewEvent', 'OCCURRED_ON', '2025Anchor', group_id,
            valid_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        # Salary (#23)
        _edge('Alice', 'HAS_SALARY', 'SalaryNode', group_id),
    ]
    # Clique Q (5-clique, 10 edges)
    q_nodes = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
    for i, src in enumerate(q_nodes):
        for dst in q_nodes[i + 1:]:
            g1_edges.append(_edge(src, 'LINKED', dst, group_id))

    for edge in g1_edges:
        key = f'{edge.name}:{edge.source_node_uuid}:{edge.target_node_uuid}'
        ctx.edges[key] = edge
        await _save_edge(driver, embedder, edge)

    # ---- G2 mirror (chain + reverse chain) ----
    g2_chain_nodes = [
        ('Alice2', ['Person']), ('AcmeCorp2', ['Company']),
        ('SanFrancisco2', ['City']), ('USA2', ['Country']),
        ('SinkX2', ['Concept']), ('MidY2', ['Concept']), ('TopZ2', ['Concept']),
    ]
    for spec in g2_chain_nodes:
        name = spec[0]
        labels = spec[1]
        node = _node(name, group_id_2, labels)
        ctx.nodes_g2[name] = node.uuid
        await _save_node(driver, embedder, node)

    g2_edges = [
        _edge('Alice2', 'WORKS_AT', 'AcmeCorp2', group_id_2),
        _edge('AcmeCorp2', 'LOCATED_IN', 'SanFrancisco2', group_id_2),
        _edge('SanFrancisco2', 'IN_COUNTRY', 'USA2', group_id_2),
        _edge('SinkX2', 'BELONGS_TO', 'MidY2', group_id_2),
        _edge('MidY2', 'PART_OF', 'TopZ2', group_id_2),
    ]
    for edge in g2_edges:
        key = f'{edge.name}:{edge.source_node_uuid}:{edge.target_node_uuid}'
        ctx.edges[key] = edge
        await _save_edge(driver, embedder, edge)

    return ctx
