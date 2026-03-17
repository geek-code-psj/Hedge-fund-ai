"""
app/graph/nodes.py
LangGraph node implementations.

Each node receives AgentState, performs work, returns a partial state dict.
LangGraph merges returned dicts into the running state automatically.

Node execution order (graph-driven):
  orchestrator_node → [news_node ‖ financial_node ‖ document_node]
                     → aggregator_node → reviewer_node
"""
from __future__ import annotations

import asyncio
import json

import httpx

from app.agents import document_agent, financial_data_agent, news_agent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.memory.store import retrieve_memory_context
from app.orchestrator.reviewer import run_reviewer
from app.schemas.models import (
    AggregatedResearch,
    AgentState,
    DocumentAgentOutput,
    FinancialDataAgentOutput,
    NewsAgentOutput,
    Sentiment,
)

logger = get_logger(__name__)
settings = get_settings()
tracer = get_tracer("graph_nodes")

# Shared connection-pooled HTTP client — created per-graph execution
_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=settings.agent_timeout + 5)
    return _http


# ─── Node 1: Orchestrator ─────────────────────────────────────────────────────

async def orchestrator_node(state: AgentState) -> dict:
    """
    Initialises the run: validates input, injects memory context.
    Acts as the 'planning' step before agents fan out.
    """
    ticker = state["ticker"].strip().upper()
    session_id = state.get("session_id", "")

    with tracer.start_as_current_span("orchestrator_node") as span:
        span.set_attribute("ticker", ticker)
        span.set_attribute("session_id", session_id)

        # Pull relevant memory from vector store
        memory_ctx = await retrieve_memory_context(
            ticker=ticker,
            query=state.get("user_query", ""),
        )

        logger.info(
            "orchestrator_planned",
            ticker=ticker,
            has_memory=bool(memory_ctx),
        )

    return {
        "ticker": ticker,
        "memory_context": memory_ctx,
        "agents_completed": [],
        "agents_failed": [],
        "reviewer_retries": 0,
    }


# ─── Node 2a: News Agent ──────────────────────────────────────────────────────

async def news_node(state: AgentState) -> dict:
    """Fan-out node: fetch news + sentiment via Finnhub."""
    ticker = state["ticker"]

    with tracer.start_as_current_span("news_node") as span:
        span.set_attribute("ticker", ticker)

        try:
            result: NewsAgentOutput = await asyncio.wait_for(
                news_agent.run(ticker, _get_http()),
                timeout=settings.agent_timeout,
            )
            completed = state.get("agents_completed", []) + ["news_agent"]
            failed = state.get("agents_failed", [])
            if result.error:
                failed = failed + ["news_agent"]
                completed = [c for c in completed if c != "news_agent"]

            logger.info("news_node_done", ticker=ticker, error=result.error)
            return {
                "news_output": result.model_dump(),
                "agents_completed": completed,
                "agents_failed": failed,
            }
        except Exception as exc:
            logger.error("news_node_exception", error=str(exc))
            return {
                "news_output": NewsAgentOutput(
                    ticker=ticker, error=str(exc),
                    sentiment=Sentiment.NEUTRAL, sentiment_score=0.0
                ).model_dump(),
                "agents_failed": state.get("agents_failed", []) + ["news_agent"],
            }


# ─── Node 2b: Financial Data Agent ───────────────────────────────────────────

async def financial_node(state: AgentState) -> dict:
    """Fan-out node: fetch price, technicals, financials."""
    ticker = state["ticker"]

    with tracer.start_as_current_span("financial_node") as span:
        span.set_attribute("ticker", ticker)

        try:
            result: FinancialDataAgentOutput = await asyncio.wait_for(
                financial_data_agent.run(ticker, _get_http()),
                timeout=settings.agent_timeout,
            )
            completed = state.get("agents_completed", []) + ["financial_data_agent"]
            failed = state.get("agents_failed", [])
            if result.error:
                failed = failed + ["financial_data_agent"]
                completed = [c for c in completed if c != "financial_data_agent"]

            return {
                "financial_output": result.model_dump(),
                "agents_completed": completed,
                "agents_failed": failed,
            }
        except Exception as exc:
            logger.error("financial_node_exception", error=str(exc))
            return {
                "financial_output": FinancialDataAgentOutput(
                    ticker=ticker, error=str(exc)
                ).model_dump(),
                "agents_failed": state.get("agents_failed", []) + ["financial_data_agent"],
            }


