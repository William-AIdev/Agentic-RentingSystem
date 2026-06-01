from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import Any

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import MarkdownHeaderTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from app.config import settings
from app.retrieval import rrf_fuse, tokenize

logger = logging.getLogger(__name__)


_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


class RulesRAG:
    def __init__(self) -> None:
        self._vectorstore: QdrantVectorStore | None = None
        self._docs: list[str] = []
        self._bm25: Any | None = None
        self._reranker: Any | None = None
        self._reranker_load_attempted = False
        self._initialized = False
        self._error: str | None = None
        self._ready = threading.Event()

    def _read_rules_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _split_rule_text(self, text: str) -> list[str]:
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

    def _init_bm25(self, docs: list[str]) -> None:
        self._docs = docs
        self._bm25 = None
        if not docs:
            return
        try:
            from rank_bm25 import BM25Okapi

            self._bm25 = BM25Okapi([tokenize(doc) for doc in docs])
        except ImportError:
            logger.warning("rank-bm25 is not installed; BM25 retrieval is disabled.")

    def _load_reranker(self) -> Any | None:
        if not settings.enable_reranker:
            return None
        if self._reranker_load_attempted:
            return self._reranker
        self._reranker_load_attempted = True
        try:
            from FlagEmbedding import FlagReranker

            self._reranker = FlagReranker(
                settings.reranker_model,
                use_fp16=settings.reranker_use_fp16,
            )
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            logger.warning("Reranker is disabled because it failed to load: %s", exc)
            self._reranker = None
        return self._reranker

    def _bm25_search(self, question: str, k: int) -> list[str]:
        if self._bm25 is None or not self._docs or k <= 0:
            return []
        scores = self._bm25.get_scores(tokenize(question))
        top_indices = sorted(
            range(len(scores)),
            key=lambda index: scores[index],
            reverse=True,
        )[:k]
        return [self._docs[index] for index in top_indices if scores[index] > 0]

    def _rerank(self, question: str, candidates: list[str], limit: int) -> list[str]:
        reranker = self._load_reranker()
        if reranker is None or not candidates:
            return candidates[:limit]
        truncated = [text[: settings.reranker_passage_chars] for text in candidates]
        pairs = [[question, text] for text in truncated]
        try:
            scores = reranker.compute_score(pairs)
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            logger.warning("Reranker scoring failed; returning fused results: %s", exc)
            return candidates[:limit]
        if not isinstance(scores, list):
            scores = [scores]
        ranked = [
            text
            for text, _ in sorted(
                zip(candidates, scores, strict=False),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
        return ranked[:limit]

    def _init_vectorstore(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        try:
            rules_path = Path(settings.rules_path)
            rules_text = self._read_rules_text(rules_path)
            if not rules_text:
                self._error = "规则文件为空或不存在。"
                self._ready.set()
                return
            docs = self._split_rule_text(rules_text)
            if not docs:
                self._error = "规则文件为空或不存在。"
                self._ready.set()
                return
            self._init_bm25(docs)

            # Use content hash to version collections and only switch alias after rebuild completes.
            rules_md5 = hashlib.md5(rules_text.encode("utf-8")).hexdigest()
            base_collection = settings.qdrant_collection
            target_collection = f"{base_collection}_{rules_md5}"

            client = QdrantClient(url=settings.qdrant_url)
            existing = {c.name for c in client.get_collections().collections}
            # Map alias -> collection for atomic cutover after rebuild.
            aliases = {a.alias_name: a.collection_name for a in client.get_aliases().aliases}

            embeddings = HuggingFaceEmbeddings(
                model_name=settings.embedding_model,
                model_kwargs={"device": settings.embedding_device},
                encode_kwargs={"normalize_embeddings": settings.embedding_normalize},
            )

            # Reuse when alias already points to the correct rules hash collection.
            if (
                not settings.rag_recreate
                and aliases.get(base_collection) == target_collection
                and target_collection in existing
            ):
                self._vectorstore = QdrantVectorStore(
                    client=client,
                    collection_name=base_collection,
                    embedding=embeddings,
                )
                self._ready.set()
                return

            # Build the target collection first; switch alias only after success.
            self._vectorstore = QdrantVectorStore.from_texts(
                texts=docs,
                embedding=embeddings,
                url=settings.qdrant_url,
                collection_name=target_collection,
                force_recreate=True,
            )

            # Switch alias only after the new collection is fully built.
            alias_ops: list[
                qdrant_models.CreateAliasOperation | qdrant_models.DeleteAliasOperation
            ] = []
            if base_collection in aliases:
                alias_ops.append(
                    qdrant_models.DeleteAliasOperation(
                        delete_alias=qdrant_models.DeleteAlias(alias_name=base_collection)
                    )
                )
            alias_ops.append(
                qdrant_models.CreateAliasOperation(
                    create_alias=qdrant_models.CreateAlias(
                        collection_name=target_collection,
                        alias_name=base_collection,
                    )
                )
            )
            client.update_collection_aliases(alias_ops)

            # Query through alias to avoid ever touching a half-built collection.
            self._vectorstore = QdrantVectorStore(
                client=client,
                collection_name=base_collection,
                embedding=embeddings,
            )

            # Remove older rule collections to keep storage tidy.
            for name in existing:
                if name != target_collection and name.startswith(f"{base_collection}_"):
                    client.delete_collection(name)
            self._ready.set()
        except Exception as exc:  # pragma: no cover - defensive
            self._error = str(exc)
            logger.exception("Failed to initialize RAG index")
            self._ready.set()

    def query(self, question: str, k: int | None = None) -> list[str]:
        self._init_vectorstore()
        if self._vectorstore is None:
            return []
        top_k = k if k is not None else settings.rag_top_k
        dense_k = max(settings.rag_dense_k, top_k)
        bm25_k = max(settings.rag_bm25_k, top_k)
        candidate_k = max(settings.rag_rerank_candidates, top_k)

        dense_results = self._vectorstore.similarity_search(question, k=dense_k)
        dense_texts = [result.page_content for result in dense_results]
        bm25_texts = self._bm25_search(question, k=bm25_k)
        candidates = rrf_fuse([dense_texts, bm25_texts], limit=candidate_k)
        return self._rerank(question, candidates, limit=top_k)

    @property
    def error(self) -> str | None:
        self._init_vectorstore()
        return self._error

    @property
    def ready(self) -> bool:
        return self._ready.is_set()


rules_rag = RulesRAG()
