"""HTTP tests for the §8 public API and §9 admin actions.

These tests wire a real :class:`ActorRegistry` and :class:`FireflyService`
onto the test app, using an :class:`AutoAckingMqttClient` so that every
outbound MQTT command auto-receives an ACK. Together with the actor's
threading-based timers, this lets us drive the full HTTP -> service ->
actor -> publish -> ACK -> future-resolution path through a synchronous
TestClient call.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any

import pykka
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.firefly.actors import ActorRegistry, RuntimeSettings
from firefly_api.firefly.service import FireflyService
from tests.firefly_helpers import AutoAckingMqttClient


VERSION = "v01.04"


# ----------------------------------------------------------------- fixtures ----


@pytest.fixture(autouse=True)
def _stop_pykka_actors() -> Generator[None, None, None]:
    yield
    pykka.ActorRegistry.stop_all(block=True, timeout=2.0)


@pytest.fixture
def settings() -> RuntimeSettings:
    return RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=200,
        ack_max_retries=1,
        keepalive_disconnect_after_seconds=60.0,
    )


@pytest.fixture
def seeded(
    client: TestClient,
    broker: dict,
    device: dict,
    segment: dict,
    led_state: dict,
) -> dict:
    """Seed a typical device with one slot and one LED state."""
    slot = client.post(
        f"/api/v1/admin/fireflies/{device['id']}/slots",
        json={
            "segment_id": segment["id"],
            "external_slot_id": "S-001",
            "segment_position": 1,
            "num_leds": 10,
        },
    ).json()
    dynamic_segment = client.post(
        f"/api/v1/admin/fireflies/{device['id']}/segments",
        json={
            "channel_num": 2,
            "segment_num_in_channel": 1,
            "first_led_index": 1,
            "last_led_index": 100,
            "mode": "dynamic",
        },
    ).json()
    return {
        "broker": broker,
        "device": device,
        "segment": segment,
        "dynamic_segment": dynamic_segment,
        "led_state": led_state,
        "slot": slot,
    }


@pytest.fixture
def runtime(
    client: TestClient,
    seeded: dict,  # noqa: ARG001 (forces device existence before runtime starts)
    session_factory: sessionmaker[Session],
    settings: RuntimeSettings,
) -> Generator[dict[str, Any], None, None]:
    """Install a real registry + service onto the test app's state."""
    mqtt = AutoAckingMqttClient(VERSION)
    registry = ActorRegistry(
        mqtt_client=mqtt, session_factory=session_factory, settings=settings
    )
    registry.start_all()
    service = FireflyService(
        registry=registry, session_factory=session_factory, settings=settings
    )
    client.app.state.firefly_service = service
    client.app.state.registry = registry
    client.app.state.mqtt_client = mqtt
    # Wait for the boot init-slots ACK to land before the test runs.
    _wait_until(
        lambda: registry.get_actor(seeded["device"]["name"])
        .ask({"type": "get_snapshot"}, timeout=2.0)["status"]
        == "online"
    )
    try:
        yield {"registry": registry, "mqtt": mqtt, "service": service}
    finally:
        registry.stop_all()
        client.app.state.firefly_service = None
        client.app.state.registry = None
        client.app.state.mqtt_client = None


def _wait_until(predicate, timeout_s: float = 3.0, interval: float = 0.01) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("Timed out waiting for predicate.")


# ----------------------------------------------------- public endpoints ----


def test_update_firefly_slots_happy_path(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "S-001",
                    "stateName": seeded["led_state"]["name"],
                    "pattern": "slot_ends",
                    "patternValue": 5,
                }
            ],
            "clientRequestId": "client-123",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deviceName"] == seeded["device"]["name"]
    assert body["status"] == "updated"
    assert body["eventId"]
    assert body["currentTaskId"]
    assert body["clientRequestId"] == "client-123"


