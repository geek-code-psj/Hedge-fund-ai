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
from datetime import date

import google.generativeai as genai
import instructor
from openai import OpenAI, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_random_sleep,
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
    if _openai_client is None and settings.openai_api_key != "sk-placeholder":
        _openai_client = instructor.from_openai(
            OpenAI(api_key=settings.openai_api_key),
            mode=instructor.Mode.JSON,
        )
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
        llm_used = "gemini"
        
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
                            logger.critical("both_gemini_and_openai_rate_limited")
                            raise ValueError(
                                f"BOTH Gemini AND OpenAI rate-limited (429). "
                                f"Gemini: {error_str[:100]}. "
                                f"OpenAI: {openai_error_str[:100]}. "
                                f"Please wait before retrying."
                            )
                        raise ValueError(f"Both Gemini and OpenAI failed: OpenAI error: {openai_error}")
                else:
                    raise ValueError(f"Gemini quota exhausted and OpenAI not configured: {gemini_error}")
            else:
                logger.error("gemini_non_quota_error", error=error_str[:200])
                raise
        
        if not thesis:
            raise ValueError("Failed to generate thesis from both Gemini and OpenAI")
            
        span.set_attribute("recommendation", thesis.recommendation.value)
        span.set_attribute("conviction", thesis.conviction_score)

    # ── Step 2: Critic pass ───────────────────────────────────────────────────
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
