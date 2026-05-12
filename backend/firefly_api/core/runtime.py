"""Actor runtime startup / shutdown (§11 steps 4-9).

``start_runtime`` runs steps 4-9 of the startup sequence: load the broker
row, connect MQTT, start the registry (which spawns one actor per
configured device and subscribes to the relevant topics), launch the
daily retention job, and build the :class:`FireflyService` used by the
HTTP layer. ``stop_runtime`` reverses these in the order required by §11.

The app factory in :mod:`firefly_api.main` deliberately does **not** call
this so that admin CRUD remains exercisable without MQTT (for tests and
the not-configured-broker startup path of §11).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from firefly_api.core.config import AppConfig
from firefly_api.db.models import MqttBroker
from firefly_api.firefly.actors import ActorRegistry, RuntimeSettings
from firefly_api.firefly.events import DbEventLog
from firefly_api.firefly.mqtt import MqttClient
from firefly_api.firefly.mqtt.client import PahoMqttClient
from firefly_api.firefly.retention import RetentionJob
from firefly_api.firefly.service import FireflyService

logger = logging.getLogger(__name__)


def _runtime_settings_from(config: AppConfig) -> RuntimeSettings:
    return RuntimeSettings(
        firefly_interface_version=config.firefly.firefly_interface_version,
        ack_timeout_ms=config.firefly.ack_timeout_ms,
        ack_max_retries=config.firefly.ack_max_retries,
        keepalive_disconnect_after_seconds=float(
            config.firefly.keepalive_disconnect_after_seconds
        ),
    )


def _build_mqtt_client(broker: MqttBroker) -> MqttClient:
    return PahoMqttClient(
        host=broker.host,
        port=broker.port,
        username=broker.username,
        password=broker.password,
        use_tls=broker.use_tls,
        client_id=broker.client_id,
    )


def start_runtime(app: FastAPI, config: AppConfig) -> None:
    """Wire the actor runtime onto ``app.state`` (idempotent-safe).

    If no broker row exists, this is a no-op (the not-configured startup
    path of §11) so the admin UI can still create one. After creating /
    changing the broker, the operator must restart the backend.
    """
    factory = app.state.session_factory
    with factory() as db:
        broker = db.scalar(select(MqttBroker).limit(1))

    if broker is None:
        logger.warning(
            "No MQTT broker is configured. Backend will serve admin CRUD only; "
            "create a broker via the admin API and restart to enable the actor "
            "runtime."
        )
        return

    settings = _runtime_settings_from(config)
    mqtt_client = _build_mqtt_client(broker)
    mqtt_client.connect()

    event_log = DbEventLog(factory)
    registry = ActorRegistry(
        mqtt_client=mqtt_client,
        session_factory=factory,
        settings=settings,
        event_log=event_log,
    )
    registry.start_all()

    retention_job = RetentionJob(
        factory, retention_days=config.events.retention_days
    )
    retention_job.start()

    service = FireflyService(
        registry=registry, session_factory=factory, settings=settings
    )

    app.state.mqtt_client = mqtt_client
    app.state.registry = registry
    app.state.retention_job = retention_job
    app.state.firefly_service = service


def stop_runtime(app: FastAPI) -> None:
    """Reverse of :func:`start_runtime` (§11 shutdown order)."""
    retention_job: RetentionJob | None = getattr(app.state, "retention_job", None)
    registry: ActorRegistry | None = getattr(app.state, "registry", None)
    mqtt_client: MqttClient | None = getattr(app.state, "mqtt_client", None)

    if retention_job is not None:
        try:
            retention_job.stop()
        except Exception:  # noqa: BLE001
            logger.exception("Error stopping retention job")
    if registry is not None:
        try:
            registry.stop_all()
        except Exception:  # noqa: BLE001
            logger.exception("Error stopping actor registry")
    if mqtt_client is not None:
        try:
            mqtt_client.disconnect()
        except Exception:  # noqa: BLE001
            logger.exception("Error disconnecting MQTT client")

    app.state.firefly_service = None
    app.state.registry = None
    app.state.retention_job = None
    app.state.mqtt_client = None


__all__ = ["start_runtime", "stop_runtime"]
