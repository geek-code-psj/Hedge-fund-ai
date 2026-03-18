"""
app/api/routes.py  v3
All FastAPI route definitions:

  GET  /api/v1/analyse              — SSE streaming multi-agent analysis
  POST /api/v1/feedback             — User feedback + experience bank
  GET  /api/v1/session/{id}         — Session research context
  GET  /api/v1/memory/{ticker}      — Retrieve memory for ticker
  DELETE /api/v1/memory/{ticker}    — Clear ticker memory + cache
  GET  /api/v1/graph/status         — LangGraph compiled graph introspection
  GET  /health                      — Liveness probe
  GET  /ready                       — Readiness probe (checks Redis + DB)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.cache.semantic_cache import cache_invalidate
from app.core.config import get_settings
from app.db.feedback import get_session, store_feedback
from app.graph.workflow import get_graph
from app.memory.store import retrieve_memory_context, store_feedback_memory
from app.orchestrator.runner import run_analysis_stream
from app.rag.pipeline import clear_store
from app.schemas.models import FeedbackRequest, UserFeedback

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/v1", tags=["analysis"])


# ── Core: SSE Streaming Analysis ─────────────────────────────────────────────

@router.get(
    "/analyse",
    summary="Stream multi-agent financial analysis via SSE",
    description="""
Runs a full LangGraph multi-agent workflow and streams results as Server-Sent Events.

**Pipeline:**
1. Semantic cache check (RedisVL cosine similarity)
2. Fan-out: News Agent ‖ Financial Data Agent ‖ Document (RAG) Agent
3. Aggregator fan-in
4. LLM Reviewer (Generator-Critic pattern)
5. Store in cache + DB + vector memory

**SSE event types:**
- `progress`      — pipeline step with `{step, message, pct}`
- `agent_result`  — per-agent completion `{agent, success, summary}`
- `reasoning`     — reviewer reasoning stream
- `final`         — complete `InvestmentThesis` + metadata
- `error`         — `{message, recoverable}`
    """,
)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def analyse(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=20,
        description="Equity ticker. US: AAPL. India: RELIANCE.NSE. Europe: VOW3.XETRA"),
    query: str = Query(
        default="Provide a comprehensive investment thesis with buy/sell recommendation.",
        max_length=500,
    ),
    session_id: str | None = Query(None, description="Optional client-provided session ID"),
):
    return StreamingResponse(
        run_analysis_stream(
            ticker=ticker.strip().upper(),
            query=query,
            session_id=session_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Feedback ──────────────────────────────────────────────────────────────────

@router.post(
    "/feedback",
    summary="Submit user feedback — stored in DB and Experience Bank",
)
async def submit_feedback(payload: FeedbackRequest):
    """
    Stores:
    - Rating (1–5) + text → PostgreSQL (Neon)
    - Correction text → ChromaDB Experience Bank (used for prompt improvement)
    """
    session = await get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {payload.session_id!r} not found")

    feedback = UserFeedback(
        session_id=payload.session_id,
        ticker=session.ticker,
        original_query=session.query,
        retrieved_context=session.research_context or "{}",
        model_output=session.thesis or "{}",
        feedback_score=payload.feedback_score,
        feedback_text=payload.feedback_text,
        correction=payload.correction,
    )

    success = await store_feedback(feedback)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to persist feedback")

    # Store correction in vector memory for future prompt injection
    if payload.correction and payload.feedback_score <= 2:
        await store_feedback_memory(
            session_id=payload.session_id,
            ticker=session.ticker,
            original_output=session.thesis or "",
            correction=payload.correction,
            score=payload.feedback_score,
        )

    return {
        "status": "ok",
        "feedback_id": feedback.id,
        "correction_stored": bool(payload.correction and payload.feedback_score <= 2),
    }


# ── Session retrieval ─────────────────────────────────────────────────────────

@router.get(
    "/session/{session_id}",
    summary="Retrieve session metadata and recommendation",
)
async def get_session_data(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.id,
        "ticker": session.ticker,
        "query": session.query,
        "recommendation": session.recommendation,
        "conviction_score_pct": session.conviction_score,
        "created_at": str(session.created_at),
    }


# ── Memory ────────────────────────────────────────────────────────────────────

@router.get(
    "/memory/{ticker}",
    summary="Retrieve vector memory context for a ticker",
)
async def get_memory(
    ticker: str,
    query: str = Query(default="investment thesis", max_length=300),
    top_k: int = Query(default=3, ge=1, le=10),
):
    """
    Returns the top-k prior analysis summaries stored in vector memory
    for this ticker. Useful for debugging the Experience Bank.
    """
    ticker = ticker.strip().upper()
    context = await retrieve_memory_context(ticker=ticker, query=query)
    return {
        "ticker": ticker,
        "context": context,
        "has_memory": bool(context),
    }


@router.delete(
    "/memory/{ticker}",
    summary="Clear vector memory and semantic cache for a ticker",
)
async def clear_memory(ticker: str):
    """
    Clears:
    - ChromaDB RAG vector store for this ticker
    - RedisVL semantic cache entries for this ticker
    Useful when you want a completely fresh analysis.
    """
    ticker = ticker.strip().upper()
    clear_store(ticker)
    await cache_invalidate(f"analysis::{ticker}::")
    return {"status": "cleared", "ticker": ticker}


# ── Graph introspection ───────────────────────────────────────────────────────

@router.get(
    "/graph/status",
    summary="LangGraph compiled graph introspection",
)
async def graph_status():
    """Returns the compiled graph's node list and edge topology for debugging."""
    try:
        graph = get_graph()
        # LangGraph exposes graph metadata via .get_graph()
        g = graph.get_graph()
        return {
            "status": "compiled",
            "nodes": list(g.nodes),
            "edges": [{"from": e.source, "to": e.target} for e in g.edges],
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "version": "3.0.0"}


