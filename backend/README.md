# Firefly API — Backend (Phases 1-3)

Python backend for the Firefly API Service. Phase 1 delivered the
foundation and admin CRUD. Phase 2 added the MQTT protocol layer, actor
runtime, and event log. Phase 3 wires the actor runtime to the HTTP
surface so external integrators can drive devices through the public
API.

## Layout

```
backend/
├── firefly_api/        # Application package
│   ├── api/admin/      # Admin CRUD endpoints (§9)
│   ├── api/public/     # Placeholder, populated in Phase 3
│   ├── core/           # config loader, error envelope, startup helpers
│   ├── db/             # SQLAlchemy models, session, repositories
│   └── schemas/        # Pydantic request/response models
├── alembic/            # Database migrations
├── tests/              # pytest suite (repositories + admin routes)
├── alembic.ini
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

The example configuration file is at the repository root in
`config/firefly-appsettings.example.json`. Copy it to
`config/firefly-appsettings.json` before running the service.

## Requirements

- Python 3.12 or later (tested on 3.14).
- SQLite (bundled with Python's stdlib).

## Install

From the repository root:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
```

(The editable install makes `firefly_api` importable from the venv.)

## Configure

```powershell
# From the repository root
copy config\firefly-appsettings.example.json config\firefly-appsettings.json
```

Edit the copy as needed. The defaults point the SQLite database at
`./data/firefly.db`, bind the backend to `0.0.0.0:8000`, and assume the
frontend bundle (later phases) at `./frontend/dist`.

## Run migrations

The application runs `alembic upgrade head` automatically on startup. If you
want to run them manually:

```powershell
# From the repository root
$env:FIREFLY_CONFIG = "config\firefly-appsettings.json"
cd backend
alembic upgrade head
Remove-Item Env:\FIREFLY_CONFIG
```

`FIREFLY_CONFIG` is only used as a developer convenience for invoking
`alembic` directly. The running service does not consult environment
variables (§13).

## Run the service

```powershell
# From the repository root
python -m firefly_api --config config\firefly-appsettings.json
```

OpenAPI interactive docs: `http://127.0.0.1:8000/docs`.

## Tests

```powershell
cd backend
pytest
```

Tests use an in-memory SQLite database with foreign-key enforcement
enabled. They cover:

- Config loader (default path, explicit path, defaults applied).
- Error envelope shape (§8.4) on 404 / 422 / business errors.
- Admin CRUD for every resource, including the spec's validation rules:
  - single-row broker constraint (§7.1)
  - segment overlap on the same channel (both forward and reverse
    direction, §6.3 / §7.3)
  - gap-free controller-wide slot index assignment after deletes (§7.4)
  - adjacent slot LED totals fit inside the segment and positions are unique
  - immutability of `segment_position` and `segment_id` on PUT
  - RESTRICT delete semantics for broker / segment / LED-state references

## What's deliberately not in this phase

Nothing remains out of scope — every spec endpoint and behavior is
implemented. Admin CRUD, MQTT actor runtime, public command API, admin
action endpoints, the `firefly_events` log writer, the daily retention
job, the events admin read endpoint, and the optional bundled-frontend
mount are all wired and tested.

The backend still starts cleanly with no MQTT broker configured (admin
CRUD remains available). Once a broker is created through the admin API,
restart the backend so the §11 runtime startup picks it up.

For Windows service packaging see [`../DEPLOYMENT.md`](../DEPLOYMENT.md).
