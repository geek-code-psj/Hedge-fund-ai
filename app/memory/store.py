"""
app/memory/store.py
Vector memory using ChromaDB + fastembed (no PyTorch — ~50MB vs ~800MB).
fastembed uses ONNX Runtime under the hood — fast, CPU-only, production-safe.

ONNX models are cached in ~/.cache/huggingface/hub/ on first download.
Subsequent requests use cached model (no 79MB re-download).
"""
from __future__ import annotations

import json
from datetime import datetime
import os

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.models import InvestmentThesis

logger = get_logger(__name__)
settings = get_settings()

# Cache ONNX models in shared location
os.environ.setdefault("HF_HOME", "/tmp/huggingface")  # Railway: use /tmp (persistent across boots)

_MEMORY_COLLECTION    = "analysis_memory"
_FEEDBACK_COLLECTION  = "feedback_bank"
_TOP_K                = 3

_client: chromadb.Client | None = None
_embed_fn = None


def _get_client() -> chromadb.Client:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path="./chroma_memory")
        logger.info("chroma_client_initialised")
    return _client


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        # fastembed: no PyTorch, ONNX Runtime, ~50MB download on first use
        _embed_fn = DefaultEmbeddingFunction()
    return _embed_fn


def _get_collection(name: str) -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=name,
        embedding_function=_get_embed_fn(),
        metadata={"hnsw:space": "cosine"},
    )


async def store_analysis_memory(ticker: str, query: str, thesis: InvestmentThesis) -> None:
    try:
        col = _get_collection(_MEMORY_COLLECTION)
        doc_id = f"{ticker}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        document = (
            f"Ticker: {ticker}\nQuery: {query}\n"
            f"Recommendation: {thesis.recommendation.value}\n"
            f"Conviction: {thesis.conviction_score:.2f}\n"
            f"Target: ${thesis.valuation.target_price_usd:.2f}\n"
            f"Summary: {thesis.executive_summary[:300]}"
        )
        col.upsert(
            ids=[doc_id],
            documents=[document],
            metadatas=[{
                "ticker": ticker,
                "recommendation": thesis.recommendation.value,
                "conviction": str(thesis.conviction_score),
                "date": thesis.analysis_date,
            }],
        )
        logger.info("memory_stored", ticker=ticker, doc_id=doc_id)
    except Exception as exc:
        logger.warning("memory_store_failed", error=str(exc))


async def retrieve_memory_context(ticker: str, query: str) -> str:
    try:
        col = _get_collection(_MEMORY_COLLECTION)
        if col.count() == 0:
            return ""
        results = col.query(
            query_texts=[f"{ticker} {query}"],
            n_results=min(_TOP_K, col.count()),
            where={"ticker": ticker},
        )
        docs = results.get("documents", [[]])[0]
        if not docs:
            results = col.query(query_texts=[query], n_results=min(2, col.count()))
            docs = results.get("documents", [[]])[0]
        if not docs:
            return ""
        return "\n\n".join(f"Prior analysis #{i+1}:\n{doc}" for i, doc in enumerate(docs))
    except Exception as exc:
        logger.warning("memory_retrieve_failed", error=str(exc))
        return ""


async def store_feedback_memory(
    session_id: str, ticker: str, original_output: str, correction: str, score: int
) -> None:
    try:
        col = _get_collection(_FEEDBACK_COLLECTION)
        document = (
            f"Ticker: {ticker}\n"
            f"Original output: {original_output[:300]}\n"
            f"User correction: {correction}\nScore: {score}/5"
        )
        col.upsert(
            ids=[session_id],
            documents=[document],
            metadatas={"ticker": ticker, "score": str(score), "is_correction": str(score <= 2), "session_id": session_id},
        )
        logger.info("feedback_memory_stored", session_id=session_id, score=score)
    except Exception as exc:
        logger.warning("feedback_memory_store_failed", error=str(exc))


async def get_relevant_corrections(ticker: str, query: str) -> str:
    try:
        col = _get_collection(_FEEDBACK_COLLECTION)
        if col.count() == 0:
            return ""
        results = col.query(
            query_texts=[f"{ticker} {query}"],
            n_results=min(2, col.count()),
            where={"is_correction": "True"},
        )
        docs = results.get("documents", [[]])[0]
        if not docs:
            return ""
        return "KNOWN CORRECTION PATTERNS:\n" + "\n---\n".join(docs)
    except Exception:
        return ""
