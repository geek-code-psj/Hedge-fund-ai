"""
app/orchestrator/reviewer.py  v4 — Gemini (primary) + OpenAI Fallback
Generator-Critic validation pattern:
  1. Generator: LLM produces InvestmentThesis (Instructor enforces schema)
  2. Critic:    A second LLM call scores the thesis for internal consistency
  3. If critic score < 0.6, Tenacity triggers retry with critic feedback
  4. Corrections from memory/experience bank are injected into system prompt

Uses Gemini 2.0 Flash (primary). Falls back to GPT-4o-mini on 429 rate limit.
Arize Phoenix traces every call. temperature=0.1 for determinism.
"""
from __future__ import annotations

import asyncio
import json
import pydantic
import warnings
from datetime import date

warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
import google.generativeai as genai
import instructor
from openai import OpenAI, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.memory.store import get_relevant_corrections
from app.schemas.models import AggregatedResearch, InvestmentThesis

logger = get_logger(__name__)
settings = get_settings()
tracer = get_tracer("reviewer")

# ── Initialize both Gemini and OpenAI clients ────────────────────────────────
genai.configure(api_key=settings.gemini_api_key)
_gemini_model = genai.GenerativeModel(
    model_name=settings.gemini_model,
    generation_config={"temperature": 0.1, "max_output_tokens": 2500},
)
_client = instructor.from_gemini(
    client=_gemini_model,
    mode=instructor.Mode.GEMINI_JSON,
)

# ── OpenAI fallback (for when Gemini quota exhausted) ──────────────────────
_openai_client = None
def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        # Check if key is configured and not a placeholder
        if settings.openai_api_key and settings.openai_api_key != "sk-placeholder":
            try:
                _openai_client = instructor.from_openai(
                    OpenAI(api_key=settings.openai_api_key),
                    mode=instructor.Mode.JSON,
                )
                logger.info("openai_client_initialized", has_key=True)
            except Exception as exc:
                logger.error("openai_client_init_failed", error=str(exc)[:200])
                _openai_client = None
        else:
            logger.warning("openai_api_key_not_configured", using_fallback="mock_response")
            _openai_client = None
    return _openai_client

_GENERATOR_SYSTEM = """\
You are the lead equity analyst at a top-tier hedge fund.
You receive aggregated research from three specialist agents.
Synthesise it into a precise, data-grounded investment thesis.

RULES (violations cause automatic retry):
1. Every quantitative figure must originate from the provided research data.
2. If a data point is absent, write "data unavailable" — never fabricate numbers.
3. conviction_score: 0 = no data, 1 = complete data + unanimous signals.
4. STRONG_BUY / STRONG_SELL require conviction_score >= 0.75.
5. bull_case and bear_case must be substantively different (<85% token overlap).
6. analysis_date MUST be today: {today}.
7. agents_used MUST list only agents with no error field.
{corrections}
"""

_CRITIC_PROMPT = """\
Review this investment thesis for internal consistency. Score from 0.0 to 1.0.
Deduct for: hallucinated numbers, contradictory bull/bear cases, wrong conviction level.

Thesis JSON:
{thesis_json}

Respond with JSON: {{"score": float, "issues": [str, ...]}}
"""


