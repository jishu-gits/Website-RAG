# backend/app/core/container.py
"""Dependency Injection container.

Using `dependency_injector`, we expose singletons for configuration,
logger, and later service classes (e.g., Gemini client, vector store).
"""

from dependency_injector import containers, providers
from .config import settings
from .logger import logger

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(packages=["app.api", "app.services"])

    config = providers.Singleton(lambda: settings)
    logger = providers.Object(logger)
    # Future providers, e.g., Gemini client, can be added here.
