"""FastAPI application factory.

The factory creates an app bound to a specific :class:`AppConfig` and an
engine/session factory. Tests use this directly with an in-memory SQLite
DB; the CLI entry point loads the JSON config and hands it in.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from firefly_api.api.admin import admin_router
from firefly_api.api.public import public_router
from firefly_api.core.config import AppConfig
from firefly_api.core.errors import register_exception_handlers
from firefly_api.db.session import create_engine_for_url, create_session_factory

logger = logging.getLogger(__name__)


def create_app(config: AppConfig) -> FastAPI:
    engine = create_engine_for_url(config.database.url)
    session_factory = create_session_factory(engine)

    app = FastAPI(
        title="Firefly API Service",
        version="0.1.0",
        description="Middleware and configuration platform for Macrolet Firefly devices.",
    )
    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    # Runtime objects (registry, mqtt client, retention job, firefly service)
    # are installed by the entry point or by tests. The default values let
    # the admin CRUD surface come up even when MQTT is not configured.
    app.state.firefly_service = None
    app.state.registry = None
    app.state.mqtt_client = None
    app.state.retention_job = None

    register_exception_handlers(app)
    app.include_router(admin_router)
    app.include_router(public_router)
    _mount_frontend_if_present(app, config)

    return app


def _resolve_frontend_root(config: AppConfig) -> Path | None:
    """Pick the directory that holds the built React bundle, if any.

    Resolution order:

    1. The configured ``frontend.staticFilesPath`` interpreted relative to
       the process working directory (the dev / source-checkout case).
    2. When the app is running inside a PyInstaller bundle, the same
       relative path interpreted against ``sys._MEIPASS`` — that's where
       the spec's ``datas`` list dropped the frontend bundle, and
       PyInstaller 6 keeps it under ``<bundle>/_internal/`` rather than
       next to the exe.

    Returns the first candidate that is a directory and contains an
    ``index.html``; otherwise ``None``.
    """
    raw = Path(config.frontend.static_files_path)
    candidates: list[Path] = [raw]
    if not raw.is_absolute() and getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / raw)
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _mount_frontend_if_present(app: FastAPI, config: AppConfig) -> None:
    """Mount the built React app at ``/`` when ``frontend.staticFilesPath`` exists.

    Behavior:

    - If the configured path does not exist (typical for the development
      workflow where the frontend is served by the Vite dev server), this
      is a silent no-op.
    - Otherwise the bundle is mounted at ``/``. A catch-all route returns
      ``index.html`` for unknown paths so client-side routes survive a
      page reload; ``/api/*`` continues to hit FastAPI normally.
    - The PyInstaller frozen case is handled too: see
      :func:`_resolve_frontend_root`.
    """
    static_root = _resolve_frontend_root(config)
    if static_root is None:
        return
    index_file = static_root / "index.html"

    # Per-file static mount avoids shadowing the API routers above. We
    # only mount the /assets/ subdir (Vite bundles everything else there)
    # plus a small allowlist for the logo + favicon.
    assets_dir = static_root / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="frontend-assets",
        )

    @app.get("/logo-firefly.png", include_in_schema=False)
    def _logo() -> FileResponse:  # noqa: ANN202
        return FileResponse(static_root / "logo-firefly.png")

    @app.get("/", include_in_schema=False)
    def _index() -> FileResponse:  # noqa: ANN202
        return FileResponse(index_file)

    # Catch-all for client-side routes (/dashboard, /devices/..., etc.).
    # Anything starting with api/ is left to the normal 404 handler so
    # unknown API endpoints don't silently return the SPA shell.
    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> FileResponse:  # noqa: ANN202
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index_file)

    logger.info("Frontend bundle mounted at / from %s", static_root)
