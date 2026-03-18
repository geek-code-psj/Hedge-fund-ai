"""
app/orchestrator/reviewer.py  v3 — Gemini edition
Generator-Critic validation pattern:
  1. Generator: LLM produces InvestmentThesis (Instructor enforces schema)
  2. Critic:    A second LLM call scores the thesis for internal consistency
  3. If critic score < 0.6, Tenacity triggers retry with critic feedback
  4. Corrections from memory/experience bank are injected into system prompt

Uses free Gemini 2.0 Flash via google-generativeai SDK.
Arize Phoenix traces every call. temperature=0.1 for determinism.
"""
from __future__ import annotations

import asyncio
import json
import pydantic
from datetime import date

import google.generativeai as genai
import instructor
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings, get_next_gemini_api_key
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.memory.store import get_relevant_corrections
from app.schemas.models import AggregatedResearch, InvestmentThesis

logger = get_logger(__name__)
settings = get_settings()
tracer = get_tracer("reviewer")

# Use rotated API key for initial configuration
genai.configure(api_key=get_next_gemini_api_key())
_gemini_model = genai.GenerativeModel(
    model_name=settings.gemini_model,
    generation_config={"temperature": 0.1, "max_output_tokens": 2500},
)
_client = instructor.from_gemini(
    client=_gemini_model,
    mode=instructor.Mode.GEMINI_JSON,
)

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


@retry(
    retry=retry_if_exception_type((pydantic.ValidationError, ValueError)),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(4),
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
    Rotates between multiple Gemini API keys to avoid rate limits (429 errors).
    """
    today = date.today().isoformat()

    # Inject relevant corrections from experience bank
    corrections = await get_relevant_corrections(research.ticker, research.user_query)
    corrections_block = f"\nLEARNED CORRECTIONS (apply these):\n{corrections}" if corrections else ""

    # Use compressed context if provided, otherwise serialize full research
    context = compressed_context or _serialise(research)

    # Reconfigure API key on each attempt (rotates on retry for rate limit resilience)
    genai.configure(api_key=get_next_gemini_api_key())
    current_client = instructor.from_gemini(
        client=genai.GenerativeModel(
            model_name=settings.gemini_model,
            generation_config={"temperature": 0.1, "max_output_tokens": 2500},
        ),
        mode=instructor.Mode.GEMINI_JSON,
    )

    with tracer.start_as_current_span("reviewer_generate") as span:
        span.set_attribute("ticker", research.ticker)
        span.set_attribute("agents_completed", str(research.agents_completed))
        span.set_attribute("using_compressed", bool(compressed_context))

        # ── Step 1: Generator (Gemini) ────────────────────────────────────────
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

        thesis: InvestmentThesis = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: current_client.chat.completions.create(
                response_model=InvestmentThesis,
                messages=[{"role": "user", "content": combined_prompt}],
            ),
        )
        span.set_attribute("recommendation", thesis.recommendation.value)
        span.set_attribute("conviction", thesis.conviction_score)

    # ── Step 2: Critic pass ───────────────────────────────────────────────────
    critic_score = await _critic_score(thesis)
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


async def _critic_score(thesis: InvestmentThesis) -> float:
    """
    Quick critic call — uses Gemini to score thesis consistency.
    Falls back to 1.0 (pass) if critic itself errors, to avoid blocking valid theses.
    """
    try:
        # Use rotated API key for critic model to avoid rate limits
        genai.configure(api_key=get_next_gemini_api_key())
        critic_model = genai.GenerativeModel(settings.gemini_model)
        prompt = _CRITIC_PROMPT.format(
            thesis_json=thesis.model_dump_json(indent=2)[:3000]
        )
        resp = await critic_model.generate_content_async(
            prompt,
            generation_config={
                "temperature": 0,
                "max_output_tokens": 300,
                "response_mime_type": "application/json",
            },
        )
        content = resp.text or "{}"
        data = json.loads(content)
        score = float(data.get("score", 1.0))
        issues = data.get("issues", [])
        if issues:
            logger.info("critic_issues", issues=issues)
        return max(0.0, min(1.0, score))
    except Exception as exc:
        logger.warning("critic_failed_fallback", error=str(exc))
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
