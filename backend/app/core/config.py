# backend/app/core/config.py
"""Application configuration using Pydantic BaseSettings.

Environment variables are loaded from a `.env` file at the project root. The class is split
into logical sub‑sections for easy access throughout the codebase.
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # ---- API settings ----
    api_host: str = Field("0.0.0.0", env="API_HOST")
    api_port: int = Field(8000, env="API_PORT")
    cors_origins: str = Field("http://localhost:3000", env="CORS_ORIGINS")
    # ---- Gemini settings ----
    gemini_api_key: SecretStr = Field(..., env="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-3.5-flash", env="GEMINI_MODEL")
    gemini_temperature: float = Field(0.3, env="GEMINI_TEMPERATURE")
    gemini_max_output_tokens: int = Field(2048, env="GEMINI_MAX_OUTPUT_TOKENS")
    # ---- Chunking settings ----
    chunk_size: int = Field(1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(200, env="CHUNK_OVERLAP")
    # ---- Embedding settings ----
    # Note: text-embedding-004 was retired Jan 2026. Use gemini-embedding-001
    # or check https://ai.google.dev/gemini-api/docs/models#embedding for
    # the current model list.
    embedding_model: str = Field("gemini-embedding-001", env="EMBEDDING_MODEL")
    embedding_batch_size: int = Field(100, env="EMBEDDING_BATCH_SIZE")
    embedding_dimension: int = Field(768, env="EMBEDDING_DIMENSION")
    # ---- Vector store settings ----
    vector_store_path: str = Field("data/vector_store", env="VECTOR_STORE_PATH")
    # ---- Retrieval settings ----
    retrieval_top_k: int = Field(5, env="RETRIEVAL_TOP_K")
    # ---- Logging settings ----
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_json: bool = Field(True, env="LOG_JSON")    

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Export a singleton that can be imported anywhere.
settings = Settings()
