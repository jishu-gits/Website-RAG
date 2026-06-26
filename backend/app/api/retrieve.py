# backend/app/api/retrieve.py
"""Retrieval diagnostics router.

POST /api/retrieve
    Run a retrieval query without generation.  Useful for debugging relevance,
    inspecting chunk scores, and tuning top‑k / MMR parameters.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.schemas import (
    RetrievalChunkOut,
    RetrieveRequest,
    RetrieveResponse,
)
from app.core.logger import logger
from app.services.retrieval import retrieve

router = APIRouter(prefix="/retrieve", tags=["Retrieval Diagnostics"])


@router.post(
    "",
    response_model=RetrieveResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve chunks (diagnostics)",
    description=(
        "Execute the retrieval pipeline without LLM generation.  Returns "
        "ranked document chunks with similarity scores and full metadata.  "
        "Use this to debug retrieval quality and tune parameters."
    ),
)
async def retrieve_chunks(body: RetrieveRequest) -> RetrieveResponse:
    logger.info("Retrieve diagnostics request", query=body.query[:80])

    result = await retrieve(
        body.query,
        top_k=body.top_k,
        filters=body.filters,
        use_mmr=body.use_mmr,
        mmr_lambda=body.mmr_lambda,
    )

    return RetrieveResponse(
        query=result.query,
        strategy=result.strategy,
        top_k=result.top_k,
        total_results=len(result.results),
        results=[
            RetrievalChunkOut(
                text=r.text,
                score=r.score,
                rank=r.rank,
                metadata=r.metadata,
            )
            for r in result.results
        ],
    )
