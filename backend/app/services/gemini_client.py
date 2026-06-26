# backend/app/services/gemini_client.py
"""Google Gemini client with streaming support.

Wraps the ``google-generativeai`` SDK to provide both blocking and streaming
generation methods.  The SDK is synchronous so we run calls in a thread pool
to keep the FastAPI event loop responsive.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from app.core.config import settings
from app.core.logger import logger


# Module‑level SDK init (idempotent)
genai.configure(api_key=settings.gemini_api_key.get_secret_value())


class GeminiClient:
    """Thin async wrapper around a Gemini ``GenerativeModel``."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        name = model_name or settings.gemini_model
        self._model = genai.GenerativeModel(name)
        self._generation_config = GenerationConfig(
            temperature=settings.gemini_temperature,
            max_output_tokens=settings.gemini_max_output_tokens,
        )
        logger.info("GeminiClient initialised", model=name)

    # ------------------------------------------------------------------
    # Blocking generation (run in thread)
    # ------------------------------------------------------------------
    async def generate(self, prompt: str) -> str:
        """Generate a complete response for *prompt*.

        Returns the full text once generation is finished.
        """
        response = await asyncio.to_thread(
            self._model.generate_content,
            prompt,
            generation_config=self._generation_config,
        )
        text = response.text
        logger.debug("Gemini generation complete", chars=len(text))
        return text

    # ------------------------------------------------------------------
    # Streaming generation
    # ------------------------------------------------------------------
    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield text chunks as they arrive from Gemini.

        The SDK's ``stream=True`` returns an iterable of partial responses.
        We iterate inside a thread and push chunks through an async queue so
        the caller can ``async for chunk in generate_stream(prompt):``.
        """
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def _stream_worker() -> None:
            try:
                response = self._model.generate_content(
                    prompt,
                    generation_config=self._generation_config,
                    stream=True,
                )
                for chunk in response:
                    if chunk.text:
                        queue.put_nowait(chunk.text)
            except Exception as exc:
                logger.error("Streaming generation error", error=str(exc))
                queue.put_nowait(None)  # signal completion on error too
                raise
            finally:
                queue.put_nowait(None)  # sentinel: generation done

        # Start streaming in a background thread
        task = asyncio.get_event_loop().run_in_executor(None, _stream_worker)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

        # Let any thread exception propagate
        await task
