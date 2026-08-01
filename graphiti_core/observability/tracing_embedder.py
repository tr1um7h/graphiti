"""Wrapper that adds tracing to any EmbedderClient without modifying it."""

from collections.abc import Iterable

from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.tracer import NoOpTracer, Tracer


class TracingEmbedder(EmbedderClient):
    """Wraps an EmbedderClient and emits graphiti.llm.embed spans."""

    def __init__(self, inner: EmbedderClient, tracer: Tracer | None = None) -> None:
        self._inner = inner
        self._tracer = tracer or NoOpTracer()

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        with self._tracer.start_span('llm.embed') as span:
            try:
                result = await self._inner.create(input_data)
                span.add_attributes({'embedding.dimension': len(result)})
                return result
            except Exception as e:
                span.set_status('error', str(e))
                span.record_exception(e)
                raise

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        with self._tracer.start_span('llm.embed') as span:
            span.add_attributes({'batch.size': len(input_data_list)})
            try:
                results = await self._inner.create_batch(input_data_list)
                span.add_attributes({'batch.result_count': len(results)})
                return results
            except Exception as e:
                span.set_status('error', str(e))
                span.record_exception(e)
                raise

    @property
    def model(self) -> str | None:
        """Expose inner embedder's model name for span attributes if available."""
        config = getattr(self._inner, 'config', None)
        if config is not None:
            return getattr(config, 'embedding_model', None) or getattr(config, 'model_name', None)
        return None
