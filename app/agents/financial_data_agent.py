"""
app/agents/financial_data_agent.py  v3
EODHD (price + history + fundamentals) + FMP (financials + insider trades)
+ Technical Indicators (RSI/MACD/Bollinger/SMA via pandas-ta)
"""
from __future__ import annotations
import asyncio
from typing import Any
import httpx
from app.agents.tools.technical_analysis import compute_indicators
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import traced
from app.schemas.models import (
    FinancialDataAgentOutput, FundamentalMetrics, InsiderTrade
)

logger = get_logger(__name__)
settings = get_settings()


async def run(ticker: str, http: httpx.AsyncClient) -> FinancialDataAgentOutput:
    async with traced("financial_data_agent", ticker=ticker):
        try:
            return await asyncio.wait_for(
                _fetch_all(ticker, http), timeout=settings.agent_timeout
            )
        except asyncio.TimeoutError:
            return FinancialDataAgentOutput(ticker=ticker, error="timeout")
        except Exception as exc:
            logger.error("financial_agent_error", ticker=ticker, error=str(exc))
            return FinancialDataAgentOutput(ticker=ticker, error=str(exc))


async def _fetch_all(ticker: str, http: httpx.AsyncClient) -> FinancialDataAgentOutput:
    eod, fmp, insiders = await asyncio.gather(
        _fetch_eodhd(ticker, http),
        _fetch_fmp(ticker, http),
        _fetch_insiders(ticker, http),
        return_exceptions=True,
    )
    eod = eod if isinstance(eod, dict) else {}
    fmp = fmp if isinstance(fmp, dict) else {}
    insiders = insiders if isinstance(insiders, list) else []

    current_price = float(eod.get("close") or 0) or None

    # Technical indicators
    technicals = None
    if eod.get("price_history") and current_price:
        technicals = compute_indicators(eod["price_history"], current_price)

    # Fundamental metrics
    fundamentals = None
    try:
        fundamentals = FundamentalMetrics(
            revenue_usd_m=_m(fmp.get("revenue")),
            revenue_growth_yoy=fmp.get("revenue_growth_yoy"),
            net_margin=fmp.get("net_margin"),
            debt_to_equity=_ratio(fmp.get("total_debt"), fmp.get("total_equity")),
            current_ratio=_ratio(fmp.get("current_assets"), fmp.get("current_liabilities")),
            free_cash_flow_usd_m=_m(fmp.get("free_cash_flow")),
            pe_ratio=eod.get("pe_ratio"),
            pb_ratio=eod.get("pb_ratio"),
            ev_ebitda=eod.get("ev_ebitda"),
            dividend_yield=eod.get("dividend_yield"),
            enterprise_value_usd_b=_b(eod.get("market_cap")),
        )
    except Exception as exc:
        logger.warning("fundamentals_parse_failed", error=str(exc))

    # Insider trades
    parsed_insiders = []
    for t in insiders[:10]:
        try:
            parsed_insiders.append(InsiderTrade(
                name=t.get("reportingName", "Unknown"),
                title=t.get("officerTitle", ""),
                transaction_type="BUY" if (t.get("transactionShares") or 0) > 0 else "SELL",
                shares=abs(int(t.get("transactionShares") or 0)),
                value_usd=t.get("transactionPrice"),
                filed_date=str(t.get("filingDate", ""))[:10],
            ))
        except Exception:
            continue

    return FinancialDataAgentOutput(
        ticker=ticker,
        current_price=current_price,
        high_52w=eod.get("high_52w"),
        low_52w=eod.get("low_52w"),
        market_cap_usd_b=_b(eod.get("market_cap")),
        sector=eod.get("sector"),
        industry=eod.get("industry"),
        fundamentals=fundamentals,
        technicals=technicals,
        insider_trades=parsed_insiders,
    )


