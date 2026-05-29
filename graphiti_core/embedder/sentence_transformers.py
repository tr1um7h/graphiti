"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from concurrent.futures import ThreadPoolExecutor
from functools import partial

from pydantic import Field

from .client import EmbedderClient, EmbedderConfig

executor = ThreadPoolExecutor(max_workers=4)


class SentenceTransformerEmbedderConfig(EmbedderConfig):
    model_name: str = Field(default='all-MiniLM-L6-v2')
    device: str = Field(default='cpu')


class SentenceTransformerEmbedder(EmbedderClient):
    """
    Local embedding using SentenceTransformers.

    This embedder runs entirely locally without API calls, suitable for
    environments without external API access or for testing purposes.
    """

    def __init__(
        self,
        config: SentenceTransformerEmbedderConfig | None = None,
        model=None,
        embedding_dim: int = 384,
    ):
        if config is None:
            config = SentenceTransformerEmbedderConfig()
        self.config = config
        self.model = model
        self._embedding_dim = embedding_dim
        self._model_loaded = False

    def _get_model(self):
        if not self._model_loaded:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(
                self.config.model_name, device=self.config.device
            )
            self._model_loaded = True
        return self.model

    async def create(self, input_data: str | list[str]) -> list[float]:
        loop = __import__('asyncio').get_event_loop()
        model = self._get_model()
        encode_fn = partial(model.encode, show_progress_bar=False)
        embedding = await loop.run_in_executor(executor, encode_fn, input_data)
        # model.encode can take str or list[str], both return 2D arrays
        if isinstance(embedding, list):
            return embedding[0][: self._embedding_dim]
        return embedding[0].tolist()[: self._embedding_dim]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        loop = __import__('asyncio').get_event_loop()
        model = self._get_model()
        encode_fn = partial(model.encode, show_progress_bar=False)
        embeddings = await loop.run_in_executor(executor, encode_fn, input_data_list)
        return [emb.tolist()[: self._embedding_dim] for emb in embeddings]