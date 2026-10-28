#!/usr/bin/env bash
# Kylin V10 arm64 — RUN ON aarch64 host (not cross-compile by default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "Expect aarch64, got $ARCH. Build on Kylin V10 arm64 or arm64 container." >&2
  exit 2
fi
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Missing .venv / sherpa-onnx aarch64 wheel" >&2; exit 1; }
"$PY" -c "import sherpa_onnx" || { echo "sherpa_onnx missing for aarch64" >&2; exit 1; }
"$PY" -m pip install -q pyinstaller
"$PY" -m PyInstaller --noconfirm --clean --name fsatts --onedir --console \
  --add-data "static:static" --collect-all sherpa_onnx \
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  scripts/build/_entrypoint_fsatts.py
echo "Done: dist/fsatts/ for Kylin V10 arm64"
