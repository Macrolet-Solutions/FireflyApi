"""Firefly LED state request/response schemas (§7.5)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime

RGB_PATTERN = r"^0x[0-9A-Fa-f]{6}$"


class _LedStateBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    name: str = Field(min_length=1, max_length=100)
    rgb: str = Field(pattern=RGB_PATTERN)
    color1_on_ms: int = Field(default=0, ge=0)
    color1_fade_up_ms: int = Field(default=0, ge=0)
    color1_fade_down_ms: int = Field(default=0, ge=0)
    repeat_after_ms: int = Field(default=0, ge=0)
    num_repetitions: int = Field(default=0, ge=0)


class FireflyLedStateCreate(_LedStateBase):
    pass


class FireflyLedStateUpdate(_LedStateBase):
    pass


class FireflyLedStateOut(_LedStateBase):
    id: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
