$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Error "未找到 .venv，请先创建虚拟环境并安装依赖"
  exit 1
}
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 19658
