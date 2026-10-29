"""Model registry for multi-speaker sherpa-onnx TTS models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os

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
    expected_sample_rate: Optional[int] = None
    tags: tuple[str, ...] = ()
    speakers: tuple[dict, ...] = ()
    # Explicit ONNX filename inside model dir (None = auto-detect)
    onnx_name: Optional[str] = None
    # Whether default packaging should include this model
    bundle_default: bool = False
    # Download archive name on GitHub tts-models release
    archive: Optional[str] = None
    # Approximate download size (MB, compressed)
    archive_mb: float = 0.0
    lang: str = "zh"

    @property
    def path(self) -> Path:
        return models_root() / self.dir_name


def _spk(n: int, name: Optional[str] = None, note: str = "") -> dict:
    return {
        "sid": n,
        "name": name or f"说话人 {n}",
        "lang": "zh",
        "note": note,
    }


def _spk_range(count: int, prefix: str = "说话人") -> tuple[dict, ...]:
    return tuple(_spk(i, f"{prefix} {i}") for i in range(count))


_MELO_SPEAKERS = (
    {
        "sid": 0,
        "name": "默认女声",
        "lang": "zh+en",
        "note": "中英混合；官方单说话人女声",
    },
)

_ZH_LL_SPEAKERS = (
    _spk(0, "说话人 0", "zh-ll 多说话人"),
    _spk(1, "说话人 1", "zh-ll 多说话人"),
    _spk(2, "说话人 2", "zh-ll 多说话人"),
    _spk(3, "说话人 3", "zh-ll 多说话人"),
    _spk(4, "说话人 4", "zh-ll 多说话人"),
)

MODEL_REGISTRY: dict[str, ModelSpec] = {
    "melo-zh-en-44k": ModelSpec(
        id="melo-zh-en-44k",
        name="Melo 中英 44.1kHz",
        dir_name="vits-melo-tts-zh_en",
        description="中英混合 · 音质优先（44.1 kHz，单女声）",
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
        description="中英混合 · 更快更小（8 kHz）",
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
    "zh-ll": ModelSpec(
        id="zh-ll",
        name="中文多说话人 zh-ll（5）",
        dir_name="sherpa-onnx-vits-zh-ll",
        description="纯中文 · 5 个说话人 · 16 kHz",
        num_speakers=5,
        expected_sample_rate=16000,
        tags=("multi", "zh"),
        speakers=_ZH_LL_SPEAKERS,
        onnx_name="model.onnx",
        bundle_default=True,
        archive="sherpa-onnx-vits-zh-ll.tar.bz2",
        archive_mb=115,
        lang="zh",
    ),
    "fanchen-c": ModelSpec(
        id="fanchen-c",
        name="范晨 C（187 说话人）",
        dir_name="vits-zh-hf-fanchen-C",
        description="纯中文 · 187 说话人 · 16 kHz",
        num_speakers=187,
        expected_sample_rate=16000,
        tags=("multi", "zh", "large"),
        speakers=_spk_range(187),
        onnx_name="vits-zh-hf-fanchen-C.onnx",
        bundle_default=False,
        archive="vits-zh-hf-fanchen-C.tar.bz2",
        archive_mb=114,
        lang="zh",
    ),
    "aishell3": ModelSpec(
        id="aishell3",
        name="AISHELL-3（174 说话人）",
        dir_name="vits-icefall-zh-aishell3",
        description="纯中文 · icefall AISHELL-3 · 174 说话人 · 8 kHz · 体积小",
        num_speakers=174,
        expected_sample_rate=8000,
        tags=("multi", "zh", "fast"),
        speakers=_spk_range(174),
        onnx_name="model.int8.onnx",
        bundle_default=True,
        archive="vits-icefall-zh-aishell3.tar.bz2",
        archive_mb=30,
        lang="zh",
    ),
    "theresa": ModelSpec(
        id="theresa",
        name="Theresa（804 说话人）",
        dir_name="vits-zh-hf-theresa",
        description="纯中文 · 804 说话人 · 22.05 kHz（体积较大，默认不打包）",
        num_speakers=804,
        expected_sample_rate=22050,
        tags=("multi", "zh", "huge"),
        speakers=_spk_range(804),
        onnx_name="theresa.onnx",
        bundle_default=False,
        archive="vits-zh-hf-theresa.tar.bz2",
        archive_mb=115,
        lang="zh",
    ),
    "eula": ModelSpec(
        id="eula",
        name="Eula（804 说话人）",
        dir_name="vits-zh-hf-eula",
        description="纯中文 · 804 说话人 · 22.05 kHz（体积较大，默认不打包）",
        num_speakers=804,
        expected_sample_rate=22050,
        tags=("multi", "zh", "huge"),
        speakers=_spk_range(804),
        onnx_name="eula.onnx",
        bundle_default=False,
        archive="vits-zh-hf-eula.tar.bz2",
        archive_mb=115,
        lang="zh",
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
    {
        "id": "zh-ll-0",
        "name": "zh-ll · 说话人 0",
        "model_id": "zh-ll",
        "sid": 0,
        "description": "中文多说话人",
    },
    {
        "id": "aishell3-10",
        "name": "AISHELL-3 · 说话人 10",
        "model_id": "aishell3",
        "sid": 10,
        "description": "AISHELL-3 示例音色",
    },
    {
        "id": "fanchen-14",
        "name": "范晨 C · 说话人 14",
        "model_id": "fanchen-c",
        "sid": 14,
        "description": "范晨多说话人示例",
    },
]


def resolve_onnx_path(model_dir: Path, spec: Optional[ModelSpec] = None) -> Optional[Path]:
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
    # Any *.onnx except rule-like names
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


def model_files_ready(model_dir: Path, spec: Optional[ModelSpec] = None) -> bool:
    onnx = resolve_onnx_path(model_dir, spec)
    tokens = model_dir / "tokens.txt"
    lexicon = model_dir / "lexicon.txt"
    return bool(onnx) and tokens.is_file() and lexicon.is_file()


def model_missing_files(model_dir: Path, spec: Optional[ModelSpec] = None) -> list[str]:
    missing: list[str] = []
    if resolve_onnx_path(model_dir, spec) is None:
        missing.append(str(model_dir / (spec.onnx_name if spec and spec.onnx_name else "model.onnx")))
    for name in ("lexicon.txt", "tokens.txt"):
        p = model_dir / name
        if not p.is_file():
            missing.append(str(p))
    return missing


def get_spec(model_id: str) -> Optional[ModelSpec]:
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
            }
        )
    return out
