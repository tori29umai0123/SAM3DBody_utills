#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[run.sh] .venv が未作成です。setup.sh を先に実行してください。"
    exit 1
fi

# Default host 0.0.0.0 so other PCs on the same LAN can reach the UI.
# Set SAM3DBODY_HOST=127.0.0.1 to restrict to this PC only.
export SAM3DBODY_HOST="${SAM3DBODY_HOST:-0.0.0.0}"
export SAM3DBODY_PORT="${SAM3DBODY_PORT:-8765}"

# 指定ポートが使われていたら順に +1 して空きを探す
FREE_PORT="$(.venv/bin/python tools/find_free_port.py "$SAM3DBODY_HOST" "$SAM3DBODY_PORT" || true)"
if [ -z "$FREE_PORT" ]; then
    echo "[run.sh][ERROR] $SAM3DBODY_HOST 付近に空きポートが見つかりません。"
    exit 1
fi
if [ "$FREE_PORT" != "$SAM3DBODY_PORT" ]; then
    echo "[run.sh] Port $SAM3DBODY_PORT is in use -> using $FREE_PORT"
fi
export SAM3DBODY_PORT="$FREE_PORT"

# Access URL はアプリの lifespan preload 完了後に main.py が stdout へ出す。
.venv/bin/python -m uvicorn sam3dbody_app.main:app --host "$SAM3DBODY_HOST" --port "$SAM3DBODY_PORT" --reload --app-dir src
