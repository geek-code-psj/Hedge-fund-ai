"""
app/agents/tools/technical_analysis.py
Computes RSI, MACD, Bollinger Bands, SMA from OHLCV price history.
Uses the `ta` library (pandas-based, no TA-Lib C dependency).
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from app.core.logging import get_logger
from app.schemas.models import (
    BollingerBands,
    MACDData,
    RSIData,
    SMAData,
    TechnicalIndicators,
    TechnicalSignal,
)

logger = get_logger(__name__)


def compute_indicators(
    price_history: list[dict],
    current_price: float,
) -> TechnicalIndicators:
    """
    Compute all technical indicators from price history.
    price_history: list of {"date": str, "close": float, "high": float, "low": float}
    Returns TechnicalIndicators with RSI, MACD, Bollinger, SMA populated.
    """
    if not price_history or len(price_history) < 20:
        logger.warning("insufficient_price_history", count=len(price_history) if price_history else 0)
        return TechnicalIndicators()

    try:
        df = pd.DataFrame(price_history)
        df = df.sort_values("date").reset_index(drop=True)
        close = df["close"].astype(float)

        rsi = _compute_rsi(close, current_price)
        macd = _compute_macd(close)
        bollinger = _compute_bollinger(close, current_price)
        sma = _compute_sma(close, current_price)

        return TechnicalIndicators(rsi=rsi, macd=macd, bollinger=bollinger, sma=sma)

    except Exception as exc:
        logger.error("technical_analysis_failed", error=str(exc))
        return TechnicalIndicators()


def _compute_rsi(close: pd.Series, current_price: float, period: int = 14) -> RSIData | None:
    try:
        import ta
        rsi_series = ta.momentum.RSIIndicator(close=close, window=period).rsi()
        rsi_value = float(rsi_series.iloc[-1])
        if pd.isna(rsi_value):
            return None
        return RSIData(value=round(rsi_value, 2), period=period)
    except Exception as exc:
        logger.warning("rsi_failed", error=str(exc))
        return None


def _compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDData | None:
    try:
        import ta
        macd_indicator = ta.trend.MACD(
            close=close, window_fast=fast, window_slow=slow, window_sign=signal
        )
        macd_val = float(macd_indicator.macd().iloc[-1])
        sig_val = float(macd_indicator.macd_signal().iloc[-1])
        hist_val = float(macd_indicator.macd_diff().iloc[-1])
        if any(pd.isna(v) for v in [macd_val, sig_val, hist_val]):
            return None
        return MACDData(
            macd_line=round(macd_val, 4),
            signal_line=round(sig_val, 4),
            histogram=round(hist_val, 4),
            signal=TechnicalSignal.NEUTRAL,
        )
    except Exception as exc:
        logger.warning("macd_failed", error=str(exc))
        return None


def _compute_bollinger(
    close: pd.Series,
    current_price: float,
    period: int = 20,
    std_dev: float = 2.0,
) -> BollingerBands | None:
    try:
        import ta
        bb = ta.volatility.BollingerBands(close=close, window=period, window_dev=std_dev)
        upper = float(bb.bollinger_hband().iloc[-1])
        middle = float(bb.bollinger_mavg().iloc[-1])
        lower = float(bb.bollinger_lband().iloc[-1])
        if any(pd.isna(v) for v in [upper, middle, lower]):
            return None
        bandwidth = (upper - lower) / middle if middle > 0 else 0
        percent_b = (current_price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
        return BollingerBands(
            upper=round(upper, 2),
            middle=round(middle, 2),
            lower=round(lower, 2),
            current_price=round(current_price, 2),
            bandwidth=round(bandwidth, 4),
            percent_b=round(percent_b, 4),
        )
    except Exception as exc:
        logger.warning("bollinger_failed", error=str(exc))
        return None


def _compute_sma(close: pd.Series, current_price: float) -> SMAData | None:
    try:
        def sma(period: int) -> float | None:
            if len(close) >= period:
                return round(float(close.rolling(window=period).mean().iloc[-1]), 2)
            return None

        return SMAData(
            sma_20=sma(20),
            sma_50=sma(50),
            sma_200=sma(200),
            current_price=round(current_price, 2),
        )
    except Exception as exc:
        logger.warning("sma_failed", error=str(exc))
        return None
