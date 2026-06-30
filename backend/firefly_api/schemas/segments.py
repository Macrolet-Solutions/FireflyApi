"""Firefly segment request/response schemas (§7.3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime


class _SegmentBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    channel_num: int = Field(ge=1)
    segment_num_in_channel: int = Field(ge=1)
    first_led_index: int = Field(ge=1)
    last_led_index: int = Field(ge=1)
    mode: Literal["static", "dynamic"] = "static"


class FireflySegmentCreate(_SegmentBase):
    pass


class FireflySegmentUpdate(_SegmentBase):
    pass


class FireflySegmentOut(_SegmentBase):
    id: int
    device_id: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
