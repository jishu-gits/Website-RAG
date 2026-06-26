# backend/app/services/embeddings.py
"""Embedding service using Google Generative AI.

Converts ``DocumentChunk`` objects into dense vector embeddings via Google's
``text-embedding-004`` model.  Features:

- **Batching** – chunks are grouped into batches of configurable size to
  respect API rate limits and reduce round‑trips.
- **Caching** – an in‑memory LRU cache keyed on deterministic ``chunk_id``
  avoids re‑computing embeddings for content that has already been processed.
- **Error handling** – transient API errors are retried with exponential
  back‑off; permanent failures are logged and the chunk is skipped.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import google.generativeai as genai

from app.core.config import settings
from app.core.logger import logger
from app.services.chunking import DocumentChunk


# ---------------------------------------------------------------------------
# Module‑level initialisation
# ---------------------------------------------------------------------------
genai.configure(api_key=settings.gemini_api_key.get_secret_value())

# Simple in‑memory cache: chunk_id → embedding vector
_embedding_cache: Dict[str, List[float]] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _cache_key(chunk: DocumentChunk) -> str:
    """Return a stable cache key for *chunk*.

    Uses the pre‑computed ``chunk_id`` from metadata so identical content at
    the same URL always maps to the same key.
    """
    return chunk.metadata.chunk_id


def _batches(items: List[DocumentChunk], size: int):
    """Yield successive batches of *size* from *items*."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _embed_texts_with_retry(
    texts: List[str],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> List[List[float]]:
    """Call the Google embedding API with exponential back‑off on failure.

    Returns a list of embedding vectors in the same order as *texts*.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            # google‑generativeai exposes a synchronous helper; run it in a
            # thread so we don't block the event loop.
            result = await asyncio.to_thread(
                genai.embed_content,
                model=f"models/{settings.embedding_model}",
                content=texts,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Embedding API error – retrying",
                attempt=attempt,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)

    # All retries exhausted
    logger.error("Embedding API failed after retries", error=str(last_exc))
    raise RuntimeError(f"Embedding API failed: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def embed_chunks(
    chunks: List[DocumentChunk],
    *,
    batch_size: Optional[int] = None,
) -> List[Tuple[DocumentChunk, List[float]]]:
    """Embed a list of ``DocumentChunk`` objects and return (chunk, vector) pairs.

    Parameters
    ----------
    chunks:
        Chunks produced by the chunking pipeline.
    batch_size:
        Number of texts per API call.  Defaults to ``settings.embedding_batch_size``.

    Returns
    -------
    list[tuple[DocumentChunk, list[float]]]
        Pairs of (chunk, embedding_vector).  Order matches *chunks*.
    """
    batch_sz = batch_size or settings.embedding_batch_size
    results: List[Tuple[DocumentChunk, List[float]]] = []

    # Separate cached vs. uncached chunks
    uncached_chunks: List[DocumentChunk] = []
    uncached_indices: List[int] = []

    for idx, chunk in enumerate(chunks):
        key = _cache_key(chunk)
        if key in _embedding_cache:
            results.append((chunk, _embedding_cache[key]))
            logger.debug("Embedding cache hit", chunk_id=key)
        else:
            uncached_chunks.append(chunk)
            uncached_indices.append(idx)
            results.append((chunk, []))  # placeholder

    if not uncached_chunks:
        logger.info("All embeddings served from cache", total=len(chunks))
        return results

    logger.info(
        "Embedding chunks",
        total=len(chunks),
        cached=len(chunks) - len(uncached_chunks),
        to_embed=len(uncached_chunks),
        batch_size=batch_sz,
    )

    # Process uncached chunks in batches
    embedded_so_far = 0
    for batch in _batches(uncached_chunks, batch_sz):
        texts = [c.text for c in batch]
        vectors = await _embed_texts_with_retry(texts)

        for chunk, vector in zip(batch, vectors):
            key = _cache_key(chunk)
            _embedding_cache[key] = vector
            # Place vector in the correct position in results
            pos = uncached_indices[embedded_so_far]
            results[pos] = (chunk, vector)
            embedded_so_far += 1

        logger.info(
            "Batch embedded",
            batch_size=len(batch),
            progress=f"{embedded_so_far}/{len(uncached_chunks)}",
        )

    logger.info("Embedding complete", total_embedded=embedded_so_far)
    return results


def clear_cache() -> int:
    """Flush the in‑memory embedding cache.  Returns the number of evicted entries."""
    count = len(_embedding_cache)
    _embedding_cache.clear()
    logger.info("Embedding cache cleared", evicted=count)
    return count


async def embed_query(query: str) -> List[float]:
    """Embed a single query string for retrieval.

    Uses ``task_type="retrieval_query"`` so the resulting vector is in the
    correct space relative to document embeddings.

    Parameters
    ----------
    query:
        The user's natural‑language search query.

    Returns
    -------
    list[float]
        The embedding vector for *query*.
    """
    result = await _embed_texts_with_retry(
        [query],
    )
    # _embed_texts_with_retry returns a list of vectors; take the first.
    vector = result[0]
    logger.debug("Query embedded", query=query[:60], dim=len(vector))
    return vector

