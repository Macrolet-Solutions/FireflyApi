"""Admin CRUD for ``/api/v1/admin/mqtt-brokers`` (§9, §7.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from firefly_api.db.repositories import brokers as repo
from firefly_api.db.session import get_db
from firefly_api.schemas.brokers import MqttBrokerCreate, MqttBrokerOut, MqttBrokerUpdate

router = APIRouter(prefix="/mqtt-brokers", tags=["admin:mqtt-brokers"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[MqttBrokerOut])
def list_brokers(db: DbSession) -> list:
    return repo.list_all(db)


@router.get("/{broker_id}", response_model=MqttBrokerOut)
def get_broker(broker_id: int, db: DbSession) -> object:
    return repo.get_by_id(db, broker_id)


@router.post("", response_model=MqttBrokerOut, status_code=status.HTTP_201_CREATED)
def create_broker(data: MqttBrokerCreate, db: DbSession) -> object:
    return repo.create(db, data)


@router.put("/{broker_id}", response_model=MqttBrokerOut)
def update_broker(broker_id: int, data: MqttBrokerUpdate, db: DbSession) -> object:
    return repo.update(db, broker_id, data)


@router.delete("/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_broker(broker_id: int, db: DbSession) -> None:
    repo.delete(db, broker_id)
