"""Per-device Pykka actor implementing the §5 state machine.

The actor receives inbound MQTT messages (from the registry) and operator
commands (from the future Phase 3 HTTP layer), maintains its in-memory
runtime state, publishes outbound MQTT commands with ACK/retry/timeout
logic, and manages a keepalive watchdog.

Inbound message shape (all are plain ``dict``):

- ``{"type": "register_request", "request": RegistrationRequestIn,
   "request_version": str}``
- ``{"type": "ack", "event_id": str}``
- ``{"type": "error", "event_id": str, "error_code": str,
   "error_descr": str | None}``
- ``{"type": "keepalive"}``
- ``{"type": "watchdog_fired"}``
- ``{"type": "command_timeout", "event_id": str}``
- ``{"type": "submit_update_slot_state", "slots": [...],
   "timeout_ms": int, "result_future": Future}``
- ``{"type": "submit_update_all_slots", "to_state": str, "pattern": int,
   "pattern_value": int, "timeout_ms": int, "result_future": Future}``
- ``{"type": "submit_reinitialize", "timeout_ms": int, "result_future": Future}``
- ``{"type": "submit_load_slots", "init_slots": [...], "timeout_ms": int,
    "result_future": Future}``
- ``{"type": "reset", "result_future": Future}``
- ``{"type": "get_snapshot"}`` -> returns dict (for tests + status endpoint)
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import pykka

from firefly_api.firefly.events import EventLog, EventRecord, EventType, NullEventLog
from firefly_api.firefly.mqtt import MqttPublisher
from firefly_api.firefly.protocol import (
    TASK_ID_RECOVERY_ERROR_CODES,
    InitSlotsSlot,
    LedStateOut,
    RegistrationRequestIn,
    SegmentOut,
    UpdateSlotStateSlot,
    init_slots_topic,
    register_resp_topic,
    reset_topic,
    update_all_slots_topic,
    update_slot_state_topic,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------- value types ----


class StateMachine(str, Enum):
    """§5.3 state machine state."""

    WAITING_ACK = "waiting_ack"
    ACTIVE = "active"
    OFFLINE = "offline"


class ActorStatus(str, Enum):
    """§5.3 public status enum."""

    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    REGISTER_ERROR = "register_error"


class CommandType(str, Enum):
    REGISTER_RESPONSE = "register_response"
    INIT_SLOTS = "init_slots"
    UPDATE_SLOT_STATE = "update_slot_state"
    UPDATE_ALL_SLOTS = "update_all_slots"


@dataclass(frozen=True)
class DeviceConfig:
    """Snapshot of a device's persisted configuration passed at actor start."""

    device_id: int
    device_name: str
    device_type: str = "FireflyController"
    init_slots: tuple[InitSlotsSlot, ...] = ()
    registration_segments: tuple[SegmentOut, ...] = ()
    registration_states: tuple[LedStateOut, ...] = ()


@dataclass(frozen=True)
class RuntimeSettings:
    firefly_interface_version: str
    ack_timeout_ms: int = 7000
    ack_max_retries: int = 3
    # ``float`` rather than ``int`` so tests can use sub-second watchdogs.
    keepalive_disconnect_after_seconds: float = 300.0


@dataclass
class PendingCommand:
    command_type: CommandType
    event_id: str
    base_payload: dict[str, Any]
    topic: str
    timeout_ms: int
    max_retries: int
    retry_count: int = 0
    task_id: str | None = None  # task_id this command was published with
    result_future: Future | None = None


@dataclass
class CommandSuccess:
    event_id: str
    task_id: str | None = None


@dataclass
class CommandFailure:
    event_id: str
    error_code: str
    error_description: str
    details: dict[str, Any] = field(default_factory=dict)


CommandOutcome = CommandSuccess | CommandFailure


# ----------------------------------------------------------- the actor ----


