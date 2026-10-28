"""FastAPI web UI for sherpa-onnx Chinese/English TTS (full + streaming)."""

from __future__ import annotations

import asyncio
import io
import json
import threading
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from .tts_engine import ROOT, engine

STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if engine.model_ready():
        try:
            info = engine.preload()
            print(
                f"[tts] preloaded model={info.get('model_id')} "
                f"threads={info.get('num_threads')} "
                f"provider={info.get('provider')} "
                f"sr={info.get('sample_rate')} "
                f"load={info.get('load_elapsed_seconds'):.2f}s"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[tts] preload failed: {exc}")
    else:
        print(f"[tts] model not ready: {engine.model_id} missing={engine.missing_files()}")
    yield


app = FastAPI(
    title="sherpa-onnx TTS Demo",
    description="基于 sherpa-onnx 的中英 TTS（多模型切换 + CUDA + 实时流）",
    version="1.4.0",
    lifespan=lifespan,
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class SynthRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="待合成文本")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="语速，1.0 为正常")
    sid: int = Field(0, ge=0, description="说话人 ID（本模型仅 1 个说话人）")
    mode: Optional[str] = Field(
        default="mixed",
        description="语言模式说明：zh / en / mixed（同一模型，仅 UI 标记）",
    )
    provider: Optional[str] = Field(
        default=None,
        description="可选：本次请求前切换到 cpu/cuda",
    )
    model_id: Optional[str] = Field(
        default=None,
        description="可选：本次请求前切换模型（如 melo-zh-en-44k / melo-zh-en-8k）",
    )


class ProviderRequest(BaseModel):
    provider: str = Field(..., description="cpu 或 cuda")
    warmup: bool = Field(True, description="切换后是否短句预热")


class ModelRequest(BaseModel):
    model_id: str = Field(..., description="注册表中的模型 id，如 melo-zh-en-8k")
    warmup: bool = Field(True, description="切换后是否短句预热")


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="缺少 static/index.html")
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    payload = {
        "ok": True,
        "model_ready": engine.model_ready(),
        "model_dir": str(engine.model_dir),
        "missing": engine.missing_files() if not engine.model_ready() else [],
        "streaming": True,
    }
    payload.update(engine.runtime_info())
    return payload


@app.get("/api/status")
def status():
    ready = engine.model_ready()
    info = {
        "model_ready": ready,
        "model_dir": str(engine.model_dir),
        "missing": engine.missing_files() if not ready else [],
        "num_speakers": None,
        "sample_rate": None,
        "lang": None,
        "streaming": True,
        "ws_tts": "/ws/tts",
        "http_stream": "/api/tts/stream",
        "provider_api": "/api/provider",
        "models_api": "/api/models",
        "models": engine.list_models(),
    }
    info.update(engine.runtime_info())
    if ready:
        try:
            tts = engine.ensure_loaded()
            info["num_speakers"] = tts.num_speakers
            info["sample_rate"] = tts.sample_rate
            info["lang"] = getattr(tts, "lang", None)
        except Exception as exc:  # noqa: BLE001
            info["load_error"] = str(exc)
    return info


@app.get("/api/provider")
def get_provider():
    info = engine.runtime_info()
    info["ok"] = True
    return info


@app.post("/api/provider")
def set_provider(req: ProviderRequest):
    try:
        result = engine.set_provider(req.provider, warmup=bool(req.warmup))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"切换 provider 失败: {exc}") from exc
    return result


@app.get("/api/models")
def list_models():
    return {
        "ok": True,
        "current": engine.model_id,
        "models": engine.list_models(),
        **engine.runtime_info(),
    }


@app.post("/api/models")
def set_model(req: ModelRequest):
    """Hot-switch TTS model (rebuild OfflineTts + optional warmup)."""
    try:
        result = engine.set_model(req.model_id, warmup=bool(req.warmup))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"切换模型失败: {exc}") from exc
    return result


def _maybe_switch(provider: Optional[str], model_id: Optional[str]) -> None:
    # Apply model first, then provider, so one rebuild each when both change
    # Prefer single rebuild when both set:
    if model_id or provider:
        kwargs = {"warmup": True}
        if model_id:
            kwargs["model_id"] = str(model_id).strip()
        if provider:
            kwargs["provider"] = str(provider).strip()
        # use internal rebuild once
        engine._rebuild(**kwargs)  # noqa: SLF001


@app.post("/api/tts")
def synthesize(req: SynthRequest):
    if not engine.model_ready() and not req.model_id:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "模型未下载。请在项目根目录运行: .\\scripts\\download_model.ps1",
                "missing": engine.missing_files(),
            },
        )
    try:
        _maybe_switch(req.provider, req.model_id)
        result = engine.synthesize(req.text, sid=req.sid, speed=req.speed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"合成失败: {exc}") from exc

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
        "X-Provider": engine.provider,
        "X-Model-Id": engine.model_id,
        "X-Saved-As": out_name,
        "Content-Disposition": f'inline; filename="{out_name}"',
        "Access-Control-Expose-Headers": (
            "X-Audio-Duration, X-Elapsed-Seconds, X-Elapsed-Ms, X-RTF, "
            "X-Sample-Rate, X-Provider, X-Model-Id, X-Saved-As"
        ),
    }
    return StreamingResponse(buf, media_type="audio/wav", headers=headers)


@app.post("/api/tts/stream")
def synthesize_http_stream(req: SynthRequest):
    if not engine.model_ready() and not req.model_id:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "模型未下载。请先运行 scripts/download_model.ps1",
                "missing": engine.missing_files(),
            },
        )

    try:
        _maybe_switch(req.provider, req.model_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def gen():
        for kind, payload in engine.synthesize_stream(
            req.text, sid=req.sid, speed=req.speed
        ):
            if kind == "meta":
                yield (json.dumps({"type": "meta", **payload}, ensure_ascii=False) + "\n").encode(
                    "utf-8"
                )
            elif kind == "chunk":
                arr = np.asarray(payload, dtype=np.float32)
                yield arr.tobytes(order="C")
            elif kind == "progress":
                continue
            elif kind == "end":
                return
            elif kind == "error":
                raise RuntimeError(str(payload))

    headers = {
        "X-Stream-Format": "json-meta-line+f32le",
        "X-Channels": "1",
        "X-Provider": engine.provider,
        "X-Model-Id": engine.model_id,
        "Cache-Control": "no-store",
        "Access-Control-Expose-Headers": "X-Stream-Format, X-Channels, X-Provider, X-Model-Id",
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
        model_id = req.get("model_id")
        if not text:
            await websocket.send_json({"type": "error", "message": "文本不能为空"})
            await websocket.close()
            return

        if provider or model_id:
            try:
                await asyncio.to_thread(
                    lambda: _maybe_switch(
                        str(provider) if provider else None,
                        str(model_id) if model_id else None,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json({"type": "error", "message": f"切换失败: {exc}"})
                await websocket.close()
                return

        if not engine.model_ready():
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "模型未就绪，请先下载模型",
                    "missing": engine.missing_files(),
                    "model_id": engine.model_id,
                }
            )
            await websocket.close()
            return

        loop = asyncio.get_running_loop()
        event_q: asyncio.Queue = asyncio.Queue(maxsize=128)

        def producer() -> None:
            try:
                for kind, payload in engine.synthesize_stream(
                    text, sid=sid, speed=speed, cancel_event=cancel
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


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=19658,
        reload=False,
    )


if __name__ == "__main__":
    main()
