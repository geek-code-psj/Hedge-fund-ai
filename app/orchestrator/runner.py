"""
app/orchestrator/runner.py
SSE streaming wrapper around the LangGraph compiled graph.

Translates LangGraph node events into SSE frames in real-time.
Handles semantic cache check/store around the graph execution.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from uuid import uuid4

from app.cache.semantic_cache import cache_lookup, cache_store
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.feedback import store_session_context
from app.graph.workflow import get_graph
from app.memory.store import store_analysis_memory
from app.orchestrator.reviewer import run_reviewer
from app.schemas.models import (
    AggregatedResearch,
    AgentState,
    InvestmentThesis,
    SSEAgentResultEvent,
    SSEErrorEvent,
    SSEFinalEvent,
    SSEProgressEvent,
)

logger = get_logger(__name__)
settings = get_settings()

# SSE step → progress percentage mapping
_NODE_PCT: dict[str, int] = {
    "orchestrator_node": 10,
    "news_node":         30,
    "financial_node":    45,
    "document_node":     60,
    "aggregator_node":   68,
    "reviewer_node":     85,
}

_NODE_LABEL: dict[str, str] = {
    "orchestrator_node": "Orchestrator planning workflow…",
    "news_node":         "News Agent: fetching Finnhub sentiment…",
    "financial_node":    "Financial Agent: pulling price + indicators…",
    "document_node":     "Document Agent: retrieving SEC filings…",
    "aggregator_node":   "Aggregating research from all agents…",
    "reviewer_node":     "LLM Reviewer synthesising thesis…",
}


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


async def run_analysis_stream(
    ticker: str,
    query: str,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Primary SSE generator consumed by FastAPI StreamingResponse.
    Streams LangGraph node events as SSE progress frames.
    """
    session_id = session_id or str(uuid4())
    t0 = time.monotonic()

    def progress(step: str, message: str, pct: int, agent: str | None = None) -> str:
        return _sse("progress", SSEProgressEvent(
            session_id=session_id,
            step=step,
            agent=agent,
            message=message,
            pct=pct,
        ).model_dump())

    # ── 1. Semantic cache check ───────────────────────────────────────────────
    yield progress("cache_check", "Checking semantic cache…", 5)
    cache_key = f"analysis::{ticker}::{query}"
    cached = await cache_lookup(cache_key)

    if cached:
        yield progress("cache_hit", "⚡ Semantic cache hit — returning cached thesis", 95)
        yield _sse("final", SSEFinalEvent(
            session_id=session_id,
            thesis=InvestmentThesis(**cached["thesis"]),
            cached=True,
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            agents_completed=cached.get("agents_completed", []),
            agents_failed=cached.get("agents_failed", []),
        ).model_dump(mode="json"))
        return

    # ── 2. Execute LangGraph workflow with live node streaming ────────────────
    yield progress("graph_start", "Launching LangGraph multi-agent workflow…", 8)

    graph = get_graph()
    initial_state: AgentState = {
        "ticker": ticker,
        "user_query": query,
        "session_id": session_id,
        "agents_completed": [],
        "agents_failed": [],
    }

    final_state: AgentState = {}
    completed_nodes: list[str] = []

    try:
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            # chunk = {node_name: partial_state_dict}
            for node_name, node_output in chunk.items():
                if node_name == "__end__":
                    continue

                pct = _NODE_PCT.get(node_name, 50)
                label = _NODE_LABEL.get(node_name, f"{node_name} running…")
                completed_nodes.append(node_name)

                # Emit progress for every node transition
                yield progress(node_name, label, pct, agent=node_name)

                # Emit agent-specific result summaries
                if node_name == "news_node" and node_output.get("news_output"):
                    no = node_output["news_output"]
                    yield _sse("agent_result", SSEAgentResultEvent(
                        session_id=session_id,
                        agent="news_agent",
                        success=not bool(no.get("error")),
                        summary=f"{no.get('headline_count',0)} headlines, sentiment={no.get('sentiment','N/A')}",
                        pct=pct,
                    ).model_dump())

                elif node_name == "financial_node" and node_output.get("financial_output"):
                    fo = node_output["financial_output"]
                    price = fo.get("price", {}) or {}
                    close = price.get("close", "N/A")
                    sector = fo.get("sector", "N/A")
                    yield _sse("agent_result", SSEAgentResultEvent(
                        session_id=session_id,
                        agent="financial_data_agent",
                        success=not bool(fo.get("error")),
                        summary=f"Price=${close} | Sector={sector}",
                        pct=pct,
                    ).model_dump())

                elif node_name == "document_node" and node_output.get("document_output"):
                    do = node_output["document_output"]
                    filings = len(do.get("filings", []))
                    risks = len(do.get("key_risks_from_filings", []))
                    yield _sse("agent_result", SSEAgentResultEvent(
                        session_id=session_id,
                        agent="document_agent",
                        success=not bool(do.get("error")),
                        summary=f"{filings} filings | {risks} risk factors",
                        pct=pct,
                    ).model_dump())

                # Stream token-by-token reasoning during reviewer
                elif node_name == "reviewer_node":
                    yield _sse("reasoning", {
                        "session_id": session_id,
                        "content": "Reviewer is synthesising all agent outputs…",
                        "step": "reviewer",
                    })

                # Merge into running final state
                final_state.update(node_output)

    except Exception as exc:
        logger.error("graph_execution_failed", error=str(exc), session_id=session_id)
        yield _sse("error", SSEErrorEvent(
            session_id=session_id,
            message=f"Graph execution failed: {exc}",
            recoverable=False,
        ).model_dump())
        return

    # ── 3. Extract and validate final thesis ──────────────────────────────────
    thesis_dict = final_state.get("thesis")
    if not thesis_dict:
        yield _sse("error", SSEErrorEvent(
            session_id=session_id,
            message="Reviewer did not produce a valid thesis. Please retry.",
            recoverable=True,
        ).model_dump())
        return

    try:
        thesis = InvestmentThesis(**thesis_dict)
    except Exception as exc:
        yield _sse("error", SSEErrorEvent(
            session_id=session_id,
            message=f"Thesis validation failed: {exc}",
            recoverable=True,
        ).model_dump())
        return

    yield progress("finalising", "Storing results and updating memory…", 92)

    # ── 4. Store cache + DB + memory ──────────────────────────────────────────
    agents_completed = final_state.get("agents_completed", [])
    agents_failed = final_state.get("agents_failed", [])

    cache_payload = {
        "thesis": thesis_dict,
        "agents_completed": agents_completed,
        "agents_failed": agents_failed,
    }
    await asyncio.gather(
        cache_store(cache_key, cache_payload),
        store_analysis_memory(ticker=ticker, query=query, thesis=thesis),
        _safe_persist(session_id, ticker, query, final_state, thesis),
        return_exceptions=True,
    )

    # ── 5. Emit final event ───────────────────────────────────────────────────
    latency = round((time.monotonic() - t0) * 1000, 1)
    yield _sse("final", SSEFinalEvent(
        session_id=session_id,
        thesis=thesis,
        cached=False,
        latency_ms=latency,
        agents_completed=agents_completed,
        agents_failed=agents_failed,
    ).model_dump(mode="json"))

    yield progress("done", f"✓ Analysis complete in {latency:.0f}ms", 100)


async def _safe_persist(session_id, ticker, query, state, thesis):
    """Non-fatal DB persistence."""
    try:
        research_dict = state.get("aggregated_research", {})
        if research_dict:
            research = AggregatedResearch(**research_dict)
            await store_session_context(
                session_id=session_id,
                ticker=ticker,
                query=query,
                research=research,
                thesis=thesis,
            )
    except Exception as exc:
        logger.warning("persist_failed", error=str(exc))
