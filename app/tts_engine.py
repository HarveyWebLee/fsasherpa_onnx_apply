"""Sherpa-ONNX Offline TTS — multi-model pool + high-concurrency queue."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
import sherpa_onnx

from .models_registry import (
    DEFAULT_MODEL_ID,
    MODEL_REGISTRY,
    VOICE_ROLE_PRESETS,
    ModelSpec,
    get_spec,
    model_files_ready,
    model_missing_files,
    models_root,
    resolve_onnx_path,
)

ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = models_root()

_STREAM_DONE = object()

SPEED_MIN = 0.5
SPEED_MAX = 2.0
SPEED_DEFAULT = 1.0


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _default_num_threads() -> int:
    return _env_int("TTS_NUM_THREADS", _env_int("SHERPA_ONNX_NUM_THREADS", 2))


def _default_provider() -> str:
    p = (os.environ.get("TTS_PROVIDER") or "cpu").strip().lower()
    return p if p in {"cpu", "cuda", "coreml"} else "cpu"


def _pool_size() -> int:
    # Concurrent OfflineTts instances per loaded model (memory vs throughput).
    # Raise TTS_ENGINE_POOL_SIZE toward 50 only if RAM allows (~100–160MB each).
    cpu = os.cpu_count() or 4
    default = min(max(4, cpu // 2), 16)
    return _env_int("TTS_ENGINE_POOL_SIZE", default)


def _max_inflight() -> int:
    # Accepted concurrent requests (running + waiting). Default ≥50.
    return _env_int("TTS_MAX_INFLIGHT", 64)


def _max_queue() -> int:
    return _env_int("TTS_MAX_QUEUE", 128)


def ensure_cuda_runtime_path() -> list[str]:
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


@dataclass
class SynthResult:
    samples: np.ndarray
    sample_rate: int
    elapsed_seconds: float
    audio_duration: float
    rtf: float
    model_id: str = ""
    sid: int = 0
    provider: str = "cpu"


class _EngineSlot:
    """One OfflineTts instance + exclusive lock (ONNX not multi-thread safe per instance)."""

    def __init__(self, tts: sherpa_onnx.OfflineTts):
        self.tts = tts
        self.lock = threading.Lock()
        self.sample_rate = int(tts.sample_rate)
        self.num_speakers = int(tts.num_speakers)


class _ModelPool:
    def __init__(self, model_id: str, provider: str, num_threads: int, size: int):
        self.model_id = model_id
        self.provider = provider
        self.num_threads = num_threads
        self.size = size
        self.slots: list[_EngineSlot] = []
        self._free: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._load_elapsed: Optional[float] = None
        self._built = False

    def _build_one(self) -> _EngineSlot:
        spec = get_spec(self.model_id)
        if spec is None:
            raise ValueError(f"未知 model_id: {self.model_id}")
        model_dir = spec.path
        if not model_files_ready(model_dir, spec):
            miss = ", ".join(model_missing_files(model_dir, spec)) or "unknown"
            raise FileNotFoundError(f"模型未就绪 {self.model_id}: {miss}")
        if self.provider == "cuda":
            ensure_cuda_runtime_path()
        onnx = resolve_onnx_path(model_dir, spec)
        assert onnx is not None
        lexicon = str(model_dir / "lexicon.txt")
        tokens = str(model_dir / "tokens.txt")
        rule_parts = [
            model_dir / "phone.fst",
            model_dir / "date.fst",
            model_dir / "number.fst",
        ]
        # Prefer new_heteronym if present after number
        het = model_dir / "new_heteronym.fst"
        if het.is_file():
            rule_parts.append(het)
        rule_fsts = ",".join(str(p) for p in rule_parts if p.is_file())
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(onnx),
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
            raise ValueError(f"OfflineTtsConfig 校验失败: {self.model_id}")
        t0 = time.perf_counter()
        tts = sherpa_onnx.OfflineTts(config)
        elapsed = time.perf_counter() - t0
        if self._load_elapsed is None:
            self._load_elapsed = elapsed
        return _EngineSlot(tts)

    def ensure(self) -> None:
        with self._lock:
            if self._built and self.slots:
                return
            self.slots = []
            while not self._free.empty():
                try:
                    self._free.get_nowait()
                except queue.Empty:
                    break
            for i in range(self.size):
                slot = self._build_one()
                self.slots.append(slot)
                self._free.put(slot)
            self._built = True

    @contextmanager
    def acquire(self, timeout: float = 120.0):
        self.ensure()
        try:
            slot = self._free.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError(
                f"模型 {self.model_id} 引擎池繁忙（pool={self.size}），请稍后重试"
            ) from exc
        try:
            yield slot
        finally:
            self._free.put(slot)

    def destroy(self) -> None:
        with self._lock:
            self.slots.clear()
            while not self._free.empty():
                try:
                    self._free.get_nowait()
                except queue.Empty:
                    break
            self._built = False


class TtsEngine:
    """Multi-model TTS with per-model engine pools and ≥50 inflight capacity."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        num_threads: Optional[int] = None,
        provider: Optional[str] = None,
    ) -> None:
        mid = (model_id or os.environ.get("TTS_MODEL_ID") or DEFAULT_MODEL_ID).strip()
        if mid not in MODEL_REGISTRY:
            mid = DEFAULT_MODEL_ID
        self.model_id = mid
        self.num_threads = int(num_threads) if num_threads is not None else _default_num_threads()
        self.provider = (provider or _default_provider()).lower()
        self.pool_size = _pool_size()
        self.max_inflight = _max_inflight()
        self.max_queue = _max_queue()

        self._pools: dict[tuple[str, str], _ModelPool] = {}
        self._pools_lock = threading.RLock()
        self._inflight = 0
        self._queued = 0
        self._inflight_lock = threading.Condition(threading.Lock())
        self._switch_count = 0
        self._stats_ok = 0
        self._stats_err = 0
        self._stats_reject = 0
        self._executor = ThreadPoolExecutor(
            max_workers=max(self.pool_size * 2, 8),
            thread_name_prefix="tts-worker",
        )

    # ----- paths / readiness -----
    @property
    def model_dir(self) -> Path:
        spec = get_spec(self.model_id)
        return spec.path if spec else MODELS_ROOT / self.model_id

    def model_ready(self, model_id: Optional[str] = None) -> bool:
        mid = model_id or self.model_id
        spec = get_spec(mid)
        if not spec:
            return False
        return model_files_ready(spec.path, spec)

    def missing_files(self, model_id: Optional[str] = None) -> list[str]:
        mid = model_id or self.model_id
        spec = get_spec(mid)
        if not spec:
            return [f"unknown model_id: {mid}"]
        return model_missing_files(spec.path, spec)

    def list_models(self) -> list[dict]:
        items: list[dict] = []
        for spec in MODEL_REGISTRY.values():
            ready = model_files_ready(spec.path, spec)
            items.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "dir": str(spec.path),
                    "expected_sample_rate": spec.expected_sample_rate,
                    "tags": list(spec.tags),
                    "ready": ready,
                    "missing": model_missing_files(spec.path, spec) if not ready else [],
                    "active": spec.id == self.model_id,
                    "num_speakers": spec.num_speakers,
                    "lang": spec.lang,
                    "bundle_default": spec.bundle_default,
                    "archive_mb": spec.archive_mb,
                }
            )
        return items

    def list_speakers(self, model_id: Optional[str] = None) -> list[dict]:
        mid = model_id or self.model_id
        spec = get_spec(mid)
        documented = list(spec.speakers) if spec and spec.speakers else []
        by_sid = {int(s["sid"]): dict(s) for s in documented}
        n = spec.num_speakers if spec else (max(by_sid.keys()) + 1 if by_sid else 1)
        # Prefer live count if pool already loaded
        pool = self._pools.get((mid, self.provider))
        if pool and pool.slots:
            n = max(n, pool.slots[0].num_speakers)
        out: list[dict] = []
        for sid in range(max(int(n), 1)):
            if sid in by_sid:
                item = dict(by_sid[sid])
            else:
                item = {
                    "sid": sid,
                    "name": f"说话人 {sid}",
                    "lang": spec.lang if spec else "zh",
                    "note": "",
                }
            item["sid"] = sid
            item["active"] = mid == self.model_id
            item["single_speaker_model"] = int(n) <= 1
            out.append(item)
        return out

    def list_voice_roles(self) -> list[dict]:
        roles: list[dict] = []
        for preset in VOICE_ROLE_PRESETS:
            mid = preset["model_id"]
            spec = get_spec(mid)
            ready = model_files_ready(spec.path, spec) if spec else False
            roles.append(
                {
                    **preset,
                    "ready": ready,
                    "active": mid == self.model_id and int(preset.get("sid", 0)) == 0,
                    "model_name": spec.name if spec else mid,
                }
            )
        return roles

    @staticmethod
    def cuda_runtime_present() -> bool:
        lib = Path(sys.prefix) / "Lib" / "site-packages" / "sherpa_onnx" / "lib"
        ep = lib / "onnxruntime_providers_cuda.dll"
        if not ep.is_file():
            if not (lib / "libonnxruntime_providers_cuda.so").is_file():
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

    def runtime_info(self) -> dict:
        spec = get_spec(self.model_id)
        with self._inflight_lock:
            inflight = self._inflight
            queued = self._queued
        pool = self._pools.get((self.model_id, self.provider))
        return {
            "num_threads": self.num_threads,
            "provider": self.provider,
            "model_id": self.model_id,
            "model_name": spec.name if spec else self.model_id,
            "model_loaded": bool(pool and pool._built),
            "load_elapsed_seconds": pool._load_elapsed if pool else None,
            "model_dir": str(self.model_dir),
            "sample_rate": pool.slots[0].sample_rate if pool and pool.slots else (
                spec.expected_sample_rate if spec else None
            ),
            "expected_sample_rate": spec.expected_sample_rate if spec else None,
            "switch_count": self._switch_count,
            "busy": inflight > 0,
            "cuda_available": self.cuda_runtime_present(),
            "num_speakers": spec.num_speakers if spec else None,
            "speakers": self.list_speakers(),
            "voice_roles": self.list_voice_roles(),
            "speed_min": SPEED_MIN,
            "speed_max": SPEED_MAX,
            "speed_default": SPEED_DEFAULT,
            "concurrency": {
                "pool_size": self.pool_size,
                "max_inflight": self.max_inflight,
                "max_queue": self.max_queue,
                "inflight": inflight,
                "queued": queued,
                "ok": self._stats_ok,
                "errors": self._stats_err,
                "rejected": self._stats_reject,
            },
        }

    def _get_pool(self, model_id: str, provider: Optional[str] = None) -> _ModelPool:
        prov = (provider or self.provider).lower()
        key = (model_id, prov)
        with self._pools_lock:
            pool = self._pools.get(key)
            if pool is None:
                pool = _ModelPool(model_id, prov, self.num_threads, self.pool_size)
                self._pools[key] = pool
            return pool

    def preload(self, model_id: Optional[str] = None) -> dict:
        mid = model_id or self.model_id
        pool = self._get_pool(mid)
        pool.ensure()
        return {
            "sample_rate": pool.slots[0].sample_rate,
            "num_threads": self.num_threads,
            "provider": self.provider,
            "model_id": mid,
            "load_elapsed_seconds": pool._load_elapsed,
            "model_dir": str(get_spec(mid).path if get_spec(mid) else ""),
            "pool_size": self.pool_size,
            "switch_count": self._switch_count,
        }

    def set_provider(self, provider: str, *, warmup: bool = True, wait_busy_timeout: float = 120.0) -> dict:
        p = provider.strip().lower()
        if p not in {"cpu", "cuda", "coreml"}:
            raise ValueError("provider 必须是 cpu / cuda / coreml")
        if p == "cuda" and not self.cuda_runtime_present():
            raise RuntimeError("未检测到 CUDA 运行时")
        prev = self.provider
        if prev == p:
            return {"ok": True, "changed": False, "provider": p, "message": "未变化"}
        self._wait_idle(wait_busy_timeout)
        self.provider = p
        self._switch_count += 1
        info = self.preload() if warmup else {"model_id": self.model_id, "provider": p}
        info.update({"ok": True, "changed": True, "previous_provider": prev, "provider": p})
        return info

    def set_model(self, model_id: str, *, warmup: bool = True, wait_busy_timeout: float = 120.0) -> dict:
        mid = model_id.strip()
        if mid not in MODEL_REGISTRY:
            raise ValueError(f"未知 model_id: {mid}。可选: {', '.join(MODEL_REGISTRY)}")
        if not self.model_ready(mid):
            raise FileNotFoundError(
                f"模型未就绪: {mid}；缺失: {', '.join(self.missing_files(mid))}"
            )
        prev = self.model_id
        if prev == mid:
            return {
                "ok": True,
                "changed": False,
                "model_id": mid,
                "message": "模型未变化",
                **self.runtime_info(),
            }
        # Soft switch: do not require global idle — new requests use new model;
        # old pool drains naturally.
        self.model_id = mid
        self._switch_count += 1
        info = self.preload(mid) if warmup else {"model_id": mid}
        info.update(
            {
                "ok": True,
                "changed": True,
                "previous_model_id": prev,
                "model_id": mid,
                "model_name": MODEL_REGISTRY[mid].name,
                "speakers": self.list_speakers(mid),
                "num_speakers": MODEL_REGISTRY[mid].num_speakers,
            }
        )
        return info

    def _wait_idle(self, timeout: float) -> None:
        deadline = time.perf_counter() + timeout
        with self._inflight_lock:
            while self._inflight > 0:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError(f"仍有 {self._inflight} 个任务进行中")
                self._inflight_lock.wait(timeout=min(1.0, remaining))

    def _admit(self) -> None:
        with self._inflight_lock:
            if self._inflight >= self.max_inflight:
                self._stats_reject += 1
                raise OverflowError(
                    f"服务繁忙：inflight={self._inflight}/{self.max_inflight}，请稍后重试"
                )
            if self._queued >= self.max_queue and self._inflight >= self.pool_size:
                self._stats_reject += 1
                raise OverflowError(
                    f"排队已满：queued={self._queued}/{self.max_queue}"
                )
            self._inflight += 1
            self._queued += 1

    def _begin_run(self) -> None:
        with self._inflight_lock:
            self._queued = max(0, self._queued - 1)

    def _release(self) -> None:
        with self._inflight_lock:
            self._inflight = max(0, self._inflight - 1)
            self._inflight_lock.notify_all()

    def synthesize(
        self,
        text: str,
        sid: int = 0,
        speed: float = 1.0,
        *,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> SynthResult:
        text = (text or "").strip()
        if not text:
            raise ValueError("文本不能为空")
        speed = float(speed)
        if speed < SPEED_MIN or speed > SPEED_MAX:
            raise ValueError(f"语速须在 {SPEED_MIN}–{SPEED_MAX}")
        mid = (model_id or self.model_id).strip()
        if mid not in MODEL_REGISTRY:
            raise ValueError(f"未知 model_id: {mid}")
        if not self.model_ready(mid):
            raise FileNotFoundError(f"模型未就绪: {mid}")

        self._admit()
        self._begin_run()
        start = time.perf_counter()
        try:
            pool = self._get_pool(mid, provider)
            gen = sherpa_onnx.GenerationConfig()
            gen.sid = int(sid)
            gen.speed = float(speed)
            gen.silence_scale = 0.2
            with pool.acquire() as slot:
                with slot.lock:
                    audio = slot.tts.generate(text, gen)
                sample_rate = slot.sample_rate
            elapsed = time.perf_counter() - start
            if audio is None or len(audio.samples) == 0:
                raise RuntimeError("合成失败：未生成音频")
            samples = np.asarray(audio.samples, dtype=np.float32)
            if not samples.flags["C_CONTIGUOUS"]:
                samples = np.ascontiguousarray(samples)
            duration = float(len(samples) / sample_rate)
            self._stats_ok += 1
            return SynthResult(
                samples=samples,
                sample_rate=int(sample_rate),
                elapsed_seconds=elapsed,
                audio_duration=duration,
                rtf=elapsed / duration if duration > 0 else 0.0,
                model_id=mid,
                sid=int(sid),
                provider=(provider or self.provider),
            )
        except Exception:
            self._stats_err += 1
            raise
        finally:
            self._release()

    def synthesize_stream(
        self,
        text: str,
        sid: int = 0,
        speed: float = 1.0,
        cancel_event: Optional[threading.Event] = None,
        *,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Iterator[tuple[str, object]]:
        text = (text or "").strip()
        if not text:
            yield ("error", "文本不能为空")
            return
        mid = (model_id or self.model_id).strip()
        if mid not in MODEL_REGISTRY:
            yield ("error", f"未知 model_id: {mid}")
            return
        try:
            self._admit()
        except OverflowError as exc:
            yield ("error", str(exc))
            return
        self._begin_run()

        q: queue.Queue = queue.Queue(maxsize=256)
        cancel = cancel_event or threading.Event()
        result_box: dict = {}

        def worker() -> None:
            gen = sherpa_onnx.GenerationConfig()
            gen.sid = int(sid)
            gen.speed = float(speed)
            gen.silence_scale = 0.2
            sample_rate = 0
            start = time.perf_counter()
            try:
                pool = self._get_pool(mid, provider)

                def callback(samples, progress: float) -> int:
                    if cancel.is_set():
                        return 0
                    arr = np.array(samples, dtype=np.float32, copy=True).reshape(-1)
                    try:
                        q.put(("chunk", arr), timeout=0.5)
                    except queue.Full:
                        q.put(("chunk", arr))
                    q.put(("progress", float(progress)))
                    return 0 if cancel.is_set() else 1

                with pool.acquire() as slot:
                    sample_rate = slot.sample_rate
                    q.put(
                        (
                            "meta",
                            {
                                "sample_rate": sample_rate,
                                "channels": 1,
                                "format": "f32le",
                                "dtype": "float32",
                                "num_threads": self.num_threads,
                                "provider": provider or self.provider,
                                "model_id": mid,
                                "sid": int(sid),
                            },
                        )
                    )
                    with slot.lock:
                        audio = slot.tts.generate(text, gen, callback)
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
                    "provider": provider or self.provider,
                    "model_id": mid,
                    "sid": int(sid),
                }
                self._stats_ok += 1
            except Exception as exc:  # noqa: BLE001
                self._stats_err += 1
                result_box["error"] = str(exc)
                q.put(
                    (
                        "meta",
                        {
                            "sample_rate": sample_rate or 16000,
                            "channels": 1,
                            "format": "f32le",
                            "dtype": "float32",
                            "model_id": mid,
                        },
                    )
                )
            finally:
                self._release()
                q.put((_STREAM_DONE, None))

        threading.Thread(target=worker, name="tts-stream", daemon=True).start()
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
        if "error" in result_box:
            yield ("error", result_box["error"])
            return
        if "end" in result_box:
            yield ("end", result_box["end"])
        else:
            yield ("error", "合成线程异常结束")


def _engine_from_env() -> TtsEngine:
    return TtsEngine(
        model_id=os.environ.get("TTS_MODEL_ID"),
        provider=os.environ.get("TTS_PROVIDER"),
    )


engine = _engine_from_env()
