@echo off
setlocal
cd /d %~dp0

where uv >nul 2>nul
if errorlevel 1 (
    echo [setup.cmd] uv が PATH にありません。https://docs.astral.sh/uv/ からインストールしてください。
    exit /b 1
)

echo [setup.cmd] Creating venv (Python 3.11)...
uv venv --python 3.11 .venv || goto :err

echo [setup.cmd] Installing dependencies (this can take a long time on first run)...
uv sync --no-dev || goto :err

echo [setup.cmd] Done. Run with run.cmd.
exit /b 0

:err
echo [setup.cmd] FAILED.
exit /b 1