def test_update_firefly_slots_unknown_external_slot_id(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "DOES-NOT-EXIST",
                    "stateName": seeded["led_state"]["name"],
                }
            ]
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "invalid_external_slot_id"


def test_update_firefly_slots_unknown_state(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {"externalSlotId": "S-001", "stateName": "NOT-A-STATE"}
            ]
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "invalid_state_name"


def test_update_firefly_slots_invalid_pattern_name(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "S-001",
                    "stateName": seeded["led_state"]["name"],
                    "pattern": "blink_fast",
                }
            ]
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "invalid_pattern"


def test_update_firefly_slots_unknown_device(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        "/api/v1/public/fireflies/FF99/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "S-001",
                    "stateName": seeded["led_state"]["name"],
                }
            ]
        },
    )
    assert r.status_code == 404
    assert r.json()["errorCode"] == "device_not_found"


def test_update_all_slots_happy_path(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update-all",
        json={
            "stateName": seeded["led_state"]["name"],
            "pattern": "full",
            "patternValue": 0,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "updated"


def test_get_device_status_returns_online_after_boot(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.get(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/status"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deviceName"] == seeded["device"]["name"]
    assert body["status"] == "online"
    assert body["currentTaskId"]


def test_load_slots_dynamic_segment_refreshes_init_slots_and_update_mapping(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/load-slots",
        json={
            "segments": [
                {
                    "channelNum": 2,
                    "segmentNumInChannel": 1,
                    "slots": [
                        {"externalSlotId": "BOX-001", "numLeds": 12},
                        {"externalSlotId": "BOX-002", "numLeds": 18},
                    ],
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "loaded"

    slots_resp = client.get(f"/api/v1/admin/fireflies/{seeded['device']['id']}/slots")
    assert slots_resp.status_code == 200, slots_resp.text
    slots = slots_resp.json()
    assert [(slot["external_slot_id"], slot["slot_index"]) for slot in slots] == [
        ("S-001", 1),
        ("BOX-001", 2),
        ("BOX-002", 3),
    ]
    assert [
        slot["segment_position"]
        for slot in slots
        if slot["external_slot_id"].startswith("BOX")
    ] == [1, 2]
    assert all(
        slot["label"] == slot["external_slot_id"]
        for slot in slots
        if slot["external_slot_id"].startswith("BOX")
    )

    init_payload = runtime["mqtt"].last_payload("/init-slots")
    assert init_payload["num-slots"] == 3
    assert init_payload["slots"][-2:] == [
        {
            "slot-inx": 2,
            "channel": 2,
            "ch-segm": 1,
            "pos-in-segm": 1,
            "num-leds": 12,
        },
        {
            "slot-inx": 3,
            "channel": 2,
            "ch-segm": 1,
            "pos-in-segm": 2,
            "num-leds": 18,
        },
    ]

    update_resp = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "BOX-002",
                    "stateName": seeded["led_state"]["name"],
                }
            ]
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    update_payload = runtime["mqtt"].last_payload("/update-slot-state")
    assert update_payload["slots"][0]["slot-inx"] == 3


def test_load_slots_empty_slots_clears_dynamic_segment(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r_load = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/load-slots",
        json={
            "segments": [
                {
                    "channelNum": 2,
                    "segmentNumInChannel": 1,
                    "slots": [{"externalSlotId": "BOX-001", "numLeds": 12}],
                }
            ]
        },
    )
    assert r_load.status_code == 200, r_load.text

    r_clear = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/load-slots",
        json={
            "segments": [
                {
                    "channelNum": 2,
                    "segmentNumInChannel": 1,
                    "slots": [],
                }
            ]
        },
    )
    assert r_clear.status_code == 200, r_clear.text

    slots_resp = client.get(f"/api/v1/admin/fireflies/{seeded['device']['id']}/slots")
    assert slots_resp.status_code == 200, slots_resp.text
    assert [slot["external_slot_id"] for slot in slots_resp.json()] == ["S-001"]
    assert runtime["mqtt"].last_payload("/init-slots")["num-slots"] == 1

    update_resp = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "BOX-001",
                    "stateName": seeded["led_state"]["name"],
                }
            ]
        },
    )
    assert update_resp.status_code == 422
    assert update_resp.json()["errorCode"] == "invalid_external_slot_id"