async def _fetch_eodhd(ticker: str, http: httpx.AsyncClient) -> dict[str, Any]:
    from datetime import date, timedelta
    symbol = ticker if "." in ticker else f"{ticker}.US"
    from_date = (date.today() - timedelta(days=365)).isoformat()
    r = await http.get(
        f"https://eodhd.com/api/eod/{symbol}"
        f"?api_token={settings.eodhd_api_key}&fmt=json&from={from_date}"
    )
    r.raise_for_status()
    data = r.json() or []
    if not data:
        return {}

    latest = data[-1]
    closes = [float(d["close"]) for d in data if d.get("close")]
    fund: dict = {}
    try:
        fr = await http.get(
            f"https://eodhd.com/api/fundamentals/{symbol}"
            f"?api_token={settings.eodhd_api_key}&fmt=json"
        )
        if fr.status_code == 200:
            raw = fr.json()
            fund = {
                "pe_ratio": raw.get("Highlights", {}).get("PERatio"),
                "pb_ratio": raw.get("Valuation", {}).get("PriceBookMRQ"),
                "ev_ebitda": raw.get("Valuation", {}).get("EnterpriseValueEbitda"),
                "market_cap": raw.get("Highlights", {}).get("MarketCapitalization"),
                "dividend_yield": raw.get("Highlights", {}).get("DividendYield"),
                "sector": raw.get("General", {}).get("Sector"),
                "industry": raw.get("General", {}).get("Industry"),
            }
    except Exception:
        pass

    return {
        "close": latest.get("close"),
        "high_52w": max(closes) if closes else None,
        "low_52w": min(closes) if closes else None,
        "price_history": [
            {"date": d["date"], "close": d.get("close", 0),
             "high": d.get("high", 0), "low": d.get("low", 0)}
            for d in data
        ],
        **fund,
    }


async def _fetch_fmp(ticker: str, http: httpx.AsyncClient) -> dict[str, Any]:
    base = f"https://financialmodelingprep.com/api/v3"
    key = settings.fmp_api_key

    async def get(path: str):
        r = await http.get(f"{base}{path}&apikey={key}")
        r.raise_for_status()
        return r.json() or []

    income, balance, cashflow = await asyncio.gather(
        get(f"/income-statement/{ticker}?period=quarter&limit=4"),
        get(f"/balance-sheet-statement/{ticker}?period=quarter&limit=4"),
        get(f"/cash-flow-statement/{ticker}?period=quarter&limit=4"),
        return_exceptions=True,
    )
    income = income if isinstance(income, list) else []
    balance = balance if isinstance(balance, list) else []
    cashflow = cashflow if isinstance(cashflow, list) else []

    li, pi = (income[0] if income else {}), (income[1] if len(income) > 1 else {})
    lb = balance[0] if balance else {}
    lc = cashflow[0] if cashflow else {}
    rev_now, rev_prev = li.get("revenue") or 0, pi.get("revenue") or 1
    return {
        "revenue": rev_now,
        "revenue_growth_yoy": (rev_now - rev_prev) / abs(rev_prev) if rev_prev else None,
        "net_margin": li.get("netIncomeRatio"),
        "total_debt": lb.get("totalDebt"),
        "total_equity": lb.get("totalStockholdersEquity"),
        "current_assets": lb.get("totalCurrentAssets"),
        "current_liabilities": lb.get("totalCurrentLiabilities"),
        "free_cash_flow": lc.get("freeCashFlow"),
    }


async def _fetch_insiders(ticker: str, http: httpx.AsyncClient) -> list[dict]:
    try:
        r = await http.get(
            f"https://financialmodelingprep.com/api/v4/insider-trading"
            f"?symbol={ticker}&limit=20&apikey={settings.fmp_api_key}"
        )
        r.raise_for_status()
        return r.json() or []
    except Exception:
        return []


def _m(v) -> float | None:
    try: return round(float(v) / 1e6, 2) if v else None
    except: return None

def _b(v) -> float | None:
    try: return round(float(v) / 1e9, 3) if v else None
    except: return None

def _ratio(n, d) -> float | None:
    try:
        if n and d and float(d) != 0:
            return round(float(n) / float(d), 4)
    except: pass
    return None
