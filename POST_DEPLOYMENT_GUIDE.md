# 🚀 POST-DEPLOYMENT OPTIMIZATION & MONITORING GUIDE

**Last Updated:** March 18, 2026  
**Status:** ✅ Live Production Deployment

---

## 📋 **POST-DEPLOYMENT CHECKLIST**

### Phase 1: Verify Core Functionality (30 min)

- [ ] **Test Backend Health**
  ```bash
  curl https://your-railway-app.railway.app/health
  # Expected: {"status": "ok", "version": "3.0.0"}
  ```

- [ ] **Test Frontend Load**
  ```bash
  # Open https://your-vercel-app.vercel.app/dashboard
  # Should load in <3 seconds
  ```

- [ ] **Test SSE Streaming**
  ```bash
  # Submit analysis request → should stream progress in real-time
  # Check browser DevTools → Network tab → response should be "pending"
  ```

- [ ] **Verify Database Connection**
  ```bash
  # Check Railway logs:
  # Should see: "startup_complete" and "otel_tracing_ready"
  ```

- [ ] **Verify Redis Cache**
  ```bash
  # Test cache hit:
  # 1. Submit analysis query
  # 2. Submit IDENTICAL query
  # 3. Second should be <1 second (cache hit)
  ```

- [ ] **Verify ChromaDB Persistence**
  ```bash
  # Submit analysis + check in Railway logs:
  # Should see: "rag_ingest" + document count
  ```

---

## 🔍 **PRODUCTION MONITORING SETUP**

### 1. **Railway Dashboard Monitoring**

**Go to:** Railway App → Monitoring tab

| Metric | Alert Threshold | Action |
|--------|---|---|
| **CPU** | >80% | Scale up Railway plan |
| **Memory** | >85% | Check for memory leaks (async generators) |
| **Disk** | >90% | Prune old ChromaDB data |
| **Errors** | >5/min | Check logs for API failures |
| **Latency** | >30s | Optimize LLM timeout |

**Setup Log Alerts:**
```yaml
# In Railway dashboard → Environment variables
# Add webhook for Slack/Discord errors:

ALERT_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK

# Then in app/core/logging.py add:
async def alert_on_critical(logger_name, level, message):
    if level == "ERROR" and "exception" in message:
        await send_webhook(message)
```

### 2. **Vercel Deployment Monitoring**

**Go to:** Vercel Dashboard → Project Settings → Integrations

- [ ] Enable **Error Tracking** (captures JavaScript errors)
- [ ] Enable **Performance Analytics** (Core Web Vitals)
- [ ] Set up **Slack notifications** on failed deploys
- [ ] Monitor **Edge Functions** latency

**Key Metrics to Watch:**
- First Contentful Paint (FCP): Target <1.5s
- Largest Contentful Paint (LCP): Target <2.5s
- Cumulative Layout Shift (CLS): Target <0.1

### 3. **Database Health (Neon PostgreSQL)**

**Go to:** Neon Dashboard → your-database → Logs

- [ ] Monitor **Connection Pool**
  ```sql
  SELECT count(*) FROM pg_stat_activity;
  -- Should be <20 active connections
  ```

- [ ] Monitor **Query Performance**
  ```sql
  SELECT query, mean_time, calls 
  FROM pg_stat_statements 
  ORDER BY mean_time DESC LIMIT 5;
  -- Look for queries >1 second
  ```

- [ ] Set up **Auto-Scaling**
  ```
  Neon Dashboard → Branches → Auto-scaling
  Min compute: 0.25 vCPU
  Max compute: 1 vCPU
  ```

### 4. **Redis Cache Health (Upstash)**

**Go to:** Upstash Dashboard → your-database → Info

- [ ] Monitor **Memory Usage**
  - Target: <70% of plan capacity
  - Upgrade if exceeding

- [ ] Monitor **Commands/Sec**
  - Normal: 100-500 ops/sec
  - Alert if >1000 (cache thrashing)

- [ ] Monitor **Hit Rate**
  ```bash
  # In app/cache/semantic_cache.py, add:
  hit_rate = cache_hits / (cache_hits + cache_misses)
  logger.info("cache_stats", hit_rate=hit_rate, hits=cache_hits, misses=cache_misses)
  ```

- [ ] Set up **TTL Optimization**
  ```python
  # Current: 15 minutes (900s)
  # If hit_rate < 50%, reduce to 5 min
  # If during market hours (9:30-16:00 ET), reduce to 5 min
  
  from datetime import datetime, time
  
  def get_ttl():
      now = datetime.now().time()
      market_hours = time(9, 30) <= now <= time(16, 0)
      return 300 if market_hours else 900
  ```

---

## 🎯 **PERFORMANCE OPTIMIZATION**

