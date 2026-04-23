#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "[setup.sh] uv is not on PATH. Install from https://docs.astral.sh/uv/"
    exit 1
fi

# Bootstrap Python 3.11 via uv (no project sync) and hand off to setup.py.
exec uv run --no-project --python 3.11 setup.py
