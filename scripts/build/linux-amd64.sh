#!/usr/bin/env bash
# Build Linux amd64 plugin (PyInstaller onedir) + tar.gz
# Run on matching/older glibc for best compatibility.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Missing .venv" >&2; exit 1; }
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
RELNAME="fsatts-linux-amd64"
REL="$ROOT/dist/$RELNAME"
rm -rf "$REL"
cp -a "$DIST" "$REL"
tar -C "$ROOT/dist" -czf "$ROOT/dist/${RELNAME}.tar.gz" "$RELNAME"
echo "OK: $REL"
echo "OK: $ROOT/dist/${RELNAME}.tar.gz"
echo "Place models under $REL/models then ./run.sh"
