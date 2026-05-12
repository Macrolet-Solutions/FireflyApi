"""MQTT abstractions used by the actor runtime.

Two narrow protocols isolate the rest of the codebase from paho-mqtt:

- :class:`MqttPublisher` is the publish-only surface needed by the device
  actor.
- :class:`MqttClient` is the full surface used by the registry to
  connect, subscribe, and dispatch inbound messages.

The concrete paho-based implementation lives in
:mod:`firefly_api.firefly.mqtt.client` and only the registry imports it.
"""

from __future__ import annotations

from typing import Callable, Protocol

InboundHandler = Callable[[str, bytes], None]


class MqttPublisher(Protocol):
    """Anything that can publish a single MQTT message."""

    def publish(self, topic: str, payload: bytes) -> None: ...


class MqttClient(MqttPublisher, Protocol):
    """Full MQTT client surface used by the registry."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def subscribe(self, topic: str) -> None: ...
    def set_message_handler(self, handler: InboundHandler) -> None: ...
    def is_connected(self) -> bool: ...


__all__ = ["InboundHandler", "MqttClient", "MqttPublisher"]