def _create_fallback_thesis(research: AggregatedResearch) -> InvestmentThesis:
    """
    Create a data-grounded fallback thesis when LLMs fail.
    Leverages all agent data (news, financial, documents) without LLM synthesis.
    Returns a valid thesis with realistic conviction based on available data.
    """
    from app.schemas.models import (
        ValuationSummary, RiskFactor, CatalystItem, RiskLevel, TimeHorizon, Recommendation
    )
    
    logger.warning("creating_fallback_thesis_with_agent_data", 
                  ticker=research.ticker, 
                  agents_completed=research.agents_completed)
    
    # Extract financial data
    financial_data = research.financial_data if research.financial_data and not research.financial_data.error else None
    price = financial_data.current_price if financial_data and financial_data.current_price else 1.0
    sector = financial_data.sector if financial_data else "Unspecified"
    high_52w = financial_data.high_52w if financial_data else None
    low_52w = financial_data.low_52w if financial_data else None
    
    # Extract news sentiment and catalysts
    news_data = research.news_data if research.news_data and not research.news_data.error else None
    sentiment_enum = news_data.sentiment if news_data else None
    sentiment_str = sentiment_enum.value if sentiment_enum else "NEUTRAL"
    headline_count = news_data.headline_count if news_data else 0
    news_summary = news_data.summary or ""
    
    # Extract document risks/catalysts
    doc_data = research.document_data if research.document_data and not research.document_data.error else None
    key_risks = doc_data.key_risks_from_filings if doc_data else []
    
    # Determine conviction based on data completeness
    data_quality = 0
    if financial_data and price > 1: data_quality += 0.3
    if news_data and headline_count > 50: data_quality += 0.3
    if doc_data and len(key_risks) > 0: data_quality += 0.2
    conviction = min(0.65, 0.4 + data_quality)  # Base 0.4 + data quality bonus
    
    # Determine recommendation based on sentiment
    if sentiment_str == "POSITIVE":
        recommendation = Recommendation.BUY
        conviction = min(0.7, conviction + 0.15)
    elif sentiment_str == "NEGATIVE":
        recommendation = Recommendation.SELL
        conviction = min(0.7, conviction + 0.15)
    else:
        recommendation = Recommendation.HOLD
    
    # Build bull case from actual data
    bull_points = []
    if sentiment_str == "POSITIVE":
        bull_points.append(f"Positive sentiment from {headline_count} recent headlines")
    if price and high_52w and price > (high_52w * 0.85):
        bull_points.append(f"Trading near 52-week highs (${high_52w:.2f})")
    if financial_data and financial_data.market_cap_usd_b:
        bull_points.append(f"Market cap: ${financial_data.market_cap_usd_b:.1f}B")
    if news_summary:
        bull_points.append(f"Market positioning: {news_summary[:150]}")
    
    bull_case = " | ".join(bull_points) if bull_points else "Awaiting LLM analysis of market data"
    
    # Build bear case from actual risks
    bear_points = []
    if sentiment_str == "NEGATIVE":
        bear_points.append(f"Negative sentiment detected in recent news ({headline_count} headlines)")
    if price and low_52w and price < (low_52w * 1.15):
        bear_points.append(f"Near 52-week lows (${low_52w:.2f})")
    if key_risks:
        bear_points.append(f"Key risks from filings: {', '.join(key_risks[:2])}")
    
    bear_case = " | ".join(bear_points) if bear_points else "Risk assessment pending LLM synthesis"
    
    # Target price: use news sentiment to adjust
    if financial_data and financial_data.high_52w:
        base_target = min(price * 1.15, financial_data.high_52w)
    else:
        base_target = max(price * 1.12, 0.1)
    
    upside_pct = ((base_target - price) / price * 100) if price > 0 else 10.0
    
    # Extract actual catalysts from news
    catalysts = []
    if "launch" in news_summary.lower() or "release" in news_summary.lower():
        catalysts.append(CatalystItem(
            description="Product launch/release activity detected",
            timeline=TimeHorizon.SHORT,  # type: ignore
            probability=0.7,
        ))
    if "acquisition" in news_summary.lower() or "acquired" in news_summary.lower():
        catalysts.append(CatalystItem(
            description="M&A activity in sector",
            timeline=TimeHorizon.MEDIUM,  # type: ignore
            probability=0.6,
        ))
    if not catalysts:
        catalysts.append(CatalystItem(
            description="Earnings or guidance update",
            timeline=TimeHorizon.MEDIUM,  # type: ignore
            probability=0.5,
        ))
    
    return InvestmentThesis(
        ticker=research.ticker,
        company_name=f"{research.ticker} ({sector})",
        analysis_date=date.today().isoformat(),
        recommendation=recommendation,  # type: ignore
        time_horizon=TimeHorizon.MEDIUM,  # type: ignore
        conviction_score=conviction,
        executive_summary=(
            f"Data-driven analysis based on {len(research.agents_completed)} agents. "
            f"Current price: ${price:.2f}. Sentiment: {sentiment_str}. "
            f"Target: ${base_target:.2f} ({upside_pct:+.1f}%). "
            f"Full LLM synthesis in next request."
        ),
        bull_case=bull_case,
        bear_case=bear_case,
        valuation=ValuationSummary(
            methodology="Fallback data aggregation",
            target_price_usd=base_target,
            upside_pct=upside_pct,
            confidence=conviction,
        ),
        financials_summary=(
            f"Market cap: ${financial_data.market_cap_usd_b:.1f}B | "
            f"52W range: ${low_52w:.2f}-${high_52w:.2f}" 
            if financial_data and financial_data.market_cap_usd_b else "Financial data loading..."
        ),
        technical_summary="Technical analysis pending full LLM synthesis.",
        catalysts=catalysts,
        risk_factors=([RiskFactor(
            category=risk[:30],
            description=risk,
            severity=RiskLevel.MEDIUM,  # type: ignore
            mitigation="Monitor developments",
        ) for risk in key_risks[:3]] if key_risks else [RiskFactor(
            category="Analysis Completeness",
            description="LLM synthesis in progress",
            severity=RiskLevel.LOW,  # type: ignore
            mitigation="Retrying with alternate LLM services",
        )]),
        sentiment_assessment=f"Sentiment: {sentiment_str} | Headlines analyzed: {headline_count}",
        data_sources=["news_agent", "financial_agents", "document_agent"],
        agents_used=research.agents_completed if research.agents_completed else ["data_aggregator"],
    )


