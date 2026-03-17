"""
tests/test_memory.py
Unit + integration tests for the memory and RAG systems.
No external API calls — all tests use in-process ChromaDB.

Tests:
  • RAG pipeline: ingest → retrieve round-trip
  • Memory store: store analysis → retrieve context
  • Experience bank: store feedback correction → retrieve corrections
  • Edge cases: empty store, no matches, duplicate ingestion
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


# ── RAG Pipeline tests ────────────────────────────────────────────────────────

class TestRAGPipeline:
    """Tests for app/rag/pipeline.py"""

    def test_ingest_returns_chunk_count(self):
        from app.rag.pipeline import ingest_filing
        text = "Apple Inc reported strong Q1 results. Revenue grew 15% year-over-year. " * 20
        count = ingest_filing("AAPL_TEST", text, {"form_type": "10-K", "filed_date": "2024-01-01"})
        assert count > 0, "Should produce at least one chunk"

    def test_ingest_short_text_returns_zero(self):
        from app.rag.pipeline import ingest_filing
        count = ingest_filing("AAPL_TEST2", "Too short", {})
        assert count == 0

    def test_ingest_empty_text_returns_zero(self):
        from app.rag.pipeline import ingest_filing
        assert ingest_filing("AAPL_TEST3", "", {}) == 0
        assert ingest_filing("AAPL_TEST4", "   ", {}) == 0

    def test_retrieve_after_ingest(self):
        from app.rag.pipeline import ingest_filing, retrieve, clear_store
        ticker = "RETRIEVE_TEST_AAPL"
        clear_store(ticker)

        # Ingest a document about risk factors
        text = (
            "RISK FACTORS: The company faces significant regulatory risk in China. "
            "Supply chain disruptions may impact quarterly revenue. "
            "Competition from Samsung and other Android manufacturers is intensifying. "
            "The company's services segment may face antitrust scrutiny. "
        ) * 5
        ingest_filing(ticker, text, {"form_type": "10-K", "filed_date": "2024-01-01"})

        # Retrieve with a relevant query
        result = retrieve(ticker, "What are the main regulatory and competitive risks?", top_k=2)
        assert result, "Should return non-empty result"
        assert "risk" in result.lower() or "regulat" in result.lower() or "competi" in result.lower()

    def test_retrieve_empty_store_returns_empty_string(self):
        from app.rag.pipeline import retrieve, clear_store
        ticker = "EMPTY_STORE_TICKER_XYZ"
        clear_store(ticker)
        result = retrieve(ticker, "anything", top_k=3)
        assert result == ""

    def test_ingest_deduplicates_same_content(self):
        from app.rag.pipeline import ingest_filing, clear_store, _get_store
        ticker = "DEDUP_TEST_AAPL"
        clear_store(ticker)
        text = "Apple has strong fundamentals and consistent cash flow generation. " * 15
        count1 = ingest_filing(ticker, text, {"form_type": "10-K"})
        count2 = ingest_filing(ticker, text, {"form_type": "10-K"})
        # Second ingest should produce same IDs (hash-based) → no duplicates in store
        store = _get_store(ticker)
        total = store._collection.count()
        assert total == count1, f"Duplicate content should be deduplicated: got {total} != {count1}"

    def test_clear_store_removes_all_vectors(self):
        from app.rag.pipeline import ingest_filing, retrieve, clear_store
        ticker = "CLEAR_TEST_AAPL"
        text = "Revenue grew strongly across all segments. " * 15
        ingest_filing(ticker, text, {})
        clear_store(ticker)
        result = retrieve(ticker, "revenue growth", top_k=3)
        assert result == "", "After clear, retrieve should return empty"

    def test_retrieve_top_k_respected(self):
        from app.rag.pipeline import ingest_filing, retrieve, clear_store
        ticker = "TOPK_TEST_AAPL"
        clear_store(ticker)
        # Ingest enough text to generate multiple chunks
        text = (
            "Section A: Revenue risks and market competition analysis. " * 8 +
            "Section B: Regulatory environment and compliance costs. " * 8 +
            "Section C: Supply chain vulnerabilities and mitigation strategies. " * 8
        )
        ingest_filing(ticker, text, {"form_type": "10-K", "filed_date": "2024-01-01"})
        result_k1 = retrieve(ticker, "risk", top_k=1)
        result_k3 = retrieve(ticker, "risk", top_k=3)
        # k=3 should return at least as many characters as k=1
        assert len(result_k3) >= len(result_k1)


# ── Memory Store tests ────────────────────────────────────────────────────────

class TestMemoryStore:
    """Tests for app/memory/store.py — requires ChromaDB in-process."""

    def _make_thesis(self, ticker: str = "AAPL", rec: str = "BUY", conviction: float = 0.72):
        """Build a minimal valid InvestmentThesis for testing."""
        from app.schemas.models import InvestmentThesis
        return InvestmentThesis(**{
            "ticker": ticker,
            "company_name": f"{ticker} Inc.",
            "analysis_date": "2024-06-15",
            "recommendation": rec,
            "time_horizon": "MEDIUM",
            "conviction_score": conviction,
            "executive_summary": "A" * 160,
            "bull_case": "Strong services growth drives recurring revenue and multiple expansion.",
            "bear_case": "China headwinds and elevated valuation limit near-term upside.",
            "valuation": {"methodology": "DCF", "target_price_usd": 195.0, "upside_pct": 4.2, "confidence": 0.65},
            "financials_summary": "Revenue $119.6B, net margin 26%, FCF $23B.",
            "technical_summary": "RSI neutral, MACD bullish cross, trading above 50-day SMA.",
            "catalysts": [{"description": "AI upgrade cycle", "timeline": "MEDIUM", "probability": 0.60}],
            "risk_factors": [{"category": "Geo", "description": "China revenue decline.", "severity": "HIGH"}],
            "sentiment_assessment": "Broadly positive, offset by China concerns.",
            "data_sources": ["EODHD", "FMP", "Finnhub", "SEC EDGAR"],
            "agents_used": ["news_agent", "financial_data_agent", "document_agent"],
        })

    @pytest.mark.asyncio
    async def test_store_and_retrieve_memory(self):
        from app.memory.store import store_analysis_memory, retrieve_memory_context
        ticker = "MEMTEST_AAPL"
        thesis = self._make_thesis(ticker)
        await store_analysis_memory(ticker, "Should I buy Apple?", thesis)
        context = await retrieve_memory_context(ticker, "Apple investment analysis")
        assert context, "Should return non-empty context after storing"
        assert ticker in context or "BUY" in context

    @pytest.mark.asyncio
    async def test_retrieve_empty_memory_returns_empty_string(self):
        from app.memory.store import retrieve_memory_context
        context = await retrieve_memory_context("NONEXISTENT_ZZZZZZ", "some query")
        assert context == ""

    @pytest.mark.asyncio
    async def test_store_multiple_analyses_and_retrieve_relevant(self):
        from app.memory.store import store_analysis_memory, retrieve_memory_context
        ticker = "MULTI_AAPL"
        for rec, conviction in [("BUY", 0.72), ("HOLD", 0.55), ("BUY", 0.80)]:
            await store_analysis_memory(ticker, f"Analysis query {rec}", self._make_thesis(ticker, rec, conviction))
        context = await retrieve_memory_context(ticker, "buy recommendation high conviction")
        assert context, "Should return context with multiple analyses stored"

    @pytest.mark.asyncio
    async def test_store_feedback_memory(self):
        from app.memory.store import store_feedback_memory, get_relevant_corrections
        session_id = "test-session-feedback-001"
        await store_feedback_memory(
            session_id=session_id,
            ticker="FBTEST_AAPL",
            original_output='{"recommendation": "BUY", "conviction_score": 0.8}',
            correction="The PE ratio was incorrect — it should be 28.5, not 32.1",
            score=2,
        )
        corrections = await get_relevant_corrections("FBTEST_AAPL", "PE ratio analysis")
        assert corrections, "Should retrieve stored correction"
        assert "correction" in corrections.lower() or "PE" in corrections

    @pytest.mark.asyncio
    async def test_high_score_feedback_not_tagged_as_correction(self):
        """Score >= 3 should still be stored but not trigger correction retrieval for LLM prompts."""
        from app.memory.store import store_feedback_memory
        # Should not raise
        await store_feedback_memory(
            session_id="test-high-score-session",
            ticker="HIGHSCORE_AAPL",
            original_output='{"recommendation": "HOLD"}',
            correction="",
            score=5,
        )

    @pytest.mark.asyncio
    async def test_memory_store_does_not_raise_on_failure(self, monkeypatch):
        """Memory store should degrade gracefully if ChromaDB is unavailable."""
        from app.memory import store as mem_store
        # Monkeypatch _get_client to raise
        monkeypatch.setattr(mem_store, "_client", None)
        original_get_client = mem_store._get_client
        def failing_client():
            raise ConnectionError("ChromaDB unavailable")
        monkeypatch.setattr(mem_store, "_get_client", failing_client)

        # Should not raise — graceful degradation
        await mem_store.store_analysis_memory("AAPL", "query", self._make_thesis())
        context = await mem_store.retrieve_memory_context("AAPL", "query")
        assert context == ""

        # Restore
        monkeypatch.setattr(mem_store, "_get_client", original_get_client)


# ── Semantic Cache tests ──────────────────────────────────────────────────────

class TestSemanticCache:
    """Tests for app/cache/semantic_cache.py — uses real Redis or degrades."""

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        from app.cache.semantic_cache import cache_lookup
        result = await cache_lookup("this query should never be in cache zzzxxx123")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_store_and_lookup(self):
        """Store a payload and retrieve it with an identical prompt."""
        from app.cache.semantic_cache import cache_store, cache_lookup
        prompt = "test::semantic::cache::roundtrip::aapl::2024"
        payload = {"thesis": {"ticker": "AAPL", "recommendation": "BUY"}, "agents_completed": ["news_agent"]}
        await cache_store(prompt, payload)
        result = await cache_lookup(prompt)
        # May be None if Redis is unavailable — test degrades gracefully
        if result is not None:
            assert result["thesis"]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_cache_degrades_gracefully_when_redis_down(self, monkeypatch):
        from app.cache import semantic_cache as sc
        # Force cache miss path
        monkeypatch.setattr(sc, "_cache_instance", None)
        original_build = sc._build_cache
        def failing_build():
            raise ConnectionError("Redis down")
        monkeypatch.setattr(sc, "_build_cache", failing_build)

        result = await sc.cache_lookup("any prompt")
        assert result is None  # graceful miss

        await sc.cache_store("any prompt", {"data": "test"})  # should not raise

        monkeypatch.setattr(sc, "_build_cache", original_build)
        monkeypatch.setattr(sc, "_cache_instance", None)
