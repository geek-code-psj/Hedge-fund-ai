"""
app/core/config.py
Single source of truth for all runtime configuration.
Validated at import time — bad config fails fast.
"""
from __future__ import annotations

from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM — Gemini (primary, supports 3 keys for rotation on rate limits)
    gemini_api_key: str = "AIza-placeholder"  # Primary/fallback
    gemini_api_key_1: str = "AIza-placeholder"
    gemini_api_key_2: str = "AIza-placeholder"
    gemini_api_key_3: str = "AIza-placeholder"
    gemini_model: str = "gemini-2.0-flash"

    # LLM — OpenAI (optional fallback)
    openai_api_key: str = "sk-placeholder"
    openai_model: str = "gpt-4o-mini"

    # Financial data
    eodhd_api_key: str = "demo"
    fmp_api_key: str = "demo"
    finnhub_api_key: str = "d_placeholder"
    sec_user_agent: str = "ResearchBot research@example.com"

    # Storage
    redis_url: str = "redis://localhost:6379"
    database_url: str = "sqlite+aiosqlite:///./hedge_fund.db"  # fallback for local dev

    # Cache
    cache_ttl_seconds: int = 900
    cache_similarity_threshold: float = 0.92
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Observability
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"

    # Timeouts
    agent_timeout: int = 20
    llm_timeout: int = 90
    orchestrator_timeout: int = 60

    # Rate limiting
    rate_limit_per_minute: int = 30

    # App
    app_env: str = "production"  # Changed from "development" for production safety
    log_level: str = "INFO"

    @field_validator("cache_similarity_threshold")
    @classmethod
    def threshold_in_range(cls, v: float) -> float:
        if not 0.5 <= v <= 1.0:
            raise ValueError("cache_similarity_threshold must be 0.5–1.0")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def get_gemini_api_keys(self) -> list[str]:
        """Return list of valid Gemini API keys for rotation."""
        keys = [
            self.gemini_api_key_1,
            self.gemini_api_key_2,
            self.gemini_api_key_3,
        ]
        # Filter out placeholder keys; fallback to primary key
        valid_keys = [k for k in keys if k and not k.startswith("AIza-placeholder")]
        return valid_keys if valid_keys else [self.gemini_api_key]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Global state for API key rotation (in-memory counter)
_gemini_key_index: int = 0


def get_next_gemini_api_key() -> str:
    """Rotate through available Gemini API keys."""
    global _gemini_key_index
    settings = get_settings()
    keys = settings.get_gemini_api_keys()
    key = keys[_gemini_key_index % len(keys)]
    _gemini_key_index = (_gemini_key_index + 1) % len(keys)
    return key
