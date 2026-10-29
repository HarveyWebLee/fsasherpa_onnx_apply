#!/usr/bin/env python3
"""Command-line TTS smoke test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import soundfile as sf

from app.tts_engine import engine


EXAMPLES = {
    "zh": "你好，欢迎使用本地文本转语音测试。",
    "en": "Hello, this is a local text to speech demo.",
    "mixed": "This is a 中英文的 text to speech 测试例子。",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="sherpa-onnx TTS CLI")
    parser.add_argument("text", nargs="?", default="", help="待合成文本")
    parser.add_argument("--example", choices=sorted(EXAMPLES), help="使用内置示例")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--sid", type=int, default=0)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "outputs" / "cli_out.wav",
    )
    args = parser.parse_args()

    text = args.text.strip()
    if args.example:
        text = EXAMPLES[args.example]
    if not text:
        parser.error("请提供 text 或 --example")

    if not engine.model_ready():
        print("模型未就绪，请先运行: uv run python scripts/download_models.py --bundle")
        print("缺失:", engine.missing_files())
        return 2

    print(f"Synthesizing: {text}")
    result = engine.synthesize(text, sid=args.sid, speed=args.speed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(args.output), result.samples, result.sample_rate, subtype="PCM_16")
    print(f"Saved: {args.output}")
    print(
        f"duration={result.audio_duration:.3f}s elapsed={result.elapsed_seconds:.3f}s "
        f"RTF={result.rtf:.3f} sr={result.sample_rate}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
