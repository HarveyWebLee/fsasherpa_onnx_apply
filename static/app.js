const textEl = document.getElementById("text");
const speedEl = document.getElementById("speed");
const speedVal = document.getElementById("speedVal");
const synthBtn = document.getElementById("synthBtn");
const streamBtn = document.getElementById("streamBtn");
const stopBtn = document.getElementById("stopBtn");
const player = document.getElementById("player");
const meta = document.getElementById("meta");
const streamMeta = document.getElementById("streamMeta");
const progressBar = document.getElementById("progressBar");
const errorEl = document.getElementById("error");
const statusBox = document.getElementById("statusBox");
const downloadLink = document.getElementById("downloadLink");
const timingBox = document.getElementById("timingBox");
const timingValue = document.getElementById("timingValue");
const timingDetail = document.getElementById("timingDetail");
const modes = document.querySelectorAll(".mode");
const cudaToggle = document.getElementById("cudaToggle");
const providerBadge = document.getElementById("providerBadge");
const providerHint = document.getElementById("providerHint");
const modelSelect = document.getElementById("modelSelect");
const modelBadge = document.getElementById("modelBadge");
const modelHint = document.getElementById("modelHint");

let currentMode = "mixed";
let objectUrl = null;
let ws = null;
let audioCtx = null;
let nextPlayTime = 0;
let streamSampleRate = 44100;
let receivedSamples = 0;
let streaming = false;
const recordedChunks = [];
let currentProvider = "cpu";
let currentModelId = "melo-zh-en-44k";
let currentSampleRate = null;
let cudaAvailable = false;
let switchingProvider = false;
let switchingModel = false;
let modelsCache = [];

let timingTimer = null;
let timingStartedAt = 0;
let timingMode = "";

const defaults = {
  zh: "你好，欢迎使用本地文本转语音测试。第一句先出声。第二句继续播放。",
  en: "Hello, this is a local streaming text to speech demo. You should hear audio before synthesis finishes.",
  mixed: "This is a 中英文的 text to speech 实时流式测试例子。第一句。第二句继续。",
};

textEl.value = defaults.mixed;
speedEl.addEventListener("input", () => {
  speedVal.textContent = Number(speedEl.value).toFixed(1);
});

modes.forEach((btn) => {
  btn.addEventListener("click", () => {
    modes.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    textEl.value = btn.dataset.sample || defaults[currentMode];
  });
});

function uiLocked() {
  return switchingProvider || switchingModel || streaming;
}

function setBusy(isBusy) {
  const lock = isBusy || switchingProvider || switchingModel;
  streamBtn.disabled = lock;
  synthBtn.disabled = lock;
  stopBtn.disabled = !isBusy;
  cudaToggle.disabled = lock || !cudaAvailable;
  modelSelect.disabled = lock;
}

function formatSeconds(sec) {
  if (!Number.isFinite(sec) || sec < 0) return "—";
  return `${sec.toFixed(3)} s`;
}

function clearTimingTicker() {
  if (timingTimer) {
    clearInterval(timingTimer);
    timingTimer = null;
  }
}

function startTiming(modeLabel) {
  clearTimingTicker();
  timingMode = modeLabel;
  timingStartedAt = performance.now();
  timingBox.className = "timing running";
  timingValue.textContent = "0.000 s";
  timingDetail.textContent =
    `${modeLabel}进行中…（本地计时 · model=${currentModelId} · provider=${currentProvider}）`;
  timingTimer = setInterval(() => {
    const elapsed = (performance.now() - timingStartedAt) / 1000;
    timingValue.textContent = formatSeconds(elapsed);
    timingDetail.textContent =
      `${modeLabel}进行中… 已用 ${formatSeconds(elapsed)} · model=${currentModelId} · provider=${currentProvider}`;
  }, 50);
}

