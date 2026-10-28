"""Frozen-app entry: start TTS web service (default port 19658)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_paths() -> None:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", base))
        os.environ.setdefault("FSATTS_STATIC_DIR", str(meipass / "static"))
        os.environ.setdefault("TTS_MODELS_ROOT", str(base / "models"))


def main() -> None:
    _prepare_paths()
    host = os.environ.get("TTS_HOST", "127.0.0.1")
    port = int(os.environ.get("TTS_PORT", "19658"))
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
