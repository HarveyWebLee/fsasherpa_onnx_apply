@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ??? .venv???: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
if "%TTS_NUM_THREADS%"=="" set TTS_NUM_THREADS=2
if /I "%TTS_PROVIDER%"=="cuda" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure_nvidia_path.ps1"
)
echo ?? TTS Web: http://127.0.0.1:19658  provider=%TTS_PROVIDER% threads=%TTS_NUM_THREADS%
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 19658
