# Firefly API — Deployment

This document covers the supported production deployment path. The
repository itself is platform-agnostic; only the contents of
[`packaging/windows/`](packaging/windows/) and
[`services/firefly_api_service.py`](services/firefly_api_service.py)
touch Windows-specific APIs.

> Future targets (Linux/systemd, Docker) belong under `packaging/<target>/`.
> See [`packaging/README.md`](packaging/README.md).

---

## Windows service (production)

### Tooling

| Tool | Used for | Source |
|---|---|---|
| **PyInstaller** | One-folder bundle (`dist/FireflyApi/`) | `backend/requirements-windows.txt` |
| **pywin32** | Service Control Manager integration | `backend/requirements-windows.txt` |
| **Node 18+** | Frontend build | (Vite, already required for dev) |

The service is registered as `MacroletFireflyApi`. It runs a uvicorn
server on `0.0.0.0:8000` by default. Bind address can be overridden
through the `FIREFLY_HOST` / `FIREFLY_PORT` environment variables in
the service registration if needed.

### Build the bundle

From the repository root, on a Windows machine with Python 3.12+ and
Node 18+ on PATH:

```powershell
packaging\windows\build.bat
```

The script does, in order:

1. Builds the React frontend (`npm ci && npm run build`) and stages
   the output under `build\frontend\` so PyInstaller can pick it up.
2. Installs `backend/requirements-windows.txt` (which pulls in
   `pyinstaller` and `pywin32` on top of the regular runtime deps) into
   the resolved Python interpreter — `backend\.venv\Scripts\python.exe`
   if present, otherwise the system `python`.
3. Runs PyInstaller with the spec at
   [`packaging/pyinstaller/firefly_api_service.spec`](packaging/pyinstaller/firefly_api_service.spec).
4. Copies the deployment helpers (`deploy.bat`, the example config)
   alongside the bundled exe.

Output:

```
dist\FireflyApi\
├── firefly_api_service.exe     The bundled service entry point
├── deploy.bat                  Install / start / stop helper
├── _internal\                  PyInstaller runtime files (DO NOT touch)
└── config\
    └── firefly-appsettings.example.json
```

### Deploy to a target machine

1. Copy the entire `dist\FireflyApi\` folder to the target server,
   typically under `C:\Macrolet\FireflyApi\`.
2. Copy `config\firefly-appsettings.example.json` to
   `config\firefly-appsettings.json` and edit the values — at minimum
   adjust `database.url` if you want the SQLite file outside the bundle
   directory.
3. Open an **elevated** PowerShell or `cmd` in the install folder and
   register the service:

   ```powershell
   .\deploy.bat install
   .\deploy.bat start
   ```

4. Verify with `.\deploy.bat status` or by browsing to
   `http://<host>:8000/` (the bundled frontend) and
   `http://<host>:8000/docs` (OpenAPI).

5. To upgrade later, stop the service, replace the folder contents
   (keep `config\` and any data directories), and start again.

### `deploy.bat` reference

| Command | Effect |
|---|---|
| `deploy.bat install` | Registers the service, sets it to auto-start, configures restart-on-failure (30 s / 30 s / 60 s). |
| `deploy.bat uninstall` | Stops and removes the service. |
| `deploy.bat start` | Starts the service. |
| `deploy.bat stop` | Stops the service. |
| `deploy.bat restart` | Stops + 3 s pause + starts. Use after broker config changes (§11). |
| `deploy.bat status` | Prints `sc query MacroletFireflyApi`. |

### Logs

Application logs are written via Python's standard logging (level set
through `logging.level` in the config). Service start / stop / failure
events also land in the Windows Application Event Log under the source
`MacroletFireflyApi` — useful when the service won't start, since
`firefly_api_service.exe install` writes its initial failures there.

### Runtime layout

When the service is running, the working directory is set to the folder
that contains `firefly_api_service.exe`. The defaults in the example
config use relative paths that resolve there:

| Config field | Resolves to |
|---|---|
| `database.url` = `sqlite:///./data/firefly.db` | `dist\FireflyApi\data\firefly.db` |
| `frontend.staticFilesPath` = `./frontend/dist` | served from inside the bundle |

The SQLite parent directory is created automatically on first start.
Migrations run automatically (the bundle includes the `alembic/`
folder) — no separate `alembic upgrade head` step is required after
upgrades.

### Running in console mode (debugging)

The same executable runs in foreground when no arguments are passed
and the SCM dispatcher isn't available — useful for inspecting startup
behavior on a target machine:

```powershell
.\firefly_api_service.exe
```

Press Ctrl+C to stop.

---

## Local development (no service)

For ordinary development the service wrapper is not needed; use the
flow described in [`README.md`](README.md). The same script can be
launched directly with `python services\firefly_api_service.py` if you
want to exercise the production startup path against a source checkout.
