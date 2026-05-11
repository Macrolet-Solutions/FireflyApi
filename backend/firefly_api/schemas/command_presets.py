"""Firefly command preset request/response schemas (§7.6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime


class _PresetBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    name: str = Field(min_length=1, max_length=100)
    led_state_id: int
    pattern: int = Field(ge=0, le=4)
    pattern_value: int = Field(default=0, ge=0)


class FireflyCommandPresetCreate(_PresetBase):
    pass


class FireflyCommandPresetUpdate(_PresetBase):
    pass


class FireflyCommandPresetOut(_PresetBase):
    id: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
