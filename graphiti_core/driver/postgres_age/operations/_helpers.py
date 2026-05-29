from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from graphiti_core.driver.postgres_age.projection import cypher_sql, node_delete_projection_cypher
from graphiti_core.driver.query_executor import QueryExecutor, Transaction


@asynccontextmanager
async def operation_transaction(
    executor: QueryExecutor, tx: Transaction | None
) -> AsyncIterator[Transaction | None]:
    if tx is not None:
        yield tx
        return

    transaction_factory = getattr(executor, 'transaction', None)
    if transaction_factory is None:
        yield None
        return

    async with transaction_factory() as new_tx:
        yield new_tx


async def run_statement(
    executor: QueryExecutor,
    tx: Transaction | None,
    query: str,
    params: dict[str, Any],
) -> None:
    if tx is not None:
        await tx.run(query, params=params)
    else:
        await executor.execute_query(query, params=params)


async def fetch_records(
    executor: QueryExecutor,
    tx: Transaction | None,
    query: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    if tx is not None:
        records, _, _ = await tx.run(query, params=params)
    else:
        records, _, _ = await executor.execute_query(query, params=params, routing_='r')
    return records


async def run_age_cypher(
    executor: QueryExecutor,
    tx: Transaction | None,
    cypher_query: str,
    columns: str = 'value agtype',
) -> None:
    postgres_executor: Any = executor
    deps = postgres_executor._deps
    graph_name = postgres_executor.graph_name
    query = cypher_sql(deps, graph_name, cypher_query, columns)
    if tx is not None:
        await tx.run(query, params=None)
    else:
        await executor.execute_query(query, params=None)


async def delete_node_projection(
    executor: QueryExecutor,
    tx: Transaction | None,
    label: str,
    uuids: list[str],
) -> None:
    if not uuids:
        return
    await run_age_cypher(executor, tx, node_delete_projection_cypher(label, uuids))


def jsonb(executor: QueryExecutor, value: dict[str, Any] | None) -> Any:
    deps = getattr(executor, '_deps', None)
    if deps is None or value is None:
        return value
    return deps.Jsonb(value)


def source_value(source: Any | None) -> str | None:
    if source is None:
        return None
    value = getattr(source, 'value', None)
    if isinstance(value, str):
        return value
    name = getattr(source, 'name', None)
    if isinstance(name, str):
        return name
    return str(source)
