"""Repository for ``firefly_devices`` (§7.2)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError, ValidationFailedError
from firefly_api.db.models import FireflyDevice, MqttBroker
from firefly_api.schemas.devices import FireflyDeviceCreate, FireflyDeviceUpdate


def list_all(db: Session) -> list[FireflyDevice]:
    return list(db.scalars(select(FireflyDevice).order_by(FireflyDevice.id)))


def get_by_id(db: Session, device_id: int) -> FireflyDevice:
    device = db.get(FireflyDevice, device_id)
    if device is None:
        raise NotFoundError(
            f"Device {device_id} not found.", error_code="device_not_found"
        )
    return device


def _ensure_broker_exists(db: Session, broker_id: int) -> None:
    if db.get(MqttBroker, broker_id) is None:
        raise ValidationFailedError(
            f"MQTT broker {broker_id} does not exist.",
            error_code="invalid_mqtt_broker_id",
        )


def create(db: Session, data: FireflyDeviceCreate) -> FireflyDevice:
    _ensure_broker_exists(db, data.mqtt_broker_id)
    device = FireflyDevice(**data.model_dump())
    db.add(device)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Device name '{data.name}' already in use.",
            error_code="device_name_conflict",
        ) from exc
    db.refresh(device)
    return device


def update(db: Session, device_id: int, data: FireflyDeviceUpdate) -> FireflyDevice:
    device = get_by_id(db, device_id)
    if data.mqtt_broker_id != device.mqtt_broker_id:
        _ensure_broker_exists(db, data.mqtt_broker_id)
    for field, value in data.model_dump().items():
        setattr(device, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"Device name '{data.name}' already in use.",
            error_code="device_name_conflict",
        ) from exc
    db.refresh(device)
    return device


def delete(db: Session, device_id: int) -> None:
    device = get_by_id(db, device_id)
    db.delete(device)
    db.commit()
