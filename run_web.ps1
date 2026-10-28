$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Error "未找到 .venv，请先创建虚拟环境并安装依赖"
  exit 1
}

# CUDA: 若 TTS_PROVIDER=cuda（或已安装 nvidia 包且未显式设为 cpu），补齐 DLL PATH
$provider = if ($env:TTS_PROVIDER) { $env:TTS_PROVIDER.Trim().ToLower() } else { "cpu" }
$nvidiaSite = Join-Path $Root ".venv\Lib\site-packages\nvidia"
if ($provider -eq "cuda" -or (($provider -ne "cpu") -and (Test-Path $nvidiaSite))) {
  & (Join-Path $Root "scripts\ensure_nvidia_path.ps1")
}
if (-not $env:TTS_NUM_THREADS) { $env:TTS_NUM_THREADS = "2" }
if (-not $env:TTS_HOST) { $env:TTS_HOST = "0.0.0.0" }
if (-not $env:TTS_PORT) { $env:TTS_PORT = "19658" }
if (-not $env:TTS_CORS_ORIGINS) { $env:TTS_CORS_ORIGINS = "*" }

Write-Host ("启动 TTS 插件服务: http://{0}:{1}  (本机可开 http://127.0.0.1:{1})  provider={2} threads={3} CORS={4}" -f $env:TTS_HOST, $env:TTS_PORT, $provider, $env:TTS_NUM_THREADS, $env:TTS_CORS_ORIGINS)
& $py -m uvicorn app.main:app --host $env:TTS_HOST --port ([int]$env:TTS_PORT)
