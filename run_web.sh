#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/"; exit 1; }
[[ -f uv.lock ]] || uv sync
export TTS_HOST="${TTS_HOST:-0.0.0.0}"
export TTS_PORT="${TTS_PORT:-19658}"
exec uv run python -m uvicorn app.main:app --host "$TTS_HOST" --port "$TTS_PORT"