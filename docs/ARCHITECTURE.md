# HomeLab Command Centre — Architecture

## 1. Overview

```
 Android app (Kotlin/Compose) ─┐                 ┌─ psutil (host metrics, /proc, mounts)
                               ├─ HTTPS/REST ──► │  FastAPI backend ── Docker (via socket proxy)
 Web app (React/Vite, nginx) ──┘  /api/v1        │  SQLite (SQLAlchemy 2 + Alembic)
        (nginx proxies /api to backend)          └─ httpx health checks (SSRF-guarded)
```

* **Backend** is the single source of truth: auth, service definitions, monitoring, alerts,
  history, backups. Clients contain **no** monitoring logic; they render API responses.
* **Web** is a static SPA served by nginx, which also reverse-proxies `/api` to the backend so
  the browser sees one origin (no CORS, `SameSite=Strict` cookies work).
* **Android** is a native Compose app talking to the same `/api/v1` endpoints, with the
  backend URL configurable at runtime (the phone's `localhost` is not the server).
* Remote access is via **Tailscale**; application-level authentication is always required.

## 2. Backend modules (`backend/app`)

| Module | Responsibility |
|---|---|
| `api/v1` | Routers and FastAPI dependencies (auth, pagination) |
| `core` | Settings (env), security (Argon2, JWT), errors, logging, rate limiting, lifespan |
| `models` | SQLAlchemy 2 ORM models |
| `schemas` | Pydantic request/response models (OpenAPI source of truth) |
| `services` | Business logic: auth, services, alerts, backups, settings, container control |
| `monitoring` | Host collector, Docker gateway, SSRF guard, health checker, scheduler |
| `notifications` | Notifier interface + optional Telegram |
| `database` | Engine/session factory, base class |
| `migrations` | Alembic revisions (run automatically at startup, or manually) |

### Background work
One `Monitor` object owns asyncio tasks started/stopped in the FastAPI lifespan:
1. **host loop** – samples psutil every `host_interval` (default 10s), keeps the latest snapshot in memory.
2. **persist loop** – writes one wide row per minute to `metric_samples` (1 row per minute, not per metric), rolls up old rows to 5‑minute buckets, prunes by retention.
3. **docker loop** – refreshes container list/stats into an in-memory cache (blocking SDK calls run in a thread).
4. **health scheduler** – every few seconds picks due services; at most `N` concurrent checks via a semaphore; a service is never checked twice concurrently.
5. **alert loop** – evaluates rules against the latest snapshots; dedupes by key, applies cooldown, resolves automatically.

API handlers read cached snapshots, so a slow service or Docker daemon can never block a request.

## 3. Data model
`users`, `refresh_tokens`, `api_keys`, `services`, `service_checks` (latest result lives on `services`; short history kept), `metric_samples`, `alerts`, `events`, `backup_jobs`, `backup_reports`, `storage_volumes`, `app_settings` (single validated JSON row).

## 4. Key decisions & trade-offs

| Decision | Rationale / trade-off |
|---|---|
| SQLite (WAL) | Zero infra; SQLAlchemy/Alembic keep PostgreSQL possible. Single backend process assumed (rate-limit state and monitor loops are in-process). |
| Access token (JWT, 15 min) + rotating opaque refresh token | Web: refresh token in `HttpOnly; SameSite=Strict` cookie, access token only in JS memory (never localStorage → XSS cannot steal a long-lived credential). Refresh requires `X-Requested-With` header (CSRF defence in depth). Mobile: refresh token returned in body, stored by Android Keystore-encrypted storage. Reuse of a rotated refresh token revokes the whole family. |
| Argon2id | OWASP-recommended password hash. |
| First-run `/auth/setup` | Only works while zero users exist; optional `HOMELAB_SETUP_TOKEN` to stop a LAN neighbour racing the owner. No default password. |
| Docker through a **socket proxy** | The backend never mounts `docker.sock`; `tecnativa/docker-socket-proxy` exposes only container list/inspect/logs/stats/start/stop/restart. Delete/create/exec/image/volume endpoints are not reachable even if the backend were compromised. |
| Container control = explicit opt-in | Master switch `HOMELAB_DOCKER_CONTROL_ENABLED` (default **off**) *and* per-service `allow_control` + per-service `allowed_actions`. Containers are addressed by ID/name taken from the server's own container list — never free-form strings passed to Docker. The backend's own container is protected. |
| SSRF guard on health checks | Scheme allow-list, no URL credentials, DNS resolved then **pinned** (defeats rebinding), blocks loopback, link-local (169.254/16 incl. cloud metadata), multicast, reserved, unspecified; allows RFC1918/CGNAT/ULA because homelab services live there (configurable). Redirects are not followed. |
| Mount health | A bind-mounted but unmounted directory looks like a valid directory inside a container. Volumes therefore support `require_mountpoint`, `marker_file` (a file the owner creates on the disk itself) and a device comparison against the root filesystem. The app never writes to, mounts or repairs disks. |
| Unavailable ≠ zero | All optional metrics are `null` when unavailable, with a separate `available` map; clients render “—”/“Unavailable”. |
| Polling over WebSocket/SSE | Cache-backed REST polling (10 s default, min 5 s) is simple, proxy-friendly and enough for a single-owner system. |
| Backup monitoring is status-tracking only | States: `never_run`, `failed`, `overdue`, `reported_success`, `restore_verified`. “Verified” is only reachable through a recorded restore test. |

## 5. Known limitations (initial release)
* Login rate-limiter and monitor state are in-memory (single process; reset on restart).
* No SMART data (needs raw device access/privileges the app deliberately does not request); disk health is limited to mount presence, usage and I/O counters.
* Host network counters from inside a bridge-networked container reflect the container namespace unless `/proc` of the host is mounted (documented; compose mounts it read-only).
* Docker socket proxy is a network trust boundary: keep it on an internal Docker network, never publish its port.
* The Android app could not be compiled in the authoring sandbox (see `docs/IMPLEMENTATION_PLAN.md`).
