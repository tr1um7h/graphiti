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

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterable
from typing import TYPE_CHECKING

from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

# Default model configuration
DEFAULT_BGE_ZH_MODEL = 'BAAI/bge-large-zh-v1.5'
DEFAULT_BGE_ZH_DIM = 1024  # bge-large-zh-v1.5 outputs 1024 dimensions


class BGELargeZHEmbedderConfig(EmbedderConfig):
    """Configuration for BGELargeZH embedder."""

    embedding_model: str = DEFAULT_BGE_ZH_MODEL


class BGELargeZHEmbedder(EmbedderClient):
    """Local BGE Large Chinese embedder using sentence-transformers.

    This embedder runs entirely locally without requiring API keys
    or network calls to external services. It is optimized for Chinese text.

    Default model: BAAI/bge-large-zh-v1.5 (1024 dimensions)

    Example usage:
        >>> embedder = BGELargeZHEmbedder()
        >>> embeddings = await embedder.create(['你好世界'])
        >>> print(len(embeddings))  # 1024
    """

    def __init__(
        self,
        config: BGELargeZHEmbedderConfig | None = None,
        device: str | None = None,
        cache_dir: str | None = None,
    ):
        """Initialize the BGE Large Chinese embedder.

        Args:
            config: Optional configuration for the embedder
            device: Device to run on ('cpu', 'cuda', 'mps', or None for auto)
            cache_dir: Optional cache directory for model files

        Raises:
            ImportError: If sentence-transformers is not installed
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                'sentence-transformers is required for BGELargeZHEmbedder. '
                'Install with: pip install sentence-transformers'
            ) from e

        self.config = config or BGELargeZHEmbedderConfig()
        self.model_name = self.config.embedding_model
        self.embedding_dim = self.config.embedding_dim

        logger.info(f'Loading sentence-transformers model: {self.model_name}')

        # bge-large-zh-v1.5 ships only pytorch_model.bin (no safetensors), so we
        # must disable the safetensors default that newer transformers assume.
        # The model is cached locally and loading never needs the network, so we
        # also drop proxy env vars during loading: a SOCKS proxy without the
        # ``socksio`` package makes httpx raise ImportError during transformers'
        # config probing (the mcp_server venv is affected). Proxies are restored
        # afterwards so downstream components (e.g. LLM clients) are unaffected.
        if cache_dir:
            os.environ['SENTENCE_TRANSFORMERS_HOME'] = cache_dir

        proxy_keys = ('all_proxy', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY')
        saved_proxy = {k: os.environ.pop(k, None) for k in proxy_keys}
        try:
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            try:
                self._model = SentenceTransformer(
                    self.model_name,
                    device=device,
                    trust_remote_code=False,
                    model_kwargs={'use_safetensors': False},
                    local_files_only=True,
                )
                logger.info(f'Model loaded from cache on device: {self._model.device}')
            except Exception as e:
                # If model not cached, attempt one-time download (needs network)
                logger.warning(f'Model {self.model_name} not found locally: {e}')
                logger.info('Attempting one-time download (future runs will be offline)...')
                os.environ.pop('HF_HUB_OFFLINE', None)
                os.environ.pop('TRANSFORMERS_OFFLINE', None)
                for k, v in saved_proxy.items():
                    if v is not None:
                        os.environ[k] = v
                self._model = SentenceTransformer(
                    self.model_name,
                    device=device,
                    trust_remote_code=False,
                    model_kwargs={'use_safetensors': False},
                )
                logger.info(f'Model downloaded and loaded on device: {self._model.device}')
        except Exception as download_error:
            logger.error(f'Failed to load model {self.model_name}: {download_error}')
            raise RuntimeError(
                f'Could not load model {self.model_name}. '
                f'Please ensure the model is cached or network is available for download. '
                f"You can pre-download with: python -c \"from sentence_transformers import "
                f"SentenceTransformer; SentenceTransformer('{self.model_name}', "
                f"model_kwargs={{'use_safetensors': False}})\""
            ) from download_error
        finally:
            for k, v in saved_proxy.items():
                if v is not None:
                    os.environ[k] = v

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        """Create an embedding for the given text input.

        Follows the ``EmbedderClient.create`` contract: always returns a single
        flat embedding vector (the embedding of the input string, or of the
        first string when a list is passed). For multiple vectors use
        :meth:`create_batch`.

        Args:
            input_data: String or list of strings to embed

        Returns:
            Single flat embedding vector
        """
        if isinstance(input_data, str):
            texts: list[str] = [input_data]
        elif isinstance(input_data, list) and all(isinstance(t, str) for t in input_data):
            texts = input_data  # type: ignore[assignment]
        else:
            raise TypeError(f'Unsupported input type: {type(input_data)}')

        if not texts:
            return []

        # Run synchronous encode in executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        embeddings: np.ndarray = await loop.run_in_executor(
            None,
            lambda: self._model.encode(  # type: ignore[misc]
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ),
        )

        # Return the first embedding, sliced to embedding_dim
        return embeddings.tolist()[0][: self.embedding_dim]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """Create embeddings for a batch of text inputs.

        Args:
            input_data_list: List of strings to embed

        Returns:
            List of embedding vectors
        """
        if not input_data_list:
            return []

        # Run synchronous encode in executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        embeddings: np.ndarray = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                input_data_list,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                batch_size=32,  # Process in batches for memory efficiency
            ),
        )

        # Slice to embedding_dim
        return [emb[: self.embedding_dim] for emb in embeddings.tolist()]

    def health_check(self) -> dict:
        """Return health status of the embedder."""
        return {
            'status': 'healthy',
            'model': self.model_name,
            'embedding_dim': self.embedding_dim,
            'device': str(self._model.device),
        }
