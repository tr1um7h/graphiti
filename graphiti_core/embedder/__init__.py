from .client import EmbedderClient
from .openai import OpenAIEmbedder, OpenAIEmbedderConfig
from .sentence_transformers import SentenceTransformerEmbedder

__all__ = [
    'EmbedderClient',
    'OpenAIEmbedder',
    'OpenAIEmbedderConfig',
    'SentenceTransformerEmbedder',
]

# BGELargeZH embedder for Chinese text is optionally available
try:
    from .bge_zh import BGELargeZHEmbedder, BGELargeZHEmbedderConfig  # noqa: F401

    __all__.extend(['BGELargeZHEmbedder', 'BGELargeZHEmbedderConfig'])
except ImportError:
    pass
