// frontend/types/index.ts
// TypeScript mirror of Python Pydantic schemas

export type Recommendation = "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL";
export type TechnicalSignal = "STRONG_BULLISH" | "BULLISH" | "NEUTRAL" | "BEARISH" | "STRONG_BEARISH";
export type Sentiment = "VERY_POSITIVE" | "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "VERY_NEGATIVE";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type TimeHorizon = "SHORT" | "MEDIUM" | "LONG";

export interface RSIData {
  value: number;
  signal: TechnicalSignal;
  period: number;
}

export interface MACDData {
  macd_line: number;
  signal_line: number;
  histogram: number;
  signal: TechnicalSignal;
}

export interface BollingerBands {
  upper: number;
  middle: number;
  lower: number;
  current_price: number;
  bandwidth: number;
  percent_b: number;
}

export interface SMAData {
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  current_price: number;
  signal: TechnicalSignal;
}

export interface TechnicalIndicators {
  rsi: RSIData | null;
  macd: MACDData | null;
  bollinger: BollingerBands | null;
  sma: SMAData | null;
  overall_technical_signal: TechnicalSignal;
}

export interface InsiderTrade {
  name: string;
  title: string;
  transaction_type: "BUY" | "SELL";
  shares: number;
  value_usd: number | null;
  filed_date: string;
}

export interface FundamentalMetrics {
  revenue_usd_m: number | null;
  revenue_growth_yoy: number | null;
  net_margin: number | null;
  debt_to_equity: number | null;
  current_ratio: number | null;
  free_cash_flow_usd_m: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  ev_ebitda: number | null;
  dividend_yield: number | null;
  enterprise_value_usd_b: number | null;
}

export interface ValuationSummary {
  methodology: string;
  target_price_usd: number;
  upside_pct: number;
  confidence: number;
}

export interface RiskFactor {
  category: string;
  description: string;
  severity: RiskLevel;
  mitigation: string | null;
}

export interface CatalystItem {
  description: string;
  timeline: TimeHorizon;
  probability: number;
}

export interface InvestmentThesis {
  ticker: string;
  company_name: string;
  analysis_date: string;
  recommendation: Recommendation;
  time_horizon: TimeHorizon;
  conviction_score: number;
  executive_summary: string;
  bull_case: string;
  bear_case: string;
  valuation: ValuationSummary;
  financials_summary: string;
  technical_summary: string;
  catalysts: CatalystItem[];
  risk_factors: RiskFactor[];
  sentiment_assessment: string;
  data_sources: string[];
  agents_used: string[];
}

// SSE event payloads
export interface SSEProgressEvent {
  session_id: string;
  step: string;
  agent: string | null;
  message: string;
  pct: number;
  timestamp: string;
}

export interface SSEAgentResultEvent {
  session_id: string;
  agent: string;
  success: boolean;
  summary: string;
  pct: number;
}

export interface SSEFinalEvent {
  session_id: string;
  thesis: InvestmentThesis;
  technical_indicators: TechnicalIndicators | null;
  cached: boolean;
  latency_ms: number;
  agents_completed: string[];
  agents_failed: string[];
}

export interface SSEErrorEvent {
  session_id: string;
  message: string;
  recoverable: boolean;
}

// Stream state machine
export type AnalysisStatus =
  | "idle"
  | "running"
  | "complete"
  | "error";

export interface AgentStatus {
  name: string;
  label: string;
  status: "pending" | "running" | "success" | "failed";
  summary: string;
  pct: number;
}

export interface AnalysisState {
  status: AnalysisStatus;
  sessionId: string | null;
  progress: number;
  currentStep: string;
  agents: Record<string, AgentStatus>;
  thesis: InvestmentThesis | null;
  technicals: TechnicalIndicators | null;
  cached: boolean;
  latencyMs: number | null;
  error: string | null;
  reasoningLog: string[];
}
