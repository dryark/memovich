"""Text embedding for vector backends (aligned with Chroma default: MiniLM L6 v2, 384-dim)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Callable, List, Sequence

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

EmbedFn = Callable[[Sequence[str]], List[List[float]]]


@lru_cache(maxsize=1)
def _load_fastembed() -> EmbedFn:
    try:
        from fastembed import TextEmbedding
    except ImportError as e:
        raise ImportError(
            "fastembed is required for embeddings. Install with: pip install fastembed"
        ) from e

    model = TextEmbedding(model_name=EMBEDDING_MODEL_ID)
    logger.info("Loaded embedding model: %s", EMBEDDING_MODEL_ID)

    def _embed(texts: Sequence[str]) -> List[List[float]]:
        return [list(vec) for vec in model.embed(list(texts))]

    return _embed


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """Embed a batch of strings; returns one vector per string."""
    if not texts:
        return []
    fn = _load_fastembed()
    return fn(texts)


def get_embed_fn() -> EmbedFn:
    """Return a cached embed function."""
    return _load_fastembed()
