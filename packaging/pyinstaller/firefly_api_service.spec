# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Firefly API Windows service.

Build from the repository root::

    pyinstaller --noconfirm packaging/pyinstaller/firefly_api_service.spec

Outputs ``dist/FireflyApi/firefly_api_service.exe`` plus the runtime
dependencies (bundled frontend, alembic versions, vendored .pyd files).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

_exe_name = "firefly_api_service"
_root = Path(SPECPATH).parents[1]
_backend = _root / "backend"
_services = _root / "services"

# Two locations are tried for the frontend bundle:
#   1. build/frontend/ — what packaging/windows/build.bat assembles.
#   2. frontend/dist/  — what ``npm run build`` produces directly during
#      development.
_frontend_dir = _root / "build" / "frontend"
if not _frontend_dir.exists():
    _frontend_dir = _root / "frontend" / "dist"

# Alembic loads migration scripts at runtime. Without this they wouldn't
# end up in the bundle and ``alembic upgrade head`` would fail.
_alembic_dir = _backend / "alembic"

hidden = (
    collect_submodules("firefly_api")
    + collect_submodules("uvicorn")
    + collect_submodules("starlette")
    + collect_submodules("fastapi")
    + collect_submodules("pydantic")
    + collect_submodules("pydantic_core")
    + collect_submodules("paho.mqtt")
    + collect_submodules("pykka")
    + collect_submodules("apscheduler")
    + [
        "alembic.runtime.migration",
        "alembic.runtime.environment",
        "sqlalchemy.dialects.sqlite",
        "win32timezone",
        "servicemanager",
        "win32serviceutil",
        "win32service",
        "win32event",
    ]
)

datas = []
if _frontend_dir.exists():
    datas.append((str(_frontend_dir), "frontend/dist"))
if _alembic_dir.exists():
    datas.append((str(_alembic_dir), "alembic"))
    # alembic.ini lives next to the alembic/ folder so it gets picked up
    # via the same script_location convention.
    if (_backend / "alembic.ini").exists():
        datas.append((str(_backend / "alembic.ini"), "."))

a = Analysis(
    [str(_services / "firefly_api_service.py")],
    pathex=[str(_backend), str(_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "PIL"],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FireflyApi",
)