function finishTiming(opts) {
  clearTimingTicker();
  const localSec = (performance.now() - timingStartedAt) / 1000;
  const serverSec =
    opts.serverSeconds != null && Number.isFinite(Number(opts.serverSeconds))
      ? Number(opts.serverSeconds)
      : null;
  const serverMs =
    opts.serverMs != null && Number.isFinite(Number(opts.serverMs))
      ? Number(opts.serverMs)
      : serverSec != null
        ? serverSec * 1000
        : null;
  const displaySec = serverSec != null ? serverSec : localSec;
  timingBox.className = "timing done";
  timingValue.textContent = formatSeconds(displaySec);

  const provider = opts.provider || currentProvider;
  const modelId = opts.modelId || currentModelId;
  const parts = [];
  parts.push(`${opts.modeLabel || timingMode || "合成"}完成`);
  parts.push(`model=${modelId}`);
  parts.push(`provider=${provider}`);
  if (opts.sampleRate != null) parts.push(`${opts.sampleRate} Hz`);
  if (serverSec != null) {
    parts.push(`服务端 ${formatSeconds(serverSec)}`);
    if (serverMs != null) parts.push(`(${serverMs.toFixed(1)} ms)`);
  }
  parts.push(`本地计时 ${formatSeconds(localSec)}`);
  if (opts.audioDuration != null && Number.isFinite(Number(opts.audioDuration))) {
    parts.push(`音频时长 ${Number(opts.audioDuration).toFixed(3)} s`);
  }
  if (opts.rtf != null && Number.isFinite(Number(opts.rtf))) {
    parts.push(`RTF ${Number(opts.rtf).toFixed(3)}`);
  }
  if (opts.extra) parts.push(opts.extra);
  timingDetail.textContent = parts.join(" · ");
  return { localSec, serverSec, displaySec };
}

function fillModelSelect(models, activeId) {
  modelsCache = models || [];
  const prev = modelSelect.value;
  modelSelect.innerHTML = "";
  modelsCache.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.id;
    const sr = m.expected_sample_rate ? `${m.expected_sample_rate}Hz` : "?Hz";
    opt.textContent = `${m.name} (${sr})${m.ready ? "" : " — 未下载"}`;
    opt.disabled = !m.ready;
    if (m.id === activeId) opt.selected = true;
    modelSelect.appendChild(opt);
  });
  if (!modelSelect.value && prev) modelSelect.value = prev;
}

function updateModelUi(data) {
  if (data.model_id) currentModelId = data.model_id;
  if (data.sample_rate != null) currentSampleRate = data.sample_rate;
  if (Array.isArray(data.models)) fillModelSelect(data.models, currentModelId);
  modelSelect.value = currentModelId;
  const sr = currentSampleRate != null ? `${currentSampleRate} Hz` : "—";
  modelBadge.textContent = `model: ${currentModelId} · ${sr}`;
  modelBadge.className = "provider-badge" + (switchingModel ? " busy" : "");
  const active = (data.models || modelsCache).find((m) => m.id === currentModelId);
  if (switchingModel) {
    modelHint.textContent = "正在切换模型并重建 OfflineTts / 预热…";
  } else if (active) {
    modelHint.textContent = `${active.description} · 目录 ${active.dir}`;
  }
}

function updateProviderUi(data) {
  currentProvider = (data && data.provider) || currentProvider || "cpu";
  cudaAvailable = !!(data && data.cuda_available);
  cudaToggle.checked = currentProvider === "cuda";
  cudaToggle.disabled = uiLocked() || !cudaAvailable;
  providerBadge.textContent = `provider: ${currentProvider}`;
  providerBadge.className =
    "provider-badge" +
    (currentProvider === "cuda" ? " cuda" : "") +
    (switchingProvider ? " busy" : "");
  if (!cudaAvailable) {
    providerHint.textContent =
      "未检测到 CUDA 运行时（需 sherpa +cuda12 轮子与 requirements-cuda.txt）。开关已禁用。";
  } else if (switchingProvider) {
    providerHint.textContent = "正在切换并重建 OfflineTts / 预热，请稍候…";
  } else {
    providerHint.textContent =
      "关闭 = CPU；开启 = CUDA。切换会热重建引擎并预热。";
  }
}

