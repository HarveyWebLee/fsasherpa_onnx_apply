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
const modes = document.querySelectorAll(".mode");

let currentMode = "mixed";
let objectUrl = null;
let ws = null;
let audioCtx = null;
let nextPlayTime = 0;
let streamSampleRate = 44100;
let receivedSamples = 0;
let streaming = false;
const recordedChunks = [];

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

function setBusy(isBusy) {
  streamBtn.disabled = isBusy;
  synthBtn.disabled = isBusy;
  stopBtn.disabled = !isBusy;
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.model_ready) {
      statusBox.className = "status ok";
      statusBox.textContent =
        `模型已就绪\n目录: ${data.model_dir}\n采样率: ${data.sample_rate || "-"} Hz\n` +
        `流式: WebSocket ${data.ws_tts || "/ws/tts"}`;
      streamBtn.disabled = false;
      synthBtn.disabled = false;
    } else {
      statusBox.className = "status bad";
      statusBox.textContent =
        `模型未就绪。请运行 scripts/download_model.ps1\n缺失: ${(data.missing || []).join(", ") || "未知"}`;
      streamBtn.disabled = true;
      synthBtn.disabled = true;
    }
  } catch (err) {
    statusBox.className = "status bad";
    statusBox.textContent = `无法连接后端: ${err}`;
    streamBtn.disabled = true;
    synthBtn.disabled = true;
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
  // copyToChannel needs a plain Float32Array
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
  if (reason) {
    streamMeta.textContent = reason;
  }
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

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/tts`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    streamMeta.textContent = "流播放：合成中，边收边播…";
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
      try {
        msg = JSON.parse(ev.data);
      } catch (_) {
        return;
      }
      if (msg.type === "meta") {
        ensureAudioContext(msg.sample_rate || 44100);
        streamMeta.textContent = `流播放：已开始（${msg.sample_rate} Hz, ${msg.format || "f32le"}）`;
      } else if (msg.type === "progress") {
        const p = Math.max(0, Math.min(1, Number(msg.progress) || 0));
        progressBar.style.width = `${(p * 100).toFixed(1)}%`;
        streamMeta.textContent = `流播放：进度 ${(p * 100).toFixed(0)}% · 已收 ${receivedSamples} samples`;
      } else if (msg.type === "end") {
        progressBar.style.width = "100%";
        const dur = receivedSamples / (streamSampleRate || 1);
        streamMeta.textContent =
          `流播放完成 · 时长约 ${dur.toFixed(2)}s · 耗时 ${(msg.elapsed_seconds || 0).toFixed(2)}s · RTF ${(msg.rtf || 0).toFixed(3)}`;
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
        stopStreaming("流播放失败");
      }
      return;
    }

    // binary PCM float32 LE
    const f32 = new Float32Array(ev.data);
    scheduleChunk(f32);
  };

  ws.onerror = () => {
    errorEl.textContent = "WebSocket 错误";
    stopStreaming("流播放出错");
  };

  ws.onclose = () => {
    if (streaming) {
      stopStreaming(streamMeta.textContent || "连接已关闭");
    }
  };
});

stopBtn.addEventListener("click", () => {
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
    meta.textContent =
      `整段 · 时长 ${res.headers.get("X-Audio-Duration") || "-"}s · ` +
      `耗时 ${res.headers.get("X-Elapsed-Seconds") || "-"}s · ` +
      `RTF ${res.headers.get("X-RTF") || "-"} · ` +
      `${res.headers.get("X-Sample-Rate") || "-"} Hz`;
  } catch (err) {
    errorEl.textContent = String(err.message || err);
  } finally {
    setBusy(false);
    synthBtn.textContent = "整段合成下载";
  }
});

refreshStatus();
