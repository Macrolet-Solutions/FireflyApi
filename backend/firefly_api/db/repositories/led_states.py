"""Repository for ``firefly_led_states`` (§7.5)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError
from firefly_api.db.models import FireflyCommandPreset, FireflyLedState
from firefly_api.schemas.led_states import FireflyLedStateCreate, FireflyLedStateUpdate


def list_all(db: Session) -> list[FireflyLedState]:
    return list(
        db.scalars(select(FireflyLedState).order_by(FireflyLedState.id))
    )


def get_by_id(db: Session, state_id: int) -> FireflyLedState:
    state = db.get(FireflyLedState, state_id)
    if state is None:
        raise NotFoundError(
            f"LED state {state_id} not found.", error_code="led_state_not_found"
        )
    return state


def create(db: Session, data: FireflyLedStateCreate) -> FireflyLedState:
    state = FireflyLedState(**data.model_dump())
    db.add(state)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"LED state name '{data.name}' already in use.",
            error_code="led_state_name_conflict",
        ) from exc
    db.refresh(state)
    return state


def update(db: Session, state_id: int, data: FireflyLedStateUpdate) -> FireflyLedState:
    state = get_by_id(db, state_id)
    for field, value in data.model_dump().items():
        setattr(state, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"LED state name '{data.name}' already in use.",
            error_code="led_state_name_conflict",
        ) from exc
    db.refresh(state)
    return state


def delete(db: Session, state_id: int) -> None:
    state = get_by_id(db, state_id)
    preset_id = db.scalar(
        select(FireflyCommandPreset.id)
        .where(FireflyCommandPreset.led_state_id == state_id)
        .limit(1)
    )
    if preset_id is not None:
        raise ConflictError(
            f"LED state {state_id} is referenced by one or more command presets.",
            error_code="led_state_in_use",
        )
    db.delete(state)
    db.commit()
