# backend/app/services/gemini_client.py
"""Google Gemini client with streaming support.

Wraps the ``google-genai`` SDK to provide both blocking and streaming
generation methods.  The SDK's methods are synchronous, so we run calls
in a thread pool to keep the FastAPI event loop responsive.

SDK migration notes (2026-06):
  - Replaced deprecated ``google-generativeai`` with ``google-genai``.
  - Old API: ``genai.configure()`` + ``genai.GenerativeModel(name)`` +
    ``model.generate_content(prompt, stream=True)``
  - New API: ``genai.Client(api_key=...)`` +
    ``client.models.generate_content(model=..., contents=...)`` +
    ``client.models.generate_content_stream(model=..., contents=...)``
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logger import logger


class GeminiClient:
    """Thin async wrapper around the Google GenAI generation API."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._model_name = model_name or settings.gemini_model
        self._client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
        )
        self._generation_config = types.GenerateContentConfig(
            temperature=settings.gemini_temperature,
            max_output_tokens=settings.gemini_max_output_tokens,
        )
        logger.info("GeminiClient initialised", model=self._model_name)

    # ------------------------------------------------------------------
    # Blocking generation (run in thread)
    # ------------------------------------------------------------------
    async def generate(self, prompt: str) -> str:
        """Generate a complete response for *prompt*.

        Returns the full text once generation is finished.
        """
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=self._model_name,
            contents=prompt,
            config=self._generation_config,
        )
        text = response.text
        logger.debug("Gemini generation complete", chars=len(text))
        return text

    # ------------------------------------------------------------------
    # Streaming generation
    # ------------------------------------------------------------------
    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield text chunks as they arrive from Gemini.

        The SDK's streaming method returns an iterable of partial responses.
        We iterate inside a thread and push chunks through an async queue so
        the caller can ``async for chunk in generate_stream(prompt):``.
        """
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def _stream_worker() -> None:
            try:
                response = self._client.models.generate_content_stream(
                    model=self._model_name,
                    contents=prompt,
                    config=self._generation_config,
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
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, _stream_worker)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

        # Let any thread exception propagate
        await task
