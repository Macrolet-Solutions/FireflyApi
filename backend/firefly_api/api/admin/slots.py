"""Admin CRUD for ``/api/v1/admin/fireflies/{deviceId}/slots`` (§9, §7.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from firefly_api.db.repositories import slots as repo
from firefly_api.db.session import get_db
from firefly_api.schemas.slots import (
    FireflySlotCreate,
    FireflySlotOut,
    FireflySlotReplaceRequest,
    FireflySlotUpdate,
)

router = APIRouter(prefix="/fireflies/{device_id}/slots", tags=["admin:slots"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[FireflySlotOut])
def list_slots(device_id: int, db: DbSession) -> list:
    return repo.list_for_device(db, device_id)


@router.get("/{slot_id}", response_model=FireflySlotOut)
def get_slot(device_id: int, slot_id: int, db: DbSession) -> object:
    return repo.get_by_id(db, device_id, slot_id)


@router.post("", response_model=FireflySlotOut, status_code=status.HTTP_201_CREATED)
def create_slot(device_id: int, data: FireflySlotCreate, db: DbSession) -> object:
    return repo.create(db, device_id, data)


@router.put(":replace", response_model=list[FireflySlotOut])
def replace_slots(
    device_id: int,
    data: FireflySlotReplaceRequest,
    db: DbSession,
) -> list:
    return repo.replace_for_device(db, device_id, data.slots)


@router.put("/{slot_id}", response_model=FireflySlotOut)
def update_slot(
    device_id: int,
    slot_id: int,
    data: FireflySlotUpdate,
    db: DbSession,
) -> object:
    return repo.update(db, device_id, slot_id, data)


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slot(device_id: int, slot_id: int, db: DbSession) -> None:
    repo.delete(db, device_id, slot_id)
