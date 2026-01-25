from __future__ import annotations

import logging
from pathlib import Path
import hashlib
from typing import List, Optional

from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.config import settings


logger = logging.getLogger(__name__)


_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


class RulesRAG:
    def __init__(self) -> None:
        self._vectorstore: Optional[QdrantVectorStore] = None
        self._initialized = False
        self._error: Optional[str] = None

    def _read_rules_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _split_rule_text(self, text: str) -> List[str]:
        if not text:
            return []
        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS_TO_SPLIT_ON)
        docs = splitter.split_text(text)
        chunks: list[str] = []
        for doc in docs:
            header_parts = [
                doc.metadata.get("h1"),
                doc.metadata.get("h2"),
                doc.metadata.get("h3"),
                doc.metadata.get("h4"),
            ]
            header = " > ".join([h for h in header_parts if h])
            if header:
                chunks.append(f"{header}\n{doc.page_content}".strip())
            else:
                chunks.append(doc.page_content.strip())
        return [chunk for chunk in chunks if chunk]

    def _init_vectorstore(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        try:
            rules_path = Path(settings.rules_path)
            rules_text = self._read_rules_text(rules_path)
            if not rules_text:
                self._error = "规则文件为空或不存在。"
                return

            # Use content hash to version collections and skip rebuilds when rules are unchanged.
            rules_md5 = hashlib.md5(rules_text.encode("utf-8")).hexdigest()
            base_collection = settings.qdrant_collection
            collection_name = f"{base_collection}_{rules_md5}"

            client = QdrantClient(url=settings.qdrant_url)
            existing = {c.name for c in client.get_collections().collections}

            embeddings = HuggingFaceBgeEmbeddings(
                model_name=settings.embedding_model,
                model_kwargs={"device": settings.embedding_device},
                encode_kwargs={"normalize_embeddings": settings.embedding_normalize},
                query_instruction="",
            )

            # Reuse the existing collection for this rules hash to avoid recomputing vectors.
            if collection_name in existing and not settings.rag_recreate:
                self._vectorstore = QdrantVectorStore(
                    client=client,
                    collection_name=collection_name,
                    embedding=embeddings,
                )
                return

            docs = self._split_rule_text(rules_text)
            if not docs:
                self._error = "规则文件为空或不存在。"
                return

            # Build a fresh collection for the current rules content.
            self._vectorstore = QdrantVectorStore.from_texts(
                texts=docs,
                embedding=embeddings,
                url=settings.qdrant_url,
                collection_name=collection_name,
                force_recreate=True,
            )

            # Remove older rule collections to keep storage tidy.
            for name in existing:
                if name != collection_name and name.startswith(f"{base_collection}_"):
                    client.delete_collection(name)
        except Exception as exc:  # pragma: no cover - defensive
            self._error = str(exc)
            logger.exception("Failed to initialize RAG index")

    def query(self, question: str, k: Optional[int] = None) -> List[str]:
        self._init_vectorstore()
        if self._vectorstore is None:
            return []
        top_k = k if k is not None else settings.rag_top_k
        results = self._vectorstore.similarity_search(question, k=top_k)
        return [r.page_content for r in results]

    @property
    def error(self) -> Optional[str]:
        self._init_vectorstore()
        return self._error


rules_rag = RulesRAG()
