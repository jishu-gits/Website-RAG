# backend/app/api/health.py
"""Health check and system status endpoints.

GET  /api/health  – lightweight liveness probe.
GET  /api/status  – detailed system status (vector store size, cache, config).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.schemas import HealthResponse, SystemStatusResponse
from app.core.config import settings
from app.core.logger import logger
from app.services.embeddings import _embedding_cache
from app.services.vector_store import vector_store

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Returns ``{status: ok}`` if the service is running.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="System status",
    description=(
        "Returns operational metrics: vector store size, embedding cache "
        "entries, and non‑secret configuration values."
    ),
)
async def system_status() -> SystemStatusResponse:
    logger.info("System status requested")
    return SystemStatusResponse(
        status="ok",
        vector_store_size=vector_store.size,
        embedding_cache_size=len(_embedding_cache),
        config={
            "gemini_model": settings.gemini_model,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "embedding_model": settings.embedding_model,
            "embedding_dimension": settings.embedding_dimension,
            "retrieval_top_k": settings.retrieval_top_k,
            "vector_store_path": settings.vector_store_path,
        },
    )
