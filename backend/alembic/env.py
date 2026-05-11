"""Alembic environment.

Loads the database URL from the application configuration file (§13) rather
than from ``alembic.ini``. This lets migrations honor whatever
``--config <path>`` the operator is using for the running service.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the firefly_api package importable when alembic is invoked from
# the backend/ directory.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from firefly_api.core.config import load_config  # noqa: E402
from firefly_api.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Return the DB URL.

    Order of precedence:

    1. ``sqlalchemy.url`` already set on the alembic config — used by
       :func:`firefly_api.core.startup.run_migrations`, which passes the URL
       in directly so the config file does not get re-read.
    2. ``FIREFLY_CONFIG`` environment variable pointing at a JSON config
       file. Developer convenience for ``alembic upgrade head`` invoked
       from the CLI; not used by normal service startup (§13).
    3. The default config path (``./config/firefly-appsettings.json``).
    """
    pre_set = config.get_main_option("sqlalchemy.url") or ""
    if pre_set:
        return pre_set
    explicit = os.environ.get("FIREFLY_CONFIG") or None
    app_config = load_config(explicit)
    return app_config.database.url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _resolve_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
