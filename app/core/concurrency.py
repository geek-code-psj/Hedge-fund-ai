"""
app/core/concurrency.py
Concurrency control utilities:
  • Global semaphore to cap simultaneous LLM calls (cost protection)
  • Per-ticker in-flight deduplication (prevent identical concurrent analyses)
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Global LLM concurrency cap ────────────────────────────────────────────────
# gpt-4o-mini: rate limit is 500 RPM on free tier — cap at 10 simultaneous
_LLM_SEMAPHORE = asyncio.Semaphore(10)

# ── Per-ticker in-flight deduplication ────────────────────────────────────────
# If two identical ticker requests arrive simultaneously, the second one
# waits for the first to complete (and then hits cache) rather than
# launching a duplicate pipeline.
_in_flight: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
_in_flight_lock = asyncio.Lock()


@asynccontextmanager
async def llm_concurrency_slot():
    """Acquire a global LLM concurrency slot. Use as async context manager."""
    await _LLM_SEMAPHORE.acquire()
    logger.debug("llm_slot_acquired", remaining=_LLM_SEMAPHORE._value)
    try:
        yield
    finally:
        _LLM_SEMAPHORE.release()
        logger.debug("llm_slot_released", remaining=_LLM_SEMAPHORE._value)


@asynccontextmanager
async def deduplicated_analysis(ticker: str, query: str):
    """
    Ensure only one analysis pipeline runs per (ticker, query) at a time.

    First caller: sets the in-flight event, runs pipeline, clears event.
    Subsequent callers: wait for the first to finish, then hit semantic cache.

    Usage:
        async with deduplicated_analysis(ticker, query) as is_leader:
            if is_leader:
                # run full pipeline
            else:
                # just check cache — it'll be warm
    """
    key = f"{ticker}::{query[:80]}"
    async with _in_flight_lock:
        if key in _in_flight and not _in_flight[key].is_set():
            # Another coroutine is already running this analysis
            event = _in_flight[key]
            is_leader = False
        else:
            # We are the leader
            event = asyncio.Event()
            _in_flight[key] = event
            is_leader = True

    if not is_leader:
        logger.info("dedup_wait", ticker=ticker)
        await asyncio.wait_for(event.wait(), timeout=settings.orchestrator_timeout)
        yield False
        return

    try:
        yield True
    finally:
        event.set()
        async with _in_flight_lock:
            _in_flight.pop(key, None)
