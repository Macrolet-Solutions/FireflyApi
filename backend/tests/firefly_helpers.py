"""Shared MQTT test doubles for the Firefly runtime tests.

- :class:`FakePublisher` is the minimum :class:`MqttPublisher`-shaped fake
  used by actor unit tests that don't drive a registry.
- :class:`FakeMqttClient` is the full :class:`MqttClient`-shaped fake used
  by registry / integration / HTTP tests; it captures publishes and
  exposes :meth:`inject` for delivering inbound messages to the handler
  installed by the registry.
- :class:`AutoAckingMqttClient` extends :class:`FakeMqttClient` and
  automatically replies with an ACK to every outbound command that
  carries an ``event-id``. This collapses the ``submit -> publish -> ACK
  -> resolve future`` choreography into a single test step.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from firefly_api.firefly.mqtt import InboundHandler
from firefly_api.firefly.protocol import ack_topic


_ACK_BEARING_SUFFIXES = (
    "/init-slots",
    "/update-slot-state",
    "/update-all-slots",
    "/register-resp",
)


class FakePublisher:
    """Capture-only publisher; the smallest test-double surface."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []
        self._lock = threading.Lock()

    def publish(self, topic: str, payload: bytes) -> None:
        with self._lock:
            self.published.append((topic, payload))

    def topics(self) -> list[str]:
        with self._lock:
            return [t for t, _ in self.published]

    def last_payload(self, topic_suffix: str) -> dict[str, Any]:
        with self._lock:
            for topic, raw in reversed(self.published):
                if topic.endswith(topic_suffix):
                    return json.loads(raw.decode("utf-8"))
        raise AssertionError(
            f"No publish for suffix {topic_suffix!r}; topics: "
            f"{[t for t, _ in self.published]}"
        )

    def clear(self) -> None:
        with self._lock:
            self.published.clear()


class FakeMqttClient(FakePublisher):
    """A full :class:`MqttClient` test double with a one-way inject channel."""

    def __init__(self) -> None:
        super().__init__()
        self.subscriptions: list[str] = []
        self._handler: InboundHandler | None = None
        self.connected = True

    # MqttClient surface ----------------------------------------------------

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def subscribe(self, topic: str) -> None:
        with self._lock:
            if topic not in self.subscriptions:
                self.subscriptions.append(topic)

    def set_message_handler(self, handler: InboundHandler) -> None:
        self._handler = handler

    def is_connected(self) -> bool:
        return self.connected

    # Helpers ---------------------------------------------------------------

    def inject(self, topic: str, payload: bytes) -> None:
        assert self._handler is not None, (
            "Cannot inject before registry.start_all() installs the handler."
        )
        self._handler(topic, payload)


class AutoAckingMqttClient(FakeMqttClient):
    """Replies with an ACK to every outbound command that has an event-id.

    The ACK is dispatched from a daemon thread so the actor's current
    message handler has time to install the matching ``pending_command``
    before the inbound ACK lands in its mailbox.
    """

    def __init__(self, version: str, *, ack_delay_s: float = 0.005) -> None:
        super().__init__()
        self._version = version
        self._ack_delay_s = ack_delay_s
        self._acked_events: set[str] = set()
        self._auto_ack_enabled = True
        self.ack_lock = threading.Lock()

    @property
    def auto_ack(self) -> bool:
        return self._auto_ack_enabled

    @auto_ack.setter
    def auto_ack(self, value: bool) -> None:
        self._auto_ack_enabled = value

    def publish(self, topic: str, payload: bytes) -> None:
        super().publish(topic, payload)
        if not self._auto_ack_enabled:
            return
        if not any(topic.endswith(s) for s in _ACK_BEARING_SUFFIXES):
            return
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        event_id = body.get("event-id")
        if not event_id:
            return
        device_name = _device_name_from_outbound_topic(topic)
        if device_name is None:
            return
        with self.ack_lock:
            if event_id in self._acked_events:
                return
            self._acked_events.add(event_id)

        timer = threading.Timer(
            self._ack_delay_s,
            self._send_ack,
            args=(device_name, event_id),
        )
        timer.daemon = True
        timer.start()

    def _send_ack(self, device_name: str, event_id: str) -> None:
        payload = json.dumps({"event-id": event_id}).encode("utf-8")
        try:
            self.inject(ack_topic(self._version, device_name), payload)
        except AssertionError:
            # The registry may have torn down between publish and ack.
            pass


def _device_name_from_outbound_topic(topic: str) -> str | None:
    """Extract ``deviceName`` from ``ff/{version}/{deviceName}/{leaf}``."""
    parts = topic.split("/")
    if len(parts) >= 4 and parts[0] == "ff":
        return parts[2]
    return None
