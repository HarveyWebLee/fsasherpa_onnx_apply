"""FastAPI web UI for sherpa-onnx Chinese/English TTS."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Optional

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .tts_engine import ROOT, engine

STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="sherpa-onnx TTS Demo",
    description="基于 sherpa-onnx + vits-melo-tts-zh_en 的中英/中英混合文本转语音测试",
    version="1.0.0",
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


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="缺少 static/index.html")
    return FileResponse(index_path)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model_ready": engine.model_ready(),
        "model_dir": str(engine.model_dir),
        "missing": engine.missing_files() if not engine.model_ready() else [],
        "sample_rate": None,
    }


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
    }
    if ready:
        try:
            tts = engine.ensure_loaded()
            info["num_speakers"] = tts.num_speakers
            info["sample_rate"] = tts.sample_rate
            info["lang"] = getattr(tts, "lang", None)
        except Exception as exc:  # noqa: BLE001
            info["load_error"] = str(exc)
    return info


@app.post("/api/tts")
def synthesize(req: SynthRequest):
    if not engine.model_ready():
        raise HTTPException(
            status_code=503,
            detail={
                "message": "模型未下载。请在项目根目录运行: .\\scripts\\download_model.ps1",
                "missing": engine.missing_files(),
            },
        )
    try:
        result = engine.synthesize(req.text, sid=req.sid, speed=req.speed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"合成失败: {exc}") from exc

    buf = io.BytesIO()
    sf.write(buf, result.samples, result.sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)

    # also save a copy under outputs/
    out_name = f"tts_{uuid.uuid4().hex[:12]}.wav"
    out_path = OUTPUT_DIR / out_name
    sf.write(str(out_path), result.samples, result.sample_rate, subtype="PCM_16")

    headers = {
        "X-Audio-Duration": f"{result.audio_duration:.3f}",
        "X-Elapsed-Seconds": f"{result.elapsed_seconds:.3f}",
        "X-RTF": f"{result.rtf:.3f}",
        "X-Sample-Rate": str(result.sample_rate),
        "X-Saved-As": out_name,
        "Content-Disposition": f'inline; filename="{out_name}"',
    }
    return StreamingResponse(buf, media_type="audio/wav", headers=headers)


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
        port=7860,
        reload=False,
    )


if __name__ == "__main__":
    main()
