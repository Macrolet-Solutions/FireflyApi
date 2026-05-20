"""JSON configuration loading per §13 of the specification.

Resolution order (per §13):

1. ``--config <path>`` command-line argument, if supplied.
2. The default path ``./config/firefly-appsettings.json`` relative to the
   process working directory.

If neither produces a readable file the loader raises ``SystemExit(2)`` with a
clear stderr message. Environment variables are not consulted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = Path("config") / "firefly-appsettings.json"


class DatabaseConfig(BaseModel):
    url: str


class FireflyConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    firefly_interface_version: str
    ack_timeout_ms: int = Field(default=7000, alias="ackTimeoutMs")
    ack_max_retries: int = Field(default=3, alias="ackMaxRetries")
    keepalive_disconnect_after_seconds: int = Field(
        default=300, alias="keepaliveDisconnectAfterSeconds"
    )


class EventsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    retention_days: int = Field(default=30, alias="retentionDays")


class FrontendConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    static_files_path: str = Field(default="./frontend/dist", alias="staticFilesPath")


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    level: str = "INFO"


class AppConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database: DatabaseConfig
    firefly: FireflyConfig
    events: EventsConfig = EventsConfig()
    frontend: FrontendConfig = FrontendConfig()
    server: ServerConfig = ServerConfig()
    logging: LoggingConfig = LoggingConfig()
    firefly_upd_file_path: str | None = Field(default=None, alias="fireflyUpdFilePath")


def _resolve_path(explicit: str | Path | None) -> Path:
    if explicit is not None:
        candidate = Path(explicit)
        if not candidate.is_file():
            print(f"Config file not found: {candidate}", file=sys.stderr)
            raise SystemExit(2)
        return candidate

    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH

    print(
        f"No --config supplied and default path {DEFAULT_CONFIG_PATH} does not exist.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate the application configuration JSON file.

    ``path`` may be a ``str`` or ``Path`` pointing at an explicit config file,
    or ``None`` to use the default search path described in §13.
    """
    resolved = _resolve_path(path)
    with resolved.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    return AppConfig.model_validate(data)
