# Hedge Fund AI — v3

**Production-ready multi-agent AI financial analysis platform** simulating a hedge-fund research workflow. Three concurrent AI agents feed a Generator-Critic LLM reviewer, streaming live to a Next.js glass-window dashboard via Server-Sent Events.

---

## Architecture

```
Browser (Next.js 15)
  └── EventSource → GET /api/v1/analyse
         │
         ▼
   FastAPI (SSE StreamingResponse)
         │
         ▼
   ┌─────────────────────────────────────────────┐
   │        LangGraph Directed Graph              │
   │                                              │
   │  START → orchestrator_node                   │
   │    (injects vector memory context)           │
   │         │                                    │
   │    ┌────┴────┬──────────────┐ fan-out        │
   │    ▼         ▼              ▼                 │
   │ news_node  financial_node  document_node      │
   │ Finnhub    EODHD+FMP       SEC EDGAR+RAG      │
   │ sentiment  RSI/MACD/BB/SMA ChromaDB           │
   │ weighting  insiders        semantic search    │
   │    │         │              │  fan-in         │
   │    └────┬────┴──────────────┘                 │
   │         ▼                                    │
   │   aggregator_node (merges all outputs)        │
   │         │                                    │
   │         ▼                                    │
   │   reviewer_node                              │
   │   ┌──────────────────────────────────┐       │
   │   │ Generator: Instructor + OpenAI   │       │
   │   │ Critic:    Consistency scorer    │       │
   │   │ Retry:     Tenacity exp backoff  │       │
   │   └──────────────────────────────────┘       │
   │         │                                    │
   │   conditional edge: pass → END               │
   │                      fail → retry (max 3)    │
   └─────────────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────┐
    │  RedisVL cache  │  Neon DB  │ ChromaDB  │
    │  (cos-sim TTL)  │ (sessions)│ (memory)  │
    └────────────────────────────────────────┘
         │
   Arize Phoenix (local Docker — MNPI-safe)
```

---

## Features

| Layer | Technology | Free? |
|-------|-----------|-------|
| Orchestration | LangGraph directed graph | ✅ |
| Agents | News (Finnhub), Financial (EODHD + FMP), Document (SEC EDGAR) | ✅ |
| Technical Analysis | RSI, MACD, Bollinger Bands, SMA via `ta` library | ✅ |
| Insider Tracking | FMP insider transactions API | ✅ |
| RAG Pipeline | ChromaDB + sentence-transformers | ✅ |
| LLM Reviewer | GPT-4o-mini + Instructor + Generator-Critic | ~$0.01/query |
| Semantic Cache | RedisVL cosine similarity, 15-min TTL | ✅ |
| Vector Memory | ChromaDB persistent experience bank | ✅ |
| Observability | Arize Phoenix (local Docker) | ✅ |
| Feedback Loop | Neon PostgreSQL + Experience Bank | ✅ |
| Frontend | Next.js 15, shadcn/ui, framer-motion, Recharts | ✅ |

---

## Quick Start

### 1. One-command setup

```bash
git clone https://github.com/yourorg/hedge-fund-ai
cd hedge-fund-ai
bash scripts/setup.sh
```

### 2. Add API keys

```bash
# Required
OPENAI_API_KEY=sk-...

# Free tier keys (optional — demo keys work for testing)
EODHD_API_KEY=demo
FMP_API_KEY=demo
FINNHUB_API_KEY=d_...
SEC_USER_AGENT="Your Name your@email.com"
```

### 3. Start the stack

```bash
# Terminal 1 — Backend
source .venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2 — Frontend
cd frontend && npm run dev

# Optional: Seed demo data (no API keys needed)
python scripts/seed_demo.py
```

### 4. Open the app

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000/dashboard |
| API Docs | http://localhost:8000/docs |
| Phoenix UI | http://localhost:6006 |
| Redis UI | http://localhost:8001 |

---

## API Reference

### `GET /api/v1/analyse` — SSE streaming analysis

```bash
curl -N "http://localhost:8000/api/v1/analyse?ticker=AAPL&query=Should+I+invest%3F"
```

**SSE events emitted:**

| Event | Payload |
|-------|---------|
| `progress` | `{session_id, step, agent, message, pct, timestamp}` |
| `agent_result` | `{session_id, agent, success, summary, pct}` |
| `reasoning` | `{session_id, content, step}` |
| `final` | `{session_id, thesis, technical_indicators, cached, latency_ms, agents_completed, agents_failed}` |
| `error` | `{session_id, message, recoverable}` |

