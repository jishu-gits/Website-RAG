# backend/app/services/chunking.py
"""Intelligent text chunking pipeline.

Uses LangChain's ``RecursiveCharacterTextSplitter`` to split ingested documents
into semantically meaningful chunks while preserving metadata (source URL,
document title, chunk index, heading context).

Chunk size and overlap are configurable via ``Settings`` and can also be
overridden per‑call.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class ChunkMetadata:
    """Metadata attached to every chunk for downstream retrieval."""

    source_url: str
    document_title: str
    chunk_index: int
    total_chunks: int
    chunk_id: str  # deterministic hash for dedup / lookup
    headings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentChunk:
    """A single chunk ready for embedding."""

    text: str
    metadata: ChunkMetadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "metadata": self.metadata.to_dict(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _generate_chunk_id(source_url: str, chunk_index: int) -> str:
    """Create a deterministic, short hash ID for a chunk."""
    raw = f"{source_url}::chunk::{chunk_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _find_nearest_headings(
    full_text: str,
    chunk_text: str,
    headings: List[str],
) -> List[str]:
    """Return the subset of *headings* that appear before the chunk's position
    in *full_text*, giving downstream consumers heading context for the chunk.

    This is a best‑effort heuristic: we locate the chunk inside the full text
    and keep every heading whose first occurrence is before or inside that span.
    """
    if not headings:
        return []

    chunk_start = full_text.find(chunk_text)
    if chunk_start == -1:
        # Fallback – return all headings (chunk may have been slightly altered)
        return headings

    chunk_end = chunk_start + len(chunk_text)
    relevant: List[str] = []
    for heading in headings:
        pos = full_text.find(heading)
        if pos != -1 and pos <= chunk_end:
            relevant.append(heading)
    return relevant


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_splitter(
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> RecursiveCharacterTextSplitter:
    """Instantiate a ``RecursiveCharacterTextSplitter`` with the given (or
    default) parameters.

    The separator hierarchy is chosen to respect semantic boundaries:
      1. Double newlines  (paragraph breaks)
      2. Single newlines  (line breaks)
      3. Sentences        (". ")
      4. Spaces           (word boundaries)
      5. Empty string     (character‑level fallback)
    """
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap

    return RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )


def chunk_document(
    doc: Dict[str, Any],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[DocumentChunk]:
    """Split a single ingested document into ``DocumentChunk`` objects.

    Parameters
    ----------
    doc:
        A document dict as produced by the ingestion pipeline.  Expected keys:
        ``text``, ``url``, ``title``, ``headings``.
    chunk_size:
        Override the default chunk size from ``Settings``.
    chunk_overlap:
        Override the default chunk overlap from ``Settings``.

    Returns
    -------
    list[DocumentChunk]
        Ordered list of chunks with full metadata.
    """
    text: str = doc.get("text", "")
    url: str = doc.get("url", "")
    title: str = doc.get("title", "")
    headings: List[str] = doc.get("headings", [])

    if not text.strip():
        logger.warning("Empty document – nothing to chunk", url=url)
        return []

    splitter = build_splitter(chunk_size, chunk_overlap)
    raw_chunks: List[str] = splitter.split_text(text)
    total = len(raw_chunks)

    chunks: List[DocumentChunk] = []
    for idx, chunk_text in enumerate(raw_chunks):
        meta = ChunkMetadata(
            source_url=url,
            document_title=title,
            chunk_index=idx,
            total_chunks=total,
            chunk_id=_generate_chunk_id(url, idx),
            headings=_find_nearest_headings(text, chunk_text, headings),
        )
        chunks.append(DocumentChunk(text=chunk_text, metadata=meta))

    logger.info(
        "Document chunked",
        url=url,
        total_chunks=total,
        chunk_size=chunk_size or settings.chunk_size,
        chunk_overlap=chunk_overlap or settings.chunk_overlap,
    )
    return chunks


def chunk_documents(
    docs: List[Dict[str, Any]],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[DocumentChunk]:
    """Convenience wrapper: chunk a batch of documents and return a flat list.

    Parameters
    ----------
    docs:
        List of document dicts from the ingestion pipeline.
    chunk_size / chunk_overlap:
        Optional overrides (applied uniformly to all documents).

    Returns
    -------
    list[DocumentChunk]
        Flat, ordered list of all chunks across all documents.
    """
    all_chunks: List[DocumentChunk] = []
    for doc in docs:
        all_chunks.extend(
            chunk_document(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        )
    logger.info(
        "Batch chunking complete",
        documents=len(docs),
        total_chunks=len(all_chunks),
    )
    return all_chunks
