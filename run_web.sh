#!/usr/bin/env bash
# Start sherpa-onnx TTS web UI (Git Bash / MSYS2 / macOS / Linux)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif [[ -x "$ROOT/.venv/Scripts/python" ]]; then
  PY="$ROOT/.venv/Scripts/python"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  echo "未找到 .venv 中的 Python。请先：" >&2
  echo "  python -m venv .venv && .venv/Scripts/pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 7860