### 1. **Backend Optimization**

**A. Reduce Cold Start Time**
```python
# ❌ Current: Imports happen at startup
from langchain_openai import ChatOpenAI
from chromadb import PersistentClient

# ✅ Better: Lazy imports
def get_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI()

# Result: ~2s faster cold start
```

**B. Add Response Compression**
```python
# app/main.py
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
# Compresses SSE streams, saves ~70% bandwidth
```

**C. Optimize LLM Latency**
```python
# Current: LLM timeout = 90 seconds
# Better: Use streaming + token budgets

# In reviewer.py:
max_tokens=1500,  # Cut from 2500
temperature=0.05,  # Lower = faster
# Result: ~30% faster thesis generation
```

**D. Cache Agent Outputs**
```python
# app/orchestrator/runner.py
# Instead of:
result = await get_graph().ainvoke(state)

# Better: Cache full graph output by ticker + date
cache_key = f"graph_{ticker}_{date.today()}"
if await cache_lookup(cache_key):
    return cached_result

result = await get_graph().ainvoke(state)
await cache_store(cache_key, result, ttl=3600)
```

### 2. **Database Optimization**

**A. Add Indexes to Neon**
```sql
-- app/db/feedback.py migrations

-- Speed up session lookups
CREATE INDEX idx_session_id ON sessions(id);

-- Speed up user feedback queries
CREATE INDEX idx_feedback_ticker ON feedback(ticker, created_at DESC);

-- Speed up memory retrieval
CREATE INDEX idx_memory_ticker ON memory(ticker, score DESC);
```

**B. Archive Old Data**
```python
# Archive thesis older than 90 days
DELETE FROM feedback 
WHERE created_at < NOW() - INTERVAL '90 days'
    AND NOT important;  # Don't delete manually marked theses

# This keeps DB size <500MB
```

**C. Connection Pool Tuning**
```python
# In app/db/feedback.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # Neon free tier: max 20 connections
    max_overflow=5,        # Burst capacity
    pool_recycle=3600,     # Recycle connections hourly
    pool_pre_ping=True,    # Test connections before use
)
```

### 3. **Frontend Optimization**

**A. Lazy Load Dashboard Components**
```typescript
// frontend/app/dashboard/page.tsx
import dynamic from 'next/dynamic';

const TechnicalCharts = dynamic(
  () => import('@/components/charts/TechnicalCharts'),
  { loading: () => <Skeleton /> }
);
// Reduces initial JS bundle by ~50KB
```

**B. Add Service Worker for Offline**
```typescript
// frontend/public/service-worker.ts
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}

// Caches analysis results locally
// User can view results even if offline
```

**C. Optimize Image Loading**
```typescript
// Use Next.js Image component with priority
import Image from 'next/image';

<Image 
  src="/og-image.jpg"
  alt="Hedge Fund AI"
  priority  // LCP image
  width={1200}
  height={630}
/>
```

---

## 🚨 **ERROR HANDLING & RECOVERY**

### 1. **Graceful Degradation**

**If Upstash Redis is down:**
```python
# Current: Returns error
cache = _get_cache()  # ← Can raise exception

# Better: Graceful fallback
try:
    cache_result = await cache_lookup(prompt)
    if cache_result:
        return cache_result
except Exception:
    logger.warning("cache_unavailable", proceed="true")
    # Continue without cache
```

**If Neon DB is down:**
```python
# Session storage falls back to in-memory (1 hour TTL)
_memory_sessions: dict[str, Session] = {}

async def get_session(session_id):
    try:
        return await db.get_session(session_id)
    except ConnectionError:
        return _memory_sessions.get(session_id)  # Fallback
```

### 2. **Retry Logic for External APIs**

```python
# app/agents/news_agent.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def fetch_finnhub(ticker):
    r = await http.get(f"https://finnhub.io/...")
    r.raise_for_status()
    return r.json()

# Retries: 0s, +2s, +4s = max 6s wait
```

### 3. **Circuit Breaker Pattern**

```python
# app/core/circuit_breaker.py (NEW FILE)
from enum import Enum
from datetime import datetime, timedelta

class CircuitState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.timeout = timeout
        self.last_failure = None
    
    async def call(self, fn, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if datetime.now() - self.last_failure > timedelta(seconds=self.timeout):
                self.state = CircuitState.HALF_OPEN
            else:
                raise Exception("Circuit breaker OPEN")
        
        try:
            result = await fn(*args, **kwargs)
            self.failure_count = 0
            self.state = CircuitState.CLOSED
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure = datetime.now()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            raise

# Usage:
breaker = CircuitBreaker(failure_threshold=3)

async def safe_fetch():
    return await breaker.call(fetch_finnhub, "AAPL")
```

