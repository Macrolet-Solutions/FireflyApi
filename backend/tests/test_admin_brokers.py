"""HTTP tests for ``/api/v1/admin/mqtt-brokers`` (§7.1, §9)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_payload(**overrides: object) -> dict:
    payload = {
        "name": "main",
        "host": "broker.example.com",
        "port": 1883,
        "username": "u",
        "password": "p",
        "use_tls": False,
        "client_id": "firefly-api",
    }
    payload.update(overrides)
    return payload


def test_list_empty_initially(client: TestClient) -> None:
    r = client.get("/api/v1/admin/mqtt-brokers")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_get_roundtrip(client: TestClient) -> None:
    r = client.post("/api/v1/admin/mqtt-brokers", json=_create_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "main"
    assert body["host"] == "broker.example.com"
    assert body["port"] == 1883
    # Password must never be returned (§12).
    assert "password" not in body

    r = client.get(f"/api/v1/admin/mqtt-brokers/{body['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == body["id"]
    assert "password" not in r.json()


def test_second_create_rejected_with_409(client: TestClient) -> None:
    client.post("/api/v1/admin/mqtt-brokers", json=_create_payload())
    r = client.post(
        "/api/v1/admin/mqtt-brokers", json=_create_payload(name="second")
    )
    assert r.status_code == 409
    assert r.json()["errorCode"] == "broker_already_configured"


def test_update_changes_fields_without_blanking_password(client: TestClient) -> None:
    created = client.post(
        "/api/v1/admin/mqtt-brokers", json=_create_payload(password="initial")
    ).json()
    update = _create_payload(host="other.example.com")
    update["password"] = None  # explicit null -> leave password unchanged
    r = client.put(f"/api/v1/admin/mqtt-brokers/{created['id']}", json=update)
    assert r.status_code == 200
    assert r.json()["host"] == "other.example.com"


def test_delete_with_device_returns_409(client: TestClient, broker: dict) -> None:
    client.post(
        "/api/v1/admin/fireflies",
        json={"name": "FF01", "mqtt_broker_id": broker["id"]},
    )
    r = client.delete(f"/api/v1/admin/mqtt-brokers/{broker['id']}")
    assert r.status_code == 409
    assert r.json()["errorCode"] == "broker_in_use"


def test_delete_when_unreferenced_succeeds(client: TestClient, broker: dict) -> None:
    r = client.delete(f"/api/v1/admin/mqtt-brokers/{broker['id']}")
    assert r.status_code == 204
    assert client.get("/api/v1/admin/mqtt-brokers").json() == []


def test_get_unknown_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/admin/mqtt-brokers/9999")
    assert r.status_code == 404
    assert r.json()["errorCode"] == "broker_not_found"
