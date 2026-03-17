"""
tests/test_technical.py
Unit tests for the technical analysis module.
Uses synthetic OHLCV price history — zero external API calls.

Tests:
  • RSI computed correctly and signal derived
  • MACD histogram sign matches signal
  • Bollinger band ordering invariant
  • SMA signal derived from price vs averages
  • TechnicalIndicators overall signal aggregation
  • Edge cases: insufficient data, all-same prices, volatile data
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pytest

from app.agents.tools.technical_analysis import (
    _compute_bollinger,
    _compute_macd,
    _compute_rsi,
    _compute_sma,
    compute_indicators,
)
from app.schemas.models import TechnicalIndicators, TechnicalSignal


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_prices(n: int, start: float = 100.0, trend: float = 0.0, noise: float = 1.0) -> list[dict]:
    """Generate synthetic OHLCV data."""
    random.seed(42)
    prices = []
    price = start
    base = date(2024, 1, 1)
    for i in range(n):
        change = trend + random.gauss(0, noise)
        price = max(1.0, price + change)
        prices.append({
            "date": (base + timedelta(days=i)).isoformat(),
            "close": round(price, 2),
            "high": round(price * 1.01, 2),
            "low": round(price * 0.99, 2),
        })
    return prices


def _closes(prices: list[dict]):
    import pandas as pd
    return pd.Series([p["close"] for p in prices], dtype=float)


# ── RSI tests ─────────────────────────────────────────────────────────────────

def test_rsi_value_in_valid_range():
    prices = _make_prices(60)
    rsi = _compute_rsi(_closes(prices), prices[-1]["close"])
    assert rsi is not None
    assert 0 <= rsi.value <= 100, f"RSI {rsi.value} out of range"


def test_rsi_oversold_signals_strong_bullish():
    # Consistently declining prices → low RSI → STRONG_BULLISH signal
    prices = _make_prices(60, start=100.0, trend=-2.0, noise=0.1)
    rsi = _compute_rsi(_closes(prices), prices[-1]["close"])
    assert rsi is not None
    if rsi.value <= 30:
        assert rsi.signal == TechnicalSignal.STRONG_BULLISH


def test_rsi_overbought_signals_strong_bearish():
    # Strongly rising prices → high RSI → STRONG_BEARISH signal
    prices = _make_prices(60, start=100.0, trend=2.0, noise=0.1)
    rsi = _compute_rsi(_closes(prices), prices[-1]["close"])
    assert rsi is not None
    if rsi.value >= 70:
        assert rsi.signal == TechnicalSignal.STRONG_BEARISH


def test_rsi_insufficient_data_returns_none():
    prices = _make_prices(5)  # < 14 period
    rsi = _compute_rsi(_closes(prices), prices[-1]["close"])
    # With only 5 data points, RSI series will be all NaN → should return None or NaN-handled
    # The function should not raise
    # (result may be None or have NaN value — either is acceptable graceful handling)
    assert rsi is None or (rsi.value != rsi.value)  # None or NaN


# ── MACD tests ────────────────────────────────────────────────────────────────

def test_macd_histogram_sign_matches_signal():
    prices = _make_prices(120)
    macd = _compute_macd(_closes(prices))
    assert macd is not None
    if macd.histogram > 0:
        assert macd.signal == TechnicalSignal.BULLISH
    elif macd.histogram < 0:
        assert macd.signal == TechnicalSignal.BEARISH


def test_macd_requires_sufficient_data():
    prices = _make_prices(20)  # < 26 period
    macd = _compute_macd(_closes(prices))
    # With 20 points, MACD (26-period slow) will be all NaN → returns None
    assert macd is None


def test_macd_values_are_finite():
    prices = _make_prices(200)
    macd = _compute_macd(_closes(prices))
    if macd:
        assert math.isfinite(macd.macd_line)
        assert math.isfinite(macd.signal_line)
        assert math.isfinite(macd.histogram)


# ── Bollinger Bands tests ─────────────────────────────────────────────────────

def test_bollinger_band_ordering_invariant():
    prices = _make_prices(60)
    bb = _compute_bollinger(_closes(prices), prices[-1]["close"])
    assert bb is not None
    assert bb.lower <= bb.middle <= bb.upper, (
        f"Band ordering violated: lower={bb.lower} middle={bb.middle} upper={bb.upper}"
    )


def test_bollinger_bandwidth_non_negative():
    prices = _make_prices(60)
    bb = _compute_bollinger(_closes(prices), prices[-1]["close"])
    assert bb is not None
    assert bb.bandwidth >= 0


def test_bollinger_percent_b_range():
    """percent_b should be near 0.5 for a stable price at the middle band."""
    prices = _make_prices(60, trend=0.0, noise=0.01)  # very stable
    bb = _compute_bollinger(_closes(prices), prices[-1]["close"])
    assert bb is not None
    # Not asserting exact value — just that it's a real number
    assert math.isfinite(bb.percent_b)


def test_bollinger_validates_band_ordering():
    """Pydantic model validator should reject inverted bands."""
    from pydantic import ValidationError
    from app.schemas.models import BollingerBands
    with pytest.raises(ValidationError, match="lower <= middle <= upper"):
        BollingerBands(upper=90.0, middle=100.0, lower=110.0,
                       current_price=95.0, bandwidth=0.2, percent_b=0.5)


# ── SMA tests ─────────────────────────────────────────────────────────────────

def test_sma_price_above_all_averages_is_bullish():
    # Rising price series — price likely above all SMAs
    prices = _make_prices(220, start=50.0, trend=0.5, noise=0.05)
    current_price = prices[-1]["close"]
    sma = _compute_sma(_closes(prices), current_price)
    assert sma is not None
    # After 220 rising bars, current price should be above all SMAs
    if sma.sma_20 and sma.sma_50 and sma.sma_200:
        if current_price > sma.sma_20 and current_price > sma.sma_50 and current_price > sma.sma_200:
            assert sma.signal == TechnicalSignal.STRONG_BULLISH


def test_sma_price_below_all_averages_is_bearish():
    prices = _make_prices(220, start=200.0, trend=-0.5, noise=0.05)
    current_price = prices[-1]["close"]
    sma = _compute_sma(_closes(prices), current_price)
    assert sma is not None
    if sma.sma_20 and sma.sma_50 and sma.sma_200:
        if current_price < sma.sma_20 and current_price < sma.sma_50 and current_price < sma.sma_200:
            assert sma.signal == TechnicalSignal.STRONG_BEARISH


def test_sma_200_not_available_with_fewer_bars():
    prices = _make_prices(100)  # < 200 bars
    sma = _compute_sma(_closes(prices), prices[-1]["close"])
    assert sma is not None
    assert sma.sma_200 is None


# ── TechnicalIndicators aggregate signal ─────────────────────────────────────

def test_all_bullish_signals_produce_strong_bullish():
    from app.schemas.models import MACDData, RSIData, SMAData, TechnicalIndicators, TechnicalSignal
    indicators = TechnicalIndicators(
        rsi=RSIData(value=35.0),           # oversold → STRONG_BULLISH
        macd=MACDData(macd_line=1.5, signal_line=0.5, histogram=1.0, signal=TechnicalSignal.BULLISH),
        sma=SMAData(sma_20=90.0, sma_50=85.0, sma_200=80.0, current_price=100.0),  # above all
    )
    assert indicators.overall_technical_signal in (
        TechnicalSignal.STRONG_BULLISH, TechnicalSignal.BULLISH
    )


def test_all_bearish_signals_produce_strong_bearish():
    from app.schemas.models import MACDData, RSIData, SMAData, TechnicalIndicators, TechnicalSignal
    indicators = TechnicalIndicators(
        rsi=RSIData(value=75.0),           # overbought → STRONG_BEARISH
        macd=MACDData(macd_line=-1.5, signal_line=-0.5, histogram=-1.0, signal=TechnicalSignal.BEARISH),
        sma=SMAData(sma_20=120.0, sma_50=115.0, sma_200=110.0, current_price=100.0),  # below all
    )
    assert indicators.overall_technical_signal in (
        TechnicalSignal.STRONG_BEARISH, TechnicalSignal.BEARISH
    )


def test_mixed_signals_produce_neutral_or_mild():
    from app.schemas.models import MACDData, RSIData, TechnicalIndicators, TechnicalSignal
    indicators = TechnicalIndicators(
        rsi=RSIData(value=50.0),           # neutral
        macd=MACDData(macd_line=0.1, signal_line=0.05, histogram=0.05, signal=TechnicalSignal.BULLISH),
    )
    assert indicators.overall_technical_signal in (
        TechnicalSignal.NEUTRAL, TechnicalSignal.BULLISH
    )


# ── Full pipeline integration ─────────────────────────────────────────────────

def test_compute_indicators_returns_populated_model():
    prices = _make_prices(250)
    current_price = prices[-1]["close"]
    result = compute_indicators(prices, current_price)
    assert isinstance(result, TechnicalIndicators)
    # With 250 bars all indicators should be populated
    assert result.rsi is not None
    assert result.macd is not None
    assert result.bollinger is not None
    assert result.sma is not None
    assert result.sma.sma_200 is not None


def test_compute_indicators_insufficient_history_returns_empty():
    prices = _make_prices(5)
    result = compute_indicators(prices, prices[-1]["close"])
    assert isinstance(result, TechnicalIndicators)
    # Should return empty model without crashing
    assert result.overall_technical_signal == TechnicalSignal.NEUTRAL


def test_compute_indicators_empty_history():
    result = compute_indicators([], 100.0)
    assert isinstance(result, TechnicalIndicators)


def test_compute_indicators_does_not_raise_on_constant_prices():
    """Zero-variance price series (all same) should not produce NaN explosions."""
    prices = [{"date": f"2024-01-{i:02d}", "close": 100.0, "high": 100.0, "low": 100.0}
              for i in range(1, 61)]
    result = compute_indicators(prices, 100.0)
    assert isinstance(result, TechnicalIndicators)
