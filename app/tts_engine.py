"""Sherpa-ONNX Offline TTS engine wrapper (performance-tuned)."""

from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
import sherpa_onnx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = ROOT / "models" / "vits-melo-tts-zh_en"

_STREAM_DONE = object()


def _default_num_threads() -> int:
    """Prefer more ORT threads on multi-core CPUs; overridable via env."""
    env = os.environ.get("TTS_NUM_THREADS") or os.environ.get("SHERPA_ONNX_NUM_THREADS")
    if env:
        try:
            n = int(env)
            if n >= 1:
                return n
        except ValueError:
            pass
    # Measured on Intel i5-10200H + Melo int8 44.1kHz: threads=2 beat 4/6/8.
    # More threads often *slow down* this model on laptop CPUs. Override via env.
    return 2


def _default_provider() -> str:
    p = (os.environ.get("TTS_PROVIDER") or "cpu").strip().lower()
    if p in {"cpu", "cuda", "coreml"}:
        return p
    return "cpu"


@dataclass
class SynthResult:
    samples: np.ndarray
    sample_rate: int
    elapsed_seconds: float
    audio_duration: float
    rtf: float


class TtsEngine:
    """Lazy-loaded, thread-safe offline TTS (single OfflineTts instance)."""

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        num_threads: Optional[int] = None,
        provider: Optional[str] = None,
    ) -> None:
        self.model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.num_threads = int(num_threads) if num_threads is not None else _default_num_threads()
        self.provider = (provider or _default_provider()).lower()
        self._tts: Optional[sherpa_onnx.OfflineTts] = None
        self._lock = threading.Lock()
        self._load_elapsed: Optional[float] = None

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
                "模型未就绪，请先运行 scripts/download_model.ps1。"
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

        # max_num_sentences=1: stream callback fires per sentence (lower first-chunk latency)
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=model,
                    lexicon=lexicon,
                    tokens=tokens,
                ),
                provider=self.provider,
                debug=False,
                num_threads=self.num_threads,
            ),
            rule_fsts=rule_fsts,
            max_num_sentences=1,
        )
        if not config.validate():
            raise ValueError("OfflineTtsConfig 校验失败，请检查模型文件路径。")
        t0 = time.perf_counter()
        tts = sherpa_onnx.OfflineTts(config)
        self._load_elapsed = time.perf_counter() - t0
        return tts

    def ensure_loaded(self) -> sherpa_onnx.OfflineTts:
        # Double-checked locking: model loaded exactly once.
        if self._tts is not None:
            return self._tts
        with self._lock:
            if self._tts is None:
                self._tts = self._build()
            return self._tts

    def preload(self) -> dict:
        """Eagerly load the model (call at app startup)."""
        tts = self.ensure_loaded()
        return {
            "sample_rate": int(tts.sample_rate),
            "num_threads": self.num_threads,
            "provider": self.provider,
            "load_elapsed_seconds": self._load_elapsed,
            "model_dir": str(self.model_dir),
        }

    def runtime_info(self) -> dict:
        return {
            "num_threads": self.num_threads,
            "provider": self.provider,
            "model_loaded": self._tts is not None,
            "load_elapsed_seconds": self._load_elapsed,
            "model_dir": str(self.model_dir),
        }

    def sample_rate(self) -> int:
        return int(self.ensure_loaded().sample_rate)

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

        start = time.perf_counter()
        with self._lock:
            audio = tts.generate(text, gen)
        elapsed = time.perf_counter() - start

        if audio is None or len(audio.samples) == 0:
            raise RuntimeError("合成失败：未生成音频（请检查英文词是否在 lexicon.txt 中）")

        # asarray without forced copy when already float32 contiguous
        samples = np.asarray(audio.samples, dtype=np.float32)
        if not samples.flags["C_CONTIGUOUS"]:
            samples = np.ascontiguousarray(samples)
        duration = float(len(samples) / audio.sample_rate)
        rtf = elapsed / duration if duration > 0 else 0.0
        return SynthResult(
            samples=samples,
            sample_rate=int(audio.sample_rate),
            elapsed_seconds=elapsed,
            audio_duration=duration,
            rtf=rtf,
        )

    def synthesize_stream(
        self,
        text: str,
        sid: int = 0,
        speed: float = 1.0,
        cancel_event: Optional[threading.Event] = None,
    ) -> Iterator[tuple[str, object]]:
        """Yield streaming events from OfflineTts callback.

        Yields:
          ("meta", dict)
          ("chunk", np.ndarray float32)
          ("progress", float)
          ("end", dict)
          ("error", str)
        """
        text = (text or "").strip()
        if not text:
            yield ("error", "文本不能为空")
            return
        if speed <= 0:
            yield ("error", "语速必须大于 0")
            return

        tts = self.ensure_loaded()
        sample_rate = int(tts.sample_rate)
        yield (
            "meta",
            {
                "sample_rate": sample_rate,
                "channels": 1,
                "format": "f32le",
                "dtype": "float32",
                "num_threads": self.num_threads,
                "provider": self.provider,
            },
        )

        # Larger queue reduces producer stalls when WebSocket is briefly slow.
        q: queue.Queue = queue.Queue(maxsize=256)
        cancel = cancel_event or threading.Event()
        result_box: dict = {}

        def callback(samples, progress: float) -> int:
            if cancel.is_set():
                return 0
            # Copy once: ORT/sherpa may reuse the underlying buffer.
            arr = np.array(samples, dtype=np.float32, copy=True).reshape(-1)
            try:
                q.put(("chunk", arr), timeout=0.5)
            except queue.Full:
                # Prefer keeping audio; drop only if cancelled
                if cancel.is_set():
                    return 0
                q.put(("chunk", arr))
            # progress is cheap JSON; skip ultra-fine duplicates later in consumer if needed
            q.put(("progress", float(progress)))
            return 0 if cancel.is_set() else 1

        def worker() -> None:
            gen = sherpa_onnx.GenerationConfig()
            gen.sid = int(sid)
            gen.speed = float(speed)
            gen.silence_scale = 0.2
            start = time.perf_counter()
            try:
                with self._lock:
                    audio = tts.generate(text, gen, callback)
                elapsed = time.perf_counter() - start
                samples = (
                    np.asarray(audio.samples, dtype=np.float32)
                    if audio is not None
                    else np.zeros(0, dtype=np.float32)
                )
                duration = float(len(samples) / sample_rate) if sample_rate else 0.0
                result_box["end"] = {
                    "elapsed_seconds": elapsed,
                    "elapsed_ms": round(elapsed * 1000.0, 1),
                    "audio_duration": duration,
                    "num_samples": int(len(samples)),
                    "sample_rate": sample_rate,
                    "rtf": (elapsed / duration) if duration > 0 else 0.0,
                    "num_threads": self.num_threads,
                    "provider": self.provider,
                }
            except Exception as exc:  # noqa: BLE001
                result_box["error"] = str(exc)
            finally:
                q.put((_STREAM_DONE, None))

        thread = threading.Thread(target=worker, name="tts-stream", daemon=True)
        thread.start()

        last_progress = -1.0
        while True:
            kind, payload = q.get()
            if kind is _STREAM_DONE:
                break
            if kind == "progress":
                # Coalesce near-identical progress to cut WS chatter
                p = float(payload)
                if abs(p - last_progress) < 0.02 and p < 0.999:
                    continue
                last_progress = p
            yield (kind, payload)

        thread.join(timeout=1.0)
        if "error" in result_box:
            yield ("error", result_box["error"])
            return
        if "end" in result_box:
            yield ("end", result_box["end"])
        else:
            yield ("error", "合成线程异常结束")


def _engine_from_env() -> TtsEngine:
    model_dir = os.environ.get("TTS_MODEL_DIR")
    return TtsEngine(model_dir=Path(model_dir) if model_dir else None)


engine = _engine_from_env()
