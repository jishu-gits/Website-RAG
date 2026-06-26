# backend/app/api/schemas.py
"""Pydantic request / response models for all API endpoints.

Centralising schemas keeps routers thin and ensures consistent validation
and OpenAPI documentation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


# ═══════════════════════════════════════════════════════════════════════════
# Ingestion
# ═══════════════════════════════════════════════════════════════════════════
class IngestRequest(BaseModel):
    """POST body for /ingest."""

    urls: List[str] = Field(
        ...,
        min_items=1,
        description="One or more seed URLs to crawl and index.",
        example=["https://example.com"],
    )
    max_depth: int = Field(
        2,
        ge=0,
        le=5,
        description="Maximum crawl depth from the seed URLs.",
    )
    chunk_size: Optional[int] = Field(
        None, ge=100, le=10000, description="Override default chunk size."
    )
    chunk_overlap: Optional[int] = Field(
        None, ge=0, le=2000, description="Override default chunk overlap."
    )


class IngestResponse(BaseModel):
    """Response from /ingest."""

    status: str = "completed"
    pages_crawled: int
    chunks_created: int
    chunks_embedded: int
    chunks_indexed: int


# ═══════════════════════════════════════════════════════════════════════════
# Chat / RAG
# ═══════════════════════════════════════════════════════════════════════════
class ChatRequest(BaseModel):
    """POST body for /chat."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's question.",
    )
    top_k: Optional[int] = Field(
        None, ge=1, le=50, description="Number of chunks to retrieve."
    )
    use_mmr: bool = Field(
        False, description="Enable MMR diversity re‑ranking."
    )
    mmr_lambda: float = Field(
        0.5, ge=0.0, le=1.0, description="MMR relevance/diversity trade‑off."
    )
    stream: bool = Field(
        False, description="If true, response is streamed as SSE."
    )
    filters: Optional[Dict[str, Any]] = Field(
        None, description="Metadata filters applied during retrieval."
    )


class CitationOut(BaseModel):
    url: str
    title: str = ""


class ChatResponse(BaseModel):
    """Response from /chat (non‑streaming)."""

    query: str
    answer: str
    citations: List[CitationOut] = []
    has_sufficient_context: bool = True
    chunks_used: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Retrieval diagnostics
# ═══════════════════════════════════════════════════════════════════════════
class RetrieveRequest(BaseModel):
    """POST body for /retrieve (diagnostics)."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: Optional[int] = Field(None, ge=1, le=100)
    use_mmr: bool = False
    mmr_lambda: float = Field(0.5, ge=0.0, le=1.0)
    filters: Optional[Dict[str, Any]] = None


class RetrievalChunkOut(BaseModel):
    text: str
    score: float
    rank: int
    metadata: Dict[str, Any] = {}


class RetrieveResponse(BaseModel):
    query: str
    strategy: str
    top_k: int
    total_results: int
    results: List[RetrievalChunkOut]


# ═══════════════════════════════════════════════════════════════════════════
# Health / System
# ═══════════════════════════════════════════════════════════════════════════
class HealthResponse(BaseModel):
    status: str = "ok"


class SystemStatusResponse(BaseModel):
    status: str = "ok"
    vector_store_size: int
    embedding_cache_size: int
    config: Dict[str, Any] = {}
