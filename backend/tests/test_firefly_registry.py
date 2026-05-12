"""Tests for the actor registry (§5.1)."""

from __future__ import annotations

import json
import time
from typing import Any

import pykka
import pytest
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import (
    FireflyDevice,
    FireflyLedState,
    FireflySegment,
    FireflySlot,
    MqttBroker,
)
from firefly_api.firefly.actors import ActorRegistry, ActorStatus, RuntimeSettings
from firefly_api.firefly.protocol import (
    REGISTER_REQ_SUBSCRIPTION,
    ack_topic,
    error_topic,
    keepalive_topic,
)
from firefly_api.firefly.protocol.topics import register_request_topic
from tests.firefly_helpers import FakeMqttClient


VERSION = "v01.04"


# ----------------------------------------------------------------- fixtures ----


@pytest.fixture(autouse=True)
def _stop_pykka_actors() -> Any:
    yield
    pykka.ActorRegistry.stop_all(block=True, timeout=2.0)


@pytest.fixture
def settings() -> RuntimeSettings:
    return RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=50,
        ack_max_retries=0,
        keepalive_disconnect_after_seconds=60.0,
    )


def _seed_two_devices(db: Session) -> tuple[FireflyDevice, FireflyDevice]:
    broker = MqttBroker(name="b", host="h", port=1883)
    db.add(broker)
    db.flush()
    state = FireflyLedState(name="OFF", rgb="0x000000")
    db.add(state)
    db.flush()
    devices = []
    for name in ("FF01", "FF02"):
        device = FireflyDevice(name=name, mqtt_broker_id=broker.id)
        db.add(device)
        db.flush()
        segment = FireflySegment(
            device_id=device.id,
            channel_num=1,
            segment_num_in_channel=1,
            first_led_index=1,
            last_led_index=100,
        )
        db.add(segment)
        db.flush()
        db.add(
            FireflySlot(
                device_id=device.id,
                segment_id=segment.id,
                slot_index=1,
                external_slot_id=f"{name}-S1",
                segment_position=1,
                num_leds=10,
            )
        )
        devices.append(device)
    db.commit()
    return devices[0], devices[1]


@pytest.fixture
def registry(
    session_factory: sessionmaker[Session],
    settings: RuntimeSettings,
) -> tuple[ActorRegistry, FakeMqttClient]:
    mqtt = FakeMqttClient()
    reg = ActorRegistry(
        mqtt_client=mqtt, session_factory=session_factory, settings=settings
    )
    return reg, mqtt


def _wait_until(predicate, timeout_s: float = 2.0, interval: float = 0.01) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("Timed out waiting for predicate.")


def _snap(ref: pykka.ActorRef) -> dict[str, Any]:
    return ref.ask({"type": "get_snapshot"}, timeout=2.0)


# ----------------------------------------------------------------- tests ----


