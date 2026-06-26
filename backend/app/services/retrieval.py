# backend/app/services/retrieval.py
"""Retrieval pipeline.

Orchestrates the flow from a raw user query to a ranked list of document chunks
ready for LLM prompt construction.  Supports:

- **Similarity search** – standard cosine‑similarity via the FAISS vector store.
- **MMR (Max Marginal Relevance)** – optional re‑ranking that balances
  relevance with diversity, reducing redundancy in retrieved chunks.
- **Metadata filtering** – post‑retrieval filter on any metadata field
  (source_url, document_title, headings, etc.).
- **Configurable top‑k** – controllable via env var or per‑call override.

The public entry point is ``retrieve()``.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from app.core.config import settings
from app.core.logger import logger
from app.services.embeddings import embed_query
from app.services.vector_store import vector_store


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class RetrievalResult:
    """A single ranked chunk returned by the retrieval pipeline."""

    text: str
    score: float
    rank: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResponse:
    """Container for a full retrieval call."""

    query: str
    strategy: str  # "similarity" | "mmr"
    top_k: int
    results: List[RetrievalResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "strategy": self.strategy,
            "top_k": self.top_k,
            "total_results": len(self.results),
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Metadata filtering
# ---------------------------------------------------------------------------
MetadataFilter = Dict[str, Any]


def _apply_filters(
    candidates: List[Dict[str, Any]],
    filters: Optional[MetadataFilter],
) -> List[Dict[str, Any]]:
    """Keep only candidates whose metadata matches every key/value in *filters*.

    Supported value types:
    - **str** – exact match (case‑insensitive).
    - **list[str]** – candidate value must be *in* the list.
    - **callable** – arbitrary predicate ``(value) -> bool``.
    """
    if not filters:
        return candidates

    filtered: List[Dict[str, Any]] = []
    for candidate in candidates:
        match = True
        for key, expected in filters.items():
            actual = candidate.get(key)
            if callable(expected):
                if not expected(actual):
                    match = False
                    break
            elif isinstance(expected, list):
                if actual not in expected:
                    match = False
                    break
            elif isinstance(expected, str):
                if str(actual).lower() != expected.lower():
                    match = False
                    break
            else:
                if actual != expected:
                    match = False
                    break
        if match:
            filtered.append(candidate)

    logger.debug(
        "Metadata filter applied",
        before=len(candidates),
        after=len(filtered),
        filters=str({k: v for k, v in filters.items() if not callable(v)}),
    )
    return filtered


# ---------------------------------------------------------------------------
# MMR re‑ranking
# ---------------------------------------------------------------------------
def _mmr_rerank(
    query_vector: List[float],
    candidates: List[Dict[str, Any]],
    top_k: int,
    lambda_mult: float = 0.5,
) -> List[Dict[str, Any]]:
    """Re‑rank *candidates* using Max Marginal Relevance.

    MMR balances *relevance* (similarity to the query) against *diversity*
    (dissimilarity to already‑selected results).

    ``lambda_mult`` controls the trade‑off:
    - 1.0 → pure relevance (equivalent to standard similarity search).
    - 0.0 → pure diversity.

    Each candidate dict must contain a ``"_vector"`` key holding the raw
    embedding (injected during the wide retrieval pass).
    """
    if not candidates:
        return []

    q = np.array(query_vector, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-10)

    # Pre‑compute normalised candidate vectors
    vecs = np.array(
        [c["_vector"] for c in candidates], dtype=np.float32
    )
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-10
    vecs = vecs / norms

    selected_indices: List[int] = []
    remaining = set(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_idx = -1
        best_score = -float("inf")
        for idx in remaining:
            relevance = float(np.dot(vecs[idx], q))
            if selected_indices:
                sel_vecs = vecs[selected_indices]
                redundancy = float(np.max(sel_vecs @ vecs[idx]))
            else:
                redundancy = 0.0
            mmr_score = lambda_mult * relevance - (1 - lambda_mult) * redundancy
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        if best_idx == -1:
            break
        selected_indices.append(best_idx)
        remaining.discard(best_idx)

    reranked = [candidates[i] for i in selected_indices]
    logger.debug("MMR re‑ranking complete", selected=len(reranked), lambda_mult=lambda_mult)
    return reranked


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def retrieve(
    query: str,
    *,
    top_k: Optional[int] = None,
    filters: Optional[MetadataFilter] = None,
    use_mmr: bool = False,
    mmr_lambda: float = 0.5,
    mmr_fetch_k_multiplier: int = 3,
) -> RetrievalResponse:
    """Retrieve the most relevant chunks for *query*.

    Parameters
    ----------
    query:
        The user's natural‑language question.
    top_k:
        Number of results to return.  Defaults to ``settings.retrieval_top_k``.
    filters:
        Optional metadata filter dict.  See ``_apply_filters`` for syntax.
    use_mmr:
        If ``True``, apply MMR re‑ranking for diversity.
    mmr_lambda:
        Trade‑off parameter for MMR (0–1).
    mmr_fetch_k_multiplier:
        When using MMR, fetch ``top_k * multiplier`` candidates from FAISS
        before re‑ranking down to *top_k*.

    Returns
    -------
    RetrievalResponse
        Ranked results ready for prompt construction.
    """
    k = top_k or settings.retrieval_top_k
    strategy = "mmr" if use_mmr else "similarity"

    logger.info("Retrieval started", query=query[:80], strategy=strategy, top_k=k)

    # 1. Embed the query
    query_vector = await embed_query(query)

    # 2. Wide retrieval from FAISS
    fetch_k = k * mmr_fetch_k_multiplier if use_mmr else k
    raw_results = vector_store.search(query_vector, top_k=fetch_k)

    # 3. Metadata filtering
    if filters:
        raw_results = _apply_filters(raw_results, filters)

    # 4. MMR re‑ranking (if requested)
    if use_mmr and raw_results:
        # Reconstruct vectors for MMR computation
        for result in raw_results:
            row = vector_store._id_to_row.get(result.get("chunk_id", ""))
            if row is not None:
                result["_vector"] = vector_store._index.reconstruct(int(row)).tolist()
            else:
                # Fallback: zero vector (won't rank well, which is fine)
                result["_vector"] = [0.0] * vector_store.dimension

        raw_results = _mmr_rerank(query_vector, raw_results, top_k=k, lambda_mult=mmr_lambda)

        # Clean up internal vector key
        for r in raw_results:
            r.pop("_vector", None)
    else:
        # Trim to top_k
        raw_results = raw_results[:k]

    # 5. Build response
    ranked: List[RetrievalResult] = []
    for rank, entry in enumerate(raw_results, start=1):
        text = entry.pop("text", "")
        score = entry.pop("score", 0.0)
        ranked.append(
            RetrievalResult(text=text, score=score, rank=rank, metadata=entry)
        )

    response = RetrievalResponse(
        query=query,
        strategy=strategy,
        top_k=k,
        results=ranked,
    )

    logger.info(
        "Retrieval complete",
        strategy=strategy,
        returned=len(ranked),
        top_k=k,
    )
    return response


def format_context_for_prompt(
    results: List[RetrievalResult],
    *,
    include_metadata: bool = True,
    max_tokens_estimate: int = 6000,
) -> str:
    """Format retrieval results into a single context string suitable for
    inclusion in an LLM prompt.

    Parameters
    ----------
    results:
        Ranked ``RetrievalResult`` objects from ``retrieve()``.
    include_metadata:
        If ``True``, prepend source URL and title above each chunk.
    max_tokens_estimate:
        Rough character budget (1 token ≈ 4 chars).  Chunks are included in
        rank order until the budget is exhausted.

    Returns
    -------
    str
        Formatted context block.
    """
    parts: List[str] = []
    char_budget = max_tokens_estimate * 4
    used = 0

    for result in results:
        block_lines: List[str] = []
        if include_metadata:
            source = result.metadata.get("source_url", "unknown")
            title = result.metadata.get("document_title", "")
            block_lines.append(f"[Source: {source}]")
            if title:
                block_lines.append(f"[Title: {title}]")
        block_lines.append(result.text)
        block = "\n".join(block_lines)

        if used + len(block) > char_budget:
            break
        parts.append(block)
        used += len(block)

    context = "\n\n---\n\n".join(parts)
    logger.debug("Prompt context built", chunks_used=len(parts), chars=used)
    return context
