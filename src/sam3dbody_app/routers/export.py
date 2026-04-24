"""FBX / BVH export endpoints (Phase 3)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from ..services.bvh_export import export_rigged_bvh
from ..services.fbx_export import export_rigged_fbx

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["export"])


@router.post("/export_fbx")
async def export_fbx(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    settings = payload.get("settings") or {}
    blender_exe = payload.get("blender_exe") or request.app.state.settings.blender_exe

    try:
        result = export_rigged_fbx(
            job_id=job_id, settings=settings, blender_exe=blender_exe,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        log.exception("fbx export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("fbx export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "fbx_path": result.fbx_path,
        "fbx_url": result.fbx_url,
        "elapsed_sec": round(result.elapsed_sec, 3),
    }


@router.post("/export_bvh")
async def export_bvh(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    settings = payload.get("settings") or {}
    blender_exe = payload.get("blender_exe") or request.app.state.settings.blender_exe
    strength = float(payload.get("strength", 1.0))

    try:
        result = export_rigged_bvh(
            job_id=job_id,
            settings=settings,
            blender_exe=blender_exe,
            strength=strength,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        log.exception("bvh export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("bvh export failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "bvh_path": result.bvh_path,
        "bvh_url": result.bvh_url,
        "elapsed_sec": round(result.elapsed_sec, 3),
        "num_frames": result.num_frames,
    }


@router.get("/blender_info")
async def blender_info(request: Request) -> dict[str, Any]:
    """Report the currently configured Blender path and whether it exists —
    handy for the UI to gate the FBX export button."""
    from pathlib import Path

    exe = request.app.state.settings.blender_exe
    exists = bool(exe) and Path(exe).is_file()
    return {"blender_exe": exe, "exists": exists}
