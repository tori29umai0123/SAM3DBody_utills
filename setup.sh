#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "[setup.sh] uv が PATH にありません。https://docs.astral.sh/uv/ からインストールしてください。"
    exit 1
fi

echo "[setup.sh] Creating venv (Python 3.11)..."
uv venv --python 3.11 .venv

echo "[setup.sh] Installing dependencies (this can take a long time on first run)..."
uv sync --no-dev

echo "[setup.sh] Done. Run with run.sh."
