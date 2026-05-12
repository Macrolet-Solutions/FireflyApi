# Firefly API — Packaging

Deployment artefacts live here, organized by target. The directory
structure is deliberately open so additional targets can land as
siblings without disturbing the existing layout:

```
packaging/
├── pyinstaller/        Platform-agnostic PyInstaller .spec files.
└── windows/            Windows: build.bat + deploy.bat (Windows service).
                        (Future: linux/, docker/, ...)
```

## Targets

### Windows (`windows/`)

Bundles the backend + frontend into a single Windows service called
`MacroletFireflyApi`. Uses **pyinstaller** for bundling and **pywin32**
for the Service Control Manager glue. See [`../DEPLOYMENT.md`](../DEPLOYMENT.md)
for the operator workflow.

Service entry point: [`services/firefly_api_service.py`](../services/firefly_api_service.py).

### Future targets

Suggested layout if Linux or container packaging is needed later:

```
packaging/
├── linux/
│   ├── build.sh
│   └── firefly-api.service     systemd unit file
└── docker/
    └── Dockerfile
```

The Python package itself ([`backend/firefly_api/`](../backend/firefly_api/))
contains no Windows-specific code; pywin32 imports are isolated to
`services/firefly_api_service.py`. Adding a Linux systemd target only
needs a small runner script (the existing `python -m firefly_api` works
as-is) plus the unit file.
