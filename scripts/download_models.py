#!/usr/bin/env python3
"""Download sherpa-onnx TTS models (GitHub release + mirrors + HF, resumable)."""

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
# mirror.ghproxy.com is often dead — omitted.
MIRRORS = [
    "https://gh-proxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
    "https://ghproxy.net/https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
    "https://ghfast.top/https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models",
]

# Optional HuggingFace (and hf-mirror) repos that host the same unpacked tree.
# Key = model id; value = HF repo id under csukuangfj / k2-fsa style.
HF_REPOS: dict[str, str] = {
    "melo-zh-en-44k": "csukuangfj/vits-melo-tts-zh_en",
    "melo-zh-en-8k": "csukuangfj/vits-melo-tts-zh_en-8k",
}

HF_BASES = [
    "https://hf-mirror.com",
    "https://huggingface.co",
]


def _is_bzip2(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(3) == b"BZh"
    except OSError:
        return False


def _archive_ok(path: Path, expect_mb: float | None = None) -> bool:
    if not path.is_file() or path.stat().st_size < 1_000_000:
        return False
    if not _is_bzip2(path):
        return False
    if expect_mb and expect_mb > 0 and path.stat().st_size < expect_mb * 1e6 * 0.85:
        return False
    try:
        with tarfile.open(path, "r:bz2") as tf:
            tf.getmembers()
        return True
    except Exception as e:
        print(f"  archive not ready: {e}", flush=True)
        return False


def _curl_one(url: str, dest: Path, *, retries: int = 2, max_time: int = 3600) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl",
        "-L",
        "-C",
        "-",
        "--connect-timeout",
        "20",
        "--max-time",
        str(max_time),
        "--retry",
        str(retries),
        "--retry-delay",
        "2",
        "-o",
        str(dest),
        url,
    ]
    print("GET", url, flush=True)
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  resume from {dest.stat().st_size / 1e6:.1f} MB", flush=True)
    return subprocess.run(cmd).returncode


def _hf_tree_download(model_id: str, dest_dir: Path) -> bool:
    """Download unpacked model files via HuggingFace resolve URLs (mirror-friendly)."""
    repo = HF_REPOS.get(model_id)
    if not repo:
        return False
    spec = MODEL_REGISTRY[model_id]
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Probe common filenames from registry + defaults
    names = []
    if spec.onnx_name:
        names.append(spec.onnx_name)
    names.extend(
        [
            "model.onnx",
            "model.int8.onnx",
            "lexicon.txt",
            "tokens.txt",
            "date.fst",
            "number.fst",
            "phone.fst",
        ]
    )
    # unique preserve order
    seen: set[str] = set()
    uniq = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)

    got_any = False
    for base in HF_BASES:
        print(f"HF try {base}/{repo}", flush=True)
        ok_files = 0
        for name in uniq:
            url = f"{base}/{repo}/resolve/main/{name}"
            dest = dest_dir / name
            # skip if already decent size for onnx / text
            if dest.is_file() and dest.stat().st_size > 100:
                ok_files += 1
                continue
            rc = _curl_one(url, dest, retries=1, max_time=1800)
            if dest.is_file() and dest.stat().st_size > 100:
                # HF may return HTML error pages — reject tiny HTML
                head = dest.read_bytes()[:32]
                if head.startswith(b"<!DOCTYPE") or head.startswith(b"<html"):
                    dest.unlink(missing_ok=True)
                    print(f"  HTML error for {name}, next mirror", flush=True)
                    break
                print(f"  got {name} ({dest.stat().st_size / 1e6:.2f} MB) rc={rc}", flush=True)
                ok_files += 1
                got_any = True
            else:
                # optional files (fst) may 404 — continue
                if name.endswith(".fst"):
                    continue
                if name in ("model.onnx", "model.int8.onnx") or name == spec.onnx_name:
                    print(f"  missing weight {name}", flush=True)
        if model_files_ready(dest_dir, spec):
            print(f"HF DONE {model_id} via {base}", flush=True)
            return True
        if got_any:
            # stay on this base if partial progress
            continue
    return model_files_ready(dest_dir, spec)


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

    if force and dest_dir.is_dir():
        # keep text assets; remove onnx only so HF/github can refill
        for p in dest_dir.glob("*.onnx"):
            p.unlink(missing_ok=True)

    # 1) GitHub release archives via mirrors
    archive = models_root() / spec.archive
    if force and archive.is_file():
        archive.unlink()

    if not force and _archive_ok(archive, expect_mb=spec.archive_mb):
        print(f"  using existing archive {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
        ok = True
    else:
        if archive.is_file() and not _is_bzip2(archive):
            print(f"  clearing corrupt/non-bz2 file ({archive.stat().st_size} B)")
            archive.unlink(missing_ok=True)

        ok = False
        for base in MIRRORS:
            url = f"{base}/{spec.archive}"
            rc = _curl_one(url, archive, retries=1)
            if _archive_ok(archive, expect_mb=spec.archive_mb):
                print(
                    f"  archive OK ({archive.stat().st_size / 1e6:.1f} MB) curl_rc={rc}", flush=True
                )
                ok = True
                break
            if archive.is_file() and not _is_bzip2(archive):
                print("  non-bz2 response; clearing before next mirror")
                archive.unlink(missing_ok=True)
            elif archive.is_file() and not _archive_ok(archive, expect_mb=spec.archive_mb):
                print(f"  partial/incomplete ({archive.stat().st_size / 1e6:.1f} MB); next mirror")
                archive.unlink(missing_ok=True)

    if ok:
        print(f"EXTRACT {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(models_root())
        archive.unlink(missing_ok=True)
        if model_files_ready(dest_dir, spec):
            print(f"DONE {model_id}")
            return True
        print(f"WARN extract incomplete {model_id}, trying HF...", flush=True)

    # 2) HuggingFace / hf-mirror fallback (file-by-file)
    print(f"FALLBACK HF for {model_id}", flush=True)
    if _hf_tree_download(model_id, dest_dir):
        print(f"DONE {model_id} (HF)")
        return True

    print(f"FAIL download {model_id}")
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Download TTS models")
    p.add_argument("--id", action="append", dest="ids", help="model id (repeatable)")
    p.add_argument("--all", action="store_true")
    p.add_argument("--bundle", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--hf-only", action="store_true", help="skip GitHub archives; use HF only")
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
        if args.hf_only:
            spec = MODEL_REGISTRY[mid]
            dest = models_root() / spec.dir_name
            if not args.force and model_files_ready(dest, spec):
                print(f"READY {mid}")
                continue
            if not _hf_tree_download(mid, dest):
                failed.append(mid)
            else:
                print(f"DONE {mid} (HF-only)")
            continue
        if not download_one(mid, force=args.force):
            failed.append(mid)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
