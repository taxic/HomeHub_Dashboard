import asyncio

import pytest

from app.monitoring.docker_gateway import (
    DockerUnavailableError,
    compute_cpu_percent,
    compute_memory,
    parse_health,
)
from tests.conftest import make_settings

API = "/api/v1"


async def setup_services(client, auth):
    for name, cname, actions in [
        ("Plex", "plex", ["restart", "stop", "start"]),
        ("Navidrome", "navidrome", ["restart"]),
    ]:
        r = await client.post(
            f"{API}/services",
            headers=auth,
            json={
                "name": name,
                "container_name": cname,
                "allow_control": True,
                "allowed_actions": actions,
            },
        )
        assert r.status_code == 201, r.text
    # Pi-hole: associated but control NOT enabled
    await client.post(
        f"{API}/services", headers=auth, json={"name": "Pi-hole", "container_name": "pihole"}
    )
    # The app's own container, wrongly marked controllable
    await client.post(
        f"{API}/services",
        headers=auth,
        json={
            "name": "Self",
            "container_name": "homelab-backend",
            "allow_control": True,
            "allowed_actions": ["stop"],
        },
    )


@pytest.fixture
async def enabled(tmp_path, monkeypatch):
    """App with control enabled (the default is off)."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app(make_settings(tmp_path, docker_control_enabled=True))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c,
    ):
        yield app, c


async def login(c):
    from tests.conftest import PASSWORD

    await c.post(f"{API}/auth/setup", json={"username": "admin", "password": PASSWORD})
    r = await c.post(
        f"{API}/auth/login", json={"username": "admin", "password": PASSWORD, "client": "mobile"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def ctl(enabled, fake_docker):
    from app.monitoring.monitor import Monitor

    app, c = enabled
    m = Monitor(app.state.ctx, docker=fake_docker)
    app.state.ctx.monitor = m
    await m.refresh_docker()
    h = await login(c)
    await setup_services(c, h)
    return c, h, m, fake_docker


def cid(fake, name):
    return next(c.id for c in fake.containers.values() if c.name == name)


# ---------------------------------------------------------------- reading
async def test_unauthenticated_cannot_read_or_act(client, mon):
    for method, path in [
        ("GET", "/containers"),
        ("GET", "/containers/plex"),
        ("GET", "/containers/plex/logs"),
        ("POST", "/containers/plex/start"),
        ("POST", "/containers/plex/stop"),
        ("POST", "/containers/plex/restart"),
    ]:
        assert (await client.request(method, f"{API}{path}")).status_code == 401


async def test_list_and_detail_with_stats_and_service_association(ctl):
    c, h, m, fake = ctl
    data = (await c.get(f"{API}/containers", headers=h)).json()
    assert data["docker_available"] is True and data["refreshed_at"]
    by = {x["name"]: x for x in data["containers"]}
    assert set(by) == {"plex", "navidrome", "pihole", "homelab-backend", "old-thing"}
    plex = by["plex"]
    assert plex["service_name"] == "Plex" and plex["short_id"] == plex["id"][:12]
    assert plex["stats"]["cpu_percent"] == 20.0 and plex["stats"]["memory_bytes"] == 200
    assert by["old-thing"]["stats"] is None  # not running: unavailable, not zero
    assert plex["can_control"] is True and plex["allowed_actions"] == ["restart", "start", "stop"]
    assert by["pihole"]["can_control"] is False and by["pihole"]["service_name"] == "Pi-hole"
    assert by["old-thing"]["service_id"] is None
    one = (await c.get(f"{API}/containers/{plex['short_id']}", headers=h)).json()
    assert one["name"] == "plex"
    assert (await c.get(f"{API}/containers/plex", headers=h)).status_code == 200


async def test_unknown_or_malformed_container_refs(ctl):
    c, h, *_ = ctl
    assert (await c.get(f"{API}/containers/doesnotexist", headers=h)).status_code == 404
    for bad in ["a;b", "-rf", "x" * 200, "..%2Fetc"]:
        r = await c.get(f"{API}/containers/{bad}", headers=h)
        assert r.status_code in (404, 422), bad


async def test_logs_bounded(ctl):
    c, h, m, fake = ctl
    r = await c.get(f"{API}/containers/plex/logs?tail=1", headers=h)
    assert r.status_code == 200 and r.json()["lines"] == fake.log_lines[-1:]
    assert (await c.get(f"{API}/containers/plex/logs?tail=999999", headers=h)).status_code == 422
    assert (await c.get(f"{API}/containers/plex/logs?tail=0", headers=h)).status_code == 422


async def test_docker_unavailable_is_reported_not_faked(ctl):
    c, h, m, fake = ctl
    fake.down = True
    await m.refresh_docker()
    data = (await c.get(f"{API}/containers", headers=h)).json()
    assert data["docker_available"] is False and data["containers"] == [] and data["docker_error"]
    assert (await c.get(f"{API}/containers/plex", headers=h)).status_code == 503
    ov = (await c.get(f"{API}/overview", headers=h)).json()["containers"]
    assert ov["available"] is False and ov["running"] == 0


# ---------------------------------------------------------------- actions
async def test_action_success_updates_state_and_audits(ctl):
    c, h, m, fake = ctl
    r = await c.post(f"{API}/containers/plex/stop", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] and r.json()["state"] == "exited" and r.json()["action"] == "stop"
    assert fake.actions() == [("stop", cid(fake, "plex"))]
    # cached snapshot is immediately truthful
    assert (await c.get(f"{API}/containers/plex", headers=h)).json()["state"] == "exited"
    # intentional stop is recorded so no "unexpected stop" alert would be raised
    svc = next(
        s
        for s in (await c.get(f"{API}/services", headers=h)).json()["items"]
        if s["name"] == "Plex"
    )
    assert svc["expected_state"] == "stopped" and svc["effective_status"] == "unknown"
    r = await c.post(f"{API}/containers/plex/start", headers=h)
    assert r.json()["state"] == "running"
    ev = (await c.get(f"{API}/events?type=container", headers=h)).json()["items"]
    assert [e["type"] for e in ev][:2] == ["container.start", "container.stop"]
    assert all(e["actor"] == "admin" for e in ev)


async def test_only_permitted_actions_on_permitted_containers(ctl):
    c, h, m, fake = ctl
    # navidrome allows restart only
    assert (await c.post(f"{API}/containers/navidrome/stop", headers=h)).status_code == 403
    assert (await c.post(f"{API}/containers/navidrome/restart", headers=h)).status_code == 200
    # pihole: service exists but control not enabled
    r = await c.post(f"{API}/containers/pihole/restart", headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_permitted"
    # container with no service at all
    assert (await c.post(f"{API}/containers/old-thing/start", headers=h)).status_code == 403
    assert fake.actions() == [("restart", cid(fake, "navidrome"))]  # nothing else reached Docker


async def test_protected_container_cannot_be_controlled_even_if_configured(ctl):
    c, h, m, fake = ctl
    r = await c.post(f"{API}/containers/homelab-backend/stop", headers=h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "protected"
    assert fake.actions() == []
    info = (await c.get(f"{API}/containers/homelab-backend", headers=h)).json()
    assert info["protected"] is True and info["can_control"] is False


async def test_control_disabled_by_default(client, auth, mon, fake_docker):
    await mon.refresh_docker()
    await setup_services(client, auth)
    r = await client.post(f"{API}/containers/plex/restart", headers=auth)
    assert r.status_code == 403 and r.json()["error"]["code"] == "control_disabled"
    assert fake_docker.actions() == []
    assert (await client.get(f"{API}/containers/plex", headers=auth)).json()["can_control"] is False


@pytest.mark.parametrize("action", ["delete", "remove", "kill", "exec", "pause", "rm", "prune"])
async def test_no_destructive_endpoints_exist(ctl, action):
    c, h, m, fake = ctl
    r = await c.post(f"{API}/containers/plex/{action}", headers=h)
    assert r.status_code in (404, 405)
    for method in ("DELETE", "PUT", "PATCH"):
        assert (await c.request(method, f"{API}/containers/plex", headers=h)).status_code == 405
    assert fake.actions() == []


async def test_container_disappears_between_discovery_and_action(ctl):
    c, h, m, fake = ctl
    fake.gone.add(cid(fake, "plex"))
    r = await c.post(f"{API}/containers/plex/restart", headers=h)
    assert r.status_code == 404
    ev = (await c.get(f"{API}/events?type=container", headers=h)).json()["items"]
    assert ev[0]["type"] == "container.restart_failed" and ev[0]["severity"] == "warning"


async def test_docker_error_during_action_is_clean_503(ctl):
    c, h, m, fake = ctl
    fake.fail_action = DockerUnavailableError("tcp://secret-host:2375 refused")
    r = await c.post(f"{API}/containers/plex/restart", headers=h)
    assert r.status_code == 503 and "secret-host" not in r.text


async def test_unexpected_error_does_not_leak_internals(ctl):
    c, h, m, fake = ctl
    fake.fail_action = RuntimeError("/var/run/docker.sock permission denied at line 42")
    r = await c.post(f"{API}/containers/plex/restart", headers=h)
    assert r.status_code == 502 and "docker.sock" not in r.text


async def test_concurrent_actions_on_same_container_serialised(ctl):
    c, h, m, fake = ctl
    gate = asyncio.Event()
    orig = fake.perform

    async def slow(container_id, action):
        await gate.wait()
        return await orig(container_id, action)

    fake.perform = slow
    t1 = asyncio.create_task(c.post(f"{API}/containers/plex/restart", headers=h))
    await asyncio.sleep(0.1)
    r2 = await c.post(f"{API}/containers/plex/restart", headers=h)
    assert r2.status_code == 409
    gate.set()
    assert (await t1).status_code == 200


async def test_api_key_cannot_control_containers(ctl):
    c, h, m, fake = ctl
    key = (await c.post(f"{API}/auth/api-keys", headers=h, json={"name": "bk"})).json()["key"]
    r = await c.post(f"{API}/containers/plex/restart", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 401 and fake.actions() == []


# ---------------------------------------------------------------- helpers
def test_parse_health():
    assert parse_health("Up 2 hours (healthy)", None) == "healthy"
    assert parse_health("Up (unhealthy)", None) == "unhealthy"
    assert parse_health("Up (health: starting)", None) == "starting"
    assert parse_health("Up 1 hour", None) == "none"
    assert parse_health("running", "unhealthy") == "unhealthy"


def test_cpu_and_memory_math():
    stats = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 300},
            "system_cpu_usage": 3000,
            "online_cpus": 4,
        },
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        "memory_stats": {"usage": 1000, "limit": 4000, "stats": {"inactive_file": 200}},
    }
    assert compute_cpu_percent(stats) == 40.0
    assert compute_memory(stats) == (800, 4000)
    assert compute_cpu_percent({}) is None and compute_memory({}) == (None, None)
    assert (
        compute_cpu_percent(
            {
                "cpu_stats": {"cpu_usage": {"total_usage": 5}, "system_cpu_usage": 10},
                "precpu_stats": {"cpu_usage": {"total_usage": 5}, "system_cpu_usage": 10},
            }
        )
        is None
    )