class FireflyDeviceActor(pykka.ThreadingActor):
    """One actor per configured Firefly device."""

    use_daemon_thread = True

    def __init__(
        self,
        *,
        config: DeviceConfig,
        settings: RuntimeSettings,
        publisher: MqttPublisher,
        event_log: EventLog | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._settings = settings
        self._publisher = publisher
        self._event_log: EventLog = event_log or NullEventLog()

        # State machine.
        self.fsm: StateMachine = StateMachine.OFFLINE
        self.status: ActorStatus = ActorStatus.UNKNOWN

        # Session state.
        self.current_task_id: str | None = None
        self.pending_command: PendingCommand | None = None
        self.slot_states: dict[int, dict[str, Any]] = {}

        # Registration metadata observed from the device.
        self.firmware_version: str | None = None
        self.mac_address: str | None = None
        self.registered_at: datetime | None = None
        self.last_keepalive_at: datetime | None = None

        # Timers.
        self._watchdog_timer: threading.Timer | None = None
        self._command_timeout_timer: threading.Timer | None = None

    # ----------------------------------------------------- lifecycle ----

    def on_start(self) -> None:
        # §5.3 boot: if at least one slot is configured, publish init-slots;
        # otherwise stay offline.
        self._arm_watchdog()
        if self._config.init_slots:
            self._start_init_slots_command(timeout_ms=self._settings.ack_timeout_ms)
        # else: stay fsm/status = offline.

    def on_stop(self) -> None:
        self._cancel_watchdog()
        self._cancel_command_timeout()
        if self.pending_command and self.pending_command.result_future is not None:
            _fail_future(
                self.pending_command.result_future,
                CommandFailure(
                    event_id=self.pending_command.event_id,
                    error_code="actor_stopped",
                    error_description="Device actor was stopped.",
                ),
            )

    def on_failure(
        self,
        exception_type: type[BaseException],
        exception_value: BaseException,
        traceback: object,
    ) -> None:
        logger.exception(
            "FireflyDeviceActor for %s failed: %s",
            self._config.device_name,
            exception_value,
        )

    # ----------------------------------------------------- dispatch ----

    def on_receive(self, message: dict[str, Any]) -> Any:
        msg_type = message.get("type")
        handler = _DISPATCH.get(msg_type)
        if handler is None:
            logger.warning(
                "Actor %s received unknown message type %r", self._config.device_name, msg_type
            )
            return None
        return handler(self, message)

    # ----------------------------------------------------- helpers (state) ----

    def _set_state(
        self,
        fsm: StateMachine | None = None,
        status: ActorStatus | None = None,
    ) -> None:
        if fsm is not None:
            self.fsm = fsm
        if status is not None:
            self.status = status

    def _clear_session(self) -> None:
        """Wipe per-session in-memory state (§5.3 Resetting / Hard reset)."""
        self.current_task_id = None
        self.slot_states = {}
        self._cancel_command_timeout()
        self.pending_command = None

    # ----------------------------------------------------- helpers (timers) ----

    def _arm_watchdog(self) -> None:
        self._cancel_watchdog()
        ref = self.actor_ref
        timer = threading.Timer(
            self._settings.keepalive_disconnect_after_seconds,
            _safe_tell,
            args=(ref, {"type": "watchdog_fired"}),
        )
        timer.daemon = True
        timer.start()
        self._watchdog_timer = timer

    def _cancel_watchdog(self) -> None:
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
            self._watchdog_timer = None

    def _arm_command_timeout(self, event_id: str, timeout_ms: int) -> None:
        self._cancel_command_timeout()
        ref = self.actor_ref
        timer = threading.Timer(
            timeout_ms / 1000.0,
            _safe_tell,
            args=(ref, {"type": "command_timeout", "event_id": event_id}),
        )
        timer.daemon = True
        timer.start()
        self._command_timeout_timer = timer

    def _cancel_command_timeout(self) -> None:
        if self._command_timeout_timer is not None:
            self._command_timeout_timer.cancel()
            self._command_timeout_timer = None

    # ----------------------------------------------------- helpers (publish) ----

    def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._publisher.publish(topic, json.dumps(payload).encode("utf-8"))

    def _publish_with_new_event_id(
        self,
        topic: str,
        base_payload: dict[str, Any],
    ) -> str:
        event_id = str(uuid.uuid4())
        full = {"event-id": event_id, **base_payload}
        self._publish(topic, full)
        return event_id

    def _record(
        self,
        event_type: str,
        event_id: str,
        *,
        task_id: str | None = None,
        payload_json: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_description: str | None = None,
    ) -> None:
        self._event_log.record(
            EventRecord(
                device_id=self._config.device_id,
                event_id=event_id,
                event_type=event_type,
                task_id=task_id,
                payload_json=payload_json,
                error_code=error_code,
                error_description=error_description,
            )
        )

    # ----------------------------------------------------- handlers ----

    def _handle_register_request(self, message: dict[str, Any]) -> None:
        request: RegistrationRequestIn = message["request"]
        request_version: str = message["request_version"]
        now = datetime.now(timezone.utc)

        self._record(
            EventType.REGISTER_REQUEST_RECEIVED,
            event_id=str(uuid.uuid4()),
            payload_json=request.model_dump(by_alias=True),
        )

        # Registration is preemptive (§5.3). Discard any in-flight command.
        if self.pending_command and self.pending_command.result_future is not None:
            _fail_future(
                self.pending_command.result_future,
                CommandFailure(
                    event_id=self.pending_command.event_id,
                    error_code="device_re_registering",
                    error_description=(
                        "Device sent a fresh registration request; in-flight "
                        "command aborted."
                    ),
                ),
            )

        self._clear_session()
        self.firmware_version = request.firmware_version
        self.mac_address = request.device_mac
        self.registered_at = now

        # Version mismatch -> register_error.
        if request_version != self._settings.firefly_interface_version:
            self._publish_registration_error(
                f"Unsupported interface version {request_version}; expected "
                f"{self._settings.firefly_interface_version}."
            )
            self._set_state(StateMachine.OFFLINE, ActorStatus.REGISTER_ERROR)
            return

        # Empty LED states -> register_error.
        if not self._config.registration_states:
            self._publish_registration_error(
                "No LED states configured for this installation."
            )
            self._set_state(StateMachine.OFFLINE, ActorStatus.REGISTER_ERROR)
            return

        # Successful registration. Publish register-resp and wait for ACK.
        base_payload = {
            "is-error": False,
            "error-descr": "",
            "device-type": self._config.device_type,
            "segments": [s.model_dump(by_alias=True) for s in self._config.registration_segments],
            "states": [s.model_dump(by_alias=True) for s in self._config.registration_states],
        }
        topic = register_resp_topic(
            self._settings.firefly_interface_version, self._config.device_name
        )
        event_id = self._publish_with_new_event_id(topic, base_payload)
        self._record(
            EventType.REGISTER_RESPONSE_SENT,
            event_id=event_id,
            payload_json={"event-id": event_id, **base_payload},
        )
        self.pending_command = PendingCommand(
            command_type=CommandType.REGISTER_RESPONSE,
            event_id=event_id,
            base_payload=base_payload,
            topic=topic,
            timeout_ms=self._settings.ack_timeout_ms,
            max_retries=self._settings.ack_max_retries,
        )
        self._arm_command_timeout(event_id, self._settings.ack_timeout_ms)
        self._set_state(StateMachine.WAITING_ACK)
        # status: leave at unknown until init-slots is ACK'd.

    def _publish_registration_error(self, description: str) -> None:
        event_id = str(uuid.uuid4())
        payload = {
            "is-error": True,
            "error-descr": description,
            "event-id": event_id,
            "device-type": self._config.device_type,
            "segments": [],
            "states": [],
        }
        topic = register_resp_topic(
            self._settings.firefly_interface_version, self._config.device_name
        )
        self._publish(topic, payload)
        self._record(
            EventType.REGISTER_RESPONSE_SENT,
            event_id=event_id,
            payload_json=payload,
            error_description=description,
        )

    def _handle_ack(self, message: dict[str, Any]) -> None:
        event_id = message["event_id"]
        self._record(
            EventType.ACK_RECEIVED,
            event_id=event_id,
            payload_json={"event-id": event_id},
        )
        pending = self.pending_command
        if pending is None or pending.event_id != event_id:
            logger.warning(
                "Actor %s: unexpected ACK event_id=%s pending=%s",
                self._config.device_name,
                event_id,
                pending.event_id if pending else None,
            )
            return

        self._cancel_command_timeout()
        self.pending_command = None

        if pending.command_type is CommandType.REGISTER_RESPONSE:
            # Per §5.3: if slots configured, proceed to init-slots.
            if self._config.init_slots:
                self._start_init_slots_command(timeout_ms=self._settings.ack_timeout_ms)
            else:
                self._set_state(StateMachine.OFFLINE, ActorStatus.OFFLINE)
            return

        if pending.command_type is CommandType.INIT_SLOTS:
            self.current_task_id = pending.task_id
            self._set_state(StateMachine.ACTIVE, ActorStatus.ONLINE)
            if pending.result_future is not None:
                _complete_future(
                    pending.result_future,
                    CommandSuccess(event_id=event_id, task_id=pending.task_id),
                )
            return

        if pending.command_type in (
            CommandType.UPDATE_SLOT_STATE,
            CommandType.UPDATE_ALL_SLOTS,
        ):
            self._apply_slot_state_changes(pending)
            self._set_state(StateMachine.ACTIVE)
            if pending.result_future is not None:
                _complete_future(
                    pending.result_future,
                    CommandSuccess(event_id=event_id, task_id=self.current_task_id),
                )
            return

    def _handle_error(self, message: dict[str, Any]) -> None:
        event_id = message["event_id"]
        error_code = message["error_code"]
        error_descr = message.get("error_descr") or ""
        self._record(
            EventType.ERROR_RECEIVED,
            event_id=event_id,
            payload_json={
                "event-id": event_id,
                "error-code": error_code,
                "error-descr": error_descr,
            },
            error_code=error_code,
            error_description=error_descr,
        )
        pending = self.pending_command
        if pending is None or pending.event_id != event_id:
            logger.warning(
                "Actor %s: unexpected error event_id=%s pending=%s",
                self._config.device_name,
                event_id,
                pending.event_id if pending else None,
            )
            return

        self._cancel_command_timeout()

        # Task-ID-recovery error codes trigger slot reinitialization.
        if error_code in TASK_ID_RECOVERY_ERROR_CODES:
            self._fail_pending(
                CommandFailure(
                    event_id=event_id,
                    error_code="task_id_recovery",
                    error_description=(
                        "Device rejected the command due to task_id "
                        "mismatch/missing; reinitializing slots."
                    ),
                    details={"firefly_error_code": error_code},
                )
            )
            self._clear_session()
            self._start_init_slots_command(timeout_ms=self._settings.ack_timeout_ms)
            return

        # Other errors complete the command with a firefly_error.
        self._fail_pending(
            CommandFailure(
                event_id=event_id,
                error_code="firefly_error",
                error_description=error_descr or f"Device error {error_code}.",
                details={"firefly_error_code": error_code},
            )
        )
        self._set_state(StateMachine.OFFLINE, ActorStatus.OFFLINE)

    def _handle_keepalive(self, _message: dict[str, Any]) -> None:
        self.last_keepalive_at = datetime.now(timezone.utc)
        self._record(
            EventType.KEEPALIVE_RECEIVED,
            event_id=str(uuid.uuid4()),
        )
        self._arm_watchdog()  # reset

        # Per §5.3: when keepalive arrives while in offline (and not in
        # register_error), generate fresh task-id and republish init-slots.
        if self.fsm is StateMachine.OFFLINE and self.status is not ActorStatus.REGISTER_ERROR:
            if self._config.init_slots:
                self._start_init_slots_command(timeout_ms=self._settings.ack_timeout_ms)

    def _handle_watchdog_fired(self, _message: dict[str, Any]) -> None:
        if self.fsm is StateMachine.OFFLINE and self.status is ActorStatus.OFFLINE:
            # Already offline — nothing to do.
            return
        self._fail_pending(
            CommandFailure(
                event_id=self.pending_command.event_id if self.pending_command else "",
                error_code="device_offline",
                error_description="Keepalive watchdog fired; device considered offline.",
            )
        )
        self._clear_session()
        self._set_state(StateMachine.OFFLINE, ActorStatus.OFFLINE)

    def _handle_command_timeout(self, message: dict[str, Any]) -> None:
        event_id = message["event_id"]
        pending = self.pending_command
        if pending is None or pending.event_id != event_id:
            # Stale timer (we already advanced to a new event_id).
            return

        if pending.retry_count < pending.max_retries:
            # Retry: new event-id, republish, reschedule timer.
            new_event_id = self._publish_with_new_event_id(pending.topic, pending.base_payload)
            self._record(
                EventType.RETRY,
                event_id=new_event_id,
                task_id=pending.task_id,
                payload_json={"event-id": new_event_id, **pending.base_payload},
            )
            pending.event_id = new_event_id
            pending.retry_count += 1
            self._arm_command_timeout(new_event_id, pending.timeout_ms)
            return

        # Retries exhausted.
        self._record(
            EventType.TIMEOUT,
            event_id=event_id,
            task_id=pending.task_id,
            error_description=(
                f"No ACK after {pending.max_retries + 1} attempts."
            ),
        )
        self._fail_pending(
            CommandFailure(
                event_id=event_id,
                error_code="firefly_ack_timeout",
                error_description=(
                    f"No ACK after {pending.max_retries + 1} attempts."
                ),
            )
        )
        self._clear_session()
        self._set_state(StateMachine.OFFLINE, ActorStatus.OFFLINE)

    def _handle_submit_update_slot_state(self, message: dict[str, Any]) -> None:
        future: Future = message["result_future"]
        timeout_ms: int = message.get("timeout_ms") or self._settings.ack_timeout_ms

        if self.fsm is not StateMachine.ACTIVE or self.current_task_id is None:
            _fail_future(
                future,
                CommandFailure(
                    event_id="",
                    error_code="device_offline",
                    error_description="Device is not active; cannot submit slot update.",
                ),
            )
            return

        slots: list[UpdateSlotStateSlot] = message["slots"]
        base_payload: dict[str, Any] = {
            "task-id": self.current_task_id,
            "slots": [s.model_dump(by_alias=True) for s in slots],
        }
        topic = update_slot_state_topic(
            self._settings.firefly_interface_version, self._config.device_name
        )
        event_id = self._publish_with_new_event_id(topic, base_payload)
        self._record(
            EventType.UPDATE_SLOT_STATE_SENT,
            event_id=event_id,
            task_id=self.current_task_id,
            payload_json={"event-id": event_id, **base_payload},
        )
        self.pending_command = PendingCommand(
            command_type=CommandType.UPDATE_SLOT_STATE,
            event_id=event_id,
            base_payload=base_payload,
            topic=topic,
            timeout_ms=timeout_ms,
            max_retries=self._settings.ack_max_retries,
            task_id=self.current_task_id,
            result_future=future,
        )
        self._arm_command_timeout(event_id, timeout_ms)
        self._set_state(StateMachine.WAITING_ACK)

    def _handle_submit_update_all_slots(self, message: dict[str, Any]) -> None:
        future: Future = message["result_future"]
        timeout_ms: int = message.get("timeout_ms") or self._settings.ack_timeout_ms

        if self.fsm is not StateMachine.ACTIVE or self.current_task_id is None:
            _fail_future(
                future,
                CommandFailure(
                    event_id="",
                    error_code="device_offline",
                    error_description="Device is not active; cannot submit update-all.",
                ),
            )
            return

        base_payload: dict[str, Any] = {
            "task-id": self.current_task_id,
            "to-state": message["to_state"],
            "pattern": message.get("pattern", 0),
            "pattern-value": message.get("pattern_value", 0),
        }
        topic = update_all_slots_topic(
            self._settings.firefly_interface_version, self._config.device_name
        )
        event_id = self._publish_with_new_event_id(topic, base_payload)
        self._record(
            EventType.UPDATE_ALL_SLOTS_SENT,
            event_id=event_id,
            task_id=self.current_task_id,
            payload_json={"event-id": event_id, **base_payload},
        )
        self.pending_command = PendingCommand(
            command_type=CommandType.UPDATE_ALL_SLOTS,
            event_id=event_id,
            base_payload=base_payload,
            topic=topic,
            timeout_ms=timeout_ms,
            max_retries=self._settings.ack_max_retries,
            task_id=self.current_task_id,
            result_future=future,
        )
        self._arm_command_timeout(event_id, timeout_ms)
        self._set_state(StateMachine.WAITING_ACK)

    def _handle_submit_reinitialize(self, message: dict[str, Any]) -> None:
        future: Future = message["result_future"]
        timeout_ms: int = message.get("timeout_ms") or self._settings.ack_timeout_ms

        if not self._config.init_slots:
            _fail_future(
                future,
                CommandFailure(
                    event_id="",
                    error_code="not_configured",
                    error_description="Device has no slots configured.",
                ),
            )
            return
        if self.status is ActorStatus.REGISTER_ERROR:
            _fail_future(
                future,
                CommandFailure(
                    event_id="",
                    error_code="register_error",
                    error_description="Device is in register_error; reset required.",
                ),
            )
            return

        self._cancel_command_timeout()
        self._start_init_slots_command(timeout_ms=timeout_ms, future=future)

    def _handle_submit_load_slots(self, message: dict[str, Any]) -> None:
        future: Future = message["result_future"]
        timeout_ms: int = message.get("timeout_ms") or self._settings.ack_timeout_ms

        if self.status is ActorStatus.REGISTER_ERROR:
            _fail_future(
                future,
                CommandFailure(
                    event_id="",
                    error_code="register_error",
                    error_description="Device is in register_error; reset required.",
                ),
            )
            return

        self._config = replace(self._config, init_slots=tuple(message["init_slots"]))
        self._cancel_command_timeout()
        self._start_init_slots_command(timeout_ms=timeout_ms, future=future)

    def _handle_reset(self, message: dict[str, Any]) -> None:
        """§5.3 Hard reset: fire-and-forget MQTT publish + session wipe."""
        future: Future = message["result_future"]
        # Cancel any pending command, fail its caller with device_resetting.
        if self.pending_command and self.pending_command.result_future is not None:
            _fail_future(
                self.pending_command.result_future,
                CommandFailure(
                    event_id=self.pending_command.event_id,
                    error_code="device_resetting",
                    error_description=(
                        "Operator triggered a hard reset; in-flight command aborted."
                    ),
                ),
            )
        self._clear_session()
        # Publish the empty reset payload. Generate an event_id for log
        # traceability only (no ACK is expected).
        event_id = str(uuid.uuid4())
        topic = reset_topic(
            self._settings.firefly_interface_version, self._config.device_name
        )
        self._publish(topic, {})
        self._record(EventType.RESET_SENT, event_id=event_id, payload_json={})
        self._set_state(StateMachine.OFFLINE, ActorStatus.OFFLINE)
        _complete_future(future, CommandSuccess(event_id=event_id))

    def _handle_get_snapshot(self, _message: dict[str, Any]) -> dict[str, Any]:
        return {
            "device_id": self._config.device_id,
            "device_name": self._config.device_name,
            "fsm": self.fsm.value,
            "status": self.status.value,
            "current_task_id": self.current_task_id,
            "pending_command_type": (
                self.pending_command.command_type.value
                if self.pending_command is not None
                else None
            ),
            "pending_event_id": (
                self.pending_command.event_id if self.pending_command is not None else None
            ),
            "pending_retry_count": (
                self.pending_command.retry_count if self.pending_command is not None else None
            ),
            "firmware_version": self.firmware_version,
            "mac_address": self.mac_address,
            "registered_at": self.registered_at,
            "last_keepalive_at": self.last_keepalive_at,
            "slot_states": dict(self.slot_states),
        }

    # ----------------------------------------------------- helpers (commands) ----

    def _start_init_slots_command(
        self,
        *,
        timeout_ms: int,
        future: Future | None = None,
    ) -> None:
        task_id = str(uuid.uuid4())
        base_payload: dict[str, Any] = {
            "task-id": task_id,
            "num-slots": len(self._config.init_slots),
            "slots": [s.model_dump(by_alias=True) for s in self._config.init_slots],
        }
        topic = init_slots_topic(
            self._settings.firefly_interface_version, self._config.device_name
        )
        event_id = self._publish_with_new_event_id(topic, base_payload)
        self._record(
            EventType.INIT_SLOTS_SENT,
            event_id=event_id,
            task_id=task_id,
            payload_json={"event-id": event_id, **base_payload},
        )
        self.pending_command = PendingCommand(
            command_type=CommandType.INIT_SLOTS,
            event_id=event_id,
            base_payload=base_payload,
            topic=topic,
            timeout_ms=timeout_ms,
            max_retries=self._settings.ack_max_retries,
            task_id=task_id,
            result_future=future,
        )
        self._arm_command_timeout(event_id, timeout_ms)
        self._set_state(StateMachine.WAITING_ACK)

    def _apply_slot_state_changes(self, pending: PendingCommand) -> None:
        if pending.command_type is CommandType.UPDATE_SLOT_STATE:
            for slot in pending.base_payload.get("slots", []):
                inx = slot.get("slot-inx")
                if inx is None:
                    continue
                self.slot_states[int(inx)] = {
                    "to_state": slot.get("to-state"),
                    "pattern": slot.get("pattern"),
                    "pattern_value": slot.get("pattern-value"),
                }
        elif pending.command_type is CommandType.UPDATE_ALL_SLOTS:
            entry = {
                "to_state": pending.base_payload.get("to-state"),
                "pattern": pending.base_payload.get("pattern"),
                "pattern_value": pending.base_payload.get("pattern-value"),
            }
            for s in self._config.init_slots:
                self.slot_states[int(s.slot_inx)] = dict(entry)

    def _fail_pending(self, failure: CommandFailure) -> None:
        pending = self.pending_command
        if pending is None:
            return
        if pending.result_future is not None:
            _fail_future(pending.result_future, failure)
        self.pending_command = None


# ----------------------------------------------------- module helpers ----


def _complete_future(future: Future, value: Any) -> None:
    if not future.done():
        future.set_result(value)


def _fail_future(future: Future, failure: CommandFailure) -> None:
    if not future.done():
        future.set_result(failure)


def _safe_tell(actor_ref: pykka.ActorRef, message: dict[str, Any]) -> None:
    """Tell an actor, swallowing errors if the actor is already stopped."""
    try:
        actor_ref.tell(message)
    except pykka.ActorDeadError:
        pass


# Dispatch table; declared at module scope so it isn't rebuilt on every
# message.
_DISPATCH: dict[str, Any] = {
    "register_request": FireflyDeviceActor._handle_register_request,
    "ack": FireflyDeviceActor._handle_ack,
    "error": FireflyDeviceActor._handle_error,
    "keepalive": FireflyDeviceActor._handle_keepalive,
    "watchdog_fired": FireflyDeviceActor._handle_watchdog_fired,
    "command_timeout": FireflyDeviceActor._handle_command_timeout,
    "submit_update_slot_state": FireflyDeviceActor._handle_submit_update_slot_state,
    "submit_update_all_slots": FireflyDeviceActor._handle_submit_update_all_slots,
    "submit_reinitialize": FireflyDeviceActor._handle_submit_reinitialize,
    "submit_load_slots": FireflyDeviceActor._handle_submit_load_slots,
    "reset": FireflyDeviceActor._handle_reset,
    "get_snapshot": FireflyDeviceActor._handle_get_snapshot,
}
