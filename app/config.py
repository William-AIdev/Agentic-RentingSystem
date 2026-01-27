from __future__ import annotations

import os
from dataclasses import dataclass

def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    # App runtime configuration (environment variables are read directly).
    app_title: str = os.getenv("APP_TITLE", "Rental Agent")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "7860"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    # Default timezone used to interpret user-provided local times.
    local_timezone: str = os.getenv("LOCAL_TIMEZONE", "Australia/Sydney")

    # LLM configuration.
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-nano")
    openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0"))

    # RAG rules + vector store configuration.
    rules_path: str = os.getenv("RULES_PATH", "agent/rules/rental_rules.md")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "rental_rules")
    rag_recreate: bool = _to_bool(os.getenv("RAG_RECREATE"), default=False)
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))

    # Embedding model configuration.
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    embedding_normalize: bool = _to_bool(os.getenv("EMBEDDING_NORMALIZE"), default=True)


settings = Settings()
