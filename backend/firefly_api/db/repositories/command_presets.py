"""Repository for ``firefly_command_presets`` (§7.6)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError, ValidationFailedError
from firefly_api.db.models import FireflyCommandPreset, FireflyLedState
from firefly_api.schemas.command_presets import (
    FireflyCommandPresetCreate,
    FireflyCommandPresetUpdate,
)


def list_all(db: Session) -> list[FireflyCommandPreset]:
    return list(
        db.scalars(select(FireflyCommandPreset).order_by(FireflyCommandPreset.id))
    )


def get_by_id(db: Session, preset_id: int) -> FireflyCommandPreset:
    preset = db.get(FireflyCommandPreset, preset_id)
    if preset is None:
        raise NotFoundError(
            f"Command preset {preset_id} not found.",
            error_code="command_preset_not_found",
        )
    return preset


def _ensure_led_state_exists(db: Session, led_state_id: int) -> None:
    if db.get(FireflyLedState, led_state_id) is None:
        raise ValidationFailedError(
            f"LED state {led_state_id} does not exist.",
            error_code="invalid_led_state_id",
        )


def create(db: Session, data: FireflyCommandPresetCreate) -> FireflyCommandPreset:
    _ensure_led_state_exists(db, data.led_state_id)
    preset = FireflyCommandPreset(**data.model_dump())
    db.add(preset)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Command preset name '{data.name}' already in use.",
            error_code="command_preset_name_conflict",
        ) from exc
    db.refresh(preset)
    return preset


def update(
    db: Session, preset_id: int, data: FireflyCommandPresetUpdate
) -> FireflyCommandPreset:
    preset = get_by_id(db, preset_id)
    if data.led_state_id != preset.led_state_id:
        _ensure_led_state_exists(db, data.led_state_id)
    for field, value in data.model_dump().items():
        setattr(preset, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Command preset name '{data.name}' already in use.",
            error_code="command_preset_name_conflict",
        ) from exc
    db.refresh(preset)
    return preset


def delete(db: Session, preset_id: int) -> None:
    preset = get_by_id(db, preset_id)
    db.delete(preset)
    db.commit()
