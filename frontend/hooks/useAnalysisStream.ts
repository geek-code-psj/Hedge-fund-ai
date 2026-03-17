// frontend/hooks/useAnalysisStream.ts
"use client";

import { useCallback, useRef, useState } from "react";
import type {
  AgentStatus,
  AnalysisState,
  SSEAgentResultEvent,
  SSEErrorEvent,
  SSEFinalEvent,
  SSEProgressEvent,
} from "@/types";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const INITIAL_AGENTS: Record<string, AgentStatus> = {
  news_agent: { name: "news_agent", label: "News & Sentiment", status: "pending", summary: "", pct: 0 },
  financial_data_agent: { name: "financial_data_agent", label: "Financial Data", status: "pending", summary: "", pct: 0 },
  document_agent: { name: "document_agent", label: "Document / RAG", status: "pending", summary: "", pct: 0 },
};

const DEFAULT_STATE: AnalysisState = {
  status: "idle",
  sessionId: null,
  progress: 0,
  currentStep: "",
  agents: INITIAL_AGENTS,
  thesis: null,
  technicals: null,
  cached: false,
  latencyMs: null,
  error: null,
  reasoningLog: [],
};

export function useAnalysisStream() {
  const [state, setState] = useState<AnalysisState>(DEFAULT_STATE);
  const esRef = useRef<EventSource | null>(null);

  const analyse = useCallback((ticker: string, query: string) => {
    // Close any previous stream
    esRef.current?.close();

    setState({
      ...DEFAULT_STATE,
      status: "running",
      agents: { ...INITIAL_AGENTS },
    });

    const params = new URLSearchParams({ ticker, query });
    const url = `${BACKEND}/api/v1/analyse?${params}`;
    const es = new EventSource(url);
    esRef.current = es;

    // ── progress ────────────────────────────────────────────────────────────
    es.addEventListener("progress", (e: MessageEvent) => {
      const data: SSEProgressEvent = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        progress: data.pct,
        currentStep: data.message,
        sessionId: prev.sessionId ?? data.session_id,
        reasoningLog: [...prev.reasoningLog, `[${data.pct}%] ${data.message}`],
        // Mark agent as running when its node fires
        agents: data.agent
          ? {
              ...prev.agents,
              [data.agent]: {
                ...(prev.agents[data.agent] ?? { name: data.agent, label: data.agent, summary: "", pct: 0 }),
                status: "running",
                pct: data.pct,
              },
            }
          : prev.agents,
      }));
    });

    // ── agent_result ─────────────────────────────────────────────────────────
    es.addEventListener("agent_result", (e: MessageEvent) => {
      const data: SSEAgentResultEvent = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        agents: {
          ...prev.agents,
          [data.agent]: {
            ...(prev.agents[data.agent] ?? { name: data.agent, label: data.agent }),
            status: data.success ? "success" : "failed",
            summary: data.summary,
            pct: data.pct,
          },
        },
        reasoningLog: [
          ...prev.reasoningLog,
          `${data.success ? "✅" : "⚠️"} ${data.agent}: ${data.summary}`,
        ],
      }));
    });

    // ── reasoning (token-by-token reviewer updates) ───────────────────────────
    es.addEventListener("reasoning", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        reasoningLog: [...prev.reasoningLog, `🧠 ${data.content}`],
      }));
    });

    // ── final ─────────────────────────────────────────────────────────────────
    es.addEventListener("final", (e: MessageEvent) => {
      const data: SSEFinalEvent = JSON.parse(e.data);
      setState((prev) => ({
        ...prev,
        status: "complete",
        progress: 100,
        thesis: data.thesis,
        technicals: data.technical_indicators ?? null,
        cached: data.cached,
        latencyMs: data.latency_ms,
        sessionId: data.session_id,
        reasoningLog: [
          ...prev.reasoningLog,
          `${data.cached ? "⚡ Cached" : "🔍 Fresh"} — ${data.latency_ms.toFixed(0)}ms`,
        ],
      }));
      es.close();
    });

    // ── error ─────────────────────────────────────────────────────────────────
    es.addEventListener("error", (e: MessageEvent) => {
      if (e.data) {
        const data: SSEErrorEvent = JSON.parse(e.data);
        setState((prev) => ({
          ...prev,
          status: "error",
          error: data.message,
          reasoningLog: [...prev.reasoningLog, `❌ ${data.message}`],
        }));
        if (!data.recoverable) es.close();
      }
    });

    es.onerror = () => {
      setState((prev) =>
        prev.status === "running"
          ? { ...prev, status: "error", error: "Connection lost. Please retry." }
          : prev
      );
      es.close();
    };
  }, []);

  const reset = useCallback(() => {
    esRef.current?.close();
    setState(DEFAULT_STATE);
  }, []);

  const submitFeedback = useCallback(
    async (score: number, text?: string, correction?: string) => {
      if (!state.sessionId) return;
      await fetch(`${BACKEND}/api/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          feedback_score: score,
          feedback_text: text ?? null,
          correction: correction ?? null,
        }),
      });
    },
    [state.sessionId]
  );

  return { state, analyse, reset, submitFeedback };
}
