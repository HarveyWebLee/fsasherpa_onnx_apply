"""Frozen-app entry: start TTS plugin service (default 0.0.0.0:19658)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_paths() -> None:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", base))
        static = meipass / "static"
        if not static.is_dir():
            static = base / "static"
        os.environ.setdefault("FSATTS_STATIC_DIR", str(static))
        os.environ.setdefault("TTS_MODELS_ROOT", str(base / "models"))
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))


def main() -> None:
    _prepare_paths()
    os.environ.setdefault("TTS_HOST", "0.0.0.0")
    os.environ.setdefault("TTS_PORT", "19658")
    os.environ.setdefault("TTS_CORS_ORIGINS", "*")
    host = os.environ.get("TTS_HOST", "0.0.0.0")
    port = int(os.environ.get("TTS_PORT", "19658"))
    # Eager import so PyInstaller collects the app package
    import app.main  # noqa: F401
    import uvicorn

    print(f"[fsatts] listening http://{host}:{port}  CORS={os.environ.get('TTS_CORS_ORIGINS')}")
    print(f"[fsatts] models={os.environ.get('TTS_MODELS_ROOT')} static={os.environ.get('FSATTS_STATIC_DIR')}")
    uvicorn.run(app.main.app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
