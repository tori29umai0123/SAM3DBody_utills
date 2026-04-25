from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import AppSettings, get_paths
from .routers import character, export, health, pipeline, preset_admin, video

log = logging.getLogger(__name__)


def _get_lan_ipv4() -> list[str]:
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def _print_access_urls() -> None:
    host = os.environ.get("SAM3DBODY_HOST")
    port = os.environ.get("SAM3DBODY_PORT")
    if not host or not port:
        # Running without the launcher scripts; nothing authoritative to print.
        return
    lines = ["", "Access URL:"]
    if host in ("0.0.0.0", "::"):
        lines.append(f"  http://127.0.0.1:{port}       (this PC)")
        for ip in _get_lan_ipv4():
            lines.append(f"  http://{ip}:{port}       (LAN)")
    else:
        lines.append(f"  http://{host}:{port}")
        if host in ("127.0.0.1", "localhost", "::1"):
            lines.append("  (LAN access disabled: set SAM3DBODY_HOST=0.0.0.0 to expose)")
    lines.append("")
    # Go through stdout so the URLs appear after uvicorn's own startup
    # logging (which writes to stderr by default).
    print("\n".join(lines), flush=True)


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
    # The access-URL banner is the LAST thing printed so it sits at the
    # bottom of the console after uvicorn's startup logs and the preload
    # log lines — users copy it from the tail of the terminal.
    async def _preload():
        from .services import sam3dbody_loader
        try:
            await asyncio.to_thread(sam3dbody_loader.load_bundle)
            log.info("preload: SAM3DBody bundle ready")
        except Exception:  # noqa: BLE001
            log.exception("preload: SAM3DBody load failed (will retry lazily)")
        _print_access_urls()

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
