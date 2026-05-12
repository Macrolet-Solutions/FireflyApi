"""Admin action endpoints that touch the actor runtime (§9.4-§9.6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from firefly_api.api.public.fireflies import get_service
from firefly_api.firefly.service import FireflyService
from firefly_api.schemas.admin_actions import (
    ActorLifecycleResponse,
    ReinitializeRequest,
    ReinitializeResponse,
    ResetResponse,
    TestSlotsRequest,
    TestSlotsResponse,
)

router = APIRouter(prefix="/fireflies/{device_id}", tags=["admin:firefly-actions"])

ServiceDep = Annotated[FireflyService, Depends(get_service)]


@router.post(":start-actor", response_model=ActorLifecycleResponse)
def start_actor(device_id: int, service: ServiceDep) -> dict:
    return service.start_actor(device_id=device_id)


@router.post(":stop-actor", response_model=ActorLifecycleResponse)
def stop_actor(device_id: int, service: ServiceDep) -> dict:
    return service.stop_actor(device_id=device_id)


@router.post(":reinitialize", response_model=ReinitializeResponse)
def reinitialize(
    device_id: int,
    body: ReinitializeRequest,
    service: ServiceDep,
) -> dict:
    return service.reinitialize(device_id=device_id, timeout_ms=body.timeout_ms)


@router.post(":reset", response_model=ResetResponse)
def reset(device_id: int, service: ServiceDep) -> dict:
    return service.reset(device_id=device_id)


@router.post("/slots:test", response_model=TestSlotsResponse)
def slots_test(
    device_id: int,
    body: TestSlotsRequest,
    service: ServiceDep,
) -> dict:
    return service.test_slot_update(
        device_id=device_id,
        slots_in=[
            {
                "slot_id": s.slot_id,
                "state_name": s.state_name,
                "pattern": s.pattern,
                "pattern_value": s.pattern_value,
            }
            for s in body.slots
        ],
        timeout_ms=body.timeout_ms,
    )
