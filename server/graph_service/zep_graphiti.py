import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException
from graphiti_core import Graphiti  # type: ignore
from graphiti_core.edges import EntityEdge  # type: ignore
from graphiti_core.embedder import EmbedderClient  # type: ignore
from graphiti_core.errors import EdgeNotFoundError, GroupsEdgesNotFoundError, NodeNotFoundError
from graphiti_core.llm_client import LLMClient  # type: ignore
from graphiti_core.nodes import EntityNode, EpisodicNode  # type: ignore

from graph_service.config import DatabaseProvider, ZepEnvDep
from graph_service.dto import FactResult

logger = logging.getLogger(__name__)


def _create_embedder(settings) -> EmbedderClient | None:
    """Create an embedder based on configuration.

    If embedding_api_url is set, use OpenAIEmbedder pointing to the remote
    embedding service. Otherwise return None to let Graphiti use its default.
    """
    embedding_url = settings.embedding_api_url or os.getenv('EMBEDDING_API_URL')
    if embedding_url:
        from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig

        logger.info(f'Using remote embedding service: {embedding_url}')
        config = OpenAIEmbedderConfig(
            api_key='not-needed',
            base_url=embedding_url,
            embedding_model=settings.embedding_model_name or 'all-MiniLM-L6-v2',
            embedding_dim=settings.postgres_age_embedding_dimension,
        )
        return OpenAIEmbedder(config=config)
    return None


def _create_llm_client(settings) -> LLMClient | None:
    """Create an LLM client based on configuration.

    If use_generic_client is True, use OpenAIGenericClient (chat/completions only)
    for providers that don't support /v1/responses (e.g. MiniMax, Ollama).
    """
    use_generic = settings.use_generic_client or os.getenv('USE_GENERIC_CLIENT', '').lower() == 'true'
    if not use_generic:
        return None  # Let Graphiti use its default OpenAIClient

    from graphiti_core.llm_client.config import LLMConfig as CoreLLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

    api_key = settings.openai_api_key or os.getenv('OPENAI_API_KEY', 'sk-placeholder')
    base_url = settings.openai_base_url or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    model = settings.openai_model_name or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o-mini')

    logger.info(f'Using OpenAIGenericClient (chat/completions only) for {model} at {base_url}')
    config = CoreLLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        small_model=model,
        temperature=None,
        max_tokens=4096,
    )
    return OpenAIGenericClient(config=config)


class ZepGraphiti(Graphiti):
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        llm_client: LLMClient | None = None,
        embedder: EmbedderClient | None = None,
        graph_driver=None,
    ):
        # Support both Neo4j and custom graph_driver
        if graph_driver is not None:
            super().__init__(graph_driver=graph_driver, llm_client=llm_client, embedder=embedder)
        else:
            super().__init__(uri, user, password, llm_client, embedder=embedder)

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
        try:
            edges = await EntityEdge.get_by_group_ids(self.driver, [group_id])
        except GroupsEdgesNotFoundError:
            logger.warning(f'No edges found for group {group_id}')
            edges = []

        nodes = await EntityNode.get_by_group_ids(self.driver, [group_id])

        episodes = await EpisodicNode.get_by_group_ids(self.driver, [group_id])

        for edge in edges:
            await edge.delete(self.driver)

        for node in nodes:
            await node.delete(self.driver)

        for episode in episodes:
            await episode.delete(self.driver)

    async def delete_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await edge.delete(self.driver)
        except EdgeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e

    async def delete_episodic_node(self, uuid: str):
        try:
            episode = await EpisodicNode.get_by_uuid(self.driver, uuid)
            await episode.delete(self.driver)
        except NodeNotFoundError as e:
            raise HTTPException(status_code=404, detail=e.message) from e


async def get_graphiti(settings: ZepEnvDep):
    embedder = _create_embedder(settings)
    llm_client = _create_llm_client(settings)

    if settings.database_provider == DatabaseProvider.POSTGRES_AGE:
        from graphiti_core.driver.postgres_age import PostgresAgeDriver

        driver = PostgresAgeDriver(
            dsn=settings.postgres_age_dsn or 'postgresql://graphiti:graphiti@localhost:55432/graphiti',
            graph_name=settings.postgres_age_graph_name or 'graphiti',
            embedding_dimension=settings.postgres_age_embedding_dimension,
        )
        client = ZepGraphiti(graph_driver=driver, embedder=embedder, llm_client=llm_client)
    else:
        client = ZepGraphiti(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            embedder=embedder,
            llm_client=llm_client,
        )

    # Configure LLM client overrides (supports any OpenAI-compatible API)
    if settings.openai_base_url is not None:
        client.llm_client.config.base_url = settings.openai_base_url
    if settings.openai_api_key is not None:
        client.llm_client.config.api_key = settings.openai_api_key
    if settings.openai_model_name is not None:
        client.llm_client.model = settings.openai_model_name

    try:
        yield client
    finally:
        await client.close()


async def initialize_graphiti(settings: ZepEnvDep):
    embedder = _create_embedder(settings)
    llm_client = _create_llm_client(settings)

    if settings.database_provider == DatabaseProvider.POSTGRES_AGE:
        from graphiti_core.driver.postgres_age import PostgresAgeDriver

        driver = PostgresAgeDriver(
            dsn=settings.postgres_age_dsn or 'postgresql://graphiti:graphiti@localhost:55432/graphiti',
            graph_name=settings.postgres_age_graph_name or 'graphiti',
            embedding_dimension=settings.postgres_age_embedding_dimension,
        )
        client = ZepGraphiti(graph_driver=driver, embedder=embedder, llm_client=llm_client)
    else:
        client = ZepGraphiti(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            embedder=embedder,
            llm_client=llm_client,
        )
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
    )


ZepGraphitiDep = Annotated[ZepGraphiti, Depends(get_graphiti)]
