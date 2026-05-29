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
    # OpenAI-compatible LLM configuration (supports MiniMax and any OpenAI API compatible provider)
    openai_api_key: str | None = Field(None)
    openai_base_url: str | None = Field(None)
    openai_model_name: str | None = Field(None)
    use_generic_client: bool = Field(default=False, description='Use OpenAIGenericClient for providers without /v1/responses (e.g. MiniMax)')

    # Embedder configuration
    embedder_provider: str = Field(default='openai', description='Embedder provider: openai or sentence-transformers')
    embedding_api_url: str | None = Field(None, description='Base URL for the embedding API (e.g. http://embedding-service:8080/v1)')
    embedding_model_name: str = Field(default='all-MiniLM-L6-v2', description='Embedding model name')

    # Neo4j configuration (legacy)
    neo4j_uri: str | None = Field(None)
    neo4j_user: str | None = Field(None)
    neo4j_password: str | None = Field(None)

    # Postgres AGE configuration (alternative to Neo4j)
    database_provider: DatabaseProvider = Field(default=DatabaseProvider.POSTGRES_AGE)
    postgres_age_dsn: str | None = Field(default=None)
    postgres_age_graph_name: str | None = Field(default=None)
    postgres_age_embedding_dimension: int = Field(default=384)

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


@lru_cache
def get_settings():
    return Settings()  # type: ignore[call-arg]


ZepEnvDep = Annotated[Settings, Depends(get_settings)]
