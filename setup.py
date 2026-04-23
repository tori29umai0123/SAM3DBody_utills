"""Unconditional reset + full setup for SAM3DBody utils.

Invocation (via setup.cmd / setup.sh):
    uv run --no-project --python 3.11 setup.py

Every run performs the following in order:
    1. Clear ``[blender] exe_path`` in ``config.ini``
    2. Delete ``blender41-portable/`` and ``ARM_blender41-portable/``
    3. Recreate ``.venv`` via ``uv venv --clear --python 3.11 .venv``
    4. Install dependencies via ``uv sync --no-dev``
    5. Prompt for an existing Blender path (Windows / Linux x86_64),
       skipping the prompt on Linux ARM64 (auto-download only).
    6. If the user enters a valid path -> persist to ``config.ini``.
       If the user skips -> auto-download the portable build and persist.

This script only uses the Python standard library so it can run with the
ephemeral interpreter uv provides via ``--no-project``.
"""
from __future__ import annotations

import configparser
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_INI = ROOT / "config.ini"
BLENDER_VER = "4.1.1"
ARM_RELEASE_TAG = "blender-arm64-v1.0"
ARM_RELEASE_BASE = (
    f"https://github.com/tori29umai0123/SAM3DBody_utills/releases/download/{ARM_RELEASE_TAG}"
)

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"
MACHINE = platform.machine().lower()
IS_ARM64 = MACHINE in ("aarch64", "arm64")

