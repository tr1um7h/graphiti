import logging
from typing import Annotated

from fastapi import Depends, HTTPException
from graphiti_core import Graphiti  # type: ignore
from graphiti_core.edges import EntityEdge  # type: ignore
from graphiti_core.embedder import EmbedderClient  # type: ignore
from graphiti_core.errors import EdgeNotFoundError, GroupsEdgesNotFoundError, NodeNotFoundError
from graphiti_core.llm_client import LLMClient  # type: ignore
from graphiti_core.nodes import EntityNode, EpisodicNode  # type: ignore

from graph_service.config import DatabaseProvider, Settings, ZepEnvDep
from graph_service.dto import FactResult

logger = logging.getLogger(__name__)


def _create_embedder(settings: Settings) -> EmbedderClient | None:
    """Create an embedder based on configuration.

    If embedding_api_url is set, use OpenAIEmbedder pointing to the remote
    embedding service. Otherwise return None to let Graphiti use its default.
    """
    if settings.embedding_api_url:
        import httpx
        from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
        from openai import AsyncOpenAI

        logger.info(f'Using remote embedding service: {settings.embedding_api_url}')
        config = OpenAIEmbedderConfig(
            api_key='not-needed',
            base_url=settings.embedding_api_url,
            embedding_model=settings.embedding_model or 'all-MiniLM-L6-v2',
            embedding_dim=settings.postgres_age_embedding_dimension,
        )
        # Use a generous timeout for local embedding services that may be slow
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), trust_env=False)
        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            http_client=http_client,
        )
        return OpenAIEmbedder(config=config, client=client)

    if settings.embedder_provider == 'bge_zh':
        from graphiti_core.embedder.bge_zh import BGELargeZHEmbedder, BGELargeZHEmbedderConfig

        logger.info('Using local BGELargeZH embedder (BAAI/bge-large-zh-v1.5, 1024d)')
        config = BGELargeZHEmbedderConfig(
            embedding_dim=settings.postgres_age_embedding_dimension or 1024,
        )
        return BGELargeZHEmbedder(config=config)

    return None


def _create_llm_client(settings: Settings) -> LLMClient | None:
    """Create an LLM client based on configuration.

    If use_generic_client is True, use OpenAIGenericClient (chat/completions only)
    for providers that don't support /v1/responses (e.g. MiniMax, Ollama).
    """
    if not settings.use_generic_client:
        return None  # Let Graphiti use its default OpenAIClient

    from graphiti_core.llm_client.config import LLMConfig as CoreLLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

    api_key = settings.openai_api_key or 'sk-placeholder'
    base_url = settings.openai_base_url or 'https://api.openai.com/v1'
    model = settings.openai_model_name or 'gpt-4o-mini'

    logger.info(f'Using OpenAIGenericClient (chat/completions only) for {model} at {base_url}')
    config = CoreLLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        small_model=model,
        temperature=None,
        max_tokens=settings.openai_max_tokens,
    )
    return OpenAIGenericClient(config=config)


def _create_driver(settings: Settings):
    """Create a graph database driver based on the configured provider."""
    if settings.database_provider == DatabaseProvider.POSTGRES_AGE:
        from graphiti_core.driver.postgres_age import PostgresAgeDriver

        dsn = settings.postgres_age_dsn
        logger.info(f'Connecting to PostgreSQL AGE: graph={settings.postgres_age_graph_name}')
        return PostgresAgeDriver(
            dsn=dsn,
            graph_name=settings.postgres_age_graph_name or 'graphiti',
            embedding_dimension=settings.postgres_age_embedding_dimension,
        )
    else:
        raise ValueError(f'Unsupported database provider: {settings.database_provider}')


class ZepGraphiti(Graphiti):
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        llm_client: LLMClient | None = None,
        embedder: EmbedderClient | None = None,
        graph_driver=None,
        tracer=None,
    ):
        # Support both Neo4j and custom graph_driver
        if graph_driver is not None:
            super().__init__(
                graph_driver=graph_driver, llm_client=llm_client, embedder=embedder, tracer=tracer
            )
        else:
            super().__init__(uri, user, password, llm_client, embedder=embedder, tracer=tracer)

    async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = ''):
        new_node = EntityNode(
            name=name,
            uuid=uuid,
            group_id=group_id,
            summary=summary,
        )
        await new_node.generate_name_embedding(self.embedder)
        await new_node.save(self.driver)
        return new_node

    async def get_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            return edge
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_group(self, group_id: str):
        driver = self.driver
        schema = getattr(driver, 'schema', 'public')

        # Delete in FK dependency order: edges first, then nodes
        # Edge tables (FK references to node tables)
        edge_tables = [
            'entity_edges',
            'episodic_edges',
            'community_edges',
            'has_episode_edges',
            'next_episode_edges',
        ]
        # Node tables (saga_nodes has FK to episodic_nodes)
        node_tables = [
            'saga_nodes',
            'community_nodes',
            'episodic_nodes',
            'entity_nodes',
        ]

        for table in edge_tables + node_tables:
            await driver.execute_query(
                f'DELETE FROM {schema}.{table} WHERE group_id = %(group_id)s',
                params={'group_id': group_id},
            )

        # Rebuild AGE graph projection after bulk delete
        try:
            await driver.graph_ops.rebuild_age_projection(driver)
        except Exception as e:
            logger.warning(f'Failed to rebuild AGE projection after group delete: {e}')

    async def delete_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await edge.delete(self.driver)
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_episodic_node(self, uuid: str):
        try:
            await self.remove_episode(uuid)
        except NodeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e


def _build_client(settings: Settings) -> ZepGraphiti:
    """Create a ZepGraphiti client from settings."""
    embedder = _create_embedder(settings)
    llm_client = _create_llm_client(settings)
    driver = _create_driver(settings)
    from graph_service.observability import setup_tracing

    tracer = setup_tracing()
    client = ZepGraphiti(
        graph_driver=driver, embedder=embedder, llm_client=llm_client, tracer=tracer
    )

    # Apply LLM overrides on the default client (when _create_llm_client returned None)
    if llm_client is None:
        if settings.openai_base_url is not None:
            client.llm_client.config.base_url = settings.openai_base_url
        if settings.openai_api_key is not None:
            client.llm_client.config.api_key = settings.openai_api_key
        if settings.openai_model_name is not None:
            client.llm_client.model = settings.openai_model_name
        if settings.openai_max_tokens:
            client.llm_client.config.max_tokens = settings.openai_max_tokens

    return client


async def get_graphiti(settings: ZepEnvDep):
    client = _build_client(settings)
    try:
        yield client
    finally:
        await client.close()


async def initialize_graphiti(settings: ZepEnvDep):
    client = _build_client(settings)
    await client.build_indices_and_constraints()


def get_fact_result_from_edge(edge: EntityEdge):
    return FactResult(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact,
        valid_at=edge.valid_at,
        invalid_at=edge.invalid_at,
        created_at=edge.created_at,
        expired_at=edge.expired_at,
        source_node_uuid=edge.source_node_uuid,
        target_node_uuid=edge.target_node_uuid,
    )


ZepGraphitiDep = Annotated[ZepGraphiti, Depends(get_graphiti)]
