# Download vits-melo-tts-zh_en for sherpa-onnx TTS demo.
# Prefer GitHub release archive; fall back to Hugging Face / hf-mirror file list.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ModelName = "vits-melo-tts-zh_en"
$ModelDir = Join-Path $Root "models\$ModelName"
$Archive = Join-Path $Root "models\$ModelName.tar.bz2"

New-Item -ItemType Directory -Force -Path (Join-Path $Root "models") | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

function Test-ModelReady {
  $need = @("model.onnx", "lexicon.txt", "tokens.txt")
  foreach ($n in $need) {
    $p = Join-Path $ModelDir $n
    if (-not (Test-Path $p) -or ((Get-Item $p).Length -lt 100)) { return $false }
  }
  return $true
}

if (Test-ModelReady) {
  Write-Host "Model already ready at $ModelDir"
  Get-ChildItem $ModelDir | Format-Table Name, Length
  exit 0
}

$ghUrls = @(
  "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2",
  "https://ghfast.top/https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2"
)

$gotArchive = $false
foreach ($url in $ghUrls) {
  Write-Host "Trying archive: $url"
  try {
    curl.exe -L --connect-timeout 30 --max-time 900 --retry 3 -o $Archive $url
    if ((Test-Path $Archive) -and ((Get-Item $Archive).Length -gt 1000000)) {
      $gotArchive = $true
      break
    }
  } catch {
    Write-Host "  failed: $_"
  }
}

if ($gotArchive) {
  Write-Host "Extracting $Archive ..."
  Push-Location (Join-Path $Root "models")
  try {
    tar -xvf (Split-Path $Archive -Leaf)
  } finally {
    Pop-Location
  }
  if (Test-ModelReady) {
    Write-Host "OK: model ready at $ModelDir"
    exit 0
  }
}

Write-Host "Archive path failed or incomplete; downloading files from Hugging Face mirror..."
$bases = @(
  "https://hf-mirror.com/csukuangfj/vits-melo-tts-zh_en/resolve/main",
  "https://huggingface.co/csukuangfj/vits-melo-tts-zh_en/resolve/main"
)

# Prefer full model.onnx; fall back to int8 then rename/copy.
$files = @(
  "model.onnx",
  "lexicon.txt",
  "tokens.txt",
  "phone.fst",
  "date.fst",
  "number.fst",
  "new_heteronym.fst",
  "LICENSE",
  "README.md"
)

function Get-One($rel) {
  $out = Join-Path $ModelDir $rel
  $parent = Split-Path $out -Parent
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  if ((Test-Path $out) -and ((Get-Item $out).Length -gt 100)) {
    Write-Host "SKIP $rel ($((Get-Item $out).Length) bytes)"
    return $true
  }
  foreach ($b in $bases) {
    $url = "$b/$rel"
    Write-Host "GET $url"
    curl.exe -L --connect-timeout 60 --max-time 1200 --retry 5 --retry-delay 3 --retry-all-errors -o $out $url
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 100)) {
      Write-Host "  saved $((Get-Item $out).Length) bytes"
      return $true
    }
  }
  return $false
}

foreach ($f in $files) {
  $ok = Get-One $f
  if (-not $ok) {
    if ($f -eq "model.onnx") {
      Write-Host "model.onnx failed; trying model.int8.onnx ..."
      if (Get-One "model.int8.onnx") {
        Copy-Item (Join-Path $ModelDir "model.int8.onnx") (Join-Path $ModelDir "model.onnx") -Force
        Write-Host "Using int8 weights as model.onnx"
      } else {
        Write-Error "Failed to download model weights"
      }
    } else {
      Write-Warning "Failed: $f"
    }
  }
}

# dict (jieba) files
$dictFiles = @(
  "jieba.dict.utf8",
  "hmm_model.utf8",
  "user.dict.utf8",
  "idf.utf8",
  "stop_words.utf8"
)
foreach ($df in $dictFiles) {
  Get-One ("dict/" + $df) | Out-Null
}

if (Test-ModelReady) {
  Write-Host "OK: model ready at $ModelDir"
  Get-ChildItem -Recurse $ModelDir | Select-Object FullName, Length | Format-Table -AutoSize
  exit 0
}

Write-Host "ERROR: model still incomplete."
Write-Host "Please manually download from:"
Write-Host "  https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2"
Write-Host "or Hugging Face: https://huggingface.co/csukuangfj/vits-melo-tts-zh_en"
exit 1
