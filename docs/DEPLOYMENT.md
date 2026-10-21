# Deployment guide (Ubuntu Server + Docker)

> Written without access to a Docker daemon: the compose file validates, but images were not built
> or run by the author. Treat first start as a test, and check the verification steps below.

## 1. Prerequisites
* Docker Engine with Compose v2 (`docker compose version`).
* Tailscale already running on the server (recommended access path).

## 2. Install
```bash
git clone <this repo> homelab-command-centre && cd homelab-command-centre/deploy
cp ../.env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # optional: paste as HOMELAB_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # optional: HOMELAB_SETUP_TOKEN
$EDITOR .env
docker compose up -d --build
docker compose ps        # all three healthy/running
```
Open `http://<WEB_BIND>:<WEB_PORT>`; the first visit asks you to create the administrator (12+ char
password). No default account exists. If `HOMELAB_SETUP_TOKEN` is set it is required here; this stops
someone else on your network claiming the account first.

`HOMELAB_SECRET_KEY` empty ⇒ a key is generated into the data volume (`/data/secret_key`, mode 0600).
Rotating it signs everyone out.

## 3. What the backend needs (and why)
| Mount / permission | Why | Notes |
|---|---|---|
| `homelab-data:/data` (named volume) | SQLite DB, generated secret key | Only writable path (root fs is read-only) |
| `/proc:/host/proc:ro` | CPU, memory, load, uptime, disk I/O of the **host** | read-only |
| `/sys:/host/sys:ro` | Host NIC byte counters (`/sys/class/net`), hwmon temps | read-only; without it, network throughput shows "unavailable" rather than container-only numbers |
| `DOCKER_HOST=tcp://docker-socket-proxy:2375` | Container list/inspect/logs/stats (+ start/stop/restart if enabled) | **No `docker.sock` in the backend.** Only the proxy mounts the socket, read-only, and answers a short allow-list |
| `user 10001`, `cap_drop: ALL`, `no-new-privileges`, `read_only` | least privilege | no `privileged`, no host network |
| External disk mounts (you add) | capacity + mount-health of USB/SATA/HDD | `read_only: true`, `propagation: rslave`, `create_host_path: false` |

Docker socket proxy facts (verified against upstream README v0.4.2, **not** against a running image):
`CONTAINERS=1` allows listing/inspecting/log/stats; `POST` stays 0; with
`DOCKER_PROXY_ALLOW_ACTIONS=1` only `containers/<id>/start|stop|restart` (and upstream's bundled
`kill`) open up. Be aware `inspect` output includes container environment variables, so a compromised
backend could read them — another reason the backend is not exposed publicly.

**Verify after first start** (from the host):
```bash
docker compose exec backend python - <<'PY'
import docker; c=docker.DockerClient(base_url="tcp://docker-socket-proxy:2375"); print([x.name for x in c.containers.list()])
try: c.containers.run("alpine","true")   # must be refused
except Exception as e: print("create refused as expected:", type(e).__name__)
PY
```

## 4. Monitoring external disks (USB-SATA safety)
1. Create an empty marker file **on the disk itself**: `sudo touch /mnt/media/.homelab-mounted` (do this
   while mounted). If the disk drops and the empty mount-point directory remains, the marker is missing
   and the app reports "Not mounted" instead of showing the root disk's free space.
2. Add a bind mount block to the backend service in `docker-compose.yml` (see the commented example).
   `create_host_path: false` makes Compose refuse to start if the path is absent rather than creating
   an empty directory.
3. In the UI: Storage → Monitor volume. Path is the **container** path; type "External disk" also
   compares the device with the root filesystem.
4. The app only ever `stat`s/`statvfs`es these paths (in a thread with a timeout, so a hung USB bridge
   shows "Not responding" instead of freezing monitoring). It never mounts, repairs, formats or writes.

Root filesystem usage uses `HOMELAB_ROOT_PATH` (default `/data`), which must be on the host's root
disk — true when Docker's data-root is `/var/lib/docker` on the NVMe. Otherwise set it to another
container path that lives on the root filesystem.

## 5. Services and container control
* Services are data: UI → Services → Add (URL and/or container name). Health checks block loopback,
  link-local/cloud-metadata and other non-LAN targets (see SECURITY.md). Use `verify_tls=false` only
  for self-signed LAN services.
* Container control is **off** by default. To enable, set in `.env`
  `HOMELAB_DOCKER_CONTROL_ENABLED=true` **and** `DOCKER_PROXY_ALLOW_ACTIONS=1`, `docker compose up -d`,
  then opt in per service ("Allow start/stop/restart", choose verbs). The backend's own containers are
  always protected. Every action is audited (Alerts & events → Events).