async function switchProvider(wantCuda) {
  const target = wantCuda ? "cuda" : "cpu";
  if (target === currentProvider) {
    updateProviderUi({ provider: currentProvider, cuda_available: cudaAvailable });
    return;
  }
  if (streaming) {
    errorEl.textContent = "请先停止当前流播放再切换 CUDA";
    cudaToggle.checked = currentProvider === "cuda";
    return;
  }
  switchingProvider = true;
  setBusy(false);
  updateProviderUi({ provider: currentProvider, cuda_available: cudaAvailable });
  errorEl.textContent = "";
  startTiming(`切换 provider → ${target}`);
  try {
    const res = await fetch("/api/provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: target, warmup: true }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : data.detail
            ? JSON.stringify(data.detail)
            : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    currentProvider = data.provider || target;
    if (data.sample_rate != null) currentSampleRate = data.sample_rate;
    finishTiming({
      modeLabel: data.changed ? "Provider 切换" : "Provider 未变",
      serverSeconds: (data.load_elapsed_seconds || 0) + (data.warmup_elapsed_seconds || 0),
      provider: currentProvider,
      modelId: data.model_id || currentModelId,
      sampleRate: data.sample_rate,
      extra:
        `load ${Number(data.load_elapsed_seconds || 0).toFixed(3)}s` +
        ` · warmup ${Number(data.warmup_elapsed_seconds || 0).toFixed(3)}s`,
    });
    await refreshStatus();
  } catch (err) {
    errorEl.textContent = String(err.message || err);
    finishTiming({ modeLabel: "Provider 切换（失败）", provider: currentProvider });
    cudaToggle.checked = currentProvider === "cuda";
    await refreshStatus();
  } finally {
    switchingProvider = false;
    setBusy(streaming);
    updateProviderUi({ provider: currentProvider, cuda_available: cudaAvailable });
  }
}

async function switchModel(modelId) {
  if (!modelId || modelId === currentModelId) {
    modelSelect.value = currentModelId;
    return;
  }
  if (streaming) {
    errorEl.textContent = "请先停止当前流播放再切换模型";
    modelSelect.value = currentModelId;
    return;
  }
  switchingModel = true;
  setBusy(false);
  updateModelUi({ model_id: currentModelId, sample_rate: currentSampleRate, models: modelsCache });
  errorEl.textContent = "";
  startTiming(`切换模型 → ${modelId}`);
  try {
    const res = await fetch("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId, warmup: true }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : data.detail
            ? JSON.stringify(data.detail)
            : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    currentModelId = data.model_id || modelId;
    if (data.sample_rate != null) currentSampleRate = data.sample_rate;
    // WebAudio context is sample-rate specific — reset on model change
    if (audioCtx) {
      try { await audioCtx.close(); } catch (_) {}
      audioCtx = null;
    }
    finishTiming({
      modeLabel: data.changed ? "模型切换" : "模型未变",
      serverSeconds: (data.load_elapsed_seconds || 0) + (data.warmup_elapsed_seconds || 0),
      provider: data.provider || currentProvider,
      modelId: currentModelId,
      sampleRate: data.sample_rate,
      extra:
        `load ${Number(data.load_elapsed_seconds || 0).toFixed(3)}s` +
        ` · warmup ${Number(data.warmup_elapsed_seconds || 0).toFixed(3)}s` +
        (data.message ? ` · ${data.message}` : ""),
    });
    await refreshStatus();
  } catch (err) {
    errorEl.textContent = String(err.message || err);
    finishTiming({ modeLabel: "模型切换（失败）", modelId: currentModelId });
    modelSelect.value = currentModelId;
    await refreshStatus();
  } finally {
    switchingModel = false;
    setBusy(streaming);
    updateModelUi({ model_id: currentModelId, sample_rate: currentSampleRate, models: modelsCache });
  }
}

cudaToggle.addEventListener("change", () => {
  switchProvider(cudaToggle.checked);
});
modelSelect.addEventListener("change", () => {
  switchModel(modelSelect.value);
});

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    updateProviderUi(data);
    updateModelUi(data);
    if (data.model_ready) {
      statusBox.className = "status ok";
      statusBox.textContent =
        `模型已就绪\n` +
        `当前: ${data.model_name || data.model_id} (${data.model_id})\n` +
        `目录: ${data.model_dir}\n` +
        `采样率: ${data.sample_rate || "-"} Hz\n` +
        `线程: ${data.num_threads || "-"} · provider: ${data.provider || "cpu"}\n` +
        `CUDA 运行时: ${data.cuda_available ? "可用" : "不可用"}` +
        (data.busy ? "\n状态: 合成进行中" : "");
      if (!uiLocked()) {
        streamBtn.disabled = false;
        synthBtn.disabled = false;
      }
    } else {
      statusBox.className = "status bad";
      statusBox.textContent =
        `当前模型未就绪 (${data.model_id || "-"})\n` +
        `请运行对应下载脚本\n缺失: ${(data.missing || []).join(", ") || "未知"}`;
      streamBtn.disabled = true;
      synthBtn.disabled = true;
    }
  } catch (err) {
    statusBox.className = "status bad";
    statusBox.textContent = `无法连接后端: ${err}`;
    streamBtn.disabled = true;
    synthBtn.disabled = true;
    cudaToggle.disabled = true;
    modelSelect.disabled = true;
  }
}

function ensureAudioContext(sampleRate) {
  if (!audioCtx || audioCtx.state === "closed") {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate });
    } catch (_) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  streamSampleRate = sampleRate || audioCtx.sampleRate;
  nextPlayTime = audioCtx.currentTime + 0.05;
}

