#!/usr/bin/env bash
# Kylin V10 arm64 — MUST run on aarch64 (do not fake success on x86_64).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "ERROR: need aarch64 host for Kylin V10 arm64 build. Current: $ARCH" >&2
  echo "Copy the repo to a Kylin V10 arm64 machine, create .venv, install" >&2
  echo "sherpa-onnx aarch64 wheel (or build from source), then re-run this script." >&2
  exit 2
fi
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Missing .venv" >&2; exit 1; }
"$PY" -c "import sherpa_onnx" || { echo "sherpa_onnx not importable for aarch64" >&2; exit 1; }
"$PY" -m pip install -q "pyinstaller>=6.0"
"$PY" -m PyInstaller --noconfirm --clean --name fsatts --onedir --console \
  --add-data "static:static" --collect-all sherpa_onnx \
  --hidden-import app --hidden-import app.main --hidden-import app.tts_engine \
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  --hidden-import soundfile --hidden-import numpy \
  scripts/build/_entrypoint_fsatts.py

DIST="$ROOT/dist/fsatts"
ASSETS="$ROOT/scripts/build/package_assets"
cp "$ASSETS/run.sh" "$ASSETS/config.example.env" "$ASSETS/README-RUN.txt" "$DIST/"
chmod +x "$DIST/fsatts" "$DIST/run.sh" || true
mkdir -p "$DIST/models"
RELNAME="fsatts-kylin-v10-arm64"
REL="$ROOT/dist/$RELNAME"
rm -rf "$REL"
cp -a "$DIST" "$REL"
tar -C "$ROOT/dist" -czf "$ROOT/dist/${RELNAME}.tar.gz" "$RELNAME"
echo "OK: $REL"
echo "OK: $ROOT/dist/${RELNAME}.tar.gz"
