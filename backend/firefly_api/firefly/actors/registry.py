"""Actor registry (§5.1).

The registry owns one actor per configured device, the MQTT subscription
list, and the inbound message dispatch path. It is constructed by the
service startup code with an :class:`MqttClient` and a SQLAlchemy session
factory, then driven by :meth:`start_all` / :meth:`stop_all`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import pykka
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from firefly_api.db.models import (
    FireflyDevice,
    FireflyLedState,
    FireflySegment,
    FireflySlot,
)
from firefly_api.firefly.actors.device import (
    DeviceConfig,
    FireflyDeviceActor,
    RuntimeSettings,
)
from firefly_api.firefly.events import EventLog, NullEventLog
from firefly_api.firefly.mqtt import MqttClient
from firefly_api.firefly.protocol import (
    REGISTER_REQ_SUBSCRIPTION,
    InboundTopicKind,
    InitSlotsSlot,
    LedStateOut,
    RegistrationRequestIn,
    SegmentOut,
    device_subscriptions,
    parse_inbound_topic,
)

logger = logging.getLogger(__name__)


class ActorRegistry:
    def __init__(
        self,
        *,
        mqtt_client: MqttClient,
        session_factory: sessionmaker[Session],
        settings: RuntimeSettings,
        event_log: EventLog | None = None,
    ) -> None:
        self._mqtt = mqtt_client
        self._session_factory = session_factory
        self._settings = settings
        self._event_log: EventLog = event_log or NullEventLog()
        self._actors: dict[str, pykka.ActorRef] = {}
        self._started = False

    # Public lifecycle -------------------------------------------------------

    def start_all(self) -> None:
        if self._started:
            return
        self._mqtt.set_message_handler(self._on_inbound)
        self._mqtt.subscribe(REGISTER_REQ_SUBSCRIPTION)
        for sub in device_subscriptions(self._settings.firefly_interface_version):
            self._mqtt.subscribe(sub)
        self._spawn_actors_for_all_devices()
        self._started = True

    def stop_all(self) -> None:
        for ref in list(self._actors.values()):
            try:
                ref.stop(block=True, timeout=2.0)
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping actor")
        self._actors.clear()
        self._started = False

    def get_actor(self, device_name: str) -> pykka.ActorRef | None:
        return self._actors.get(device_name)

    def device_names(self) -> list[str]:
        return list(self._actors.keys())

    def is_broker_connected(self) -> bool:
        return self._mqtt.is_connected()

    @property
    def settings(self) -> RuntimeSettings:
        return self._settings

    # Per-device lifecycle (admin actions §9.2 / §9.3) ----------------------

    def start_actor_for_device(self, device_name: str) -> str:
        """Start the actor for ``device_name`` if not already running.

        Returns ``"started"`` or ``"already_running"``. The caller is
        responsible for validating broker connectivity (raises if not).
        """
        if device_name in self._actors:
            return "already_running"
        with self._session_factory() as db:
            led_states = db.scalars(
                select(FireflyLedState).order_by(FireflyLedState.id)
            ).all()
            registration_states = tuple(_to_registration_states(led_states))
            device = db.scalar(
                select(FireflyDevice).where(FireflyDevice.name == device_name)
            )
            if device is None:
                raise KeyError(device_name)
            config = self._build_device_config(db, device, registration_states)
        self._spawn_one(config)
        return "started"

    def stop_actor_for_device(self, device_name: str) -> str:
        """Stop the actor for ``device_name`` if running.

        Returns ``"stopped"`` or ``"already_stopped"``.
        """
        actor = self._actors.pop(device_name, None)
        if actor is None:
            return "already_stopped"
        try:
            actor.stop(block=True, timeout=2.0)
        except Exception:  # noqa: BLE001
            logger.exception("Error stopping actor for %s", device_name)
        return "stopped"

    # Inbound message dispatch ----------------------------------------------

    def _on_inbound(self, topic: str, payload: bytes) -> None:
        parsed = parse_inbound_topic(topic)
        if parsed is None:
            logger.warning("Ignoring unknown inbound topic: %s", topic)
            return

        if parsed.kind is InboundTopicKind.REGISTER_REQUEST:
            self._dispatch_register_request(parsed.version, payload)
            return

        actor = self._actors.get(parsed.device_name or "")
        if actor is None:
            logger.warning(
                "Inbound %s for unknown device %s; ignoring.",
                parsed.kind.value,
                parsed.device_name,
            )
            return

        try:
            if parsed.kind is InboundTopicKind.ACK:
                from firefly_api.firefly.protocol import AckIn

                ack = AckIn.model_validate_json(payload)
                actor.tell({"type": "ack", "event_id": ack.event_id})
            elif parsed.kind is InboundTopicKind.ERROR:
                from firefly_api.firefly.protocol import ErrorIn

                err = ErrorIn.model_validate_json(payload)
                actor.tell(
                    {
                        "type": "error",
                        "event_id": err.event_id,
                        "error_code": err.error_code,
                        "error_descr": err.error_descr,
                    }
                )
            elif parsed.kind is InboundTopicKind.KEEPALIVE:
                # Keepalive payload is optional; we don't need its contents.
                actor.tell({"type": "keepalive"})
        except ValidationError as exc:
            logger.warning(
                "Malformed payload on topic %s; ignoring: %s", topic, exc
            )

    def _dispatch_register_request(self, version: str, payload: bytes) -> None:
        try:
            request = RegistrationRequestIn.model_validate_json(payload)
        except ValidationError as exc:
            logger.warning("Malformed register-req payload; ignoring: %s", exc)
            return
        actor = self._actors.get(request.device_id)
        if actor is None:
            logger.warning(
                "register-req for unknown device %s; ignoring.", request.device_id
            )
            return
        actor.tell(
            {
                "type": "register_request",
                "request": request,
                "request_version": version,
            }
        )

    # Spawning ---------------------------------------------------------------

    def _spawn_actors_for_all_devices(self) -> None:
        with self._session_factory() as db:
            devices = db.scalars(select(FireflyDevice).order_by(FireflyDevice.id)).all()
            led_states = db.scalars(
                select(FireflyLedState).order_by(FireflyLedState.id)
            ).all()
            registration_states = tuple(_to_registration_states(led_states))
            for device in devices:
                config = self._build_device_config(db, device, registration_states)
                self._spawn_one(config)

    def _spawn_one(self, config: DeviceConfig) -> pykka.ActorRef:
        actor_ref = FireflyDeviceActor.start(
            config=config,
            settings=self._settings,
            publisher=self._mqtt,
            event_log=self._event_log,
        )
        self._actors[config.device_name] = actor_ref
        return actor_ref

    def _build_device_config(
        self,
        db: Session,
        device: FireflyDevice,
        registration_states: tuple[LedStateOut, ...],
    ) -> DeviceConfig:
        segments = db.scalars(
            select(FireflySegment)
            .where(FireflySegment.device_id == device.id)
            .order_by(FireflySegment.id)
        ).all()
        slots = db.scalars(
            select(FireflySlot)
            .where(FireflySlot.device_id == device.id)
            .order_by(FireflySlot.slot_index)
        ).all()
        segment_by_id = {seg.id: seg for seg in segments}

        registration_segments = tuple(
            SegmentOut(
                channel=seg.channel_num,
                ch_segm=seg.segment_num_in_channel,
                first_led_inx=seg.first_led_index,
                last_led_inx=seg.last_led_index,
            )
            for seg in segments
        )

        init_slots = tuple(
            InitSlotsSlot(
                slot_inx=slot.slot_index,
                channel=segment_by_id[slot.segment_id].channel_num,
                ch_segm=segment_by_id[slot.segment_id].segment_num_in_channel,
                pos_in_segm=slot.segment_position,
                num_leds=slot.num_leds,
            )
            for slot in slots
        )

        return DeviceConfig(
            device_id=device.id,
            device_name=device.name,
            init_slots=init_slots,
            registration_segments=registration_segments,
            registration_states=registration_states,
        )


def _to_registration_states(
    led_states: Iterable[FireflyLedState],
) -> Iterable[LedStateOut]:
    for s in led_states:
        yield LedStateOut(
            name=s.name,
            rgb=s.rgb,
            color1_on_ms=s.color1_on_ms,
            color1_fade_up_ms=s.color1_fade_up_ms,
            color1_fade_down_ms=s.color1_fade_down_ms,
            repeat_after_ms=s.repeat_after_ms,
            num_rep=s.num_repetitions,
        )


__all__ = ["ActorRegistry"]