## 6. Remote access with Tailscale
* Set `WEB_BIND` to the server's Tailscale IP (`tailscale ip -4`) so the UI is not exposed on the LAN.
* From a phone/laptop on the tailnet use `http://<tailscale-ip>:8080` or MagicDNS
  `http://<hostname>.<tailnet>.ts.net:8080`.
* Better: terminate HTTPS with Tailscale and set `HOMELAB_COOKIE_SECURE=true`:
  `sudo tailscale serve --bg --https=443 http://127.0.0.1:8080` (keep `WEB_BIND=127.0.0.1`), then use
  `https://<hostname>.<tailnet>.ts.net/`. (Check `tailscale serve --help` for your Tailscale version's syntax.)
* Tailscale authenticates devices, **not** the app: the login is still required.
* Set `HOMELAB_PUBLIC_URL` to the address clients should use (informational, shown in Settings).
* Never port-forward the web port to the internet.

## 7. Operations
**Logs:** `docker compose logs -f backend` (JSON lines, no credentials or bodies; request IDs in errors).
**Health:** `GET /api/v1/health/live` and `/health/ready` (also the container HEALTHCHECK).

**Upgrade**
```bash
cd homelab-command-centre && git pull
docker compose -f deploy/docker-compose.yml exec backend python -m app.cli backup   # safety copy first
cd deploy && docker compose up -d --build
```
Alembic migrations run automatically at backend start. Downgrades are not supported after a migration
runs on real data — restore the pre-upgrade backup instead.

**Back up the app's own database** (consistent while running):
```bash
docker compose exec backend python -m app.cli backup           # writes /data/backups/homelab-<ts>.db
docker compose cp backend:/data/backups/. /srv/backups/homelab/ # copy off the volume
docker compose exec backend python -m app.cli check             # PRAGMA integrity_check
```
**Restore:**
```bash
docker compose stop backend
docker run --rm -v homelab-command-centre_homelab-data:/data -v /srv/backups/homelab:/b alpine \
  sh -c 'cp /b/homelab-YYYYmmdd-HHMMSS.db /data/homelab.db && rm -f /data/homelab.db-wal /data/homelab.db-shm && chown 10001:10001 /data/homelab.db'
docker compose start backend
```
(The backup contains password hashes and session records: store it as you would any credential.)

**Forgot the password:** `docker compose exec backend python -m app.cli reset-password <username>`
(requires shell access to the host; signs out every session).

**Retention:** defaults — 1-minute samples for 48 h, 5-minute averages for 30 d, events/resolved alerts
90 d. Adjustable in Settings → Monitoring. History lives in the data volume and survives restarts and
container recreation. At defaults the DB grows by roughly a few MB per month.

## 8. Backups monitoring
Create jobs in Backups, create an API key in Settings → Security (scope `backup:report` only), and call
from your script (`deploy/scripts/report-backup.sh`). States: *Success reported* (script says OK, **not**
proof of restorability), *Restore verified* (only after you report a `restore_test` success), *Failed*,
*Overdue*, *Never reported*, *Restore test failed*. The app never reads, runs or deletes backups.

## 9. Troubleshooting
| Symptom | Check |
|---|---|
| UI says "Backend unreachable" | `docker compose ps`; `curl localhost:8080/api/v1/health`; Tailscale connected? |
| "Docker is unavailable" | proxy running? `docker compose logs docker-socket-proxy`; backend env `DOCKER_HOST` |
| Network throughput "unavailable" | `/sys` mount present and `HOMELAB_HOST_SYS_PATH=/host/sys`? (see backend log warning) |
| Temperature "unavailable" | Normal on some hardware; needs `coretemp`/`k10temp` hwmon visible (`sensors`) |
| Disk shows "Not mounted" | Marker file missing, or disk really dropped; run `dmesg \| tail` on the host. The app does not remount |
| 429 on login | Rate limit (5 failures / 15 min per account+IP); wait, or restart backend to clear |
| Container buttons missing/disabled | control enabled on server **and** proxy, service has `allow_control` + verbs, container not protected |
| Android can't connect | use the server's Tailscale IP/name, not `localhost`; phone on tailnet; `http://` includes the port |
| Permission denied writing /data | volume ownership: `docker compose down && docker volume rm …` only if empty, or `chown 10001` |
| Everything signed out after restart | `HOMELAB_SECRET_KEY` changed or `/data/secret_key` lost |

## 10. Android APK
See [ANDROID.md](ANDROID.md).
