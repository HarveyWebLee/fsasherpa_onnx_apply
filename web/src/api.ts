export type ModelInfo = {
  id: string;
  name: string;
  description: string;
  ready: boolean;
  active?: boolean;
  num_speakers: number;
  expected_sample_rate?: number;
  tags?: string[];
  lang?: string;
  missing?: string[];
  archive_mb?: number;
  backend?: string;
  supports_stream?: boolean;
};

export type Speaker = {
  sid: number;
  name: string;
  lang?: string;
  note?: string;
  single_speaker_model?: boolean;
};

export type StatusPayload = {
  model_ready: boolean;
  model_id: string;
  model_name?: string;
  provider: string;
  cuda_available?: boolean;
  sample_rate?: number;
  num_speakers?: number;
  streaming?: boolean;
  supports_stream?: boolean;
  models: ModelInfo[];
  speakers: Speaker[];
  concurrency?: {
    pool_size: number;
    max_inflight: number;
    inflight: number;
    queued: number;
    rejected?: number;
  };
  speed_min?: number;
  speed_max?: number;
};

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(String(detail));
    } catch {
      /* keep text */
    }
    const msg =
      typeof detail === "object" && detail && "detail" in (detail as object)
        ? JSON.stringify((detail as { detail: unknown }).detail)
        : String(detail);
    throw new Error(msg || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function fetchStatus() {
  return j<StatusPayload>("/api/status");
}

export function fetchSpeakers(modelId: string) {
  return j<{ speakers: Speaker[]; num_speakers: number; ready: boolean }>(
    `/api/speakers?model_id=${encodeURIComponent(modelId)}`,
  );
}

export function switchModel(modelId: string, warmup = true) {
  return j("/api/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId, warmup }),
  });
}

export function switchProvider(provider: string, warmup = true) {
  return j("/api/provider", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, warmup }),
  });
}

export type SynthParams = {
  text: string;
  speed: number;
  sid: number;
  model_id: string;
  provider?: string;
};

export async function synthesizeWav(params: SynthParams): Promise<{
  blob: Blob;
  headers: Record<string, string>;
}> {
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  const headers: Record<string, string> = {};
  [
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
  ].forEach((k) => {
    const v = res.headers.get(k);
    if (v) headers[k] = v;
  });
  return { blob: await res.blob(), headers };
}

export type StreamSynthHandlers = {
  onMeta?: (meta: Record<string, unknown>) => void;
  onChunk?: (samples: Float32Array) => void;
  onProgress?: (progress: number) => void;
  onEnd?: (end: Record<string, unknown>) => void;
};

function wsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

/** Stream TTS over WebSocket; returns when end/error. */
export function synthesizeStreamWs(
  params: SynthParams,
  handlers: StreamSynthHandlers,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl("/ws/tts"));
    ws.binaryType = "arraybuffer";
    let settled = false;
    let endPayload: Record<string, unknown> = {};

    const cleanup = () => {
      signal?.removeEventListener("abort", onAbort);
      try {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      } catch {
        /* ignore */
      }
    };

    const fail = (err: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(err);
    };

    const ok = () => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(endPayload);
    };

    const onAbort = () => fail(new Error("已取消"));
    signal?.addEventListener("abort", onAbort);

    ws.onopen = () => {
      ws.send(JSON.stringify(params));
    };
    ws.onerror = () => fail(new Error("WebSocket 连接失败"));
    ws.onclose = () => {
      if (!settled) fail(new Error("WebSocket 已关闭"));
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") {
        const buf = ev.data as ArrayBuffer;
        handlers.onChunk?.(new Float32Array(buf.slice(0)));
        return;
      }
      try {
        const data = JSON.parse(ev.data) as Record<string, unknown>;
        const typ = data.type;
        if (typ === "meta") {
          handlers.onMeta?.(data);
        } else if (typ === "progress") {
          handlers.onProgress?.(Number(data.progress ?? 0));
        } else if (typ === "end") {
          endPayload = data;
          handlers.onEnd?.(data);
          ok();
        } else if (typ === "error") {
          fail(new Error(String(data.message || "流式合成失败")));
        }
      } catch (e) {
        fail(e as Error);
      }
    };
  });
}

export function float32ToWavBlob(samples: Float32Array, sampleRate: number): Blob {
  const numSamples = samples.length;
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + numSamples * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, numSamples * 2, true);
  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}
