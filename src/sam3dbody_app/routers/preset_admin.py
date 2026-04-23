"""Preset pack admin endpoints (Phase 5)."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..services import preset_admin as svc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["preset_admin"])


def _require_feature(request: Request) -> None:
    """Gate every mutating endpoint on ``[features] preset_pack_admin = true``.
    Reads the live setting on each call so editing config.ini at runtime
    takes effect without restarting the server."""
    from ..config import AppSettings

    settings = AppSettings.load()
    if not settings.feature_preset_pack_admin:
        raise HTTPException(
            status_code=403,
            detail=(
                "Preset Pack Admin is disabled. Enable it by setting "
                "`[features] preset_pack_admin = true` in config.ini."
            ),
        )


@router.get("/preset_packs")
async def list_packs() -> dict[str, Any]:
    # Read-only, always allowed; the frontend uses this for the Character
    # section's active-pack label too.
    return {"active": svc.active_pack_name(), "packs": svc.list_packs()}


@router.post("/preset_packs/active")
async def set_active_pack(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    _require_feature(request)
    name = str(payload.get("name") or "")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        svc.switch_active_pack(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"pack '{name}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"active": svc.active_pack_name()}


@router.post("/preset_packs/clone")
async def clone_pack(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    _require_feature(request)
    source = str(payload.get("source") or "default")
    target = str(payload.get("target") or "")
    if not target:
        raise HTTPException(status_code=400, detail="target is required")
    try:
        dst = svc.clone_pack(source, target)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"source '{source}' not found")
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"target '{target}' already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"cloned": str(dst)}


@router.delete("/preset_packs/{name}")
async def delete_pack(request: Request, name: str) -> dict[str, Any]:
    _require_feature(request)
    try:
        svc.delete_pack(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"pack '{name}' not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"deleted": name, "active": svc.active_pack_name()}


# ---------------------------------------------------------------------------
# FBX rebuild
# ---------------------------------------------------------------------------

@router.get("/fbx_status")
async def fbx_status() -> dict[str, Any]:
    # Read-only probe; always allowed.
    return svc.fbx_status()


@router.post("/fbx_upload")
async def fbx_upload(request: Request, fbx: UploadFile = File(...)) -> dict[str, Any]:
    _require_feature(request)
    """Replace tools/bone_backup/all_parts_bs.fbx with the uploaded FBX.
    Call `/api/rebuild_blendshapes` afterwards to regenerate the npz +
    vertex JSONs."""
    if fbx.content_type and "fbx" not in (fbx.content_type or "").lower():
        log.info("fbx upload content_type=%s (accepted)", fbx.content_type)
    with tempfile.NamedTemporaryFile(suffix=".fbx", delete=False) as tmp:
        shutil.copyfileobj(fbx.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        dst = svc.adopt_fbx_upload(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()
    return {"fbx_path": str(dst), **svc.fbx_status()}


@router.post("/rebuild_blendshapes")
async def rebuild_blendshapes(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _require_feature(request)
    payload = payload or {}
    blender_exe = str(payload.get("blender_exe") or request.app.state.settings.blender_exe)
    try:
        result = svc.rebuild_blendshapes_from_fbx(blender_exe=blender_exe)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        log.exception("rebuild failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("rebuild failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "fbx_path": result.fbx_path,
        "npz_path": result.npz_path,
        "num_blendshapes": result.num_blendshapes,
        "num_vertex_jsons": result.num_vertex_jsons,
        "elapsed_sec": round(result.elapsed_sec, 3),
        "blender_log_tail": result.blender_log_tail,
        **svc.fbx_status(),
    }