def test_load_slots_rejects_static_segment(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/load-slots",
        json={
            "segments": [
                {
                    "channelNum": 1,
                    "segmentNumInChannel": 1,
                    "slots": [{"externalSlotId": "BOX-001", "numLeds": 12}],
                }
            ]
        },
    )
    assert r.status_code == 422
    assert r.json()["errorCode"] == "dynamic_slot_layout_invalid"


# ------------------------------------------------ admin command endpoints ----


def test_reinitialize_happy_path(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:reinitialize",
        json={"timeoutMs": 500},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deviceId"] == seeded["device"]["id"]
    assert body["status"] == "reinitialized"
    assert body["currentTaskId"]


def test_reset_publishes_and_returns(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:reset",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reset_published"
    assert body["eventId"]
    mqtt = runtime["mqtt"]
    assert any(t.endswith("/reset") for t in mqtt.topics())


def test_slots_test_admin_endpoint(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}/slots:test",
        json={
            "slots": [
                {
                    "slotId": seeded["slot"]["id"],
                    "stateName": seeded["led_state"]["name"],
                    "pattern": "full",
                }
            ],
            "timeoutMs": 200,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "updated"
    assert body["deviceName"] == seeded["device"]["name"]
    # clientRequestId is not part of the admin shape.
    assert "clientRequestId" not in body


# ------------------------------------------------ actor lifecycle endpoints ----


def test_start_actor_already_running(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:start-actor",
    )
    assert r.status_code == 200, r.text
    assert r.json()["actorStatus"] == "already_running"


def test_stop_then_start_actor(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:stop-actor",
    )
    assert r.status_code == 200, r.text
    assert r.json()["actorStatus"] == "stopped"

    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:start-actor",
    )
    assert r.status_code == 200, r.text
    assert r.json()["actorStatus"] == "started"


def test_stop_actor_idempotent(
    client: TestClient, seeded: dict, runtime: dict[str, Any]
) -> None:
    client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:stop-actor",
    )
    r = client.post(
        f"/api/v1/admin/fireflies/{seeded['device']['id']}:stop-actor",
    )
    assert r.status_code == 200
    assert r.json()["actorStatus"] == "already_stopped"


# ------------------------------------------------ runtime-not-started guard ----


def test_public_endpoint_when_runtime_not_started(
    client: TestClient, seeded: dict
) -> None:
    """Without a runtime installed, public endpoints return 503."""
    r = client.post(
        f"/api/v1/public/fireflies/{seeded['device']['name']}/slots:update",
        json={
            "slots": [
                {
                    "externalSlotId": "S-001",
                    "stateName": seeded["led_state"]["name"],
                }
            ]
        },
    )
    assert r.status_code == 503
    assert r.json()["errorCode"] == "runtime_not_started"


# ------------------------------------------------ broker test-connection ----


def test_broker_test_connection_unreachable_returns_502(
    client: TestClient, broker: dict
) -> None:
    # Force the broker to point at an unreachable port. We use 127.0.0.1:1
    # so no real network call leaves the box; paho will fail quickly.
    client.put(
        f"/api/v1/admin/mqtt-brokers/{broker['id']}",
        json={**broker, "host": "127.0.0.1", "port": 1, "password": None},
    )
    r = client.post(
        f"/api/v1/admin/mqtt-brokers/{broker['id']}:test-connection",
    )
    assert r.status_code == 502, r.text
    body = r.json()
    assert body["brokerId"] == broker["id"]
    assert body["success"] is False
    assert body["errorCode"] in {"broker_unreachable", "broker_protocol_error"}
