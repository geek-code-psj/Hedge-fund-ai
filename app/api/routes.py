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


@router.get("/diagnostics/{ticker}", include_in_schema=False)
async def full_diagnostics(ticker: str):
    """
    TRANSPARENT DIAGNOSTIC - Shows complete truth about ALL APIs
    Access: https://your-app.com/api/v1/diagnostics/AAPL
    
    Shows:
    - What each API is returning (RAW responses)
    - Which APIs working ✅ vs failing ❌
    - Environmental status (keys set, etc)
    - Clear verdict on root cause
    """
    import httpx
    from datetime import date, timedelta
    
    ticker = ticker.upper()
    results = {
        "timestamp": date.today().isoformat(),
        "ticker": ticker,
        "environment": {
            "gemini_key_configured": settings.gemini_api_key and settings.gemini_api_key != "AIza-placeholder",
            "openai_key_configured": settings.openai_api_key and settings.openai_api_key != "sk-placeholder",
            "eodhd_key_configured": settings.eodhd_api_key and settings.eodhd_api_key != "demo",
            "fmp_key_configured": settings.fmp_api_key and settings.fmp_api_key != "demo",
        },
        "apis": {}
    }
    
    async with httpx.AsyncClient(timeout=12.0) as http:
        # ============ EODHD Price (Most Important) ============
        results["apis"]["eodhd_price"] = {"status": "🔍 Testing..."}
        symbol = ticker if "." in ticker else f"{ticker}.US"
        from_date = (date.today() - timedelta(days=365)).isoformat()
        
        try:
            url = f"https://eodhd.com/api/eod/{symbol}?api_token={settings.eodhd_api_key}&fmt=json&from={from_date}&limit=1"
            r = await http.get(url)
            
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    latest = data[-1]
                    results["apis"]["eodhd_price"] = {
                        "status": "✅ SUCCESS",
                        "price": latest.get("close"),
                        "date": latest.get("date"),
                        "high": latest.get("high"),
                        "low": latest.get("low"),
                        "http_code": 200
                    }
                else:
                    results["apis"]["eodhd_price"] = {
                        "status": "❌ EMPTY",
                        "response": data,
                        "http_code": 200
                    }
            else:
                results["apis"]["eodhd_price"] = {
                    "status": f"❌ HTTP {r.status_code}",
                    "error": r.text[:200],
                    "http_code": r.status_code
                }
        except Exception as e:
            results["apis"]["eodhd_price"] = {
                "status": "❌ EXCEPTION",
                "error": str(e)[:150]
            }
        
        # ============ EODHD Fundamentals (Sector) ============
        results["apis"]["eodhd_fundamentals"] = {"status": "🔍 Testing..."}
        try:
            url = f"https://eodhd.com/api/fundamentals/{symbol}?api_token={settings.eodhd_api_key}&fmt=json"
            r = await http.get(url)
            
            if r.status_code == 200:
                raw = r.json()
                sector = raw.get("General", {}).get("Sector") if raw.get("General") else None
                results["apis"]["eodhd_fundamentals"] = {
                    "status": "✅ SUCCESS" if sector else "⚠️ NO SECTOR",
                    "sector": sector,
                    "industry": raw.get("General", {}).get("Industry") if raw.get("General") else None,
                    "market_cap": raw.get("Highlights", {}).get("MarketCapitalization"),
                    "http_code": 200
                }
            else:
                results["apis"]["eodhd_fundamentals"] = {
                    "status": f"❌ HTTP {r.status_code}",
                    "error": r.text[:200],
                    "http_code": r.status_code
                }
        except Exception as e:
            results["apis"]["eodhd_fundamentals"] = {
                "status": "❌ EXCEPTION",
                "error": str(e)[:150]
            }
        
        # ============ FMP Financial Data ============
        results["apis"]["fmp"] = {"status": "🔍 Testing..."}
        try:
            url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?period=quarter&limit=1&apikey={settings.fmp_api_key}"
            r = await http.get(url)
            
            if r.status_code == 200:
                data = r.json()
                results["apis"]["fmp"] = {
                    "status": "✅ SUCCESS" if data else "⚠️ EMPTY",
                    "records": len(data) if isinstance(data, list) else 0,
                    "http_code": 200
                }
            elif r.status_code == 403:
                error_msg = r.json().get("Error Message", "") if "Error Message" in r.text else r.text[:200]
                results["apis"]["fmp"] = {
                    "status": "❌ 403 FORBIDDEN",
                    "reason": error_msg,
                    "http_code": 403,
                    "note": "Legacy API deprecated? Check https://site.financialmodelingprep.com/developer/docs"
                }
            else:
                results["apis"]["fmp"] = {
                    "status": f"❌ HTTP {r.status_code}",
                    "error": r.text[:200],
                    "http_code": r.status_code
                }
        except Exception as e:
            results["apis"]["fmp"] = {
                "status": "❌ EXCEPTION",
                "error": str(e)[:150]
            }
        
        # ============ Finnhub News ============
        results["apis"]["finnhub_news"] = {"status": "🔍 Testing..."}
        if settings.finnhub_api_key and settings.finnhub_api_key != "d_placeholder":
            try:
                url = f"https://finnhub.io/api/v1/news?symbol={ticker}&limit=5&token={settings.finnhub_api_key}"
                r = await http.get(url)
                
                if r.status_code == 200:
                    data = r.json()
                    results["apis"]["finnhub_news"] = {
                        "status": "✅ SUCCESS",
                        "headlines": len(data) if isinstance(data, list) else 0,
                        "http_code": 200
                    }
                else:
                    results["apis"]["finnhub_news"] = {
                        "status": f"❌ HTTP {r.status_code}",
                        "error": r.text[:150],
                        "http_code": r.status_code
                    }
            except Exception as e:
                results["apis"]["finnhub_news"] = {
                    "status": "❌ EXCEPTION",
                    "error": str(e)[:150]
                }
        else:
            results["apis"]["finnhub_news"] = {
                "status": "⏭️ SKIPPED",
                "reason": "No Finnhub API key configured"
            }
    
    # ============ LLM Status (Gemini + OpenAI) ============
    results["llm_status"] = {
        "gemini": "✅ KEY SET" if results["environment"]["gemini_key_configured"] else "❌ NO KEY",
        "openai": "✅ KEY SET" if results["environment"]["openai_key_configured"] else "❌ NO KEY",
        "note": "Keys set but may still be rate-limited or exhausted"
    }
    
    # ============ VERDICT ============
    api_status = results["apis"]
    eodhd_ok = api_status.get("eodhd_price", {}).get("status", "").startswith("✅")
    fmp_ok = api_status.get("fmp", {}).get("status", "").startswith("✅")
    news_ok = api_status.get("finnhub_news", {}).get("status", "").startswith("✅")
    
    if eodhd_ok and fmp_ok and news_ok:
        verdict = "🟢 ALL APIS WORKING - Issue is in LLM layer (Gemini/OpenAI exhausted?)"
    elif eodhd_ok:
        verdict = "🟡 PARTIAL - EODHD works, FMP 403/exhausted. Using EODHD-only mode."
    elif not results["environment"]["gemini_key_configured"] or not results["environment"]["openai_key_configured"]:
        verdict = "🔴 LLM KEYS MISSING - Add to Railway Variables"
    else:
        verdict = "🔴 CRITICAL - Multiple API failures. Check API status pages."
    
    results["verdict"] = verdict
    
    return results


