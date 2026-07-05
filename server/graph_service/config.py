from enum import Enum
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class DatabaseProvider(str, Enum):
    NEO4J = 'neo4j'
    POSTGRES_AGE = 'postgres_age'


class Settings(BaseSettings):
    """Graphiti Server configuration.

    Environment variables mirror the MCP server's config schema so that both
    services share identical configuration semantics.
    """

    # --- LLM configuration (OpenAI-compatible) ---------------------------
    openai_api_key: str | None = Field(None)
    openai_base_url: str | None = Field(None)
    openai_model_name: str | None = Field(None)
    use_generic_client: bool = Field(
        default=False,
        description='Use OpenAIGenericClient for providers without /v1/responses (e.g. MiniMax)',
    )
    openai_max_tokens: int = Field(default=16384, description='Max tokens for LLM responses')
    llm_timeout: int = Field(default=600, description='LLM request timeout in seconds')

    # --- Embedder configuration ------------------------------------------
    embedder_provider: str = Field(default='bge_zh')
    embedding_api_url: str | None = Field(
        default=None,
        description='Base URL for the embedding API (e.g. http://localhost:8080/v1)',
    )
    embedding_model: str = Field(default='BAAI/bge-large-zh-v1.5')

    # --- PostgreSQL AGE configuration -------------------------------------
    database_provider: DatabaseProvider = Field(default=DatabaseProvider.POSTGRES_AGE)
    postgres_age_dsn: str = Field(
        default='postgresql://graphiti:graphiti@localhost:55432/graphiti',
        description='PostgreSQL AGE connection DSN',
    )
    postgres_age_graph_name: str = Field(default='graphiti')
    postgres_age_embedding_dimension: int = Field(default=1024)

    # --- Neo4j configuration (legacy fallback) ----------------------------
    neo4j_uri: str | None = Field(None)
    neo4j_user: str | None = Field(None)
    neo4j_password: str | None = Field(None)

    # --- Telemetry --------------------------------------------------------
    graphiti_telemetry_enabled: bool = Field(default=False)

    # --- Server -----------------------------------------------------------
    port: int = Field(default=8000, description='Server listen port')

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


@lru_cache
def get_settings():
    return Settings()  # type: ignore[call-arg]


ZepEnvDep = Annotated[Settings, Depends(get_settings)]
