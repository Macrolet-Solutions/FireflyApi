"""Tests for the optional frontend static-files mount (§10, Phase 5).

When ``frontend.staticFilesPath`` points at a real directory, the app
serves the SPA at ``/`` with a catch-all fallback for client-side routes.
When the path is missing, the mount is a silent no-op and only the API
routes are served.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.core.config import (
    AppConfig,
    DatabaseConfig,
    FireflyConfig,
    FrontendConfig,
)
from firefly_api.main import create_app


@pytest.fixture
def bundled_frontend(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><html><body><h1>Firefly</h1></body></html>",
        encoding="utf-8",
    )
    (dist / "logo-firefly.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "index-abc.js").write_text("console.log('hi');", encoding="utf-8")
    return dist


def _make_client(
    session_factory: sessionmaker[Session],
    dist: Path | None,
) -> TestClient:
    cfg = AppConfig(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        firefly=FireflyConfig(firefly_interface_version="v01.04"),
        frontend=FrontendConfig(
            static_files_path=str(dist) if dist else "/nope/does/not/exist"
        ),
    )
    app = create_app(cfg)
    # Reuse the test engine via the conftest session factory.
    app.state.session_factory = session_factory
    return TestClient(app)


def test_root_serves_index_when_bundle_present(
    session_factory: sessionmaker[Session], bundled_frontend: Path
) -> None:
    with _make_client(session_factory, bundled_frontend) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert "<h1>Firefly</h1>" in r.text


def test_logo_served_when_bundle_present(
    session_factory: sessionmaker[Session], bundled_frontend: Path
) -> None:
    with _make_client(session_factory, bundled_frontend) as client:
        r = client.get("/logo-firefly.png")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_assets_served_when_bundle_present(
    session_factory: sessionmaker[Session], bundled_frontend: Path
) -> None:
    with _make_client(session_factory, bundled_frontend) as client:
        r = client.get("/assets/index-abc.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_spa_fallback_serves_index_for_client_route(
    session_factory: sessionmaker[Session], bundled_frontend: Path
) -> None:
    with _make_client(session_factory, bundled_frontend) as client:
        r = client.get("/devices/42")
    assert r.status_code == 200
    assert "<h1>Firefly</h1>" in r.text


def test_unknown_api_route_still_404s_with_envelope(
    session_factory: sessionmaker[Session], bundled_frontend: Path
) -> None:
    with _make_client(session_factory, bundled_frontend) as client:
        r = client.get("/api/v1/admin/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) >= {"errorCode", "errorDescription", "details"}


def test_admin_api_still_works_alongside_mount(
    session_factory: sessionmaker[Session], bundled_frontend: Path
) -> None:
    with _make_client(session_factory, bundled_frontend) as client:
        r = client.get("/api/v1/admin/mqtt-brokers")
    assert r.status_code == 200
    assert r.json() == []


def test_no_mount_when_path_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with _make_client(session_factory, None) as client:
        r = client.get("/")
    assert r.status_code == 404
