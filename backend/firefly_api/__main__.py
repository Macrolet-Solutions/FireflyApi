"""CLI entry point: ``python -m firefly_api [--config PATH] [--host HOST] [--port PORT]``.

Performs the startup sequence in §11 (Phase 1 scope only: load config,
create the SQLite parent directory, run Alembic migrations, serve the
FastAPI app). MQTT and the actor runtime arrive in Phase 2.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from firefly_api.core.config import load_config
from firefly_api.core.runtime import start_runtime, stop_runtime
from firefly_api.core.startup import bootstrap
from firefly_api.main import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="firefly_api")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to firefly-appsettings.json (default ./config/firefly-appsettings.json).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override server.host from the JSON config.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override server.port from the JSON config.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    bootstrap(config)
    app = create_app(config)
    start_runtime(app, config)

    try:
        uvicorn.run(
            app,
            host=args.host or config.server.host,
            port=args.port or config.server.port,
        )
    finally:
        stop_runtime(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