function scheduleChunk(float32) {
  if (!audioCtx || !float32 || float32.length === 0) return;
  recordedChunks.push(float32);
  const buffer = audioCtx.createBuffer(1, float32.length, streamSampleRate);
  const channel = buffer.getChannelData(0);
  channel.set(float32);
  const src = audioCtx.createBufferSource();
  src.buffer = buffer;
  src.connect(audioCtx.destination);
  const startAt = Math.max(audioCtx.currentTime + 0.01, nextPlayTime);
  src.start(startAt);
  nextPlayTime = startAt + buffer.duration;
  receivedSamples += float32.length;
}

function floatChunksToWavBlob(chunks, sampleRate) {
  let total = 0;
  chunks.forEach((c) => (total += c.length));
  const pcm = new Float32Array(total);
  let offset = 0;
  chunks.forEach((c) => {
    pcm.set(c, offset);
    offset += c.length;
  });
  const pcm16 = new Int16Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const buffer = new ArrayBuffer(44 + pcm16.length * 2);
  const view = new DataView(buffer);
  const writeStr = (o, s) => {
    for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + pcm16.length * 2, true);
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
  view.setUint32(40, pcm16.length * 2, true);
  new Int16Array(buffer, 44).set(pcm16);
  return new Blob([buffer], { type: "audio/wav" });
}

function stopStreaming(reason) {
  streaming = false;
  if (ws) {
    try { ws.close(); } catch (_) {}
    ws = null;
  }
  setBusy(false);
  if (reason) streamMeta.textContent = reason;
}

