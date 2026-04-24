@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

set CUDA_VERSION=12.8
set CUDA_BASE=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA
set CUDA_PATH=%CUDA_BASE%\v%CUDA_VERSION%
set CUDA_HOME=%CUDA_PATH%
set PATH=%CUDA_PATH%\bin;%~dp0.venv\Scripts;%PATH%

if not exist .venv\Scripts\python.exe (
    echo [run.cmd] .venv not found. Please run setup.cmd first.
    pause
    exit /b 1
)

REM Default host 0.0.0.0 so other PCs on the same LAN can reach the UI.
REM Set SAM3DBODY_HOST=127.0.0.1 to restrict to this PC only.
if "%SAM3DBODY_HOST%"=="" set SAM3DBODY_HOST=0.0.0.0
if "%SAM3DBODY_PORT%"=="" set SAM3DBODY_PORT=8765

REM If the requested port is in use, scan upward for a free one.
set "FREE_PORT="
for /f "usebackq tokens=*" %%p in (`.venv\Scripts\python.exe tools\find_free_port.py %SAM3DBODY_HOST% %SAM3DBODY_PORT%`) do set "FREE_PORT=%%p"
if "!FREE_PORT!"=="" (
    echo [run.cmd][ERROR] No free port available near %SAM3DBODY_HOST%:%SAM3DBODY_PORT%.
    exit /b 1
)
if not "!FREE_PORT!"=="%SAM3DBODY_PORT%" (
    echo [run.cmd] Port %SAM3DBODY_PORT% is in use -^> using !FREE_PORT!
)
set SAM3DBODY_PORT=!FREE_PORT!

REM Access URL はアプリの lifespan preload 完了後に main.py が stdout へ出す。
.venv\Scripts\python.exe -m uvicorn sam3dbody_app.main:app --host %SAM3DBODY_HOST% --port %SAM3DBODY_PORT% --reload --app-dir src
