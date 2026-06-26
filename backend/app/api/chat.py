# backend/app/api/chat.py
"""Chat router – RAG‑powered question answering.

POST /api/chat
    Non‑streaming: returns a complete ``ChatResponse``.
    Streaming (``stream=true``): returns ``text/event-stream`` with SSE events.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse, CitationOut
from app.core.logger import logger
from app.services.rag_pipeline import ask, ask_stream

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question (RAG)",
    description=(
        "Submit a natural‑language question.  The system retrieves relevant "
        "chunks from the vector store, constructs a grounded prompt, and "
        "generates an answer via Google Gemini.  Set ``stream=true`` for "
        "server‑sent events."
    ),
)
async def chat(body: ChatRequest):
    logger.info("Chat request", query=body.query[:80], stream=body.stream)

    if body.stream:
        return StreamingResponse(
            _sse_generator(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non‑streaming path
    rag_response = await ask(
        body.query,
        top_k=body.top_k,
        filters=body.filters,
        use_mmr=body.use_mmr,
        mmr_lambda=body.mmr_lambda,
    )

    return ChatResponse(
        query=rag_response.query,
        answer=rag_response.answer,
        citations=[
            CitationOut(url=c.url, title=c.title) for c in rag_response.citations
        ],
        has_sufficient_context=rag_response.has_sufficient_context,
        chunks_used=rag_response.chunks_used,
    )


async def _sse_generator(body: ChatRequest):
    """Yield SSE‑formatted ``data:`` lines from the streaming RAG pipeline."""
    async for event_json in ask_stream(
        body.query,
        top_k=body.top_k,
        filters=body.filters,
        use_mmr=body.use_mmr,
        mmr_lambda=body.mmr_lambda,
    ):
        yield f"data: {event_json}\n\n"
