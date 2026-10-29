# Build Windows x64 plugin bundle (PyInstaller onedir) + zip
# Usage (repo root):
#   .\scripts\build\windows.ps1              # include models/ when present (default)
#   .\scripts\build\windows.ps1 -SkipModels  # smaller CI/dev package without models
#   $env:INCLUDE_MODELS='0'; .\scripts\build\windows.ps1
# Requires: uv (https://docs.astral.sh/uv/)
param(
  [switch]$SkipModels,
  [switch]$IncludeModels
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv not found. Install: https://docs.astral.sh/uv/"
}
Write-Host "uv sync --extra dev ..."
& uv sync --extra dev

# Default: bundle models when repo models/ has content.
# -SkipModels or INCLUDE_MODELS=0 => empty models/ only
# -IncludeModels or INCLUDE_MODELS=1 => force include (fail if missing usable models)
$envFlag = $env:INCLUDE_MODELS
$wantModels = $true
if ($SkipModels) { $wantModels = $false }
elseif ($IncludeModels) { $wantModels = $true }
elseif ($null -ne $envFlag -and $envFlag -ne "") {
  $wantModels = ($envFlag -notin @("0", "false", "False", "no", "NO"))
}

$entry = Join-Path $Root "scripts\build\_entrypoint_fsatts.py"
$assets = Join-Path $Root "scripts\build\package_assets"
$srcModels = Join-Path $Root "models"

function Get-ModelDirs([string]$ModelsRoot) {
  if (-not (Test-Path $ModelsRoot)) { return @() }
  Get-ChildItem -Path $ModelsRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object {
      $onnx = Get-ChildItem $_.FullName -Filter '*.onnx' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch 'rule' -and $_.Length -gt 1000 } |
        Select-Object -First 1
      $hasLex = Test-Path (Join-Path $_.FullName 'lexicon.txt')
      $hasTok = Test-Path (Join-Path $_.FullName 'tokens.txt')
      $null -ne $onnx -and $hasLex -and $hasTok
    }
}

$modelDirs = @(Get-ModelDirs $srcModels)

if ($wantModels) {
  if ($modelDirs.Count -eq 0) {
    if ($IncludeModels -or ($envFlag -in @("1", "true", "True", "yes", "YES"))) {
      throw "INCLUDE_MODELS requested but no usable model dirs under $srcModels"
    }
    Write-Host "WARN: models/ has no usable TTS model dirs; packaging empty models/."
    $wantModels = $false
  } else {
    $names = ($modelDirs | ForEach-Object { $_.Name }) -join ", "
    Write-Host "Building onedir bundle (CPU). Will include models: $names"
  }
} else {
  Write-Host "Building onedir bundle (CPU). Models SKIPPED (-SkipModels / INCLUDE_MODELS=0)."
}

if (-not (Test-Path "web\dist\index.html")) {
  Write-Host "Building frontend (web/dist missing)..."
  Push-Location web
  pnpm install --frozen-lockfile
  pnpm run build
  Pop-Location
}

& uv run python -m PyInstaller `
  --noconfirm `
  --clean `
  --name fsatts `
  --onedir `
  --console `
  --add-data "web/dist;web/dist" `
  --collect-all sherpa_onnx `
  --hidden-import app `
  --hidden-import app.main `
  --hidden-import app.tts_engine `
  --hidden-import app.models_registry `
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

$dstModels = Join-Path $dist "models"
if (Test-Path $dstModels) { Remove-Item $dstModels -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dstModels | Out-Null
Set-Content -Path (Join-Path $dstModels ".gitkeep") -Value ""

if ($wantModels) {
  foreach ($d in $modelDirs) {
    Write-Host "Copying model $($d.Name) ..."
    Copy-Item $d.FullName (Join-Path $dstModels $d.Name) -Recurse -Force
  }
}

$relName = "fsatts-windows-x64"
$rel = Join-Path $Root "dist\$relName"
if (Test-Path $rel) {
  Get-Process -Name fsatts -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 500
  try {
    Remove-Item $rel -Recurse -Force -ErrorAction Stop
  } catch {
    cmd /c "rmdir /s /q `"$rel`"" | Out-Null
    if (Test-Path $rel) { throw "Cannot remove locked release folder $rel : $_" }
  }
}
Copy-Item $dist $rel -Recurse
$zip = Join-Path $Root "dist\$relName.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
& uv run python -c @"
import zipfile, pathlib
rel = pathlib.Path(r'$rel')
zip_path = pathlib.Path(r'$zip')
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for p in rel.rglob('*'):
        if p.is_file():
            zf.write(p, p.relative_to(rel.parent).as_posix())
print('zip', zip_path, 'bytes', zip_path.stat().st_size)
"@

Write-Host "OK: $rel"
Write-Host "OK: $zip"
if ($wantModels) {
  Write-Host "Models bundled under models/. Unzip and run.bat (port 19658)."
} else {
  Write-Host "Next: copy models into $rel\models then run.bat  (port 19658)"
}