@router.get("/diagnostics/{ticker}", include_in_schema=False)
async def complete_diagnostics(ticker: str):
    """
    🔍 COMPLETE TRANSPARENCY: Shows EVERYTHING the app is doing.
    No hidden failures, no fake data. Real API responses shown.
    Access: /api/v1/diagnostics/{ticker}
    """
    from datetime import date, timedelta
    import httpx
    
    ticker = ticker.upper()
    results = {
        "timestamp": date.today().isoformat(),
        "ticker": ticker,
        "____IMPORTANT": "This shows REAL API calls with REAL responses - no filtering",
        "environment": {
            "gemini_configured": settings.gemini_api_key not in ["AIza-placeholder", "demo"],
            "openai_configured": settings.openai_api_key not in ["sk-placeholder", "demo"],
            "eodhd_configured": settings.eodhd_api_key != "demo",
            "fmp_configured": settings.fmp_api_key != "demo",
        },
        "api_tests": {}
    }
    
    async with httpx.AsyncClient(timeout=10.0) as http:
        # TEST 1: EODHD Price
        results["api_tests"]["1_eodhd_price"] = {}
        symbol = ticker if "." in ticker else f"{ticker}.US"
        try:
            url = f"https://eodhd.com/api/eod/{symbol}?api_token={settings.eodhd_api_key}&fmt=json&from=2025-01-01&limit=1"
            r = await http.get(url, timeout=5.0)
            results["api_tests"]["1_eodhd_price"]["status_code"] = r.status_code
            results["api_tests"]["1_eodhd_price"]["success"] = r.status_code == 200
            if r.status_code == 200:
                data = r.json()
                if data and isinstance(data, list):
                    results["api_tests"]["1_eodhd_price"]["data"] = data[0] if data else None
                    results["api_tests"]["1_eodhd_price"]["result"] = "✅ PRICE DATA WORKING"
                else:
                    results["api_tests"]["1_eodhd_price"]["result"] = "❌ Empty response"
            else:
                results["api_tests"]["1_eodhd_price"]["result"] = f"❌ HTTP {r.status_code}"
                results["api_tests"]["1_eodhd_price"]["response_text"] = r.text[:300]
        except Exception as e:
            results["api_tests"]["1_eodhd_price"]["result"] = f"❌ Exception: {str(e)[:100]}"
        
        # TEST 2: EODHD Fundamentals (Sector)
        results["api_tests"]["2_eodhd_sector"] = {}
        try:
            url = f"https://eodhd.com/api/fundamentals/{symbol}?api_token={settings.eodhd_api_key}&fmt=json"
            r = await http.get(url, timeout=5.0)
            results["api_tests"]["2_eodhd_sector"]["status_code"] = r.status_code
            results["api_tests"]["2_eodhd_sector"]["success"] = r.status_code == 200
            if r.status_code == 200:
                data = r.json()
                sector = data.get("General", {}).get("Sector")
                results["api_tests"]["2_eodhd_sector"]["sector_returned"] = sector
                results["api_tests"]["2_eodhd_sector"]["has_general_field"] = bool(data.get("General"))
                results["api_tests"]["2_eodhd_sector"]["result"] = "✅ SECTOR FOUND" if sector else "⚠️ No sector in response"
            else:
                results["api_tests"]["2_eodhd_sector"]["result"] = f"❌ HTTP {r.status_code}"
        except Exception as e:
            results["api_tests"]["2_eodhd_sector"]["result"] = f"❌ Exception: {str(e)[:100]}"
        
        # TEST 3: FMP Income Statement
        results["api_tests"]["3_fmp_financials"] = {}
        try:
            url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?period=quarter&limit=1&apikey={settings.fmp_api_key}"
            r = await http.get(url, timeout=5.0)
            results["api_tests"]["3_fmp_financials"]["status_code"] = r.status_code
            results["api_tests"]["3_fmp_financials"]["success"] = r.status_code == 200
            if r.status_code == 200:
                data = r.json()
                results["api_tests"]["3_fmp_financials"]["result"] = "✅ FMP WORKING" if data else "⚠️ Empty"
                results["api_tests"]["3_fmp_financials"]["data_sample"] = data[0] if isinstance(data, list) and data else None
            elif r.status_code == 403:
                results["api_tests"]["3_fmp_financials"]["result"] = "❌ 403 Forbidden (Legacy API deprecated or no access)"
                try:
                    error = r.json().get("Error Message", "")
                    results["api_tests"]["3_fmp_financials"]["error_details"] = error[:200]
                except:
                    pass
            else:
                results["api_tests"]["3_fmp_financials"]["result"] = f"❌ HTTP {r.status_code}"
        except Exception as e:
            results["api_tests"]["3_fmp_financials"]["result"] = f"❌ Exception: {str(e)[:100]}"
        
        # TEST 4: Finnhub News
        results["api_tests"]["4_finnhub_news"] = {}
        if settings.finnhub_api_key != "d_placeholder":
            try:
                url = f"https://finnhub.io/api/v1/news?symbol={ticker}&limit=5&token={settings.finnhub_api_key}"
                r = await http.get(url, timeout=5.0)
                results["api_tests"]["4_finnhub_news"]["status_code"] = r.status_code
                results["api_tests"]["4_finnhub_news"]["success"] = r.status_code == 200
                if r.status_code == 200:
                    data = r.json()
                    count = len(data) if isinstance(data, list) else 0
                    results["api_tests"]["4_finnhub_news"]["headline_count"] = count
                    results["api_tests"]["4_finnhub_news"]["result"] = f"✅ {count} Headlines found"
                    if data and isinstance(data, list):
                        results["api_tests"]["4_finnhub_news"]["sample_headline"] = data[0].get("headline", "")[:150]
                else:
                    results["api_tests"]["4_finnhub_news"]["result"] = f"❌ HTTP {r.status_code}"
            except Exception as e:
                results["api_tests"]["4_finnhub_news"]["result"] = f"❌ Exception: {str(e)[:100]}"
        else:
            results["api_tests"]["4_finnhub_news"]["result"] = "⏭️ Skipped - no Finnhub key"
    
    # Summary
    results["summary"] = {
        "eodhd_price_working": results["api_tests"]["1_eodhd_price"].get("success", False),
        "eodhd_sector_working": results["api_tests"]["2_eodhd_sector"].get("success", False),
        "fmp_working": results["api_tests"]["3_fmp_financials"].get("success", False),
        "news_working": results["api_tests"]["4_finnhub_news"].get("success", False),
    }
    
    results["verdict"] = _diagnose_issues(results)
    
    return results


