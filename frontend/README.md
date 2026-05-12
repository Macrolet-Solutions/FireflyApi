# Firefly API — Frontend (Phase 4)

React + TypeScript + Vite operational console for the Firefly API
backend. The UI covers every operator workflow from §10 of the spec:

- Dashboard with broker status, fleet health, and recent errors.
- Device list and per-device detail with live status, lifecycle
  controls (start/stop actor, reinitialize, reset) and tabs for
  segments and slots.
- LED state catalog and command preset editors with the spec's
  "reset required" banner after edits.
- Manual test panel that drives the admin `slots:test` endpoint.
- Event log backed by `/api/v1/admin/events`, polling every 5 s, with
  expandable rows for the full JSON payload.

The shell carries the `logo-firefly.png` brand mark and a one-click
light/dark theme toggle (Mantine's color-scheme manager, persisted in
local storage automatically).

## Tech

- **Vite** for dev / build.
- **React 18** + **TypeScript** (strict).
- **Mantine v7** for components, theming, and the light/dark switch.
- **TanStack Query v5** for server state.
- **React Router v6** for navigation.
- **Tabler Icons** for the icon set.

## Install

```powershell
cd frontend
npm install
```

## Dev workflow

Start the backend (from the repo root) and the frontend dev server
together. The dev server proxies `/api/*` to `http://127.0.0.1:8000`,
so no CORS configuration is needed.

```powershell
# Terminal 1 — backend
python -m firefly_api --config config/firefly-appsettings.json

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open <http://localhost:5173/>.

## Production build

```powershell
cd frontend
npm run build
```

Output lands in `frontend/dist/`. The backend's
`frontend.staticFilesPath` setting (see
`config/firefly-appsettings.example.json`) points at this directory
ready for the Phase 5 packaging step that mounts the bundle on the
FastAPI app.

## Layout

```
frontend/
├── public/
│   └── logo-firefly.png        # Bundled brand mark, served at /logo-firefly.png
├── src/
│   ├── api/                    # Fetch wrapper + typed TanStack Query hooks
│   ├── components/             # AppLayout, ThemeToggle, BrokerStatusBadge, …
│   ├── lib/                    # date formatting, multi-device status query
│   ├── pages/                  # One file per route
│   │   └── device/             # Sub-tabs of the device detail page
│   ├── styles/globals.css
│   ├── App.tsx                 # Route table
│   ├── main.tsx                # Mantine + Query + Router providers
│   └── theme.ts                # Firefly brand color tuple
├── index.html
├── package.json
├── postcss.config.cjs
├── tsconfig.json
└── vite.config.ts
```
