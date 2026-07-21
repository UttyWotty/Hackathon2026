"""
Embeddings service using sentence-transformers with nomic-embed-text.

This module provides text embeddings for semantic search / RAG using local models.
Config is driven by environment variables for model selection and cache tuning.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants & environment helpers
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DEFAULT_CACHE_MAX_ITEMS = 256
DEFAULT_CACHE_TTL_SECONDS = 3600

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
EMBEDDING_CACHE_MAX_ITEMS: int = int(
    os.getenv("EMBEDDING_CACHE_MAX_ITEMS", str(DEFAULT_CACHE_MAX_ITEMS))
)
EMBEDDING_CACHE_TTL_SECONDS: int = int(
    os.getenv("EMBEDDING_CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS))
)


def _make_cache_key(model_id: str, text_value: str) -> str:
    """
    Build a stable cache key without storing raw text in memory keys.

    Notes:
      - This is a cache key only (not a security boundary).
      - We hash the content to avoid keeping large strings in the key.
    """
    h = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
    return f"{model_id}|{h}"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class _EmbeddingCache:
    """
    Simple in-memory LRU cache with TTL.

    Stores embeddings keyed by (model/text_hash).
    """

    def __init__(self, *, max_items: int, ttl_seconds: int) -> None:
        self._max_items = max(0, int(max_items))
        self._ttl_seconds = max(0, int(ttl_seconds))
        self._store: "OrderedDict[str, tuple[float, List[float]]]" = OrderedDict()

    def get(self, key: str) -> Optional[List[float]]:
        """Get cached value or None if missing/expired."""
        if self._max_items <= 0 or self._ttl_seconds <= 0:
            return None

        item = self._store.get(key)
        if not item:
            return None

        expires_at, value = item
        now = time.time()
        if expires_at <= now:
            self._store.pop(key, None)
            return None

        # Mark as recently used.
        self._store.move_to_end(key, last=True)
        return value

    def set(self, key: str, value: List[float]) -> None:
        """Set cached value."""
        if self._max_items <= 0 or self._ttl_seconds <= 0:
            return

        expires_at = time.time() + float(self._ttl_seconds)
        self._store[key] = (expires_at, value)
        self._store.move_to_end(key, last=True)

        # Evict LRU
        while len(self._store) > self._max_items:
            self._store.popitem(last=False)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingService:
    """Generate embeddings using sentence-transformers with nomic-embed-text."""

    model_id: str
    _cache: _EmbeddingCache = field(repr=False)
    _model: Optional[SentenceTransformer] = field(repr=False, default=None)

    def __post_init__(self) -> None:
        """Dataclass post-init. Model loading is deferred to first use."""

    def _ensure_model_loaded(self) -> None:
        """Load the sentence-transformer model on first use.

        Deferred loading avoids import-time failures when optional
        dependencies (e.g. einops) are missing but the embedding
        service is not yet needed.
        """
        if self._model is not None:
            return
        logger.info("Loading embedding model: %s", self.model_id)
        self._model = SentenceTransformer(self.model_id, trust_remote_code=True)
        logger.info(
            "Embedding model loaded (dim=%d)",
            self._model.get_sentence_embedding_dimension(),
        )

    @classmethod
    def from_env(cls) -> "EmbeddingService":
        """Construct service from environment."""
        return cls(
            model_id=EMBEDDING_MODEL,
            _cache=_EmbeddingCache(
                max_items=EMBEDDING_CACHE_MAX_ITEMS,
                ttl_seconds=EMBEDDING_CACHE_TTL_SECONDS,
            ),
        )

    def get_embedding(self, text: str) -> List[float]:
        """
        Get a text embedding.

        Args:
            text: Input text.

        Returns:
            Embedding vector as list[float]. Returns [] on failure.
        """
        if not text:
            return []

        cache_key = _make_cache_key(self.model_id, text)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Embedding cache hit (model=%s)", self.model_id)
            return cached

        self._ensure_model_loaded()

        try:
            vector = self._model.encode(text, convert_to_numpy=True)
            embedding = (
                vector.tolist() if isinstance(vector, np.ndarray) else list(vector)
            )

            self._cache.set(cache_key, embedding)
            logger.debug(
                "Generated embedding (model=%s, dims=%d)",
                self.model_id,
                len(embedding),
            )
            return embedding

        except Exception:
            logger.warning("Embedding generation failed", exc_info=True)
            return []

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for multiple texts.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        results: List[Optional[List[float]]] = []
        uncached_texts: List[str] = []
        uncached_indices: List[int] = []

        # Check cache first
        for i, text in enumerate(texts):
            if not text:
                results.append([])
                continue

            cache_key = _make_cache_key(self.model_id, text)
            cached = self._cache.get(cache_key)
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)  # Placeholder
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Fetch uncached embeddings in a single batch call
        if uncached_texts:
            self._ensure_model_loaded()
            try:
                vectors = self._model.encode(uncached_texts, convert_to_numpy=True)

                for idx, vector in zip(uncached_indices, vectors):
                    embedding = (
                        vector.tolist()
                        if isinstance(vector, np.ndarray)
                        else list(vector)
                    )
                    results[idx] = embedding
                    cache_key = _make_cache_key(self.model_id, texts[idx])
                    self._cache.set(cache_key, embedding)

            except Exception:
                logger.warning("Batch embedding generation failed", exc_info=True)
                for idx in uncached_indices:
                    if results[idx] is None:
                        results[idx] = []

        # Replace any remaining None with empty list
        return [r if r is not None else [] for r in results]

    async def get_embedding_async(self, text: str) -> List[float]:
        """
        Async wrapper for get_embedding to avoid blocking the event loop.

        Args:
            text: Input text.

        Returns:
            Embedding vector list.
        """
        return await asyncio.to_thread(self.get_embedding, text)

    async def get_embeddings_batch_async(self, texts: List[str]) -> List[List[float]]:
        """
        Async wrapper for get_embeddings_batch.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors.
        """
        return await asyncio.to_thread(self.get_embeddings_batch, texts)


# Backwards compatibility alias
OllamaEmbeddingService = EmbeddingService
BedrockEmbeddingService = EmbeddingService

# Singleton instance
embedding_service = EmbeddingService.from_env()
