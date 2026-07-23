#!/usr/bin/env bash
# =============================================================================
# Start the SIMS Lite backend (development mode)
# =============================================================================
set -euo pipefail

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting Uvicorn..."
uvicorn app.main:app \
  --host "${APP_HOST:-0.0.0.0}" \
  --port "${APP_PORT:-8001}" \
  --reload \
  --log-level info
