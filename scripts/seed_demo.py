"""
scripts/seed_demo.py
Seeds the local system with a pre-built AAPL analysis demo.
Useful for testing the frontend without spending OpenAI credits.

Run: python scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

DEMO_THESIS = {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "analysis_date": "2024-06-15",
    "recommendation": "BUY",
    "time_horizon": "MEDIUM",
    "conviction_score": 0.72,
    "executive_summary": (
        "Apple Inc. demonstrates durable fundamentals with Q1 FY2024 revenue of $119.6B "
        "(+2.1% YoY), net margin of 26.2%, and free cash flow of $23B. The Services segment "
        "continues to expand at 35% gross margin, providing recurring revenue diversification "
        "from hardware cycles. China exposure remains the primary headwind (-13% YoY) while "
        "the AI-driven iPhone upgrade cycle represents the key upside catalyst for FY2025. "
        "Current P/E of 28.5x is elevated versus historical averages but justified by "
        "Services growth trajectory and capital return program."
    ),
    "bull_case": (
        "Apple Intelligence adoption accelerates the iPhone 16/17 upgrade cycle, "
        "driving Services attach rates and recurring revenue growth above 15% YoY. "
        "The $110B buyback program provides consistent EPS accretion and floor valuation."
    ),
    "bear_case": (
        "China revenue decline accelerates as Huawei regains domestic market share "
        "and regulatory restrictions tighten. P/E compression in a higher-for-longer "
        "interest rate environment limits multiple expansion potential."
    ),
    "valuation": {
        "methodology": "DCF + Peer Comps",
        "target_price_usd": 195.0,
        "upside_pct": 4.2,
        "confidence": 0.65,
    },
    "financials_summary": (
        "Revenue $119.6B (+2.1% YoY), net margin 26.2%, EPS $2.18, "
        "FCF $23B, D/E 1.87x, current ratio 1.07x."
    ),
    "technical_summary": (
        "RSI at 52 (neutral zone). MACD showing bullish cross above signal line. "
        "Price trading above 20-day and 50-day SMA but below 200-day — mixed picture. "
        "Bollinger %B at 63% — room to run before overbought."
    ),
    "catalysts": [
        {
            "description": "Apple Intelligence AI features drive iPhone 16 upgrade supercycle",
            "timeline": "MEDIUM",
            "probability": 0.60,
        },
        {
            "description": "Services segment achieves 20% revenue growth with expanding margins",
            "timeline": "LONG",
            "probability": 0.55,
        },
    ],
    "risk_factors": [
        {
            "category": "Geographic Concentration",
            "description": "China accounts for ~17% of revenue and declined 13% YoY. Further regulatory actions or consumer boycotts could materially impact results.",
            "severity": "HIGH",
            "mitigation": "Geographic diversification into India and Southeast Asia underway.",
        },
        {
            "category": "Regulatory / Antitrust",
            "description": "App Store under regulatory scrutiny in EU (DMA) and US. Forced payment system changes could reduce Services margin.",
            "severity": "MEDIUM",
            "mitigation": "Alternative business models being developed; EU compliance already underway.",
        },
    ],
    "sentiment_assessment": (
        "Broadly positive news sentiment (+0.42) with 12 recent headlines. "
        "Key themes: AI investment narrative, iPhone 16 expectations. "
        "China headwinds remain a recurring concern in analyst commentary."
    ),
    "data_sources": ["EODHD", "FMP", "Finnhub", "SEC EDGAR"],
    "agents_used": ["news_agent", "financial_data_agent", "document_agent"],
}

DEMO_TECHNICALS = {
    "rsi": {"value": 52.4, "signal": "NEUTRAL", "period": 14},
    "macd": {"macd_line": 1.82, "signal_line": 1.24, "histogram": 0.58, "signal": "BULLISH"},
    "bollinger": {
        "upper": 195.80, "middle": 187.15, "lower": 178.50,
        "current_price": 187.15, "bandwidth": 0.092, "percent_b": 0.50,
    },
    "sma": {
        "sma_20": 185.40, "sma_50": 182.10, "sma_200": 191.30,
        "current_price": 187.15, "signal": "BULLISH",
    },
    "overall_technical_signal": "BULLISH",
}


async def seed():
    from app.cache.semantic_cache import cache_store

    print("Seeding semantic cache with demo AAPL analysis...")
    cache_key = "analysis::AAPL::Provide a comprehensive investment thesis with buy/sell recommendation."
    payload = {
        "thesis": DEMO_THESIS,
        "technical_indicators": DEMO_TECHNICALS,
        "agents_completed": ["news_agent", "financial_data_agent", "document_agent"],
        "agents_failed": [],
    }
    await cache_store(cache_key, payload)
    print("✅ Demo AAPL analysis cached")
    print()
    print("Test it:")
    print('  curl -N "http://localhost:8000/api/v1/analyse?ticker=AAPL"')
    print()
    print("You should see: ⚡ Semantic cache hit — returning cached thesis")


if __name__ == "__main__":
    asyncio.run(seed())
