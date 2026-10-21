from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Alert, Event, MetricSample
from app.schemas.settings import AppSettings
from app.services import metrics_service
from tests.conftest import make_settings

API = "/api/v1"
NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def sample(ts, res=60, **kw):
    return MetricSample(ts=ts, resolution=res, **kw)


async def test_persist_skips_empty_and_duplicate_rows(app):
    from app.monitoring.host import HostCollector

    host = HostCollector().collect()
    host.cpu_percent = host.memory = host.swap = host.network = host.load_avg = None
    host.temperature_c = None
    assert metrics_service.sample_from_snapshot(host, [], None, NOW) is None  # nothing measured

    async with app.state.ctx.session_factory() as s:
        assert await metrics_service.persist_sample(s, sample(NOW, cpu_percent=1.0)) is True
        await s.commit()
        assert await metrics_service.persist_sample(s, sample(NOW, cpu_percent=2.0)) is False


async def test_rollup_averages_ignoring_nulls_and_prunes(app):
    cfg = AppSettings(retention_raw_hours=6, retention_rollup_days=7)
    async with app.state.ctx.session_factory() as s:
        old = NOW - timedelta(hours=10)
        base = old.replace(minute=0, second=0)
        s.add_all(
            [
                sample(base + timedelta(minutes=0), cpu_percent=10, temp_c=None),
                sample(base + timedelta(minutes=1), cpu_percent=30, temp_c=None),
                sample(base + timedelta(minutes=2), cpu_percent=None, temp_c=50),
                sample(base + timedelta(minutes=6), cpu_percent=50),
            ]
        )
        recent = NOW - timedelta(minutes=5)
        s.add(sample(recent, cpu_percent=99))
        s.add(sample(NOW - timedelta(days=9), res=300, cpu_percent=1))  # beyond rollup retention
        await s.commit()
        result = await metrics_service.rollup_and_prune(s, cfg, now=NOW)
        await s.commit()
        assert (
            result["rolled_up"] == 2
            and result["deleted_raw"] == 4
            and result["deleted_rollup"] == 1
        )
        rows = (await s.execute(select(MetricSample).order_by(MetricSample.ts))).scalars().all()
        assert [r.resolution for r in rows] == [300, 300, 60]
        assert (
            rows[0].cpu_percent == 20.0 and rows[0].temp_c == 50
        )  # null ignored, not treated as 0
        assert rows[1].cpu_percent == 50 and rows[1].temp_c is None  # all-null stays null
        # idempotent
        again = await metrics_service.rollup_and_prune(s, cfg, now=NOW)
        assert again["rolled_up"] == 0 and again["deleted_raw"] == 0


async def test_retention_prunes_events_and_resolved_alerts(app):
    cfg = AppSettings(retention_events_days=7)
    async with app.state.ctx.session_factory() as s:
        s.add_all(
            [
                Event(ts=NOW - timedelta(days=30), type="x", message="old"),
                Event(ts=NOW, type="x", message="new"),
            ]
        )
        s.add_all(
            [
                Alert(
                    key="a",
                    type="t",
                    severity="warning",
                    status="resolved",
                    title="old",
                    message="m",
                    first_seen_at=NOW - timedelta(days=40),
                    last_seen_at=NOW - timedelta(days=40),
                    resolved_at=NOW - timedelta(days=39),
                ),
                Alert(
                    key="b",
                    type="t",
                    severity="warning",
                    status="open",
                    title="open-old",
                    message="m",
                    first_seen_at=NOW - timedelta(days=40),
                    last_seen_at=NOW,
                ),
            ]
        )
        await s.commit()
        res = await metrics_service.rollup_and_prune(s, cfg, now=NOW)
        await s.commit()
        assert res["deleted_events"] == 1 and res["deleted_alerts"] == 1
        assert (
            await s.execute(select(func.count()).select_from(Alert))
        ).scalar_one() == 1  # open one kept


async def test_history_buckets_and_range_validation(client, auth, app):
    now = datetime.now(UTC).replace(microsecond=0)
    async with app.state.ctx.session_factory() as s:
        for i in range(10):
            s.add(sample(now - timedelta(minutes=i), cpu_percent=float(i), mem_percent=50.0))
        s.add(sample(now - timedelta(days=3), res=300, cpu_percent=7.0))
        await s.commit()
    h = (await client.get(f"{API}/metrics/history?range=1h", headers=auth)).json()
    assert h["bucket_seconds"] == 60 and len(h["points"]) == 10
    assert h["points"][0]["swap_percent"] is None  # unavailable stays null
    d7 = (await client.get(f"{API}/metrics/history?range=7d", headers=auth)).json()
    assert d7["bucket_seconds"] == 1800 and any(p["cpu_percent"] == 7.0 for p in d7["points"])
    assert (await client.get(f"{API}/metrics/history?range=5y", headers=auth)).status_code == 422
    assert (await client.get(f"{API}/metrics/history")).status_code == 401


async def test_history_survives_restart(tmp_path):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app
    from tests.conftest import PASSWORD

    cfg = make_settings(tmp_path)
    app1 = create_app(cfg)
    async with app1.router.lifespan_context(app1):
        async with app1.state.ctx.session_factory() as s:
            s.add(
                sample(
                    datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=2),
                    cpu_percent=42.0,
                )
            )
            await s.commit()
    app2 = create_app(make_settings(tmp_path))  # fresh process, same data dir
    async with (
        app2.router.lifespan_context(app2),
        AsyncClient(transport=ASGITransport(app=app2), base_url="http://t") as c,
    ):
        await c.post(f"{API}/auth/setup", json={"username": "admin", "password": PASSWORD})
        r = await c.post(
            f"{API}/auth/login",
            json={"username": "admin", "password": PASSWORD, "client": "mobile"},
        )
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        pts = (await c.get(f"{API}/metrics/history?range=1h", headers=h)).json()["points"]
        assert [p["cpu_percent"] for p in pts] == [42.0]


async def test_current_metrics_unavailable_until_first_sample(client, auth, mon):
    r = (await client.get(f"{API}/metrics/current", headers=auth)).json()
    assert r == {"available": False, "host": None, "sampled_at": None, "stale": False}
    await mon.sample_host()
    r = (await client.get(f"{API}/metrics/current", headers=auth)).json()
    assert r["available"] and r["host"]["memory"]["total_bytes"] > 0 and r["stale"] is False


async def test_stale_data_is_flagged(client, auth, mon):
    await mon.sample_host()
    mon.host.sampled_at = datetime.now(UTC) - timedelta(minutes=10)
    assert (await client.get(f"{API}/metrics/current", headers=auth)).json()["stale"] is True
    ov = (await client.get(f"{API}/overview", headers=auth)).json()
    assert ov["stale"] is True and ov["status"] == "unknown"


async def test_persist_loop_row_from_real_sample(app, mon):
    await mon.sample_host()
    row = metrics_service.sample_from_snapshot(
        mon.host, mon.volumes, mon.root_volume, datetime.now(UTC)
    )
    assert row is not None and row.mem_percent is not None and row.disk_root_percent is not None
    assert row.storage_max_percent is None  # no external volumes configured => unavailable, not 0
