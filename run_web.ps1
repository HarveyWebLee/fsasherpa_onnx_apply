# fsatts - start with uv
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "uv not found. Install: https://docs.astral.sh/uv/"
}
if (-not (Test-Path "$Root\uv.lock")) {
  Write-Host "uv sync (first run)..."
  uv sync
}
if (-not $env:TTS_HOST) { $env:TTS_HOST = "0.0.0.0" }
if (-not $env:TTS_PORT) { $env:TTS_PORT = "19658" }
if (-not $env:TTS_MAX_INFLIGHT) { $env:TTS_MAX_INFLIGHT = "64" }
if (-not $env:TTS_PRELOAD) { $env:TTS_PRELOAD = "1" }
Write-Host "Starting fsatts on http://127.0.0.1:$($env:TTS_PORT) (max_inflight=$($env:TTS_MAX_INFLIGHT)) ..."
uv run python -m uvicorn app.main:app --host $env:TTS_HOST --port $env:TTS_PORT
