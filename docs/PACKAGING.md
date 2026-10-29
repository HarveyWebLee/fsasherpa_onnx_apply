# 打包说明

## 依赖与前端

```powershell
uv sync
cd web; pnpm install --frozen-lockfile; pnpm run build; cd ..
```

安装包需包含 `web/dist`（或运行时再构建）。

## 模型策略

- **默认打进包**（`bundle_default=true`）：Melo 44k / Melo 8k（中英混合）
- **可选**：Kokoro multi-lang v1.1 int8（`kokoro-zh-en-v1_1`，103 说话人，需先下载）
- 跳过模型：`INCLUDE_MODELS=0` 或打包脚本 `-SkipModels`
- 打包前可运行：`uv run python scripts/download_models.py --bundle`

## Windows

见 `scripts/build/windows.ps1`。打包前确保：

1. `uv sync`（或已有 `.venv`）
2. `web/dist` 已构建
3. 需要的模型在 `models/`（至少两套 Melo；Kokoro 可选）

```powershell
.\scripts\build\windows.ps1
.\scripts\build\windows.ps1 -SkipModels
```

## Linux / 麒麟

在目标架构机器执行对应脚本：

- `scripts/build/linux-amd64.sh`
- `scripts/build/kylin-v10-arm64.sh`

## 运行时环境变量

见 README「并发」一节。默认端口 **19658**（`TTS_PORT`）。
