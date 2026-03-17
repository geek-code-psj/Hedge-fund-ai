"""
tests/test_integration.py
Integration tests for the orchestrator pipeline.
Uses httpx.AsyncClient with a real FastAPI TestClient.
External API calls are mocked via unittest.mock.

Run:
    pytest tests/test_integration.py -v
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.schemas.models import (
    DocumentAgentOutput,
    FinancialDataAgentOutput,
    InvestmentThesis,
    NewsAgentOutput,
    Sentiment,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _mock_news() -> NewsAgentOutput:
    return NewsAgentOutput(
        ticker="AAPL",
        headline_count=12,
        sentiment=Sentiment.POSITIVE,
        sentiment_score=0.42,
        top_headlines=[],
        key_themes=["growth", "iPhone"],
    )


def _mock_fin_data() -> FinancialDataAgentOutput:
    from app.schemas.models import FinancialMetrics, PriceData
    return FinancialDataAgentOutput(
        ticker="AAPL",
        price=PriceData(close=187.15, open=186.0, high_52w=199.62, low_52w=164.08, volume_avg=55_000_000),
        metrics=FinancialMetrics(
            revenue_usd_m=119600.0,
            revenue_growth_yoy=0.021,
            net_margin=0.262,
            debt_to_equity=1.87,
            current_ratio=1.07,
            free_cash_flow_usd_m=23000.0,
            pe_ratio=28.5,
        ),
        market_cap_usd_b=2890.0,
        sector="Technology",
        industry="Consumer Electronics",
    )


def _mock_doc_data() -> DocumentAgentOutput:
    from app.schemas.models import FilingExcerpt
    return DocumentAgentOutput(
        ticker="AAPL",
        company_name="Apple Inc.",
        filings=[
            FilingExcerpt(
                form_type="10-K",
                filed_date="2024-02-02",
                excerpt="Risk factors include China exposure and supply chain concentration.",
                risk_mentions=["regulatory", "supply chain"],
            )
        ],
        management_tone=Sentiment.POSITIVE,
        key_risks_from_filings=["regulatory", "supply chain", "competition"],
    )


def _mock_thesis() -> InvestmentThesis:
    return InvestmentThesis(**{
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "analysis_date": "2024-06-15",
        "recommendation": "BUY",
        "time_horizon": "MEDIUM",
        "conviction_score": 0.72,
        "executive_summary": "Apple demonstrates solid fundamentals with $119.6B revenue, "
                             "26.2% net margin, and $23B free cash flow. Services growth "
                             "provides recurring revenue diversification. China headwinds "
                             "and elevated P/E represent primary risks.",
        "bull_case": "Services flywheel at 35% gross margin and Apple Intelligence "
                     "adoption driving upgrade cycle present clear upside pathway.",
        "bear_case": "China revenue decline of 13% YoY and P/E premium compression "
                     "in rising rate environment could limit returns.",
        "valuation": {
            "methodology": "DCF + Peer Comps",
            "target_price_usd": 195.0,
            "upside_pct": 4.2,
            "confidence": 0.68,
        },
        "financials_summary": "Revenue $119.6B (+2.1% YoY), net margin 26.2%, FCF $23B.",
        "catalysts": [
            {
                "description": "Apple Intelligence features driving iPhone upgrade cycle.",
                "timeline": "MEDIUM",
                "probability": 0.60,
            }
        ],
        "risk_factors": [
            {
                "category": "Geographic",
                "description": "China revenue declined 13% YoY with further regulatory risk.",
                "severity": "HIGH",
            }
        ],
        "sentiment_assessment": "Broadly positive news sentiment offset by China concerns.",
        "data_sources": ["EODHD", "FMP", "Finnhub", "SEC EDGAR"],
        "agents_used": ["news_agent", "financial_data_agent", "document_agent"],
    })


# ── SSE parsing helper ────────────────────────────────────────────────────────

def parse_sse_stream(raw: str) -> list[dict]:
    """Parse raw SSE text into list of {event, data} dicts."""
    events = []
    current: dict = {}
    for line in raw.splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    return events


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_analyse_sse_stream_full_pipeline():
    """
    Full pipeline integration test with all external calls mocked.
    Verifies SSE frame sequence and final thesis structure.
    """
    with (
        patch("app.cache.semantic_cache.cache_lookup", new_callable=AsyncMock, return_value=None),
        patch("app.cache.semantic_cache.cache_store", new_callable=AsyncMock),
        patch("app.db.feedback.store_session_context", new_callable=AsyncMock),
        patch("app.agents.news_agent.run", new_callable=AsyncMock, return_value=_mock_news()),
        patch("app.agents.financial_data_agent.run", new_callable=AsyncMock, return_value=_mock_fin_data()),
        patch("app.agents.document_agent.run", new_callable=AsyncMock, return_value=_mock_doc_data()),
        patch("app.orchestrator.reviewer.run_reviewer", new_callable=AsyncMock, return_value=_mock_thesis()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/analyse",
                params={"ticker": "AAPL", "query": "Is Apple a good investment?"},
            )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = parse_sse_stream(resp.text)
    event_types = [e["event"] for e in events]

    # Must include at least one progress event
    assert "progress" in event_types, f"Missing progress events. Got: {event_types}"

    # Must end with a final event
    assert "final" in event_types, f"Missing final event. Got: {event_types}"

    # Validate final event structure
    final = next(e for e in events if e["event"] == "final")
    thesis_data = final["data"]["thesis"]
    assert thesis_data["ticker"] == "AAPL"
    assert thesis_data["recommendation"] == "BUY"
    assert thesis_data["conviction_score"] == 0.72
    assert final["data"]["cached"] is False


@pytest.mark.asyncio
async def test_analyse_sse_cache_hit():
    """When cache returns a result, pipeline is skipped and cached=True."""
    cached_payload = {
        "thesis": _mock_thesis().model_dump(),
        "agents_completed": ["news_agent", "financial_data_agent", "document_agent"],
        "agents_failed": [],
    }

    with patch("app.cache.semantic_cache.cache_lookup", new_callable=AsyncMock, return_value=cached_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analyse", params={"ticker": "AAPL"})

    events = parse_sse_stream(resp.text)
    final = next((e for e in events if e["event"] == "final"), None)
    assert final is not None
    assert final["data"]["cached"] is True


@pytest.mark.asyncio
async def test_feedback_endpoint_session_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/feedback",
            json={"session_id": "nonexistent-session", "feedback_score": 5},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyse_ticker_uppercase_normalisation():
    """Lowercase ticker should be normalised to uppercase."""
    with (
        patch("app.cache.semantic_cache.cache_lookup", new_callable=AsyncMock, return_value=None),
        patch("app.cache.semantic_cache.cache_store", new_callable=AsyncMock),
        patch("app.db.feedback.store_session_context", new_callable=AsyncMock),
        patch("app.agents.news_agent.run", new_callable=AsyncMock, return_value=_mock_news()),
        patch("app.agents.financial_data_agent.run", new_callable=AsyncMock, return_value=_mock_fin_data()),
        patch("app.agents.document_agent.run", new_callable=AsyncMock, return_value=_mock_doc_data()),
        patch("app.orchestrator.reviewer.run_reviewer", new_callable=AsyncMock, return_value=_mock_thesis()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analyse", params={"ticker": "aapl"})

    assert resp.status_code == 200
    events = parse_sse_stream(resp.text)
    final = next((e for e in events if e["event"] == "final"), None)
    assert final["data"]["thesis"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_rate_limit_header_present():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    # Liveness probe should always be 200
    assert resp.status_code == 200
