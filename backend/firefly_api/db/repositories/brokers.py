"""Repository for ``mqtt_brokers`` (§7.1).

Version 1 enforces a single-row constraint at the application layer: ``create``
raises :class:`firefly_api.core.errors.ConflictError` with code
``broker_already_configured`` when a row already exists.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from firefly_api.core.errors import ConflictError, NotFoundError
from firefly_api.db.models import FireflyDevice, MqttBroker
from firefly_api.schemas.brokers import MqttBrokerCreate, MqttBrokerUpdate


def list_all(db: Session) -> list[MqttBroker]:
    return list(db.scalars(select(MqttBroker).order_by(MqttBroker.id)))


def get_by_id(db: Session, broker_id: int) -> MqttBroker:
    broker = db.get(MqttBroker, broker_id)
    if broker is None:
        raise NotFoundError(
            f"MQTT broker {broker_id} not found.", error_code="broker_not_found"
        )
    return broker


def _has_any(db: Session) -> bool:
    return db.scalar(select(MqttBroker.id).limit(1)) is not None


def create(db: Session, data: MqttBrokerCreate) -> MqttBroker:
    if _has_any(db):
        raise ConflictError(
            "Only one MQTT broker may be configured.",
            error_code="broker_already_configured",
        )
    broker = MqttBroker(**data.model_dump())
    db.add(broker)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Broker name already in use.", error_code="broker_name_conflict"
        ) from exc
    db.refresh(broker)
    return broker


def update(db: Session, broker_id: int, data: MqttBrokerUpdate) -> MqttBroker:
    broker = get_by_id(db, broker_id)
    payload = data.model_dump(exclude_unset=False)
    if data.password is None:
        # An omitted/null password on PUT means "leave the stored password
        # unchanged" rather than "blank the password". This matches the
        # admin UI workflow where the password field is normally redacted.
        payload.pop("password", None)
    for field, value in payload.items():
        setattr(broker, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Broker name already in use.", error_code="broker_name_conflict"
        ) from exc
    db.refresh(broker)
    return broker


def delete(db: Session, broker_id: int) -> None:
    broker = get_by_id(db, broker_id)
    device_count = db.scalar(
        select(FireflyDevice.id)
        .where(FireflyDevice.mqtt_broker_id == broker_id)
        .limit(1)
    )
    if device_count is not None:
        raise ConflictError(
            f"Broker {broker_id} is referenced by one or more devices.",
            error_code="broker_in_use",
        )
    db.delete(broker)
    db.commit()
