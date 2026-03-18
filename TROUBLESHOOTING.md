# Troubleshooting Guide

## Issue 1: Price=$N/A | Sector=None

### Root Causes (in order of likelihood):

**1. Using Demo API Keys (Most Common)**
```
EODHD_API_KEY=demo          ← No real data
FMP_API_KEY=demo            ← No real data
```

**Solution:** Add real API keys to Railway environment
```env
EODHD_API_KEY=<your-actual-key>        # From https://eodhd.com
FMP_API_KEY=<your-actual-key>          # From https://financialmodelingprep.com
```

**Verify:** Check the debug endpoint:
```bash
curl https://your-app.com/api/v1/debug/financial-api/AAPL
```

Response should show:
- `"is_demo": false` ← Means real keys loaded
- `"status": "ok"` ← Means API responded
- `"sample": {"close": 123.45, ...}` ← Means data returned

---

**2. API Keys Set But Environment Not Reloaded**

Railway may not have redeployed after you added keys.

**Solution:**
1. Go to Railway dashboard
2. Click "Deploy" button manually (force redeploy)
3. Wait 2-3 minutes for startup
4. Try again

**Verify:** Check logs for:
```
[DEBUG] eodhd_demo_key_warning
[DEBUG] fmp_demo_key_warning
```
If you see these, your keys aren't loaded yet.

---

**3. API Keys Correct But APIs Failing**

Check if APIs themselves are down or rate-limited.

**Solution:** Check the debug endpoint response for:
```json
{
  "eodhd": {
    "error": "API error message here"
  },
  "fmp": {
    "error": "API error message here"
  }
}
```

If you see `"error"` fields:
- **"429"** in error → API rate limit hit (your key exhausted)
- **"401"** → Invalid API key
- **"Connection refused"** → API down

---

**4. Float Parsing Bug (Now Fixed in 0b5a663)**

Old code: `current_price = float(eod.get("close") or 0) or None`

This converted price=0 to None (logic error).

**Solution:** Already pushed. Just redeploy.

---

## Issue 2: 429 Rate Limits (Gemini + OpenAI)

### Error Pattern:
```
429 You exceeded your current quota
Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests
```

### Root Causes:

**1. Gemini Free Tier Exhausted (60 requests/day limit)**

Daily limit reset at UTC 00:00.

**Solution – Option A (Immediate):**
Use OpenAI fallback (already implemented):
```env
OPENAI_API_KEY=sk-<your-openai-key>
```

App will:
- Try Gemini first (free)
- On 429, wait 2s then switch to OpenAI
- Cost: ~$0.003/request (only when Gemini exhausted)

**Verify:** Check logs for:
```
[INFO] openai_fallback_success ticker=AAPL
```

---

**Solution – Option B (Long-term):**
Upgrade Gemini to Pay-As-You-Go:
1. Go to: https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com
2. Click "Enable Billing"
3. Set budget alerts: $5-10/month
4. Cost: ~$0.045/request (no daily limits)

**Why:** Gemini is cheaper long-term than fallback to OpenAI.

---

**2. OpenAI Also Rate-Limited (You're Using Both)**

If you see:
```
[CRITICAL] both_gemini_and_openai_rate_limited
```

Both APIs hit quota simultaneously.

**Solution:**
- Wait 1-2 hours for quotas to reset
- OR upgrade one/both to paid plans
- OR space out requests (implement queue with delays)

**Costs per month (1000 requests/day):**
| LLM | Cost/day | Cost/month |
|-----|----------|-----------|
| Gemini free | $0 | $0 (60 req limit) |
| OpenAI fallback | $3 | $90 |
| Gemini paid | $0.75 | $22.50 |
| Both paid | $1 | $30 |

---

## Issue 3: API Rate Limits (Financial Data)

EODHD and FMP also have rate limits.

**EODHD Limits:**
- Free: 120 requests/day
- Paid: Higher limits

**FMP Limits:**
- Free: 250 requests/day  
- Paid: Unlimited

**Solution:**
1. Implement request caching (already done with Redis)
2. Check debug endpoint for FMP/EODHD errors
3. If hitting limits, upgrade to paid tiers

---

## How to Diagnose Issues

### Step 1: Check Environment Variables
```bash
# In Railway dashboard, click your service
# Look at "Variables" tab
# Verify you can see:
- EODHD_API_KEY        (should NOT be "demo")
- FMP_API_KEY          (should NOT be "demo")
- GEMINI_API_KEY       (should start with "AIza")
- OPENAI_API_KEY       (should start with "sk-")
```

### Step 2: Check Logs
```bash
# In Railway, click "Logs" tab
# Search for:
- "eodhd_demo_key_warning"     ← Using demo keys
- "eodhd_rate_limit_429"       ← API rate limited
- "gemini_quota_exhausted"     ← Gemini out of quota
- "openai_fallback_success"    ← Fallback working
- "both_gemini_and_openai_rate_limited"  ← Both APIs exhausted
```

### Step 3: Use Debug Endpoint
```bash
curl -s "https://your-app.com/api/v1/debug/financial-api/AAPL" | jq '.'
```

Output tells you:
- Which API keys are set
- What each API is returning
- Any errors from API calls

### Step 4: Check Quotas

**Gemini:** https://ai.google.dev/account/quotas
- Shows daily usage (resets at UTC 00:00)
- Set alerts if approaching limit

**OpenAI:** https://platform.openai.com/usage/overview
- Real-time usage stats
- See which model consuming credits

**EODHD:** https://eodhd.com/account/dashboard
- Shows request count

**FMP:** https://financialmodelingprep.com/developer/docs/dashboard
- Shows request count

---

## Quick Fix Checklist

### For "Price=$N/A | Sector=None":
- [ ] Verify real API keys in Railway environment (not "demo")
- [ ] Force redeploy: Railway dashboard → Deploy button
- [ ] Wait 2-3 minutes
- [ ] Test with debug endpoint: `/api/v1/debug/financial-api/AAPL`
- [ ] Check logs for "demo_key_warning" or API errors

### For "429 Rate Limit" errors:
- [ ] Add OPENAI_API_KEY to Railway env (for fallback)
- [ ] Check Gemini quota at: https://ai.google.dev/account/quotas
- [ ] Check logs for "openai_fallback_success" (means fallback working)
- [ ] If both failing: wait for quota reset (UTC 00:00) or upgrade to paid

### For "Both APIs Rate Limited":
- [ ] Wait 1-2 hours for free tier quotas to reset
- [ ] OR upgrade Gemini to Pay-As-You-Go (~$0.045/req)
- [ ] OR reduce request volume (implement rate limiting on frontend)

---

## Still Having Issues?

1. **Run debug endpoint:** `curl https://your-app.com/api/v1/debug/financial-api/AAPL`
2. **Check logs:** Look for ERROR or WARNING messages
3. **Share:** The debug output + relevant log lines
4. **We'll diagnose:** The exact point of failure

---

## Estimated Time to Fix

| Issue | Time |
|-------|------|
| Add real API keys | 1 min |
| Force Railway redeploy | 3 min |
| Add OpenAI fallback | 2 min |
| Upgrade to paid Gemini | 5 min |
| **Total** | **~5-10 min** |
