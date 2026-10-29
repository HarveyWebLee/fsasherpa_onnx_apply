# 打包说明

## 依赖与前端

`powershell
uv sync
cd web; npm ci; npm run build; cd ..
`

安装包需包含 web/dist（或运行时再构建）。

## 模型策略

- **默认打进包**（undle_default=true）：Melo 44k/8k、zh-ll、aishell3  
- **默认不打包**（体积大 / 按需）：fanchen-c、theresa、eula  

跳过模型：INCLUDE_MODELS=0 或打包脚本 -SkipModels。  
只打默认：运行 uv run python scripts/download_models.py --bundle 后打包。

Theresa / Eula 压缩包各约 115MB，解压后含 *.onnx ~116MB 与可选 
ule.far ~172MB；磁盘紧张时只保留 onnx+lexicon+tokens+fst。

## Windows

见 scripts/build/（沿用现有 satts.spec）。打包前确保：

1. uv sync（或已有 .venv）
2. web/dist 已构建
3. 需要的模型在 models/

## Linux / 麒麟

在目标架构机器执行对应 scripts/build/linux-amd64.sh / kylin-v10-arm64.sh。

## 运行时环境变量

见 README「并发」一节。


## uv + huge models

Packaging scripts use uv sync --extra dev and uv run python -m PyInstaller (no plain pip/venv required).

Huge multi-speaker directories skipped unless INCLUDE_HUGE_MODELS=1:
- vits-zh-hf-theresa
- vits-zh-hf-eula
- vits-zh-hf-fanchen-C

Frontend assets come from web/dist (built automatically if missing).