### `POST /api/v1/feedback`

```json
{
  "session_id": "abc-123",
  "feedback_score": 4,
  "feedback_text": "Good analysis but missed the dividend angle",
  "correction": "Apple's dividend yield is 0.51% — not mentioned"
}
```

Corrections with `feedback_score <= 2` are stored in the Experience Bank and injected into future reviewer prompts for the same ticker.

### `GET /api/v1/memory/{ticker}`

Returns prior analysis summaries stored in vector memory for debugging the Experience Bank.

### `DELETE /api/v1/memory/{ticker}`

Clears ChromaDB RAG store + RedisVL semantic cache for a ticker (forces fresh analysis).

### `GET /api/v1/graph/status`

Returns the compiled LangGraph node list and edge topology.

### `GET /ready`

Readiness probe — checks Redis and PostgreSQL connectivity. Returns 503 if either is down.

---

## Technical Indicators

Computed from 1-year OHLCV history using the `ta` library (no TA-Lib C dependency):

| Indicator | Parameters | Signal logic |
|-----------|-----------|-------------|
| RSI | Period 14 | ≥70 → STRONG_BEARISH (overbought); ≤30 → STRONG_BULLISH (oversold) |
| MACD | 12/26/9 | Histogram > 0 → BULLISH; < 0 → BEARISH |
| Bollinger Bands | 20 period, 2σ | percent_b > 1 → above upper; < 0 → below lower |
| SMA | 20/50/200 | Above all three → STRONG_BULLISH; below all → STRONG_BEARISH |
| Overall | Weighted avg | Average of RSI + MACD + SMA signals |

---

## Deployment

### Option A: Vercel + Render (recommended free stack)

```bash
# 1. Deploy frontend to Vercel
cd frontend
vercel deploy --prod
# Set env var: NEXT_PUBLIC_API_URL=https://your-api.onrender.com

# 2. Deploy backend to Render
# Push repo to GitHub → connect to render.com → auto-detect render.yaml
# Set secrets: OPENAI_API_KEY, REDIS_URL (Upstash), DATABASE_URL (Neon)
```

### Option B: Fly.io (3 free VMs)

```bash
fly auth login
fly launch --config infra/fly.toml
fly secrets set OPENAI_API_KEY=sk-... REDIS_URL=redis://... DATABASE_URL=postgresql://...
fly deploy
```

### Option C: Full Docker stack (local)

```bash
docker compose -f infra/docker-compose.yml up --build
```

---

## Free Infrastructure

