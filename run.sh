#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[run.sh] .venv が未作成です。setup.sh を先に実行してください。"
    exit 1
fi

# Default host 0.0.0.0 so other PCs on the same LAN can reach the UI.
# Set SAM3DBODY_HOST=127.0.0.1 to restrict to this PC only.
HOST="${SAM3DBODY_HOST:-0.0.0.0}"
PORT="${SAM3DBODY_PORT:-8765}"

# 指定ポートが使われていたら順に +1 して空きを探す
FREE_PORT="$(.venv/bin/python tools/find_free_port.py "$HOST" "$PORT" || true)"
if [ -z "$FREE_PORT" ]; then
    echo "[run.sh][ERROR] $HOST 付近に空きポートが見つかりません。"
    exit 1
fi
if [ "$FREE_PORT" != "$PORT" ]; then
    echo "[run.sh] Port $PORT is in use -> using $FREE_PORT"
fi
PORT="$FREE_PORT"

.venv/bin/python tools/show_urls.py "$HOST" "$PORT"

.venv/bin/python -m uvicorn sam3dbody_app.main:app --host "$HOST" --port "$PORT" --reload --app-dir src
