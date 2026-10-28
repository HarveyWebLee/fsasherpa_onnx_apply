# Prepend pip nvidia-* CUDA/cuDNN bin dirs to PATH (needed for sherpa-onnx CUDA EP on Windows).
# Dot-source or call before starting uvicorn when TTS_PROVIDER=cuda.
$ErrorActionPreference = "SilentlyContinue"
$Root = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { Get-Location }
$site = Join-Path $Root ".venv\Lib\site-packages\nvidia"
if (-not (Test-Path $site)) {
  Write-Warning "未找到 $site 。CUDA 运行时请: pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-cuda-nvrtc-cu12 nvidia-curand-cu12 nvidia-cusolver-cu12 nvidia-cusparse-cu12 nvidia-nvjitlink-cu12"
  return
}
$bins = Get-ChildItem $site -Directory | ForEach-Object {
  $b = Join-Path $_.FullName "bin"
  if (Test-Path $b) { $b }
}
if (-not $bins) { return }
$env:PATH = ($bins -join ";") + ";" + $env:PATH
Write-Host ("[ensure_nvidia_path] 已加入 {0} 个 nvidia/*/bin 到 PATH" -f @($bins).Count)
