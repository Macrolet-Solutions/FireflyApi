"""Admin CRUD for ``/api/v1/admin/fireflies`` (§9, §7.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from firefly_api.db.repositories import devices as repo
from firefly_api.db.session import get_db
from firefly_api.schemas.devices import (
    FireflyDeviceCreate,
    FireflyDeviceOut,
    FireflyDeviceUpdate,
)

router = APIRouter(prefix="/fireflies", tags=["admin:fireflies"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[FireflyDeviceOut])
def list_devices(db: DbSession) -> list:
    return repo.list_all(db)


@router.get("/{device_id}", response_model=FireflyDeviceOut)
def get_device(device_id: int, db: DbSession) -> object:
    return repo.get_by_id(db, device_id)


@router.post("", response_model=FireflyDeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(data: FireflyDeviceCreate, db: DbSession) -> object:
    return repo.create(db, data)


@router.put("/{device_id}", response_model=FireflyDeviceOut)
def update_device(device_id: int, data: FireflyDeviceUpdate, db: DbSession) -> object:
    return repo.update(db, device_id, data)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int, db: DbSession) -> None:
    repo.delete(db, device_id)
