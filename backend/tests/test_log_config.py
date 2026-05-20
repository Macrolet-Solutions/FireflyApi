"""Tests for application file logging."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.core.config import LoggingConfig
from firefly_api.core.log_config import append_daily_log_line, configure_logging
from firefly_api.main import create_app


def _make_client(app_config, session_factory: sessionmaker[Session]) -> TestClient:
    app = create_app(app_config)
    app.state.session_factory = session_factory
    return TestClient(app)


def test_configure_logging_writes_daily_log_file(
    app_config, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    app_config.logging = LoggingConfig(level="INFO", folder=str(tmp_path))
    configure_logging(app_config, force=True)

    with _make_client(app_config, session_factory) as client:
        r = client.get("/api/v1/admin/mqtt-brokers")

    assert r.status_code == 200
    log_file = tmp_path / f"log_{datetime.now():%Y%m%d}.txt"
    text = log_file.read_text(encoding="utf-8")
    assert "GET /api/v1/admin/mqtt-brokers -> 200" in text


def test_relative_log_folder_resolves_under_current_working_directory(
    app_config, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app_config.logging = LoggingConfig(level="INFO", folder="./AppLogs")

    configure_logging(app_config, force=True)

    expected = tmp_path / "AppLogs" / f"log_{datetime.now():%Y%m%d}.txt"
    assert expected.is_file()


def test_api_calls_are_logged_even_when_app_level_is_warning(
    app_config, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    app_config.logging = LoggingConfig(level="WARNING", folder=str(tmp_path))
    configure_logging(app_config, force=True)

    with _make_client(app_config, session_factory) as client:
        r = client.get("/api/v1/admin/mqtt-brokers")

    assert r.status_code == 200
    log_file = tmp_path / f"log_{datetime.now():%Y%m%d}.txt"
    text = log_file.read_text(encoding="utf-8")
    assert "GET /api/v1/admin/mqtt-brokers -> 200" in text


def test_direct_daily_append_writes_access_line(tmp_path: Path) -> None:
    append_daily_log_line(
        tmp_path,
        "firefly_api.access",
        "INFO",
        "GET /direct-file -> 200 1.00ms client=testclient",
    )

    log_file = tmp_path / f"log_{datetime.now():%Y%m%d}.txt"
    text = log_file.read_text(encoding="utf-8")
    assert "INFO [firefly_api.access] GET /direct-file -> 200" in text