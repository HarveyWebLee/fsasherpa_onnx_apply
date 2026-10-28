const textEl = document.getElementById("text");
const speedEl = document.getElementById("speed");
const speedVal = document.getElementById("speedVal");
const synthBtn = document.getElementById("synthBtn");
const player = document.getElementById("player");
const meta = document.getElementById("meta");
const errorEl = document.getElementById("error");
const statusBox = document.getElementById("statusBox");
const downloadLink = document.getElementById("downloadLink");
const modes = document.querySelectorAll(".mode");

let currentMode = "mixed";
let objectUrl = null;

const defaults = {
  zh: "你好，欢迎使用本地文本转语音测试。",
  en: "Hello, this is a local text to speech demo.",
  mixed: "This is a 中英文的 text to speech 测试例子。",
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

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.model_ready) {
      statusBox.className = "status ok";
      statusBox.textContent =
        `模型已就绪\n目录: ${data.model_dir}\n采样率: ${data.sample_rate || "-"} Hz\n说话人数: ${data.num_speakers ?? "-"}`;
      synthBtn.disabled = false;
    } else {
      statusBox.className = "status bad";
      statusBox.textContent =
        `模型未就绪。请在项目根目录运行:\\n.\\scripts\\download_model.ps1\\n缺失: ${(data.missing || []).join(", ") || "未知"}`;
      synthBtn.disabled = true;
    }
  } catch (err) {
    statusBox.className = "status bad";
    statusBox.textContent = `无法连接后端: ${err}`;
    synthBtn.disabled = true;
  }
}

synthBtn.addEventListener("click", async () => {
  errorEl.textContent = "";
  meta.textContent = "";
  const text = textEl.value.trim();
  if (!text) {
    errorEl.textContent = "请输入文本";
    return;
  }
  synthBtn.disabled = true;
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
      `时长 ${res.headers.get("X-Audio-Duration") || "-"}s · ` +
      `耗时 ${res.headers.get("X-Elapsed-Seconds") || "-"}s · ` +
      `RTF ${res.headers.get("X-RTF") || "-"} · ` +
      `${res.headers.get("X-Sample-Rate") || "-"} Hz`;
  } catch (err) {
    errorEl.textContent = String(err.message || err);
  } finally {
    synthBtn.disabled = false;
    synthBtn.textContent = "合成并播放";
  }
});

refreshStatus();
