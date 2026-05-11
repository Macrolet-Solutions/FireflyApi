"""Shared Pydantic primitives for API schemas.

The §8 timestamp convention is RFC 3339 / ISO 8601 in UTC with a trailing ``Z``
and millisecond precision (e.g. ``2026-05-07T10:15:00.123Z``). The
``UtcDateTime`` annotated type ensures every datetime serialized through a
Pydantic model uses that format on the wire while remaining a TZ-aware
``datetime`` in Python.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def to_iso_millis_z(value: datetime) -> str:
    """Serialize a datetime to ``YYYY-MM-DDTHH:MM:SS.mmmZ`` UTC.

    Naive datetimes are treated as UTC. This accommodates SQLite, which
    strips ``tzinfo`` on reads even when the column is declared
    ``DateTime(timezone=True)``. The §7 contract is that all stored
    timestamps are UTC, so this is consistent with the data model.
    """
    if value.tzinfo is None:
        utc = value.replace(tzinfo=timezone.utc)
    else:
        utc = value.astimezone(timezone.utc)
    return f"{utc.strftime('%Y-%m-%dT%H:%M:%S.')}{utc.microsecond // 1000:03d}Z"


UtcDateTime = Annotated[
    datetime,
    PlainSerializer(to_iso_millis_z, return_type=str, when_used="json"),
]
