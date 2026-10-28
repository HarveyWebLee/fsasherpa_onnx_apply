# sherpa-onnx 文本转语音（中英）本地网页测试

基于 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) Python API，使用官方预训练模型 **vits-melo-tts-zh_en**（中文 + 英文，单说话人），提供：

- 中文 TTS
- 英文 TTS
- 中英混合 TTS
- 本地网页测试（输入文本 -> 合成 -> 在线播放 / 下载 WAV）

## 环境

本机已验证使用：

- **Python 3.14.4**（`python` / `py -3.14`）
- Windows 10+
- 依赖见 `requirements.txt`（含 `sherpa-onnx` 2.0.x，已有 cp314 Windows 轮子）

> 若你机器上的 Python 装不上 `sherpa-onnx`，请用 `py -0p` 查看其他解释器，并在对应环境中安装。

## 目录结构

```text
fsasherpa-onnx-test/
  app/
    main.py           # FastAPI 网页服务
    tts_engine.py     # sherpa-onnx OfflineTts 封装
  static/             # 前端页面
  scripts/
    download_model.ps1
    cli_tts.py
  models/             # 大模型（gitignore，需单独下载）
  outputs/            # 合成出的 wav
  requirements.txt
  run_web.ps1
  run_web.sh
  run_web.bat
  README.md
```

## 安装

在项目根目录：

```powershell
cd E:\WORK\CODE\fsasherpa-onnx-test
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

## 下载模型

约 50-170MB。推荐一键脚本（优先 GitHub release，失败则走 Hugging Face / hf-mirror）：

```powershell
.\scripts\download_model.ps1
```

手动方式（任选其一）：

1. GitHub Release：
   https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2
2. Hugging Face：https://huggingface.co/csukuangfj/vits-melo-tts-zh_en

需要至少：`model.onnx`（或把 `model.int8.onnx` 复制为 `model.onnx`）、`lexicon.txt`、`tokens.txt`，以及 `phone.fst` / `date.fst` / `number.fst`、`dict/`。

目标路径：

```text
models/vits-melo-tts-zh_en/model.onnx
models/vits-melo-tts-zh_en/lexicon.txt
models/vits-melo-tts-zh_en/tokens.txt
models/vits-melo-tts-zh_en/dict/
```

> 若使用 int8 权重，体积更小、速度更快，音质略低于 fp32 `model.onnx`。

## 启动网页

```powershell
cd E:\WORK\CODE\fsasherpa-onnx-test
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 19658
```

快捷脚本（按终端选择）：

| 终端 | 命令 |
|------|------|
| PowerShell | `.\run_web.ps1` |
| Git Bash (MINGW64) | `./run_web.sh` |
| Git Bash 调 PowerShell | `powershell.exe -File ./run_web.ps1` |
| CMD | `run_web.bat` |

> 不要在 Git Bash 里直接 `./run_web.ps1`：bash 会把 `.ps1` 当 shell 脚本执行，并报 BOM / `Set-Location` 找不到等错误。

浏览器打开：http://127.0.0.1:19658

## 实时流播放（边合成边播）

本项目用 sherpa-onnx `OfflineTts.generate(..., callback=...)` 在合成过程中分块回调 PCM，经 **WebSocket** 推到浏览器，前端用 **Web Audio API** 排队播放。

### 网页上怎么用

1. 启动服务（PowerShell / Git Bash / CMD 任选）：

```powershell
.\run_web.ps1
```

```bash
./run_web.sh
```

2. 打开 http://127.0.0.1:19658
3. 输入中文 / 英文 / 中英混合文本（可用上方模式按钮填入示例）
4. 点击 **「实时流播放」** —— 合成尚未结束时就应开始出声；进度条会更新
5. 页面中部 **「文本转语音总时长」** 会实时跳动已用时间；结束后显示服务端/本地总耗时（秒）
6. 需要完整文件时：点 **「整段合成下载」**，或流播放结束后用 **「下载 WAV」**
6. 播放中可点 **「停止」** 中断

### 接口

| 接口 | 说明 |
|------|------|
| `WS /ws/tts` | 实时流（推荐）。客户端发 JSON `{"text","speed","sid"}`；服务端先发 meta JSON，再发 binary float32 LE PCM，期间可发 progress，最后 end/error |
| `POST /api/tts/stream` | HTTP chunked：首行 JSON meta + 后续 raw f32le（便于脚本验证） |
| `POST /api/tts` | 整段 WAV（原有） |

### 本地脚本验证流式端点

先启动网页服务，再另开终端：

```powershell
.\.venv\Scripts\python.exe .\scripts\test_stream_ws.py
```

期望输出多行 `chunk#N: ... bytes`，最后 `RESULT ok=True`。

## CLI 验证

```powershell
.\.venv\Scripts\python.exe .\scripts\cli_tts.py --example mixed
.\.venv\Scripts\python.exe .\scripts\cli_tts.py --example zh
.\.venv\Scripts\python.exe .\scripts\cli_tts.py --example en
```

## 三种语言示例

| 模式 | 示例文本 |
|------|----------|
| 中文 | 你好，欢迎使用本地文本转语音测试。 |
| 英文 | Hello, this is a local text to speech demo. |
| 中英混合 | This is a 中英文的 text to speech 测试例子。 |

说明：同一模型覆盖三种模式；英文词需出现在 `lexicon.txt` 中。

## API

- `GET /api/status` — 模型是否就绪
- `POST /api/tts` — JSON：`{"text":"...","speed":1.0,"sid":0}`，返回 `audio/wav`

## 常见问题

1. **下载失败**：国内访问 GitHub/HF 可能超时，可开代理或使用 hf-mirror 后重跑下载脚本。
2. **onnxruntime / DLL 报错**：安装 Visual C++ Redistributable。
3. **首次合成较慢**：模型在第一次请求时加载。

## 许可

本仓库测试代码可自由使用；模型与 sherpa-onnx 遵循各自上游协议。