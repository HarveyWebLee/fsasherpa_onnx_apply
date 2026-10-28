#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
export TTS_HOST="${TTS_HOST:-0.0.0.0}"
export TTS_PORT="${TTS_PORT:-19658}"
export TTS_CORS_ORIGINS="${TTS_CORS_ORIGINS:-*}"
export TTS_MODELS_ROOT="${TTS_MODELS_ROOT:-$DIR/models}"
echo "Starting fsatts plugin on ${TTS_HOST}:${TTS_PORT}"
exec ./fsatts
