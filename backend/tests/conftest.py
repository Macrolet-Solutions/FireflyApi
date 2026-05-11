"""Shared fixtures for repository and route tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from firefly_api.core.config import (
    AppConfig,
    DatabaseConfig,
    FireflyConfig,
)
from firefly_api.db.models import Base
from firefly_api.main import create_app


def _make_test_engine() -> Engine:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    eng = _make_test_engine()
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        firefly=FireflyConfig(firefly_interface_version="v01.04"),
    )


@pytest.fixture
def client(
    app_config: AppConfig,
    session_factory: sessionmaker[Session],
) -> Generator[TestClient, None, None]:
    """A TestClient backed by the shared in-memory engine.

    ``create_app`` constructs its own engine from ``app_config.database.url``
    but we immediately overwrite ``session_factory`` on app.state so every
    HTTP request runs against the test engine fixture instead.
    """
    app = create_app(app_config)
    app.state.session_factory = session_factory
    with TestClient(app) as c:
        yield c


@pytest.fixture
def broker(client: TestClient) -> dict:
    r = client.post(
        "/api/v1/admin/mqtt-brokers",
        json={
            "name": "default",
            "host": "localhost",
            "port": 1883,
            "username": "user",
            "password": "secret",
            "use_tls": False,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def device(client: TestClient, broker: dict) -> dict:
    r = client.post(
        "/api/v1/admin/fireflies",
        json={"name": "FF01", "mqtt_broker_id": broker["id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def segment(client: TestClient, device: dict) -> dict:
    r = client.post(
        f"/api/v1/admin/fireflies/{device['id']}/segments",
        json={
            "channel_num": 1,
            "segment_num_in_channel": 1,
            "first_led_index": 1,
            "last_led_index": 150,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def led_state(client: TestClient) -> dict:
    r = client.post(
        "/api/v1/admin/led-states",
        json={"name": "NEEDS-ATTENTION", "rgb": "0xFF8000"},
    )
    assert r.status_code == 201, r.text
    return r.json()
