#!/usr/bin/env bash
set -euo pipefail
export OMNI_HOST="${OMNI_HOST:-0.0.0.0}"
export OMNI_PORT="${OMNI_PORT:-8000}"
exec uvicorn app.main:app --host "$OMNI_HOST" --port "$OMNI_PORT"
