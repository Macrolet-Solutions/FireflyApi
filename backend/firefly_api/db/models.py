"""SQLAlchemy ORM models for §7 of the spec.

Notes:

- ``created_at`` / ``updated_at`` are timezone-aware UTC. The application is
  responsible for always supplying TZ-aware values (see §7).
- ``firefly_events`` has no ``updated_at`` because rows are insert-only
  (§7.7).
- Foreign-key behavior matches §7.8. SQLite enforces these only when the
  ``PRAGMA foreign_keys = ON`` is set; see :mod:`firefly_api.db.session`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


SEGMENT_MODE_STATIC = "static"
SEGMENT_MODE_DYNAMIC = "dynamic"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class _Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class MqttBroker(Base, _Timestamped):
    __tablename__ = "mqtt_brokers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    devices: Mapped[list[FireflyDevice]] = relationship(back_populates="mqtt_broker")


class FireflyDevice(Base, _Timestamped):
    __tablename__ = "firefly_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mqtt_broker_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mqtt_brokers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    mqtt_broker: Mapped[MqttBroker] = relationship(back_populates="devices")
    segments: Mapped[list[FireflySegment]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    slots: Mapped[list[FireflySlot]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[FireflyEvent]] = relationship(
        back_populates="device", cascade="all, delete-orphan", passive_deletes=True
    )


class FireflySegment(Base, _Timestamped):
    __tablename__ = "firefly_segments"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "channel_num",
            "segment_num_in_channel",
            name="uq_firefly_segments_device_channel_segment",
        ),
        CheckConstraint("first_led_index >= 1", name="ck_firefly_segments_first_led_ge_1"),
        CheckConstraint("last_led_index >= 1", name="ck_firefly_segments_last_led_ge_1"),
        CheckConstraint(
            "mode IN ('static', 'dynamic')",
            name="ck_firefly_segments_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("firefly_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_num: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_num_in_channel: Mapped[int] = mapped_column(Integer, nullable=False)
    first_led_index: Mapped[int] = mapped_column(Integer, nullable=False)
    last_led_index: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SEGMENT_MODE_STATIC
    )

    device: Mapped[FireflyDevice] = relationship(back_populates="segments")
    slots: Mapped[list[FireflySlot]] = relationship(back_populates="segment")

    @property
    def led_count(self) -> int:
        return abs(self.last_led_index - self.first_led_index) + 1


class FireflySlot(Base, _Timestamped):
    __tablename__ = "firefly_slots"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "slot_index", name="uq_firefly_slots_device_slot_index"
        ),
        UniqueConstraint(
            "device_id",
            "external_slot_id",
            name="uq_firefly_slots_device_external_slot_id",
        ),
        CheckConstraint("slot_index >= 1", name="ck_firefly_slots_slot_index_ge_1"),
        CheckConstraint(
            "segment_position >= 1",
            name="ck_firefly_slots_segment_position_ge_1",
        ),
        CheckConstraint("num_leds >= 1", name="ck_firefly_slots_num_leds_ge_1"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("firefly_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("firefly_segments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    external_slot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    segment_position: Mapped[int] = mapped_column(Integer, nullable=False)
    num_leds: Mapped[int] = mapped_column(Integer, nullable=False)

    device: Mapped[FireflyDevice] = relationship(back_populates="slots")
    segment: Mapped[FireflySegment] = relationship(back_populates="slots")


class FireflyLedState(Base, _Timestamped):
    __tablename__ = "firefly_led_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    rgb: Mapped[str] = mapped_column(String(8), nullable=False)
    color1_on_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color1_fade_up_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color1_fade_down_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repeat_after_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    presets: Mapped[list[FireflyCommandPreset]] = relationship(back_populates="led_state")


class FireflyCommandPreset(Base, _Timestamped):
    __tablename__ = "firefly_command_presets"
    __table_args__ = (
        CheckConstraint(
            "pattern BETWEEN 0 AND 4",
            name="ck_firefly_command_presets_pattern_range",
        ),
        CheckConstraint(
            "pattern_value >= 0",
            name="ck_firefly_command_presets_pattern_value_ge_0",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    led_state_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("firefly_led_states.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pattern: Mapped[int] = mapped_column(Integer, nullable=False)
    pattern_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    led_state: Mapped[FireflyLedState] = relationship(back_populates="presets")


class FireflyEvent(Base):
    __tablename__ = "firefly_events"
    __table_args__ = (
        Index("ix_firefly_events_device_created", "device_id", "created_at"),
        Index("ix_firefly_events_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("firefly_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    device: Mapped[FireflyDevice] = relationship(back_populates="events")