SKIP_KEYWORDS = {"n", "no", "skip", "s", "auto"}
MAX_PROMPT_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def run(cmd: list[str]) -> None:
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def _onerror_chmod(func, path, exc_info):
    """shutil.rmtree onerror hook: clear the read-only bit and retry."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def rmtree_if_exists(p: Path) -> None:
    """Remove a directory tree with Windows-friendly fallbacks.

    If a file inside is locked (VS Code / running Python / antivirus etc.),
    rename the directory out of the way so uv can create a fresh one.
    Never silently no-ops — any failure raises after logging actionable hints.
    """
    if not p.exists():
        return
    log(f"removing {p.name}/ ...")

    # Attempt 1: plain rmtree
    try:
        shutil.rmtree(p)
        return
    except Exception:
        pass

    # Attempt 2: rmtree with chmod-on-error retry
    try:
        shutil.rmtree(p, onerror=_onerror_chmod)
        if not p.exists():
            return
    except Exception:
        pass

    # Attempt 3: rename out of the way (lets the fresh venv be created anyway)
    stale = p.parent / f"{p.name}.stale.{int(time.time())}"
    try:
        p.rename(stale)
        log(f"WARN: could not delete {p.name} (files are locked by another process).")
        log(f"      renamed to {stale.name}; delete it manually after closing VS Code /")
        log(f"      any running Python / Blender that was using .venv.")
        return
    except Exception as e:
        log(f"ERROR: could not remove or rename {p.name}: {e}")
        log("      A process is holding files in that folder.")
        log("      Close VS Code, any running Python, and try again.")
        raise


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# config.ini I/O
# ---------------------------------------------------------------------------

def clear_blender_in_config() -> None:
    if not CONFIG_INI.is_file():
        return
    cp = configparser.ConfigParser()
    cp.read(CONFIG_INI, encoding="utf-8")
    if "blender" not in cp:
        cp["blender"] = {}
    cp["blender"]["exe_path"] = ""
    with CONFIG_INI.open("w", encoding="utf-8") as f:
        cp.write(f)
    log("config.ini [blender] exe_path cleared")


def write_blender_path(blender_exe: Path) -> None:
    abs_path = str(blender_exe.resolve())
    cp = configparser.ConfigParser()
    if CONFIG_INI.is_file():
        cp.read(CONFIG_INI, encoding="utf-8")
    if "blender" not in cp:
        cp["blender"] = {}
    cp["blender"]["exe_path"] = abs_path
    with CONFIG_INI.open("w", encoding="utf-8") as f:
        cp.write(f)
    log(f"config.ini blender.exe_path = {abs_path}")


# ---------------------------------------------------------------------------
# uv-driven venv + deps
# ---------------------------------------------------------------------------

def setup_venv(wipe: bool) -> None:
    venv_dir = ROOT / ".venv"
    venv_python = venv_dir / ("Scripts" if IS_WINDOWS else "bin") / (
        "python.exe" if IS_WINDOWS else "python"
    )
    if wipe or not venv_python.exists():
        log("creating fresh venv (Python 3.11) ...")
        run(["uv", "venv", "--clear", "--python", "3.11", ".venv"])
    else:
        log("reusing existing .venv")
    log("syncing dependencies (this can take a long time on first run) ...")
    run(["uv", "sync", "--no-dev"])


def prompt_yes_no(question: str, *, default_no: bool = True) -> bool:
    suffix = "[y/N]" if default_no else "[Y/n]"
    for _ in range(3):
        try:
            raw = input(f"{question} {suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return not default_no
        if not raw:
            return not default_no
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  please answer y or n.")
    return not default_no


# ---------------------------------------------------------------------------
# interactive prompt
# ---------------------------------------------------------------------------

def prompt_blender_path() -> Path | None:
    """Return Path if the user entered a valid one, None for auto-download."""
    print()
    print("[setup] Blender 4.1+ is required for FBX export.")
    print("        Enter the full path to your existing blender executable,")
    print("        or press ENTER to auto-download the official portable build.")
    if IS_WINDOWS:
        print("          example: C:\\Program Files\\Blender Foundation\\Blender 4.1\\blender.exe")
    else:
        print("          example: /opt/blender-4.1/blender")
    print("        Surrounding quotes are OK.")
    print("        Type 'n' / 'skip' / 'auto' to auto-download instead.")
    print()

    for attempt in range(MAX_PROMPT_ATTEMPTS):
        try:
            raw = input("Blender path (ENTER to auto-download): ")
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        raw = _strip_quotes(raw)
        low = raw.strip().lower()
        if not raw or low in SKIP_KEYWORDS:
            return None

        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        if p.is_file():
            return p

        remaining = MAX_PROMPT_ATTEMPTS - attempt - 1
        print(f"[setup] ERROR: not a file: {p}")
        if remaining > 0:
            print(f"        {remaining} attempt(s) left, or press ENTER to auto-download.")
            print()

    log("ERROR: giving up after 3 invalid attempts.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Blender auto-download (platform specific)
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path) -> None:
    log(f"downloading {url}")
    # Blender's CDN rejects the default "Python-urllib/*" UA with 403.
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, dest.open("wb") as f:
        shutil.copyfileobj(resp, f)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def auto_dl_windows() -> Path:
    zip_name = f"blender-{BLENDER_VER}-windows-x64.zip"
    extracted = ROOT / f"blender-{BLENDER_VER}-windows-x64"
    target = ROOT / "blender41-portable"
    archive = ROOT / zip_name

    if archive.is_file():
        log(f"reusing cached archive: {archive.name}")
    else:
        _download(
            f"https://download.blender.org/release/Blender4.1/{zip_name}",
            archive,
        )

    log("extracting ...")
    if extracted.exists():
        shutil.rmtree(extracted)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(ROOT)
    if not (extracted / "blender.exe").is_file():
        raise RuntimeError(f"extraction failed: {extracted / 'blender.exe'} missing")

    if target.exists():
        shutil.rmtree(target)
    extracted.rename(target)
    archive.unlink(missing_ok=True)
    log(f"Blender installed: {target / 'blender.exe'}")
    return target / "blender.exe"


def auto_dl_linux_x64() -> Path:
    archive_name = f"blender-{BLENDER_VER}-linux-x64.tar.xz"
    extracted = ROOT / f"blender-{BLENDER_VER}-linux-x64"
    target = ROOT / "blender41-portable"
    archive = ROOT / archive_name

    if archive.is_file():
        log(f"reusing cached archive: {archive.name}")
    else:
        _download(
            f"https://download.blender.org/release/Blender4.1/{archive_name}",
            archive,
        )

    log("extracting ...")
    if extracted.exists():
        shutil.rmtree(extracted)
    with tarfile.open(archive) as tf:
        tf.extractall(ROOT)
    if not (extracted / "blender").is_file():
        raise RuntimeError(f"extraction failed: {extracted / 'blender'} missing")

    if target.exists():
        shutil.rmtree(target)
    extracted.rename(target)
    archive.unlink(missing_ok=True)
    log(f"Blender installed: {target / 'blender'}")
    return target / "blender"


def auto_dl_linux_arm64() -> Path:
    archive_name = "ARM_blender41-portable.tar.xz"
    sha_name = archive_name + ".sha256"
    target = ROOT / "ARM_blender41-portable"
    archive = ROOT / archive_name
    sha_file = ROOT / sha_name

    if archive.is_file() and sha_file.is_file():
        log(f"reusing cached archive: {archive.name}")
    else:
        _download(f"{ARM_RELEASE_BASE}/{archive_name}", archive)
        _download(f"{ARM_RELEASE_BASE}/{sha_name}", sha_file)

    expected = sha_file.read_text().split()[0]
    got = _sha256(archive)
    if got != expected:
        raise RuntimeError(f"sha256 mismatch: expected={expected} got={got}")
    log("sha256 verified.")

    log("extracting ...")
    if target.exists():
        shutil.rmtree(target)
    with tarfile.open(archive) as tf:
        tf.extractall(ROOT)
    bin_blender = target / "bin" / "blender"
    if not bin_blender.is_file():
        raise RuntimeError(f"extraction failed: {bin_blender} missing")

    archive.unlink(missing_ok=True)
    sha_file.unlink(missing_ok=True)
    log(f"Blender installed: {bin_blender}")

    # Some ARM builds lack numpy in Blender's bundled Python; inject if needed.
    _ensure_blender_numpy(
        bin_blender,
        target / "bin" / "4.1" / "python" / "lib" / "python3.11" / "site-packages",
    )
    return bin_blender


def _ensure_blender_numpy(blender_exe: Path, site_dir: Path) -> None:
    if not blender_exe.is_file():
        return
    expr = f"import sys; sys.path.insert(0, {str(site_dir)!r}); import numpy"
    probe = subprocess.run(
        [str(blender_exe), "--background", "--python-expr", expr],
        capture_output=True,
    )
    if probe.returncode == 0:
        log(f"Blender numpy OK ({site_dir})")
        return
    log(f"installing numpy into {site_dir}")
    site_dir.mkdir(parents=True, exist_ok=True)
    venv_python = ROOT / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / (
        "python.exe" if IS_WINDOWS else "python"
    )
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--target", str(site_dir),
         "--no-deps", "--upgrade", "numpy<2"],
        check=True,
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _cleanup_stale_dirs() -> None:
    """Best-effort cleanup of previously-renamed *.stale.* leftovers."""
    for pat in (".venv.stale.*", "blender41-portable.stale.*", "ARM_blender41-portable.stale.*"):
        for stale in ROOT.glob(pat):
            try:
                shutil.rmtree(stale, onerror=_onerror_chmod)
            except Exception:
                pass


def main() -> int:
    os.chdir(ROOT)

    log("--- Setup ---")
    _cleanup_stale_dirs()

    # First: ask whether to wipe .venv. (Keeping it skips the ~GB reinstall.)
    venv_exists = (ROOT / ".venv").exists()
    if venv_exists:
        wipe_venv = prompt_yes_no(
            "Delete .venv and reinstall all dependencies from scratch?",
            default_no=True,
        )
    else:
        wipe_venv = True  # nothing to keep

    # Always reset Blender configuration (the interactive prompt comes later).
    clear_blender_in_config()
    rmtree_if_exists(ROOT / "blender41-portable")
    rmtree_if_exists(ROOT / "ARM_blender41-portable")
    if wipe_venv:
        rmtree_if_exists(ROOT / ".venv")

    setup_venv(wipe=wipe_venv)

    # On Linux ARM64 we don't prompt: there's no widely-used standalone binary.
    if IS_LINUX and IS_ARM64:
        chosen: Path | None = None
    elif IS_WINDOWS or IS_LINUX:
        chosen = prompt_blender_path()
    elif IS_MAC:
        log("macOS detected. Blender auto-download is not supported; please install")
        log("Blender manually and set config.ini [blender] exe_path by hand.")
        log("Done. Run with ./run.sh once you configure Blender.")
        return 0
    else:
        log(f"WARN: unsupported platform {sys.platform} / {MACHINE}; configure Blender manually.")
        return 0

    if chosen is not None:
        write_blender_path(chosen)
    else:
        if IS_WINDOWS:
            exe = auto_dl_windows()
        elif IS_LINUX and IS_ARM64:
            exe = auto_dl_linux_arm64()
        elif IS_LINUX:
            exe = auto_dl_linux_x64()
        else:
            log("no auto-download for this platform")
            return 0
        write_blender_path(exe)

    log("Done. Run with run.cmd (Windows) or run.sh (Linux/macOS).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"[setup] FAILED: command exited with {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\n[setup] Aborted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"[setup] FAILED: {e}", file=sys.stderr)
        sys.exit(1)
