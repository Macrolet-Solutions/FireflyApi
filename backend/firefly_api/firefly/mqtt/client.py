"""paho-mqtt-based concrete implementation of :class:`MqttClient`.

QoS 0 is used on every publish and subscribe (§6.6). Reconnect handling
re-subscribes to all previously requested topics so the registry can stay
hands-off after the initial connect.
"""

from __future__ import annotations

import logging
import threading

import paho.mqtt.client as paho

from firefly_api.firefly.mqtt import InboundHandler

logger = logging.getLogger(__name__)

QOS = 0


class PahoMqttClient:
    """Thin wrapper around ``paho.mqtt.client.Client`` (callback API v2)."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = False,
        client_id: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=client_id or "",
        )
        if username is not None:
            self._client.username_pw_set(username, password)
        if use_tls:
            self._client.tls_set()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._handler: InboundHandler | None = None
        self._connected = threading.Event()
        self._subscriptions: list[str] = []
        self._lock = threading.Lock()
        self._connect_timeout_s = 5.0

    def set_message_handler(self, handler: InboundHandler) -> None:
        self._handler = handler

    def connect(self) -> None:
        self._connected.clear()
        self._client.connect_async(self._host, self._port, keepalive=30)
        self._client.loop_start()
        if not self._connected.wait(timeout=self._connect_timeout_s):
            self._client.loop_stop()
            raise TimeoutError(
                f"MQTT connect timed out after {self._connect_timeout_s} s"
                f" ({self._host}:{self._port})."
            )

    def disconnect(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()

    def subscribe(self, topic: str) -> None:
        with self._lock:
            if topic not in self._subscriptions:
                self._subscriptions.append(topic)
        self._client.subscribe(topic, qos=QOS)

    def publish(self, topic: str, payload: bytes) -> None:
        self._client.publish(topic, payload=payload, qos=QOS)

    # paho v2 callbacks ------------------------------------------------------

    def _on_connect(
        self,
        _client: paho.Client,
        _userdata: object,
        _flags: object,
        reason_code: int,
        _props: object = None,
    ) -> None:
        if reason_code == 0:
            self._connected.set()
            with self._lock:
                subs = list(self._subscriptions)
            for sub in subs:
                self._client.subscribe(sub, qos=QOS)
        else:
            logger.warning("MQTT connect refused: reason_code=%s", reason_code)

    def _on_message(
        self,
        _client: paho.Client,
        _userdata: object,
        msg: paho.MQTTMessage,
    ) -> None:
        if self._handler is None:
            return
        try:
            self._handler(msg.topic, msg.payload)
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled exception in MQTT message handler")

    def _on_disconnect(
        self,
        _client: paho.Client,
        _userdata: object,
        _flags: object,
        reason_code: int,
        _props: object = None,
    ) -> None:
        self._connected.clear()
        if reason_code != 0:
            logger.warning("Unexpected MQTT disconnect: reason_code=%s", reason_code)
