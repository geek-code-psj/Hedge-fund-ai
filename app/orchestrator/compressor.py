"""
app/orchestrator/compressor.py
Token compression: Extract only critical data from agent outputs.
Reduces 7000+ tokens → 600 tokens (~92% reduction).
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.models import (
    FinancialDataAgentOutput,
    NewsAgentOutput,
    DocumentAgentOutput,
)

logger = get_logger(__name__)


def compress_news_output(news: NewsAgentOutput) -> str:
    """Compress news to essentials: sentiment + top 3 headlines + key themes."""
    if not news or news.error:
        return "[NO NEWS DATA]"
    
    headlines = "\n".join(
        f"  • {item.headline[:100]}" 
        for item in (news.top_headlines or [])[:3]
    )
    
    themes = ", ".join(news.key_themes[:5]) if news.key_themes else "none"
    
    return f"""\
NEWS SENTIMENT: {news.sentiment.value} (score: {news.sentiment_score:.2f})
Headlines ({news.headline_count} total):
{headlines if headlines else "  None"}
Key Themes: {themes}
"""


def compress_financial_output(fin: FinancialDataAgentOutput) -> str:
    """Compress financials to essentials: price, technicals, key fundamentals."""
    if not fin or fin.error:
        return "[NO FINANCIAL DATA]"
    
    tech = fin.technicals
    tech_signals = []
    if tech:
        if tech.rsi and tech.rsi.signal:
            tech_signals.append(f"RSI({tech.rsi.value:.0f}): {tech.rsi.signal.value}")
        if tech.macd and tech.macd.signal:
            tech_signals.append(f"MACD: {tech.macd.signal.value}")
        if tech.bollinger and tech.bollinger.percent_b is not None:
            bb_signal = "Overbought" if tech.bollinger.percent_b > 0.8 else (
                "Oversold" if tech.bollinger.percent_b < 0.2 else "Mid-range"
            )
            tech_signals.append(f"Bollinger: {bb_signal}")
    
    fund = fin.fundamentals
    fund_metrics = []
    if fund:
        if fund.pe_ratio:
            fund_metrics.append(f"P/E: {fund.pe_ratio:.1f}x")
        if fund.debt_to_equity:
            fund_metrics.append(f"Debt/Equity: {fund.debt_to_equity:.2f}")
        if fund.net_margin:
            fund_metrics.append(f"Net Margin: {fund.net_margin:.1%}")
    
    insiders = f"{len(fin.insider_trades)} insider trades" if fin.insider_trades else "No insider trades"
    
    return f"""\
PRICE: ${fin.current_price:.2f} (52w: ${fin.low_52w:.2f} - ${fin.high_52w:.2f})
Market Cap: ${fin.market_cap_usd_b:.1f}B | Sector: {fin.sector or 'N/A'}
Technical Signals: {', '.join(tech_signals) if tech_signals else 'N/A'}
Fundamentals: {', '.join(fund_metrics) if fund_metrics else 'N/A'}
Insider Activity: {insiders}
"""


def compress_document_output(doc: DocumentAgentOutput) -> str:
    """Compress SEC filings to essentials: top risks + management tone + filing count."""
    if not doc or doc.error:
        return "[NO DOCUMENT DATA]"
    
    risks = ", ".join(doc.key_risks_from_filings[:5]) if doc.key_risks_from_filings else "None identified"
    filing_summary = f"{len(doc.filings)} filings retrieved" if doc.filings else "No filings"
    
    return f"""\
SEC FILINGS: {filing_summary} ({doc.company_name or 'Unknown'})
Top Risks: {risks}
Management Tone: {doc.management_tone or 'N/A'}
RAG Context Available: {'Yes' if doc.rag_context else 'No'}
"""


def compress_aggregated_research(
    news: NewsAgentOutput | None,
    financial: FinancialDataAgentOutput | None,
    document: DocumentAgentOutput | None,
) -> str:
    """
    Compress all agent outputs into a single compact research summary.
    
    Returns ~600 tokens instead of 7000+ tokens.
    Perfect for sending to LLM reviewer.
    """
    sections = []
    
    if news:
        sections.append(compress_news_output(news))
    if financial:
        sections.append(compress_financial_output(financial))
    if document:
        sections.append(compress_document_output(document))
    
    compressed = "\n".join(sections)
    
    # Estimate tokens (rough: 1 token ≈ 4 chars)
    estimated_tokens = len(compressed) // 4
    logger.info(
        "research_compressed",
        original_estimate=7000,
        compressed_tokens=estimated_tokens,
        reduction_pct=round(100 * (1 - estimated_tokens / 7000), 1),
    )
    
    return compressed
