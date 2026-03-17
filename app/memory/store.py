"""
app/memory/store.py
Vector memory system:
  • Stores every completed analysis as an embedding in ChromaDB
  • On new queries, retrieves semantically similar past analyses
  • Injects retrieved context into the orchestrator as "memory"
  • Stores user preferences and feedback for dynamic prompt injection

Free stack:
  • ChromaDB — ephemeral in-process (local) or persistent on disk
  • HuggingFace sentence-transformers — zero API cost embeddings
"""
from __future__ import annotations

import json
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions
from langchain_community.embeddings import HuggingFaceEmbeddings

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.models import InvestmentThesis

logger = get_logger(__name__)
settings = get_settings()

_MEMORY_COLLECTION = "analysis_memory"
_PREFERENCE_COLLECTION = "user_preferences"
_FEEDBACK_COLLECTION = "feedback_bank"
_TOP_K = 3

_client: chromadb.Client | None = None
_embed_fn = None


def _get_client() -> chromadb.Client:
    global _client
    if _client is None:
        # Persistent on-disk storage — survives container restarts
        _client = chromadb.PersistentClient(path="./chroma_memory")
        logger.info("chroma_client_initialised")
    return _client


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
    return _embed_fn


def _get_collection(name: str) -> chromadb.Collection:
    return _get_client().get_or_create_collection(
        name=name,
        embedding_function=_get_embed_fn(),
        metadata={"hnsw:space": "cosine"},
    )


# ─── Write: store completed analysis ─────────────────────────────────────────

async def store_analysis_memory(
    ticker: str,
    query: str,
    thesis: InvestmentThesis,
) -> None:
    """
    Embed and store a completed analysis for future retrieval.
    Document = summary string. Metadata = structured fields for filtering.
    """
    try:
        col = _get_collection(_MEMORY_COLLECTION)
        doc_id = f"{ticker}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        document = (
            f"Ticker: {ticker}\n"
            f"Query: {query}\n"
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
                "target_price": str(thesis.valuation.target_price_usd),
            }],
        )
        logger.info("memory_stored", ticker=ticker, doc_id=doc_id)
    except Exception as exc:
        logger.warning("memory_store_failed", error=str(exc))


# ─── Read: retrieve context for new analysis ─────────────────────────────────

async def retrieve_memory_context(ticker: str, query: str) -> str:
    """
    Return a formatted string of prior analyses relevant to this (ticker, query).
    Injected into the orchestrator node for dynamic context enrichment.
    """
    try:
        col = _get_collection(_MEMORY_COLLECTION)
        count = col.count()
        if count == 0:
            return ""

        results = col.query(
            query_texts=[f"{ticker} {query}"],
            n_results=min(_TOP_K, count),
            where={"ticker": ticker},  # filter to same ticker first
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            # Broaden search to any ticker if same-ticker yields nothing
            results = col.query(
                query_texts=[query],
                n_results=min(2, count),
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]

        if not docs:
            return ""

        lines = [f"Prior analysis #{i+1}:\n{doc}" for i, doc in enumerate(docs)]
        return "\n\n".join(lines)

    except Exception as exc:
        logger.warning("memory_retrieve_failed", error=str(exc))
        return ""


# ─── Feedback bank: store user corrections ───────────────────────────────────

async def store_feedback_memory(
    session_id: str,
    ticker: str,
    original_output: str,
    correction: str,
    score: int,
) -> None:
    """
    Store user feedback/corrections as retrievable memory.
    Low-score feedback (1-2) is tagged as corrections for prompt improvement.
    """
    try:
        col = _get_collection(_FEEDBACK_COLLECTION)
        document = (
            f"Ticker: {ticker}\n"
            f"Original output: {original_output[:300]}\n"
            f"User correction: {correction}\n"
            f"Score: {score}/5"
        )
        col.upsert(
            ids=[session_id],
            documents=[document],
            metadatas={
                "ticker": ticker,
                "score": str(score),
                "is_correction": str(score <= 2),
                "session_id": session_id,
            },
        )
        logger.info("feedback_memory_stored", session_id=session_id, score=score)
    except Exception as exc:
        logger.warning("feedback_memory_store_failed", error=str(exc))


# ─── Preference retrieval: inject user preferences into prompts ───────────────

async def get_relevant_corrections(ticker: str, query: str) -> str:
    """
    Retrieve past corrections for this ticker to inject into the reviewer prompt.
    Implements the 'prompt improvement loop'.
    """
    try:
        col = _get_collection(_FEEDBACK_COLLECTION)
        count = col.count()
        if count == 0:
            return ""

        results = col.query(
            query_texts=[f"{ticker} {query}"],
            n_results=min(2, count),
            where={"is_correction": "True"},
        )
        docs = results.get("documents", [[]])[0]
        if not docs:
            return ""

        return "KNOWN CORRECTION PATTERNS:\n" + "\n---\n".join(docs)
    except Exception:
        return ""
