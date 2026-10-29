#!/usr/bin/env python3
"""Benchmark OfflineTts RTF across thread counts."""

from __future__ import annotations

import time
from pathlib import Path

import sherpa_onnx

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "vits-melo-tts-zh_en"

TEXTS = {
    "short": "你好。",
    "medium": "欢迎使用本地文本转语音。这是第二句测试。",
    "long": (
        "This is a 中英文混合的 text to speech 性能测试。"
        "我们用更长的段落来观察实时率。"
        "第三句继续，观察耗时是否随长度近似线性增长。"
    ),
}


def build(num_threads: int, max_num_sentences: int = 1) -> sherpa_onnx.OfflineTts:
    model = str(MODEL_DIR / "model.onnx")
    lexicon = str(MODEL_DIR / "lexicon.txt")
    tokens = str(MODEL_DIR / "tokens.txt")
    rules = ",".join(
        str(MODEL_DIR / n)
        for n in ("phone.fst", "date.fst", "number.fst")
        if (MODEL_DIR / n).is_file()
    )
    vits = sherpa_onnx.OfflineTtsVitsModelConfig(
        model=model,
        lexicon=lexicon,
        tokens=tokens,
    )
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=vits,
            provider="cpu",
            debug=False,
            num_threads=num_threads,
        ),
        rule_fsts=rules,
        max_num_sentences=max_num_sentences,
    )
    assert cfg.validate()
    return sherpa_onnx.OfflineTts(cfg)


def run_one(tts, text: str):
    gen = sherpa_onnx.GenerationConfig()
    gen.sid = 0
    gen.speed = 1.0
    gen.silence_scale = 0.2
    t0 = time.perf_counter()
    audio = tts.generate(text, gen)
    elapsed = time.perf_counter() - t0
    n = len(audio.samples) if audio is not None else 0
    dur = n / float(audio.sample_rate) if n and audio.sample_rate else 0.0
    rtf = elapsed / dur if dur > 0 else float("inf")
    return elapsed, dur, rtf


def main() -> None:
    print("model_bytes", (MODEL_DIR / "model.onnx").stat().st_size)
    print("\n=== warmup threads=2 ===")
    tts = build(2)
    e, d, r = run_one(tts, TEXTS["short"])
    print(f"warmup short elapsed={e:.3f}s audio={d:.3f}s rtf={r:.3f}")
    del tts

    results = []
    # Focus on practical thread counts; one run each after warmup inside loop
    for threads in (2, 4, 6):
        print(f"\n=== threads={threads} ===")
        tts = build(threads)
        # internal warmup
        run_one(tts, "嗯。")
        for name, text in TEXTS.items():
            e, d, r = run_one(tts, text)
            print(f"  {name:6s} elapsed={e:.3f}s audio={d:.3f}s rtf={r:.3f} chars={len(text)}")
            results.append((threads, name, e, d, r))
        del tts

    print("\n=== SUMMARY ===")
    print(f"{'thr':>3} {'text':>6} {'elapsed':>8} {'audio':>8} {'rtf':>8}")
    for thr, name, e, d, r in results:
        print(f"{thr:3d} {name:>6} {e:8.3f} {d:8.3f} {r:8.3f}")


if __name__ == "__main__":
    main()
