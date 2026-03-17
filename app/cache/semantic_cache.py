"""
app/cache/semantic_cache.py
RedisVL semantic cache:
  • Free local embeddings via sentence-transformers (all-MiniLM-L6-v2)
  • Cosine similarity search — configurable threshold
  • Strict TTL to guard against stale financial data
  • Graceful degradation if Redis is unavailable
"""
from __future__ import annotations

import json
from typing import Any

from redisvl.extensions.llmcache import SemanticCache

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()

_cache_instance: SemanticCache | None = None


def _get_cache() -> SemanticCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache(
            name="hedge_fund_ai_cache",
            redis_url=_settings.redis_url,
            # redisvl uses distance not similarity; convert threshold
            distance_threshold=round(1.0 - _settings.cache_similarity_threshold, 4),
            ttl=_settings.cache_ttl_seconds,
            vectorizer_type="hf",
            vectorizer_kwargs={"model": _settings.embedding_model},
        )
        logger.info(
            "semantic_cache_initialised",
            ttl=_settings.cache_ttl_seconds,
            threshold=_settings.cache_similarity_threshold,
        )
    return _cache_instance


async def cache_lookup(prompt: str) -> dict[str, Any] | None:
    """
    Check semantic cache. Returns parsed dict on hit, None on miss.
    Never raises — Redis failure degrades to cache miss.
    """
    try:
        cache = _get_cache()
        results = cache.check(prompt=prompt, num_results=1)
        if results:
            hit = results[0]
            distance = hit.get("vector_distance", 1.0)
            similarity = round(1.0 - distance, 4)
            logger.info(
                "cache_hit",
                similarity=similarity,
                entry_id=hit.get("entry_id", "?"),
            )
            return json.loads(hit["response"])
    except Exception as exc:
        logger.warning("cache_lookup_degraded", error=str(exc))
    return None


async def cache_store(prompt: str, payload: dict[str, Any]) -> None:
    """
    Store payload in semantic cache with configured TTL.
    Never raises.
    """
    try:
        cache = _get_cache()
        cache.store(prompt=prompt, response=json.dumps(payload))
        logger.info("cache_store", prompt_prefix=prompt[:60])
    except Exception as exc:
        logger.warning("cache_store_degraded", error=str(exc))


async def cache_invalidate(prompt: str) -> None:
    """Force-invalidate a cached entry (e.g. after user feedback indicating staleness)."""
    try:
        cache = _get_cache()
        results = cache.check(prompt=prompt, num_results=1)
        if results:
            entry_id = results[0].get("entry_id")
            if entry_id:
                cache.delete(entry_id)
                logger.info("cache_invalidated", entry_id=entry_id)
    except Exception as exc:
        logger.warning("cache_invalidate_degraded", error=str(exc))
