# backend/app/api/ingest.py
"""Ingestion router – crawl, chunk, embed, and index websites.

POST /api/ingest
    Accepts a list of seed URLs and runs the full ingestion pipeline:
    crawl → extract → chunk → embed → store in FAISS.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.schemas import IngestRequest, IngestResponse
from app.core.logger import logger
from app.services.chunking import chunk_documents
from app.services.embeddings import embed_chunks
from app.services.ingestion import ingest_urls
from app.services.vector_store import vector_store

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest one or more websites",
    description=(
        "Crawl the supplied seed URLs (up to *max_depth*), extract clean text, "
        "split into chunks, compute embeddings, and store everything in the "
        "FAISS vector index.  Returns a summary of work done."
    ),
)
async def ingest(body: IngestRequest) -> IngestResponse:
    logger.info(
        "Ingest request received",
        urls=body.urls,
        max_depth=body.max_depth,
    )

    # 1. Crawl & extract
    ingestion_result = await ingest_urls(body.urls)
    documents = ingestion_result["documents"]

    # 2. Chunk
    chunks = chunk_documents(
        documents,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
    )

    # 3. Embed
    pairs = await embed_chunks(chunks)

    # 4. Index in FAISS
    added = vector_store.add(pairs)
    vector_store.save()

    response = IngestResponse(
        pages_crawled=len(documents),
        chunks_created=len(chunks),
        chunks_embedded=len(pairs),
        chunks_indexed=added,
    )

    logger.info(
        "Ingest complete",
        pages=response.pages_crawled,
        chunks=response.chunks_created,
        indexed=response.chunks_indexed,
    )
    return response
