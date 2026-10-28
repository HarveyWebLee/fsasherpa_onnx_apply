# 作为插件服务给其他网页调用

本服务默认监听 **`0.0.0.0:19658`**，已启用 **CORS**（默认允许任意源 `*`）。

## 快速检查

```bash
curl -s http://127.0.0.1:19658/api/health
```

## 浏览器跨域示例（整段 WAV）

```html
<button id="speak">Speak</button>
<script>
const BASE = "http://127.0.0.1:19658"; // 或局域网 IP:19658

document.getElementById("speak").onclick = async () => {
  const res = await fetch(`${BASE}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: "你好，这是跨域 TTS 调用示例。",
      speed: 1.0,
      sid: 0,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  new Audio(url).play();
  console.log("elapsed_s", res.headers.get("X-Elapsed-Seconds"));
};
</script>
```

## WebSocket 流式示例

```javascript
const ws = new WebSocket("ws://127.0.0.1:19658/ws/tts");
ws.binaryType = "arraybuffer";
ws.onopen = () => {
  ws.send(JSON.stringify({ text: "第一句。第二句。", speed: 1.0, sid: 0 }));
};
ws.onmessage = (ev) => {
  if (typeof ev.data === "string") {
    const msg = JSON.parse(ev.data);
    console.log(msg.type, msg);
  } else {
    // Float32 LE PCM mono — 用 Web Audio 播放
    console.log("pcm bytes", ev.data.byteLength);
  }
};
```

## CORS 收紧

```bash
# Windows PowerShell
$env:TTS_CORS_ORIGINS="http://localhost:5173,https://app.example.com"
.\run_web.ps1
```

## 注意点

1. **混合内容**：外站若是 `https://`，浏览器可能拦截对 `http://127.0.0.1` 的请求；开发可用本机 https 反代，或页面也用 http。
2. **WebSocket 源**：`ws://` / `wss://` 需与页面策略一致；CORS 头主要约束 XHR/fetch，WS 仍受浏览器连接策略影响。
3. **局域网**：把 BASE 换成插件机器 IP，并放行防火墙 TCP **19658**。
4. **语速 / 角色**：`speed` ∈ [0.5, 2.0]；Melo 中英目前 `sid` 仅 `0`。
5. **不要公网裸奔**：默认 CORS=* 仅适合受控环境。
