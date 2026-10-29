"""Model registry for sherpa-onnx TTS (Chinese-English Melo only)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def models_root() -> Path:
    env = os.environ.get("TTS_MODELS_ROOT") or os.environ.get("FSATTS_MODELS_ROOT")
    if env:
        return Path(env)
    return ROOT / "models"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    dir_name: str
    description: str
    num_speakers: int = 1
    expected_sample_rate: int | None = None
    tags: tuple[str, ...] = ()
    speakers: tuple[dict, ...] = ()
    # Explicit ONNX filename inside model dir (None = auto-detect)
    onnx_name: str | None = None
    # Whether default packaging should include this model
    bundle_default: bool = False
    # Download archive name on GitHub tts-models release
    archive: str | None = None
    # Approximate download size (MB, compressed)
    archive_mb: float = 0.0
    lang: str = "zh+en"

    @property
    def path(self) -> Path:
        return models_root() / self.dir_name


_MELO_SPEAKERS = (
    {
        "sid": 0,
        "name": "默认女声",
        "lang": "zh+en",
        "note": "中英混合；官方单说话人女声",
    },
)

MODEL_REGISTRY: dict[str, ModelSpec] = {
    "melo-zh-en-44k": ModelSpec(
        id="melo-zh-en-44k",
        name="Melo 中英 44.1kHz",
        dir_name="vits-melo-tts-zh_en",
        description="中英混合（支持英文与中英混读）· 音质优先 · 44.1 kHz，单女声",
        num_speakers=1,
        expected_sample_rate=44100,
        tags=("default", "quality", "zh-en"),
        speakers=_MELO_SPEAKERS,
        onnx_name="model.onnx",
        bundle_default=True,
        archive="vits-melo-tts-zh_en.tar.bz2",
        archive_mb=170,
        lang="zh+en",
    ),
    "melo-zh-en-8k": ModelSpec(
        id="melo-zh-en-8k",
        name="Melo 中英 8kHz",
        dir_name="vits-melo-tts-zh_en-8k",
        description="中英混合（支持英文与中英混读）· 更快更小 · 8 kHz",
        num_speakers=1,
        expected_sample_rate=8000,
        tags=("fast", "8k", "zh-en"),
        speakers=_MELO_SPEAKERS,
        onnx_name="model.onnx",
        bundle_default=True,
        archive="vits-melo-tts-zh_en-8k.tar.bz2",
        archive_mb=50,
        lang="zh+en",
    ),
}

DEFAULT_MODEL_ID = "melo-zh-en-44k"

VOICE_ROLE_PRESETS: list[dict] = [
    {
        "id": "melo-female-44k",
        "name": "Melo 女声 · 44.1k",
        "model_id": "melo-zh-en-44k",
        "sid": 0,
        "description": "中英混合，音质优先",
    },
    {
        "id": "melo-female-8k",
        "name": "Melo 女声 · 8k",
        "model_id": "melo-zh-en-8k",
        "sid": 0,
        "description": "中英混合，速度优先",
    },
]


def resolve_onnx_path(model_dir: Path, spec: ModelSpec | None = None) -> Path | None:
    """Find the ONNX weights file for a model directory."""
    candidates: list[Path] = []
    if spec and spec.onnx_name:
        candidates.append(model_dir / spec.onnx_name)
    candidates.extend(
        [
            model_dir / "model.onnx",
            model_dir / "model.int8.onnx",
        ]
    )
    if model_dir.is_dir():
        for p in sorted(model_dir.glob("*.onnx")):
            if p.name.lower().endswith(".onnx") and "rule" not in p.name.lower():
                candidates.append(p)
    seen: set[Path] = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        if p.is_file() and p.stat().st_size > 1000:
            return p
    return None


def model_files_ready(model_dir: Path, spec: ModelSpec | None = None) -> bool:
    onnx = resolve_onnx_path(model_dir, spec)
    tokens = model_dir / "tokens.txt"
    lexicon = model_dir / "lexicon.txt"
    return bool(onnx) and tokens.is_file() and lexicon.is_file()


def model_missing_files(model_dir: Path, spec: ModelSpec | None = None) -> list[str]:
    missing: list[str] = []
    if resolve_onnx_path(model_dir, spec) is None:
        missing.append(
            str(model_dir / (spec.onnx_name if spec and spec.onnx_name else "model.onnx"))
        )
    for name in ("lexicon.txt", "tokens.txt"):
        p = model_dir / name
        if not p.is_file():
            missing.append(str(p))
    return missing


def get_spec(model_id: str) -> ModelSpec | None:
    return MODEL_REGISTRY.get(model_id)


def list_downloadable() -> list[dict]:
    out = []
    for spec in MODEL_REGISTRY.values():
        ready = model_files_ready(spec.path, spec)
        out.append(
            {
                "id": spec.id,
                "name": spec.name,
                "dir": spec.dir_name,
                "archive": spec.archive,
                "archive_mb": spec.archive_mb,
                "bundle_default": spec.bundle_default,
                "num_speakers": spec.num_speakers,
                "ready": ready,
                "tags": list(spec.tags),
                "lang": spec.lang,
            }
        )
    return out
