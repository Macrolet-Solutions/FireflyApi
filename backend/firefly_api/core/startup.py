"""Startup helpers shared by the entry point and tests.

§11 startup sequence:

1. Load application configuration from JSON.
2. Open / create the SQLite database file (and its parent directory).
3. Run ``alembic upgrade head``. Abort if migrations fail.
4-9. (Implemented in later phases — MQTT broker, actors.)
10. Serve FastAPI routes (handled by the entry point).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config

from firefly_api.core.config import AppConfig


def _backend_root() -> Path:
    # backend/firefly_api/core/startup.py -> backend/
    return Path(__file__).resolve().parent.parent.parent


def ensure_sqlite_parent_dir(db_url: str) -> None:
    """Create the parent directory of a SQLite file-backed DB if needed."""
    if not db_url.startswith("sqlite:"):
        return
    if db_url == "sqlite:///:memory:" or db_url == "sqlite://":
        return
    # SQLAlchemy SQLite URLs look like sqlite:///./data/firefly.db or
    # sqlite:////absolute/path/firefly.db.
    parsed = urlparse(db_url)
    # netloc is empty for sqlite; the path holds everything after 'sqlite://'.
    raw_path = parsed.path
    # Strip the leading slash that SQLAlchemy requires before relative paths
    # (sqlite:///./data/x.db -> '/./data/x.db').
    if raw_path.startswith("/./") or raw_path.startswith("/."):
        raw_path = raw_path[1:]
    elif raw_path.startswith("/"):
        # Absolute path on POSIX (/tmp/x.db) or a triple-slash relative on
        # Windows. Both behave correctly once handed to pathlib.
        pass
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
    """Steps 2 and 3 of the §11 startup sequence."""
    ensure_sqlite_parent_dir(config.database.url)
    run_migrations(config)
