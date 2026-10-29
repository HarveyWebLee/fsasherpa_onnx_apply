# 跨平台本地插件服务打包

把本仓库打成可在 **Windows x64**、**Linux amd64**、**麒麟 V10 arm64** 运行的本地 TTS 插件服务，供浏览器/客户端通过 HTTP / WebSocket 调用。

## 默认监听

| 变量 | 默认 | 说明 |
|------|------|------|
| `TTS_HOST` | `0.0.0.0` | 插件模式监听所有网卡；仅本机可设 `127.0.0.1` |
| `TTS_PORT` | `19658` | 服务端口 |
| `TTS_CORS_ORIGINS` | `*` | CORS；生产建议改为具体源，逗号分隔 |
| `TTS_MODELS_ROOT` | `./models`（打包后为 exe 旁 `models/`） | 模型目录；**默认会打进安装包**（见下）；也可外置覆盖 |
| `TTS_PROVIDER` | `cpu` | `cpu` / `cuda`（CUDA 需额外运行时） |

健康检查：`GET http://127.0.0.1:19658/api/health`

## 模型是否打进安装包

| 行为 | 说明 |
|------|------|
| **默认** | 若仓库 `models/` 下存在可用模型目录（含 `model.onnx` 或 `model.int8.onnx` + `lexicon.txt` + `tokens.txt`），则**全部拷入**安装包的 `models/`（通常含 `vits-melo-tts-zh_en`，有 8k 也会带上） |
| **跳过模型**（更小的 CI/开发包） | Windows：`.\scripts\build\windows.ps1 -SkipModels` 或 `$env:INCLUDE_MODELS='0'`；Linux/麒麟：`INCLUDE_MODELS=0 ./scripts/build/...` |
| **强制包含** | Windows：`-IncludeModels`；各平台也可设 `INCLUDE_MODELS=1` |

模型体积大约 100–260MB，zip/tar 会明显变大；没有模型时脚本会告警并打出空 `models/`。

仍可用环境变量 **`TTS_MODELS_ROOT`** 指向外部模型目录，覆盖包内 `models/`。

## 一键打包

### Windows x64（可在本仓库直接执行）

```powershell
.\scripts\build\windows.ps1
# 不打包模型（体积更小）：
# .\scripts\build\windows.ps1 -SkipModels
```

产物：

- `dist/fsatts-windows-x64/` — 可运行目录（含 `fsatts.exe`、`run.bat`、以及已拷贝的 `models/`）
- `dist/fsatts-windows-x64.zip` — 安装包（解压即用）

安装启动：

1. 解压 zip
2. 若包内已有 `models/vits-melo-tts-zh_en/`，可直接下一步；否则把模型拷入 `models/`（见 README 下载说明）
3. 双击 `run.bat` 或命令行运行 `fsatts.exe`
4. 浏览器打开 `http://127.0.0.1:19658`

### Linux amd64

在 **amd64 Linux**（建议 Ubuntu 22.04+，注意 glibc 兼容）上：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
chmod +x scripts/build/linux-amd64.sh
./scripts/build/linux-amd64.sh
# 不打包模型：INCLUDE_MODELS=0 ./scripts/build/linux-amd64.sh
```

产物：`dist/fsatts-linux-amd64/` 与 `dist/fsatts-linux-amd64.tar.gz`。解压后 `./run.sh`。

### 麒麟 V10 arm64

**必须在 aarch64 真机或 arm64 容器上构建**（x86 上脚本会 exit 2，不会伪造成功）：

```bash
# 在麒麟 V10 arm64 上
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # 需 aarch64 的 sherpa-onnx wheel，否则从源码装
chmod +x scripts/build/kylin-v10-arm64.sh
./scripts/build/kylin-v10-arm64.sh
# 不打包模型：INCLUDE_MODELS=0 ./scripts/build/kylin-v10-arm64.sh
```

产物：`dist/fsatts-kylin-v10-arm64.tar.gz`。

若 PyPI 无对应 arm64 轮子：按 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 文档在目标机编译安装后再打包。

## 技术选型

| 方案 | 角色 |
|------|------|
| **PyInstaller onedir** | MVP 首选；`--collect-all sherpa_onnx` |
| Nuitka | 二期可选 |
| Docker | 纯 Linux 服务器场景可选；桌面麒麟不依赖 Docker |

默认把**仓库里已有的模型目录**一并打进 onedir/zip/tar，解压即可跑；仍可用 `TTS_MODELS_ROOT` 外置更新。CUDA 默认为可选附加，CPU 包可独立运行。

## 可选 installer

- Windows：可用 Inno Setup / NSIS 把 `fsatts-windows-x64` 目录打成 Setup.exe（本仓库未捆绑 ISS 脚本；zip 已足够分发）。
- Linux：可将 tar.gz 解压到 `/opt/fsatts` 并写 systemd user unit（示例见下）。

```ini
# ~/.config/systemd/user/fsatts.service （示例）
[Unit]
Description=fsatts TTS plugin
[Service]
WorkingDirectory=%h/fsatts-linux-amd64
Environment=TTS_HOST=127.0.0.1
Environment=TTS_PORT=19658
ExecStart=%h/fsatts-linux-amd64/fsatts
Restart=on-failure
[Install]
WantedBy=default.target
```

## 安全提示

默认 `0.0.0.0` + `CORS=*` 方便局域网调试；生产或不可信网络请：

1. `TTS_HOST=127.0.0.1` 或防火墙仅放行可信网段
2. `TTS_CORS_ORIGINS=https://your-app.example.com`
3. 不要把服务裸暴露到公网