def _diagnose_issues(results: dict) -> str:
    """Generate clear diagnosis."""
    summary = results.get("summary", {})
    env = results.get("environment", {})
    
    if not env.get("gemini_configured") and not env.get("openai_configured"):
        return "🔴 CRITICAL: No LLM keys configured. Add GEMINI_API_KEY and OPENAI_API_KEY to Railway Variables."
    
    if summary.get("eodhd_price_working") and summary.get("fmp_working"):
        return "🟢 ALL APIs WORKING - Issue is likely in LLM layer (Gemini/OpenAI exhausted?)"
    elif summary.get("eodhd_price_working"):
        return "🟡 EODHD Working but FMP deprecated - Price data OK, financials limited"
    else:
        return "🔴 APIs Not responding - Check API keys, rate limits, and service status"


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
            results["fmp"]["http_status"] = r.status_code
            r.raise_for_status()
            data = r.json()
            results["fmp"]["status"] = "ok" if data else "empty"
            if data and isinstance(data, list) and len(data) > 0:
                results["fmp"]["sample"] = {"revenue": data[0].get("revenue"), "date": data[0].get("date")}
            else:
                results["fmp"]["response"] = data
        except httpx.HTTPStatusError as exc:
            results["fmp"]["http_status"] = exc.response.status_code
            results["fmp"]["error"] = f"{exc.response.status_code} {exc.response.reason_phrase}"
            
            # If 403, try a simpler free-tier endpoint
            if exc.response.status_code == 403:
                try:
                    r2 = await http.get(
                        f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
                        f"?apikey={settings.fmp_api_key}"
                    )
                    if r2.status_code == 200:
                        results["fmp"]["alternate_test"] = "profile endpoint works (free tier accessible)"
                        results["fmp"]["suggestion"] = "Use profile or quote endpoints instead of income-statement"
                    else:
                        results["fmp"]["alternate_test_status"] = r2.status_code
                except:
                    results["fmp"]["alternate_test"] = "failed"
                
                # Add guidance about FMP legacy API deprecation
                if "Legacy Endpoint" in str(exc.response.text):
                    results["fmp"]["legacy_api_warning"] = "FMP deprecated legacy endpoints (v3 income-statement, balance-sheet, etc.)"
                    results["fmp"]["solution_a"] = "Upgrade to FMP's new API endpoints (check https://site.financialmodelingprep.com/developer/docs)"
                    results["fmp"]["solution_b"] = "Set FMP_API_KEY=disabled in Railway Variables to use EODHD-only analysis"
            
            try:
                results["fmp"]["response_body"] = exc.response.json()
            except:
                results["fmp"]["response_body"] = exc.response.text[:200]
        except Exception as exc:
            results["fmp"]["error"] = str(exc)
    
    return results
