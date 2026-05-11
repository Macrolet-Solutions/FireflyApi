"""Standard error response shape (§8.4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    error_code: str = Field(alias="errorCode")
    error_description: str = Field(alias="errorDescription")
    details: dict[str, Any] = Field(default_factory=dict)
