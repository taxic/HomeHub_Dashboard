# API overview

Base path `/api/v1`; interactive docs at `/docs` (backend port, disable with `HOMELAB_DOCS_ENABLED=false`);
machine-readable schema in `docs/openapi.json` (web types are generated from it: `npm run gen:api`).

**Errors** always look like `{"error": {"code", "message", "details"?, "request_id"?}}`.
**Lists** that can grow return `{items, total, limit, offset}` (`limit` ≤ 200).
**Auth:** `Authorization: Bearer <access token>`. Web clients get the refresh token as an HttpOnly cookie;
mobile clients (`"client": "mobile"` at login) receive it in the body.

| Area | Endpoints |
|---|---|
| Health (public) | `GET /health`, `/health/live`, `/health/ready` |
| Auth | `GET /auth/status`, `POST /auth/setup`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`, `/auth/sessions`, `DELETE /auth/sessions/{id}`, `POST /auth/change-password`, `GET/POST /auth/api-keys`, `DELETE /auth/api-keys/{id}` |
| Overview & metrics | `GET /overview`, `/metrics/current`, `/metrics/history?range=1h\|6h\|24h\|7d\|30d` |
| Containers | `GET /containers`, `/containers/{id}`, `/containers/{id}/logs?tail=`, `POST /containers/{id}/start\|stop\|restart` |
| Services | `GET/POST /services`, `GET/PATCH/DELETE /services/{id}`, `POST /services/{id}/check` |
| Storage | `GET /storage`, `GET/POST /storage/volumes`, `PATCH/DELETE /storage/volumes/{id}` |
| Alerts | `GET /alerts?status=open\|resolved\|all`, `POST /alerts/{id}/acknowledge`, `GET /events` |
| Backups | `GET/POST /backups`, `GET/PATCH/DELETE /backups/{id}`, `GET /backups/{id}/reports`, `POST /backups/{id}/report` (admin **or** API key `backup:report`) |
| Settings | `GET/PATCH /settings`, `POST /settings/test-notification` |

`container id` accepts the full/short Docker id or the container name; it is looked up in the server's
own snapshot, never passed through to Docker.

## Reporting a backup result
```bash
curl -fsS -X POST "$HOMELAB_URL/api/v1/backups/1/report" \
  -H "Authorization: Bearer $HOMELAB_API_KEY" -H 'Content-Type: application/json' \
  -d '{"status":"success","message":"rsync ok","size_bytes":123456789}'
# a restore test (the only thing that can make a job "restore verified")
  -d '{"kind":"restore_test","status":"success","message":"restored sample, checksums match"}'
```
See `deploy/scripts/report-backup.sh`.
