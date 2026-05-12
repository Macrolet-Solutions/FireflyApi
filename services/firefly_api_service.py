"""Firefly API Windows service wrapper.

Mirrors the WcsAuraAi services/* pattern: the same script is the SCM
entry point (when launched by the Windows service manager) and a
console-mode launcher (when invoked from a developer shell). The
console fallback is what makes ``python services/firefly_api_service.py``
useful during development.

Install / control from an elevated prompt::

    python services/firefly_api_service.py install
    python services/firefly_api_service.py start
    python services/firefly_api_service.py stop
    python services/firefly_api_service.py remove

Once packaged with PyInstaller the same commands work against the
bundled ``firefly_api_service.exe``::

    firefly_api_service.exe install
    firefly_api_service.exe start
    ...

The wrapper relies on the in-process FastAPI app + uvicorn server. The
host/port are baked here so the bundled service has a stable default
even before the operator edits the config file; everything else lives in
``config/firefly-appsettings.json``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# When the bundled exe runs as a service the working directory is
# typically ``C:\Windows\System32``. Re-anchoring on the exe location
# means relative paths (the default config search path, ``./data/``)
# resolve next to the bundle.
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    # When run from a dev checkout the script lives in services/; make
    # backend/ importable so ``import firefly_api`` works without an
    # editable install.
    _BACKEND = Path(__file__).resolve().parent.parent / "backend"
    if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))

import pywintypes  # noqa: E402
import servicemanager  # noqa: E402
import uvicorn  # noqa: E402
import win32event  # noqa: E402
import win32service  # noqa: E402
import win32serviceutil  # noqa: E402

from firefly_api.core.config import load_config  # noqa: E402
from firefly_api.core.runtime import start_runtime, stop_runtime  # noqa: E402
from firefly_api.core.startup import bootstrap  # noqa: E402
from firefly_api.main import create_app  # noqa: E402

logger = logging.getLogger("FireflyApiService")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000


class FireflyApiService(win32serviceutil.ServiceFramework):
    _svc_name_ = "MacroletFireflyApi"
    _svc_display_name_ = "Macrolet Firefly API"
    _svc_description_ = (
        "Middleware and configuration platform for Macrolet Firefly devices."
    )

    def __init__(self, args: list[str]) -> None:
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.server: uvicorn.Server | None = None
        self.app = None

    def SvcStop(self) -> None:  # noqa: N802 (pywin32 convention)
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.server is not None:
            self.server.should_exit = True

    def SvcDoRun(self) -> None:  # noqa: N802 (pywin32 convention)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        try:
            self._run_server()
        except Exception:  # noqa: BLE001
            logger.exception("Service crashed")
            servicemanager.LogErrorMsg(
                "FireflyApiService crashed; see the application log file."
            )
            raise
        finally:
            if self.app is not None:
                try:
                    stop_runtime(self.app)
                except Exception:  # noqa: BLE001
                    logger.exception("Error during stop_runtime")

    def _run_server(self) -> None:
        config = load_config()
        bootstrap(config)
        self.app = create_app(config)
        start_runtime(self.app, config)

        host, port = _resolve_bind()
        uvi_config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level=config.logging.level.lower(),
            log_config=None,
        )
        self.server = uvicorn.Server(uvi_config)
        self.server.run()


def _resolve_bind() -> tuple[str, int]:
    """Bind address for service mode.

    Service mode does not parse CLI args, so we pick up overrides from
    the FIREFLY_HOST / FIREFLY_PORT environment variables when set. The
    spec discourages env vars for application config (§13), but these
    are a deployment-time wiring concern, not config — they only steer
    where uvicorn listens.
    """
    host = os.environ.get("FIREFLY_HOST", DEFAULT_HOST)
    port = int(os.environ.get("FIREFLY_PORT", DEFAULT_PORT))
    return host, port


def _run_console_mode() -> None:
    """Same lifecycle as the service, run in the current terminal."""
    config = load_config()
    bootstrap(config)
    app = create_app(config)
    start_runtime(app, config)
    host, port = _resolve_bind()
    print(
        f"Running Firefly API in console mode on http://{host}:{port} "
        "(Ctrl+C to stop) ..."
    )
    uvi = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=config.logging.level.lower(),
        )
    )
    try:
        uvi.run()
    finally:
        stop_runtime(app)


def main() -> None:
    if len(sys.argv) == 1:
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(FireflyApiService)
            servicemanager.StartServiceCtrlDispatcher()
        except pywintypes.error:
            _run_console_mode()
    else:
        win32serviceutil.HandleCommandLine(FireflyApiService)


if __name__ == "__main__":
    main()
