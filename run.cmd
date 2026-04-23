@echo off
setlocal
cd /d %~dp0

set CUDA_VERSION=12.8
set CUDA_BASE=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA
set CUDA_PATH=%CUDA_BASE%\v%CUDA_VERSION%
set CUDA_HOME=%CUDA_PATH%
set PATH=%CUDA_PATH%\bin;%~dp0.venv\Scripts;%PATH%

if not exist .venv\Scripts\python.exe (
    echo [run.cmd] .venv Ç™ñ¢çÏê¨Ç≈Ç∑ÅBsetup.cmd ÇêÊÇ…é¿çsÇµÇƒÇ≠ÇæÇ≥Ç¢ÅB
    exit /b 1
)

if "%SAM3DBODY_HOST%"=="" set SAM3DBODY_HOST=127.0.0.1
if "%SAM3DBODY_PORT%"=="" set SAM3DBODY_PORT=8765

.venv\Scripts\python.exe -m uvicorn sam3dbody_app.main:app --host %SAM3DBODY_HOST% --port %SAM3DBODY_PORT% --reload --app-dir src