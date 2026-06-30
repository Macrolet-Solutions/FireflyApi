"""High-level operations used by the HTTP layer (§4 module layout).

The service translates HTTP request data into actor messages, waits
synchronously on the actor's result future (§8 ACK-waiting semantics),
and raises :class:`FireflyError` subclasses with the standardized
``errorCode`` tokens expected by §8.4 / §9.

This module **does not** depend on FastAPI; route handlers in
:mod:`firefly_api.api` translate :class:`FireflyError` exceptions into
the HTTP response envelope.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.core.errors import (
    ConflictError,
    FireflyError,
    NotFoundError,
    ValidationFailedError,
)
from firefly_api.db.models import (
    FireflyDevice,
    FireflyLedState,
    FireflySegment,
    FireflySlot,
)
from firefly_api.db.repositories import slots as slots_repo
from firefly_api.firefly.actors import (
    ActorRegistry,
    ActorStatus,
    CommandFailure,
    CommandOutcome,
    CommandSuccess,
    RuntimeSettings,
)
from firefly_api.firefly.protocol import (
    InitSlotsSlot,
    UpdateSlotStateSlot,
    pattern_from_public_name,
)

logger = logging.getLogger(__name__)


class FireflyServiceError(FireflyError):
    """Custom HTTP error for ACK-waiting failures (§8.4)."""


class FireflyService:
    def __init__(
        self,
        *,
        registry: ActorRegistry,
        session_factory: sessionmaker[Session],
        settings: RuntimeSettings,
    ) -> None:
        self._registry = registry
        self._session_factory = session_factory
        self._settings = settings

    # ----------------------------------------------------- public API (§8) ----

    def update_slots(
        self,
        *,
        device_name: str,
        slots_in: list[dict],
        timeout_ms: int | None,
        client_request_id: str | None,
    ) -> dict:
        self._ensure_broker_connected()
        actor, device = self._lookup_actor_by_name(device_name)

        slots = self._build_update_slots_from_external(device, slots_in)
        per_attempt_ms = timeout_ms or self._settings.ack_timeout_ms

        future: Future = Future()
        actor.tell(
            {
                "type": "submit_update_slot_state",
                "slots": slots,
                "timeout_ms": per_attempt_ms,
                "result_future": future,
            }
        )
        outcome = self._await_outcome(future, per_attempt_ms)
        snapshot = self._snapshot(actor)
        return {
            "deviceName": device_name,
            "status": "updated",
            "eventId": outcome.event_id,
            "currentTaskId": snapshot.get("current_task_id"),
            "clientRequestId": client_request_id,
        }

    def update_all_slots(
        self,
        *,
        device_name: str,
        state_name: str,
        pattern: str,
        pattern_value: int,
        timeout_ms: int | None,
        client_request_id: str | None,
    ) -> dict:
        self._ensure_broker_connected()
        actor, _device = self._lookup_actor_by_name(device_name)
        self._ensure_state_exists(state_name)
        pattern_int = pattern_from_public_name(pattern)
        per_attempt_ms = timeout_ms or self._settings.ack_timeout_ms

        future: Future = Future()
        actor.tell(
            {
                "type": "submit_update_all_slots",
                "to_state": state_name,
                "pattern": int(pattern_int),
                "pattern_value": pattern_value,
                "timeout_ms": per_attempt_ms,
                "result_future": future,
            }
        )
        outcome = self._await_outcome(future, per_attempt_ms)
        snapshot = self._snapshot(actor)
        return {
            "deviceName": device_name,
            "status": "updated",
            "eventId": outcome.event_id,
            "currentTaskId": snapshot.get("current_task_id"),
            "clientRequestId": client_request_id,
        }

    def load_slots(
        self,
        *,
        device_name: str,
        segments_in: list[dict],
    ) -> dict:
        self._ensure_broker_connected()
        actor, device = self._lookup_actor_by_name(device_name)
        with self._session_factory() as db:
            slots_repo.replace_dynamic_segments(db, device.id, segments_in)
            init_slots = self._build_init_slots(db, device.id)

        per_attempt_ms = self._settings.ack_timeout_ms
        future: Future = Future()
        actor.tell(
            {
                "type": "submit_load_slots",
                "init_slots": init_slots,
                "timeout_ms": per_attempt_ms,
                "result_future": future,
            }
        )
        outcome = self._await_outcome(future, per_attempt_ms)
        snapshot = self._snapshot(actor)
        return {
            "deviceName": device_name,
            "status": "loaded",
            "eventId": outcome.event_id,
            "currentTaskId": snapshot.get("current_task_id"),
            "clientRequestId": None,
        }

    def get_device_status(self, *, device_name: str) -> dict:
        actor, _device = self._lookup_actor_by_name(device_name)
        snap = self._snapshot(actor)
        return {
            "deviceName": device_name,
            "status": snap["status"],
            "firmwareVersion": snap.get("firmware_version"),
            "macAddress": snap.get("mac_address"),
            "registeredAt": snap.get("registered_at"),
            "lastKeepaliveAt": snap.get("last_keepalive_at"),
            "currentTaskId": snap.get("current_task_id"),
        }

    # ----------------------------------------------------- admin (§9.4-§9.6) ----

    def reinitialize(self, *, device_id: int, timeout_ms: int | None) -> dict:
        self._ensure_broker_connected()
        actor, device = self._lookup_actor_by_id(device_id)
        per_attempt_ms = timeout_ms or self._settings.ack_timeout_ms

        future: Future = Future()
        actor.tell(
            {
                "type": "submit_reinitialize",
                "timeout_ms": per_attempt_ms,
                "result_future": future,
            }
        )
        outcome = self._await_outcome(future, per_attempt_ms)
        snapshot = self._snapshot(actor)
        return {
            "deviceId": device.id,
            "status": "reinitialized",
            "eventId": outcome.event_id,
            "currentTaskId": snapshot.get("current_task_id"),
        }

    def reset(self, *, device_id: int) -> dict:
        self._ensure_broker_connected()
        actor, device = self._lookup_actor_by_id(device_id)

        future: Future = Future()
        actor.tell({"type": "reset", "result_future": future})
        # The reset future resolves as soon as the publish hands off; a
        # generous wallclock cap is fine.
        outcome = self._await_outcome(future, timeout_ms=2000)
        return {
            "deviceId": device.id,
            "status": "reset_published",
            "eventId": outcome.event_id,
        }

    def start_actor(self, *, device_id: int) -> dict:
        with self._session_factory() as db:
            device = db.get(FireflyDevice, device_id)
        if device is None:
            raise NotFoundError(
                f"Device {device_id} not found.", error_code="device_not_found"
            )
        if not self._registry.is_broker_connected():
            raise ConflictError(
                "MQTT broker is not connected.",
                error_code="broker_not_connected",
            )
        actor_status = self._registry.start_actor_for_device(device.name)
        return {"deviceId": device.id, "actorStatus": actor_status}

    def stop_actor(self, *, device_id: int) -> dict:
        with self._session_factory() as db:
            device = db.get(FireflyDevice, device_id)
        if device is None:
            raise NotFoundError(
                f"Device {device_id} not found.", error_code="device_not_found"
            )
        actor_status = self._registry.stop_actor_for_device(device.name)
        return {"deviceId": device.id, "actorStatus": actor_status}

    def test_slot_update(
        self,
        *,
        device_id: int,
        slots_in: list[dict],
        timeout_ms: int | None,
    ) -> dict:
        self._ensure_broker_connected()
        actor, device = self._lookup_actor_by_id(device_id)
        slots = self._build_update_slots_from_internal(device, slots_in)
        per_attempt_ms = timeout_ms or self._settings.ack_timeout_ms

        future: Future = Future()
        actor.tell(
            {
                "type": "submit_update_slot_state",
                "slots": slots,
                "timeout_ms": per_attempt_ms,
                "result_future": future,
            }
        )
        outcome = self._await_outcome(future, per_attempt_ms)
        snapshot = self._snapshot(actor)
        return {
            "deviceName": device.name,
            "status": "updated",
            "eventId": outcome.event_id,
            "currentTaskId": snapshot.get("current_task_id"),
        }

    # ----------------------------------------------------- internal helpers ----

    def _ensure_broker_connected(self) -> None:
        if not self._registry.is_broker_connected():
            raise FireflyServiceError(
                "MQTT broker is not currently connected.",
                status_code=503,
                error_code="broker_unavailable",
            )

    def _lookup_actor_by_name(self, device_name: str):
        actor = self._registry.get_actor(device_name)
        if actor is None:
            raise NotFoundError(
                f"Device '{device_name}' is not configured.",
                error_code="device_not_found",
            )
        with self._session_factory() as db:
            device = db.scalar(
                select(FireflyDevice).where(FireflyDevice.name == device_name)
            )
        if device is None:
            raise NotFoundError(
                f"Device '{device_name}' is not configured.",
                error_code="device_not_found",
            )
        return actor, device

    def _lookup_actor_by_id(self, device_id: int):
        with self._session_factory() as db:
            device = db.get(FireflyDevice, device_id)
        if device is None:
            raise NotFoundError(
                f"Device {device_id} not found.", error_code="device_not_found"
            )
        actor = self._registry.get_actor(device.name)
        if actor is None:
            raise ConflictError(
                f"Actor for device {device.name} is not running.",
                error_code="actor_not_running",
            )
        return actor, device

    def _ensure_state_exists(self, state_name: str) -> None:
        with self._session_factory() as db:
            exists = db.scalar(
                select(FireflyLedState.id).where(FireflyLedState.name == state_name)
            )
        if exists is None:
            raise ValidationFailedError(
                f"LED state '{state_name}' is not configured.",
                error_code="invalid_state_name",
            )

    def _build_update_slots_from_external(
        self, device: FireflyDevice, slots_in: list[dict]
    ) -> list[UpdateSlotStateSlot]:
        if not slots_in:
            raise ValidationFailedError(
                "At least one slot is required.",
                error_code="empty_slots_list",
            )
        with self._session_factory() as db:
            db_slots = db.scalars(
                select(FireflySlot).where(FireflySlot.device_id == device.id)
            ).all()
            valid_state_names = set(
                db.scalars(select(FireflyLedState.name)).all()
            )
        slot_map = {s.external_slot_id: s.slot_index for s in db_slots}
        return [
            self._build_slot_struct(s, slot_map, valid_state_names) for s in slots_in
        ]

    def _build_init_slots(self, db: Session, device_id: int) -> tuple[InitSlotsSlot, ...]:
        segments = db.scalars(
            select(FireflySegment).where(FireflySegment.device_id == device_id)
        ).all()
        segment_by_id = {segment.id: segment for segment in segments}
        slots = db.scalars(
            select(FireflySlot)
            .where(FireflySlot.device_id == device_id)
            .order_by(FireflySlot.slot_index)
        ).all()
        return tuple(
            InitSlotsSlot(
                slot_inx=slot.slot_index,
                channel=segment_by_id[slot.segment_id].channel_num,
                ch_segm=segment_by_id[slot.segment_id].segment_num_in_channel,
                pos_in_segm=slot.segment_position,
                num_leds=slot.num_leds,
            )
            for slot in slots
        )

    def _build_update_slots_from_internal(
        self, device: FireflyDevice, slots_in: list[dict]
    ) -> list[UpdateSlotStateSlot]:
        if not slots_in:
            raise ValidationFailedError(
                "At least one slot is required.",
                error_code="empty_slots_list",
            )
        with self._session_factory() as db:
            db_slots = db.scalars(
                select(FireflySlot).where(FireflySlot.device_id == device.id)
            ).all()
            valid_state_names = set(
                db.scalars(select(FireflyLedState.name)).all()
            )
        slot_map = {s.id: s.slot_index for s in db_slots}
        result: list[UpdateSlotStateSlot] = []
        for s in slots_in:
            slot_id = s["slot_id"]
            if slot_id not in slot_map:
                raise ValidationFailedError(
                    f"Slot {slot_id} is not configured for device "
                    f"{device.name}.",
                    error_code="invalid_slot_id",
                )
            self._validate_state_and_pattern(s, valid_state_names)
            result.append(
                UpdateSlotStateSlot(
                    slot_inx=slot_map[slot_id],
                    to_state=s["state_name"],
                    pattern=int(pattern_from_public_name(s["pattern"])),
                    pattern_value=s.get("pattern_value", 0),
                )
            )
        return result

    def _build_slot_struct(
        self,
        slot_in: dict,
        slot_map: dict[str, int],
        valid_state_names: set[str],
    ) -> UpdateSlotStateSlot:
        external = slot_in["external_slot_id"]
        if external not in slot_map:
            raise ValidationFailedError(
                f"External slot id '{external}' is not configured for this device.",
                error_code="invalid_external_slot_id",
            )
        self._validate_state_and_pattern(slot_in, valid_state_names)
        return UpdateSlotStateSlot(
            slot_inx=slot_map[external],
            to_state=slot_in["state_name"],
            pattern=int(pattern_from_public_name(slot_in["pattern"])),
            pattern_value=slot_in.get("pattern_value", 0),
        )

    def _validate_state_and_pattern(
        self, slot_in: dict, valid_state_names: set[str]
    ) -> None:
        state_name = slot_in["state_name"]
        if state_name not in valid_state_names:
            raise ValidationFailedError(
                f"LED state '{state_name}' is not configured.",
                error_code="invalid_state_name",
            )
        # pattern_from_public_name raises ValidationFailedError(invalid_pattern)
        # for unknown names, so we let that bubble up.
        pattern_from_public_name(slot_in["pattern"])

    def _snapshot(self, actor) -> dict:
        return actor.ask({"type": "get_snapshot"}, timeout=2.0)

    def _await_outcome(self, future: Future, timeout_ms: int) -> CommandSuccess:
        """Wait on the actor's outcome and translate failures to FireflyError."""
        wallclock_s = (
            timeout_ms * (self._settings.ack_max_retries + 1) / 1000.0 + 2.0
        )
        try:
            outcome: CommandOutcome = future.result(timeout=wallclock_s)
        except FuturesTimeoutError as exc:
            # The actor's own timer should have fired before this. If we hit
            # this path, something deeper is wrong; surface as 504.
            raise FireflyServiceError(
                "Actor did not produce a result within the request budget.",
                status_code=504,
                error_code="firefly_ack_timeout",
            ) from exc

        if isinstance(outcome, CommandSuccess):
            return outcome
        self._raise_for_failure(outcome)

    def _raise_for_failure(self, failure: CommandFailure) -> None:
        status_map = {
            "device_offline": (409, "device_offline"),
            "device_re_registering": (503, "device_re_registering"),
            "device_resetting": (503, "device_resetting"),
            "task_id_recovery": (502, "firefly_error"),
            "firefly_error": (502, "firefly_error"),
            "firefly_ack_timeout": (504, "firefly_ack_timeout"),
            "actor_stopped": (503, "actor_stopped"),
            "register_error": (409, "register_error"),
            "not_configured": (422, "not_configured"),
        }
        status_code, error_code = status_map.get(
            failure.error_code, (502, "firefly_error")
        )
        details = dict(failure.details)
        if failure.event_id:
            details.setdefault("eventId", failure.event_id)
        raise FireflyServiceError(
            failure.error_description,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["FireflyService", "FireflyServiceError"]
