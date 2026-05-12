"""Aggregator router for ``/api/v1/admin/*`` endpoints (§9)."""

from __future__ import annotations

from fastapi import APIRouter

from firefly_api.api.admin import (
    actions,
    brokers,
    command_presets,
    devices,
    events,
    led_states,
    segments,
    slots,
)

admin_router = APIRouter(prefix="/api/v1/admin")
admin_router.include_router(brokers.router)
admin_router.include_router(devices.router)
admin_router.include_router(segments.router)
admin_router.include_router(slots.router)
admin_router.include_router(led_states.router)
admin_router.include_router(command_presets.router)
admin_router.include_router(events.router)
admin_router.include_router(actions.router)
