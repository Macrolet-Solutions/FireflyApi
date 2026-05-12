"""``firefly_events`` read schemas (§9 events admin endpoints)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime


class FireflyEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    device_id: int = Field(alias="deviceId")
    event_id: str = Field(alias="eventId")
    event_type: str = Field(alias="eventType")
    task_id: str | None = Field(default=None, alias="taskId")
    payload_json: dict[str, Any] | None = Field(default=None, alias="payloadJson")
    error_code: str | None = Field(default=None, alias="errorCode")
    error_description: str | None = Field(default=None, alias="errorDescription")
    created_at: UtcDateTime = Field(alias="createdAt")
