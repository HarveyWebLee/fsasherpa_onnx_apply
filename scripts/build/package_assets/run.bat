@echo off
setlocal
cd /d "%~dp0"
if not defined TTS_HOST set TTS_HOST=0.0.0.0
if not defined TTS_PORT set TTS_PORT=19658
if not defined TTS_CORS_ORIGINS set TTS_CORS_ORIGINS=*
if not defined TTS_MODELS_ROOT set TTS_MODELS_ROOT=%~dp0models
echo Starting fsatts plugin on %TTS_HOST%:%TTS_PORT%
fsatts.exe
