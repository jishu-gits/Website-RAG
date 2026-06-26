# backend/app/core/logger.py
"""Structured logger configuration using structlog.

Provides a configured `logger` instance that can be imported throughout the
application. Logs are emitted in JSON format by default, with a human‑readable
fallback when `LOG_JSON` is false.
"""

import sys
import logging
import structlog
from .config import settings

def configure_logging() -> structlog.BoundLogger:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
    )
    # Decide processors based on JSON flag
    if settings.log_json:
        processors = [
            structlog.processors.JSONRenderer()
        ]
    else:
        processors = [
            structlog.dev.ConsoleRenderer()
        ]
    structlog.configure(
        processors=[structlog.processors.TimeStamper(fmt="iso")]
        + processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()

# Export a module‑level logger for convenience
logger = configure_logging()
