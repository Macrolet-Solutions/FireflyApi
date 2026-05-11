"""Firefly device request/response schemas (§7.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime


class _DeviceBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    name: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    mqtt_broker_id: int


class FireflyDeviceCreate(_DeviceBase):
    pass


class FireflyDeviceUpdate(_DeviceBase):
    pass


class FireflyDeviceOut(_DeviceBase):
    id: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
