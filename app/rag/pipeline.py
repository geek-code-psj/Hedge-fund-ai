"""
app/rag/pipeline.py  v2
RAG pipeline: chunk → embed → store → retrieve.

Free stack:
  • sentence-transformers all-MiniLM-L6-v2  (local, no API cost)
  • ChromaDB persistent client              (local disk)
"""
from __future__ import annotations

import asyncio
import hashlib

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_chroma_client: chromadb.PersistentClient | None = None
_embed_fn = None


def _client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path="./chroma_rag")
    return _chroma_client


def _embedder():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
    return _embed_fn


async def embed_and_store(collection_name: str, texts: list[str]) -> int:
    if not texts:
        return 0
    loop = asyncio.get_event_loop()

    def _sync():
        col = _client().get_or_create_collection(
            name=collection_name,
            embedding_function=_embedder(),
            metadata={"hnsw:space": "cosine"},
        )
        ids = [hashlib.md5(t.encode()).hexdigest()[:16] for t in texts]
        col.upsert(ids=ids, documents=texts)
        return len(texts)

    count = await loop.run_in_executor(None, _sync)
    logger.info("rag_stored", collection=collection_name, chunks=count)
    return count


async def semantic_search(collection_name: str, query: str, k: int = 4) -> list[str]:
    loop = asyncio.get_event_loop()

    def _sync():
        try:
            col = _client().get_collection(
                name=collection_name, embedding_function=_embedder()
            )
            n = col.count()
            if n == 0:
                return []
            results = col.query(query_texts=[query], n_results=min(k, n))
            return results.get("documents", [[]])[0]
        except Exception as exc:
            logger.warning("rag_search_failed", error=str(exc))
            return []

    passages = await loop.run_in_executor(None, _sync)
    logger.info("rag_retrieved", hits=len(passages))
    return passages


async def delete_collection(collection_name: str) -> None:
    try:
        _client().delete_collection(collection_name)
    except Exception:
        pass
