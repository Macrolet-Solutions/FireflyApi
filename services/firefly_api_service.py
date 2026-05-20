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

The service name and display name can be overridden by placing
``--service-name <name>`` and ``--service-display-name <name>`` before
the pywin32 command. ``deploy.bat`` exposes those options for packaged
installs.

The wrapper relies on the in-process FastAPI app + uvicorn server. The
bind host/port and application settings live in
``config/firefly-appsettings.json``.
"""

from __future__ import annotations

import logging
import os
import subprocess
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

from firefly_api.core.config import AppConfig, load_config  # noqa: E402
from firefly_api.core.log_config import configure_logging  # noqa: E402
from firefly_api.core.runtime import start_runtime, stop_runtime  # noqa: E402
from firefly_api.core.startup import bootstrap  # noqa: E402
from firefly_api.main import create_app  # noqa: E402

logger = logging.getLogger("FireflyApiService")

DEFAULT_SERVICE_NAME = "MacroletFireflyApi"
DEFAULT_SERVICE_DISPLAY_NAME = "Macrolet Firefly API"


class FireflyApiService(win32serviceutil.ServiceFramework):
    _svc_name_ = DEFAULT_SERVICE_NAME
    _svc_display_name_ = DEFAULT_SERVICE_DISPLAY_NAME
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
        configure_logging(config)
        bootstrap(config)
        self.app = create_app(config)
        start_runtime(self.app, config)

        host, port = _resolve_bind(config)
        uvi_config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level=config.logging.level.lower(),
            access_log=True,
            log_config=None,
        )
        self.server = uvicorn.Server(uvi_config)
        self.server.run()


def _resolve_bind(config: AppConfig) -> tuple[str, int]:
    """Bind address for service mode from application config."""
    return config.server.host, config.server.port


def _parse_service_metadata_args(argv: list[str]) -> tuple[str, str, list[str]]:
    service_name = DEFAULT_SERVICE_NAME
    display_name = DEFAULT_SERVICE_DISPLAY_NAME
    remaining = [argv[0]]

    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--service-name":
            index += 1
            if index >= len(argv):
                raise SystemExit("--service-name requires a value")
            service_name = argv[index]
        elif arg == "--service-display-name":
            index += 1
            if index >= len(argv):
                raise SystemExit("--service-display-name requires a value")
            display_name = argv[index]
        else:
            remaining.append(arg)
        index += 1

    return service_name, display_name, remaining


def _configure_service_metadata(service_name: str, display_name: str) -> None:
    FireflyApiService._svc_name_ = service_name
    FireflyApiService._svc_display_name_ = display_name
    FireflyApiService._exe_args_ = subprocess.list2cmdline(
        ["--service-name", service_name]
    )


def _run_console_mode() -> None:
    """Same lifecycle as the service, run in the current terminal."""
    config = load_config()
    configure_logging(config)
    bootstrap(config)
    app = create_app(config)
    start_runtime(app, config)
    host, port = _resolve_bind(config)
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
            access_log=True,
            log_config=None,
        )
    )
    try:
        uvi.run()
    finally:
        stop_runtime(app)


def main() -> None:
    service_name, display_name, remaining = _parse_service_metadata_args(sys.argv)
    _configure_service_metadata(service_name, display_name)
    sys.argv = remaining

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
