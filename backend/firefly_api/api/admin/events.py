"""Admin read endpoints for the ``firefly_events`` log (§7.7, §9)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from firefly_api.core.errors import NotFoundError
from firefly_api.db.models import FireflyEvent
from firefly_api.db.session import get_db
from firefly_api.schemas.events import FireflyEventOut

router = APIRouter(prefix="/events", tags=["admin:events"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[FireflyEventOut])
def list_events(
    db: DbSession,
    device_id: Annotated[int | None, Query(alias="deviceId", ge=1)] = None,
    event_type: Annotated[str | None, Query(alias="eventType")] = None,
    before_id: Annotated[
        int | None,
        Query(alias="beforeId", description="Return rows with id < this (pagination)."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list:
    stmt = select(FireflyEvent)
    if device_id is not None:
        stmt = stmt.where(FireflyEvent.device_id == device_id)
    if event_type is not None:
        stmt = stmt.where(FireflyEvent.event_type == event_type)
    if before_id is not None:
        stmt = stmt.where(FireflyEvent.id < before_id)
    stmt = stmt.order_by(FireflyEvent.id.desc()).limit(limit)
    return list(db.scalars(stmt))


@router.get("/{event_id}", response_model=FireflyEventOut)
def get_event(event_id: int, db: DbSession) -> object:
    row = db.get(FireflyEvent, event_id)
    if row is None:
        raise NotFoundError(
            f"Event {event_id} not found.", error_code="event_not_found"
        )
    return row
