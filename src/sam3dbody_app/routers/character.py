"""Body-shape / preset-pack endpoints (Phase 2).

Mirrors the /sam3d/autosave and /sam3d/preset/{name} routes of the upstream
ComfyUI-SAM3DBody_utills node, plus a /api/render that applies slider values
to a cached pose session.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..services import preset_pack
from ..services.character_shape import BODY_PARAM_KEYS, BONE_LENGTH_KEYS, discover_blendshape_names
from ..services.renderer import render_from_session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["character"])


# ---------------------------------------------------------------------------
# Slider definitions (used by the frontend to build the UI dynamically).
# ---------------------------------------------------------------------------

@router.get("/slider_schema")
async def slider_schema() -> dict[str, Any]:
    """Return the full slider list (body_params + bone_lengths + blendshapes
    discovered from the active pack's npz)."""
    pack = preset_pack.active_pack_paths()
    bs_names = list(discover_blendshape_names(pack.npz_path))
    return {
        "pack": pack.pack_dir.name,
        "body_params": [
            {"key": k, "min": -5.0, "max": 5.0, "step": 0.01, "default": 0.0}
            for k in BODY_PARAM_KEYS
        ],
        "bone_lengths": [
            {"key": "torso", "min": 0.3, "max": 1.8, "step": 0.01, "default": 1.0},
            {"key": "neck",  "min": 0.3, "max": 2.0, "step": 0.01, "default": 1.0},
            {"key": "arm",   "min": 0.3, "max": 2.0, "step": 0.01, "default": 1.0},
            {"key": "leg",   "min": 0.3, "max": 2.0, "step": 0.01, "default": 1.0},
        ],
        "blendshapes": [
            {"key": name, "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0}
            for name in bs_names
        ],
    }


# ---------------------------------------------------------------------------
# Preset I/O.
# ---------------------------------------------------------------------------

@router.get("/presets")
async def list_presets() -> dict[str, Any]:
    return {"presets": preset_pack.list_presets()}


@router.get("/preset/{name}")
async def get_preset(name: str) -> dict[str, Any]:
    try:
        return preset_pack.load_preset(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"preset '{name}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/preset/{name}")
async def save_preset(name: str, settings: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        p = preset_pack.save_preset(name, settings)
        return {"saved": str(p)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Render (apply slider settings to a cached pose).
# ---------------------------------------------------------------------------

@router.post("/render")
async def render(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    settings = payload.get("settings") or {}
    try:
        result = render_from_session(job_id, settings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("render failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "job_id": result.job_id,
        "obj_url": result.obj_url,
        "elapsed_sec": round(result.elapsed_sec, 3),
        "settings": result.settings,
    }
