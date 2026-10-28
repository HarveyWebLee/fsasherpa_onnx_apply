#!/usr/bin/env bash
# Build Linux amd64 (PyInstaller). Run on matching/older glibc.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Missing .venv" >&2; exit 1; }
"$PY" -m pip install -q pyinstaller
"$PY" -m PyInstaller --noconfirm --clean --name fsatts --onedir --console \
  --add-data "static:static" --collect-all sherpa_onnx \
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  scripts/build/_entrypoint_fsatts.py
echo "Done: dist/fsatts/ port 19658"
