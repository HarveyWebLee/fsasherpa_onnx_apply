# Download optional fast Melo 8kHz model (does NOT replace vits-melo-tts-zh_en).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dest = Join-Path $Root "models\vits-melo-tts-zh_en-8k"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$Base = if ($env:HF_ENDPOINT) { $env:HF_ENDPOINT.TrimEnd('/') } else { "https://hf-mirror.com" }
$Repo = "Luigi/vits-melo-tts-zh_en-8k"
$files = @("model.onnx", "tokens.txt", "lexicon.txt")

foreach ($f in $files) {
  $out = Join-Path $Dest $f
  if ((Test-Path $out) -and ((Get-Item $out).Length -gt 1000)) {
    Write-Host "skip $f"
    continue
  }
  $url = "$Base/$Repo/resolve/main/$f"
  Write-Host "Downloading $url"
  & curl.exe -L --fail --retry 3 -o $out $url
  if ($LASTEXITCODE -ne 0) { throw "download failed: $f" }
}

$Src = Join-Path $Root "models\vits-melo-tts-zh_en"
foreach ($name in @("dict", "phone.fst", "date.fst", "number.fst")) {
  $s = Join-Path $Src $name
  $d = Join-Path $Dest $name
  if (-not (Test-Path $d) -and (Test-Path $s)) {
    Write-Host "copy $name from 44.1k model"
    if (Test-Path $s -PathType Container) {
      Copy-Item $s $d -Recurse -Force
    } else {
      Copy-Item $s $d -Force
    }
  }
}

Write-Host "Done. Start with:"
Write-Host ("  `$env:TTS_MODEL_DIR = '" + $Dest + "'")
Write-Host "  .\run_web.ps1"
