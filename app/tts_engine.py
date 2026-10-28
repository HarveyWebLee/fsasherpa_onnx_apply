"""Sherpa-ONNX Offline TTS engine wrapper (multi-model + provider hot-switch)."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
import sherpa_onnx

ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = ROOT / "models"
DEFAULT_MODEL_ID = "melo-zh-en-44k"
DEFAULT_MODEL_DIR = MODELS_ROOT / "vits-melo-tts-zh_en"

_STREAM_DONE = object()


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    dir_name: str
    description: str
    expected_sample_rate: Optional[int] = None
    tags: tuple[str, ...] = ()

    @property
    def path(self) -> Path:
        return MODELS_ROOT / self.dir_name


# Registry of known models. dirs may be absent until downloaded.
MODEL_REGISTRY: dict[str, ModelSpec] = {
    "melo-zh-en-44k": ModelSpec(
        id="melo-zh-en-44k",
        name="Melo 中英 44.1kHz",
        dir_name="vits-melo-tts-zh_en",
        description="默认音质优先（int8 / 44.1 kHz）",
        expected_sample_rate=44100,
        tags=("default", "quality"),
    ),
    "melo-zh-en-8k": ModelSpec(
        id="melo-zh-en-8k",
        name="Melo 中英 8kHz",
        dir_name="vits-melo-tts-zh_en-8k",
        description="更快更小（8 kHz，音质下降）；目录独立，不替换 44.1k",
        expected_sample_rate=8000,
        tags=("fast", "8k"),
    ),
}


def _default_num_threads() -> int:
    env = os.environ.get("TTS_NUM_THREADS") or os.environ.get("SHERPA_ONNX_NUM_THREADS")
    if env:
        try:
            n = int(env)
            if n >= 1:
                return n
        except ValueError:
            pass
    return 2


def _default_provider() -> str:
    p = (os.environ.get("TTS_PROVIDER") or "cpu").strip().lower()
    if p in {"cpu", "cuda", "coreml"}:
        return p
    return "cpu"


def _resolve_model_id_from_env() -> str:
    mid = (os.environ.get("TTS_MODEL_ID") or "").strip()
    if mid and mid in MODEL_REGISTRY:
        return mid
    model_dir = os.environ.get("TTS_MODEL_DIR")
    if model_dir:
        p = Path(model_dir).resolve()
        for spec in MODEL_REGISTRY.values():
            if spec.path.resolve() == p:
                return spec.id
        # custom dir — register dynamically under id "custom"
        return "custom"
    return DEFAULT_MODEL_ID


def ensure_cuda_runtime_path() -> list[str]:
    """Prepend pip nvidia-*/bin dirs to PATH so ORT CUDA EP can load DLLs."""
    added: list[str] = []
    candidates = [
        Path(sys.prefix) / "Lib" / "site-packages" / "nvidia",
        ROOT / ".venv" / "Lib" / "site-packages" / "nvidia",
    ]
    site_packages = next((p for p in candidates if p.is_dir()), None)
    if site_packages is None:
        return added
    path_now = os.environ.get("PATH", "")
    parts = path_now.split(os.pathsep) if path_now else []
    for sub in sorted(site_packages.iterdir()):
        b = sub / "bin"
        if b.is_dir():
            s = str(b)
            if s not in parts:
                parts.insert(0, s)
                added.append(s)
    if added:
        os.environ["PATH"] = os.pathsep.join(parts)
    return added


def model_files_ready(model_dir: Path) -> bool:
    required = [model_dir / "model.onnx", model_dir / "lexicon.txt", model_dir / "tokens.txt"]
    return all(p.is_file() and p.stat().st_size > 0 for p in required)


def model_missing_files(model_dir: Path) -> list[str]:
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
        path = model_dir / name
        if name == "dict":
            if not path.is_dir():
                missing.append(str(path))
        elif not path.is_file():
            missing.append(str(path))
    return missing


@dataclass
class SynthResult:
    samples: np.ndarray
    sample_rate: int
    elapsed_seconds: float
    audio_duration: float
    rtf: float


class TtsEngine:
    """Lazy-loaded, thread-safe offline TTS (single OfflineTts; hot-switch model/provider)."""

    def __init__(
        self,
        model_dir: Optional[Path] = None,
        num_threads: Optional[int] = None,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        self.num_threads = int(num_threads) if num_threads is not None else _default_num_threads()
        self.provider = (provider or _default_provider()).lower()
        self._tts: Optional[sherpa_onnx.OfflineTts] = None
        self._lock = threading.RLock()
        self._load_elapsed: Optional[float] = None
        self._switch_count = 0
        self._busy = 0
        self._busy_cond = threading.Condition(self._lock)
        self._sample_rate: Optional[int] = None

        # Resolve model
        if model_dir is not None:
            self.model_dir = Path(model_dir)
            self.model_id = model_id or self._id_for_dir(self.model_dir) or "custom"
        elif model_id:
            self.model_id = model_id
            self.model_dir = self._dir_for_id(model_id)
        else:
            mid = _resolve_model_id_from_env()
            if mid == "custom":
                self.model_id = "custom"
                self.model_dir = Path(os.environ["TTS_MODEL_DIR"])
            else:
                self.model_id = mid
                self.model_dir = MODEL_REGISTRY[mid].path

    @staticmethod
    def _id_for_dir(path: Path) -> Optional[str]:
        try:
            resolved = path.resolve()
        except Exception:  # noqa: BLE001
            resolved = path
        for spec in MODEL_REGISTRY.values():
            try:
                if spec.path.resolve() == resolved:
                    return spec.id
            except Exception:  # noqa: BLE001
                if spec.path == path:
                    return spec.id
        return None

    @staticmethod
    def _dir_for_id(model_id: str) -> Path:
        if model_id not in MODEL_REGISTRY:
            raise ValueError(f"未知 model_id: {model_id}")
        return MODEL_REGISTRY[model_id].path

    def list_models(self) -> list[dict]:
        items: list[dict] = []
        for spec in MODEL_REGISTRY.values():
            ready = model_files_ready(spec.path)
            items.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "dir": str(spec.path),
                    "expected_sample_rate": spec.expected_sample_rate,
                    "tags": list(spec.tags),
                    "ready": ready,
                    "missing": model_missing_files(spec.path) if not ready else [],
                    "active": spec.id == self.model_id,
                }
            )
        # Include custom active dir if not in registry
        if self.model_id == "custom" or self._id_for_dir(self.model_dir) is None:
            ready = model_files_ready(self.model_dir)
            items.append(
                {
                    "id": "custom",
                    "name": "自定义 TTS_MODEL_DIR",
                    "description": str(self.model_dir),
                    "dir": str(self.model_dir),
                    "expected_sample_rate": None,
                    "tags": ["custom"],
                    "ready": ready,
                    "missing": model_missing_files(self.model_dir) if not ready else [],
                    "active": self.model_id == "custom" or True,
                }
            )
        return items

    def model_ready(self) -> bool:
        return model_files_ready(self.model_dir)

    def missing_files(self) -> list[str]:
        return model_missing_files(self.model_dir)

    def _build(self) -> sherpa_onnx.OfflineTts:
        if not self.model_ready():
            missing = ", ".join(self.missing_files()) or "unknown"
            raise FileNotFoundError(
                "模型未就绪，请先运行对应下载脚本。"
                f" model_id={self.model_id} 缺失: {missing}"
            )

        if self.provider == "cuda":
            ensure_cuda_runtime_path()

        model = str(self.model_dir / "model.onnx")
        lexicon = str(self.model_dir / "lexicon.txt")
        tokens = str(self.model_dir / "tokens.txt")
        rule_parts = [
            self.model_dir / "phone.fst",
            self.model_dir / "date.fst",
            self.model_dir / "number.fst",
        ]
        rule_fsts = ",".join(str(p) for p in rule_parts if p.is_file())

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
        self._sample_rate = int(tts.sample_rate)
        return tts

    def ensure_loaded(self) -> sherpa_onnx.OfflineTts:
        if self._tts is not None:
            return self._tts
        with self._lock:
            if self._tts is None:
                self._tts = self._build()
            return self._tts

    def preload(self) -> dict:
        tts = self.ensure_loaded()
        return {
            "sample_rate": int(tts.sample_rate),
            "num_threads": self.num_threads,
            "provider": self.provider,
            "model_id": self.model_id,
            "load_elapsed_seconds": self._load_elapsed,
            "model_dir": str(self.model_dir),
            "switch_count": self._switch_count,
        }

    def runtime_info(self) -> dict:
        spec = MODEL_REGISTRY.get(self.model_id)
        return {
            "num_threads": self.num_threads,
            "provider": self.provider,
            "model_id": self.model_id,
            "model_name": spec.name if spec else self.model_id,
            "model_loaded": self._tts is not None,
            "load_elapsed_seconds": self._load_elapsed,
            "model_dir": str(self.model_dir),
            "sample_rate": self._sample_rate,
            "expected_sample_rate": spec.expected_sample_rate if spec else None,
            "switch_count": self._switch_count,
            "busy": self._busy > 0,
            "cuda_available": self.cuda_runtime_present(),
        }

    @staticmethod
    def cuda_runtime_present() -> bool:
        lib = Path(sys.prefix) / "Lib" / "site-packages" / "sherpa_onnx" / "lib"
        ep = lib / "onnxruntime_providers_cuda.dll"
        if not ep.is_file():
            ep_so = lib / "libonnxruntime_providers_cuda.so"
            if not ep_so.is_file():
                return False
        nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
        if not nvidia.is_dir():
            nvidia = ROOT / ".venv" / "Lib" / "site-packages" / "nvidia"
        if not nvidia.is_dir():
            return False
        cudart = list(nvidia.glob("cuda_runtime/bin/cudart64_*.dll")) or list(
            nvidia.glob("cuda_runtime/**/libcudart.so*")
        )
        return bool(cudart)

    def _rebuild(
        self,
        *,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
        model_dir: Optional[Path] = None,
        warmup: bool = True,
        wait_busy_timeout: float = 120.0,
    ) -> dict:
        """Internal: wait for idle, apply model/provider changes, rebuild + warmup."""
        t_wait0 = time.perf_counter()
        with self._busy_cond:
            deadline = time.perf_counter() + float(wait_busy_timeout)
            while self._busy > 0:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError(
                        f"仍有 {self._busy} 个合成任务在进行，无法切换"
                    )
                self._busy_cond.wait(timeout=min(1.0, remaining))
            wait_s = time.perf_counter() - t_wait0

            prev_provider = self.provider
            prev_model = self.model_id
            prev_dir = str(self.model_dir)

            if provider is not None:
                p = provider.strip().lower()
                if p not in {"cpu", "cuda", "coreml"}:
                    raise ValueError("provider 必须是 cpu / cuda / coreml")
                if p == "cuda" and not self.cuda_runtime_present():
                    raise RuntimeError(
                        "当前环境未检测到 CUDA 运行时（sherpa CUDA EP DLL 或 nvidia pip 包）。"
                    )
                self.provider = p

            if model_id is not None or model_dir is not None:
                if model_id is not None:
                    mid = model_id.strip()
                    if mid not in MODEL_REGISTRY and mid != "custom":
                        raise ValueError(f"未知 model_id: {mid}。可选: {', '.join(MODEL_REGISTRY)}")
                    if mid == "custom":
                        if model_dir is None and self.model_id != "custom":
                            raise ValueError("custom model_id 需要同时提供 model_dir")
                        self.model_id = "custom"
                        if model_dir is not None:
                            self.model_dir = Path(model_dir)
                    else:
                        self.model_id = mid
                        self.model_dir = MODEL_REGISTRY[mid].path
                elif model_dir is not None:
                    self.model_dir = Path(model_dir)
                    self.model_id = self._id_for_dir(self.model_dir) or "custom"

            same = (
                self._tts is not None
                and prev_provider == self.provider
                and prev_model == self.model_id
                and prev_dir == str(self.model_dir)
            )
            if same:
                return {
                    "ok": True,
                    "changed": False,
                    "provider": self.provider,
                    "previous_provider": prev_provider,
                    "model_id": self.model_id,
                    "previous_model_id": prev_model,
                    "model_dir": str(self.model_dir),
                    "num_threads": self.num_threads,
                    "load_elapsed_seconds": self._load_elapsed,
                    "warmup_elapsed_seconds": 0.0,
                    "wait_busy_seconds": wait_s,
                    "switch_count": self._switch_count,
                    "sample_rate": self._sample_rate,
                    "message": "配置未变，无需重建",
                }

            if not self.model_ready():
                raise FileNotFoundError(
                    f"模型未就绪: {self.model_id} @ {self.model_dir}；"
                    f"缺失: {', '.join(self.missing_files()) or 'unknown'}"
                )

            old = self._tts
            self._tts = None
            self._load_elapsed = None
            self._sample_rate = None
            del old

            tts = self._build()
            self._tts = tts
            self._switch_count += 1
            load_s = self._load_elapsed or 0.0

            warmup_s = 0.0
            if warmup:
                tw = time.perf_counter()
                gen = sherpa_onnx.GenerationConfig()
                gen.sid = 0
                gen.speed = 1.0
                gen.silence_scale = 0.2
                _ = tts.generate("嗯。", gen)
                warmup_s = time.perf_counter() - tw

            return {
                "ok": True,
                "changed": True,
                "provider": self.provider,
                "previous_provider": prev_provider,
                "model_id": self.model_id,
                "previous_model_id": prev_model,
                "model_dir": str(self.model_dir),
                "model_name": (MODEL_REGISTRY[self.model_id].name
                               if self.model_id in MODEL_REGISTRY else self.model_id),
                "num_threads": self.num_threads,
                "load_elapsed_seconds": load_s,
                "warmup_elapsed_seconds": warmup_s,
                "wait_busy_seconds": wait_s,
                "switch_count": self._switch_count,
                "sample_rate": int(tts.sample_rate),
                "message": (
                    f"已切换 model {prev_model}→{self.model_id}, "
                    f"provider {prev_provider}→{self.provider}"
                ),
            }

    def set_provider(
        self,
        provider: str,
        *,
        warmup: bool = True,
        wait_busy_timeout: float = 120.0,
    ) -> dict:
        return self._rebuild(
            provider=provider, warmup=warmup, wait_busy_timeout=wait_busy_timeout
        )

    def set_model(
        self,
        model_id: str,
        *,
        warmup: bool = True,
        wait_busy_timeout: float = 120.0,
    ) -> dict:
        return self._rebuild(
            model_id=model_id, warmup=warmup, wait_busy_timeout=wait_busy_timeout
        )

    def _acquire_busy(self) -> None:
        with self._busy_cond:
            self._busy += 1

    def _release_busy(self) -> None:
        with self._busy_cond:
            self._busy = max(0, self._busy - 1)
            self._busy_cond.notify_all()

    def sample_rate(self) -> int:
        return int(self.ensure_loaded().sample_rate)

    def synthesize(self, text: str, sid: int = 0, speed: float = 1.0) -> SynthResult:
        text = (text or "").strip()
        if not text:
            raise ValueError("文本不能为空")
        if speed <= 0:
            raise ValueError("语速必须大于 0")

        gen = sherpa_onnx.GenerationConfig()
        gen.sid = int(sid)
        gen.speed = float(speed)
        gen.silence_scale = 0.2

        self._acquire_busy()
        start = time.perf_counter()
        try:
            tts = self.ensure_loaded()
            with self._lock:
                audio = tts.generate(text, gen)
        finally:
            self._release_busy()
        elapsed = time.perf_counter() - start

        if audio is None or len(audio.samples) == 0:
            raise RuntimeError("合成失败：未生成音频（请检查英文词是否在 lexicon.txt 中）")

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
        text = (text or "").strip()
        if not text:
            yield ("error", "文本不能为空")
            return
        if speed <= 0:
            yield ("error", "语速必须大于 0")
            return

        q: queue.Queue = queue.Queue(maxsize=256)
        cancel = cancel_event or threading.Event()
        result_box: dict = {}
        meta_ready = threading.Event()

        def callback(samples, progress: float) -> int:
            if cancel.is_set():
                return 0
            arr = np.array(samples, dtype=np.float32, copy=True).reshape(-1)
            try:
                q.put(("chunk", arr), timeout=0.5)
            except queue.Full:
                if cancel.is_set():
                    return 0
                q.put(("chunk", arr))
            q.put(("progress", float(progress)))
            return 0 if cancel.is_set() else 1

        def worker() -> None:
            gen = sherpa_onnx.GenerationConfig()
            gen.sid = int(sid)
            gen.speed = float(speed)
            gen.silence_scale = 0.2
            self._acquire_busy()
            start = time.perf_counter()
            sample_rate = 0
            try:
                tts = self.ensure_loaded()
                sample_rate = int(tts.sample_rate)
                q.put(
                    (
                        "meta",
                        {
                            "sample_rate": sample_rate,
                            "channels": 1,
                            "format": "f32le",
                            "dtype": "float32",
                            "num_threads": self.num_threads,
                            "provider": self.provider,
                            "model_id": self.model_id,
                        },
                    )
                )
                meta_ready.set()
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
                    "model_id": self.model_id,
                }
            except Exception as exc:  # noqa: BLE001
                result_box["error"] = str(exc)
                if not meta_ready.is_set():
                    q.put(
                        (
                            "meta",
                            {
                                "sample_rate": sample_rate or 44100,
                                "channels": 1,
                                "format": "f32le",
                                "dtype": "float32",
                                "num_threads": self.num_threads,
                                "provider": self.provider,
                                "model_id": self.model_id,
                            },
                        )
                    )
                    meta_ready.set()
            finally:
                self._release_busy()
                q.put((_STREAM_DONE, None))

        thread = threading.Thread(target=worker, name="tts-stream", daemon=True)
        thread.start()

        last_progress = -1.0
        while True:
            kind, payload = q.get()
            if kind is _STREAM_DONE:
                break
            if kind == "progress":
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
    model_id = os.environ.get("TTS_MODEL_ID")
    return TtsEngine(
        model_dir=Path(model_dir) if model_dir else None,
        model_id=model_id if model_id else None,
    )


engine = _engine_from_env()
