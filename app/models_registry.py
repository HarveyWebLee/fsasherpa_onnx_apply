"""Model registry for sherpa-onnx TTS (zh+en Melo + Kokoro)."""

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
    # Backend: "vits" (Melo) or "kokoro"
    backend: str = "vits"
    # Whether OfflineTts callback streaming is supported for this model
    supports_stream: bool = True

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

_KOKORO_SPEAKERS = (
    {"sid": 0, "name": "af_maple", "lang": "zh+en", "note": "美式英语音色"},
    {"sid": 1, "name": "af_sol", "lang": "zh+en", "note": "美式英语音色"},
    {"sid": 2, "name": "bf_vale", "lang": "zh+en", "note": "英式英语音色"},
    {"sid": 3, "name": "zf_001", "lang": "zh+en", "note": "中文女声"},
    {"sid": 4, "name": "zf_002", "lang": "zh+en", "note": "中文女声"},
    {"sid": 5, "name": "zf_003", "lang": "zh+en", "note": "中文女声"},
    {"sid": 6, "name": "zf_004", "lang": "zh+en", "note": "中文女声"},
    {"sid": 7, "name": "zf_005", "lang": "zh+en", "note": "中文女声"},
    {"sid": 8, "name": "zf_006", "lang": "zh+en", "note": "中文女声"},
    {"sid": 9, "name": "zf_007", "lang": "zh+en", "note": "中文女声"},
    {"sid": 10, "name": "zf_008", "lang": "zh+en", "note": "中文女声"},
    {"sid": 11, "name": "zf_017", "lang": "zh+en", "note": "中文女声"},
    {"sid": 12, "name": "zf_018", "lang": "zh+en", "note": "中文女声"},
    {"sid": 13, "name": "zf_019", "lang": "zh+en", "note": "中文女声"},
    {"sid": 14, "name": "zf_021", "lang": "zh+en", "note": "中文女声"},
    {"sid": 15, "name": "zf_022", "lang": "zh+en", "note": "中文女声"},
    {"sid": 16, "name": "zf_023", "lang": "zh+en", "note": "中文女声"},
    {"sid": 17, "name": "zf_024", "lang": "zh+en", "note": "中文女声"},
    {"sid": 18, "name": "zf_026", "lang": "zh+en", "note": "中文女声"},
    {"sid": 19, "name": "zf_027", "lang": "zh+en", "note": "中文女声"},
    {"sid": 20, "name": "zf_028", "lang": "zh+en", "note": "中文女声"},
    {"sid": 21, "name": "zf_032", "lang": "zh+en", "note": "中文女声"},
    {"sid": 22, "name": "zf_036", "lang": "zh+en", "note": "中文女声"},
    {"sid": 23, "name": "zf_038", "lang": "zh+en", "note": "中文女声"},
    {"sid": 24, "name": "zf_039", "lang": "zh+en", "note": "中文女声"},
    {"sid": 25, "name": "zf_040", "lang": "zh+en", "note": "中文女声"},
    {"sid": 26, "name": "zf_042", "lang": "zh+en", "note": "中文女声"},
    {"sid": 27, "name": "zf_043", "lang": "zh+en", "note": "中文女声"},
    {"sid": 28, "name": "zf_044", "lang": "zh+en", "note": "中文女声"},
    {"sid": 29, "name": "zf_046", "lang": "zh+en", "note": "中文女声"},
    {"sid": 30, "name": "zf_047", "lang": "zh+en", "note": "中文女声"},
    {"sid": 31, "name": "zf_048", "lang": "zh+en", "note": "中文女声"},
    {"sid": 32, "name": "zf_049", "lang": "zh+en", "note": "中文女声"},
    {"sid": 33, "name": "zf_051", "lang": "zh+en", "note": "中文女声"},
    {"sid": 34, "name": "zf_059", "lang": "zh+en", "note": "中文女声"},
    {"sid": 35, "name": "zf_060", "lang": "zh+en", "note": "中文女声"},
    {"sid": 36, "name": "zf_067", "lang": "zh+en", "note": "中文女声"},
    {"sid": 37, "name": "zf_070", "lang": "zh+en", "note": "中文女声"},
    {"sid": 38, "name": "zf_071", "lang": "zh+en", "note": "中文女声"},
    {"sid": 39, "name": "zf_072", "lang": "zh+en", "note": "中文女声"},
    {"sid": 40, "name": "zf_073", "lang": "zh+en", "note": "中文女声"},
    {"sid": 41, "name": "zf_074", "lang": "zh+en", "note": "中文女声"},
    {"sid": 42, "name": "zf_075", "lang": "zh+en", "note": "中文女声"},
    {"sid": 43, "name": "zf_076", "lang": "zh+en", "note": "中文女声"},
    {"sid": 44, "name": "zf_077", "lang": "zh+en", "note": "中文女声"},
    {"sid": 45, "name": "zf_078", "lang": "zh+en", "note": "中文女声"},
    {"sid": 46, "name": "zf_079", "lang": "zh+en", "note": "中文女声"},
    {"sid": 47, "name": "zf_083", "lang": "zh+en", "note": "中文女声"},
    {"sid": 48, "name": "zf_084", "lang": "zh+en", "note": "中文女声"},
    {"sid": 49, "name": "zf_085", "lang": "zh+en", "note": "中文女声"},
    {"sid": 50, "name": "zf_086", "lang": "zh+en", "note": "中文女声"},
    {"sid": 51, "name": "zf_087", "lang": "zh+en", "note": "中文女声"},
    {"sid": 52, "name": "zf_088", "lang": "zh+en", "note": "中文女声"},
    {"sid": 53, "name": "zf_090", "lang": "zh+en", "note": "中文女声"},
    {"sid": 54, "name": "zf_092", "lang": "zh+en", "note": "中文女声"},
    {"sid": 55, "name": "zf_093", "lang": "zh+en", "note": "中文女声"},
    {"sid": 56, "name": "zf_094", "lang": "zh+en", "note": "中文女声"},
    {"sid": 57, "name": "zf_099", "lang": "zh+en", "note": "中文女声"},
    {"sid": 58, "name": "zm_009", "lang": "zh+en", "note": "中文男声"},
    {"sid": 59, "name": "zm_010", "lang": "zh+en", "note": "中文男声"},
    {"sid": 60, "name": "zm_011", "lang": "zh+en", "note": "中文男声"},
    {"sid": 61, "name": "zm_012", "lang": "zh+en", "note": "中文男声"},
    {"sid": 62, "name": "zm_013", "lang": "zh+en", "note": "中文男声"},
    {"sid": 63, "name": "zm_014", "lang": "zh+en", "note": "中文男声"},
    {"sid": 64, "name": "zm_015", "lang": "zh+en", "note": "中文男声"},
    {"sid": 65, "name": "zm_016", "lang": "zh+en", "note": "中文男声"},
    {"sid": 66, "name": "zm_020", "lang": "zh+en", "note": "中文男声"},
    {"sid": 67, "name": "zm_025", "lang": "zh+en", "note": "中文男声"},
    {"sid": 68, "name": "zm_029", "lang": "zh+en", "note": "中文男声"},
    {"sid": 69, "name": "zm_030", "lang": "zh+en", "note": "中文男声"},
    {"sid": 70, "name": "zm_031", "lang": "zh+en", "note": "中文男声"},
    {"sid": 71, "name": "zm_033", "lang": "zh+en", "note": "中文男声"},
    {"sid": 72, "name": "zm_034", "lang": "zh+en", "note": "中文男声"},
    {"sid": 73, "name": "zm_035", "lang": "zh+en", "note": "中文男声"},
    {"sid": 74, "name": "zm_037", "lang": "zh+en", "note": "中文男声"},
    {"sid": 75, "name": "zm_041", "lang": "zh+en", "note": "中文男声"},
    {"sid": 76, "name": "zm_045", "lang": "zh+en", "note": "中文男声"},
    {"sid": 77, "name": "zm_050", "lang": "zh+en", "note": "中文男声"},
    {"sid": 78, "name": "zm_052", "lang": "zh+en", "note": "中文男声"},
    {"sid": 79, "name": "zm_053", "lang": "zh+en", "note": "中文男声"},
    {"sid": 80, "name": "zm_054", "lang": "zh+en", "note": "中文男声"},
    {"sid": 81, "name": "zm_055", "lang": "zh+en", "note": "中文男声"},
    {"sid": 82, "name": "zm_056", "lang": "zh+en", "note": "中文男声"},
    {"sid": 83, "name": "zm_057", "lang": "zh+en", "note": "中文男声"},
    {"sid": 84, "name": "zm_058", "lang": "zh+en", "note": "中文男声"},
    {"sid": 85, "name": "zm_061", "lang": "zh+en", "note": "中文男声"},
    {"sid": 86, "name": "zm_062", "lang": "zh+en", "note": "中文男声"},
    {"sid": 87, "name": "zm_063", "lang": "zh+en", "note": "中文男声"},
    {"sid": 88, "name": "zm_064", "lang": "zh+en", "note": "中文男声"},
    {"sid": 89, "name": "zm_065", "lang": "zh+en", "note": "中文男声"},
    {"sid": 90, "name": "zm_066", "lang": "zh+en", "note": "中文男声"},
    {"sid": 91, "name": "zm_068", "lang": "zh+en", "note": "中文男声"},
    {"sid": 92, "name": "zm_069", "lang": "zh+en", "note": "中文男声"},
    {"sid": 93, "name": "zm_080", "lang": "zh+en", "note": "中文男声"},
    {"sid": 94, "name": "zm_081", "lang": "zh+en", "note": "中文男声"},
    {"sid": 95, "name": "zm_082", "lang": "zh+en", "note": "中文男声"},
    {"sid": 96, "name": "zm_089", "lang": "zh+en", "note": "中文男声"},
    {"sid": 97, "name": "zm_091", "lang": "zh+en", "note": "中文男声"},
    {"sid": 98, "name": "zm_095", "lang": "zh+en", "note": "中文男声"},
    {"sid": 99, "name": "zm_096", "lang": "zh+en", "note": "中文男声"},
    {"sid": 100, "name": "zm_097", "lang": "zh+en", "note": "中文男声"},
    {"sid": 101, "name": "zm_098", "lang": "zh+en", "note": "中文男声"},
    {"sid": 102, "name": "zm_100", "lang": "zh+en", "note": "中文男声"},
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
        backend="vits",
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
        backend="vits",
    ),
    "kokoro-zh-en-v1_1": ModelSpec(
        id="kokoro-zh-en-v1_1",
        name="Kokoro 中英 v1.1 (int8)",
        dir_name="kokoro-int8-multi-lang-v1_1",
        description="中英混合 · Kokoro multi-lang v1.1 int8 · 103 说话人 · 24 kHz",
        num_speakers=103,
        expected_sample_rate=24000,
        tags=("multi-speaker", "zh-en", "kokoro", "int8"),
        speakers=_KOKORO_SPEAKERS,
        onnx_name="model.int8.onnx",
        bundle_default=False,
        archive="kokoro-int8-multi-lang-v1_1.tar.bz2",
        archive_mb=120,
        lang="zh+en",
        backend="kokoro",
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
        "id": "kokoro-zf-001",
        "name": "Kokoro zf_001",
        "model_id": "kokoro-zh-en-v1_1",
        "sid": 3,
        "description": "Kokoro 中文女声示例",
    },
    {
        "id": "kokoro-af-maple",
        "name": "Kokoro af_maple",
        "model_id": "kokoro-zh-en-v1_1",
        "sid": 0,
        "description": "Kokoro 美式女声示例",
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


def _kokoro_lexicon_paths(model_dir: Path) -> list[Path]:
    """Preferred lexicon files for Kokoro zh+en (comma-joined at load time)."""
    zh = model_dir / "lexicon-zh.txt"
    us = model_dir / "lexicon-us-en.txt"
    gb = model_dir / "lexicon-gb-en.txt"
    found: list[Path] = []
    if us.is_file():
        found.append(us)
    elif gb.is_file():
        found.append(gb)
    if zh.is_file():
        found.append(zh)
    return found


def model_files_ready(model_dir: Path, spec: ModelSpec | None = None) -> bool:
    onnx = resolve_onnx_path(model_dir, spec)
    tokens = model_dir / "tokens.txt"
    if not onnx or not tokens.is_file():
        return False
    backend = (spec.backend if spec else "vits") or "vits"
    if backend == "kokoro":
        voices = model_dir / "voices.bin"
        data_dir = model_dir / "espeak-ng-data"
        lexica = _kokoro_lexicon_paths(model_dir)
        return voices.is_file() and data_dir.is_dir() and len(lexica) >= 2
    lexicon = model_dir / "lexicon.txt"
    return lexicon.is_file()


def model_missing_files(model_dir: Path, spec: ModelSpec | None = None) -> list[str]:
    missing: list[str] = []
    if resolve_onnx_path(model_dir, spec) is None:
        missing.append(
            str(model_dir / (spec.onnx_name if spec and spec.onnx_name else "model.onnx"))
        )
    tokens = model_dir / "tokens.txt"
    if not tokens.is_file():
        missing.append(str(tokens))
    backend = (spec.backend if spec else "vits") or "vits"
    if backend == "kokoro":
        for name in ("voices.bin",):
            p = model_dir / name
            if not p.is_file():
                missing.append(str(p))
        data_dir = model_dir / "espeak-ng-data"
        if not data_dir.is_dir():
            missing.append(str(data_dir))
        lexica = _kokoro_lexicon_paths(model_dir)
        if not any(p.name.startswith("lexicon-") and "en" in p.name for p in lexica):
            missing.append(str(model_dir / "lexicon-us-en.txt"))
        if not any(p.name == "lexicon-zh.txt" for p in lexica):
            missing.append(str(model_dir / "lexicon-zh.txt"))
    else:
        lexicon = model_dir / "lexicon.txt"
        if not lexicon.is_file():
            missing.append(str(lexicon))
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
                "backend": spec.backend,
                "supports_stream": spec.supports_stream,
            }
        )
    return out
