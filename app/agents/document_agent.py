"""
app/agents/document_agent.py  v3
SEC EDGAR free API → ingest filing text into ChromaDB RAG pipeline
→ retrieve semantically relevant passages for the reviewer context.
"""
from __future__ import annotations
import asyncio, re
from typing import Any
import httpx
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import traced
from app.rag.pipeline import ingest_filing, retrieve
from app.schemas.models import DocumentAgentOutput, FilingExcerpt, Sentiment

logger = get_logger(__name__)
settings = get_settings()

_RISK_KW = [
    "litigation","regulatory","competition","debt","liquidity","cybersecurity",
    "inflation","interest rate","supply chain","geopolitical","lawsuit",
    "investigation","going concern","fraud","restatement",
]

async def run(ticker: str, http: httpx.AsyncClient) -> DocumentAgentOutput:
    async with traced("document_agent", ticker=ticker):
        try:
            return await asyncio.wait_for(_fetch(ticker, http), timeout=settings.agent_timeout)
        except asyncio.TimeoutError:
            return DocumentAgentOutput(ticker=ticker, error="timeout")
        except Exception as exc:
            logger.error("document_agent_error", ticker=ticker, error=str(exc))
            return DocumentAgentOutput(ticker=ticker, error=str(exc))

async def _fetch(ticker: str, http: httpx.AsyncClient) -> DocumentAgentOutput:
    clean = ticker.split(".")[0].upper()
    is_indian = any(x in ticker.upper() for x in [".NSE", ".BSE"])
    return await _eodhd_fallback(ticker, clean, http) if is_indian else await _sec_edgar(ticker, clean, http)

async def _sec_edgar(ticker: str, clean: str, http: httpx.AsyncClient) -> DocumentAgentOutput:
    headers = {"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}
    cik, company_name = await _resolve_cik(clean, http, headers)
    if not cik:
        return DocumentAgentOutput(ticker=ticker, error=f"CIK not found for {clean}")

    try:
        r = await http.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=headers)
        r.raise_for_status()
        submissions = r.json()
    except Exception as exc:
        return DocumentAgentOutput(ticker=ticker, company_name=company_name, error=str(exc))

    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    target = {"10-K", "10-Q", "8-K"}
    fetch_tasks = []
    for form, date, acc, doc in zip(forms, dates, accessions, docs):
        if form in target and len(fetch_tasks) < 4:
            acc_clean = acc.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc}"
            fetch_tasks.append((form, date, url))

    raw_texts = await asyncio.gather(
        *[_filing_text(url, http, headers) for _, _, url in fetch_tasks],
        return_exceptions=True,
    )

    filings: list[FilingExcerpt] = []
    for (form, date, url), text in zip(fetch_tasks, raw_texts):
        if isinstance(text, Exception): text = ""
        try:
            filings.append(FilingExcerpt(
                form_type=form, filed_date=date,
                excerpt=(text[:2000] if text else f"[{form} unavailable]"),
                risk_mentions=_risks(text), source_url=url,
            ))
        except Exception:
            continue
        if text:
            ingest_filing(ticker, text, {"form_type": form, "filed_date": date})

    rag_ctx = retrieve(ticker, f"investment risks and financial outlook for {clean}", top_k=4)
    all_risks = list({r for f in filings for r in f.risk_mentions})[:10]

    logger.info("document_agent_complete", ticker=ticker, filings=len(filings), rag=bool(rag_ctx))
    return DocumentAgentOutput(
        ticker=ticker, company_name=company_name or clean,
        filings=filings, rag_context=rag_ctx[:4000] if rag_ctx else None,
        management_tone=_tone(filings), key_risks_from_filings=all_risks,
    )

async def _resolve_cik(clean: str, http: httpx.AsyncClient, headers: dict) -> tuple[str | None, str | None]:
    try:
        r = await http.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
        r.raise_for_status()
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == clean:
                return str(entry["cik_str"]).zfill(10), entry.get("title")
    except Exception as exc:
        logger.warning("cik_lookup_failed", error=str(exc))
    return None, None

async def _filing_text(url: str, http: httpx.AsyncClient, headers: dict) -> str:
    try:
        r = await http.get(url, headers=headers, follow_redirects=True)
        if r.status_code != 200: return ""
        text = re.sub(r"<[^>]+>", " ", r.text)
        return re.sub(r"\s+", " ", text).strip()[:15_000]
    except Exception:
        return ""

async def _eodhd_fallback(ticker: str, clean: str, http: httpx.AsyncClient) -> DocumentAgentOutput:
    from datetime import date, timedelta
    from_date = (date.today() - timedelta(days=30)).isoformat()
    try:
        r = await http.get(
            f"https://eodhd.com/api/news?s={ticker}&offset=0&limit=10"
            f"&from={from_date}&api_token={settings.eodhd_api_key}&fmt=json"
        )
        r.raise_for_status()
        articles = r.json() or []
        filings = []
        for a in articles[:5]:
            content = a.get("content", a.get("title", ""))
            try:
                filings.append(FilingExcerpt(
                    form_type="NEWS",
                    filed_date=str(a.get("date", ""))[:10] or "2000-01-01",
                    excerpt=content[:2000],
                    risk_mentions=_risks(content),
                ))
                if content: ingest_filing(ticker, content, {"form_type": "NEWS"})
            except Exception:
                continue
        rag_ctx = retrieve(ticker, f"risks and outlook for {clean}", top_k=3)
        return DocumentAgentOutput(
            ticker=ticker, company_name=clean, filings=filings,
            rag_context=rag_ctx[:4000] if rag_ctx else None,
            management_tone=_tone(filings),
            key_risks_from_filings=list({r for f in filings for r in f.risk_mentions})[:10],
        )
    except Exception as exc:
        return DocumentAgentOutput(ticker=ticker, error=str(exc))

def _risks(text: str) -> list[str]:
    low = text.lower()
    return [k for k in _RISK_KW if k in low]

def _tone(filings: list[FilingExcerpt]) -> Sentiment:
    t = " ".join(f.excerpt for f in filings).lower()
    p = sum(t.count(w) for w in ["growth","strong","record","confident","expanding"])
    n = sum(t.count(w) for w in ["risk","decline","uncertain","challenge","loss","litigation"])
    return Sentiment.POSITIVE if p > n * 1.5 else Sentiment.NEGATIVE if n > p * 1.5 else Sentiment.NEUTRAL