---

## 📊 **METRICS DASHBOARD (Self-Hosted)**

### Option 1: Prometheus + Grafana (Free, DIY)

**Create:** `docker-compose.monitoring.yml`
```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
  
  grafana:
    image: grafana/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
```

**Add metrics to FastAPI:**
```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

request_count = Counter(
    'hedge_fund_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'hedge_fund_request_duration_seconds',
    'Request duration',
    ['endpoint']
)

cache_hits = Counter('cache_hits_total', 'Cache hits')
cache_misses = Counter('cache_misses_total', 'Cache misses')

# Usage in routes:
@app.get("/api/v1/analyse")
async def analyse(request, ticker, query):
    with request_duration.labels(endpoint="analyse").time():
        # ... your code
        request_count.labels(
            method="GET",
            endpoint="analyse",
            status="200"
        ).inc()
```

### Option 2: Use Railway Native Metrics

Already included! Go to:
- Railway Dashboard → Metrics tab
- See CPU, Memory, Network in real-time

---

## 🔐 **SECURITY HARDENING**

### 1. **Environment Variables Audit**

```bash
# ❌ What to avoid:
export OPENAI_API_KEY=sk-abc...  # Visible in logs

# ✅ Better: Use Railway secrets
Railway Dashboard → Project Settings → Variables
# Add as "Protected" (hidden in logs)
```

**Audit Railway secrets:**
```bash
# Verify all sensitive keys are marked as "Protected":
- GEMINI_API_KEY
- OPENAI_API_KEY
- OPENAI_ORG_ID
- DATABASE_URL
- REDIS_URL
```

### 2. **CORS Security**

```python
# Current: CORS open in production ⚠️
origins = ["*"] if not settings.is_production else [...]

# Better: Whitelist only your Vercel domain
origins = [
    "https://your-vercel-app.vercel.app",
    "https://your-vercel-app.com",  # Custom domain if used
]

if settings.is_production:
    origins = origins
else:
    origins = ["*"]  # Dev only
```

### 3. **Rate Limiting Tuning**

```python
# Current: 30 requests/minute globally
rate_limit_per_minute = 30

# Better: Tier by user
@limiter.limit("60/minute")  # Free tier
async def analyse_free_user(ticker):
    pass

@limiter.limit("300/minute")  # Pro tier (future)
async def analyse_pro_user(ticker):
    pass
```

### 4. **Input Validation**

```python
# Add: Ticker validation in routes
@router.get("/analyse")
async def analyse(
    ticker: str = Query(..., regex="^[A-Z]{1,5}(\.[A-Z]{2,3})?$"),
    # Matches: AAPL, AAPL.US, RELIANCE.NSE
    query: str = Query(..., max_length=500),
):
    pass
```

---

## 📈 **SCALING CHECKLIST** (When you hit growth)

### If Traffic Exceeds 100 req/min:

1. **Upgrade Railway Plan**
   ```
   Starter ($5/mo) → Pro+ ($30/mo)
   Gets: ↑CPU, ↑RAM, ↑concurrent containers
   ```

2. **Upgrade Redis (Upstash)**
   ```
   Free (256MB) → Pro ($15/mo)
   Gets: ↑bandwidth, ↑concurrent connections
   ```

3. **Switch to PostgreSQL Connection Pool**
   ```
   Neon auto-scales but add:
   - PgBouncer layer (connection pooling)
   - Read replicas for reports
   ```

4. **Add CDN for Frontend**
   ```
   Vercel already included + Cloudflare (free tier)
   Gets: ↑edge caching, ↑geographic distribution
   ```

5. **Batch LLM Requests**
   ```python
   # Instead of: 1 analysis = 1 LLM call
   # Better: Batch 5 analyses → 1 LLM call (if time-sensitive)
   
   async def batch_analyse(tickers: list[str]):
       analyses = await asyncio.gather(*[
           get_graph().ainvoke({"ticker": t, ...})
           for t in tickers
       ])
       return analyses
   ```

---

## 🧪 **LOAD TESTING (Before scaling)**

### Using Apache Bench (Free)

```bash
# Install: brew install httpd (macOS) or apt-get install apache2-utils (Linux)

# Test backend
ab -n 100 -c 10 https://your-railway-app.railway.app/health
# 100 requests, 10 concurrent

# Test SSE streaming
ab -n 50 -c 5 'https://your-railway-app.railway.app/api/v1/analyse?ticker=AAPL'
```

### Using k6 (Better for SSE)

