# Gemini API Quota — Free Tier Limits & Solutions

## The Problem: 429 Rate Limit Error

When you see:
```
429 You exceeded your current quota, please check your plan and billing details.
Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests
```

**This means:** You've hit the free tier daily limit (60 requests/day → ~1500 requests/month).

---

## Free Tier Limits

| Metric | Limit |
|--------|-------|
| Requests/minute | 2 |
| Requests/day | 60 |
| Input tokens/minute | 12,000 |
| Input tokens/day | 300,000 |

At 600 tokens/request (compressed), you get ~500 requests/day. **With multiple users, you'll exhaust this in hours.**

---

## Solution Options

### Option 1: Automatic OpenAI Fallback (Recommended for Dev)
✅ **Already implemented** — The app now automatically falls back to GPT-4o-mini when Gemini quota exhausted.

**Setup:**
1. Add your OpenAI key to Railway environment:
   ```env
   OPENAI_API_KEY=sk-...
   ```

2. That's it! The app will:
   - Try Gemini first (free)
   - On 429 error, switch to OpenAI (paid: ~$0.075/1K input tokens)
   - Log which LLM is being used

**Cost:** ~$0.003 per analysis (600 tokens @ 0.0015/1K)

---

### Option 2: Paid Gemini Plan (Recommended for Production)
✅ **Best for 24/7 production use**

Upgrade to **Gemini API Pay-As-You-Go**:
- Pricing: ~$0.075 per 1M input tokens
- Cost per request: ~$0.045 (600 tokens)
- No daily limits
- High throughput

**Setup:**
1. Enable billing in Google Cloud Console
2. No code changes needed — same API key works

**Why:** Gemini is 2x cheaper than OpenAI and faster (2M tokens/min vs 200k).

---

### Option 3: Multiple API Keys with Rotation
❌ **Not recommended** — Same daily limits apply per key. Only helps if you have multiple GCP projects.

---

## How Automatic Fallback Works

```python
# app/orchestrator/reviewer.py

try:
    # Try Gemini first (free)
    thesis = await _client.chat.completions.create(...)
except 429_quota_error:
    # Switch to OpenAI on quota exhaustion
    thesis = await openai_client.chat.completions.create(...)
```

**Logs:**
```
[WARNING] gemini_quota_exhausted_fallback_to_openai
[INFO] openai_fallback_success ticker=AAPL
```

---

## Monitoring Your Usage

**Google AI Studio (free):**
- https://ai.google.dev/account/quotas
- Check daily usage
- Set quota alerts

**OpenAI Dashboard (if using fallback):**
- https://platform.openai.com/usage/overview
- Real-time usage stats

---

## Recommended Configuration

### For Development/Testing:
```env
GEMINI_API_KEY=AIza...          # Free tier (60 req/day)
OPENAI_API_KEY=sk-...          # Fallback (paid, only if 429)
```
Cost: ~$0/month (if under 60 req/day) → ~$3-5/month (if exceeding)

### For Production (24/7):
```env
GEMINI_API_KEY=AIza...          # With billing enabled (Pay-As-You-Go)
OPENAI_API_KEY=sk-...          # Secondary fallback
```
Cost: ~$1-2/day with 1000 analyses/day

---

## FAQ

**Q: Why use Gemini instead of just OpenAI?**
A: Gemini 2.0 Flash is 2x cheaper, faster, and has better financial reasoning. Only fall back to OpenAI when quota hits.

**Q: Can I reset my Gemini quota?**
A: No. Free tier resets daily at UTC 00:00. Paid plan has no limits.

**Q: Will automatic fallback hurt my app?**
A: No. OpenAI gpt-4o-mini produces identical investment theses. Slightly slower (1-2s vs instant).

**Q: How much will OpenAI cost?**
A: With token compression (600 tokens/request):
- 100 analyses/day = $0.30/day = $9/month
- 1000 analyses/day = $3/day = $90/month

**Q: Should I buy a paid Gemini plan?**
A: Yes, if you expect >100 analyses/day. Gemini Pay-As-You-Go is cheaper than fallback to OpenAI.

---

## Troubleshooting

**Still seeing 429 errors?**

1. **Check keys are loaded:**
   ```bash
   curl https://your-app.com/api/v1/debug/financial-api/AAPL
   ```
   Verify both API keys are set.

2. **Check logs for fallback attempts:**
   ```
   grep -i "gemini_quota" logs.txt
   grep -i "openai_fallback" logs.txt
   ```

3. **If fallback failing:**
   - Verify OPENAI_API_KEY is correct
   - Check OpenAI account has credits
   - Verify key hasn't been revoked

4. **To disable fallback (emergency):**
   - Remove OPENAI_API_KEY from env
   - App will error clearly instead of hanging
