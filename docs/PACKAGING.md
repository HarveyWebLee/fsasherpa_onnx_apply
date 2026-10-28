# 跨平台本地插件服务打包方案（草案）

目标：把本仓库打成可在 **Windows x64**、**Linux amd64**、**麒麟 V10 arm64** 上运行的本地 TTS 插件服务，供浏览器/其他客户端通过 HTTP（及 WebSocket）调用。

## 产品形态

- 本地常驻服务：`127.0.0.1:<port>`（当前开发默认 **19658**）
- 对外 API：`POST /api/tts`、`WS /ws/tts`、`GET /api/status`、`POST /api/models`、`POST /api/provider`
- 模型文件：与可执行文件分离（推荐），首次启动下载或随安装包附带 `models/`
- 一键脚本：`scripts/build/<platform>.sh|.ps1` 产出安装包/压缩包

## 技术选型（与 sherpa-onnx 原生依赖）

| 方案 | 优点 | 风险 / 成本 | 建议 |
|------|------|-------------|------|
| **PyInstaller** | 成熟、Windows/Linux 易出单目录包 | arm64/麒麟需在目标机或对应 wheel 环境打包；需收集 `sherpa_onnx`、ORT、CUDA 可选 DLL | **首选 MVP** |
| **Nuitka** | 可编译成更接近原生二进制 | 编译慢；C 扩展/动态库收集仍复杂 | 二期性能优化 |
| **Docker** | Linux amd64 交付简单 | 麒麟桌面/无 Docker 场景不适用；GPU 透传另议 | 仅 Linux 服务器可选 |
| **conda-pack / venv zip** | 实现快 | 体积大、不像安装包 | 内测过渡 |

**sherpa-onnx 要点：**

- Python 轮子内含原生 `.so` / `.pyd` + 可选 CUDA EP；打包必须 `--collect-all sherpa_onnx`。
- **CUDA 可选**：默认 CPU 包；CUDA 作 Windows 可选附加组件。
- **模型不进二进制**：安装包旁挂 `models/`，或首次运行下载。

## 平台策略

### Windows x64（本机可先做）

- 工具：PyInstaller onedir
- 脚本：`scripts/build/windows.ps1`
- 产物：`dist/fsatts/`；入口 `fsatts.exe`

### Linux amd64

- 脚本：`scripts/build/linux-amd64.sh`
- 在目标 glibc 世代上构建

### 麒麟 V10 arm64

- **优先在目标机本地构建**（`scripts/build/kylin-v10-arm64.sh`）
- 需要 aarch64 的 `sherpa-onnx` wheel，或从源码编译
- 交叉编译不作默认路径

## 目录约定（产物）

```text
dist/fsatts-<os>-<arch>/
  fsatts(.exe)
  run.sh / run.bat
  models/               # 可选预置
  config.example.env    # TTS_PORT=19658
```

## 当前骨架

- `docs/PACKAGING.md`（本文）
- `scripts/build/windows.ps1`
- `scripts/build/linux-amd64.sh`
- `scripts/build/kylin-v10-arm64.sh`
- `scripts/build/fsatts.spec.example`
- `scripts/build/_entrypoint_fsatts.py`

本阶段不执行超长全平台编译；Windows 小规模验证后再扩。

## 开放问题

1. 安装包是否捆绑 44.1k + 8k 模型？
2. 是否注册 Windows 服务 / systemd？
3. 是否只绑 127.0.0.1？
