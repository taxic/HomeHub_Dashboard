# Security model

The backend is a privileged service (it can see and, if you enable it, control containers). Treat it
accordingly.

## Trust boundaries
```
Internet ✗ (never exposed)      Tailnet/LAN ──► web (nginx :8080) ──► backend (internal net only) ──► docker-socket-proxy ──► docker.sock (ro)
```
Only `web` publishes a port, bound to `WEB_BIND` (default `127.0.0.1`). Tailscale does not replace the
app login.

## Controls
| Area | Control |
|---|---|
| Passwords | Argon2id; ≥12 chars; constant-ish-time verification (dummy hash for unknown users); no default account; first-run setup works only while no user exists (+ optional setup token) |
| Sessions | 15-min JWT access token (HS256, `iss`/`exp`/`typ` checked, bound to a session family so revocation is immediate); 30-day **rotating opaque refresh token** stored hashed; reuse after a 15 s grace revokes the whole family |
| Browser | Access token only in JS memory (never localStorage); refresh token in `HttpOnly; SameSite=Strict; Path=/api/v1/auth` cookie, `Secure` when `HOMELAB_COOKIE_SECURE=true`; cookie-authenticated refresh/logout require `X-Requested-With`; nginx CSP `script-src 'self'`, `frame-ancestors 'none'` |
| Android | Refresh token AES-256-GCM encrypted with a non-exportable AndroidKeyStore key; access token memory-only; `allowBackup=false`; OkHttp does not follow redirects and never logs bodies |
| Brute force | Failure limiter per account+IP (5/15 min) and per IP (20/15 min), `Retry-After`; client IP from `X-Forwarded-For` only when the peer is a trusted proxy (nginx overwrites the header) |
| API keys | Scope `backup:report` only; stored as SHA-256 of a 256-bit random secret; shown once; revocable; cannot reach any other endpoint (tested) |
| Input | Pydantic bounds on every field (`extra="forbid"`), 256 KiB body cap (also for chunked bodies), validation errors never echo input |
| Errors | Uniform envelope; 500s are generic with a request ID; Docker/transport error text is not forwarded verbatim for actions |
| Docker | Backend has no socket; proxy allow-list (`CONTAINERS`, optional start/stop/restart; `POST` off). Application layer additionally: master switch (default off) → protected list → per-service `allow_control` → per-service verb allow-list; container looked up in the server's own snapshot (no client-supplied Docker args); per-container action lock; audit event per action |
| SSRF (health checks) | http/https only, no URL credentials, DNS resolved once then **connection pinned to the validated IP** (rebinding), every resolved address must pass, loopback / link-local (169.254/16 incl. metadata) / multicast / reserved / unspecified blocked (also IPv4-mapped IPv6), LAN/CGNAT/ULA allowed (configurable), redirects not followed, timeouts + bounded concurrency, URLs never logged |
| Filesystem | Monitored paths are `stat`-only, must lie under `HOMELAB_STORAGE_ALLOWED_ROOTS`, no `..`; marker file is a plain filename; the app never writes outside `/data` |
| Secrets | Telegram token, setup token, secret key only via environment; never returned by the API or stored in the DB/browser; `.env`, keystores, DBs git-ignored |
| Supply chain | Locked backend (`requirements.lock`) and web (`package-lock.json`); `pip-audit` / `npm audit` clean at time of writing |

## Tests covering the boundaries
Backend: unauthenticated access to every protected route, API-key scope isolation, refresh rotation/
reuse, CSRF header, rate limiting, SSRF classification and DNS-rebinding, container permission matrix
(disabled / not permitted / action not permitted / protected / vanished / Docker error / concurrent),
absence of destructive endpoints, oversize bodies, no echo of submitted secrets. Web: confirmation
dialogs, refresh single-flight, token never in storage. Android core: redirect refusal, refresh
rotation/single-flight, offline-does-not-logout, whitelist of container endpoints.

## Known limitations (initial release)
* Login limiter and monitor state are in-memory: single backend process only; reset on restart.
* No TLS in the stack itself. Use Tailscale (WireGuard) and preferably `tailscale serve` HTTPS. The
  Android app permits cleartext (Tailscale IPs can't be enumerated in a network-security-config) and
  warns for non-private `http://` addresses.
* Any authenticated session is the (single) administrator: there is no role separation. Anyone who has
  the admin login can read logs of **any** container (they may contain secrets) and the backend can
  `inspect` containers (environment variables visible to it).
* Docker proxy `ALLOW_RESTARTS` also exposes `kill`; the app never calls it. A compromised backend could.
* No SMART data: disk health is limited to mount presence, capacity and I/O counters.
* Alerts are evaluated every 15 s with a 2-cycle confirmation; background Android notifications run
  at WorkManager's 15-minute minimum. Use Telegram for faster delivery.
* Refresh-token replay within a 15-second grace window is tolerated (concurrent tabs) but not honoured.
* JWT signing key is symmetric and shared by one process; rotating it logs everyone out.
* The Android app, Docker images and real-hardware behaviour have not been exercised (see README status).
