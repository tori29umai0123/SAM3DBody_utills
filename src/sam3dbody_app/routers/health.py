from __future__ import annotations

import sys

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/features")
async def features(request: Request):
    """Runtime feature flags that the frontend uses to gate UI elements.
    Reads live from config.ini so editing the ini at runtime takes effect
    without a server restart."""
    from ..config import AppSettings

    s = AppSettings.load()
    return {
        "preset_pack_admin": bool(s.feature_preset_pack_admin),
        "debug": bool(s.feature_debug),
        "blender_exe": s.blender_exe,
    }


@router.get("/health")
async def health(request: Request):
    paths = request.app.state.paths
    settings = request.app.state.settings

    info: dict = {
        "status": "ok",
        "python": sys.version.split()[0],
        "root": str(paths.root),
        "active_pack": paths.active_pack_name(),
        "device": settings.device,
    }

    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        info["cuda_device"] = (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        )
    except Exception as exc:
        info["torch_error"] = str(exc)

    return info
