"""Public integration API request/response schemas (§8)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime
from firefly_api.schemas.slots import EXTERNAL_SLOT_ID_PATTERN


class UpdateSlotIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    external_slot_id: str = Field(alias="externalSlotId", pattern=EXTERNAL_SLOT_ID_PATTERN)
    state_name: str = Field(alias="stateName", min_length=1)
    pattern: str = "full"
    pattern_value: int = Field(default=0, alias="patternValue", ge=0)


class UpdateFireflySlotsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slots: list[UpdateSlotIn]
    client_request_id: str | None = Field(default=None, alias="clientRequestId")
    timeout_ms: int | None = Field(default=None, alias="timeoutMs", ge=1)


class UpdateAllSlotsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state_name: str = Field(alias="stateName", min_length=1)
    pattern: str = "full"
    pattern_value: int = Field(default=0, alias="patternValue", ge=0)
    client_request_id: str | None = Field(default=None, alias="clientRequestId")
    timeout_ms: int | None = Field(default=None, alias="timeoutMs", ge=1)


class LoadSlotIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    external_slot_id: str = Field(alias="externalSlotId", pattern=EXTERNAL_SLOT_ID_PATTERN)
    num_leds: int = Field(alias="numLeds", ge=1)


class LoadSlotsSegmentIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channel_num: int = Field(alias="channelNum", ge=1)
    segment_num_in_channel: int = Field(alias="segmentNumInChannel", ge=1)
    slots: list[LoadSlotIn]


class LoadSlotsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    segments: list[LoadSlotsSegmentIn] = Field(min_length=1)


class CommandResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_name: str = Field(alias="deviceName")
    status: str
    event_id: str = Field(alias="eventId")
    current_task_id: str | None = Field(default=None, alias="currentTaskId")
    client_request_id: str | None = Field(default=None, alias="clientRequestId")


class DeviceStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_name: str = Field(alias="deviceName")
    status: str
    firmware_version: str | None = Field(default=None, alias="firmwareVersion")
    mac_address: str | None = Field(default=None, alias="macAddress")
    registered_at: UtcDateTime | None = Field(default=None, alias="registeredAt")
    last_keepalive_at: UtcDateTime | None = Field(default=None, alias="lastKeepaliveAt")
    current_task_id: str | None = Field(default=None, alias="currentTaskId")
