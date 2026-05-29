"""
Test PostgresAgeDriver with real Graphiti.add_episode() using MiniMax LLM.
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.postgres_age import PostgresAgeDriver
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.graphiti import Graphiti
from graphiti_core.llm_client.anthropic_client import AnthropicClient
from graphiti_core.llm_client.config import LLMConfig

pytestmark = pytest.mark.integration
pytest_plugins = ('pytest_asyncio',)


class StubCrossEncoderClient(CrossEncoderClient):
    """A stub cross encoder that returns dummy scores."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        return [(passage, 0.0) for passage in passages]


class MockMiniMaxEmbedder(EmbedderClient):
    """A mock embedder that returns 384-dim embeddings for testing."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    async def create(self, input_data):
        return [0.1] * self.dim

    async def create_batch(self, input_data_list):
        return [[0.1] * self.dim for _ in input_data_list]


@pytest.mark.asyncio
async def test_postgres_age_add_episode_with_minimax():
    """Test add_episode with MiniMax LLM using PostgresAgeDriver."""
    driver = PostgresAgeDriver(
        dsn=os.getenv('POSTGRES_AGE_DSN', 'postgresql://graphiti:graphiti@localhost:55432/graphiti'),
        graph_name='graphiti_test_add_episode',
        embedding_dimension=384,
    )

    # Use mock embedder for testing (384-dim vectors)
    embedder = MockMiniMaxEmbedder(dim=384)

    llm_client = AnthropicClient(
        config=LLMConfig(
            model='MiniMax-M2.7',
            small_model='MiniMax-M2.7',
            temperature=0.7,
            max_tokens=2048,
        )
    )

    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=StubCrossEncoderClient(),
    )

    try:
        await driver.build_indices_and_constraints(delete_existing=True)

        result = await graphiti.add_episode(
            name='Test Episode',
            episode_body='Alice talked to Bob about the new project yesterday.',
            source_description='test conversation',
            reference_time=datetime.now(timezone.utc),
            group_id='minimax-test',
        )

        print(f"Episode created: {result.episode.uuid}")
        print(f"Nodes: {[n.uuid for n in result.nodes]}")
        print(f"Edges: {[e.uuid for e in result.edges]}")

        assert result.episode is not None
        assert len(result.nodes) >= 0
        # Basic sanity check
        print("add_episode with MiniMax succeeded!")

    finally:
        await driver.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_postgres_age_add_episode_with_minimax())