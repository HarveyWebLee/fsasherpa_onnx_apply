# Build Windows x64 plugin bundle (PyInstaller onedir) + zip
# Usage (repo root):
#   .\scripts\build\windows.ps1              # include models/ when present (default)
#   .\scripts\build\windows.ps1 -SkipModels  # smaller CI/dev package without models
#   $env:INCLUDE_MODELS='0'; .\scripts\build\windows.ps1
param(
  [switch]$SkipModels,
  [switch]$IncludeModels
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Missing .venv" }

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

& $venvPy -m pip install -q "pyinstaller>=6.0"
$entry = Join-Path $Root "scripts\build\_entrypoint_fsatts.py"
$assets = Join-Path $Root "scripts\build\package_assets"
$srcModels = Join-Path $Root "models"

# Huge multi-speaker packs skipped unless INCLUDE_HUGE_MODELS=1
$HugeModelDirs = @('vits-zh-hf-theresa', 'vits-zh-hf-eula', 'vits-zh-hf-fanchen-C')
function Get-ModelDirs([string]$ModelsRoot) {
  if (-not (Test-Path $ModelsRoot)) { return @() }
  $includeHuge = $env:INCLUDE_HUGE_MODELS -in @('1', 'true', 'True', 'yes', 'YES')
  Get-ChildItem -Path $ModelsRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object {
      if (-not $includeHuge -and ($_.Name -in $HugeModelDirs)) { return $false }
      $onnx = Get-ChildItem $_.FullName -Filter '*.onnx' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch 'rule' -and $_.Length -gt 1000 } |
        Select-Object -First 1
      $hasLex = Test-Path (Join-Path $_.FullName 'lexicon.txt')
      $hasTok = Test-Path (Join-Path $_.FullName 'tokens.txt')
      $null -ne $onnx -and $hasLex -and $hasTok
    }
}
}

$modelDirs = @(Get-ModelDirs $srcModels)

if ($wantModels) {
  if ($modelDirs.Count -eq 0) {
    if ($IncludeModels -or ($envFlag -in @("1", "true", "True", "yes", "YES"))) {
      throw "INCLUDE_MODELS requested but no usable model dirs under $srcModels (need model.onnx/int8 + lexicon.txt + tokens.txt)"
    }
    Write-Host "WARN: models/ has no usable TTS model dirs; packaging empty models/ (use download_model.ps1 first for a full zip)."
    $wantModels = $false
  } else {
    $names = ($modelDirs | ForEach-Object { $_.Name }) -join ", "
    Write-Host "Building onedir bundle (CPU). Will include models: $names"
  }
} else {
  Write-Host "Building onedir bundle (CPU). Models SKIPPED (-SkipModels / INCLUDE_MODELS=0)."
}

& $venvPy -m PyInstaller `
  --noconfirm `
  --clean `
  --name fsatts `
  --onedir `
  --console `
  --add-data "static;static" `
  --add-data "web/dist;web/dist" `
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

# Stage release folder name
$relName = "fsatts-windows-x64"
$rel = Join-Path $Root "dist\$relName"
if (Test-Path $rel) {
  # Prior run.bat may lock DLLs under the release folder
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
# Use Python zipfile (Compress-Archive can fail on nested base_library.zip locks)
& $venvPy -c @"
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
  Write-Host "Models bundled under models/. Unzip and run.bat (port 19658). Override with TTS_MODELS_ROOT if needed."
} else {
  Write-Host "Next: copy models into $rel\models then run.bat  (port 19658)"
}