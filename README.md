# HomeLab Command Centre

A self-hosted control panel for a small Ubuntu/Docker homelab: one authenticated backend API, a
responsive web dashboard and a native Android app. It monitors host health, Docker containers,
service availability, storage/mount health and backup freshness, keeps history, raises alerts, and
(optionally, off by default) starts/stops/restarts *explicitly permitted* containers.

```
Android app (Compose) ─┐
                       ├─ /api/v1 (REST, JWT) ─► FastAPI backend ─► psutil (host) · Docker (via socket proxy) · SQLite
Web app (React, nginx) ┘
```

| Part | Tech | Where |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, SQLite | `backend/` |
| Web | React 19, TypeScript, Vite, TanStack Query, Recharts | `web/` |
| Android | Kotlin, Jetpack Compose, Material 3, Retrofit/OkHttp, WorkManager | `android/` (`:core` + `:app`) |
| Deployment | Docker Compose (+ docker-socket-proxy) | `deploy/` |

## Status — what is verified and what is not

| Area | State | Evidence |
|---|---|---|
| Backend | **Complete, tested** | 194 pytest tests pass; ruff clean; migrations tested; run end-to-end with real host metrics |
| Web | **Complete, tested** | 46 vitest tests; eslint + `tsc` clean; production build; screenshots reviewed at desktop and mobile widths against a live backend |
| Android `:core` (API, auth, repositories, polling, policies) | **Tested** | 40 JUnit tests pass (MockWebServer; contract tests against real backend JSON) |
| Android `:app` (Compose UI, ViewModels, Keystore store, WorkManager) | **Written, NOT compiled** | The authoring sandbox had no Android SDK and could not reach Google Maven. Expect to fix small compile errors on first build in Android Studio. UI tests in `androidTest/` have never been run. |
| Docker integration | **Tested against a fake gateway only** | No Docker daemon in the sandbox. The compose file validates (`docker compose config`) but images were never built or run, and the real Docker SDK / socket proxy were never exercised. |
| Hardware metrics | Verified on the sandbox VM only | CPU temperature and USB-SATA mount behaviour are untested on the real OptiPlex |

Please read [docs/SECURITY.md](docs/SECURITY.md) (limitations included) before exposing this to anything but your own tailnet.

## Quick start

```bash
cd deploy
cp ../.env.example .env        # edit: WEB_BIND, secrets; see comments inside
docker compose up -d --build
# open http://<WEB_BIND>:8080 → "Create the administrator" (first run only)
```

Full steps (Tailscale access, monitoring external disks, enabling container control, upgrades,
backup/restore of the app's own database, building the APK): **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

Local development:

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
HOMELAB_DATA_DIR=./data HOMELAB_COOKIE_SECURE=false uvicorn app.main:get_app --factory --reload
# web (proxies /api to localhost:8000)
cd web && npm ci && npm run dev
# android core tests (JDK 21 only)
cd android && ./gradlew :core:test
```

## Design principles

* **Real data or an honest gap.** Every metric is `null` when unavailable and rendered as "—", never
  as zero. If the backend is unreachable, clients say so and label any data still on screen as stale.
* **Optional integrations degrade gracefully.** No Docker, no sensors, no Telegram, a missing disk —
  the rest keeps working and the problem is reported.
* **No arbitrary execution.** Clients can only ask for `start`/`stop`/`restart` of containers that a
  service definition explicitly allows, and only if the server owner enabled control. There is no
  shell, exec, create, delete, prune or volume operation anywhere.
* **Configuration, not code.** Services, volumes, thresholds, intervals and retention are data
  managed through the UI/API.

## Documentation

* [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
* [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — install, permissions/mounts, Tailscale, upgrade, backup, troubleshooting
* [docs/SECURITY.md](docs/SECURITY.md) — threat model, controls, known limitations
* [docs/API.md](docs/API.md) — endpoints, auth, reporting backups from scripts
* [docs/ANDROID.md](docs/ANDROID.md) — building, installing and connecting the app
* [docs/DESIGN.md](docs/DESIGN.md) — shared design tokens
* `docs/openapi.json` — generated API schema (`/docs` serves Swagger UI)
