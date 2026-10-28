#!/usr/bin/env python3
"""Verify /ws/tts returns PCM chunks (run while server is up)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:9658/ws/tts")
    parser.add_argument(
        "--text",
        default="你好。这是流式测试。Hello streaming speech.",
    )
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    try:
        import websockets
    except ImportError:
        print("请先: pip install websockets", file=sys.stderr)
        return 2

    chunks = 0
    samples = 0
    meta = None
    async with websockets.connect(args.url, max_size=16 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"text": args.text, "speed": args.speed, "sid": 0}))
        while True:
            msg = await ws.recv()
            if isinstance(msg, bytes):
                chunks += 1
                samples += len(msg) // 4
                print(f"chunk#{chunks}: {len(msg)} bytes ({len(msg)//4} samples)")
                continue
            data = json.loads(msg)
            typ = data.get("type")
            print("json:", data)
            if typ == "meta":
                meta = data
            elif typ in ("end", "error"):
                break

    ok = bool(chunks > 0 and samples > 0 and meta is not None and meta.get("sample_rate"))
    print(
        f"RESULT ok={ok} chunks={chunks} samples={samples} "
        f"sr={meta.get('sample_rate') if meta else None}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
