"""Startup helpers shared by the entry point and tests.

§11 startup sequence:

1. Load application configuration from JSON.
2. Open / create the SQLite database file (and its parent directory).
3. Run ``alembic upgrade head``. Abort if migrations fail.
4-9. (Implemented in later phases — MQTT broker, actors.)
10. Serve FastAPI routes (handled by the entry point).
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy.engine import make_url

from alembic import command
from firefly_api.core.auth import initialize_auth
from firefly_api.core.config import AppConfig
from firefly_api.db.session import create_engine_for_url, create_session_factory


def _backend_root() -> Path:
    """Resolve the directory that contains ``alembic.ini`` and ``alembic/``.

    Two layouts:

    - **Source checkout**: ``backend/firefly_api/core/startup.py`` →
      ``backend/`` after three ``parent`` calls.
    - **PyInstaller bundle**: when the app is frozen, the ``alembic.ini``
      and ``alembic/`` directory are emitted into ``sys._MEIPASS``
      (PyInstaller's runtime extraction root) by the spec's ``datas``
      list, so the bundle root is the right answer.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent.parent


def ensure_sqlite_parent_dir(db_url: str) -> None:
    """Create the parent directory of a SQLite file-backed DB if needed."""
    if not db_url.startswith("sqlite:"):
        return
    if db_url == "sqlite:///:memory:" or db_url == "sqlite://":
        return
    raw_path = make_url(db_url).database
    if raw_path is None:
        raise ValueError("SQLite database URL must specify a database path.")
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)


def run_migrations(config: AppConfig) -> None:
    """Run ``alembic upgrade head`` against the configured database."""
    alembic_cfg = Config(str(_backend_root() / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_backend_root() / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", config.database.url)
    command.upgrade(alembic_cfg, "head")


def bootstrap(config: AppConfig) -> None:
    """Migrate the database and initialize authentication before serving requests."""
    ensure_sqlite_parent_dir(config.database.url)
    run_migrations(config)
    engine = create_engine_for_url(config.database.url)
    try:
        with create_session_factory(engine)() as db:
            initialize_auth(db)
    finally:
        engine.dispose()
