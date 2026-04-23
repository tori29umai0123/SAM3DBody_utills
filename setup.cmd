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

REM --- 同梱 Blender (Windows x64) ---------------------------------------------
REM FBX エクスポート用に公式ポータブル版 Blender 4.1 を blender41-portable/ に
REM 配置する。既に配置済みならスキップ。
set "BLENDER_VER=4.1.1"
set "BLENDER_ZIP_DIR=blender-%BLENDER_VER%-windows-x64"
set "BLENDER_URL=https://download.blender.org/release/Blender4.1/%BLENDER_ZIP_DIR%.zip"
set "BLENDER_TARGET=blender41-portable"

if exist "%BLENDER_TARGET%\blender.exe" (
    echo [setup.cmd] Bundled Blender OK: %BLENDER_TARGET%\blender.exe
    goto :done
)

set "BLENDER_ZIP=%TEMP%\%BLENDER_ZIP_DIR%.zip"
echo [setup.cmd] Downloading official Blender %BLENDER_VER% for Windows x64...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%BLENDER_URL%' -OutFile '%BLENDER_ZIP%' -UseBasicParsing" || goto :err

echo [setup.cmd] Extracting...
powershell -NoProfile -Command "Expand-Archive -Path '%BLENDER_ZIP%' -DestinationPath '%TEMP%\sam3dbody-blender' -Force" || goto :err

if not exist "%TEMP%\sam3dbody-blender\%BLENDER_ZIP_DIR%\blender.exe" (
    echo [setup.cmd][ERROR] 展開した Blender が見つかりません。
    goto :err
)

if exist "%BLENDER_TARGET%" rmdir /s /q "%BLENDER_TARGET%"
move "%TEMP%\sam3dbody-blender\%BLENDER_ZIP_DIR%" "%BLENDER_TARGET%" >nul || goto :err
del /q "%BLENDER_ZIP%" 2>nul
rmdir /s /q "%TEMP%\sam3dbody-blender" 2>nul
echo [setup.cmd] Blender installed: %BLENDER_TARGET%\blender.exe

:done
echo [setup.cmd] Done. Run with run.cmd.
exit /b 0

:err
echo [setup.cmd] FAILED.
exit /b 1
