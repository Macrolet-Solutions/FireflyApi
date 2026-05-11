"""Admin CRUD for ``/api/v1/admin/fireflies/{deviceId}/segments`` (§9, §7.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from firefly_api.db.repositories import segments as repo
from firefly_api.db.session import get_db
from firefly_api.schemas.segments import (
    FireflySegmentCreate,
    FireflySegmentOut,
    FireflySegmentUpdate,
)

router = APIRouter(prefix="/fireflies/{device_id}/segments", tags=["admin:segments"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[FireflySegmentOut])
def list_segments(device_id: int, db: DbSession) -> list:
    return repo.list_for_device(db, device_id)


@router.get("/{segment_id}", response_model=FireflySegmentOut)
def get_segment(device_id: int, segment_id: int, db: DbSession) -> object:
    return repo.get_by_id(db, device_id, segment_id)


@router.post("", response_model=FireflySegmentOut, status_code=status.HTTP_201_CREATED)
def create_segment(device_id: int, data: FireflySegmentCreate, db: DbSession) -> object:
    return repo.create(db, device_id, data)


@router.put("/{segment_id}", response_model=FireflySegmentOut)
def update_segment(
    device_id: int,
    segment_id: int,
    data: FireflySegmentUpdate,
    db: DbSession,
) -> object:
    return repo.update(db, device_id, segment_id, data)


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_segment(device_id: int, segment_id: int, db: DbSession) -> None:
    repo.delete(db, device_id, segment_id)
