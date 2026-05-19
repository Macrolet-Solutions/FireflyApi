"""Pydantic models for Firefly MQTT JSON payloads (§6.3).

Field aliases match the wire format exactly (``firmware-version``,
``event-id``, etc.). Use ``model_dump(by_alias=True)`` when serializing
to JSON for publish, and ``Model.model_validate_json(...)`` when parsing
an incoming payload.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Inbound payloads -----------------------------------------------------------


class RegistrationRequestIn(BaseModel):
    """``cmd/ptm/register-req/{version}`` payload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    firmware_version: str = Field(alias="firmware-version")
    device_id: str = Field(alias="device-id")
    device_mac: str = Field(alias="device-mac")


class AckIn(BaseModel):
    """``ptm/{v}/{name}/ack`` payload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event_id: str = Field(alias="event-id")


class ErrorIn(BaseModel):
    """``ptm/{v}/{name}/error`` payload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event_id: str = Field(alias="event-id")
    error_code: str = Field(alias="error-code")
    error_descr: str | None = Field(default=None, alias="error-descr")

    @field_validator("error_code", mode="before")
    @classmethod
    def _coerce_error_code(cls, value: object) -> object:
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value


class KeepaliveIn(BaseModel):
    """``ptm/{v}/{name}/keepalive`` payload."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    free_memory: int | None = Field(default=None, alias="free-memory")
    battery: int | None = Field(default=None, alias="battery")


# Outbound payloads ----------------------------------------------------------


class SegmentOut(BaseModel):
    """One segment entry in the registration response."""

    model_config = ConfigDict(populate_by_name=True)

    channel: int
    ch_segm: int = Field(alias="ch-segm")
    first_led_inx: int = Field(alias="first-led-inx")
    last_led_inx: int = Field(alias="last-led-inx")


class LedStateOut(BaseModel):
    """One state entry in the registration response."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    rgb: str
    color1_on_ms: int = Field(default=0, alias="color1-on-ms")
    color1_fade_up_ms: int = Field(default=0, alias="color1-fade-up-ms")
    color1_fade_down_ms: int = Field(default=0, alias="color1-fade-down-ms")
    repeat_after_ms: int = Field(default=0, alias="repeat-after-ms")
    num_rep: int = Field(default=0, alias="num-rep")


class RegistrationResponseOut(BaseModel):
    """``ff/{v}/{name}/register-resp`` payload."""

    model_config = ConfigDict(populate_by_name=True)

    is_error: bool = Field(alias="is-error")
    error_descr: str = Field(default="", alias="error-descr")
    event_id: str = Field(alias="event-id")
    device_type: str = Field(alias="device-type")
    segments: list[SegmentOut] = Field(default_factory=list)
    states: list[LedStateOut] = Field(default_factory=list)


class InitSlotsSlot(BaseModel):
    """One slot entry inside an ``init-slots`` payload."""

    model_config = ConfigDict(populate_by_name=True)

    slot_inx: int = Field(alias="slot-inx")
    channel: int
    ch_segm: int = Field(alias="ch-segm")
    pos_in_segm: int = Field(alias="pos-in-segm")
    num_leds: int = Field(alias="num-leds")


class InitSlotsOut(BaseModel):
    """``ff/{v}/{name}/init-slots`` payload."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="event-id")
    task_id: str = Field(alias="task-id")
    num_slots: int = Field(alias="num-slots")
    slots: list[InitSlotsSlot]


class UpdateSlotStateSlot(BaseModel):
    """One slot entry inside an ``update-slot-state`` payload."""

    model_config = ConfigDict(populate_by_name=True)

    slot_inx: int = Field(alias="slot-inx")
    to_state: str = Field(alias="to-state")
    pattern: int = 0
    pattern_value: int = Field(default=0, alias="pattern-value")


class UpdateSlotStateOut(BaseModel):
    """``ff/{v}/{name}/update-slot-state`` payload."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="event-id")
    task_id: str = Field(alias="task-id")
    slots: list[UpdateSlotStateSlot]


class UpdateAllSlotsOut(BaseModel):
    """``ff/{v}/{name}/update-all-slots`` payload."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="event-id")
    task_id: str = Field(alias="task-id")
    to_state: str = Field(alias="to-state")
    pattern: int = 0
    pattern_value: int = Field(default=0, alias="pattern-value")
