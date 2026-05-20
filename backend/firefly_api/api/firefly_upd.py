"""Legacy Firefly firmware update endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import FileResponse

from firefly_api.core.config import AppConfig

DEFAULT_FIREFLY_UPD_FILE_PATH = Path("data") / "firefly_upd" / "macrolet.cart.bin"

router = APIRouter(tags=["admin:firmware"])


def _resolve_firefly_upd_file_path(config: AppConfig) -> Path:
    if config.firefly_upd_file_path:
        return Path(config.firefly_upd_file_path)
    return Path.cwd() / DEFAULT_FIREFLY_UPD_FILE_PATH


@router.get("/firefly_upd", include_in_schema=False, response_model=None)
def get_firefly_update(request: Request) -> FileResponse | Response:
    config: AppConfig = request.app.state.config
    file_path = _resolve_firefly_upd_file_path(config)
    if not file_path.is_file():
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=file_path.name,
    )