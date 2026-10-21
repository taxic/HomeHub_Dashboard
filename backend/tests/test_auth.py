import pytest

from tests.conftest import PASSWORD

API = "/api/v1"


async def test_health_is_public_and_minimal(client):
    r = await client.get(f"{API}/health")
    assert r.status_code == 200
    assert set(r.json()) == {"status", "version", "time", "public_url"}
    assert (await client.get(f"{API}/health/ready")).status_code == 200
    assert (await client.get(f"{API}/health/live")).status_code == 200


async def test_setup_flow_only_once(client):
    assert (await client.get(f"{API}/auth/status")).json()["setup_required"] is True
    r = await client.post(f"{API}/auth/setup", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 201 and "password" not in r.text
    assert (await client.get(f"{API}/auth/status")).json()["setup_required"] is False
    r = await client.post(f"{API}/auth/setup", json={"username": "evil", "password": PASSWORD})
    assert r.status_code == 409


async def test_setup_rejects_weak_password(client):
    r = await client.post(f"{API}/auth/setup", json={"username": "admin", "password": "short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "weak_password"


async def test_setup_token_enforced(tmp_path):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path, setup_token="s3cret-setup-token"))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c,
    ):
        body = {"username": "admin", "password": PASSWORD}
        assert (await c.post(f"{API}/auth/setup", json=body)).status_code == 403
        ok = await c.post(f"{API}/auth/setup", json={**body, "setup_token": "s3cret-setup-token"})
        assert ok.status_code == 201


async def test_protected_endpoints_require_auth(client):
    for method, path in [
        ("GET", "/settings"),
        ("PATCH", "/settings"),
        ("GET", "/auth/me"),
        ("GET", "/auth/sessions"),
        ("GET", "/auth/api-keys"),
    ]:
        r = await client.request(method, f"{API}{path}", json={} if method == "PATCH" else None)
        assert r.status_code == 401, (method, path)
        assert r.json()["error"]["code"] == "unauthorized"


async def test_login_wrong_password_generic_error(client, auth):
    r = await client.post(f"{API}/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    r2 = await client.post(f"{API}/auth/login", json={"username": "ghost", "password": "nope"})
    assert r2.status_code == 401
    assert r.json()["error"]["message"] == r2.json()["error"]["message"]


async def test_login_rate_limited(client, auth):
    for _ in range(5):
        await client.post(f"{API}/auth/login", json={"username": "admin", "password": "bad"})
    r = await client.post(f"{API}/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


async def test_web_login_uses_httponly_cookie_and_hides_refresh_token(client, auth):
    r = await client.post(f"{API}/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.json()["refresh_token"] is None
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/v1/auth" in cookie


async def test_refresh_requires_csrf_header_for_cookie(client, auth):
    await client.post(f"{API}/auth/login", json={"username": "admin", "password": PASSWORD})
    r = await client.post(f"{API}/auth/refresh")
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = await client.post(f"{API}/auth/refresh", headers={"X-Requested-With": "hlcc"})
    assert r.status_code == 200 and r.json()["access_token"]


async def test_mobile_refresh_rotation_and_reuse_detection(client, auth, monkeypatch):
    r = await client.post(
        f"{API}/auth/login", json={"username": "admin", "password": PASSWORD, "client": "mobile"}
    )
    first = r.json()["refresh_token"]
    r2 = await client.post(f"{API}/auth/refresh", json={"refresh_token": first})
    assert r2.status_code == 200
    second = r2.json()["refresh_token"]
    assert second != first
    # Immediate replay: tolerated as a race, but not honoured.
    r3 = await client.post(f"{API}/auth/refresh", json={"refresh_token": first})
    assert r3.status_code == 401 and r3.json()["error"]["code"] == "refresh_conflict"
    # Replay after the grace window => theft assumed, family revoked.
    from app.services import auth_service

    monkeypatch.setattr(auth_service, "REFRESH_REUSE_GRACE_SECONDS", -1)
    r4 = await client.post(f"{API}/auth/refresh", json={"refresh_token": first})
    assert r4.status_code == 401
    r5 = await client.post(f"{API}/auth/refresh", json={"refresh_token": second})
    assert r5.status_code == 401
    # access token from the revoked family no longer works
    stale = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    assert (await client.get(f"{API}/auth/me", headers=stale)).status_code == 401


async def test_logout_revokes_session(client, auth):
    r = await client.post(
        f"{API}/auth/login", json={"username": "admin", "password": PASSWORD, "client": "mobile"}
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(f"{API}/auth/me", headers=h)).status_code == 200
    await client.post(f"{API}/auth/logout", json={"refresh_token": r.json()["refresh_token"]})
    assert (await client.get(f"{API}/auth/me", headers=h)).status_code == 401


async def test_tampered_and_garbage_tokens_rejected(client, auth):
    token = auth["Authorization"].split()[1]
    for bad in (token[:-3] + "abc", "garbage", ""):
        r = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401


async def test_change_password_revokes_other_sessions(client, auth):
    other = await client.post(
        f"{API}/auth/login", json={"username": "admin", "password": PASSWORD, "client": "mobile"}
    )
    other_h = {"Authorization": f"Bearer {other.json()['access_token']}"}
    new_pw = "another long passphrase 42"
    r = await client.post(
        f"{API}/auth/change-password",
        headers=auth,
        json={"current_password": PASSWORD, "new_password": new_pw},
    )
    assert r.status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=auth)).status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=other_h)).status_code == 401
    bad = await client.post(
        f"{API}/auth/change-password",
        headers=auth,
        json={"current_password": "wrong", "new_password": new_pw + "x"},
    )
    assert bad.status_code == 400


