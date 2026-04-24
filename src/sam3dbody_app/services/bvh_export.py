"""BVH export helpers.

Image-tab export builds a rigged FBX first, then converts it to a single-frame
BVH. Video-tab export rebuilds the animated FBX for the cached motion, then
converts the full clip to BVH.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_paths
from .animated_fbx_export import AnimatedFBXResult, build_animated_fbx_from_motion
from .fbx_export import FBXExportResult, export_rigged_fbx

log = logging.getLogger(__name__)


@dataclass
class BVHExportResult:
    bvh_path: str
    bvh_url: str
    elapsed_sec: float
    num_frames: int | None = None
    motion_id: str | None = None


def convert_fbx_to_bvh(
    src_fbx: str | Path,
    dst_bvh: str | Path,
    *,
    blender_exe: str,
    strength: float = 1.0,
    single_frame: bool = False,
    timeout_sec: int = 600,
) -> None:
    paths = get_paths()
    script = (paths.root / "tools" / "fbx2bvh_simple.py").resolve()
    correction = (paths.root / "tools" / "rest_correction.json").resolve()

    if not script.is_file():
        raise RuntimeError(f"BVH conversion script missing: {script}")
    if not correction.is_file():
        raise RuntimeError(f"rest correction JSON missing: {correction}")
    if not blender_exe or not Path(blender_exe).is_file():
        raise RuntimeError(
            f"Blender executable not found: {blender_exe!r}. "
            "Set SAM3DBODY_BLENDER_EXE or configure [blender] exe_path."
        )

    cmd = [
        blender_exe,
        "--background",
        "--python",
        str(script),
        "--",
        str(src_fbx),
        str(dst_bvh),
        "--strength",
        str(float(strength)),
        "--correction",
        str(correction),
    ]
    if single_frame:
        cmd.append("--single-frame")

    log.info("bvh subprocess: %s", " ".join(shlex.quote(c) for c in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    if result.returncode != 0:
        log.error("bvh stdout:\n%s", result.stdout or "")
        log.error("bvh stderr:\n%s", result.stderr or "")
        raise RuntimeError(f"bvh export failed (exit {result.returncode}). See server log.")

    out_path = Path(dst_bvh)
    if not out_path.is_file():
        log.error("bvh stdout:\n%s", result.stdout or "")
        log.error("bvh stderr:\n%s", result.stderr or "")
        raise RuntimeError(f"bvh export reported success but {out_path} was not created.")

    if result.stdout:
        log.info("bvh stdout tail:\n%s", result.stdout[-800:])


def export_rigged_bvh(
    job_id: str,
    settings: dict[str, Any] | None,
    *,
    blender_exe: str,
    strength: float = 1.0,
    timeout_sec: int = 600,
) -> BVHExportResult:
    t0 = time.monotonic()
    paths = get_paths()

    fbx_result: FBXExportResult = export_rigged_fbx(
        job_id=job_id,
        settings=settings,
        blender_exe=blender_exe,
        timeout_sec=timeout_sec,
    )
    output_path = (paths.tmp_dir / "rigged.bvh").resolve()
    convert_fbx_to_bvh(
        fbx_result.fbx_path,
        output_path,
        blender_exe=blender_exe,
        strength=strength,
        single_frame=True,
        timeout_sec=timeout_sec,
    )
    elapsed = time.monotonic() - t0
    return BVHExportResult(
        bvh_path=str(output_path),
        bvh_url=f"/tmp/rigged.bvh?v={uuid.uuid4().hex[:8]}",
        elapsed_sec=elapsed,
        num_frames=1,
    )


def export_animated_bvh_from_motion(
    motion_id: str,
    settings: dict[str, Any] | None,
    *,
    blender_exe: str,
    root_motion_mode: str = "auto_ground_lock",
    strength: float = 1.0,
    timeout_sec_base: int = 600,
) -> BVHExportResult:
    t0 = time.monotonic()
    paths = get_paths()

    fbx_result: AnimatedFBXResult = build_animated_fbx_from_motion(
        motion_id,
        settings,
        blender_exe=blender_exe,
        root_motion_mode=root_motion_mode,
        timeout_sec_base=timeout_sec_base,
    )
    output_path = (paths.tmp_dir / "animated.bvh").resolve()
    timeout_s = max(timeout_sec_base, 30 + 2 * fbx_result.num_frames)
    convert_fbx_to_bvh(
        fbx_result.fbx_path,
        output_path,
        blender_exe=blender_exe,
        strength=strength,
        single_frame=False,
        timeout_sec=timeout_s,
    )
    elapsed = time.monotonic() - t0
    return BVHExportResult(
        bvh_path=str(output_path),
        bvh_url=f"/tmp/animated.bvh?v={uuid.uuid4().hex[:8]}",
        elapsed_sec=elapsed,
        num_frames=fbx_result.num_frames,
        motion_id=fbx_result.motion_id,
    )
