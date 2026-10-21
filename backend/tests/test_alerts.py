import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models import Alert, Service
from app.notifications.telegram import TelegramNotifier
from app.schemas.metrics import VolumeStatus
from app.services.alert_engine import AlertEngine
from tests.fakes import make_container

API = "/api/v1"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class Recorder:
    name = "rec"

    def __init__(self):
        self.sent = []

    def configured(self):
        return True

    async def send(self, n):
        self.sent.append(n)


@pytest.fixture
async def engine(app, mon):
    app.state.ctx.runtime = app.state.ctx.runtime.model_copy(update={"telegram_enabled": True})
    rec = Recorder()
    eng = AlertEngine(app.state.ctx, mon, [rec])
    eng.rec = rec
    mon.alert_engine = eng
    await mon.sample_host()
    return eng


async def open_alerts(app, status="open"):
    async with app.state.ctx.session_factory() as s:
        return list((await s.execute(select(Alert).where(Alert.status == status))).scalars())


async def run(engine, n=2):
    """Conditions need CONFIRM_CYCLES consecutive evaluations."""
    for _ in range(n):
        await engine.evaluate(NOW)


def volume(state="ok", percent=10.0, id_=1, required=True):
    return VolumeStatus(
        id=id_,
        name="Media HDD",
        path="/mnt/media",
        kind="external",
        required=required,
        state=state,
        percent=percent,
        message="Path is not a mount point" if state != "ok" else None,
        checked_at=NOW,
    )


def fill_samples(mon, cpu, minutes=6, mem=20.0):
    mon.recent.clear()
    base = time.monotonic()
    for i in range(minutes * 6 + 1):
        mon.recent.append((base - minutes * 60 + i * 10, cpu, mem))


async def test_transient_condition_needs_confirmation(app, engine, mon):
    mon.volumes = [volume("unmounted")]
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []  # single blip: nothing yet
    mon.volumes = [volume("ok")]
    await engine.evaluate(NOW)
    mon.volumes = [volume("unmounted")]
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []  # streak was reset by the recovery in between


async def test_missing_mount_alert_lifecycle_and_dedup(app, engine, mon):
    mon.volumes = [volume("unmounted")]
    await run(engine, 5)
    alerts = await open_alerts(app)
    assert len(alerts) == 1  # deduplicated across cycles
    a = alerts[0]
    assert a.type == "mount_unavailable" and a.severity == "critical" and a.occurrences >= 1
    assert "Nothing was modified" in a.message
    assert len(engine.rec.sent) == 1  # one notification, not one per cycle
    mon.volumes = [volume("ok")]
    await engine.evaluate(NOW + timedelta(minutes=1))
    assert await open_alerts(app) == []
    resolved = await open_alerts(app, "resolved")
    assert len(resolved) == 1 and resolved[0].resolved_at
    assert [n.kind for n in engine.rec.sent] == ["opened", "resolved"]


async def test_non_required_volume_does_not_alert(app, engine, mon):
    mon.volumes = [volume("missing", required=False)]
    await run(engine, 3)
    assert await open_alerts(app) == []


async def test_storage_usage_warning_then_critical_escalates_and_notifies(app, engine, mon):
    mon.volumes = [volume(percent=88.0)]
    await run(engine)
    (a,) = await open_alerts(app)
    assert a.severity == "warning"
    mon.volumes = [volume(percent=97.0)]
    await engine.evaluate(NOW)
    (a,) = await open_alerts(app)
    assert a.severity == "critical"
    assert [n.kind for n in engine.rec.sent] == ["opened", "escalated"]
    mon.volumes = [volume(percent=50.0)]
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []


async def test_threshold_is_configurable(app, engine, mon, client, auth):
    mon.volumes = [volume(percent=60.0)]
    await run(engine)
    assert await open_alerts(app) == []
    r = await client.patch(
        f"{API}/settings",
        headers=auth,
        json={"storage_warn_percent": 50, "storage_crit_percent": 90},
    )
    assert r.status_code == 200
    await run(engine)
    assert (await open_alerts(app))[0].severity == "warning"


async def test_cpu_alert_requires_sustained_usage(app, engine, mon):
    fill_samples(mon, cpu=99.0, minutes=1)  # only 1 minute of history; needs 5
    await run(engine, 3)
    assert await open_alerts(app) == []
    fill_samples(mon, cpu=99.0, minutes=6)
    await run(engine)
    (a,) = await open_alerts(app)
    assert a.type == "cpu_high" and a.severity == "critical"
    fill_samples(mon, cpu=10.0, minutes=6)
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []


