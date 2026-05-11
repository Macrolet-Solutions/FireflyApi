"""Firefly slot request/response schemas (§7.4).

Notes:

- ``slot_index`` is server-assigned and only appears in the ``Out`` shape.
  Clients must not send it on POST or PUT (§7.4).
- ``segment_id`` and ``segment_position`` are immutable on PUT and therefore
  only appear in the ``Create`` shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from firefly_api.schemas.common import UtcDateTime

EXTERNAL_SLOT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class FireflySlotCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    segment_id: int
    external_slot_id: str = Field(pattern=EXTERNAL_SLOT_ID_PATTERN)
    label: str | None = Field(default=None, max_length=255)
    segment_position: int = Field(ge=1)
    num_leds: int = Field(ge=1)


class FireflySlotUpdate(BaseModel):
    """Mutable PUT fields (§7.4): external_slot_id, label, num_leds."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    external_slot_id: str = Field(pattern=EXTERNAL_SLOT_ID_PATTERN)
    label: str | None = Field(default=None, max_length=255)
    num_leds: int = Field(ge=1)


class FireflySlotOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int
    device_id: int
    segment_id: int
    slot_index: int
    external_slot_id: str
    label: str | None
    segment_position: int
    num_leds: int
    created_at: UtcDateTime
    updated_at: UtcDateTime
