"""Tests that the error envelope shape is consistent (§8.4)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _assert_envelope(body: dict) -> None:
    assert set(body.keys()) >= {"errorCode", "errorDescription", "details"}
    assert isinstance(body["errorCode"], str)
    assert isinstance(body["errorDescription"], str)
    assert isinstance(body["details"], dict)


def test_404_for_unknown_route_uses_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/admin/does-not-exist")
    assert r.status_code == 404
    _assert_envelope(r.json())


def test_404_for_known_resource_id_uses_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/admin/mqtt-brokers/9999")
    assert r.status_code == 404
    body = r.json()
    _assert_envelope(body)
    assert body["errorCode"] == "broker_not_found"


def test_422_validation_error_uses_envelope(client: TestClient) -> None:
    r = client.post(
        "/api/v1/admin/mqtt-brokers",
        json={"name": "", "host": "x", "port": 1883},
    )
    assert r.status_code == 422
    body = r.json()
    _assert_envelope(body)
