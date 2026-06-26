# backend/app/services/rag_pipeline.py
"""Retrieval‑Augmented Generation (RAG) pipeline.

End‑to‑end flow:
1. Retrieve relevant document chunks via the retrieval service.
2. Build a grounded prompt with context, citations, and instructions.
3. Generate an answer with Google Gemini (blocking or streaming).
4. Parse the answer and attach source citations.
5. Gracefully handle insufficient context.

Public API:
- ``ask()``           – full blocking answer with citations.
- ``ask_stream()``    – streaming answer yielding JSON‑serialisable events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, AsyncIterator, Dict, List, Optional

from app.core.config import settings
from app.core.logger import logger
from app.services.gemini_client import GeminiClient
from app.services.retrieval import (
    MetadataFilter,
    RetrievalResult,
    format_context_for_prompt,
    retrieve,
)


# ---------------------------------------------------------------------------
# Module‑level Gemini client
# ---------------------------------------------------------------------------
_client = GeminiClient()


# ---------------------------------------------------------------------------
# Prompt engineering
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions based ONLY on the provided \
context extracted from web pages.

Rules:
1. Answer the question using ONLY the context below.  Do NOT use outside knowledge.
2. If the context does not contain enough information to answer, respond with:
   "I don't have enough information from the indexed pages to answer this question."
3. Be concise and accurate.
4. At the end of your answer, include a "Sources:" section listing the URLs you \
   used, one per line.  Only cite sources that you actually used.
5. If you quote or closely paraphrase a passage, mention its source inline \
   like [Source: <url>].
"""

_INSUFFICIENT_CONTEXT_MARKER = "I don't have enough information"


def build_prompt(query: str, context: str) -> str:
    """Assemble the full prompt sent to Gemini."""
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"--- CONTEXT START ---\n{context}\n--- CONTEXT END ---\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class Citation:
    """A source citation extracted from the generated answer."""

    url: str
    title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RAGResponse:
    """Full response from the RAG pipeline."""

    query: str
    answer: str
    citations: List[Citation] = field(default_factory=list)
    has_sufficient_context: bool = True
    chunks_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "has_sufficient_context": self.has_sufficient_context,
            "chunks_used": self.chunks_used,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_citations(
    answer: str,
    retrieval_results: List[RetrievalResult],
) -> List[Citation]:
    """Extract citations from the generated answer.

    We build citations from retrieval results whose source URL actually appears
    in the generated text, plus any URLs listed in a trailing "Sources:" block.
    """
    citations: List[Citation] = []
    seen_urls: set[str] = set()

    for result in retrieval_results:
        url = result.metadata.get("source_url", "")
        title = result.metadata.get("document_title", "")
        if url and url in answer and url not in seen_urls:
            citations.append(Citation(url=url, title=title))
            seen_urls.add(url)

    # Also parse a trailing "Sources:" block if present
    lower = answer.lower()
    sources_idx = lower.rfind("sources:")
    if sources_idx != -1:
        sources_block = answer[sources_idx:]
        for result in retrieval_results:
            url = result.metadata.get("source_url", "")
            title = result.metadata.get("document_title", "")
            if url and url in sources_block and url not in seen_urls:
                citations.append(Citation(url=url, title=title))
                seen_urls.add(url)

    return citations


def _check_sufficient_context(answer: str) -> bool:
    """Return ``False`` if the model indicated insufficient context."""
    return _INSUFFICIENT_CONTEXT_MARKER.lower() not in answer.lower()


