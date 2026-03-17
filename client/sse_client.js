/**
 * client/sse_client.js
 * Browser-side SSE consumer for the Hedge Fund AI streaming API.
 *
 * Event types received:
 *   progress      → { session_id, step, agent, message, pct, timestamp }
 *   agent_result  → { session_id, agent, success, summary, pct }
 *   final         → { session_id, thesis, cached, latency_ms, agents_completed, agents_failed }
 *   error         → { session_id, message, recoverable }
 */

class HedgeFundAnalysisClient {
  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl;
    this.es = null;
  }

  /**
   * Stream an analysis for a given ticker.
   * @param {string} ticker       e.g. "AAPL" or "RELIANCE.NSE"
   * @param {string} query        Natural language question
   * @param {object} handlers     { onProgress, onAgentResult, onFinal, onError, onComplete }
   * @returns {string}            session_id
   */
  analyse(ticker, query, handlers = {}) {
    const sessionId = crypto.randomUUID();
    const params = new URLSearchParams({
      ticker,
      query,
      session_id: sessionId,
    });

    const url = `${this.baseUrl}/api/v1/analyse?${params}`;
    this.es = new EventSource(url);

    // ── Progress events ──────────────────────────────────────────────────────
    this.es.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data);
      console.log(`[${data.pct}%] ${data.message}`);
      handlers.onProgress?.(data);
    });

    // ── Agent result events ──────────────────────────────────────────────────
    this.es.addEventListener("agent_result", (e) => {
      const data = JSON.parse(e.data);
      const icon = data.success ? "✅" : "⚠️";
      console.log(`${icon} ${data.agent}: ${data.summary}`);
      handlers.onAgentResult?.(data);
    });

    // ── Final event ───────────────────────────────────────────────────────────
    this.es.addEventListener("final", (e) => {
      const data = JSON.parse(e.data);
      const tag = data.cached ? "⚡ CACHED" : "🔍 FRESH";
      console.log(`${tag} Analysis complete in ${data.latency_ms.toFixed(0)}ms`);
      console.log(`Recommendation: ${data.thesis.recommendation}`);
      console.log(`Conviction: ${(data.thesis.conviction_score * 100).toFixed(0)}%`);
      handlers.onFinal?.(data);
      this.es.close();
      handlers.onComplete?.();
    });

    // ── Error events ─────────────────────────────────────────────────────────
    this.es.addEventListener("error", (e) => {
      if (e.data) {
        const data = JSON.parse(e.data);
        console.error(`Error: ${data.message}`);
        handlers.onError?.(data);
      }
      if (!e.data || !JSON.parse(e.data).recoverable) {
        this.es.close();
      }
    });

    return sessionId;
  }

  /** Submit user feedback (1–5) after receiving a final analysis. */
  async submitFeedback(sessionId, score, text = null) {
    const resp = await fetch(`${this.baseUrl}/api/v1/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        feedback_score: score,
        feedback_text: text,
      }),
    });
    if (!resp.ok) throw new Error(`Feedback failed: ${resp.statusText}`);
    return resp.json();
  }

  close() {
    this.es?.close();
  }
}

// ── Example usage ─────────────────────────────────────────────────────────────

const client = new HedgeFundAnalysisClient();

const sessionId = client.analyse(
  "AAPL",
  "Should I invest in Apple for a 12-month horizon?",
  {
    onProgress: ({ pct, message, agent }) => {
      document.querySelector("#progress-bar").style.width = `${pct}%`;
      document.querySelector("#status").textContent = message;
    },

    onAgentResult: ({ agent, success, summary }) => {
      const row = document.querySelector(`#agent-${agent}`);
      if (row) {
        row.querySelector(".status").textContent = success ? "✅" : "⚠️";
        row.querySelector(".summary").textContent = summary;
      }
    },

    onFinal: ({ thesis, cached, latency_ms }) => {
      renderThesis(thesis);
      document.querySelector("#latency").textContent =
        `${cached ? "⚡ Cached" : "🔍 Live"} — ${latency_ms.toFixed(0)}ms`;
    },

    onError: ({ message }) => {
      document.querySelector("#error-banner").textContent = message;
      document.querySelector("#error-banner").hidden = false;
    },
  }
);

function renderThesis(thesis) {
  document.querySelector("#recommendation").textContent = thesis.recommendation;
  document.querySelector("#target-price").textContent =
    `$${thesis.valuation.target_price_usd.toFixed(2)}`;
  document.querySelector("#conviction").textContent =
    `${(thesis.conviction_score * 100).toFixed(0)}%`;
  document.querySelector("#summary").textContent = thesis.executive_summary;
  document.querySelector("#bull-case").textContent = thesis.bull_case;
  document.querySelector("#bear-case").textContent = thesis.bear_case;
}

export { HedgeFundAnalysisClient };
