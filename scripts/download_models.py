#!/usr/bin/env python3
"""Download sherpa-onnx TTS models (GitHub release + mirrors, resumable)."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models_registry import MODEL_REGISTRY, model_files_ready, models_root  # noqa: E402

# Prefer China-friendly mirrors first; GitHub last.
MIRRORS = [
    "https://ghfast.top/https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
    "https://mirror.ghproxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
]


def _curl(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl", "-L", "-C", "-",
        "--connect-timeout", "30", "--max-time", "3600",
        "--retry", "5", "--retry-delay", "3", "--retry-all-errors",
        "-o", str(dest), url,
    ]
    print("GET", url, flush=True)
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  resume from {dest.stat().st_size/1e6:.1f} MB", flush=True)
    r = subprocess.run(cmd)
    return r.returncode == 0 and dest.is_file() and dest.stat().st_size > 1_000_000


def download_one(model_id: str, force: bool = False) -> bool:
    spec = MODEL_REGISTRY.get(model_id)
    if not spec or not spec.archive:
        print(f"SKIP {model_id}: no archive")
        return False
    dest_dir = models_root() / spec.dir_name
    if not force and model_files_ready(dest_dir, spec):
        print(f"READY {model_id} @ {dest_dir}")
        return True
    models_root().mkdir(parents=True, exist_ok=True)
    archive = models_root() / spec.archive
    if force and archive.is_file():
        archive.unlink()
    ok = False
    for base in MIRRORS:
        url = f"{base}/{spec.archive}"
        if _curl(url, archive):
            ok = True
            break
        # bad tiny response (error HTML) — remove so next mirror starts clean
        if archive.is_file() and archive.stat().st_size < 1_000_000:
            print(f"  tiny/bad file ({archive.stat().st_size} B), clearing for next mirror")
            archive.unlink(missing_ok=True)
    if not ok:
        print(f"FAIL download {model_id}")
        return False
    print(f"EXTRACT {archive} ({archive.stat().st_size/1e6:.1f} MB)")
    with tarfile.open(archive, "r:bz2") as tf:
        tf.extractall(models_root())
    archive.unlink(missing_ok=True)
    if model_files_ready(dest_dir, spec):
        print(f"DONE {model_id}")
        return True
    print(f"FAIL extract incomplete {model_id}")
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Download TTS models")
    p.add_argument("--id", action="append", dest="ids", help="model id (repeatable)")
    p.add_argument("--all", action="store_true")
    p.add_argument("--bundle", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()
    if args.list:
        for s in MODEL_REGISTRY.values():
            ready = model_files_ready(s.path, s)
            print(
                f"{s.id:16} speakers={s.num_speakers:4} ~{s.archive_mb:5.0f}MB "
                f"bundle={s.bundle_default} ready={ready}  {s.name}"
            )
        return 0
    ids = list(args.ids or [])
    if args.all:
        ids = list(MODEL_REGISTRY.keys())
    elif args.bundle or not ids:
        ids = [k for k, s in MODEL_REGISTRY.items() if s.bundle_default]
    failed = []
    for mid in ids:
        if mid not in MODEL_REGISTRY:
            print(f"unknown id: {mid}")
            failed.append(mid)
            continue
        if not download_one(mid, force=args.force):
            failed.append(mid)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
