#!/usr/bin/env bash
# scripts/setup.sh
# One-command local development bootstrap.
# Run from repo root: bash scripts/setup.sh

set -euo pipefail
BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${BLUE}[setup]${NC} $1"; }
ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

log "Hedge Fund AI v3 — Local Development Setup"
echo "============================================"

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v python3.11 >/dev/null 2>&1 || { warn "python3.11 not found. Install from https://python.org"; exit 1; }
command -v docker      >/dev/null 2>&1 || { warn "Docker not found. Install from https://docker.com"; exit 1; }
command -v node        >/dev/null 2>&1 || { warn "Node.js not found. Install from https://nodejs.org"; }
ok "Prerequisites OK"

# ── Python env ────────────────────────────────────────────────────────────────
log "Setting up Python environment..."
python3.11 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
ok "Python dependencies installed"

# ── Env file ──────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  warn ".env created from .env.example — add your API keys before running"
else
  ok ".env already exists"
fi

# ── Frontend ─────────────────────────────────────────────────────────────────
if command -v node >/dev/null 2>&1; then
  log "Installing frontend dependencies..."
  cd frontend
  if [ ! -f .env.local ]; then
    cp .env.local.example .env.local
    ok "frontend/.env.local created"
  fi
  npm install --prefer-offline --silent
  cd ..
  ok "Frontend dependencies installed"
fi

# ── Infrastructure ────────────────────────────────────────────────────────────
log "Starting Docker services (Redis + Arize Phoenix)..."
docker compose -f infra/docker-compose.yml up -d redis phoenix
ok "Redis and Phoenix started"

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API keys (OPENAI_API_KEY is required)"
echo "  2. Start backend:   source .venv/bin/activate && uvicorn app.main:app --reload"
echo "  3. Start frontend:  cd frontend && npm run dev"
echo "  4. Open app:        http://localhost:3000"
echo "  5. API docs:        http://localhost:8000/docs"
echo "  6. Phoenix UI:      http://localhost:6006"
echo "  7. Redis UI:        http://localhost:8001"
echo ""
echo "Run tests:  pytest tests/ -v"
echo "DeepEval:   deepeval test run tests/test_evaluation.py -n 4 -c -i"
