# infra/Dockerfile
# Ultra-slim runtime image (~600-800 MB) for Railway

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Build tools (cmake/g++ needed for chromadb compiled sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Use official 'uv' binary for 10-100x faster installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Compile requirements directly into the system python
RUN uv pip install --system --no-cache .

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security: non-root user
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /home/appuser/app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy strictly installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy ONLY backend application source
COPY app/ ./app/

# Set ownership
RUN chown -R appuser:appuser /home/appuser

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# 2 workers for free-tier single-vCPU hosts
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--log-level", "info"]
