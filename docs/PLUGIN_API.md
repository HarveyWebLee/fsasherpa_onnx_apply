# fsatts Plugin API

Base URL 默认：http://127.0.0.1:19658  
CORS：TTS_CORS_ORIGINS（默认 *）

## Health / Status

- GET /api/health — ok、model_ready、inflight、queue_depth、max_inflight、concurrency
- GET /api/status — 模型列表、说话人、并发统计、voice roles

## Models / Speakers / Provider

- GET /api/models — 注册表与就绪状态
- POST /api/models { "model_id", "warmup": true } — 切换默认模型（懒加载池）
- GET /api/speakers?model_id= — 某模型说话人列表（大列表可搜索由前端处理）
- GET|POST /api/provider — cpu / cuda

## TTS

### POST /api/tts

`json
{
  "text": "你好 hello",
  "speed": 1.0,
  "sid": 0,
  "model_id": "melo-zh-en-44k",
  "provider": "cpu"
}
`

返回 udio/wav。响应头：X-Elapsed-Ms、X-RTF、X-Sample-Rate、X-Model-Id、X-Sid 等。

繁忙（超过 TTS_MAX_INFLIGHT）→ **503** + Retry-After: 2。

### POST /api/tts/stream

首行 JSON meta（\n 结尾），随后 float32 LE PCM 块。

### WS /ws/tts

首帧 JSON 请求；服务端推送 meta / binary chunk / progress / end / error。

## 并发说明

单进程 uvicorn + 每模型引擎池。请保持 workers=1，用 TTS_ENGINE_POOL_SIZE 扩并行。

## 语言能力（Language）

本服务仅提供支持中英混合的模型：

| model_id | lang | 英文 | 中英混合 |
|---|---|---|---|
| `melo-zh-en-44k` / `melo-zh-en-8k` | `zh+en` | 支持 | 支持 |
| `kokoro-zh-en-v1_1` | `zh+en` | 支持 | 支持（103 说话人） |

`GET /api/models` 与 `/api/status` 返回的每条模型含 `lang` 字段（`zh+en`）。
默认 HTTP 端口：**19658**（环境变量 `TTS_PORT`）。

