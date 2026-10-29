# fsatts — 本地多模型 sherpa-onnx TTS 插件

生产级本地 TTS 服务：**React 19 + Ant Design 6** 前端 + **FastAPI** 后端，支持多说话人模型切换与 ≥50 在途并发。

## 功能

- 中英混合 Melo（44.1k / 8k）+ 多说话人中文模型（zh-ll 5 / 范晨C 187 / AISHELL-3 174 / Theresa·Eula 804）
- 按模型切换说话人（大列表可搜索）；切换**不会**自动合成
- HTTP `/api/tts`、流式 `/api/tts/stream`、WebSocket `/ws/tts`，CORS 可配
- 引擎池 + 在途队列（默认 `TTS_MAX_INFLIGHT=64`，满则 503）
- Python 依赖用 **uv** 管理（`pyproject.toml` + `uv.lock`）

## 快速开始

```powershell
# 需要已安装 uv: https://docs.astral.sh/uv/
cd E:\WORK\CODE\fsasherpa-onnx-test
uv sync
# 构建前端（首次 / 前端变更后）
cd web; npm install; npm run build; cd ..
# 下载默认打包模型（Melo + zh-ll + aishell3；大模型按需）
uv run python scripts/download_models.py --bundle
# 启动
.\run_web.ps1
# 或
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 19658
```

打开 http://127.0.0.1:19658

## 模型

| id | 说明 | 说话人 | 默认打包 |
|----|------|--------|----------|
| melo-zh-en-44k | 中英 44.1k | 1 | 是 |
| melo-zh-en-8k | 中英 8k | 1 | 是 |
| zh-ll | 中文多说话人 | 5 | 是 |
| aishell3 | icefall AISHELL-3 | 174 | 是 |
| fanchen-c | 范晨 C | 187 | 否 |
| theresa | Theresa | 804 | 否 |
| eula | Eula | 804 | 否 |

```powershell
uv run python scripts/download_models.py --list
uv run python scripts/download_models.py --id fanchen-c
uv run python scripts/download_models.py --id theresa --id eula
# 仅 HuggingFace / hf-mirror：
uv run python scripts/download_models.py --hf-only --id zh-ll
```

下载优先使用 gh-proxy / ghproxy / ghfast，失败再回退 HuggingFace（`hf-mirror.com`）。大模型（theresa / eula）默认不打进安装包，按需下载即可。

## 并发

| 环境变量 | 默认 | 含义 |
|----------|------|------|
| TTS_ENGINE_POOL_SIZE | min(max(4,cpu/2),16) | 每模型 OfflineTts 实例数 |
| TTS_MAX_INFLIGHT | 64 | 在途请求上限（≥50） |
| TTS_MAX_QUEUE | 128 | 排队上限 |
| TTS_PRELOAD | 1 | 启动预加载当前模型 |
| TTS_NUM_THREADS | 2 | 每实例 ONNX 线程 |
| TTS_PROVIDER | cpu | cpu / cuda |

真并行推理受 **引擎池大小 × 内存** 限制（每实例约 100–160MB）。把 `TTS_ENGINE_POOL_SIZE` 调高可提高并行度；`TTS_MAX_INFLIGHT` 保证至少可接受 50+ 在途请求，队列满返回 **503 + Retry-After**。

## API

详见 [docs/PLUGIN_API.md](docs/PLUGIN_API.md)。健康检查含 inflight / queue_depth。

## 打包

见 [docs/PACKAGING.md](docs/PACKAGING.md)。大模型（theresa/eula/fanchen）默认不打进安装包，请用下载脚本按需获取。

## 开发前端

```powershell
# 终端 1：后端
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 19658
# 终端 2：Vite
cd web; npm run dev
```

## 目录

```
app/                 FastAPI + TTS 引擎池
web/                 React 19 + Ant Design 6（构建产物 web/dist）
scripts/             下载 / 打包 / 压测
models/              已入库（*.onnx 走 Git LFS；压缩包等杂项见 models/.gitignore）
docs/                PLUGIN_API / PACKAGING
pyproject.toml       uv 项目定义
uv.lock              锁定依赖
```
