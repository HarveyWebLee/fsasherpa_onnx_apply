# -*- coding: utf-8 -*-
"""Fair CPU vs CUDA benchmark for baseline Chinese text."""
from __future__ import annotations
import os, sys, time, subprocess, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEXT = "你好，欢迎使用本地文本转语音测试。第一句先出声。第二句继续播放。"

def gpu_util_sample(stop_evt, out_list, interval=0.4):
    while not stop_evt.wait(interval):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split(",")
                out_list.append((float(parts[0]), float(parts[1])))
        except Exception:
            pass

def run_provider(provider: str, rounds: int = 2):
    # Fresh engine per provider
    from app.tts_engine import TtsEngine
    eng = TtsEngine(provider=provider, num_threads=2)
    info = eng.preload()
    print(f"\n=== provider={provider} load={info['load_elapsed_seconds']:.3f}s sr={info['sample_rate']} ===", flush=True)

    # warmup
    _ = eng.synthesize("嗯。")
    results = {"full": [], "stream": [], "gpu": []}

    for i in range(rounds):
        stop = threading.Event()
        samples = []
        th = None
        if provider == "cuda":
            th = threading.Thread(target=gpu_util_sample, args=(stop, samples), daemon=True)
            th.start()
        r = eng.synthesize(TEXT)
        results["full"].append(r)
        print(f"  full#{i+1} elapsed={r.elapsed_seconds:.3f}s audio={r.audio_duration:.3f}s rtf={r.rtf:.3f}", flush=True)

        t0 = time.perf_counter()
        end = None
        first_chunk = None
        for kind, payload in eng.synthesize_stream(TEXT):
            if kind == "chunk" and first_chunk is None:
                first_chunk = time.perf_counter() - t0
            elif kind == "end":
                end = payload
        wall = time.perf_counter() - t0
        results["stream"].append((wall, end, first_chunk))
        print(
            f"  stream#{i+1} wall={wall:.3f}s end_elapsed={end['elapsed_seconds']:.3f}s "
            f"audio={end['audio_duration']:.3f}s rtf={end['rtf']:.3f} first_chunk={first_chunk:.3f}s",
            flush=True,
        )
        if th:
            stop.set()
            th.join(timeout=1)
            results["gpu"].extend(samples)
            if samples:
                util = [u for u, _ in samples]
                mem = [m for _, m in samples]
                print(f"  gpu_util max={max(util):.0f}% avg={sum(util)/len(util):.0f}% mem_max={max(mem):.0f}MiB n={len(samples)}", flush=True)

    return results

def main():
    print("TEXT:", TEXT)
    print("chars:", len(TEXT))
    cpu = run_provider("cpu", rounds=2)
    cuda = run_provider("cuda", rounds=2)

    def avg_full(rs):
        es = [x.elapsed_seconds for x in rs["full"]]
        ds = [x.audio_duration for x in rs["full"]]
        rt = [x.rtf for x in rs["full"]]
        return sum(es)/len(es), sum(ds)/len(ds), sum(rt)/len(rt)

    def avg_stream(rs):
        walls = [w for w, _, _ in rs["stream"]]
        ends = [e["elapsed_seconds"] for _, e, _ in rs["stream"]]
        auds = [e["audio_duration"] for _, e, _ in rs["stream"]]
        rtfs = [e["rtf"] for _, e, _ in rs["stream"]]
        firsts = [f for _, _, f in rs["stream"] if f is not None]
        return (
            sum(walls)/len(walls),
            sum(ends)/len(ends),
            sum(auds)/len(auds),
            sum(rtfs)/len(rtfs),
            (sum(firsts)/len(firsts) if firsts else None),
        )

    print("\n======== COMPARISON TABLE ========")
    print("baseline_user: cpu/2thr/44100 full=13.639s RTF=2.433 audio=5.606s | stream~13.649s RTF=2.359")
    ce, cd, cr = avg_full(cpu)
    ue, ud, ur = avg_full(cuda)
    csw, cse, csa, csr, csf = avg_stream(cpu)
    usw, use, usa, usr, usf = avg_stream(cuda)
    print(f"{'mode':<8} {'full_s':>8} {'audio_s':>8} {'RTF':>8} {'stream_s':>9} {'s_RTF':>8} {'1st_chunk':>9}")
    print(f"{'cpu':<8} {ce:8.3f} {cd:8.3f} {cr:8.3f} {csw:9.3f} {csr:8.3f} {csf:9.3f}")
    print(f"{'cuda':<8} {ue:8.3f} {ud:8.3f} {ur:8.3f} {usw:9.3f} {usr:8.3f} {usf:9.3f}")
    print(f"{'user_bl':<8} {13.639:8.3f} {5.606:8.3f} {2.433:8.3f} {13.649:9.3f} {2.359:8.3f} {'n/a':>9}")
    if ue > 0:
        print(f"speedup full cpu/cuda = {ce/ue:.3f}x  ( >1 means cuda faster )")
        print(f"speedup stream cpu/cuda = {csw/usw:.3f}x")

if __name__ == "__main__":
    main()