streamBtn.addEventListener("click", async () => {
  errorEl.textContent = "";
  meta.textContent = "";
  const text = textEl.value.trim();
  if (!text) {
    errorEl.textContent = "请输入文本";
    return;
  }

  stopStreaming();
  recordedChunks.length = 0;
  receivedSamples = 0;
  progressBar.style.width = "0%";
  streaming = true;
  setBusy(true);
  streamMeta.textContent = "流播放：连接中…";
  startTiming("实时流播放");

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/tts`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    streamMeta.textContent = `流播放：合成中（${currentModelId} / ${currentProvider}）…`;
    startTiming("实时流播放");
    ws.send(
      JSON.stringify({
        text,
        speed: Number(speedEl.value),
        sid: 0,
        mode: currentMode,
      })
    );
  };

  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg.type === "meta") {
        if (msg.provider) currentProvider = msg.provider;
        if (msg.model_id) currentModelId = msg.model_id;
        if (msg.sample_rate) currentSampleRate = msg.sample_rate;
        updateProviderUi({ provider: currentProvider, cuda_available: cudaAvailable });
        updateModelUi({ model_id: currentModelId, sample_rate: currentSampleRate, models: modelsCache });
        ensureAudioContext(msg.sample_rate || 44100);
        streamMeta.textContent =
          `流播放：已开始（${msg.sample_rate} Hz, model=${msg.model_id || currentModelId}, provider=${msg.provider || currentProvider}）`;
      } else if (msg.type === "progress") {
        const p = Math.max(0, Math.min(1, Number(msg.progress) || 0));
        progressBar.style.width = `${(p * 100).toFixed(1)}%`;
        const localSec = (performance.now() - timingStartedAt) / 1000;
        streamMeta.textContent =
          `流播放：进度 ${(p * 100).toFixed(0)}% · 已用 ${formatSeconds(localSec)} · ${currentModelId}`;
      } else if (msg.type === "end") {
        progressBar.style.width = "100%";
        const dur = receivedSamples / (streamSampleRate || 1);
        if (msg.provider) currentProvider = msg.provider;
        if (msg.model_id) currentModelId = msg.model_id;
        const timing = finishTiming({
          modeLabel: "实时流播放",
          serverSeconds: msg.elapsed_seconds,
          serverMs: msg.elapsed_ms,
          audioDuration: msg.audio_duration != null ? msg.audio_duration : dur,
          rtf: msg.rtf,
          provider: msg.provider || currentProvider,
          modelId: msg.model_id || currentModelId,
          sampleRate: msg.sample_rate || currentSampleRate,
        });
        streamMeta.textContent =
          `流播放完成 · ${msg.model_id || currentModelId} · ${msg.sample_rate || currentSampleRate}Hz · ` +
          `总时长 ${formatSeconds(timing.displaySec)} · RTF ${(msg.rtf || 0).toFixed(3)}`;
        if (recordedChunks.length) {
          const blob = floatChunksToWavBlob(recordedChunks, streamSampleRate);
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          objectUrl = URL.createObjectURL(blob);
          player.src = objectUrl;
          downloadLink.href = objectUrl;
          downloadLink.download = "stream_tts.wav";
          downloadLink.classList.remove("disabled");
        }
        stopStreaming(streamMeta.textContent);
      } else if (msg.type === "error") {
        errorEl.textContent = msg.message || "流式合成失败";
        finishTiming({ modeLabel: "实时流播放（失败）" });
        stopStreaming("流播放失败");
      }
      return;
    }
    scheduleChunk(new Float32Array(ev.data));
  };

  ws.onerror = () => {
    errorEl.textContent = "WebSocket 错误";
    finishTiming({ modeLabel: "实时流播放（出错）" });
    stopStreaming("流播放出错");
  };

  ws.onclose = () => {
    if (streaming) {
      finishTiming({ modeLabel: "实时流播放（中断）" });
      stopStreaming(streamMeta.textContent || "连接已关闭");
    }
  };
});

stopBtn.addEventListener("click", () => {
  const localSec = timingStartedAt ? (performance.now() - timingStartedAt) / 1000 : 0;
  finishTiming({
    modeLabel: "已停止",
    extra: `停止时已用 ${formatSeconds(localSec)}`,
  });
  stopStreaming("已停止");
  if (audioCtx) {
    try { audioCtx.close(); } catch (_) {}
    audioCtx = null;
  }
});

synthBtn.addEventListener("click", async () => {
  errorEl.textContent = "";
  meta.textContent = "";
  const text = textEl.value.trim();
  if (!text) {
    errorEl.textContent = "请输入文本";
    return;
  }
  setBusy(true);
  synthBtn.textContent = "合成中…";
  startTiming("整段合成");
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        speed: Number(speedEl.value),
        sid: 0,
        mode: currentMode,
      }),
    });
    if (!res.ok) {
      let detail = await res.text();
      try {
        const j = JSON.parse(detail);
        detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch (_) {}
      throw new Error(detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(blob);
    player.src = objectUrl;
    await player.play().catch(() => {});
    downloadLink.href = objectUrl;
    downloadLink.download = res.headers.get("X-Saved-As") || "tts.wav";
    downloadLink.classList.remove("disabled");

    const serverSec = parseFloat(res.headers.get("X-Elapsed-Seconds") || "");
    const serverMs = parseFloat(res.headers.get("X-Elapsed-Ms") || "");
    const audioDur = parseFloat(res.headers.get("X-Audio-Duration") || "");
    const rtf = parseFloat(res.headers.get("X-RTF") || "");
    const providerHdr = res.headers.get("X-Provider") || currentProvider;
    const modelHdr = res.headers.get("X-Model-Id") || currentModelId;
    const srHdr = parseInt(res.headers.get("X-Sample-Rate") || "", 10);
    currentProvider = providerHdr;
    currentModelId = modelHdr;
    if (Number.isFinite(srHdr)) currentSampleRate = srHdr;
    updateProviderUi({ provider: currentProvider, cuda_available: cudaAvailable });
    updateModelUi({ model_id: currentModelId, sample_rate: currentSampleRate, models: modelsCache });
    const timing = finishTiming({
      modeLabel: "整段合成",
      serverSeconds: Number.isFinite(serverSec) ? serverSec : null,
      serverMs: Number.isFinite(serverMs) ? serverMs : null,
      audioDuration: Number.isFinite(audioDur) ? audioDur : null,
      rtf: Number.isFinite(rtf) ? rtf : null,
      provider: providerHdr,
      modelId: modelHdr,
      sampleRate: Number.isFinite(srHdr) ? srHdr : currentSampleRate,
    });
    meta.textContent =
      `整段 · ${modelHdr} · ${Number.isFinite(srHdr) ? srHdr : "-"}Hz · provider=${providerHdr} · ` +
      `音频 ${Number.isFinite(audioDur) ? audioDur.toFixed(3) : "-"}s · ` +
      `总时长 ${formatSeconds(timing.displaySec)} · RTF ${Number.isFinite(rtf) ? rtf.toFixed(3) : "-"}`;
  } catch (err) {
    errorEl.textContent = String(err.message || err);
    finishTiming({ modeLabel: "整段合成（失败）" });
  } finally {
    setBusy(false);
    synthBtn.textContent = "整段合成下载";
  }
});

refreshStatus();
