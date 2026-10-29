@echo off
cd /d "%~dp0"
where uv >nul 2>nul || (echo Install uv first: https://docs.astral.sh/uv/ & exit /b 1)
if not exist "uv.lock" uv sync
if "%TTS_HOST%"=="" set TTS_HOST=0.0.0.0
if "%TTS_PORT%"=="" set TTS_PORT=19658
uv run python -m uvicorn app.main:app --host %TTS_HOST% --port %TTS_PORT%