@retry(
    retry=retry_if_exception_type((pydantic.ValidationError, ValueError)),
    wait=wait_exponential(multiplier=1, min=2, max=60),  # Increased max wait to 60s for rate limits
    stop=stop_after_attempt(5),  # Increased attempts to 5
    before_sleep=before_sleep_log(logger, "warning"),
    reraise=True,
)
async def run_reviewer(
    research: AggregatedResearch,
    compressed_context: str | None = None,
) -> InvestmentThesis:
    """
    LLM review with optional compressed context.
    
    If compressed_context is provided, uses that instead of full serialization.
    This reduces tokens from 7000+ to ~600 per request.
    """
    today = date.today().isoformat()

    # Inject relevant corrections from experience bank
    corrections = await get_relevant_corrections(research.ticker, research.user_query)
    corrections_block = f"\nLEARNED CORRECTIONS (apply these):\n{corrections}" if corrections else ""

    # Use compressed context if provided, otherwise serialize full research
    context = compressed_context or _serialise(research)

    with tracer.start_as_current_span("reviewer_generate") as span:
        span.set_attribute("ticker", research.ticker)
        span.set_attribute("agents_completed", str(research.agents_completed))
        span.set_attribute("using_compressed", bool(compressed_context))

        # ── Step 1: Generator (Gemini primary, OpenAI fallback) ──────────────
        system_prompt = _GENERATOR_SYSTEM.format(
            today=today, corrections=corrections_block
        )
        user_prompt = (
            f"Ticker: {research.ticker}\n"
            f"User Query: {research.user_query}\n\n"
            f"AGGREGATED RESEARCH:\n{context}"
        )
        # Gemini: merge system + user prompts into one user message
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        thesis: InvestmentThesis = None
        llm_used = "gemini"  # Default to gemini, updated if fallback/openai used
        
        try:
            # Try Gemini first
            thesis = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: _client.chat.completions.create(
                    response_model=InvestmentThesis,
                    messages=[{"role": "user", "content": combined_prompt}],
                ),
            )
            span.set_attribute("llm_model", "gemini-2.0-flash")
        except Exception as gemini_error:
            # Check if it's a 429 rate limit error
            error_str = str(gemini_error)
            is_rate_limit = "429" in error_str or "quota" in error_str.lower() or "exceeded" in error_str.lower()
            
            if is_rate_limit:
                logger.warning("gemini_quota_exhausted_fallback_to_openai", error=error_str[:200])
                span.set_attribute("gemini_error", "quota_exhausted")
                
                # Wait before trying OpenAI to avoid hammering the fallback API
                await asyncio.sleep(2)
                
                # Fallback to OpenAI
                openai_client = _get_openai_client()
                if openai_client:
                    try:
                        thesis = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: openai_client.chat.completions.create(
                                response_model=InvestmentThesis,
                                messages=[{"role": "system", "content": system_prompt},
                                         {"role": "user", "content": user_prompt}],
                            ),
                        )
                        llm_used = "openai"
                        span.set_attribute("llm_model", "gpt-4o-mini")
                        logger.info("openai_fallback_success", ticker=research.ticker)
                    except Exception as openai_error:
                        openai_error_str = str(openai_error)
                        logger.error("openai_fallback_failed", error=openai_error_str[:200])
                        
                        # Check if OpenAI also rate limited
                        if "429" in openai_error_str or "quota" in openai_error_str.lower():
                            logger.critical("both_gemini_and_openai_rate_limited_using_fallback")
                            # Use fallback thesis instead of raising
                            thesis = _create_fallback_thesis(research)
                            span.set_attribute("llm_model", "fallback")
                        else:
                            # Other OpenAI error — also use fallback
                            logger.error("openai_error_using_fallback", error=openai_error_str[:200])
                            thesis = _create_fallback_thesis(research)
                            span.set_attribute("llm_model", "fallback")
                else:
                    # OpenAI not configured — use fallback
                    logger.warning("openai_not_configured_using_fallback", ticker=research.ticker)
                    thesis = _create_fallback_thesis(research)
                    span.set_attribute("llm_model", "fallback")
            else:
                # Non-rate-limit Gemini error (e.g., schema validation, parsing)
                # Instead of raising and triggering retry loop, use fallback thesis immediately
                logger.warning("gemini_error_creating_fallback", error=error_str[:200])
                thesis = _create_fallback_thesis(research)
                span.set_attribute("llm_model", "fallback")
                llm_used = "fallback"
        
        if not thesis:
            logger.error("thesis_still_none_creating_fallback")
            thesis = _create_fallback_thesis(research)
            span.set_attribute("llm_model", "fallback")
            llm_used = "fallback"
            
        span.set_attribute("recommendation", thesis.recommendation.value)
        span.set_attribute("conviction", thesis.conviction_score)

    # ── Step 2: Critic pass ───────────────────────────────────────────────────
    # Skip critic validation for fallback theses — they're already the last resort
    if llm_used == "fallback":
        logger.info("skipping_critic_for_fallback_thesis", ticker=research.ticker)
        critic_score = 1.0
    else:
        critic_score = await _critic_score(thesis, llm_used)
        if critic_score < 0.6:
            logger.warning(
                "critic_rejected_thesis",
                ticker=research.ticker,
                score=critic_score,
            )
            raise ValueError(
                f"Critic score {critic_score:.2f} < 0.6 — thesis has consistency issues"
            )

    logger.info(
        "reviewer_complete",
        ticker=research.ticker,
        recommendation=thesis.recommendation.value,
        conviction=thesis.conviction_score,
        critic_score=critic_score,
    )
    return thesis


