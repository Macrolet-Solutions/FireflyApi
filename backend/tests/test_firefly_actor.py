"""Tests for the device actor state machine (§5.3, §5.4)."""

from __future__ import annotations

import time
from concurrent.futures import Future
from typing import Any

import pykka
import pytest

from firefly_api.firefly.actors import (
    ActorStatus,
    CommandFailure,
    CommandSuccess,
    DeviceConfig,
    FireflyDeviceActor,
    RuntimeSettings,
    StateMachine,
)
from firefly_api.firefly.protocol import (
    ERROR_TASK_ID_MISMATCH,
    InitSlotsSlot,
    LedStateOut,
    RegistrationRequestIn,
    SegmentOut,
    UpdateSlotStateSlot,
)
from tests.firefly_helpers import FakePublisher


VERSION = "v01.04"
DEVICE = "FF01"


# ----------------------------------------------------------------- fixtures ----


@pytest.fixture(autouse=True)
def _stop_pykka_actors() -> Any:
    yield
    pykka.ActorRegistry.stop_all(block=True, timeout=2.0)


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def settings() -> RuntimeSettings:
    # Fast timers for tests. ack_timeout_ms is intentionally short so timeout
    # tests don't sit waiting for seconds; keepalive watchdog is long enough
    # to not interfere with other tests.
    return RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=50,
        ack_max_retries=2,
        keepalive_disconnect_after_seconds=60.0,
    )


def _make_config(
    *,
    with_slots: bool = True,
    with_states: bool = True,
) -> DeviceConfig:
    return DeviceConfig(
        device_id=1,
        device_name=DEVICE,
        init_slots=(
            (
                InitSlotsSlot(
                    slot_inx=1,
                    channel=1,
                    ch_segm=1,
                    pos_in_segm=1,
                    num_leds=10,
                ),
                InitSlotsSlot(
                    slot_inx=2,
                    channel=1,
                    ch_segm=1,
                    pos_in_segm=11,
                    num_leds=10,
                ),
            )
            if with_slots
            else ()
        ),
        registration_segments=(
            SegmentOut(channel=1, ch_segm=1, first_led_inx=1, last_led_inx=150),
        ),
        registration_states=(
            (
                LedStateOut(name="OFF", rgb="0x000000"),
                LedStateOut(name="NEEDS-ATTENTION", rgb="0xFF8000"),
            )
            if with_states
            else ()
        ),
    )


def _start(
    publisher: FakePublisher,
    settings: RuntimeSettings,
    *,
    config: DeviceConfig | None = None,
) -> pykka.ActorRef:
    return FireflyDeviceActor.start(
        config=config or _make_config(),
        settings=settings,
        publisher=publisher,
    )


def _snap(ref: pykka.ActorRef) -> dict[str, Any]:
    return ref.ask({"type": "get_snapshot"}, timeout=2.0)


def _wait_until(predicate, timeout_s: float = 2.0, interval: float = 0.01) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("Timed out waiting for predicate to become true.")


# ----------------------------------------------------------------- tests ----


def test_boot_with_slots_publishes_init_slots(publisher: FakePublisher, settings: RuntimeSettings) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    payload = publisher.last_payload("/init-slots")
    assert payload["num-slots"] == 2
    assert "task-id" in payload
    assert "event-id" in payload
    snap = _snap(ref)
    assert snap["fsm"] == StateMachine.WAITING_ACK.value
    assert snap["status"] == ActorStatus.UNKNOWN.value
    assert snap["pending_command_type"] == "init_slots"


def test_boot_without_slots_stays_offline(publisher: FakePublisher, settings: RuntimeSettings) -> None:
    ref = _start(publisher, settings, config=_make_config(with_slots=False))
    # Give the actor a moment to "boot".
    time.sleep(0.02)
    assert publisher.topics() == []
    snap = _snap(ref)
    assert snap["fsm"] == StateMachine.OFFLINE.value
    assert snap["status"] == ActorStatus.UNKNOWN.value


def test_init_slots_ack_transitions_to_active_online(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    event_id = publisher.last_payload("/init-slots")["event-id"]
    task_id = publisher.last_payload("/init-slots")["task-id"]
    ref.tell({"type": "ack", "event_id": event_id})

    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)
    snap = _snap(ref)
    assert snap["fsm"] == StateMachine.ACTIVE.value
    assert snap["current_task_id"] == task_id
    assert snap["pending_command_type"] is None


def test_registration_flow_publishes_register_resp_then_init_slots(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    # Start without slots so boot doesn't publish init-slots; that way the
    # register-resp ACK is what kicks off init-slots.
    cfg = _make_config(with_slots=True)
    ref = _start(publisher, settings, config=cfg)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    publisher.clear()  # focus the assertions on the registration flow

    ref.tell(
        {
            "type": "register_request",
            "request": RegistrationRequestIn(
                firmware_version="1.2.3", device_id=DEVICE, device_mac="AABBCCDDEEFF"
            ),
            "request_version": VERSION,
        }
    )

    _wait_until(lambda: any("register-resp" in t for t in publisher.topics()))
    resp = publisher.last_payload("/register-resp")
    assert resp["is-error"] is False
    assert resp["device-type"] == "FireflyController"
    assert len(resp["segments"]) == 1
    assert len(resp["states"]) == 2

    # ACK the register-resp -> actor should publish init-slots next.
    ref.tell({"type": "ack", "event_id": resp["event-id"]})
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_payload = publisher.last_payload("/init-slots")
    ref.tell({"type": "ack", "event_id": init_payload["event-id"]})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)


