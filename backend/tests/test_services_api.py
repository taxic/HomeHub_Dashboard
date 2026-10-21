import httpx
import pytest

API = "/api/v1"


async def create(client, auth, **kw):
    body = {"name": "Plex", "category": "media", "url": "http://192.168.1.5:32400/web", **kw}
    return await client.post(f"{API}/services", headers=auth, json=body)


async def test_requires_auth(client):
    for method, path in [
        ("GET", "/services"),
        ("POST", "/services"),
        ("GET", "/services/1"),
        ("PATCH", "/services/1"),
        ("DELETE", "/services/1"),
        ("POST", "/services/1/check"),
    ]:
        r = await client.request(
            method, f"{API}{path}", json={} if method in ("POST", "PATCH") else None
        )
        assert r.status_code == 401, (method, path)


async def test_crud_lifecycle(client, auth):
    r = await create(client, auth, description="Media server", icon="plex", container_name="plex")
    assert r.status_code == 201, r.text
    svc = r.json()
    assert svc["health_status"] == "unknown" and svc["allow_control"] is False
    sid = svc["id"]

    assert (await client.get(f"{API}/services/{sid}", headers=auth)).json()["name"] == "Plex"
    page = (await client.get(f"{API}/services", headers=auth)).json()
    assert page["total"] == 1 and page["items"][0]["id"] == sid

    r = await client.patch(
        f"{API}/services/{sid}", headers=auth, json={"interval_seconds": 120, "enabled": False}
    )
    assert (
        r.status_code == 200
        and r.json()["interval_seconds"] == 120
        and r.json()["effective_status"] == "disabled"
    )

    assert (await client.delete(f"{API}/services/{sid}", headers=auth)).status_code == 200
    assert (await client.get(f"{API}/services/{sid}", headers=auth)).status_code == 404


async def test_new_service_without_code_changes_listed_by_category(client, auth):
    await create(client, auth, name="A", category="media")
    await create(client, auth, name="B", category="network", url="http://192.168.1.2/admin")
    only = (await client.get(f"{API}/services?category=network", headers=auth)).json()
    assert [s["name"] for s in only["items"]] == ["B"]


@pytest.mark.parametrize(
    "patch",
    [
        {"url": "ftp://192.168.1.5/"},
        {"url": "http://user:pass@192.168.1.5/"},
        {"url": "javascript:alert(1)"},
        {"url": "http://169.254.169.254/latest/meta-data/"},
        {"url": "http://127.0.0.1:8000/api/v1/settings"},
        {"url": "http://metadata.google.internal/"},
        {"interval_seconds": 1},
        {"timeout_seconds": 500},
        {"expected_status": "abc"},
        {"expected_status": "700"},
        {"container_name": "bad name; rm -rf /"},
        {"container_name": "../etc"},
        {"name": "  "},
        {"allowed_actions": ["delete"]},
        {"unknown_field": 1},
    ],
)
async def test_validation_and_ssrf_rejected_on_create(client, auth, patch):
    r = await create(client, auth, **patch)
    assert r.status_code == 422, (patch, r.text)
    assert r.json()["error"]["code"] in ("validation_error", "blocked_url")


async def test_duplicate_name_conflict(client, auth):
    assert (await create(client, auth)).status_code == 201
    r = await create(client, auth, name="plex")
    assert r.status_code == 409


async def test_service_needs_url_or_container(client, auth):
    r = await client.post(f"{API}/services", headers=auth, json={"name": "Empty"})
    assert r.status_code == 422


async def test_docker_only_service_allowed(client, auth):
    r = await client.post(
        f"{API}/services", headers=auth, json={"name": "Syncthing", "container_name": "syncthing"}
    )
    assert r.status_code == 201 and r.json()["url"] is None


async def test_control_requires_container_and_actions(client, auth):
    r = await create(client, auth, allow_control=True)
    assert r.status_code == 422
    r = await create(client, auth, container_name="plex", allow_control=True)
    assert r.status_code == 422
    r = await create(
        client,
        auth,
        container_name="plex",
        allow_control=True,
        allowed_actions=["restart", "restart"],
    )
    assert r.status_code == 201 and r.json()["allowed_actions"] == ["restart"]


