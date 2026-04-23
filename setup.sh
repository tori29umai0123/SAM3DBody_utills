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

# --- 同梱 Blender -----------------------------------------------------------
# Linux 上で FBX エクスポートに使う Blender 4.1 をプロジェクト直下に配置する。
#   - x86_64 Linux : 公式ポータブル版を download.blender.org から自動 DL
#   - ARM64  Linux : 公式配布が無いため自前ビルドを GitHub Releases から自動 DL
OS="$(uname -s)"
ARCH="$(uname -m)"
BLENDER_VER="4.1.1"
ARM_RELEASE_TAG="blender-arm64-v1.0"
ARM_RELEASE_BASE="https://github.com/tori29umai0123/SAM3DBody_utills/releases/download/${ARM_RELEASE_TAG}"

_fetch() {
    # $1=url, $2=out
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$2" "$1"
    else
        echo "[setup.sh][ERROR] curl または wget が必要です。"
        return 1
    fi
}

install_official_blender_x64() {
    local target_dir="blender41-portable"
    if [[ -x "$target_dir/blender" ]]; then
        echo "[setup.sh] Bundled Blender OK: $target_dir/blender"
        return 0
    fi

    local url="https://download.blender.org/release/Blender4.1/blender-${BLENDER_VER}-linux-x64.tar.xz"
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN
    local archive="$tmp/blender.tar.xz"

    echo "[setup.sh] Downloading official Blender ${BLENDER_VER} for x86_64 Linux..."
    _fetch "$url" "$archive" || return 1

    echo "[setup.sh] Extracting..."
    tar -xJf "$archive" -C "$tmp"
    local extracted="$tmp/blender-${BLENDER_VER}-linux-x64"
    if [[ ! -d "$extracted" ]]; then
        echo "[setup.sh][ERROR] 展開に失敗しました: $extracted が見つかりません"
        return 1
    fi
    rm -rf "$target_dir"
    mv "$extracted" "$target_dir"
    echo "[setup.sh] Blender installed: $target_dir/blender"
}

install_portable_blender_arm64() {
    local target_dir="ARM_blender41-portable"
    if [[ -x "$target_dir/bin/blender" ]]; then
        echo "[setup.sh] Bundled Blender OK: $target_dir/bin/blender"
        return 0
    fi

    local archive_url="${ARM_RELEASE_BASE}/ARM_blender41-portable.tar.xz"
    local sha_url="${ARM_RELEASE_BASE}/ARM_blender41-portable.tar.xz.sha256"
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN
    local archive="$tmp/blender.tar.xz"
    local sha_file="$tmp/blender.tar.xz.sha256"

    echo "[setup.sh] Downloading bundled Blender (ARM64) from GitHub Releases..."
    _fetch "$archive_url" "$archive" || return 1
    _fetch "$sha_url" "$sha_file" || return 1

    local expected got
    expected="$(awk '{print $1}' "$sha_file")"
    got="$(sha256sum "$archive" | awk '{print $1}')"
    if [[ -z "$expected" || "$got" != "$expected" ]]; then
        echo "[setup.sh][ERROR] sha256 mismatch: expected=$expected got=$got"
        return 1
    fi
    echo "[setup.sh] sha256 verified."

    echo "[setup.sh] Extracting..."
    tar -xJf "$archive" -C .
    if [[ ! -x "$target_dir/bin/blender" ]]; then
        echo "[setup.sh][ERROR] 展開に失敗: $target_dir/bin/blender が見つかりません"
        return 1
    fi
    echo "[setup.sh] Blender installed: $target_dir/bin/blender"
}

ensure_blender_numpy() {
    # Blender 4.1 の FBX exporter は numpy を import する。公式ビルドは同梱しているが、
    # 自前ビルド版は含まれないケースがあるため、site-packages に numpy を注入する。
    local blender_exe="$1"
    local site_dir="$2"
    if [[ -z "$blender_exe" || -z "$site_dir" ]]; then
        return 0
    fi
    if "$blender_exe" --background --python-expr "import sys; sys.path.insert(0, '$site_dir'); import numpy" >/dev/null 2>&1; then
        echo "[setup.sh] Blender numpy OK ($site_dir)"
        return 0
    fi
    echo "[setup.sh] Installing numpy into Blender's site-packages..."
    mkdir -p "$site_dir"
    .venv/bin/python -m pip install --target "$site_dir" --no-deps --upgrade "numpy<2"
}

if [[ "$OS" == "Linux" ]]; then
    case "$ARCH" in
        x86_64|amd64)
            install_official_blender_x64
            ensure_blender_numpy \
                "blender41-portable/blender" \
                "blender41-portable/4.1/python/lib/python3.11/site-packages"
            ;;
        aarch64|arm64)
            install_portable_blender_arm64
            ensure_blender_numpy \
                "ARM_blender41-portable/bin/blender" \
                "ARM_blender41-portable/bin/4.1/python/lib/python3.11/site-packages"
            ;;
        *)
            echo "[setup.sh][WARN] 未対応のアーキテクチャ: $ARCH (Blender は別途用意してください)"
            ;;
    esac
fi

echo "[setup.sh] Done. Run with run.sh."
