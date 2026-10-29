#!/usr/bin/env bash
# Build Linux amd64 plugin (PyInstaller onedir) + tar.gz
# Requires: uv (https://docs.astral.sh/uv/)
# Run on matching/older glibc for best compatibility.
#
# Models: by default, copy usable dirs from repo models/ into the package.
#   INCLUDE_MODELS=0 ./scripts/build/linux-amd64.sh   # skip (smaller CI/dev)
#   INCLUDE_HUGE_MODELS=1 ...  # also pack theresa/eula/fanchen
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

command -v uv >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/" >&2; exit 1; }
echo "uv sync --extra dev ..."
uv sync --extra dev

INCLUDE_MODELS="${INCLUDE_MODELS:-1}"
want_models=1
case "$INCLUDE_MODELS" in
  0|false|False|no|NO) want_models=0 ;;
esac

HUGE_MODELS="vits-zh-hf-theresa vits-zh-hf-eula vits-zh-hf-fanchen-C"
include_huge=0
case "${INCLUDE_HUGE_MODELS:-0}" in
  1|true|True|yes|YES) include_huge=1 ;;
esac

list_model_dirs() {
  local root="$1"
  [[ -d "$root" ]] || return 0
  local d name onnx
  for d in "$root"/*/; do
    [[ -d "$d" ]] || continue
    name="$(basename "$d")"
    if (( ! include_huge )); then
      case " $HUGE_MODELS " in
        *" $name "*) continue ;;
      esac
    fi
    onnx="$(find "$d" -maxdepth 1 -type f -name '*.onnx' ! -name '*rule*' -size +1000c | head -n1 || true)"
    if [[ -n "$onnx" ]] && [[ -f "${d}lexicon.txt" ]] && [[ -f "${d}tokens.txt" ]]; then
      printf '%s\n' "$name"
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

if [[ ! -f web/dist/index.html ]]; then
  echo "Building frontend (web/dist missing)..."
  (cd web && npm ci && npm run build)
fi

uv run python -m PyInstaller --noconfirm --clean --name fsatts --onedir --console \
  --add-data "static:static" --add-data "web/dist:web/dist" --collect-all sherpa_onnx \
  --hidden-import app --hidden-import app.main --hidden-import app.tts_engine \
  --hidden-import app.models_registry \
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
RELNAME="fsatts-linux-amd64"
REL="$ROOT/dist/$RELNAME"
rm -rf "$REL"
cp -a "$DIST" "$REL"
tar -C "$ROOT/dist" -czf "$ROOT/dist/${RELNAME}.tar.gz" "$RELNAME"
echo "OK: $REL"
echo "OK: $ROOT/dist/${RELNAME}.tar.gz"
if (( want_models )); then
  echo "Models bundled. Unzip/tar and ./run.sh (override with TTS_MODELS_ROOT if needed)."
else
  echo "Place models under $REL/models then ./run.sh"
fi
