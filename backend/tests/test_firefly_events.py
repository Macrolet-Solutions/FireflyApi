"""Tests for ``firefly_api.firefly.events`` (§7.7).

Covers:

- The in-memory event-log fake captures records as expected.
- :class:`DbEventLog` writes rows that round-trip through SQLAlchemy.
- The actor emits the spec's event types at the right lifecycle moments.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import Future
from typing import Any

import pykka
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import FireflyEvent
from firefly_api.firefly.actors import (
    DeviceConfig,
    FireflyDeviceActor,
    RuntimeSettings,
)
from firefly_api.firefly.events import (
    DbEventLog,
    EventRecord,
    EventType,
    InMemoryEventLog,
)
from firefly_api.firefly.protocol import (
    ERROR_TASK_ID_MISMATCH,
    InitSlotsSlot,
    LedStateOut,
    RegistrationRequestIn,
    SegmentOut,
    UpdateSlotStateSlot,
)


VERSION = "v01.04"
DEVICE = "FF01"


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, payload))

    def last(self, suffix: str) -> dict[str, Any]:
        for t, p in reversed(self.published):
            if t.endswith(suffix):
                return json.loads(p.decode("utf-8"))
        raise AssertionError(f"no publish for suffix {suffix!r}")


@pytest.fixture(autouse=True)
def _stop_pykka_actors() -> Any:
    yield
    pykka.ActorRegistry.stop_all(block=True, timeout=2.0)


@pytest.fixture
def settings() -> RuntimeSettings:
    return RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=50,
        ack_max_retries=1,
        keepalive_disconnect_after_seconds=60.0,
    )


def _make_config(*, with_slots: bool = True, with_states: bool = True) -> DeviceConfig:
    return DeviceConfig(
        device_id=42,
        device_name=DEVICE,
        init_slots=(
            (
                InitSlotsSlot(slot_inx=1, channel=1, ch_segm=1, pos_in_segm=1, num_leds=10),
            )
            if with_slots
            else ()
        ),
        registration_segments=(
            SegmentOut(channel=1, ch_segm=1, first_led_inx=1, last_led_inx=150),
        ),
        registration_states=(
            (LedStateOut(name="OFF", rgb="0x000000"),) if with_states else ()
        ),
    )


def _wait_until(predicate, timeout_s: float = 2.0, interval: float = 0.01) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("Timed out waiting for predicate.")


# ----------------------------------------------------------------- DbEventLog ----


def test_db_event_log_persists_records(
    session_factory: sessionmaker[Session], device: dict
) -> None:
    log = DbEventLog(session_factory)
    log.record(
        EventRecord(
            device_id=device["id"],
            event_id="00000000-0000-0000-0000-000000000001",
            event_type=EventType.INIT_SLOTS_SENT,
            task_id="task-1",
            payload_json={"num-slots": 0},
        )
    )
    log.record(
        EventRecord(
            device_id=device["id"],
            event_id="00000000-0000-0000-0000-000000000002",
            event_type=EventType.ACK_RECEIVED,
            payload_json={"event-id": "00000000-0000-0000-0000-000000000001"},
        )
    )
    with session_factory() as db:
        rows = (
            db.scalars(
                select(FireflyEvent)
                .where(FireflyEvent.device_id == device["id"])
                .order_by(FireflyEvent.id)
            )
            .all()
        )
    assert [r.event_type for r in rows] == [
        EventType.INIT_SLOTS_SENT,
        EventType.ACK_RECEIVED,
    ]
    assert rows[0].task_id == "task-1"
    assert rows[0].payload_json == {"num-slots": 0}


# ----------------------------------------------------------------- actor wiring ----


def test_actor_emits_init_slots_sent_on_boot(settings: RuntimeSettings) -> None:
    publisher = FakePublisher()
    log = InMemoryEventLog()
    FireflyDeviceActor.start(
        config=_make_config(),
        settings=settings,
        publisher=publisher,
        event_log=log,
    )
    _wait_until(lambda: EventType.INIT_SLOTS_SENT in log.types_for(42))
    types = log.types_for(42)
    # The boot ACK timeout is short, so we may also see RETRY/TIMEOUT
    # rows; we only care that INIT_SLOTS_SENT is first.
    assert types[0] == EventType.INIT_SLOTS_SENT


def test_actor_logs_full_registration_flow(settings: RuntimeSettings) -> None:
    publisher = FakePublisher()
    log = InMemoryEventLog()
    cfg = _make_config(with_slots=False)  # avoid the boot init-slots noise
    ref = FireflyDeviceActor.start(
        config=cfg, settings=settings, publisher=publisher, event_log=log
    )

    ref.tell(
        {
            "type": "register_request",
            "request": RegistrationRequestIn(
                firmware_version="1.2.3", device_id=DEVICE, device_mac="AABBCCDDEEFF"
            ),
            "request_version": VERSION,
        }
    )
    _wait_until(lambda: EventType.REGISTER_RESPONSE_SENT in log.types_for(42))
    resp_event_id = publisher.last("/register-resp")["event-id"]
    ref.tell({"type": "ack", "event_id": resp_event_id})

    _wait_until(
        lambda: log.types_for(42).count(EventType.ACK_RECEIVED) >= 1
    )
    types = log.types_for(42)
    assert types[0] == EventType.REGISTER_REQUEST_RECEIVED
    assert types[1] == EventType.REGISTER_RESPONSE_SENT
    assert EventType.ACK_RECEIVED in types


def test_actor_logs_retry_and_timeout(settings: RuntimeSettings) -> None:
    publisher = FakePublisher()
    log = InMemoryEventLog()
    FireflyDeviceActor.start(
        config=_make_config(),
        settings=settings,
        publisher=publisher,
        event_log=log,
    )
    # No ACK arrives; with ack_max_retries=1 we get one initial publish, one
    # retry, then a timeout row.
    _wait_until(lambda: EventType.TIMEOUT in log.types_for(42), timeout_s=2.0)
    types = log.types_for(42)
    assert types.count(EventType.INIT_SLOTS_SENT) == 1
    assert types.count(EventType.RETRY) == 1
    assert types.count(EventType.TIMEOUT) == 1


def test_actor_logs_error_received_and_task_id_recovery(
    settings: RuntimeSettings,
) -> None:
    publisher = FakePublisher()
    log = InMemoryEventLog()
    ref = FireflyDeviceActor.start(
        config=_make_config(),
        settings=settings,
        publisher=publisher,
        event_log=log,
    )
    _wait_until(lambda: EventType.INIT_SLOTS_SENT in log.types_for(42))
    init_event = publisher.last("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: EventType.ACK_RECEIVED in log.types_for(42))

    future: Future = Future()
    ref.tell(
        {
            "type": "submit_update_slot_state",
            "slots": [UpdateSlotStateSlot(slot_inx=1, to_state="OFF")],
            "timeout_ms": 500,
            "result_future": future,
        }
    )
    _wait_until(lambda: EventType.UPDATE_SLOT_STATE_SENT in log.types_for(42))
    update_event = publisher.last("/update-slot-state")["event-id"]

    ref.tell(
        {
            "type": "error",
            "event_id": update_event,
            "error_code": ERROR_TASK_ID_MISMATCH,
            "error_descr": "wrong",
        }
    )

    _wait_until(lambda: EventType.ERROR_RECEIVED in log.types_for(42))
    # After the recovery, the actor publishes a fresh init-slots.
    _wait_until(
        lambda: log.types_for(42).count(EventType.INIT_SLOTS_SENT) >= 2
    )
    err_rows = [r for r in log.records if r.event_type == EventType.ERROR_RECEIVED]
    assert err_rows[0].error_code == ERROR_TASK_ID_MISMATCH


def test_actor_logs_reset_sent(settings: RuntimeSettings) -> None:
    publisher = FakePublisher()
    log = InMemoryEventLog()
    cfg = _make_config(with_slots=False)
    ref = FireflyDeviceActor.start(
        config=cfg, settings=settings, publisher=publisher, event_log=log
    )
    fut: Future = Future()
    ref.tell({"type": "reset", "result_future": fut})
    fut.result(timeout=1.0)
    assert EventType.RESET_SENT in log.types_for(42)


def test_actor_logs_keepalive_received(settings: RuntimeSettings) -> None:
    publisher = FakePublisher()
    log = InMemoryEventLog()
    cfg = _make_config(with_slots=False)
    ref = FireflyDeviceActor.start(
        config=cfg, settings=settings, publisher=publisher, event_log=log
    )
    ref.tell({"type": "keepalive"})
    _wait_until(lambda: EventType.KEEPALIVE_RECEIVED in log.types_for(42))
