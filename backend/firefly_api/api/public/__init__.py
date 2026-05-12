"""Aggregator router for ``/api/v1/public/*`` endpoints (§8)."""

from __future__ import annotations

from fastapi import APIRouter

from firefly_api.api.public import fireflies

public_router = APIRouter(prefix="/api/v1/public")
public_router.include_router(fireflies.router)
