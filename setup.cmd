@echo off
setlocal
cd /d %~dp0

where uv >nul 2>nul
if errorlevel 1 (
    echo [setup.cmd] uv is not on PATH. Install from https://docs.astral.sh/uv/
    pause
    exit /b 1
)

REM Bootstrap Python 3.11 via uv ^(no project sync^) and hand off to setup.py.
uv run --no-project --python 3.11 setup.py
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" echo [setup.cmd] FAILED with code %RC%.
pause
exit /b %RC%