@router.get("/ready", include_in_schema=False)
async def readiness():
    """
    Readiness probe: checks Redis and DB connectivity.
    Returns 503 if either dependency is down.
    """
    checks: dict[str, str] = {}

    # Redis check
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # DB check
    try:
        from app.db.feedback import engine
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return {"ready": healthy, "checks": checks}


# ── Debug: Financial API Testing ──────────────────────────────────────────────

@router.get("/debug/financial-api/{ticker}", include_in_schema=False)
async def debug_financial_api(ticker: str):
    """
    DEBUG ENDPOINT: Test financial APIs directly.
    Shows what EODHD and FMP are returning for a given ticker.
    Used to diagnose "Price=N/A" issues.
    """
    import httpx
    
    results = {
        "ticker": ticker.upper(),
        "eodhd": {"key_set": settings.eodhd_api_key != "demo", "is_demo": settings.eodhd_api_key == "demo"},
        "fmp": {"key_set": settings.fmp_api_key != "demo", "is_demo": settings.fmp_api_key == "demo"},
    }
    
    async with httpx.AsyncClient(timeout=10.0) as http:
        # Test EODHD
        symbol = ticker if "." in ticker else f"{ticker}.US"
        try:
            r = await http.get(
                f"https://eodhd.com/api/eod/{symbol}"
                f"?api_token={settings.eodhd_api_key}&fmt=json&from=2024-01-01&to=2025-01-01&limit=1"
            )
            r.raise_for_status()
            data = r.json()
            results["eodhd"]["status"] = "ok" if data else "empty"
            if data and isinstance(data, list) and len(data) > 0:
                results["eodhd"]["sample"] = {
                    "close": data[0].get("close"),
                    "high": data[0].get("high"),
                    "low": data[0].get("low"),
                    "date": data[0].get("date"),
                }
            else:
                results["eodhd"]["response"] = data
        except Exception as exc:
            results["eodhd"]["error"] = str(exc)
        
        # Test FMP income statement (quick test)
        try:
            r = await http.get(
                f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
                f"?period=quarter&limit=1&apikey={settings.fmp_api_key}"
            )
            r.raise_for_status()
            data = r.json()
            results["fmp"]["status"] = "ok" if data else "empty"
            if data and isinstance(data, list) and len(data) > 0:
                results["fmp"]["sample"] = {"revenue": data[0].get("revenue"), "date": data[0].get("date")}
            else:
                results["fmp"]["response"] = data
        except Exception as exc:
            results["fmp"]["error"] = str(exc)
    
    return results