# ---------------------------------------------------------------------------
# Public API – blocking
# ---------------------------------------------------------------------------
async def ask(
    query: str,
    *,
    top_k: Optional[int] = None,
    filters: Optional[MetadataFilter] = None,
    use_mmr: bool = False,
    mmr_lambda: float = 0.5,
) -> RAGResponse:
    """Ask a question and receive a complete RAG answer with citations.

    Parameters
    ----------
    query:
        The user's natural‑language question.
    top_k:
        Number of chunks to retrieve.
    filters:
        Optional metadata filters for retrieval.
    use_mmr:
        Enable MMR diversity re‑ranking.
    mmr_lambda:
        MMR relevance/diversity trade‑off.

    Returns
    -------
    RAGResponse
        Complete answer with citations and context flags.
    """
    logger.info("RAG pipeline started", query=query[:80])

    # 1. Retrieve
    retrieval_response = await retrieve(
        query, top_k=top_k, filters=filters, use_mmr=use_mmr, mmr_lambda=mmr_lambda,
    )
    results = retrieval_response.results

    # 2. Handle empty retrieval
    if not results:
        logger.warning("No chunks retrieved – returning insufficient context")
        return RAGResponse(
            query=query,
            answer="I don't have enough information from the indexed pages to answer this question.",
            has_sufficient_context=False,
            chunks_used=0,
        )

    # 3. Build prompt
    context = format_context_for_prompt(results)
    prompt = build_prompt(query, context)
    logger.debug("Prompt built", prompt_chars=len(prompt), chunks=len(results))

    # 4. Generate
    answer = await _client.generate(prompt)

    # 5. Post‑process
    citations = _extract_citations(answer, results)
    sufficient = _check_sufficient_context(answer)

    response = RAGResponse(
        query=query,
        answer=answer,
        citations=citations,
        has_sufficient_context=sufficient,
        chunks_used=len(results),
    )

    logger.info(
        "RAG pipeline complete",
        sufficient_context=sufficient,
        citations=len(citations),
        answer_chars=len(answer),
    )
    return response


# ---------------------------------------------------------------------------
# Public API – streaming
# ---------------------------------------------------------------------------
async def ask_stream(
    query: str,
    *,
    top_k: Optional[int] = None,
    filters: Optional[MetadataFilter] = None,
    use_mmr: bool = False,
    mmr_lambda: float = 0.5,
) -> AsyncIterator[str]:
    """Stream a RAG answer as server‑sent events (SSE).

    Yields JSON‑encoded event strings suitable for ``text/event-stream``.
    Event types:
    - ``{"event": "retrieval", "chunks_used": N}``
    - ``{"event": "token",     "content": "..."}``
    - ``{"event": "citations", "citations": [...]}``
    - ``{"event": "done",      "has_sufficient_context": bool}``
    - ``{"event": "error",     "detail": "..."}``
    """
    logger.info("RAG streaming started", query=query[:80])

    # 1. Retrieve
    try:
        retrieval_response = await retrieve(
            query, top_k=top_k, filters=filters, use_mmr=use_mmr, mmr_lambda=mmr_lambda,
        )
        results = retrieval_response.results
    except Exception as exc:
        yield json.dumps({"event": "error", "detail": str(exc)})
        return

    yield json.dumps({"event": "retrieval", "chunks_used": len(results)})

    # 2. Handle empty retrieval
    if not results:
        no_ctx = "I don't have enough information from the indexed pages to answer this question."
        yield json.dumps({"event": "token", "content": no_ctx})
        yield json.dumps({"event": "done", "has_sufficient_context": False})
        return

    # 3. Build prompt
    context = format_context_for_prompt(results)
    prompt = build_prompt(query, context)

    # 4. Stream generation
    full_answer = ""
    try:
        async for chunk in _client.generate_stream(prompt):
            full_answer += chunk
            yield json.dumps({"event": "token", "content": chunk})
    except Exception as exc:
        logger.error("Streaming generation failed", error=str(exc))
        yield json.dumps({"event": "error", "detail": str(exc)})
        return

    # 5. Post‑process (sent as final events)
    citations = _extract_citations(full_answer, results)
    sufficient = _check_sufficient_context(full_answer)

    if citations:
        yield json.dumps({
            "event": "citations",
            "citations": [c.to_dict() for c in citations],
        })

    yield json.dumps({"event": "done", "has_sufficient_context": sufficient})

    logger.info(
        "RAG streaming complete",
        sufficient_context=sufficient,
        citations=len(citations),
        answer_chars=len(full_answer),
    )
