# infra/Dockerfile  v5
# Target: < 600 MB image, builds in < 4 minutes on Railway free tier
#
# Key decisions:
#   - fastembed (ONNX, 50MB) replaces sentence-transformers (PyTorch, 800MB)
#   - arize-phoenix and deepeval are DEV ONLY — not installed here
#   - No model pre-download — downloads on first request, cached in Railway volume
#   - Single-stage build (no multi-stage needed — cuts copy time)

FROM python:3.11-slim

WORKDIR /app

# System deps — minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Fast installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only the dependency manifest first (layer cache — only re-installs when pyproject.toml changes)
COPY pyproject.toml .

# Install ONLY runtime deps (not dev extras which include deepeval + phoenix + torch)
RUN uv pip install --system --no-cache \
    fastapi "uvicorn[standard]" httpx python-multipart python-dotenv \
    "pydantic>=2.7.0" pydantic-settings \
    "langgraph>=0.2.0" "langchain>=0.2.0" langchain-openai langchain-community \
    "openai>=1.35.0" "instructor>=1.3.0" tenacity \
    "langchain-chroma>=0.1.0" "chromadb>=0.5.0" langchain-text-splitters tiktoken \
    "pandas>=2.2.0" "numpy>=1.26.0" ta \
    "redisvl>=0.3.0" redis \
    asyncpg "sqlalchemy[asyncio]" aiosqlite \
    opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    openinference-instrumentation-openai \
    slowapi PyJWT structlog

# Copy application source
COPY app/ ./app/

# Create non-root user
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app

# Cache dirs for fastembed/ONNX models (downloaded on first request)
ENV HF_HOME=/home/appuser/.cache/huggingface
ENV FASTEMBED_CACHE_DIR=/home/appuser/.cache/fastembed
ENV ONNX_DISABLE_STATIC_ANALYSIS=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=5 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Shell form (not array) so $PORT environment variable expands correctly
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --loop uvloop --log-level info