async def test_cpu_spike_in_window_does_not_alert(app, engine, mon):
    fill_samples(mon, cpu=99.0, minutes=6)
    mon.recent[len(mon.recent) // 2] = (mon.recent[len(mon.recent) // 2][0], 5.0, 20.0)
    await run(engine, 3)
    assert await open_alerts(app) == []


async def test_memory_alert(app, engine, mon):
    fill_samples(mon, cpu=5.0, minutes=6, mem=90.0)
    await run(engine)
    (a,) = await open_alerts(app)
    assert a.type == "mem_high" and a.severity == "warning"


async def test_service_down_alert_and_recovery(app, engine, mon, client, auth):
    sid = (
        await client.post(
            f"{API}/services",
            headers=auth,
            json={"name": "Plex", "url": "http://192.168.1.5:32400/web"},
        )
    ).json()["id"]
    async with app.state.ctx.session_factory() as s:
        svc = await s.get(Service, sid)
        svc.health_status, svc.last_error = "unhealthy", "Timed out after 5s"
        await s.commit()
    await run(engine)
    (a,) = await open_alerts(app)
    assert a.type == "service_down" and "Plex" in a.title and a.message == "Timed out after 5s"
    async with app.state.ctx.session_factory() as s:
        (await s.get(Service, sid)).health_status = "healthy"
        await s.commit()
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []


async def test_container_unexpected_stop_but_not_intentional_stop(
    app, engine, mon, client, auth, fake_docker
):
    await client.post(
        f"{API}/services", headers=auth, json={"name": "Plex", "container_name": "plex"}
    )
    await client.post(
        f"{API}/services",
        headers=auth,
        json={
            "name": "Navidrome",
            "container_name": "navidrome",
            "allow_control": True,
            "allowed_actions": ["stop"],
        },
    )
    await mon.refresh_docker()
    await run(engine)
    assert await open_alerts(app) == []
    for c in fake_docker.containers.values():
        if c.name in ("plex", "navidrome"):
            c.state = "exited"
    # navidrome was stopped on purpose through the app => expected_state=stopped
    async with app.state.ctx.session_factory() as s:
        nav = (await s.execute(select(Service).where(Service.name == "Navidrome"))).scalar_one()
        nav.expected_state = "stopped"
        await s.commit()
    await mon.refresh_docker()
    await run(engine)
    (a,) = await open_alerts(app)
    assert a.type == "container_down" and "Plex" in a.title


async def test_docker_outage_does_not_resolve_container_alerts(
    app, engine, mon, client, auth, fake_docker
):
    await client.post(
        f"{API}/services", headers=auth, json={"name": "Plex", "container_name": "plex"}
    )
    fake_docker.containers = {k: v for k, v in fake_docker.containers.items() if v.name != "plex"}
    await mon.refresh_docker()
    await run(engine)
    assert [a.type for a in await open_alerts(app)] == ["container_down"]
    fake_docker.down = True
    await mon.refresh_docker()
    await run(engine)
    types = sorted(a.type for a in await open_alerts(app))
    assert types == ["container_down", "docker_unavailable"]  # can't claim recovery while blind
    fake_docker.down = False
    fake_docker.containers["x"] = make_container("plex")
    await mon.refresh_docker()
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []


async def test_docker_never_reachable_does_not_alert(app, engine, mon, fake_docker):
    fake_docker.down = True
    await mon.refresh_docker()
    await run(engine, 3)
    assert await open_alerts(app) == []  # a host without Docker access is not an incident


async def test_acknowledge_flow_and_no_reminder_when_acked(app, engine, mon, client, auth):
    mon.volumes = [volume("missing")]
    await run(engine)
    a = (await client.get(f"{API}/alerts", headers=auth)).json()["items"][0]
    assert a["acknowledged_at"] is None
    r = await client.post(f"{API}/alerts/{a['id']}/acknowledge", headers=auth)
    assert r.status_code == 200 and r.json()["acknowledged_by"] == "admin"
    # past the renotify window, an acknowledged alert stays quiet
    await engine.evaluate(NOW + timedelta(hours=10))
    assert [n.kind for n in engine.rec.sent] == ["opened"]
    assert (await client.post(f"{API}/alerts/9999/acknowledge", headers=auth)).status_code == 404
    assert (await client.post(f"{API}/alerts/{a['id']}/acknowledge")).status_code == 401
    ev = [
        e["type"]
        for e in (await client.get(f"{API}/events?type=alert", headers=auth)).json()["items"]
    ]
    assert "alert.acknowledged" in ev and "alert.opened" in ev


async def test_reminder_after_cooldown_for_unacknowledged(app, engine, mon):
    mon.volumes = [volume("missing")]
    await run(engine)
    await engine.evaluate(NOW + timedelta(minutes=30))
    assert len(engine.rec.sent) == 1  # within the cooldown (default 240 min)
    await engine.evaluate(NOW + timedelta(hours=5))
    assert [n.kind for n in engine.rec.sent] == ["opened", "reminder"]


async def test_flapping_reopens_in_app_but_does_not_spam_notifications(app, engine, mon):
    for i in range(3):
        t = NOW + timedelta(minutes=i * 2)
        mon.volumes = [volume("missing")]
        await engine.evaluate(t)
        await engine.evaluate(t + timedelta(seconds=15))
        mon.volumes = [volume("ok")]
        await engine.evaluate(t + timedelta(minutes=1))
    assert len(await open_alerts(app, "resolved")) == 3  # full history is kept in-app
    # one "opened" + one "resolved"; the two flap re-opens stay silent (no notification spam)
    assert [n.kind for n in engine.rec.sent] == ["opened", "resolved"]


async def test_notification_min_severity_and_disabled_toggle(app, engine, mon):
    app.state.ctx.runtime = app.state.ctx.runtime.model_copy(
        update={"notify_min_severity": "critical"}
    )
    mon.volumes = [volume(percent=88.0)]  # warning only
    await run(engine)
    assert len(await open_alerts(app)) == 1 and engine.rec.sent == []
    app.state.ctx.runtime = app.state.ctx.runtime.model_copy(
        update={"telegram_enabled": False, "notify_min_severity": "warning"}
    )
    mon.volumes = [volume("missing", id_=2)]
    await run(engine)
    assert engine.rec.sent == []  # telegram disabled => in-app only


async def test_stale_host_data_alert(app, engine, mon):
    mon.host.sampled_at = datetime.now(UTC) - timedelta(minutes=10)
    await run(engine)
    assert [a.type for a in await open_alerts(app)] == ["monitor_stale"]


async def test_alerts_for_deleted_service_are_resolved(app, engine, mon, client, auth):
    sid = (
        await client.post(
            f"{API}/services", headers=auth, json={"name": "X", "url": "http://192.168.1.5/"}
        )
    ).json()["id"]
    async with app.state.ctx.session_factory() as s:
        (await s.get(Service, sid)).health_status = "unhealthy"
        await s.commit()
    await run(engine)
    assert len(await open_alerts(app)) == 1
    await client.delete(f"{API}/services/{sid}", headers=auth)
    await engine.evaluate(NOW)
    assert await open_alerts(app) == []


async def test_alert_list_filters_and_pagination(app, engine, mon, client, auth):
    mon.volumes = [volume("missing", id_=1), volume(percent=90.0, id_=2)]
    await run(engine)
    all_open = (await client.get(f"{API}/alerts", headers=auth)).json()
    assert all_open["total"] == 2
    crit = (await client.get(f"{API}/alerts?severity=critical", headers=auth)).json()
    assert crit["total"] == 1
    page = (await client.get(f"{API}/alerts?limit=1&offset=1", headers=auth)).json()
    assert len(page["items"]) == 1 and page["total"] == 2
    assert (await client.get(f"{API}/alerts?limit=1000", headers=auth)).status_code == 422
    assert (await client.get(f"{API}/alerts?status=bogus", headers=auth)).status_code == 422
    assert (await client.get(f"{API}/alerts")).status_code == 401


# ------------------------------------------------------------------ telegram
async def test_telegram_sends_and_never_logs_token(caplog):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["body"] = str(req.url), req.content.decode()
        return httpx.Response(200, json={"ok": True})

    from app.notifications.base import Notification

    n = TelegramNotifier("123:SECRET", "42", transport=httpx.MockTransport(handler))
    await n.send(Notification("opened", "critical", "Disk gone", "details"))
    assert "bot123:SECRET/sendMessage" in seen["url"] and "Disk gone" in seen["body"]

    def boom(req):
        raise httpx.ConnectError("failed for https://api.telegram.org/bot123:SECRET/sendMessage")

    n2 = TelegramNotifier("123:SECRET", "42", transport=httpx.MockTransport(boom))
    with caplog.at_level("DEBUG"), pytest.raises(RuntimeError):
        await n2.send(Notification("opened", "warning", "t", "m"))
    assert "SECRET" not in caplog.text and n2.failures == 1


async def test_notifier_failure_does_not_break_alerting(app, engine, mon):
    class Failing(Recorder):
        async def send(self, n):
            raise RuntimeError("down")

    engine.notifiers = [Failing()]
    mon.volumes = [volume("missing")]
    await run(engine)
    assert len(await open_alerts(app)) == 1


async def test_test_notification_endpoint(client, auth, app):
    r = await client.post(f"{API}/settings/test-notification", headers=auth)
    assert r.status_code in (400,)  # not configured in the test env (no monitor/extras)
    assert (await client.post(f"{API}/settings/test-notification")).status_code == 401
    app.state.ctx.extras["telegram"] = TelegramNotifier(
        "1:tok",
        "9",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True})),
    )
    assert (await client.post(f"{API}/settings/test-notification", headers=auth)).status_code == 200
    app.state.ctx.extras["telegram"] = TelegramNotifier(
        "1:tok", "9", transport=httpx.MockTransport(lambda req: httpx.Response(401))
    )
    r = await client.post(f"{API}/settings/test-notification", headers=auth)
    assert r.status_code == 502 and "tok" not in r.text
