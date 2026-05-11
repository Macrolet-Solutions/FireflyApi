"""Admin CRUD for ``/api/v1/admin/command-presets`` (§9, §7.6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from firefly_api.db.repositories import command_presets as repo
from firefly_api.db.session import get_db
from firefly_api.schemas.command_presets import (
    FireflyCommandPresetCreate,
    FireflyCommandPresetOut,
    FireflyCommandPresetUpdate,
)

router = APIRouter(prefix="/command-presets", tags=["admin:command-presets"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[FireflyCommandPresetOut])
def list_presets(db: DbSession) -> list:
    return repo.list_all(db)


@router.get("/{preset_id}", response_model=FireflyCommandPresetOut)
def get_preset(preset_id: int, db: DbSession) -> object:
    return repo.get_by_id(db, preset_id)


@router.post(
    "", response_model=FireflyCommandPresetOut, status_code=status.HTTP_201_CREATED
)
def create_preset(data: FireflyCommandPresetCreate, db: DbSession) -> object:
    return repo.create(db, data)


@router.put("/{preset_id}", response_model=FireflyCommandPresetOut)
def update_preset(
    preset_id: int, data: FireflyCommandPresetUpdate, db: DbSession
) -> object:
    return repo.update(db, preset_id, data)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(preset_id: int, db: DbSession) -> None:
    repo.delete(db, preset_id)
