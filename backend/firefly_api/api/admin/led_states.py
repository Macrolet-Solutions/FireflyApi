"""Admin CRUD for ``/api/v1/admin/led-states`` (§9, §7.5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from firefly_api.db.repositories import led_states as repo
from firefly_api.db.session import get_db
from firefly_api.schemas.led_states import (
    FireflyLedStateCreate,
    FireflyLedStateOut,
    FireflyLedStateUpdate,
)

router = APIRouter(prefix="/led-states", tags=["admin:led-states"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[FireflyLedStateOut])
def list_led_states(db: DbSession) -> list:
    return repo.list_all(db)


@router.get("/{state_id}", response_model=FireflyLedStateOut)
def get_led_state(state_id: int, db: DbSession) -> object:
    return repo.get_by_id(db, state_id)


@router.post("", response_model=FireflyLedStateOut, status_code=status.HTTP_201_CREATED)
def create_led_state(data: FireflyLedStateCreate, db: DbSession) -> object:
    return repo.create(db, data)


@router.put("/{state_id}", response_model=FireflyLedStateOut)
def update_led_state(state_id: int, data: FireflyLedStateUpdate, db: DbSession) -> object:
    return repo.update(db, state_id, data)


@router.delete("/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_led_state(state_id: int, db: DbSession) -> None:
    repo.delete(db, state_id)
