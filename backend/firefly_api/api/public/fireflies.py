"""Public integration endpoints for Firefly devices (§8)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from firefly_api.firefly.service import FireflyService
from firefly_api.schemas.public import (
    CommandResponse,
    DeviceStatusResponse,
    UpdateAllSlotsRequest,
    UpdateFireflySlotsRequest,
)

router = APIRouter(prefix="/fireflies", tags=["public:fireflies"])


def get_service(request: Request) -> FireflyService:
    service: FireflyService | None = getattr(request.app.state, "firefly_service", None)
    if service is None:
        # Phase 1 startup mode (no actor runtime) has no service. Tests
        # explicitly install one before exercising these routes.
        from firefly_api.core.errors import FireflyError

        raise FireflyError(
            "Firefly runtime is not initialized.",
            status_code=503,
            error_code="runtime_not_started",
        )
    return service


ServiceDep = Annotated[FireflyService, Depends(get_service)]


@router.post("/{device_name}/slots:update", response_model=CommandResponse)
def update_firefly_slots(
    device_name: str,
    body: UpdateFireflySlotsRequest,
    service: ServiceDep,
) -> dict:
    return service.update_slots(
        device_name=device_name,
        slots_in=[
            {
                "external_slot_id": s.external_slot_id,
                "state_name": s.state_name,
                "pattern": s.pattern,
                "pattern_value": s.pattern_value,
            }
            for s in body.slots
        ],
        timeout_ms=body.timeout_ms,
        client_request_id=body.client_request_id,
    )


@router.post("/{device_name}/slots:update-all", response_model=CommandResponse)
def update_all_slots(
    device_name: str,
    body: UpdateAllSlotsRequest,
    service: ServiceDep,
) -> dict:
    return service.update_all_slots(
        device_name=device_name,
        state_name=body.state_name,
        pattern=body.pattern,
        pattern_value=body.pattern_value,
        timeout_ms=body.timeout_ms,
        client_request_id=body.client_request_id,
    )


@router.get("/{device_name}/status", response_model=DeviceStatusResponse)
def get_device_status(
    device_name: str,
    service: ServiceDep,
) -> dict:
    return service.get_device_status(device_name=device_name)
