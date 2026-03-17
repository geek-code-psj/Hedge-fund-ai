"""
app/main.py
FastAPI application factory.
Lifespan handles startup/shutdown of:
  • Database tables
  • Phoenix OTEL tracing
  • Structured logging
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.routes import limiter, router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import configure_tracing
from app.db.feedback import init_db

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("startup_begin", env=settings.app_env)

    configure_tracing()
    await init_db()

    logger.info("startup_complete")
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Hedge Fund AI — Financial Analysis Platform",
        description=(
            "Multi-agent AI equity research platform with real-time SSE streaming, "
            "semantic caching, structured LLM output, and observability."
        ),
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Rate limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── CORS ──────────────────────────────────────────────────────────────────
    origins = ["*"] if not settings.is_production else [
        "https://your-frontend-domain.com"
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
