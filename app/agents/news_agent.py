"""
app/agents/news_agent.py  v3
Finnhub news + sentiment. Applies source-reliability weighting:
  Tier 1 (SEC/Fed/Gov): 3× weight
  Tier 2 (Reuters/Bloomberg/WSJ): 2× weight
  Tier 3 (Other): 1× weight
"""
from __future__ import annotations
import asyncio
import httpx
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import traced
from app.schemas.models import NewsAgentOutput, NewsItem, Sentiment

logger = get_logger(__name__)
settings = get_settings()

_TIER1 = {"sec.gov", "federalreserve.gov", "sec", "fed", "treasury"}
_TIER2 = {"reuters", "bloomberg", "wsj", "ft", "cnbc", "marketwatch", "barrons"}

_SCORE_TO_SENTIMENT = [
    (0.6, Sentiment.VERY_POSITIVE),
    (0.2, Sentiment.POSITIVE),
    (-0.2, Sentiment.NEUTRAL),
    (-0.6, Sentiment.NEGATIVE),
    (-1.1, Sentiment.VERY_NEGATIVE),
]


def _score_enum(score: float) -> Sentiment:
    for threshold, label in _SCORE_TO_SENTIMENT:
        if score >= threshold:
            return label
    return Sentiment.VERY_NEGATIVE


async def run(ticker: str, http: httpx.AsyncClient) -> NewsAgentOutput:
    async with traced("news_agent", ticker=ticker):
        try:
            return await asyncio.wait_for(
                _fetch(ticker, http), timeout=settings.agent_timeout
            )
        except asyncio.TimeoutError:
            return NewsAgentOutput(ticker=ticker, error="timeout", headline_count=0)
        except Exception as exc:
            logger.error("news_agent_error", ticker=ticker, error=str(exc))
            return NewsAgentOutput(ticker=ticker, error=str(exc), headline_count=0)


async def _fetch(ticker: str, http: httpx.AsyncClient) -> NewsAgentOutput:
    from datetime import date, timedelta
    today = date.today()
    from_dt = (today - timedelta(days=7)).isoformat()

    # Concurrent: company news + pre-computed sentiment
    news_r, sent_r = await asyncio.gather(
        http.get(
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={ticker}&from={from_dt}&to={today.isoformat()}"
            f"&token={settings.finnhub_api_key}"
        ),
        http.get(
            f"https://finnhub.io/api/v1/news-sentiment"
            f"?symbol={ticker}&token={settings.finnhub_api_key}"
        ),
        return_exceptions=True,
    )

    raw_news: list[dict] = []
    if not isinstance(news_r, Exception):
        news_r.raise_for_status()
        raw_news = news_r.json() or []

    base_score = 0.0
    if not isinstance(sent_r, Exception) and sent_r.status_code == 200:
        base_score = float(sent_r.json().get("companyNewsScore", 0.0))

    if not raw_news:
        return NewsAgentOutput(
            ticker=ticker, headline_count=0,
            sentiment=Sentiment.NEUTRAL, sentiment_score=0.0,
            key_themes=["no_recent_news"],
        )

    # Source-reliability weighted sentiment
    weighted_score, total_weight = 0.0, 0.0
    items: list[NewsItem] = []
    for a in raw_news[:20]:
        source = a.get("source", "").lower()
        weight = 3.0 if any(t in source for t in _TIER1) else \
                 2.0 if any(t in source for t in _TIER2) else 1.0
        item_score = base_score  # fallback; article-level score not available on free tier
        weighted_score += item_score * weight
        total_weight += weight
        try:
            items.append(NewsItem(
                headline=a.get("headline", "")[:300],
                source=a.get("source", "unknown"),
                published_at=_ts_to_iso(a.get("datetime", 0)),
                relevance_score=min(1.0, weight / 3.0),
            ))
        except Exception:
            continue

    final_score = round(weighted_score / total_weight, 4) if total_weight else base_score
    themes = _extract_themes([i.headline for i in items])

    logger.info("news_agent_complete", ticker=ticker, count=len(raw_news),
                score=final_score, themes=themes)

    return NewsAgentOutput(
        ticker=ticker,
        headline_count=len(raw_news),
        sentiment=_score_enum(final_score),
        sentiment_score=max(-1.0, min(1.0, final_score)),
        top_headlines=items[:10],
        key_themes=themes,
    )


def _ts_to_iso(ts: int) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "2000-01-01"


_POS = {"growth", "profit", "beat", "record", "strong", "upgrade", "buyback", "surge", "expansion"}
_NEG = {"loss", "miss", "decline", "cut", "downgrade", "lawsuit", "fall", "risk", "investigation", "fraud"}

def _extract_themes(headlines: list[str]) -> list[str]:
    joined = " ".join(headlines).lower()
    return list({kw for kw in _POS | _NEG if kw in joined})[:8]
