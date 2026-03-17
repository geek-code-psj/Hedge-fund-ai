"""
app/schemas/models.py  v3.0
Complete Pydantic contracts:
  • LangGraph AgentState TypedDict
  • Technical indicators (RSI, MACD, Bollinger, SMA)
  • Agent outputs (News, FinancialData, Document)
  • InvestmentThesis — frozen, validated LLM output contract
  • Memory / Experience Bank
  • SSE wire protocol events
  • API request/response shapes
"""
from __future__ import annotations

import operator
import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class Sentiment(str, Enum):
    VERY_POSITIVE = "VERY_POSITIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    VERY_NEGATIVE = "VERY_NEGATIVE"

class Recommendation(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class TimeHorizon(str, Enum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"

class TechnicalSignal(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


# ─── LangGraph State ──────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    """Typed state object threaded through all LangGraph nodes."""
    ticker: str
    user_query: str
    session_id: str
    news_output: dict | None
    financial_output: dict | None
    document_output: dict | None
    aggregated_research: dict | None
    compressed_research: str  # Token-optimized context for LLM
    memory_context: str | None
    memory_note: str | None
    thesis: dict | None
    # Use Annotated with operator.add for concurrent list updates (fan-out nodes)
    # This allows parallel nodes to update without "Can receive only one value per step" error
    agents_completed: Annotated[list[str], operator.add]
    agents_failed: Annotated[list[str], operator.add]
    human_feedback_required: bool
    human_correction: dict | None
    error: str | None
    reviewer_retries: int


# ─── Technical Indicators ─────────────────────────────────────────────────────

class RSIData(BaseModel):
    value: float = Field(..., ge=0, le=100)
    signal: TechnicalSignal = TechnicalSignal.NEUTRAL
    period: int = 14

    @model_validator(mode="after")
    def derive_signal(self) -> "RSIData":
        if self.value >= 70:
            self.signal = TechnicalSignal.STRONG_BEARISH
        elif self.value >= 60:
            self.signal = TechnicalSignal.BEARISH
        elif self.value <= 30:
            self.signal = TechnicalSignal.STRONG_BULLISH
        elif self.value <= 40:
            self.signal = TechnicalSignal.BULLISH
        else:
            self.signal = TechnicalSignal.NEUTRAL
        return self


class MACDData(BaseModel):
    macd_line: float
    signal_line: float
    histogram: float
    signal: TechnicalSignal = TechnicalSignal.NEUTRAL

    @model_validator(mode="after")
    def derive_signal(self) -> "MACDData":
        if self.histogram > 0 and self.macd_line > self.signal_line:
            self.signal = TechnicalSignal.BULLISH
        elif self.histogram > 0:
            self.signal = TechnicalSignal.BULLISH
        elif self.histogram < 0 and self.macd_line < self.signal_line:
            self.signal = TechnicalSignal.BEARISH
        else:
            self.signal = TechnicalSignal.BEARISH
        return self


class BollingerBands(BaseModel):
    upper: float = Field(gt=0)
    middle: float = Field(gt=0)
    lower: float = Field(gt=0)
    current_price: float = Field(gt=0)
    bandwidth: float = Field(ge=0)
    percent_b: float

    @model_validator(mode="after")
    def validate_band_order(self) -> "BollingerBands":
        if not (self.lower <= self.middle <= self.upper):
            raise ValueError("Bollinger bands must satisfy: lower <= middle <= upper")
        return self


class SMAData(BaseModel):
    sma_20: float | None = Field(None, gt=0)
    sma_50: float | None = Field(None, gt=0)
    sma_200: float | None = Field(None, gt=0)
    current_price: float = Field(gt=0)
    signal: TechnicalSignal = TechnicalSignal.NEUTRAL

    @model_validator(mode="after")
    def derive_signal(self) -> "SMAData":
        above = sum(1 for s in [self.sma_20, self.sma_50, self.sma_200]
                    if s and self.current_price > s)
        if above == 3:
            self.signal = TechnicalSignal.STRONG_BULLISH
        elif above == 2:
            self.signal = TechnicalSignal.BULLISH
        elif above == 0:
            self.signal = TechnicalSignal.STRONG_BEARISH
        elif above == 1:
            self.signal = TechnicalSignal.BEARISH
        return self


class TechnicalIndicators(BaseModel):
    rsi: RSIData | None = None
    macd: MACDData | None = None
    bollinger: BollingerBands | None = None
    sma: SMAData | None = None
    overall_technical_signal: TechnicalSignal = TechnicalSignal.NEUTRAL

    @model_validator(mode="after")
    def compute_overall(self) -> "TechnicalIndicators":
        score_map = {
            TechnicalSignal.STRONG_BULLISH: 2,
            TechnicalSignal.BULLISH: 1,
            TechnicalSignal.NEUTRAL: 0,
            TechnicalSignal.BEARISH: -1,
            TechnicalSignal.STRONG_BEARISH: -2,
        }
        signals = [s for s in [
            self.rsi.signal if self.rsi else None,
            self.macd.signal if self.macd else None,
            self.sma.signal if self.sma else None,
        ] if s]
        if not signals:
            return self
        avg = sum(score_map[s] for s in signals) / len(signals)
        if avg >= 1.5:
            self.overall_technical_signal = TechnicalSignal.STRONG_BULLISH
        elif avg >= 0.5:
            self.overall_technical_signal = TechnicalSignal.BULLISH
        elif avg <= -1.5:
            self.overall_technical_signal = TechnicalSignal.STRONG_BEARISH
        elif avg <= -0.5:
            self.overall_technical_signal = TechnicalSignal.BEARISH
        return self


# ─── Agent outputs ────────────────────────────────────────────────────────────

class NewsItem(BaseModel):
    headline: str = Field(max_length=300)
    source: str
    published_at: str
    relevance_score: Annotated[float, Field(ge=0.0, le=1.0)]


class NewsAgentOutput(BaseModel):
    ticker: str
    headline_count: int = Field(ge=0)
    sentiment: Sentiment = Sentiment.NEUTRAL
    sentiment_score: Annotated[float, Field(ge=-1.0, le=1.0)] = 0.0
    top_headlines: list[NewsItem] = Field(default_factory=list, max_length=10)
    key_themes: list[str] = Field(default_factory=list, max_length=8)
    agent: str = "news_agent"
    error: str | None = None


class InsiderTrade(BaseModel):
    name: str
    title: str
    transaction_type: str
    shares: int = Field(ge=0)
    value_usd: float | None = None
    filed_date: str


class FundamentalMetrics(BaseModel):
    revenue_usd_m: float | None = None
    revenue_growth_yoy: float | None = None
    net_margin: float | None = Field(None, ge=-5.0, le=1.0)
    debt_to_equity: float | None = Field(None, ge=0)
    current_ratio: float | None = Field(None, gt=0)
    free_cash_flow_usd_m: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = Field(None, ge=0)
    enterprise_value_usd_b: float | None = None

    @field_validator("revenue_growth_yoy", mode="before")
    @classmethod
    def growth_bounds(cls, v):
        if v is not None and not (-2.0 <= float(v) <= 10.0):
            raise ValueError(f"revenue_growth_yoy={v} outside [-200%, +1000%]")
        return v


class FinancialDataAgentOutput(BaseModel):
    ticker: str
    current_price: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    market_cap_usd_b: float | None = None
    sector: str | None = None
    industry: str | None = None
    fundamentals: FundamentalMetrics | None = None
    technicals: TechnicalIndicators | None = None
    insider_trades: list[InsiderTrade] = Field(default_factory=list, max_length=10)
    agent: str = "financial_data_agent"
    error: str | None = None


class FilingExcerpt(BaseModel):
    form_type: str
    filed_date: str
    excerpt: str = Field(max_length=2000)
    risk_mentions: list[str] = Field(default_factory=list, max_length=10)
    source_url: str | None = None


class DocumentAgentOutput(BaseModel):
    ticker: str
    company_name: str | None = None
    filings: list[FilingExcerpt] = Field(default_factory=list, max_length=5)
    rag_context: str | None = Field(None, max_length=4000)
    management_tone: Sentiment | None = None
    key_risks_from_filings: list[str] = Field(default_factory=list, max_length=10)
    agent: str = "document_agent"
    error: str | None = None


class AggregatedResearch(BaseModel):
    ticker: str
    user_query: str
    news: NewsAgentOutput | None = None
    financial_data: FinancialDataAgentOutput | None = None
    documents: DocumentAgentOutput | None = None
    memory_context: str | None = None
    agents_completed: list[str] = Field(default_factory=list)
    agents_failed: list[str] = Field(default_factory=list)


# ─── Investment Thesis ────────────────────────────────────────────────────────

class RiskFactor(BaseModel):
    category: str = Field(max_length=80)
    description: str = Field(max_length=600)
    severity: RiskLevel
    mitigation: str | None = Field(None, max_length=300)


class CatalystItem(BaseModel):
    description: str = Field(max_length=400)
    timeline: TimeHorizon
    probability: Annotated[float, Field(ge=0.0, le=1.0)]


class ValuationSummary(BaseModel):
    methodology: str = Field(max_length=100)
    target_price_usd: float = Field(gt=0)
    upside_pct: float
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class InvestmentThesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    company_name: str
    analysis_date: str

    recommendation: Recommendation
    time_horizon: TimeHorizon
    conviction_score: Annotated[float, Field(ge=0.0, le=1.0)]

    executive_summary: str = Field(min_length=150, max_length=1500)
    bull_case: str = Field(min_length=60, max_length=700)
    bear_case: str = Field(min_length=60, max_length=700)

    valuation: ValuationSummary
    financials_summary: str = Field(min_length=50, max_length=600)
    technical_summary: str = Field(min_length=30, max_length=400)

    catalysts: list[CatalystItem] = Field(min_length=1, max_length=6)
    risk_factors: list[RiskFactor] = Field(min_length=1, max_length=8)
    sentiment_assessment: str = Field(min_length=30, max_length=400)

    data_sources: list[str] = Field(min_length=1)
    agents_used: list[str] = Field(min_length=1)

    @field_validator("ticker", mode="before")
    @classmethod
    def upper_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("analysis_date", mode="before")
    @classmethod
    def iso_date(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(f"analysis_date must be YYYY-MM-DD, got: {v}")
        return v

    @model_validator(mode="after")
    def conviction_guard(self) -> "InvestmentThesis":
        if self.recommendation in (Recommendation.STRONG_BUY, Recommendation.STRONG_SELL):
            if self.conviction_score < 0.75:
                raise ValueError(
                    f"{self.recommendation} requires conviction_score >= 0.75, "
                    f"got {self.conviction_score:.2f}"
                )
        return self

    @model_validator(mode="after")
    def bull_bear_differ(self) -> "InvestmentThesis":
        shared = set(self.bull_case.split()) & set(self.bear_case.split())
        total = set(self.bull_case.split()) | set(self.bear_case.split())
        if total and len(shared) / len(total) > 0.85:
            raise ValueError("bull_case and bear_case are >85% identical")
        return self


# ─── Memory / Experience Bank ─────────────────────────────────────────────────

class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    ticker: str
    entry_type: str  # "correction" | "preference" | "feedback"
    content: str = Field(max_length=2000)
    embedding_text: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─── SSE protocol ─────────────────────────────────────────────────────────────

class SSEProgressEvent(BaseModel):
    session_id: str
    step: str
    agent: str | None = None
    message: str
    pct: int = Field(ge=0, le=100)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SSEAgentResultEvent(BaseModel):
    session_id: str
    agent: str
    success: bool
    summary: str
    data: dict | None = None
    pct: int


class SSEFinalEvent(BaseModel):
    session_id: str
    thesis: InvestmentThesis
    technical_indicators: TechnicalIndicators | None = None
    cached: bool
    latency_ms: float
    agents_completed: list[str]
    agents_failed: list[str]


class SSEHumanReviewEvent(BaseModel):
    session_id: str
    message: str = "Human review required before synthesis"
    research_summary: dict


class SSEErrorEvent(BaseModel):
    session_id: str
    message: str
    recoverable: bool = False


# ─── API contracts ────────────────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    ticker: str = Field(..., max_length=20)
    query: str = Field(
        default="Provide a comprehensive investment thesis with buy/sell recommendation.",
        max_length=500,
    )
    enable_human_review: bool = False


class FeedbackRequest(BaseModel):
    session_id: str
    feedback_score: int = Field(ge=1, le=5)
    feedback_text: str | None = Field(None, max_length=2000)
    correction: str | None = Field(None, max_length=2000)


class UserFeedback(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    ticker: str
    original_query: str
    retrieved_context: str
    model_output: str
    feedback_score: int = Field(ge=1, le=5)
    feedback_text: str | None = None
    correction: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