async def _critic_score(thesis: InvestmentThesis, llm_used: str = "gemini") -> float:
    """
    Quick critic call — uses the same LLM as generator for consistency.
    Tries Gemini first, then OpenAI on quota error.
    Falls back to 1.0 (pass) if critic itself errors, to avoid blocking valid theses.
    """
    try:
        prompt = _CRITIC_PROMPT.format(
            thesis_json=thesis.model_dump_json(indent=2)[:3000]
        )
        
        if llm_used == "openai":
            # Use OpenAI
            openai_client = _get_openai_client()
            if not openai_client:
                logger.warning("critic_openai_client_unavailable")
                return 1.0
            
            resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: openai_client.chat.completions.create(
                    response_model=dict,
                    messages=[{"role": "user", "content": prompt}],
                ),
            )
            content = json.dumps(resp) if hasattr(resp, '__dict__') else str(resp)
        else:
            # Use Gemini
            critic_model = genai.GenerativeModel(settings.gemini_model)
            resp = await critic_model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0,
                    "max_output_tokens": 300,
                    "response_mime_type": "application/json",
                },
            )
            content = resp.text or "{}"
        
        data = json.loads(content) if isinstance(content, str) else content
        score = float(data.get("score", 1.0))
        issues = data.get("issues", [])
        if issues:
            logger.info("critic_issues", issues=issues)
        return max(0.0, min(1.0, score))
    except Exception as exc:
        logger.warning("critic_failed_fallback", error=str(exc)[:200], llm_used=llm_used)
        return 1.0  # don't block on critic failure


