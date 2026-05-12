"""Admin action endpoint schemas (§9.1-§9.6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime


# §9.1 broker test-connection -------------------------------------------------


class TestConnectionSuccess(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    broker_id: int = Field(alias="brokerId")
    success: bool = True
    connected_at: UtcDateTime = Field(alias="connectedAt")


class TestConnectionFailure(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    broker_id: int = Field(alias="brokerId")
    success: bool = False
    error_code: str = Field(alias="errorCode")
    error_description: str = Field(alias="errorDescription")


# §9.2 / §9.3 start-actor / stop-actor ---------------------------------------


class ActorLifecycleResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_id: int = Field(alias="deviceId")
    actor_status: str = Field(alias="actorStatus")


# §9.4 reinitialize ----------------------------------------------------------


class ReinitializeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timeout_ms: int | None = Field(default=None, alias="timeoutMs", ge=1)


class ReinitializeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_id: int = Field(alias="deviceId")
    status: str
    event_id: str = Field(alias="eventId")
    current_task_id: str | None = Field(default=None, alias="currentTaskId")


# §9.5 slots:test (admin manual test panel) ----------------------------------


class TestSlotIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slot_id: int = Field(alias="slotId")
    state_name: str = Field(alias="stateName", min_length=1)
    pattern: str = "full"
    pattern_value: int = Field(default=0, alias="patternValue", ge=0)


class TestSlotsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slots: list[TestSlotIn]
    timeout_ms: int | None = Field(default=None, alias="timeoutMs", ge=1)


class TestSlotsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_name: str = Field(alias="deviceName")
    status: str
    event_id: str = Field(alias="eventId")
    current_task_id: str | None = Field(default=None, alias="currentTaskId")


# §9.6 reset -----------------------------------------------------------------


class ResetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    device_id: int = Field(alias="deviceId")
    status: str
    event_id: str = Field(alias="eventId")
