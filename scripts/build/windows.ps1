# Build Windows x64 plugin bundle (PyInstaller onedir) + zip
# Usage (repo root): .\scripts\build\windows.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Missing .venv" }

& $venvPy -m pip install -q "pyinstaller>=6.0"
$entry = Join-Path $Root "scripts\build\_entrypoint_fsatts.py"
$assets = Join-Path $Root "scripts\build\package_assets"

Write-Host "Building onedir bundle (CPU). Models are NOT bundled — place models/ beside the exe."
& $venvPy -m PyInstaller `
  --noconfirm `
  --clean `
  --name fsatts `
  --onedir `
  --console `
  --add-data "static;static" `
  --collect-all sherpa_onnx `
  --hidden-import app `
  --hidden-import app.main `
  --hidden-import app.tts_engine `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import soundfile `
  --hidden-import numpy `
  $entry

$dist = Join-Path $Root "dist\fsatts"
if (-not (Test-Path $dist)) { throw "dist\fsatts missing" }

Copy-Item (Join-Path $assets "run.bat") $dist -Force
Copy-Item (Join-Path $assets "config.example.env") $dist -Force
Copy-Item (Join-Path $assets "README-RUN.txt") $dist -Force
New-Item -ItemType Directory -Force -Path (Join-Path $dist "models") | Out-Null
Set-Content -Path (Join-Path $dist "models\.gitkeep") -Value ""

# Stage release folder name
$relName = "fsatts-windows-x64"
$rel = Join-Path $Root "dist\$relName"
if (Test-Path $rel) { Remove-Item $rel -Recurse -Force }
Copy-Item $dist $rel -Recurse
$zip = Join-Path $Root "dist\$relName.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
# Use Python zipfile (Compress-Archive can fail on nested base_library.zip locks)
& $venvPy -c @"
import zipfile, pathlib
rel = pathlib.Path(r'$rel')
zip_path = pathlib.Path(r'$zip')
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for p in rel.rglob('*'):
        if p.is_file():
            zf.write(p, p.relative_to(rel.parent).as_posix())
print('zip', zip_path)
"@

Write-Host "OK: $rel"
Write-Host "OK: $zip"
Write-Host "Next: copy models into $rel\models then run.bat  (port 19658)"
