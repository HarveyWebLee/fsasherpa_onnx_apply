#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/"; exit 1; }
[[ -f uv.lock ]] || uv sync
export TTS_HOST="${TTS_HOST:-0.0.0.0}"
export TTS_PORT="${TTS_PORT:-19658}"
export TTS_MAX_INFLIGHT="${TTS_MAX_INFLIGHT:-64}"
export TTS_PRELOAD="${TTS_PRELOAD:-1}"
echo "Starting fsatts on http://127.0.0.1:${TTS_PORT} (max_inflight=${TTS_MAX_INFLIGHT}) ..."
exec uv run python -m uvicorn app.main:app --host "$TTS_HOST" --port "$TTS_PORT"
