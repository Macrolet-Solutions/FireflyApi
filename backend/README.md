# Firefly API — Backend (Phase 1)

Python backend for the Firefly API Service. Phase 1 delivers the foundation
and admin CRUD over the configuration tables. MQTT and the actor runtime
arrive in Phase 2; the public integration API in Phase 3.

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
`./data/firefly.db` and assume the frontend bundle (later phases) at
`./frontend/dist`.

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
python -m firefly_api --config config\firefly-appsettings.json --host 127.0.0.1 --port 8000
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
  - append-only slot index assignment (§7.4)
  - slot range fits inside its segment and does not overlap siblings
  - immutability of `segment_position` and `segment_id` on PUT
  - RESTRICT delete semantics for broker / segment / LED-state references

## What's deliberately not in this phase

The following appear in the spec but are out of scope for Phase 1 — they
arrive in Phase 2 (MQTT + actor runtime) or Phase 3 (public/admin HTTP
command surface):

- All public endpoints (`/api/v1/public/*`).
- Admin action endpoints: `:start-actor`, `:stop-actor`, `:reinitialize`,
  `:reset`, `:test-connection`, `slots:test`.
- Admin events listing (`/api/v1/admin/events`).
- MQTT broker connection, the actor registry, and any device runtime
  behavior.
- The daily `firefly_events` retention cron job.

The Phase 1 backend starts cleanly with no MQTT broker configured —
operators configure one through the admin API, then restart the backend
(§11) to enable Phase 2 functionality once it lands.
