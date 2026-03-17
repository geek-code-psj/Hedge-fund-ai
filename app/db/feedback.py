"""
app/db/feedback.py
PostgreSQL feedback storage via SQLAlchemy async.
Free tier: Neon (0.5 GB, autoscale-to-zero).
Fallback: SQLite for local development without a DB.

Tables:
  sessions  — research context per analysis run
  feedback  — user ratings linked to sessions
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.models import AggregatedResearch, InvestmentThesis, UserFeedback

logger = get_logger(__name__)
settings = get_settings()

# ── Engine ─────────────────────────────────────────────────────────────────────
# Neon requires ?sslmode=require for asyncpg; SQLite works locally
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


# ── Models ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    ticker = Column(String(20), nullable=False, index=True)
    query = Column(Text, nullable=False)
    research_context = Column(Text)         # JSON-serialised AggregatedResearch
    thesis = Column(Text)                   # JSON-serialised InvestmentThesis
    recommendation = Column(String(20))
    conviction_score = Column(Integer)      # stored as 0–100 integer
    created_at = Column(DateTime, server_default=func.now())


class FeedbackRecord(Base):
    __tablename__ = "feedback"

    id = Column(String(64), primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    feedback_score = Column(Integer, nullable=False)
    feedback_text = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# ── Lifecycle ──────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create tables on startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db_tables_ready")


# ── Repository functions ───────────────────────────────────────────────────────

async def store_session_context(
    session_id: str,
    ticker: str,
    query: str,
    research: AggregatedResearch,
    thesis: InvestmentThesis,
) -> None:
    """Persist research context + thesis for later feedback and evaluation."""
    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                record = SessionRecord(
                    id=session_id,
                    ticker=ticker,
                    query=query,
                    research_context=research.model_dump_json(),
                    thesis=thesis.model_dump_json(),
                    recommendation=thesis.recommendation.value,
                    conviction_score=int(thesis.conviction_score * 100),
                )
                session.add(record)
        logger.info("session_stored", session_id=session_id, ticker=ticker)
    except Exception as exc:
        # Non-fatal — analysis result already returned to user
        logger.warning("session_store_failed", error=str(exc))


async def store_feedback(feedback: UserFeedback) -> bool:
    """
    Store user feedback.
    Returns True on success, False on failure.
    Feedback data feeds future prompt-tuning and DeepEval evaluation datasets.
    """
    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                record = FeedbackRecord(
                    id=feedback.id,
                    session_id=feedback.session_id,
                    feedback_score=feedback.feedback_score,
                    feedback_text=feedback.feedback_text,
                )
                session.add(record)
        logger.info(
            "feedback_stored",
            session_id=feedback.session_id,
            score=feedback.feedback_score,
        )
        return True
    except Exception as exc:
        logger.error("feedback_store_failed", error=str(exc))
        return False


async def get_session(session_id: str) -> SessionRecord | None:
    """Retrieve a session record by ID."""
    try:
        async with AsyncSessionFactory() as session:
            return await session.get(SessionRecord, session_id)
    except Exception as exc:
        logger.error("session_get_failed", error=str(exc))
        return None
