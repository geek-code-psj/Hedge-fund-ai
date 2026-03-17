"""
tests/test_evaluation.py
DeepEval LLM evaluation suite for Hedge Fund AI.

Metrics:
  1. AnswerRelevancyMetric   — penalise rambling / off-topic output
  2. FaithfulnessMetric      — penalise hallucinated figures
  3. ContextualPrecisionMetric — penalise irrelevant context retrieval

Run:
    deepeval test run tests/test_evaluation.py -n 4 -c -i --verbose

Flags:
  -n 4   parallel workers
  -c     cache LLM evaluation calls
  -i     inline metric scores
"""
from __future__ import annotations

import json
import pytest

from deepeval import assert_test
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualPrecisionMetric,
)
from deepeval.test_case import LLMTestCase

# ── Evaluation model (cost-effective) ─────────────────────────────────────────
EVAL_MODEL = "gpt-4o-mini"

# ── Fixture: realistic research context ───────────────────────────────────────

APPLE_CONTEXT = [
    """
    NEWS AGENT (POSITIVE, score=0.42):
    Headlines: Apple beats Q1 FY2024 revenue estimates at $119.6B (+2.1% YoY).
    iPhone sales grow in US and Europe; China down 13% YoY.
    Apple Intelligence features driving upgrade cycle in analyst commentary.
    Key themes: revenue, growth, iPhone, China risk, AI.
    """,
    """
    FINANCIAL DATA AGENT:
    Price: Close=$187.15, 52w H/L=$199.62/$164.08
    Market Cap: $2.89T
    Sector: Technology | Industry: Consumer Electronics
    Metrics: revenue=$119.6B, net_margin=0.262, revenue_growth_yoy=0.021,
    pe_ratio=28.5, pb_ratio=45.2, free_cash_flow_usd_m=23000, debt_to_equity=1.87
    """,
    """
    DOCUMENT AGENT (management tone: POSITIVE):
    10-K filed 2024-02-02: Risk factors include China regulatory exposure,
    supply chain concentration, AI competition from Google and Microsoft,
    foreign currency headwinds. Management highlighted services growth
    as primary diversification strategy with 35% gross margin in Services.
    """,
]

# ── Fixture: thesis outputs ────────────────────────────────────────────────────

GOOD_THESIS = """
Apple Inc. (AAPL) — HOLD recommendation with a 12-month target of $195.
Q1 FY2024 revenue of $119.6B came in at +2.1% YoY, below the historical
growth pace, with net margin of 26.2% demonstrating durable profitability.
The Services segment continues to expand, providing recurring revenue at
~35% gross margin. Key risks include China exposure (13% YoY decline) and
elevated P/E of 28.5x in a higher-rate environment. Free cash flow of $23B
supports buyback program. Conviction: 0.68 (data complete, mixed signals).
Bull case: Services flywheel and Apple Intelligence upgrade cycle.
Bear case: China regulatory risk and China revenue decline acceleration.
"""

HALLUCINATED_THESIS = """
Apple reported revenue of $145B in Q1, beating estimates by 25%. The company's
AI division generated $30B in revenue with 90% margins. The stock trades at
a P/E of 12x making it dramatically undervalued. Management guided for 40%
revenue growth in the next quarter. STRONG_BUY with target $350.
"""

RAMBLING_THESIS = """
Apple is a well-known technology company. Investing in stocks involves risk.
The technology sector has been volatile over the years. Warren Buffett once
said diversification is protection against ignorance. The stock market can
go up or down. Investors should always consult a financial advisor before
making investment decisions. Apple makes iPhones, which are popular devices
sold around the world in many countries. Past performance is not a guarantee
of future results. Consider your risk tolerance before investing.
"""

QUERY = "Should I invest in Apple stock? Provide a detailed analysis with recommendation."


# ── Metric factories ───────────────────────────────────────────────────────────

def relevancy_metric(threshold: float = 0.7) -> AnswerRelevancyMetric:
    return AnswerRelevancyMetric(
        threshold=threshold,
        model=EVAL_MODEL,
        include_reason=True,
        async_mode=True,
    )


def faithfulness_metric(threshold: float = 0.75) -> FaithfulnessMetric:
    return FaithfulnessMetric(
        threshold=threshold,
        model=EVAL_MODEL,
        include_reason=True,
        async_mode=True,
    )


def contextual_precision_metric(threshold: float = 0.65) -> ContextualPrecisionMetric:
    return ContextualPrecisionMetric(
        threshold=threshold,
        model=EVAL_MODEL,
        include_reason=True,
    )


def make_case(output: str, context: list[str] | None = None) -> LLMTestCase:
    return LLMTestCase(
        input=QUERY,
        actual_output=output,
        retrieval_context=context or APPLE_CONTEXT,
    )


# ── Tests: Good thesis passes all metrics ─────────────────────────────────────

def test_good_thesis_relevancy():
    assert_test(make_case(GOOD_THESIS), [relevancy_metric(0.7)])


def test_good_thesis_faithfulness():
    assert_test(make_case(GOOD_THESIS), [faithfulness_metric(0.75)])


def test_good_thesis_contextual_precision():
    assert_test(make_case(GOOD_THESIS), [contextual_precision_metric(0.65)])


