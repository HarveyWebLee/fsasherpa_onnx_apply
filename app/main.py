"""FastAPI TTS plugin — multi-model, concurrent, React UI."""

from __future__ import annotations

import asyncio
import io
import json
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from .models_registry import MODEL_REGISTRY, list_downloadable
from .tts_engine import ROOT, engine

APP_VERSION = "2.0.0"


def _resolve_static_dir() -> Path:
    env = os.environ.get("FSATTS_STATIC_DIR") or os.environ.get("TTS_STATIC_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # React production build (Vite)
    web_dist = ROOT / "web" / "dist"
    if (web_dist / "index.html").is_file():
        return web_dist
    import sys

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        for base in (meipass, Path(sys.executable).resolve().parent):
            cand = base / "web" / "dist"
            if cand.is_dir():
                return cand
    return web_dist


STATIC_DIR = _resolve_static_dir()
OUTPUT_DIR = Path(os.environ.get("TTS_OUTPUT_DIR") or (ROOT / "outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_HOST = os.environ.get("TTS_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("TTS_PORT", "19658"))
CORS_ORIGINS_RAW = os.environ.get("TTS_CORS_ORIGINS", "*").strip()
PRELOAD = os.environ.get("TTS_PRELOAD", "1").strip().lower() not in {"0", "false", "no"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if PRELOAD and engine.model_ready():
        try:
            info = engine.preload()
            print(
                f"[tts] preloaded model={info.get('model_id')} "
                f"pool={info.get('pool_size')} "
                f"provider={info.get('provider')} "
                f"sr={info.get('sample_rate')} "
                f"load={info.get('load_elapsed_seconds'):.2f}s"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[tts] preload failed: {exc}")
    else:
        print(
            f"[tts] ready={engine.model_ready()} model={engine.model_id} "
            f"preload={PRELOAD} missing={engine.missing_files() if not engine.model_ready() else []}"
        )
    yield


app = FastAPI(
    title="fsatts — sherpa-onnx TTS Plugin",
    description="本地多模型 TTS 插件（CORS / 流式 / ≥50 并发队列）",
    version=APP_VERSION,
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in CORS_ORIGINS_RAW.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Audio-Duration",
        "X-Elapsed-Seconds",
        "X-Elapsed-Ms",
        "X-RTF",
        "X-Sample-Rate",
        "X-Provider",
        "X-Model-Id",
        "X-Speed",
        "X-Sid",
        "X-Saved-As",
        "X-Stream-Format",
        "X-Channels",
        "Retry-After",
    ],
)

# Vite assets under /assets
if STATIC_DIR.is_dir():
    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")


class SynthRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    sid: int = Field(0, ge=0)
    provider: str | None = None
    model_id: str | None = None


class ProviderRequest(BaseModel):
    provider: str
    warmup: bool = True


class ModelRequest(BaseModel):
    model_id: str
    warmup: bool = True


def _http_from_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, OverflowError):
        return HTTPException(
            status_code=503,
            detail={"message": str(exc), "code": "busy"},
            headers={"Retry-After": "2"},
        )
    if isinstance(exc, TimeoutError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (RuntimeError, FileNotFoundError)):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="缺少前端 index.html，请先构建 web/")
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    info = engine.runtime_info()
    payload = {
        "ok": True,
        "service": "fsatts",
        "version": APP_VERSION,
        "model_ready": engine.model_ready(),
        "model_dir": str(engine.model_dir),
        "missing": engine.missing_files() if not engine.model_ready() else [],
        "streaming": True,
        "supports_stream": bool(
            MODEL_REGISTRY[engine.model_id].supports_stream
            if engine.model_id in MODEL_REGISTRY
            else True
        ),
        "listen_host": DEFAULT_HOST,
        "listen_port": DEFAULT_PORT,
        "cors_origins": _cors_origins,
        "plugin": True,
        "queue_depth": info.get("concurrency", {}).get("queued"),
        "inflight": info.get("concurrency", {}).get("inflight"),
        "max_inflight": info.get("concurrency", {}).get("max_inflight"),
    }
    payload.update(info)
    return payload


@app.get("/health")
def health_alias():
    """Compat alias for older clients / probes."""
    return health()


@app.get("/api/status")
def status():
    ready = engine.model_ready()
    info = {
        "model_ready": ready,
        "model_dir": str(engine.model_dir),
        "missing": engine.missing_files() if not ready else [],
        "streaming": True,
        "supports_stream": bool(
            MODEL_REGISTRY[engine.model_id].supports_stream
            if engine.model_id in MODEL_REGISTRY
            else True
        ),
        "ws_tts": "/ws/tts",
        "http_stream": "/api/tts/stream",
        "provider_api": "/api/provider",
        "models_api": "/api/models",
        "models": engine.list_models(),
        "downloadable": list_downloadable(),
    }
    info.update(engine.runtime_info())
    info["voice_roles"] = engine.list_voice_roles()
    return info


@app.get("/api/provider")
def get_provider():
    info = engine.runtime_info()
    info["ok"] = True
    return info


@app.post("/api/provider")
def set_provider(req: ProviderRequest):
    try:
        return engine.set_provider(req.provider, warmup=bool(req.warmup))
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@app.get("/api/models")
def list_models():
    return {
        "ok": True,
        "current": engine.model_id,
        "models": engine.list_models(),
        "downloadable": list_downloadable(),
        **engine.runtime_info(),
    }


@app.post("/api/models")
def set_model(req: ModelRequest):
    try:
        return engine.set_model(req.model_id, warmup=bool(req.warmup))
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc


@app.get("/api/speakers")
def speakers(model_id: str | None = Query(default=None)):
    mid = model_id or engine.model_id
    if mid not in MODEL_REGISTRY:
        raise HTTPException(status_code=400, detail=f"未知 model_id: {mid}")
    return {
        "ok": True,
        "model_id": mid,
        "speakers": engine.list_speakers(mid),
        "num_speakers": MODEL_REGISTRY[mid].num_speakers,
        "ready": engine.model_ready(mid),
    }


@app.post("/api/tts")
def synthesize(req: SynthRequest):
    mid = req.model_id or engine.model_id
    if not engine.model_ready(mid):
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"模型未下载: {mid}。请运行: uv run python scripts/download_models.py --id {mid}",
                "missing": engine.missing_files(mid),
                "model_id": mid,
            },
        )
    try:
        if req.provider and req.provider != engine.provider:
            engine.set_provider(req.provider, warmup=False)
        result = engine.synthesize(
            req.text,
            sid=req.sid,
            speed=req.speed,
            model_id=mid,
            provider=req.provider,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc

    buf = io.BytesIO()
    sf.write(buf, result.samples, result.sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    out_name = f"tts_{uuid.uuid4().hex[:12]}.wav"
    out_path = OUTPUT_DIR / out_name
    sf.write(str(out_path), result.samples, result.sample_rate, subtype="PCM_16")
    headers = {
        "X-Audio-Duration": f"{result.audio_duration:.3f}",
        "X-Elapsed-Seconds": f"{result.elapsed_seconds:.3f}",
        "X-Elapsed-Ms": f"{result.elapsed_seconds * 1000.0:.1f}",
        "X-RTF": f"{result.rtf:.3f}",
        "X-Sample-Rate": str(result.sample_rate),
        "X-Provider": result.provider,
        "X-Model-Id": result.model_id,
        "X-Speed": f"{req.speed:.3f}",
        "X-Sid": str(int(req.sid)),
        "X-Saved-As": out_name,
        "Content-Disposition": f'inline; filename="{out_name}"',
        "Access-Control-Expose-Headers": (
            "X-Audio-Duration, X-Elapsed-Seconds, X-Elapsed-Ms, X-RTF, "
            "X-Sample-Rate, X-Provider, X-Model-Id, X-Speed, X-Sid, X-Saved-As"
        ),
    }
    return StreamingResponse(buf, media_type="audio/wav", headers=headers)


@app.post("/api/tts/stream")
def synthesize_http_stream(req: SynthRequest):
    mid = req.model_id or engine.model_id
    if not engine.model_ready(mid):
        raise HTTPException(
            status_code=503,
            detail={"message": f"模型未就绪: {mid}", "missing": engine.missing_files(mid)},
        )
    try:
        if req.provider and req.provider != engine.provider:
            engine.set_provider(req.provider, warmup=False)
    except Exception as exc:  # noqa: BLE001
        raise _http_from_exc(exc) from exc

    def gen():
        try:
            for kind, payload in engine.synthesize_stream(
                req.text, sid=req.sid, speed=req.speed, model_id=mid, provider=req.provider
            ):
                if kind == "meta":
                    yield (
                        json.dumps({"type": "meta", **payload}, ensure_ascii=False) + "\n"
                    ).encode("utf-8")
                elif kind == "chunk":
                    yield np.asarray(payload, dtype=np.float32).tobytes(order="C")
                elif kind == "end":
                    return
                elif kind == "error":
                    raise RuntimeError(str(payload))
        except OverflowError as exc:
            raise RuntimeError(str(exc)) from exc

    headers = {
        "X-Stream-Format": "json-meta-line+f32le",
        "X-Channels": "1",
        "X-Provider": engine.provider,
        "X-Model-Id": mid,
        "Cache-Control": "no-store",
    }
    return StreamingResponse(gen(), media_type="application/octet-stream", headers=headers)


@app.websocket("/ws/tts")
async def ws_tts(websocket: WebSocket):
    await websocket.accept()
    cancel = threading.Event()
    try:
        raw = await websocket.receive_text()
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "请求必须是 JSON 文本"})
            await websocket.close()
            return

        text = str(req.get("text", "")).strip()
        speed = float(req.get("speed", 1.0))
        sid = int(req.get("sid", 0))
        provider = req.get("provider")
        model_id = req.get("model_id") or engine.model_id
        if not text:
            await websocket.send_json({"type": "error", "message": "文本不能为空"})
            await websocket.close()
            return

        if provider and str(provider) != engine.provider:
            try:
                await asyncio.to_thread(lambda: engine.set_provider(str(provider), warmup=False))
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json(
                    {"type": "error", "message": f"切换 provider 失败: {exc}"}
                )
                await websocket.close()
                return

        if not engine.model_ready(str(model_id)):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "模型未就绪",
                    "missing": engine.missing_files(str(model_id)),
                    "model_id": model_id,
                }
            )
            await websocket.close()
            return

        loop = asyncio.get_running_loop()
        event_q: asyncio.Queue = asyncio.Queue(maxsize=128)

        def producer() -> None:
            try:
                for kind, payload in engine.synthesize_stream(
                    text,
                    sid=sid,
                    speed=speed,
                    cancel_event=cancel,
                    model_id=str(model_id),
                    provider=str(provider) if provider else None,
                ):
                    if cancel.is_set():
                        break
                    fut = asyncio.run_coroutine_threadsafe(event_q.put((kind, payload)), loop)
                    try:
                        fut.result(timeout=60)
                    except Exception:
                        cancel.set()
                        break
            finally:
                asyncio.run_coroutine_threadsafe(event_q.put(("__done__", None)), loop)

        threading.Thread(target=producer, name="ws-tts-prod", daemon=True).start()

        while True:
            kind, payload = await event_q.get()
            if kind == "__done__":
                break
            if websocket.client_state != WebSocketState.CONNECTED:
                cancel.set()
                break
            if kind == "meta":
                await websocket.send_json({"type": "meta", **payload})
            elif kind == "chunk":
                arr = np.asarray(payload, dtype=np.float32)
                await websocket.send_bytes(arr.tobytes(order="C"))
            elif kind == "progress":
                await websocket.send_json({"type": "progress", "progress": float(payload)})
            elif kind == "end":
                await websocket.send_json({"type": "end", **payload})
            elif kind == "error":
                await websocket.send_json({"type": "error", "message": str(payload)})
    except WebSocketDisconnect:
        cancel.set()
    except Exception as exc:  # noqa: BLE001
        cancel.set()
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        cancel.set()
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/download/{filename}")
def download(filename: str):
    safe = Path(filename).name
    path = OUTPUT_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type="audio/wav", filename=safe)


# SPA fallback for client-side routes (React Router if any)
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        raise HTTPException(status_code=404)
    candidate = STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    raise HTTPException(status_code=404)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        reload=False,
        workers=1,  # shared in-process engine pool; scale via TTS_ENGINE_POOL_SIZE
    )


if __name__ == "__main__":
    main()
