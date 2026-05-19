"""Runtime startup behavior around unavailable MQTT brokers."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from firefly_api.core.config import AppConfig
from firefly_api.core.runtime import start_runtime
from firefly_api.firefly.mqtt import InboundHandler


class FailingMqttClient:
    def __init__(self) -> None:
        self.disconnected = False

    def connect(self) -> None:
        raise TimeoutError("boom")

    def disconnect(self) -> None:
        self.disconnected = True

    def subscribe(self, topic: str) -> None:
        raise AssertionError(f"unexpected subscribe to {topic}")

    def set_message_handler(self, handler: InboundHandler) -> None:
        raise AssertionError(f"unexpected handler {handler}")

    def publish(self, topic: str, payload: bytes) -> None:
        raise AssertionError(f"unexpected publish to {topic}: {payload!r}")

    def is_connected(self) -> bool:
        return False


def test_start_runtime_leaves_admin_available_when_mqtt_connect_fails(
    client: TestClient,
    app_config: AppConfig,
    broker: dict,  # noqa: ARG001 (forces a broker row before startup)
    monkeypatch,
    caplog,
) -> None:
    mqtt = FailingMqttClient()
    monkeypatch.setattr(
        "firefly_api.core.runtime._build_mqtt_client", lambda _broker: mqtt
    )

    with caplog.at_level(logging.ERROR, logger="firefly_api.core.runtime"):
        start_runtime(client.app, app_config)

    assert mqtt.disconnected is True
    assert client.app.state.firefly_service is None
    assert client.app.state.registry is None
    assert client.app.state.retention_job is None
    assert client.app.state.mqtt_client is None
    assert "is not reachable" in caplog.text

    response = client.get("/api/v1/admin/mqtt-brokers")
    assert response.status_code == 200

    response = client.get("/api/v1/public/fireflies/FF01/status")
    assert response.status_code == 503
    assert response.json()["errorCode"] == "runtime_not_started"