def test_good_thesis_all_metrics():
    """All three metrics must pass simultaneously."""
    assert_test(
        make_case(GOOD_THESIS),
        [relevancy_metric(0.7), faithfulness_metric(0.75), contextual_precision_metric(0.65)],
    )


# ── Tests: Hallucinated thesis fails faithfulness ─────────────────────────────

def test_hallucinated_thesis_fails_faithfulness():
    metric = faithfulness_metric(0.75)
    tc = make_case(HALLUCINATED_THESIS)
    metric.measure(tc)
    assert metric.score < 0.75, (
        f"Expected faithfulness < 0.75 for hallucinated output, got {metric.score:.3f}. "
        f"Reason: {metric.reason}"
    )


# ── Tests: Rambling thesis fails relevancy ────────────────────────────────────

def test_rambling_thesis_fails_relevancy():
    metric = relevancy_metric(0.7)
    tc = make_case(RAMBLING_THESIS)
    metric.measure(tc)
    assert metric.score < 0.7, (
        f"Expected relevancy < 0.7 for rambling output, got {metric.score:.3f}. "
        f"Reason: {metric.reason}"
    )


# ── Tests: Pydantic schema contracts (no LLM calls) ──────────────────────────

def test_strong_buy_requires_high_conviction():
    from pydantic import ValidationError
    from app.schemas.models import InvestmentThesis, Recommendation

    base = _thesis_payload()
    base["recommendation"] = "STRONG_BUY"
    base["conviction_score"] = 0.50  # too low

    with pytest.raises(ValidationError, match="conviction_score"):
        InvestmentThesis(**base)


def test_strong_sell_requires_high_conviction():
    from pydantic import ValidationError
    from app.schemas.models import InvestmentThesis

    base = _thesis_payload()
    base["recommendation"] = "STRONG_SELL"
    base["conviction_score"] = 0.60

    with pytest.raises(ValidationError, match="conviction_score"):
        InvestmentThesis(**base)


def test_valid_strong_buy_with_high_conviction():
    from app.schemas.models import InvestmentThesis

    base = _thesis_payload()
    base["recommendation"] = "STRONG_BUY"
    base["conviction_score"] = 0.85
    # Should not raise
    thesis = InvestmentThesis(**base)
    assert thesis.recommendation.value == "STRONG_BUY"


def test_invalid_analysis_date_format():
    from pydantic import ValidationError
    from app.schemas.models import InvestmentThesis

    base = _thesis_payload()
    base["analysis_date"] = "15/06/2024"  # wrong format

    with pytest.raises(ValidationError, match="analysis_date"):
        InvestmentThesis(**base)


def test_ticker_normalised_to_uppercase():
    from app.schemas.models import InvestmentThesis

    base = _thesis_payload()
    base["ticker"] = "aapl"
    thesis = InvestmentThesis(**base)
    assert thesis.ticker == "AAPL"


def test_implausible_revenue_growth_rejected():
    from pydantic import ValidationError
    from app.schemas.models import FinancialMetrics

    with pytest.raises(ValidationError):
        FinancialMetrics(revenue_growth_yoy=15.0)  # 1500% — implausible


def test_52w_high_below_low_rejected():
    from pydantic import ValidationError
    from app.schemas.models import PriceData

    with pytest.raises(ValidationError):
        PriceData(close=100.0, open=98.0, high_52w=90.0, low_52w=95.0, volume_avg=1_000_000)


def test_news_item_invalid_date_rejected():
    from pydantic import ValidationError
    from app.schemas.models import NewsItem

    with pytest.raises(ValidationError):
        NewsItem(
            headline="Apple beats earnings",
            source="Reuters",
            published_at="June 15 2024",  # wrong format
            relevance_score=0.8,
        )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _thesis_payload() -> dict:
    """Minimal valid InvestmentThesis payload for schema tests."""
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "analysis_date": "2024-06-15",
        "recommendation": "BUY",
        "time_horizon": "MEDIUM",
        "conviction_score": 0.68,
        "executive_summary": "A" * 160,
        "bull_case": "Strong services growth and Apple Intelligence upgrade cycle "
                     "should drive multiple expansion over the next 12 months.",
        "bear_case": "China revenue decline and elevated P/E in rising-rate "
                     "environment present meaningful downside risk.",
        "valuation": {
            "methodology": "DCF + Peer Comps",
            "target_price_usd": 195.0,
            "upside_pct": 4.2,
            "confidence": 0.65,
        },
        "financials_summary": "Revenue $119.6B (+2.1% YoY), net margin 26.2%, FCF $23B.",
        "catalysts": [
            {
                "description": "Apple Intelligence AI feature adoption drives iPhone upgrade cycle.",
                "timeline": "MEDIUM",
                "probability": 0.60,
            }
        ],
        "risk_factors": [
            {
                "category": "Geographic",
                "description": "China revenue declined 13% YoY and further regulatory actions are possible.",
                "severity": "HIGH",
            }
        ],
        "sentiment_assessment": "Broadly positive sentiment on AI narrative, offset by China concerns.",
        "data_sources": ["EODHD", "FMP", "Finnhub", "SEC EDGAR"],
        "agents_used": ["news_agent", "financial_data_agent", "document_agent"],
    }
