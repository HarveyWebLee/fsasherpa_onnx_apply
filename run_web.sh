#!/usr/bin/env bash
# Start sherpa-onnx TTS plugin service (Git Bash / MSYS2 / macOS / Linux)
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

export TTS_NUM_THREADS="${TTS_NUM_THREADS:-2}"
export TTS_HOST="${TTS_HOST:-0.0.0.0}"
export TTS_PORT="${TTS_PORT:-19658}"
export TTS_CORS_ORIGINS="${TTS_CORS_ORIGINS:-*}"
PROVIDER="${TTS_PROVIDER:-cpu}"

if [[ "${PROVIDER}" == "cuda" ]]; then
  NVIDIA_ROOT="$ROOT/.venv/Lib/site-packages/nvidia"
  if [[ -d "$NVIDIA_ROOT" ]]; then
    while IFS= read -r -d '' b; do
      PATH="$b;$PATH"
      export PATH
    done < <(find "$NVIDIA_ROOT" -type d -name bin -print0 2>/dev/null || true)
    echo "[run_web] nvidia bin dirs prepended for CUDA"
  else
    echo "[run_web] 警告: 未找到 nvidia site-packages，CUDA EP 可能缺 DLL" >&2
  fi
fi

echo "启动 TTS 插件服务: http://${TTS_HOST}:${TTS_PORT}  (本机 http://127.0.0.1:${TTS_PORT})  provider=${PROVIDER} threads=${TTS_NUM_THREADS} CORS=${TTS_CORS_ORIGINS}"
exec "$PY" -m uvicorn app.main:app --host "$TTS_HOST" --port "$TTS_PORT"
