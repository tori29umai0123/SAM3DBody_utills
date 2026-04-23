"""Video → animated rigged FBX endpoints (Phase 4)."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..config import AppSettings
from ..services.animated_fbx_export import (
    build_animated_fbx_from_motion,
    export_animated_fbx,
    run_motion_inference,
)
from ..services.video_frames import probe_video

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["video"])


@router.post("/process_video")
async def process_video(
    request: Request,
    video: UploadFile = File(...),
    settings: str = Form("{}"),
    fps: float | None = Form(None),
    bbox_threshold: float = Form(0.8),
    inference_type: str = Form("full"),
    root_motion_mode: str = Form("auto_ground_lock"),
    max_frames: int | None = Form(None),
    stride: int = Form(1),
    blender_exe: str | None = Form(None),
) -> dict[str, Any]:
    """Run per-frame SAM3 + SAM3DBody on the uploaded video and bake an
    animated rigged FBX. SAM3 params come from ``config.ini [sam3]``."""
    # Stream the upload to a temp file so PyAV can seek.
    if video.content_type and not video.content_type.startswith(("video/", "application/octet-stream")):
        raise HTTPException(status_code=400, detail=f"expected video/*, got {video.content_type}")

    suffix = Path(video.filename or "").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(video.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        settings_obj: dict[str, Any] = json.loads(settings) if settings else {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"settings JSON parse failed: {exc}")

    # Read config.ini live so edits hot-reload without restart.
    app_settings = AppSettings.load()
    sam3 = app_settings.sam3
    exe = blender_exe or app_settings.blender_exe

    try:
        result = export_animated_fbx(
            video_path=tmp_path,
            settings=settings_obj,
            blender_exe=exe,
            fps=fps,
            bbox_threshold=bbox_threshold,
            inference_type=inference_type,
            root_motion_mode=root_motion_mode,
            max_frames=max_frames,
            stride=max(1, int(stride)),
            use_sam3=sam3.use_sam3,
            sam3_text_prompt=sam3.text_prompt,
            sam3_threshold=sam3.confidence_threshold,
        )
    except RuntimeError as exc:
        log.exception("animated fbx export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("animated fbx export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()

    return {
        "motion_id": result.motion_id,
        "fbx_path": result.fbx_path,
        "fbx_url": result.fbx_url,
        "elapsed_sec": round(result.elapsed_sec, 3),
        "num_frames": result.num_frames,
        "skipped_frames": result.skipped_frames,
    }


@router.post("/infer_motion")
async def infer_motion(
    request: Request,
    video: UploadFile = File(...),
    fps: float | None = Form(None),
    bbox_threshold: float = Form(0.8),
    inference_type: str = Form("full"),
    max_frames: int | None = Form(None),
    stride: int = Form(1),
) -> dict[str, Any]:
    """Phase 1 of the motion → FBX pipeline: only the slow SAM3 + SAM3DBody
    per-frame inference. Returns a ``motion_id`` that the frontend then
    feeds back into ``/api/build_animated_fbx`` along with any character
    settings. SAM3 params come from ``config.ini [sam3]``."""
    if video.content_type and not video.content_type.startswith(("video/", "application/octet-stream")):
        raise HTTPException(status_code=400, detail=f"expected video/*, got {video.content_type}")

    suffix = Path(video.filename or "").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(video.file, tmp)
        tmp_path = Path(tmp.name)

    app_settings = AppSettings.load()
    sam3 = app_settings.sam3

    try:
        motion = run_motion_inference(
            tmp_path,
            bbox_threshold=bbox_threshold,
            inference_type=inference_type,
            max_frames=max_frames,
            stride=max(1, int(stride)),
            use_sam3=sam3.use_sam3,
            sam3_text_prompt=sam3.text_prompt,
            sam3_threshold=sam3.confidence_threshold,
            fps=fps,
        )
    except RuntimeError as exc:
        log.exception("motion inference failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("motion inference failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()

    return {
        "motion_id": motion.motion_id,
        "num_frames": motion.num_frames,
        "skipped_frames": motion.skipped_frames,
        "fps": motion.fps,
        "source_name": motion.source_name,
    }


@router.post("/build_animated_fbx")
async def build_animated_fbx(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Phase 2: rebuild the animated FBX for a cached motion with different
    character settings — no video re-inference."""
    motion_id = str(payload.get("motion_id") or "")
    if not motion_id:
        raise HTTPException(status_code=400, detail="motion_id is required")
    settings = payload.get("settings") or {}
    root_motion_mode = payload.get("root_motion_mode") or "auto_ground_lock"

    app_settings = AppSettings.load()
    exe = payload.get("blender_exe") or app_settings.blender_exe

    try:
        result = build_animated_fbx_from_motion(
            motion_id,
            settings,
            blender_exe=exe,
            root_motion_mode=root_motion_mode,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        log.exception("animated fbx build failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("animated fbx build failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "motion_id": result.motion_id,
        "fbx_path": result.fbx_path,
        "fbx_url": result.fbx_url,
        "elapsed_sec": round(result.elapsed_sec, 3),
        "num_frames": result.num_frames,
        "skipped_frames": result.skipped_frames,
    }


@router.post("/probe_video")
async def probe_video_endpoint(video: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(video.filename or "").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(video.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        info = probe_video(tmp_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        try:
            tmp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()
    return info
