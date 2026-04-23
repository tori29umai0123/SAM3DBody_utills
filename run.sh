#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[run.sh] .venv が未作成です。setup.sh を先に実行してください。"
    exit 1
fi

HOST="${SAM3DBODY_HOST:-127.0.0.1}"
PORT="${SAM3DBODY_PORT:-8765}"

.venv/bin/python -m uvicorn sam3dbody_app.main:app --host "$HOST" --port "$PORT" --reload --app-dir src