```javascript
// load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '30s', target: 20 },  // Ramp up
    { duration: '1m30s', target: 20 }, // Stay
    { duration: '30s', target: 0 },   // Ramp down
  ],
};

export default function() {
  let res = http.get(
    'https://your-railway-app.railway.app/api/v1/analyse?ticker=AAPL&query=buy'
  );
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 3s': (r) => r.timings.duration < 3000,
  });
  
  sleep(1);
}
```

**Run:**
```bash
k6 run load-test.js
```

---

## 🔄 **CONTINUOUS DEPLOYMENT BEST PRACTICES**

### 1. **Add Staging Environment**

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches:
      - main      # → Production
      - staging   # → Staging

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to Staging
        if: github.ref == 'refs/heads/staging'
        env:
          RAILWAY_API_TOKEN: ${{ secrets.RAILWAY_API_TOKEN }}
        run: |
          railway deploy --service backend-staging
      
      - name: Deploy to Production
        if: github.ref == 'refs/heads/main'
        run: |
          railway deploy --service backend-prod
```

### 2. **Add Pre-Deploy Checks**

```yaml
# .github/workflows/tests.yml
name: Tests & Quality

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install deps
        run: pip install -e ".[dev]"
      
      - name: Lint
        run: ruff check app/ tests/
      
      - name: Type check
        run: pyright app/
      
      - name: Tests
        run: pytest tests/ --cov=app --cov-fail-under=70
      
      - name: Security scan
        run: bandit -r app/ -ll
```

### 3. **Rollback Procedure**

```bash
# If production breaks, rollback to previous deploy:

# 1. See deployment history in Railway
railway deployments --service backend

# 2. Rollback to specific build
railway deploy --build-id <build-id>

# Or just revert git & push:
git revert HEAD
git push origin main
# (Railway auto-deploys)
```

---

## 📞 **SUPPORT & ALERTING**

### 1. **Critical Error Alerts (Slack)**

```python
# app/core/logging.py
import httpx

async def alert_slack(level: str, message: str, error: str):
    if level not in ["ERROR", "CRITICAL"]:
        return
    
    webhook = os.getenv("SLACK_WEBHOOK")
    if not webhook:
        return
    
    payload = {
        "text": f"🚨 {level}: {message}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{error}```"}
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(webhook, json=payload)

# Hook into logging:
logger.error("agent_timeout", error=error)
await alert_slack("ERROR", "Agent timeout", error)
```

**Add to Railway secrets:**
```
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK
```

### 2. **Uptime Monitoring (Free)**

Use: https://uptimerobot.com/

```
Monitor: https://your-railway-app.railway.app/health
Frequency: Every 5 minutes
Alert: If down >5 min, send email
```

### 3. **Database Backup Alerts**

Neon PostgreSQL auto-backups every 24h. Verify:
```
Neon Dashboard → Backups tab
Should see: "Latest: 1 day ago"
```

---

## 📋 **WEEKLY OPERATIONS CHECKLIST**

- [ ] Check Railway metrics (CPU, Memory, Errors)
- [ ] Check Vercel Analytics (CWV, error rate)
- [ ] Test SSE streaming manually
- [ ] Review app logs for warnings
- [ ] Check cache hit rate (Upstash)
- [ ] Verify DB connection pool < 20
- [ ] Run sample analysis end-to-end
- [ ] Check Slack alerts (none should exist)
- [ ] Back up local ChromaDB data (if manual backups needed)

---

## ✅ **FINAL SIGN-OFF**

**Your Production Status:**

| Component | Status | Action |
|-----------|--------|--------|
| **Backend** | ✅ Live | Monitor Railway CPU |
| **Frontend** | ✅ Live | Monitor Core Web Vitals |
| **Database** | ✅ Connected | Set up auto-scaling |
| **Cache** | ✅ Working | Monitor hit rate |
| **Auto-deploy** | ✅ Active | No action |
| **Monitoring** | ⚠️ Basic | Set up Prometheus |
| **Alerting** | ⚠️ Manual | Configure Slack webhook |
| **Testing** | ⚠️ None | Set up load tests |
| **Backups** | ✅ Auto | Verify weekly |

---

## 🎉 **Deployment Summary**

```
🚀 Hedge Fund AI v3 - LIVE
├─ Frontend: Vercel ✅ (https://your-vercel-app.vercel.app)
├─ Backend: Railway ✅ (https://your-railway-app.railway.app)
├─ Database: Neon ✅ (Auto-scaling)
├─ Cache: Upstash Redis ✅ (Semantic)
├─ Vector DB: ChromaDB ✅ (Railway disk)
├─ CI/CD: GitHub Actions ✅ (Auto-deploy)
└─ Cost: $5/month ✅

Next: Set up monitoring + alerts!
```

---

**Questions? Check Railway/Vercel logs:**
```bash
railway logs
# or
vercel logs
```
