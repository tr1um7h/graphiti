from __future__ import annotations

import json
import re
from typing import Any, cast

from typing_extensions import LiteralString

_CYPHER_COLUMNS_RE = re.compile(
    r'\A\s*[A-Za-z_][A-Za-z0-9_]*\s+agtype(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s+agtype)*\s*\Z'
)
_IDENTIFIER_RE = re.compile(r'\A[A-Za-z_][A-Za-z0-9_]*\Z')


def cypher_sql(deps: Any, graph_name: str, cypher_query: str, columns: str) -> Any:
    if _CYPHER_COLUMNS_RE.fullmatch(columns) is None:
        raise ValueError('columns must be comma-separated <identifier> agtype definitions')
    delimiter = _dollar_quote_delimiter(cypher_query)

    return deps.sql.SQL('SELECT * FROM cypher({}, {}{}{}) AS ({})').format(
        deps.sql.Literal(graph_name),
        deps.sql.SQL(delimiter),
        deps.sql.SQL(cast(LiteralString, cypher_query)),
        deps.sql.SQL(delimiter),
        deps.sql.SQL(cast(LiteralString, columns)),
    )


def decode_agtype_value(value: Any) -> Any:
    if value is None:
        return None

    text = str(value)
    if text.endswith('::numeric'):
        text = text.removesuffix('::numeric')

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text.strip('"')


def node_projection_cypher(label: str, uuid: str, group_id: str, name: str | None = None) -> str:
    _validate_identifier(label, 'label')
    assignments = [
        f'n.group_id = {_literal(group_id)}',
        f'n.node_kind = {_literal(label)}',
    ]
    if name is not None:
        assignments.append(f'n.name = {_literal(name)}')

    return f"""
    MERGE (n:{label} {{uuid: {_literal(uuid)}}})
    SET {', '.join(assignments)}
    """


def edge_projection_cypher(
    edge_type: str,
    source_label: str,
    target_label: str,
    uuid: str,
    group_id: str,
    source_node_uuid: str,
    target_node_uuid: str,
    name: str | None = None,
) -> str:
    _validate_identifier(edge_type, 'edge_type')
    _validate_identifier(source_label, 'source_label')
    _validate_identifier(target_label, 'target_label')
    assignments = [
        f'e.group_id = {_literal(group_id)}',
        f'e.edge_kind = {_literal(edge_type)}',
    ]
    if name is not None:
        assignments.append(f'e.name = {_literal(name)}')

    return f"""
    MERGE (source_node:{source_label} {{uuid: {_literal(source_node_uuid)}}})
    SET source_node.node_kind = {_literal(source_label)}
    MERGE (target_node:{target_label} {{uuid: {_literal(target_node_uuid)}}})
    SET target_node.node_kind = {_literal(target_label)}
    MERGE (source_node)-[e:{edge_type} {{uuid: {_literal(uuid)}}}]->(target_node)
    SET {', '.join(assignments)}
    """


def edge_delete_projection_cypher(edge_type: str, uuid: str) -> str:
    _validate_identifier(edge_type, 'edge_type')
    return f"""
    MATCH ()-[e:{edge_type} {{uuid: {_literal(uuid)}}}]->()
    DELETE e
    """


def node_delete_projection_cypher(label: str, uuids: list[str]) -> str:
    _validate_identifier(label, 'label')
    return f"""
    MATCH (n:{label})
    WHERE n.uuid IN {_literal(uuids)}
    DETACH DELETE n
    """


def _literal(value: Any) -> str:
    return json.dumps(value)


def _dollar_quote_delimiter(cypher_query: str) -> str:
    for index in range(100):
        delimiter = f'$graphiti_age_{index}$'
        if delimiter not in cypher_query:
            return delimiter
    raise ValueError('Unable to find safe dollar-quote delimiter for AGE Cypher')


def _validate_identifier(value: str, name: str) -> None:
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f'{name} must be a Cypher identifier')
