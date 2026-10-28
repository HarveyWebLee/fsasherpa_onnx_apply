#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/models/vits-melo-tts-zh_en-8k"
mkdir -p "$DEST"
BASE="${HF_ENDPOINT:-https://hf-mirror.com}"
BASE="${BASE%/}"
REPO="Luigi/vits-melo-tts-zh_en-8k"
for f in model.onnx tokens.txt lexicon.txt; do
  if [[ -s "$DEST/$f" ]]; then echo "skip $f"; continue; fi
  url="$BASE/$REPO/resolve/main/$f"
  echo "Downloading $url"
  curl -L --fail -o "$DEST/$f" "$url"
done
SRC="$ROOT/models/vits-melo-tts-zh_en"
for name in dict phone.fst date.fst number.fst; do
  if [[ ! -e "$DEST/$name" && -e "$SRC/$name" ]]; then
    cp -a "$SRC/$name" "$DEST/$name"
    echo "copied $name"
  fi
done
echo "Done. export TTS_MODEL_DIR=$DEST && ./run_web.sh"
