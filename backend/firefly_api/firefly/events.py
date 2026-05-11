"""Event-logging interface and DB-backed implementation (§7.7).

The actor runtime emits an :class:`EventRecord` for every MQTT publish and
every received message, plus internal lifecycle moments (timeout, retry).
The default :class:`DbEventLog` writes each record as one row in
``firefly_events``; tests can substitute a fake.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import FireflyEvent

logger = logging.getLogger(__name__)


class EventType:
    """String constants matching the §7.7 event_type enum."""

    REGISTER_REQUEST_RECEIVED = "register_request_received"
    REGISTER_RESPONSE_SENT = "register_response_sent"
    INIT_SLOTS_SENT = "init_slots_sent"
    UPDATE_SLOT_STATE_SENT = "update_slot_state_sent"
    UPDATE_ALL_SLOTS_SENT = "update_all_slots_sent"
    RESET_SENT = "reset_sent"
    ACK_RECEIVED = "ack_received"
    ERROR_RECEIVED = "error_received"
    KEEPALIVE_RECEIVED = "keepalive_received"
    TIMEOUT = "timeout"
    RETRY = "retry"


@dataclass(frozen=True)
class EventRecord:
    device_id: int
    event_id: str
    event_type: str
    task_id: str | None = None
    payload_json: dict[str, Any] | None = None
    error_code: str | None = None
    error_description: str | None = None


class EventLog(Protocol):
    def record(self, event: EventRecord) -> None: ...


class NullEventLog:
    """No-op event log; used as the default so tests that don't care about
    event persistence don't need to provide an implementation."""

    def record(self, event: EventRecord) -> None:  # noqa: D401, ARG002
        return


class DbEventLog:
    """Writes each ``EventRecord`` as a row in ``firefly_events``."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, event: EventRecord) -> None:
        session = self._session_factory()
        try:
            session.add(
                FireflyEvent(
                    device_id=event.device_id,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    task_id=event.task_id,
                    payload_json=event.payload_json,
                    error_code=event.error_code,
                    error_description=event.error_description,
                )
            )
            session.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to persist event %s for device %d",
                event.event_type,
                event.device_id,
            )
            session.rollback()
        finally:
            session.close()


class InMemoryEventLog:
    """Test fixture-friendly log that stores records in a list."""

    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def record(self, event: EventRecord) -> None:
        self.records.append(event)

    def types_for(self, device_id: int) -> list[str]:
        return [r.event_type for r in self.records if r.device_id == device_id]


__all__ = [
    "DbEventLog",
    "EventLog",
    "EventRecord",
    "EventType",
    "InMemoryEventLog",
    "NullEventLog",
]