# ─── Node 2c: Document Agent ──────────────────────────────────────────────────

async def document_node(state: AgentState) -> dict:
    """Fan-out node: SEC EDGAR filings + RAG retrieval."""
    ticker = state["ticker"]

    with tracer.start_as_current_span("document_node") as span:
        span.set_attribute("ticker", ticker)

        try:
            result: DocumentAgentOutput = await asyncio.wait_for(
                document_agent.run(ticker, _get_http()),
                timeout=settings.agent_timeout,
            )
            completed = state.get("agents_completed", []) + ["document_agent"]
            failed = state.get("agents_failed", [])
            if result.error:
                failed = failed + ["document_agent"]
                completed = [c for c in completed if c != "document_agent"]

            return {
                "document_output": result.model_dump(),
                "agents_completed": completed,
                "agents_failed": failed,
            }
        except Exception as exc:
            logger.error("document_node_exception", error=str(exc))
            return {
                "document_output": DocumentAgentOutput(
                    ticker=ticker, error=str(exc)
                ).model_dump(),
                "agents_failed": state.get("agents_failed", []) + ["document_agent"],
            }


# ─── Node 3: Aggregator (fan-in) ──────────────────────────────────────────────

async def aggregator_node(state: AgentState) -> dict:
    """
    Fan-in node: waits for all agents (LangGraph guarantees this via edge topology),
    merges their outputs into a single AggregatedResearch payload.
    """
    ticker = state["ticker"]

    with tracer.start_as_current_span("aggregator_node") as span:
        completed = state.get("agents_completed", [])
        failed = state.get("agents_failed", [])
        span.set_attribute("agents_completed", str(completed))
        span.set_attribute("agents_failed", str(failed))

        # Deserialise agent outputs back into Pydantic models
        news = _safe_parse(NewsAgentOutput, state.get("news_output"), ticker)
        fin = _safe_parse(FinancialDataAgentOutput, state.get("financial_output"), ticker)
        doc = _safe_parse(DocumentAgentOutput, state.get("document_output"), ticker)

        # Attach memory context to aggregated research if available
        memory_note = ""
        if state.get("memory_context"):
            memory_note = f"\n\n=== MEMORY CONTEXT (prior analyses) ===\n{state['memory_context']}"

        research = AggregatedResearch(
            ticker=ticker,
            user_query=state.get("user_query", ""),
            news=news,
            financial_data=fin,
            documents=doc,
            agents_completed=completed,
            agents_failed=failed,
        )

        logger.info(
            "aggregator_merged",
            ticker=ticker,
            completed=len(completed),
            failed=len(failed),
        )

    return {
        "aggregated_research": research.model_dump(),
        "memory_note": memory_note,
    }


# ─── Node 4: Reviewer ────────────────────────────────────────────────────────

async def reviewer_node(state: AgentState) -> dict:
    """
    LLM Reviewer: takes AggregatedResearch → produces InvestmentThesis.
    On Pydantic validation failure, increments retry counter.
    The conditional edge in workflow.py decides whether to retry.
    """
    ticker = state["ticker"]
    retries = state.get("reviewer_retries", 0)

    with tracer.start_as_current_span("reviewer_node") as span:
        span.set_attribute("ticker", ticker)
        span.set_attribute("retry_attempt", retries)

        try:
            research_dict = state.get("aggregated_research", {})
            research = AggregatedResearch(**research_dict)

            # Inject memory context into the research object's user query
            memory_note = state.get("memory_note", "")
            if memory_note:
                research = research.model_copy(
                    update={"user_query": research.user_query + memory_note}
                )

            thesis = await run_reviewer(research)
            logger.info(
                "reviewer_success",
                ticker=ticker,
                recommendation=thesis.recommendation.value,
                conviction=thesis.conviction_score,
            )
            return {"thesis": thesis.model_dump(), "reviewer_retries": retries}

        except Exception as exc:
            logger.warning(
                "reviewer_failed",
                ticker=ticker,
                attempt=retries + 1,
                error=str(exc),
            )
            return {
                "thesis": None,
                "reviewer_retries": retries + 1,
                "error": str(exc),
            }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_parse(model_cls, data: dict | None, ticker: str):
    """Safely re-instantiate a Pydantic model from a dict, with fallback."""
    if not data:
        return None
    try:
        return model_cls(**data)
    except Exception:
        return model_cls(ticker=ticker, error="deserialization_failed")
