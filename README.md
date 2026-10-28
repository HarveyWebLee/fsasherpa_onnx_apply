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
python -m uvicorn app.main:app --host 127.0.0.1 --port 7860
```

快捷脚本（按终端选择）：

| 终端 | 命令 |
|------|------|
| PowerShell | `.\run_web.ps1` |
| Git Bash (MINGW64) | `./run_web.sh` |
| Git Bash 调 PowerShell | `powershell.exe -File ./run_web.ps1` |
| CMD | `run_web.bat` |

> 不要在 Git Bash 里直接 `./run_web.ps1`：bash 会把 `.ps1` 当 shell 脚本执行，并报 BOM / `Set-Location` 找不到等错误。

浏览器打开：http://127.0.0.1:7860

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