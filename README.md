# Firefly API Service

Middleware and configuration platform for Macrolet Firefly devices. See
[`FireflyApiServiceSpec.md`](FireflyApiServiceSpec.md) for the full
specification.

## Status

This repository is being built incrementally per the phases in §16 of the
spec:

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend foundation + admin CRUD | ✅ |
| 2 | MQTT protocol & actor runtime | ✅ |
| 3 | Public + admin HTTP command surface | ✅ |
| 4 | React frontend | ✅ |
| 5 | Packaging & deployment docs | ✅ |

## Layout

```
.
├── backend/                # Python / FastAPI service
├── frontend/               # React + TypeScript + Mantine UI
├── services/               # Service entry points (Windows: pywin32)
├── packaging/              # Build + deploy artefacts (per OS)
│   ├── pyinstaller/        # Platform-agnostic .spec files
│   └── windows/            # build.bat + deploy.bat
├── config/
│   └── firefly-appsettings.example.json
├── DEPLOYMENT.md           # Production deployment guide
├── FireflyApiServiceSpec.md
├── logo-firefly.png
└── README.md
```

## Deploy to production (Windows service)

See [`DEPLOYMENT.md`](DEPLOYMENT.md). Short version:

```powershell
packaging\windows\build.bat
# copy dist\FireflyApi\ to the target machine
.\deploy.bat install
.\deploy.bat start
```

Other deployment targets (Linux/systemd, Docker) can be added as sibling
folders under [`packaging/`](packaging/) without touching the
application code — pywin32 only appears in
[`services/firefly_api_service.py`](services/firefly_api_service.py) and
[`backend/requirements-windows.txt`](backend/requirements-windows.txt).

## Quick start (development)

```powershell
# 1. Set up the backend (see backend/README.md for details)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .

# 2. Set up the frontend
cd ../frontend
npm install

# 3. Copy the example config
cd ..
copy config\firefly-appsettings.example.json config\firefly-appsettings.json

# 4a. Run the backend (terminal 1)
python -m firefly_api --config config\firefly-appsettings.json

# 4b. Run the frontend dev server (terminal 2). It proxies /api to the backend.
cd frontend
npm run dev
```

- Frontend dev: <http://localhost:5173/>
- Backend OpenAPI: <http://127.0.0.1:8000/docs>

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for the per-tier development
workflow (tests, migrations, production build).