| Service | Free Tier | Use |
|---------|----------|-----|
| [Render.com](https://render.com) | 750 hrs/mo | Backend |
| [Vercel](https://vercel.com) | Unlimited hobby | Frontend |
| [Fly.io](https://fly.io) | 3 shared VMs | Alternative backend |
| [Neon](https://neon.tech) | 0.5 GB, autoscale-to-zero | PostgreSQL |
| [Redis Cloud](https://redis.com/try-free/) | 30 MB | Semantic cache |
| [Upstash](https://upstash.com) | 10k commands/day | Alternative Redis |
| EODHD | `demo` key | EOD price data |
| FMP | 250 req/day | Financial statements |
| Finnhub | 60 req/min | News sentiment |
| SEC EDGAR | Fully free | Company filings |
| sentence-transformers | Local (no API) | Embeddings |
| ChromaDB | In-process | RAG + memory |

**Estimated monthly cost: $0–$5** (primarily OpenAI tokens at ~$0.15/1M input)

---

## Testing

```bash
# Fast: schema + technical indicator unit tests (no LLM, no external APIs)
pytest tests/test_evaluation.py tests/test_technical.py tests/test_memory.py -v

# Integration: full pipeline with mocked external calls
pytest tests/test_integration.py -v

# DeepEval quality gate (requires OPENAI_API_KEY)
deepeval test run tests/test_evaluation.py -n 4 -c -i --verbose

# All tests with coverage
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

**DeepEval thresholds:**

| Metric | Threshold | Penalises |
|--------|-----------|----------|
| Answer Relevancy | ≥ 0.70 | Off-topic / rambling responses |
| Faithfulness | ≥ 0.75 | Hallucinated financial figures |
| Contextual Precision | ≥ 0.65 | Irrelevant retrieved context |

---

## Project Structure

```
hedge-fund-ai/
├── app/
│   ├── main.py                          # FastAPI factory + lifespan
│   ├── api/routes.py                    # All endpoints (SSE, feedback, memory, graph)
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings (env-validated)
│   │   ├── concurrency.py               # Semaphore + deduplication
│   │   ├── logging.py                   # structlog JSON logging
│   │   └── telemetry.py                 # Arize Phoenix OTEL tracing
│   ├── schemas/models.py                # All Pydantic contracts (10+ validators)
│   ├── graph/
│   │   ├── workflow.py                  # LangGraph compiled directed graph
│   │   └── nodes.py                     # 5 LangGraph node implementations
│   ├── agents/
│   │   ├── news_agent.py                # Finnhub + source-reliability weighting
│   │   ├── financial_data_agent.py      # EODHD + FMP + technicals + insiders
│   │   ├── document_agent.py            # SEC EDGAR + RAG ingestion
│   │   └── tools/technical_analysis.py  # RSI, MACD, Bollinger, SMA
│   ├── orchestrator/
│   │   ├── runner.py                    # SSE stream from LangGraph astream()
│   │   └── reviewer.py                  # Generator-Critic + Tenacity + corrections
│   ├── rag/pipeline.py                  # ChromaDB ingestion + retrieval
│   ├── memory/store.py                  # Vector memory + experience bank
│   ├── cache/semantic_cache.py          # RedisVL cosine similarity cache
│   └── db/feedback.py                   # SQLAlchemy async + Neon PostgreSQL
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx                     # Animated landing page
│   │   ├── dashboard/page.tsx           # 5-tab glass-window dashboard
│   │   └── api/                         # SSE + feedback proxy routes
│   ├── components/
│   │   ├── agents/AgentTimeline.tsx     # Live agent cards + reasoning terminal
│   │   ├── charts/TechnicalCharts.tsx   # RSI/MACD/Bollinger/SMA charts
│   │   └── dashboard/                   # Thesis, Sentiment, Insider, Confidence
│   ├── hooks/useAnalysisStream.ts       # Full SSE state machine
│   └── types/index.ts                   # TypeScript mirror of Pydantic schemas
│
├── tests/
│   ├── test_evaluation.py               # DeepEval + Pydantic schema contracts
│   ├── test_integration.py              # Full pipeline with mocked calls
│   ├── test_technical.py                # Technical indicator maths
│   └── test_memory.py                   # RAG + memory + cache tests
│
├── infra/
│   ├── docker-compose.yml               # Phoenix + Redis + App
│   ├── Dockerfile                       # Multi-stage production build
│   ├── render.yaml                      # Render.com free tier deploy
│   └── fly.toml                         # Fly.io free tier deploy
│
├── scripts/
│   ├── setup.sh                         # One-command bootstrap
│   └── seed_demo.py                     # Seed demo data (no API keys)
│
└── .github/workflows/ci.yml             # 7-job CI: lint → unit → integration → DeepEval → build
```

---

## Schema Validation Rules

| Constraint | Rule |
|-----------|------|
| `STRONG_BUY` / `STRONG_SELL` | `conviction_score >= 0.75` |
| `analysis_date` | ISO-8601 `YYYY-MM-DD` |
| `revenue_growth_yoy` | `-200%` to `+1000%` |
| Bollinger bands | `lower <= middle <= upper` |
| `net_margin` | `-500%` to `+100%` |
| `sentiment_score` | `-1.0` to `+1.0` |
| Bull/Bear case | `< 85%` token overlap |
| `target_price_usd` | `> 0` |
| RSI | `0` to `100` |
| `conviction_score` | `0.0` to `1.0` |

---

## Generator-Critic Pattern

```
1. GENERATOR  →  Instructor patches OpenAI → structured InvestmentThesis
                 Pydantic validates schema + domain rules
                 Tenacity retries on ValidationError (up to 4×, exp backoff)
                 
2. CRITIC     →  Second LLM call scores thesis for internal consistency (0.0–1.0)
                 Checks: no hallucinated numbers, non-contradictory bull/bear,
                         correct conviction level for recommendation signal
                         
3. GATE       →  critic_score >= 0.6 → thesis accepted
                 critic_score < 0.6  → Tenacity triggers retry with critic feedback
                 
4. CORRECTIONS→  Low-scored feedback (1–2) from users is stored in ChromaDB
                 Experience Bank and injected into the generator system prompt
                 on future requests for the same ticker
```
