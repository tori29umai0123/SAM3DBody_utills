"""Preset pack administration — create / clone / switch packs, rebuild the
active pack's blend-shape data from a Blender FBX.

ComfyUI-SAM3DBody_utills compatible layout:

    presets/
        default/                  (always-present baseline)
            face_blendshapes.npz
            mhr_reference_vertices.json
            <obj>_vertices.json …
            chara_settings_presets/
                autosave.json
                ...
        <custom_pack>/            (user-created packs follow the same shape)
    active_preset.ini             [active]\npack = <name>
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_paths, write_config_section

log = logging.getLogger(__name__)

_RESERVED_PACKS = {"default"}  # kept read-only so fresh installs always work


# ---------------------------------------------------------------------------
# Pack enumeration / switching
# ---------------------------------------------------------------------------

def _valid_pack_name(name: str) -> bool:
    if not name:
        return False
    if "/" in name or "\\" in name or ".." in name or name.startswith("."):
        return False
    return True


def list_packs() -> list[str]:
    presets_dir = get_paths().presets_dir
    if not presets_dir.is_dir():
        return []
    return sorted(p.name for p in presets_dir.iterdir() if p.is_dir())


def active_pack_name() -> str:
    return get_paths().active_pack_name()


def switch_active_pack(name: str) -> str:
    if not _valid_pack_name(name):
        raise ValueError(f"invalid pack name: {name!r}")
    paths = get_paths()
    pack_dir = paths.presets_dir / name
    if not pack_dir.is_dir():
        raise FileNotFoundError(str(pack_dir))

    write_config_section("active", {"pack": name})
    # Drop Paths cache so subsequent get_paths().active_pack_name() reads the new value.
    get_paths.cache_clear()  # type: ignore[attr-defined]
    # Blend-shape schema may differ between packs — drop the render LRU so
    # stale cached meshes don't leak across the switch.
    try:
        from .renderer import invalidate_cache
        invalidate_cache()
    except Exception:  # noqa: BLE001
        pass
    return name


def clone_pack(source: str, target: str) -> Path:
    if not _valid_pack_name(source) or not _valid_pack_name(target):
        raise ValueError(f"invalid pack name: source={source!r} target={target!r}")
    if target in _RESERVED_PACKS:
        raise ValueError(f"'{target}' is reserved; pick a different name")
    paths = get_paths()
    src = paths.presets_dir / source
    dst = paths.presets_dir / target
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    if dst.exists():
        raise FileExistsError(str(dst))
    shutil.copytree(src, dst)
    log.info("cloned pack %s -> %s", src, dst)
    return dst


def delete_pack(name: str) -> None:
    if not _valid_pack_name(name):
        raise ValueError(f"invalid pack name: {name!r}")
    if name in _RESERVED_PACKS:
        raise ValueError(f"'{name}' is reserved and cannot be deleted")
    paths = get_paths()
    pack_dir = paths.presets_dir / name
    if not pack_dir.is_dir():
        raise FileNotFoundError(str(pack_dir))
    shutil.rmtree(pack_dir)
    # If the active pack was just wiped, fall back to default.
    if paths.active_pack_name() == name:
        switch_active_pack("default")


# ---------------------------------------------------------------------------
# Blender FBX rebuild — runs extract_face_blendshapes.py + rebuild_vertex_jsons.py
# ---------------------------------------------------------------------------

@dataclass
class RebuildResult:
    fbx_path: str
    npz_path: str
    num_blendshapes: int
    num_vertex_jsons: int
    elapsed_sec: float
    blender_log_tail: str


def _current_fbx_path() -> Path:
    return get_paths().root / "tools" / "bone_backup" / "all_parts_bs.fbx"


def fbx_status() -> dict[str, Any]:
    """Return mtime / size of the reference FBX and the currently-cached npz
    so the UI can tell the user whether a rebuild is pending."""
    fbx = _current_fbx_path()
    pack = get_paths().active_pack_dir()
    npz = pack / "face_blendshapes.npz"
    return {
        "fbx_path": str(fbx),
        "fbx_exists": fbx.is_file(),
        "fbx_mtime": fbx.stat().st_mtime if fbx.is_file() else None,
        "fbx_size": fbx.stat().st_size if fbx.is_file() else None,
        "npz_path": str(npz),
        "npz_exists": npz.is_file(),
        "npz_mtime": npz.stat().st_mtime if npz.is_file() else None,
        "stale": (
            fbx.is_file() and npz.is_file()
            and fbx.stat().st_mtime > npz.stat().st_mtime
        ),
        "active_pack": active_pack_name(),
    }


def adopt_fbx_upload(src_path: Path) -> Path:
    """Copy ``src_path`` (a freshly-uploaded FBX) into the canonical
    ``tools/bone_backup/all_parts_bs.fbx`` location and return the canonical
    path. Downstream extract_face_blendshapes.py always reads from there."""
    dst = _current_fbx_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dst)
    return dst


def rebuild_blendshapes_from_fbx(
    *,
    blender_exe: str,
    python_exe: str | None = None,
    timeout_sec: int = 600,
) -> RebuildResult:
    """Run the two-step FBX → npz → vertex-JSON pipeline against the current
    active preset pack. Requires Blender + this venv's torch."""
    t0 = time.monotonic()
    paths = get_paths()
    fbx = _current_fbx_path()
    if not fbx.is_file():
        raise FileNotFoundError(f"reference FBX missing: {fbx}")
    if not blender_exe or not Path(blender_exe).is_file():
        raise RuntimeError(
            f"Blender executable not found: {blender_exe!r}. "
            "Set SAM3DBODY_BLENDER_EXE or pass blender_exe."
        )

    extract_script = (paths.root / "tools" / "extract_face_blendshapes.py").resolve()
    rebuild_script = (paths.root / "tools" / "rebuild_vertex_jsons.py").resolve()
    for s in (extract_script, rebuild_script):
        if not s.is_file():
            raise FileNotFoundError(str(s))

    # Step 1: Blender headless — produces presets/<pack>/face_blendshapes.npz
    cmd_bl = [blender_exe, "--background", "--python", str(extract_script)]
    log.info("rebuild step 1/2: %s", cmd_bl)
    blender_result = subprocess.run(
        cmd_bl, capture_output=True, text=True, timeout=timeout_sec,
    )
    if blender_result.returncode != 0:
        log.error("blender stdout:\n%s", blender_result.stdout or "")
        log.error("blender stderr:\n%s", blender_result.stderr or "")
        raise RuntimeError(
            f"extract_face_blendshapes.py failed (exit {blender_result.returncode})"
        )

    # Step 2: our venv's Python — produces presets/<pack>/<obj>_vertices.json
    py = python_exe or sys.executable
    cmd_py = [str(py), str(rebuild_script)]
    log.info("rebuild step 2/2: %s", cmd_py)
    py_result = subprocess.run(
        cmd_py, capture_output=True, text=True, timeout=timeout_sec,
    )
    if py_result.returncode != 0:
        log.error("rebuild_vertex_jsons stdout:\n%s", py_result.stdout or "")
        log.error("rebuild_vertex_jsons stderr:\n%s", py_result.stderr or "")
        raise RuntimeError(
            f"rebuild_vertex_jsons.py failed (exit {py_result.returncode})"
        )

    pack = paths.active_pack_dir()
    npz_path = pack / "face_blendshapes.npz"
    if not npz_path.is_file():
        raise RuntimeError(f"npz expected at {npz_path} but missing")

    # New blendshape schema — drop the render LRU so old cached meshes
    # built against the previous keys don't replay.
    try:
        from .renderer import invalidate_cache
        invalidate_cache()
    except Exception:  # noqa: BLE001
        pass

    # Count outputs for the response.
    try:
        import numpy as np
        with np.load(npz_path) as npz:
            shapes = list(npz["meta_shapes"]) if "meta_shapes" in npz.files else []
    except Exception as exc:  # noqa: BLE001
        log.warning("npz probe failed: %s", exc)
        shapes = []
    num_vertex_jsons = len(list(pack.glob("*_vertices.json")))

    tail = (blender_result.stdout or "")[-1200:]
    elapsed = time.monotonic() - t0
    log.info(
        "rebuild done: pack=%s shapes=%d vertex_jsons=%d elapsed=%.2fs",
        pack.name, len(shapes), num_vertex_jsons, elapsed,
    )
    return RebuildResult(
        fbx_path=str(fbx),
        npz_path=str(npz_path),
        num_blendshapes=len(shapes),
        num_vertex_jsons=num_vertex_jsons,
        elapsed_sec=elapsed,
        blender_log_tail=tail,
    )