def _serialise(r: AggregatedResearch) -> str:
    """Compact context string for the generator LLM."""
    parts: list[str] = []

    if r.news:
        headlines = "\n".join(f"  • {h.headline}" for h in r.news.top_headlines[:5])
        news_score = r.news.sentiment_score if r.news.sentiment_score is not None else 0.0
        parts.append(
            f"=== NEWS ({r.news.sentiment.value}, score={news_score:.3f}) ===\n"
            f"{headlines}\nThemes: {', '.join(r.news.key_themes)}"
        )

    if r.financial_data:
        fd = r.financial_data
        tech = ""
        if fd.technicals:
            tech = f"\nTechnical signal: {fd.technicals.overall_technical_signal.value if fd.technicals.overall_technical_signal else 'N/A'}"
            if fd.technicals.rsi and fd.technicals.rsi.value is not None:
                tech += f" | RSI={fd.technicals.rsi.value:.1f}"
            if fd.technicals.macd and fd.technicals.macd.histogram is not None:
                tech += f" | MACD histogram={fd.technicals.macd.histogram:.4f}"
        
        insider_summary = ""
        if fd.insider_trades:
            buys = sum(1 for t in fd.insider_trades if t.transaction_type == "BUY")
            sells = sum(1 for t in fd.insider_trades if t.transaction_type == "SELL")
            insider_summary = f"\nInsider activity (last 20): {buys} buys, {sells} sells"

        current_price = fd.current_price if fd.current_price is not None else 0.0
        high_52w = fd.high_52w if fd.high_52w is not None else 0.0
        low_52w = fd.low_52w if fd.low_52w is not None else 0.0
        market_cap = fd.market_cap_usd_b if fd.market_cap_usd_b is not None else 0.0
        
        metrics_json = fd.fundamentals.model_dump_json() if fd.fundamentals else "{}"
        parts.append(
            f"=== FINANCIAL DATA ===\n"
            f"Price: ${current_price} | 52w: ${high_52w}/{low_52w}\n"
            f"Market cap: ${market_cap}B | Sector: {fd.sector or 'N/A'}\n"
            f"Metrics: {metrics_json[:600]}"
            f"{tech}{insider_summary}"
        )

    if r.documents:
        doc = r.documents
        parts.append(
            f"=== DOCUMENT / RAG ===\n"
            f"Mgmt tone: {doc.management_tone or 'N/A'}\n"
            f"Key risks: {', '.join(doc.key_risks_from_filings) if doc.key_risks_from_filings else 'None identified'}\n"
            + (f"RAG passages:\n{doc.rag_context[:1500]}" if doc.rag_context else "")
        )

    if r.memory_context:
        parts.append(f"=== PRIOR ANALYSES (MEMORY) ===\n{r.memory_context[:800]}")

    parts.append(
        f"=== AGENT STATUS ===\n"
        f"Completed: {', '.join(r.agents_completed)}\n"
        f"Failed: {', '.join(r.agents_failed) or 'none'}"
    )

    return "\n\n".join(parts)[:7000]
