"""Sherpa-ONNX Offline TTS engine wrapper."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import sherpa_onnx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = ROOT / "models" / "vits-melo-tts-zh_en"


@dataclass
class SynthResult:
    samples: np.ndarray
    sample_rate: int
    elapsed_seconds: float
    audio_duration: float
    rtf: float


class TtsEngine:
    """Lazy-loaded, thread-safe Offline TTS."""

    def __init__(self, model_dir: Optional[Path] = None, num_threads: int = 2) -> None:
        self.model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.num_threads = num_threads
        self._tts: Optional[sherpa_onnx.OfflineTts] = None
        self._lock = threading.Lock()

    def model_ready(self) -> bool:
        required = [
            self.model_dir / "model.onnx",
            self.model_dir / "lexicon.txt",
            self.model_dir / "tokens.txt",
        ]
        return all(p.is_file() for p in required)

    def missing_files(self) -> list[str]:
        names = [
            "model.onnx",
            "lexicon.txt",
            "tokens.txt",
            "phone.fst",
            "date.fst",
            "number.fst",
            "dict",
        ]
        missing: list[str] = []
        for name in names:
            path = self.model_dir / name
            if name == "dict":
                if not path.is_dir():
                    missing.append(str(path))
            elif not path.is_file():
                missing.append(str(path))
        return missing

    def _build(self) -> sherpa_onnx.OfflineTts:
        if not self.model_ready():
            missing = ", ".join(self.missing_files()) or "unknown"
            raise FileNotFoundError(
                f"模型未就绪，请先运行 scripts/download_model.ps1。"
                f" 缺失: {missing}"
            )

        model = str(self.model_dir / "model.onnx")
        lexicon = str(self.model_dir / "lexicon.txt")
        tokens = str(self.model_dir / "tokens.txt")
        rule_parts = [
            self.model_dir / "phone.fst",
            self.model_dir / "date.fst",
            self.model_dir / "number.fst",
        ]
        rule_fsts = ",".join(str(p) for p in rule_parts if p.is_file())

        vits_kwargs = dict(
            model=model,
            lexicon=lexicon,
            tokens=tokens,
        )
        # note: since sherpa-onnx v1.12.15, dict_dir is unused for Melo; keep dict/ for completeness

        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(**vits_kwargs),
                provider="cpu",
                debug=False,
                num_threads=self.num_threads,
            ),
            rule_fsts=rule_fsts,
            max_num_sentences=2,
        )
        if not config.validate():
            raise ValueError("OfflineTtsConfig 校验失败，请检查模型文件路径。")
        return sherpa_onnx.OfflineTts(config)

    def ensure_loaded(self) -> sherpa_onnx.OfflineTts:
        with self._lock:
            if self._tts is None:
                self._tts = self._build()
            return self._tts

    def synthesize(self, text: str, sid: int = 0, speed: float = 1.0) -> SynthResult:
        text = (text or "").strip()
        if not text:
            raise ValueError("文本不能为空")
        if speed <= 0:
            raise ValueError("语速必须大于 0")

        tts = self.ensure_loaded()
        gen = sherpa_onnx.GenerationConfig()
        gen.sid = int(sid)
        gen.speed = float(speed)
        gen.silence_scale = 0.2

        start = time.time()
        with self._lock:
            audio = tts.generate(text, gen)
        elapsed = time.time() - start

        if audio is None or len(audio.samples) == 0:
            raise RuntimeError("合成失败：未生成音频（请检查英文词是否在 lexicon.txt 中）")

        samples = np.asarray(audio.samples, dtype=np.float32)
        duration = float(len(samples) / audio.sample_rate)
        rtf = elapsed / duration if duration > 0 else 0.0
        return SynthResult(
            samples=samples,
            sample_rate=int(audio.sample_rate),
            elapsed_seconds=elapsed,
            audio_duration=duration,
            rtf=rtf,
        )


# singleton used by web app / CLI
engine = TtsEngine()
