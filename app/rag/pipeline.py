"""
app/rag/pipeline.py
RAG pipeline — ChromaDB with DefaultEmbeddingFunction (built-in ONNX, no external deps).
"""
from __future__ import annotations

import hashlib
from typing import Any

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_CHUNK_SIZE    = 512
_CHUNK_OVERLAP = 64
_TOP_K         = 4

_embed_fn       = None
_vector_stores: dict[str, chromadb.Collection] = {}
_chroma_client: chromadb.Client | None = None


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        # DefaultEmbeddingFunction ships with chromadb itself — no extra install
        _embed_fn = DefaultEmbeddingFunction()
    return _embed_fn


def _get_client() -> chromadb.Client:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path="./chroma_memory")
    return _chroma_client


def _get_store(ticker: str) -> chromadb.Collection:
    if ticker not in _vector_stores:
        _vector_stores[ticker] = _get_client().get_or_create_collection(
            name=f"filings_{ticker.lower().replace('.', '_')}",
            embedding_function=_get_embed_fn(),
        )
    return _vector_stores[ticker]


def ingest_filing(ticker: str, text: str, metadata: dict[str, Any] | None = None) -> int:
    if not text or len(text.strip()) < 50:
        return 0
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
    )
    chunks = splitter.split_text(text)
    if not chunks:
        return 0
    store = _get_store(ticker)
    meta  = metadata or {}
    ids   = [hashlib.md5(c.encode()).hexdigest() for c in chunks]
    metas = [{**meta, "chunk_idx": i, "ticker": ticker} for i, _ in enumerate(chunks)]
    try:
        store.add(documents=chunks, metadatas=metas, ids=ids)
        logger.info("rag_ingest", ticker=ticker, chunks=len(chunks))
        return len(chunks)
    except Exception as exc:
        logger.warning("rag_ingest_failed", error=str(exc))
        return 0


def retrieve(ticker: str, query: str, top_k: int = _TOP_K) -> str:
    try:
        store = _get_store(ticker)
        if store.count() == 0:
            return ""
        results = store.query(query_texts=[query], n_results=min(top_k, store.count()))
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        if not documents:
            return ""
        passages = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas), 1):
            form = meta.get("form_type", "FILING")
            date = meta.get("filed_date", "")
            passages.append(f"[{form} {date} — excerpt {i}]\n{doc}")
        return "\n\n".join(passages)
    except Exception as exc:
        logger.warning("rag_retrieve_failed", ticker=ticker, error=str(exc))
        return ""


def clear_store(ticker: str) -> None:
    if ticker in _vector_stores:
        try:
            _vector_stores[ticker].delete_collection()
            del _vector_stores[ticker]
            logger.info("rag_store_cleared", ticker=ticker)
        except Exception:
            pass
