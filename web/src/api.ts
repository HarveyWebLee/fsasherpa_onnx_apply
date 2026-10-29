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
    `/api/speakers?model_id=${encodeURIComponent(modelId)}`
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