async def test_clearing_container_revokes_control(client, auth):
    sid = (
        await create(
            client, auth, container_name="plex", allow_control=True, allowed_actions=["restart"]
        )
    ).json()["id"]
    r = await client.patch(f"{API}/services/{sid}", headers=auth, json={"container_name": None})
    assert r.status_code == 200 and r.json()["allow_control"] is False


async def test_patching_url_to_blocked_target_rejected(client, auth):
    sid = (await create(client, auth)).json()["id"]
    r = await client.patch(
        f"{API}/services/{sid}", headers=auth, json={"url": "http://169.254.169.254/"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "blocked_url"


async def test_manual_check_updates_result(client, auth, mon):
    sid = (await create(client, auth)).json()["id"]
    r = await client.post(f"{API}/services/{sid}/check", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["health_status"] == "healthy" and body["last_status_code"] == 200
    assert (
        body["last_success_at"]
        and body["last_response_ms"] is not None
        and body["effective_status"] == "healthy"
    )


async def test_failure_debounced_until_threshold_then_unhealthy_then_recovers(
    client, auth, mon, monkeypatch
):
    from app.monitoring import healthcheck

    monkeypatch.setattr(healthcheck, "BACKOFF_SECONDS", 0)
    sid = (await create(client, auth)).json()["id"]
    await client.post(f"{API}/services/{sid}/check", headers=auth)  # healthy

    mon.http_state["handler"] = lambda req: httpx.Response(500)
    r1 = (await client.post(f"{API}/services/{sid}/check", headers=auth)).json()
    assert r1["consecutive_failures"] == 1 and r1["health_status"] == "healthy"  # blip tolerated
    assert r1["last_error"] and r1["last_success_at"]
    r2 = (await client.post(f"{API}/services/{sid}/check", headers=auth)).json()
    assert r2["health_status"] == "unhealthy" and r2["effective_status"] == "unhealthy"

    mon.http_state["handler"] = lambda req: httpx.Response(200)
    r3 = (await client.post(f"{API}/services/{sid}/check", headers=auth)).json()
    assert r3["health_status"] == "healthy" and r3["consecutive_failures"] == 0
    types = [
        e["type"]
        for e in (await client.get(f"{API}/events?type=service", headers=auth)).json()["items"]
    ]
    assert "service.unhealthy" in types and "service.recovered" in types


async def test_check_without_url_is_400(client, auth, mon):
    sid = (
        await client.post(
            f"{API}/services", headers=auth, json={"name": "d", "container_name": "x"}
        )
    ).json()["id"]
    assert (await client.post(f"{API}/services/{sid}/check", headers=auth)).status_code == 400


async def test_slow_check_does_not_block_api_and_no_overlap(client, auth, mon):
    import asyncio

    gate = asyncio.Event()
    calls = []

    async def slow_check(*a, **kw):
        calls.append(1)
        await gate.wait()
        from app.monitoring.healthcheck import CheckResult

        return CheckResult(True, 200, 5.0, None)

    mon.checker.check = slow_check
    sid = (await create(client, auth)).json()["id"]
    first = asyncio.create_task(mon.check_service(sid))
    await asyncio.sleep(0.05)
    assert (await client.get(f"{API}/health")).status_code == 200  # API stays responsive
    assert await mon.check_service(sid) is False  # no overlapping check for the same service
    gate.set()
    assert await first is True and len(calls) == 1


async def test_scheduler_only_runs_due_enabled_services(client, auth, mon):
    a = (await create(client, auth, name="a")).json()["id"]
    b = (await create(client, auth, name="b", url="http://192.168.1.9/", enabled=False)).json()[
        "id"
    ]
    ran = []

    async def fake_run(sid):
        ran.append(sid)

    mon._run_check = fake_run
    await mon._schedule_due()
    import asyncio

    await asyncio.sleep(0.05)
    assert ran == [a] and b not in ran
