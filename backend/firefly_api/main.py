"""FastAPI application factory.

The factory creates an app bound to a specific :class:`AppConfig` and an
engine/session factory. Tests use this directly with an in-memory SQLite
DB; the CLI entry point loads the JSON config and hands it in.
"""

from __future__ import annotations

from fastapi import FastAPI

from firefly_api.api.admin import admin_router
from firefly_api.core.config import AppConfig
from firefly_api.core.errors import register_exception_handlers
from firefly_api.db.session import create_engine_for_url, create_session_factory


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

    register_exception_handlers(app)
    app.include_router(admin_router)

    return app
