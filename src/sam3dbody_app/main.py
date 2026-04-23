from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import AppSettings, get_paths
from .routers import character, export, health, pipeline, preset_admin, video

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    paths = get_paths()
    settings = AppSettings.load()
    app.state.paths = paths
    app.state.settings = settings

    # Warm up the heavyweight models on a background thread so the first
    # /api/process / /api/infer_motion doesn't pay the 5-10 s cold-start.
    # `asyncio.to_thread` keeps the event loop free while torch loads
    # weights; the per-loader caches make subsequent requests no-ops.
    async def _preload():
        from .services import sam3_loader, sam3dbody_loader
        try:
            await asyncio.to_thread(sam3dbody_loader.load_bundle)
            log.info("preload: SAM3DBody bundle ready")
        except Exception:  # noqa: BLE001
            log.exception("preload: SAM3DBody load failed (will retry lazily)")
        if settings.sam3.use_sam3:
            try:
                await asyncio.to_thread(sam3_loader.load_bundle)
                log.info("preload: SAM3 bundle ready")
            except Exception:  # noqa: BLE001
                log.exception("preload: SAM3 load failed (will retry lazily)")

    preload_task = asyncio.create_task(_preload())

    try:
        yield
    finally:
        if not preload_task.done():
            preload_task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="SAM 3D Body Standalone", version="0.1.0", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(pipeline.router)
    app.include_router(character.router)
    app.include_router(export.router)
    app.include_router(video.router)
    app.include_router(preset_admin.router)

    paths = get_paths()
    web_dir = paths.web_dir
    index_path = web_dir / "index.html"

    @app.get("/", include_in_schema=False)
    async def root():
        if index_path.is_file():
            return FileResponse(index_path)
        return {"status": "ok", "message": "web/index.html not found"}

    static_dir = web_dir / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Serve the transient tmp directory (mesh.obj / mask.png / *.fbx).
    # Everything here is a single-file output that gets overwritten on each
    # call — the frontend cache-busts with a `?v=...` query string when
    # reloading. The legacy /output path is aliased to the same directory
    # so older bookmarks / external tools still resolve.
    if paths.tmp_dir.is_dir():
        app.mount("/tmp", StaticFiles(directory=paths.tmp_dir), name="tmp")

    return app


app = create_app()
