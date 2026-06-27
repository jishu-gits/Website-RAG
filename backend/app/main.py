# backend/app/main.py
"""FastAPI application entry point.

Creates the app with:
- CORS middleware (configurable origins)
- Request / response logging middleware
- All API routers registered under ``/api``
- Rich OpenAPI metadata
- Startup / shutdown lifecycle hooks
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, health, ingest, retrieve
from app.core.config import settings
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run setup on startup and teardown on shutdown."""
    logger.info(
        "Application starting",
        host=settings.api_host,
        port=settings.api_port,
    )

    # Validate embedding model on startup — fail fast if the configured
    # model is retired, unsupported, or the API is unreachable.
    from app.services.embeddings import validate_embedding_model

    await validate_embedding_model()

    yield
    # Persist vector store on graceful shutdown
    from app.services.vector_store import vector_store

    vector_store.save()
    logger.info("Application shut down – vector store saved")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(
        title="Website RAG Assistant API",
        description=(
            "A Retrieval‑Augmented Generation assistant that crawls websites, "
            "indexes their content in a FAISS vector store, and answers "
            "questions using Google Gemini – with source citations."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    # Parse comma-separated origins from settings or default to localhost
    cors_origins = [
        origin.strip() 
        for origin in settings.cors_origins.split(",") 
        if origin.strip()
    ] if hasattr(settings, "cors_origins") and settings.cors_origins else ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Security Headers Middleware ───────────────────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # ── Request logging middleware ────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "Unhandled exception",
                request_id=request_id,
                error=str(exc),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Request completed",
            request_id=request_id,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(health.router,    prefix="/api")
    app.include_router(ingest.router,    prefix="/api")
    app.include_router(chat.router,      prefix="/api")
    app.include_router(retrieve.router,  prefix="/api")

    return app


# Instantiate for uvicorn: ``uvicorn app.main:app``
app = create_app()
