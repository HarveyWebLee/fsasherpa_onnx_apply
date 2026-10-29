#!/usr/bin/env bash
# Kylin V10 arm64 — MUST run on aarch64 (do not fake success on x86_64).
#
# Models: by default, copy usable dirs from repo models/ into the package.
#   INCLUDE_MODELS=0 ./scripts/build/kylin-v10-arm64.sh   # skip
#   INCLUDE_MODELS=1 ./scripts/build/kylin-v10-arm64.sh   # include when present
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

INCLUDE_MODELS="${INCLUDE_MODELS:-1}"
want_models=1
case "$INCLUDE_MODELS" in
  0|false|False|no|NO) want_models=0 ;;
esac

list_model_dirs() {
  local root="$1"
  [[ -d "$root" ]] || return 0
  local d
  for d in "$root"/*/; do
    [[ -d "$d" ]] || continue
    if { [[ -f "${d}model.onnx" ]] || [[ -f "${d}model.int8.onnx" ]]; } \
       && [[ -f "${d}lexicon.txt" ]] && [[ -f "${d}tokens.txt" ]]; then
      printf '%s\n' "$(basename "$d")"
    fi
  done
}

mapfile -t MODEL_DIRS < <(list_model_dirs "$ROOT/models")
if (( want_models )); then
  if ((${#MODEL_DIRS[@]} == 0)); then
    echo "WARN: models/ has no usable TTS model dirs; packaging empty models/."
    want_models=0
  else
    echo "Will include models: ${MODEL_DIRS[*]}"
  fi
else
  echo "Models SKIPPED (INCLUDE_MODELS=0)."
fi

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
rm -rf "$DIST/models"
mkdir -p "$DIST/models"
touch "$DIST/models/.gitkeep"
if (( want_models )); then
  for name in "${MODEL_DIRS[@]}"; do
    echo "Copying model $name ..."
    cp -a "$ROOT/models/$name" "$DIST/models/"
  done
fi
RELNAME="fsatts-kylin-v10-arm64"
REL="$ROOT/dist/$RELNAME"
rm -rf "$REL"
cp -a "$DIST" "$REL"
tar -C "$ROOT/dist" -czf "$ROOT/dist/${RELNAME}.tar.gz" "$RELNAME"
echo "OK: $REL"
echo "OK: $ROOT/dist/${RELNAME}.tar.gz"
if (( want_models )); then
  echo "Models bundled. Extract and ./run.sh (override with TTS_MODELS_ROOT if needed)."
else
  echo "Place models under $REL/models then ./run.sh"
fi