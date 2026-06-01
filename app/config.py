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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    model_base_url: str | None = os.getenv("CUSTOM_MODEL_BASE_URL", None)
    model_provider: str = os.getenv("MODEL_PROVIDER", "openai")

    # RAG rules + vector store configuration.
    rules_path: str = os.getenv("RULES_PATH", "agent/rules/rental_rules.md")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "rental_rules")
    rag_recreate: bool = _to_bool(os.getenv("RAG_RECREATE"), default=False)
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))
    rag_dense_k: int = int(os.getenv("RAG_DENSE_K", "6"))
    rag_bm25_k: int = int(os.getenv("RAG_BM25_K", "6"))
    rag_rerank_candidates: int = int(os.getenv("RAG_RERANK_CANDIDATES", "6"))

    # Embedding model configuration.
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    embedding_normalize: bool = _to_bool(os.getenv("EMBEDDING_NORMALIZE"), default=True)

    # Optional reranker configuration. Disabled by default for CPU-only deployments.
    enable_reranker: bool = _to_bool(os.getenv("ENABLE_RERANKER"), default=False)
    reranker_model: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    reranker_use_fp16: bool = _to_bool(os.getenv("RERANKER_USE_FP16"), default=False)
    reranker_passage_chars: int = int(os.getenv("RERANKER_PASSAGE_CHARS", "800"))

    # System prompt configuration.
    SYSTEM_PROMPT: str = (
        "- You are a clothing rental assistant and should only answer related questions. "
        "Other questions may be ignored.\n"
        "- When users ask explanatory questions about processes / rules / deposits / "
        "cleaning / sizing, prioritize calling rag_rules_tool.\n"
        "- If a previous attempt failed due to the RAG tool not being initialized, you must "
        "try to call the tool when the customer ask again.\n"
        "- When users create / update / cancel / query orders, you must call the "
        "corresponding order-related tools.\n"
        "- If required fields are missing (such as order number, date, SKU, etc.), ask "
        "follow-up questions to collect the missing information first."
    )


settings = Settings()