def test_registration_version_mismatch_sets_register_error(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    publisher.clear()
    ref.tell(
        {
            "type": "register_request",
            "request": RegistrationRequestIn(
                firmware_version="1.2.3", device_id=DEVICE, device_mac="AABBCCDDEEFF"
            ),
            "request_version": "v99.99",
        }
    )
    _wait_until(lambda: any("register-resp" in t for t in publisher.topics()))
    resp = publisher.last_payload("/register-resp")
    assert resp["is-error"] is True
    assert "v99.99" in resp["error-descr"]
    snap = _snap(ref)
    assert snap["status"] == ActorStatus.REGISTER_ERROR.value
    assert snap["fsm"] == StateMachine.OFFLINE.value


def test_registration_with_no_led_states_sets_register_error(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    cfg = _make_config(with_states=False)
    ref = _start(publisher, settings, config=cfg)
    publisher.clear()
    ref.tell(
        {
            "type": "register_request",
            "request": RegistrationRequestIn(
                firmware_version="1.2.3", device_id=DEVICE, device_mac="AABBCCDDEEFF"
            ),
            "request_version": VERSION,
        }
    )
    _wait_until(lambda: any("register-resp" in t for t in publisher.topics()))
    resp = publisher.last_payload("/register-resp")
    assert resp["is-error"] is True
    assert "LED states" in resp["error-descr"]
    snap = _snap(ref)
    assert snap["status"] == ActorStatus.REGISTER_ERROR.value


def test_registration_preempts_in_flight_command(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    # We're now in waiting_ack for init_slots. Issue a register_request.
    publisher.clear()
    ref.tell(
        {
            "type": "register_request",
            "request": RegistrationRequestIn(
                firmware_version="1.2.4", device_id=DEVICE, device_mac="AABBCCDDEEFF"
            ),
            "request_version": VERSION,
        }
    )
    _wait_until(lambda: any("register-resp" in t for t in publisher.topics()))
    snap = _snap(ref)
    assert snap["pending_command_type"] == "register_response"
    assert snap["current_task_id"] is None


def test_command_timeout_retries_then_exhausts(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    # No ACK ever arrives. ack_timeout_ms = 50, ack_max_retries = 2, so
    # we expect 1 initial publish + 2 retries = 3 init-slots publishes,
    # then transition to offline.
    _wait_until(
        lambda: sum(1 for t in publisher.topics() if t.endswith("/init-slots")) >= 3,
        timeout_s=2.0,
    )
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.OFFLINE.value, timeout_s=2.0)
    snap = _snap(ref)
    assert snap["fsm"] == StateMachine.OFFLINE.value
    assert snap["pending_command_type"] is None


def test_submit_update_slot_state_then_ack_completes_future(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)

    future: Future = Future()
    ref.tell(
        {
            "type": "submit_update_slot_state",
            "slots": [
                UpdateSlotStateSlot(slot_inx=1, to_state="NEEDS-ATTENTION", pattern=1, pattern_value=10)
            ],
            "timeout_ms": 200,
            "result_future": future,
        }
    )
    _wait_until(lambda: any(t.endswith("/update-slot-state") for t in publisher.topics()))
    payload = publisher.last_payload("/update-slot-state")
    ref.tell({"type": "ack", "event_id": payload["event-id"]})

    result = future.result(timeout=2.0)
    assert isinstance(result, CommandSuccess)
    snap = _snap(ref)
    assert snap["fsm"] == StateMachine.ACTIVE.value
    assert snap["slot_states"][1]["to_state"] == "NEEDS-ATTENTION"
    assert snap["slot_states"][1]["pattern"] == 1


def test_submit_when_offline_fails_immediately(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    cfg = _make_config(with_slots=False)
    ref = _start(publisher, settings, config=cfg)
    future: Future = Future()
    ref.tell(
        {
            "type": "submit_update_slot_state",
            "slots": [UpdateSlotStateSlot(slot_inx=1, to_state="OFF")],
            "timeout_ms": 100,
            "result_future": future,
        }
    )
    result = future.result(timeout=1.0)
    assert isinstance(result, CommandFailure)
    assert result.error_code == "device_offline"


def test_task_id_recovery_error_reinitializes_slots(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)

    future: Future = Future()
    ref.tell(
        {
            "type": "submit_update_slot_state",
            "slots": [UpdateSlotStateSlot(slot_inx=1, to_state="OFF")],
            "timeout_ms": 200,
            "result_future": future,
        }
    )
    _wait_until(lambda: any(t.endswith("/update-slot-state") for t in publisher.topics()))
    update_event = publisher.last_payload("/update-slot-state")["event-id"]
    publisher.clear()

    # Device replies with task_id mismatch.
    ref.tell(
        {
            "type": "error",
            "event_id": update_event,
            "error_code": ERROR_TASK_ID_MISMATCH,
            "error_descr": "",
        }
    )

    # The original future must fail, and the actor must publish init-slots.
    result = future.result(timeout=1.0)
    assert isinstance(result, CommandFailure)
    assert result.error_code == "task_id_recovery"
    _wait_until(lambda: any(t.endswith("/init-slots") for t in publisher.topics()))
    snap = _snap(ref)
    assert snap["pending_command_type"] == "init_slots"


def test_generic_error_completes_pending_with_firefly_error(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)

    future: Future = Future()
    ref.tell(
        {
            "type": "submit_update_slot_state",
            "slots": [UpdateSlotStateSlot(slot_inx=1, to_state="OFF")],
            "timeout_ms": 200,
            "result_future": future,
        }
    )
    _wait_until(lambda: any(t.endswith("/update-slot-state") for t in publisher.topics()))
    event_id = publisher.last_payload("/update-slot-state")["event-id"]
    ref.tell(
        {
            "type": "error",
            "event_id": event_id,
            "error_code": "SOME_OTHER_ERROR",
            "error_descr": "bad",
        }
    )
    result = future.result(timeout=1.0)
    assert isinstance(result, CommandFailure)
    assert result.error_code == "firefly_error"
    assert result.details["firefly_error_code"] == "SOME_OTHER_ERROR"
    snap = _snap(ref)
    assert snap["status"] == ActorStatus.OFFLINE.value


def test_watchdog_fires_when_no_keepalive(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    fast_settings = RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=5000,
        ack_max_retries=2,
        keepalive_disconnect_after_seconds=0.1,
    )
    ref = _start(publisher, fast_settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)

    # Watchdog will fire ~0.1s after the most recent arming (which was the
    # actor start; ACK does not reset it).
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.OFFLINE.value, timeout_s=1.0)


def test_keepalive_while_offline_triggers_fresh_init_slots(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    fast_settings = RuntimeSettings(
        firefly_interface_version=VERSION,
        ack_timeout_ms=50,
        ack_max_retries=0,
        keepalive_disconnect_after_seconds=60.0,
    )
    ref = _start(publisher, fast_settings)
    # Let init-slots time out and transition to offline.
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.OFFLINE.value, timeout_s=1.0)
    publisher.clear()

    ref.tell({"type": "keepalive"})
    _wait_until(lambda: any(t.endswith("/init-slots") for t in publisher.topics()))
    snap = _snap(ref)
    assert snap["pending_command_type"] == "init_slots"


def test_reset_publishes_and_clears_session(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)
    publisher.clear()

    future: Future = Future()
    ref.tell({"type": "reset", "result_future": future})
    result = future.result(timeout=1.0)
    assert isinstance(result, CommandSuccess)
    assert any(t.endswith("/reset") for t in publisher.topics())
    reset_payload = publisher.last_payload("/reset")
    assert reset_payload == {}
    snap = _snap(ref)
    assert snap["fsm"] == StateMachine.OFFLINE.value
    assert snap["status"] == ActorStatus.OFFLINE.value
    assert snap["current_task_id"] is None


def test_reset_preempts_in_flight_command(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)

    submit_future: Future = Future()
    ref.tell(
        {
            "type": "submit_update_slot_state",
            "slots": [UpdateSlotStateSlot(slot_inx=1, to_state="OFF")],
            "timeout_ms": 5000,
            "result_future": submit_future,
        }
    )
    _wait_until(lambda: any(t.endswith("/update-slot-state") for t in publisher.topics()))

    reset_future: Future = Future()
    ref.tell({"type": "reset", "result_future": reset_future})

    submit_result = submit_future.result(timeout=1.0)
    reset_result = reset_future.result(timeout=1.0)
    assert isinstance(submit_result, CommandFailure)
    assert submit_result.error_code == "device_resetting"
    assert isinstance(reset_result, CommandSuccess)


def test_reinitialize_publishes_new_init_slots(
    publisher: FakePublisher, settings: RuntimeSettings
) -> None:
    ref = _start(publisher, settings)
    _wait_until(lambda: any("init-slots" in t for t in publisher.topics()))
    init_event = publisher.last_payload("/init-slots")["event-id"]
    first_task = publisher.last_payload("/init-slots")["task-id"]
    ref.tell({"type": "ack", "event_id": init_event})
    _wait_until(lambda: _snap(ref)["status"] == ActorStatus.ONLINE.value)
    publisher.clear()

    future: Future = Future()
    ref.tell({"type": "submit_reinitialize", "timeout_ms": 200, "result_future": future})
    _wait_until(lambda: any(t.endswith("/init-slots") for t in publisher.topics()))
    new_payload = publisher.last_payload("/init-slots")
    assert new_payload["task-id"] != first_task
    ref.tell({"type": "ack", "event_id": new_payload["event-id"]})
    result = future.result(timeout=1.0)
    assert isinstance(result, CommandSuccess)
    snap = _snap(ref)
    assert snap["current_task_id"] == new_payload["task-id"]
