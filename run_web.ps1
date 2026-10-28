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

Write-Host ("启动 TTS Web: http://127.0.0.1:19658  provider={0} threads={1}" -f $provider, $env:TTS_NUM_THREADS)
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 19658
