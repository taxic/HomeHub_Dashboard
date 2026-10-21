# Implementation plan & status

Authoring environment: Python 3.13, Node 22, JDK 21, Gradle 8.14. **No Docker daemon** and **no Android
SDK** (Google Maven / dl.google.com blocked). Maven Central worked intermittently (rate limited).

| Phase | Scope | Status |
|---|---|---|
| 0 | Inspect, architecture, plan | done |
| 1 | Backend foundation: config, DB, Alembic, auth, health, errors | done, tested |
| 2 | Host + Docker monitoring, services, SSRF-safe checks, history/retention | done, tested (Docker via fake gateway) |
| 3 | Web dashboard | done, tested, visually reviewed |
| 4 | Android app | `:core` done and tested; `:app` written, **uncompiled** |
| 5 | Controlled container actions + audit | done and tested (backend, web, android-core); never run against real Docker |
| 6 | Alerts, backups, Telegram | done, tested (Telegram via mock transport) |
| 7 | Hardening, docs, release | docs/deploy files done; dependency audits clean; images and APK **not built** |

## Next concrete steps (for the owner)
1. `docker compose up -d --build` on the server; run the verification snippet in DEPLOYMENT.md §3.
2. Open `android/` in Android Studio, fix any compile errors in `:app`, run `:app:connectedDebugAndroidTest`.
3. Add your external disks (marker file + bind mount) and confirm the "Not mounted" path by unplugging
   a **non-critical** disk while watching Storage.
4. Optionally: Postgres support (models are portable; untested), SMART via a separate read-only
   collector, WebSocket/SSE push instead of polling.
