# backend/app/services/embeddings.py
"""Embedding service using the Google GenAI SDK.

Converts ``DocumentChunk`` objects into dense vector embeddings via Google's
embedding models.  Features:

- **Batching** – chunks are grouped into batches of configurable size to
  respect API rate limits and reduce round-trips.
- **Caching** – an in-memory dict keyed on deterministic ``chunk_id``
  avoids re-computing embeddings for content that has already been processed.
- **Error handling** – transient API errors are retried with exponential
  back-off; permanent failures are logged and propagated.
- **Task-type separation** – document embeddings use ``RETRIEVAL_DOCUMENT``,
  query embeddings use ``RETRIEVAL_QUERY`` so vectors are in the correct
  subspace for asymmetric similarity search.
- **Startup validation** – ``validate_embedding_model()`` fires a single
  test embedding on startup and fails fast if the configured model is
  unsupported or unreachable.

SDK migration notes (2026-06):
  - Replaced deprecated ``google-generativeai`` (EOL Nov 2025) with ``google-genai``.
  - Replaced retired model ``text-embedding-004`` (shut down Jan 2026) with
    ``gemini-embedding-001``.
  - Old API: ``genai.embed_content(model=..., content=..., task_type=...)``
    → returned ``{"embedding": [[...], ...]}``
  - New API: ``client.models.embed_content(model=..., contents=..., config=...)``
    → returns object with ``.embeddings[i].values``
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logger import logger
from app.services.chunking import DocumentChunk


# ---------------------------------------------------------------------------
# Module-level initialisation
# ---------------------------------------------------------------------------
_client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

# Simple in-memory cache: chunk_id → embedding vector
_embedding_cache: Dict[str, List[float]] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _cache_key(chunk: DocumentChunk) -> str:
    """Return a stable cache key for *chunk*.

    Uses the pre-computed ``chunk_id`` from metadata so identical content at
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
    task_type: str = "RETRIEVAL_DOCUMENT",
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> List[List[float]]:
    """Call the Google embedding API with exponential back-off on failure.

    Parameters
    ----------
    texts:
        The texts to embed.
    task_type:
        ``"RETRIEVAL_DOCUMENT"`` for document embeddings,
        ``"RETRIEVAL_QUERY"`` for query embeddings.

    Returns a list of embedding vectors in the same order as *texts*.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            # The google-genai client is synchronous; run it in a thread
            # so we don't block the event loop.
            result = await asyncio.to_thread(
                _client.models.embed_content,
                model=settings.embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embedding_dimension,
                ),
            )
            # New SDK returns: result.embeddings → list of ContentEmbedding
            # Each ContentEmbedding has a .values attribute (list[float]).
            return [emb.values for emb in result.embeddings]
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
# Startup validation
# ---------------------------------------------------------------------------
async def validate_embedding_model() -> None:
    """Validate the configured embedding model on startup.

    Fires one small embedding request.  If the model is unsupported or the
    API is unreachable, raises a descriptive exception so the app fails fast
    instead of silently breaking on the first user query.

    Also logs:
    - Installed SDK version
    - Configured embedding model
    - Whether the API is reachable
    - Returned vector dimension
    """
    sdk_version = getattr(genai, "__version__", "unknown")
    model_name = settings.embedding_model
    expected_dim = settings.embedding_dimension

    logger.info(
        "Embedding startup validation",
        sdk="google-genai",
        sdk_version=sdk_version,
        model=model_name,
        expected_dimension=expected_dim,
    )

    try:
        vectors = await _embed_texts_with_retry(
            ["startup validation test"],
            task_type="RETRIEVAL_DOCUMENT",
            max_retries=2,
            base_delay=0.5,
        )
        actual_dim = len(vectors[0])

        if actual_dim != expected_dim:
            raise RuntimeError(
                f"Embedding dimension mismatch: model '{model_name}' returned "
                f"{actual_dim}-dim vectors but EMBEDDING_DIMENSION is set to "
                f"{expected_dim}. Update EMBEDDING_DIMENSION in your environment "
                f"or set output_dimensionality accordingly."
            )

        logger.info(
            "Embedding API reachable — validation passed",
            model=model_name,
            dimension=actual_dim,
        )

    except RuntimeError:
        # Re-raise dimension mismatch or API failure directly
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Embedding model '{model_name}' is not available or the API is "
            f"unreachable.  Original error: {exc}\n\n"
            f"Possible fixes:\n"
            f"  1. Check that GEMINI_API_KEY is valid.\n"
            f"  2. Change EMBEDDING_MODEL to a supported model "
            f"(e.g. 'gemini-embedding-001').\n"
            f"  3. Verify network connectivity to the Gemini API."
        ) from exc


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
        vectors = await _embed_texts_with_retry(
            texts,
            task_type="RETRIEVAL_DOCUMENT",
        )

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
    """Flush the in-memory embedding cache.  Returns the number of evicted entries."""
    count = len(_embedding_cache)
    _embedding_cache.clear()
    logger.info("Embedding cache cleared", evicted=count)
    return count


async def embed_query(query: str) -> List[float]:
    """Embed a single query string for retrieval.

    Uses ``task_type="RETRIEVAL_QUERY"`` so the resulting vector is in the
    correct subspace relative to document embeddings (which use
    ``RETRIEVAL_DOCUMENT``).

    Parameters
    ----------
    query:
        The user's natural-language search query.

    Returns
    -------
    list[float]
        The embedding vector for *query*.
    """
    result = await _embed_texts_with_retry(
        [query],
        task_type="RETRIEVAL_QUERY",
    )
    # _embed_texts_with_retry returns a list of vectors; take the first.
    vector = result[0]
    logger.debug("Query embedded", query=query[:60], dim=len(vector))
    return vector
