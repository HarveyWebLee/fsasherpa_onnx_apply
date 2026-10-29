# fsatts — 本地中英混合 sherpa-onnx TTS 插件

生产级本地 TTS 服务：**React 19 + Ant Design 6** 前端 + **FastAPI** 后端，支持中英混合合成与 ≥50 在途并发。

## 功能

- 中英混合 Melo（44.1k / 8k），支持英文与中英混读
- 模型 / 说话人切换（切换**不会**自动合成）
- HTTP `/api/tts`、流式 `/api/tts/stream`、WebSocket `/ws/tts`，CORS 可配
- 引擎池 + 在途队列（默认 `TTS_MAX_INFLIGHT=64`，满则 503）
- Python 依赖由 **uv** 管理（`pyproject.toml` + `uv.lock`）

## 快速开始

```powershell
# 需要已安装 uv: https://docs.astral.sh/uv/
cd E:\WORK\CODE\fsasherpa-onnx-test
uv sync
# 构建前端（首次 / 前端变更后）
cd web; pnpm install; pnpm run build; cd ..
# 下载默认模型（两套 Melo）
uv run python scripts/download_models.py --bundle
# 启动
.\run_web.ps1
# 或 uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 19658
```

打开 http://127.0.0.1:19658 （默认端口 **19658**）

## 模型

本项目**仅保留支持中英混合**的 Melo 模型；纯中文多说话人模型已移除。

| id             | 说明                     | 说话人 | 默认打包 |
| -------------- | ------------------------ | ------ | -------- |
| melo-zh-en-44k | 中英混合 · 44.1 kHz      | 1      | 是       |
| melo-zh-en-8k  | 中英混合 · 8 kHz（更快） | 1      | 是       |

```powershell
uv run python scripts/download_models.py --list
uv run python scripts/download_models.py --bundle
uv run python scripts/download_models.py --id melo-zh-en-44k
# 仅 HuggingFace / hf-mirror：
uv run python scripts/download_models.py --hf-only --id melo-zh-en-8k
```

下载优先使用 gh-proxy / ghproxy / ghfast，失败再回退 HuggingFace（`hf-mirror.com`）。

## 并发

| 环境变量             | 默认                 | 含义                       |
| -------------------- | -------------------- | -------------------------- |
| TTS_ENGINE_POOL_SIZE | min(max(4,cpu/2),16) | 每模型 OfflineTts 实例数   |
| TTS_MAX_INFLIGHT     | 64                   | 在途请求上限（≥50）        |
| TTS_MAX_QUEUE        | 128                  | 排队上限                   |
| TTS_PRELOAD          | 1                    | 启动预加载当前模型         |
| TTS_NUM_THREADS      | 2                    | 每实例 ONNX 线程           |
| TTS_PROVIDER         | cpu                  | cpu / cuda                 |
| TTS_PORT             | 19658                | HTTP 服务端口              |

真并行推理受 **引擎池大小 × 内存** 限制。把 `TTS_ENGINE_POOL_SIZE` 调高可提高并行度；`TTS_MAX_INFLIGHT` 保证至少可接受 50+ 在途请求，队列满返回 **503 + Retry-After**。

## API

详见 [docs/PLUGIN_API.md](docs/PLUGIN_API.md)。健康检查含 inflight / queue_depth。

## 打包

见 [docs/PACKAGING.md](docs/PACKAGING.md)。默认把两套 Melo 打进安装包；可用 `INCLUDE_MODELS=0` / `-SkipModels` 跳过。

## 开发前端

```powershell
# 终端 1：后端
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 19658
# 终端 2：Vite
cd web; pnpm run dev
```

## 代码检查与格式化

### 前端（`web/`，Prettier + ESLint + TypeScript，包管理用 pnpm）

```powershell
cd web
pnpm install
pnpm run format        # Prettier 写回
pnpm run lint          # ESLint
pnpm run lint:fix     # ESLint 自动修复
pnpm run typecheck     # tsc --noEmit
pnpm run check         # typecheck + lint + format:check
pnpm run build         # 先 typecheck 再 vite build
```

配置：`web/.prettierrc.json`、`web/eslint.config.js`（flat，React 19 + TS + Vite）。

### 后端（Python / FastAPI，Ruff via uv）

```powershell
uv sync               # 含 dev 组：ruff、pyinstaller
uv run ruff format app scripts
uv run ruff check app scripts
uv run ruff check --fix app scripts
```
