# Build Windows x64 local plugin bundle (PyInstaller).
# Usage (from repo root): .\scripts\build\windows.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Missing .venv — pip install -r requirements.txt pyinstaller" }

& $venvPy -m pip install -q pyinstaller
$entry = Join-Path $Root "scripts\build\_entrypoint_fsatts.py"

Write-Host "Building onedir bundle (CPU). May take several minutes..."
& $venvPy -m PyInstaller `
  --noconfirm `
  --clean `
  --name fsatts `
  --onedir `
  --console `
  --add-data "static;static" `
  --collect-all sherpa_onnx `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on `
  $entry

Write-Host "Done. See dist\fsatts\ — place models\ beside it. Default port 19658."