async def test_sessions_list_and_revoke(client, auth):
    sessions = (await client.get(f"{API}/auth/sessions", headers=auth)).json()
    assert len(sessions) == 1 and sessions[0]["current"] is True
    assert "token" not in str(sessions[0]).lower()
    assert (
        await client.delete(f"{API}/auth/sessions/{sessions[0]['id']}", headers=auth)
    ).status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=auth)).status_code == 401


async def test_api_key_cannot_access_user_endpoints(client, auth):
    r = await client.post(f"{API}/auth/api-keys", headers=auth, json={"name": "backup-script"})
    assert r.status_code == 201
    body = r.json()
    assert body["key"].startswith("hlcc_")
    listed = (await client.get(f"{API}/auth/api-keys", headers=auth)).json()
    assert "key" not in listed[0] and "key_hash" not in listed[0]
    key_h = {"Authorization": f"Bearer {body['key']}"}
    assert (await client.get(f"{API}/settings", headers=key_h)).status_code == 401
    assert (await client.get(f"{API}/auth/me", headers=key_h)).status_code == 401


async def test_validation_errors_use_envelope_and_do_not_echo_input(client):
    r = await client.post(f"{API}/auth/login", json={"username": "a", "password": ["x" * 3]})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and "request_id" in err
    assert "xxx" not in r.text


async def test_unknown_route_uses_envelope(client):
    r = await client.get(f"{API}/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


async def test_oversized_body_rejected(client):
    r = await client.post(
        f"{API}/auth/login", content=b"x" * 300_000, headers={"content-type": "application/json"}
    )
    assert r.status_code == 413


async def test_security_headers_and_request_id(client):
    r = await client.get(f"{API}/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-request-id"]


@pytest.mark.parametrize(
    "body",
    [
        {"dashboard_refresh_seconds": 1},
        {"cpu_warn_percent": 99},
        {"unknown_field": 1},
        {"default_theme": "neon"},
    ],
)
async def test_settings_validation(client, auth, body):
    r = await client.patch(f"{API}/settings", headers=auth, json=body)
    assert r.status_code == 422, r.text


async def test_settings_roundtrip_persists(client, auth):
    r = await client.patch(
        f"{API}/settings",
        headers=auth,
        json={"dashboard_refresh_seconds": 30, "cpu_warn_percent": 70},
    )
    assert r.status_code == 200
    got = (await client.get(f"{API}/settings", headers=auth)).json()
    assert got["settings"]["dashboard_refresh_seconds"] == 30
    assert got["settings"]["cpu_warn_percent"] == 70
    assert "telegram_bot_token" not in str(got)