def test_start_all_subscribes_and_spawns_actors(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        assert REGISTER_REQ_SUBSCRIPTION in mqtt.subscriptions
        assert f"ptm/{VERSION}/+/ack" in mqtt.subscriptions
        assert f"ptm/{VERSION}/+/error" in mqtt.subscriptions
        assert f"ptm/{VERSION}/+/keepalive" in mqtt.subscriptions
        assert set(reg.device_names()) == {"FF01", "FF02"}
        # Each actor publishes an init-slots on boot.
        _wait_until(
            lambda: sum(1 for t in mqtt.topics() if t.endswith("/init-slots")) == 2
        )
    finally:
        reg.stop_all()


def test_register_request_dispatched_to_correct_actor(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        # Inject a register-req for FF02.
        payload = json.dumps(
            {
                "firmware-version": "1.0",
                "device-id": "FF02",
                "device-mac": "AABBCCDDEEFF",
            }
        ).encode("utf-8")
        mqtt.inject(register_request_topic(VERSION), payload)
        actor = reg.get_actor("FF02")
        assert actor is not None
        _wait_until(lambda: _snap(actor)["firmware_version"] == "1.0")
        # FF01 must not be affected.
        ff01 = reg.get_actor("FF01")
        assert ff01 is not None
        assert _snap(ff01)["firmware_version"] is None
    finally:
        reg.stop_all()


def test_register_request_for_unknown_device_is_ignored(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        payload = json.dumps(
            {
                "firmware-version": "1.0",
                "device-id": "FF99",
                "device-mac": "AABBCCDDEEFF",
            }
        ).encode("utf-8")
        # Should not raise even though FF99 is not configured.
        mqtt.inject(register_request_topic(VERSION), payload)
        # Existing devices unaffected.
        assert _snap(reg.get_actor("FF01"))["firmware_version"] is None
    finally:
        reg.stop_all()


def test_ack_routed_by_device_name_in_topic(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        # Wait for both init-slots publishes.
        _wait_until(
            lambda: sum(1 for t in mqtt.topics() if t.endswith("/init-slots")) >= 2
        )
        # Find the init-slots event_id for FF01.
        init_event_ids: dict[str, str] = {}
        for topic, raw in list(mqtt.published):
            if topic.endswith("/init-slots"):
                body = json.loads(raw)
                for name in ("FF01", "FF02"):
                    if f"/{name}/" in topic:
                        init_event_ids[name] = body["event-id"]
        assert "FF01" in init_event_ids

        # Send the ACK for FF01 only.
        ack_payload = json.dumps({"event-id": init_event_ids["FF01"]}).encode("utf-8")
        mqtt.inject(ack_topic(VERSION, "FF01"), ack_payload)

        _wait_until(
            lambda: _snap(reg.get_actor("FF01"))["status"] == ActorStatus.ONLINE.value
        )
        assert _snap(reg.get_actor("FF02"))["status"] != ActorStatus.ONLINE.value
    finally:
        reg.stop_all()


def test_error_routed_by_device_name(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        _wait_until(
            lambda: sum(1 for t in mqtt.topics() if t.endswith("/init-slots")) >= 2
        )
        # Find FF01's init-slots event_id.
        ff01_event: str | None = None
        for topic, raw in list(mqtt.published):
            if topic.endswith("/init-slots") and "/FF01/" in topic:
                ff01_event = json.loads(raw)["event-id"]
                break
        assert ff01_event is not None

        err_payload = json.dumps(
            {
                "event-id": ff01_event,
                "error-code": "GENERIC_ERR",
                "error-descr": "x",
            }
        ).encode("utf-8")
        mqtt.inject(error_topic(VERSION, "FF01"), err_payload)
        _wait_until(
            lambda: _snap(reg.get_actor("FF01"))["status"] == ActorStatus.OFFLINE.value
        )
    finally:
        reg.stop_all()


def test_keepalive_routed_by_device_name(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        # Empty payload — keepalive metrics are optional.
        mqtt.inject(keepalive_topic(VERSION, "FF01"), b"{}")
        actor = reg.get_actor("FF01")
        _wait_until(lambda: _snap(actor)["last_keepalive_at"] is not None)
    finally:
        reg.stop_all()


def test_malformed_payload_does_not_crash_registry(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        # Should be logged and ignored, not raised.
        mqtt.inject(ack_topic(VERSION, "FF01"), b"not-json")
        mqtt.inject(register_request_topic(VERSION), b"{}")
        # Registry still alive and responsive.
        assert reg.get_actor("FF01") is not None
    finally:
        reg.stop_all()


def test_unknown_topic_is_ignored(
    registry: tuple[ActorRegistry, FakeMqttClient],
    session_factory: sessionmaker[Session],
) -> None:
    reg, mqtt = registry
    with session_factory() as db:
        _seed_two_devices(db)
    reg.start_all()
    try:
        mqtt.inject("something/random", b"{}")
    finally:
        reg.stop_all()
