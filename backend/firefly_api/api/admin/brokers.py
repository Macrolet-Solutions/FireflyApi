"""Admin CRUD for ``/api/v1/admin/mqtt-brokers`` (§9, §7.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from firefly_api.db.repositories import brokers as repo
from firefly_api.db.session import get_db
from firefly_api.firefly.mqtt.client import PahoMqttClient
from firefly_api.schemas.brokers import MqttBrokerCreate, MqttBrokerOut, MqttBrokerUpdate
from firefly_api.schemas.common import to_iso_millis_z

router = APIRouter(prefix="/mqtt-brokers", tags=["admin:mqtt-brokers"])

DbSession = Annotated[Session, Depends(get_db)]


CONNECT_TIMEOUT_S = 5.0


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


@router.post("/{broker_id}:test-connection")
def test_connection(broker_id: int, db: DbSession) -> JSONResponse:
    """Open a transient MQTT connection (§9.1).

    On success returns 200 with ``{brokerId, success: true, connectedAt}``.
    On failure returns 502 with ``{brokerId, success: false, errorCode,
    errorDescription}``.
    """
    broker = repo.get_by_id(db, broker_id)
    client = PahoMqttClient(
        host=broker.host,
        port=broker.port,
        username=broker.username,
        password=broker.password,
        use_tls=broker.use_tls,
        client_id=broker.client_id,
    )
    client._connect_timeout_s = CONNECT_TIMEOUT_S  # noqa: SLF001 (private knob)
    try:
        client.connect()
    except TimeoutError:
        return JSONResponse(
            status_code=502,
            content={
                "brokerId": broker.id,
                "success": False,
                "errorCode": "broker_unreachable",
                "errorDescription": (
                    f"connect timeout after {int(CONNECT_TIMEOUT_S * 1000)} ms"
                ),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={
                "brokerId": broker.id,
                "success": False,
                "errorCode": "broker_protocol_error",
                "errorDescription": str(exc),
            },
        )
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return JSONResponse(
        status_code=200,
        content={
            "brokerId": broker.id,
            "success": True,
            "connectedAt": to_iso_millis_z(datetime.now(timezone.utc)),
        },
    )
