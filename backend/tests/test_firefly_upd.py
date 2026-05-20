"""Tests for the legacy Firefly firmware update endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.core.config import AppConfig, DatabaseConfig, FireflyConfig
from firefly_api.main import create_app


def _make_client(
    session_factory: sessionmaker[Session], firmware_path: Path | None
) -> TestClient:
    cfg = AppConfig(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        firefly=FireflyConfig(firefly_interface_version="v01.04"),
        firefly_upd_file_path=str(firmware_path) if firmware_path else None,
    )
    app = create_app(cfg)
    app.state.session_factory = session_factory
    return TestClient(app)


def test_firefly_upd_serves_configured_firmware_file(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    firmware_path = tmp_path / "macrolet.cart.bin"
    firmware_path.write_bytes(b"firmware-bytes")

    with _make_client(session_factory, firmware_path) as client:
        r = client.get("/firefly_upd")

    assert r.status_code == 200
    assert r.content == b"firmware-bytes"
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'filename="macrolet.cart.bin"' in r.headers["content-disposition"]


def test_firefly_upd_returns_404_when_configured_file_is_missing(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    with _make_client(session_factory, tmp_path / "missing.bin") as client:
        r = client.get("/firefly_upd")

    assert r.status_code == 404
    assert r.content == b""


def test_firefly_upd_uses_legacy_default_path(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch
) -> None:
    firmware_path = tmp_path / "data" / "firefly_upd" / "macrolet.cart.bin"
    firmware_path.parent.mkdir(parents=True)
    firmware_path.write_bytes(b"default-firmware")
    monkeypatch.chdir(tmp_path)

    with _make_client(session_factory, None) as client:
        r = client.get("/firefly_upd")

    assert r.status_code == 200
    assert r.content == b"default-firmware"