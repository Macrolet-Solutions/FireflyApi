"""Aggregator router for ``/api/v1/admin/*`` endpoints (§9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from firefly_api.api.admin import (
    actions,
    brokers,
    command_presets,
    devices,
    events,
    led_states,
    segments,
    slots,
    users,
)
from firefly_api.core.auth import authorize_admin_api

admin_router = APIRouter(
    prefix="/api/v1/admin", dependencies=[Depends(authorize_admin_api)]
)
admin_router.include_router(brokers.router)
admin_router.include_router(devices.router)
admin_router.include_router(segments.router)
admin_router.include_router(slots.router)
admin_router.include_router(led_states.router)
admin_router.include_router(command_presets.router)
admin_router.include_router(events.router)
admin_router.include_router(actions.router)
admin_router.include_router(users.router)
