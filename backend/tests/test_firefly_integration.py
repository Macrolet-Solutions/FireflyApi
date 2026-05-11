"""End-to-end-ish integration test for the actor runtime.

Wires together the actor registry, a fake MQTT client, and a real
:class:`DbEventLog` against an in-memory SQLite. Verifies a full
registration -> init-slots ACK lifecycle produces the expected
``firefly_events`` rows.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pykka
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import (
    FireflyDevice,
    FireflyEvent,
    FireflyLedState,
    FireflySegment,
    FireflySlot,
    MqttBroker,
)
from firefly_api.firefly.actors import ActorRegistry, ActorStatus, RuntimeSettings
from firefly_api.firefly.events import DbEventLog, EventType
from firefly_api.firefly.mqtt import InboundHandler
from firefly_api.firefly.protocol import (
    ack_topic,
    keepalive_topic,
)
from firefly_api.firefly.protocol.topics import register_request_topic


VERSION = "v01.04"


class FakeMqttClient:
    def __init__(self) -> None:
        self.subscriptions: list[str] = []
        self.publishes: list[tuple[str, bytes]] = []
        self._handler: InboundHandler | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def subscribe(self, topic: str) -> None:
        with self._lock:
            self.subscriptions.append(topic)

    def publish(self, topic: str, payload: bytes) -> None:
        with self._lock:
            self.publishes.append((topic, payload))

    def set_message_handler(self, handler: InboundHandler) -> None:
        self._handler = handler

    def inject(self, topic: str, payload: bytes) -> None:
        assert self._handler is not None
        self._handler(topic, payload)

    def last_for(self, device_name: str, suffix: str) -> dict[str, Any]:
        marker = f"/{device_name}/"
        for topic, raw in reversed(self.publishes):
            if marker in topic and topic.endswith(suffix):
                return json.loads(raw.decode("utf-8"))
        raise AssertionError(f"no publish for {device_name} suffix {suffix!r}")


@pytest.fixture(autouse=True)
def _stop_pykka_actors() -> Any:
    yield
    pykka.ActorRegistry.stop_all(block=True, timeout=2.0)


def _seed(db: Session) -> FireflyDevice:
    broker = MqttBroker(name="b", host="h", port=1883)
    db.add(broker)
    db.flush()
    state = FireflyLedState(name="OFF", rgb="0x000000")
    db.add(state)
    db.flush()
    device = FireflyDevice(name="FF01", mqtt_broker_id=broker.id)
    db.add(device)
    db.flush()
    seg = FireflySegment(
        device_id=device.id,
        channel_num=1,
        segment_num_in_channel=1,
        first_led_index=1,
        last_led_index=100,
    )
    db.add(seg)
    db.flush()
    db.add(
        FireflySlot(
            device_id=device.id,
            segment_id=seg.id,
            slot_index=1,
            external_slot_id="FF01-S1",
            segment_position=1,
            num_leds=10,
        )
    )
    db.commit()
    return device


def _wait_until(predicate, timeout_s: float = 2.0) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for predicate")


def test_full_registration_lifecycle_writes_expected_event_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        device = _seed(db)
        device_id = device.id

    settings = RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=200,
        ack_max_retries=0,
        keepalive_disconnect_after_seconds=60.0,
    )
    mqtt = FakeMqttClient()
    event_log = DbEventLog(session_factory)
    reg = ActorRegistry(
        mqtt_client=mqtt,
        session_factory=session_factory,
        settings=settings,
        event_log=event_log,
    )
    reg.start_all()
    try:
        # Boot publishes init-slots; ACK it.
        _wait_until(
            lambda: any(t.endswith("/init-slots") for t in [t for t, _ in mqtt.publishes])
        )
        init_event_id = mqtt.last_for("FF01", "/init-slots")["event-id"]

        ack_payload = json.dumps({"event-id": init_event_id}).encode()
        mqtt.inject(ack_topic(VERSION, "FF01"), ack_payload)

        actor = reg.get_actor("FF01")
        assert actor is not None
        _wait_until(
            lambda: actor.ask({"type": "get_snapshot"}, timeout=2.0)["status"]
            == ActorStatus.ONLINE.value
        )

        # Send a keepalive too.
        mqtt.inject(keepalive_topic(VERSION, "FF01"), b"{}")

        # Drive a fresh registration cycle.
        reg_payload = json.dumps(
            {
                "firmware-version": "1.0",
                "device-id": "FF01",
                "device-mac": "AABBCCDDEEFF",
            }
        ).encode()
        mqtt.inject(register_request_topic(VERSION), reg_payload)

        # Wait until the actor has processed both messages.
        _wait_until(
            lambda: actor.ask({"type": "get_snapshot"}, timeout=2.0)["firmware_version"]
            == "1.0"
        )

        # Give the DB writer a moment to flush.
        time.sleep(0.05)
    finally:
        reg.stop_all()

    with session_factory() as db:
        rows = (
            db.scalars(
                select(FireflyEvent)
                .where(FireflyEvent.device_id == device_id)
                .order_by(FireflyEvent.id)
            )
            .all()
        )
    types = [r.event_type for r in rows]
    assert EventType.INIT_SLOTS_SENT in types
    assert EventType.ACK_RECEIVED in types
    assert EventType.KEEPALIVE_RECEIVED in types
    assert EventType.REGISTER_REQUEST_RECEIVED in types
    assert EventType.REGISTER_RESPONSE_SENT in types

    # Every outbound row's event_id appears in payload_json under "event-id".
    for row in rows:
        if row.event_type.endswith("_sent"):
            assert row.payload_json is not None
            assert row.payload_json.get("event-id") == row.event_id
