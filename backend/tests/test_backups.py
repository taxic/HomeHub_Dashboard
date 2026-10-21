from datetime import UTC, datetime, timedelta

import pytest

from app.models import BackupJob
from app.services.backup_service import compute_state

API = "/api/v1"


def iso(dt):
    return dt.isoformat()


async def make_job(client, auth, **kw):
    r = await client.post(
        f"{API}/backups", headers=auth, json={"name": "Nightly", "max_age_hours": 36, **kw}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def report(client, headers, jid, **kw):
    body = {"status": "success", **kw}
    return await client.post(f"{API}/backups/{jid}/report", headers=headers, json=body)


async def test_new_job_has_never_run_state(client, auth):
    job = await make_job(
        client, auth, schedule_text="daily 02:00", report_path="/var/log/backup.log"
    )
    assert job["state"] == "never_run" and job["last_success_at"] is None


async def test_reported_success_is_not_verified(client, auth):
    jid = (await make_job(client, auth))["id"]
    r = await report(client, auth, jid, message="rsync ok", size_bytes=5_000_000_000)
    assert r.status_code == 200
    j = r.json()
    assert j["state"] == "reported_success" and "no restore test" in j["state_reason"]
    assert j["age_hours"] is not None and j["last_restore_test_at"] is None


async def test_only_a_restore_test_makes_it_verified(client, auth):
    jid = (await make_job(client, auth))["id"]
    await report(client, auth, jid)
    j = (
        await report(
            client, auth, jid, kind="restore_test", message="restored 3 files, checksums match"
        )
    ).json()
    assert j["state"] == "restore_verified" and j["last_restore_test_success_at"]
    # A failed restore test overrides the comfort of "reported success".
    j = (
        await report(client, auth, jid, kind="restore_test", status="failed", message="corrupt")
    ).json()
    assert j["state"] == "restore_failed"


async def test_failed_backup_then_success(client, auth):
    jid = (await make_job(client, auth))["id"]
    await report(client, auth, jid, finished_at=iso(datetime.now(UTC) - timedelta(hours=2)))
    j = (await report(client, auth, jid, status="failed", message="disk full")).json()
    assert j["state"] == "failed" and j["state_reason"] == "disk full" and j["last_success_at"]
    j = (await report(client, auth, jid)).json()
    assert j["state"] == "reported_success"


async def test_overdue_when_too_old(client, auth):
    jid = (await make_job(client, auth, max_age_hours=24))["id"]
    j = (
        await report(client, auth, jid, finished_at=iso(datetime.now(UTC) - timedelta(hours=30)))
    ).json()
    assert j["state"] == "overdue" and "30h ago" in j["state_reason"]


async def test_old_restore_test_expires_verification(client, auth):
    jid = (await make_job(client, auth, verification_max_age_days=30))["id"]
    await report(client, auth, jid)
    j = (
        await report(
            client,
            auth,
            jid,
            kind="restore_test",
            finished_at=iso(datetime.now(UTC) - timedelta(days=45)),
        )
    ).json()
    assert j["state"] == "reported_success"


async def test_out_of_order_report_does_not_regress_state(client, auth):
    jid = (await make_job(client, auth))["id"]
    await report(client, auth, jid)
    j = (
        await report(
            client,
            auth,
            jid,
            status="failed",
            finished_at=iso(datetime.now(UTC) - timedelta(hours=5)),
        )
    ).json()
    assert j["state"] == "reported_success"  # the older failure is history, not current state


@pytest.mark.parametrize(
    "body",
    [
        {"status": "success", "finished_at": "2999-01-01T00:00:00+00:00"},
        {"status": "success", "finished_at": "2001-01-01T00:00:00+00:00"},
        {"status": "success", "finished_at": "2026-01-01T00:00:00"},
        {"status": "maybe"},
        {"status": "success", "kind": "delete"},
        {"status": "success", "size_bytes": -1},
        {"status": "success", "message": "x" * 501},
        {"status": "success", "extra": 1},
    ],
)
async def test_report_validation(client, auth, body):
    jid = (await make_job(client, auth))["id"]
    r = await client.post(f"{API}/backups/{jid}/report", headers=auth, json=body)
    assert r.status_code == 422, body


async def test_api_key_can_report_but_nothing_else(client, auth):
    jid = (await make_job(client, auth))["id"]
    key = (
        await client.post(f"{API}/auth/api-keys", headers=auth, json={"name": "nightly-script"})
    ).json()
    kh = {"Authorization": f"Bearer {key['key']}"}
    r = await report(client, kh, jid, message="from script")
    assert r.status_code == 200
    ev = (await client.get(f"{API}/events?type=backup", headers=auth)).json()["items"][0]
    assert ev["actor"] == "apikey:nightly-script"
    for method, path in [
        ("GET", "/backups"),
        ("DELETE", f"/backups/{jid}"),
        ("PATCH", f"/backups/{jid}"),
        ("GET", "/containers"),
        ("GET", "/overview"),
    ]:
        assert (
            await client.request(
                method, f"{API}{path}", headers=kh, json={} if method == "PATCH" else None
            )
        ).status_code == 401, path
    # revoke => reports rejected
    await client.delete(f"{API}/auth/api-keys/{key['id']}", headers=auth)
    assert (await report(client, kh, jid)).status_code == 401
    assert (await report(client, {"Authorization": "Bearer hlcc_forged"}, jid)).status_code == 401
    assert (
        await client.post(f"{API}/backups/{jid}/report", json={"status": "success"})
    ).status_code == 401


async def test_report_unknown_job_404(client, auth):
    assert (await report(client, auth, 999)).status_code == 404


async def test_crud_and_unique_names(client, auth):
    job = await make_job(client, auth)
    assert (
        await client.post(f"{API}/backups", headers=auth, json={"name": "nightly"})
    ).status_code == 409
    r = await client.patch(
        f"{API}/backups/{job['id']}", headers=auth, json={"max_age_hours": 48, "enabled": False}
    )
    assert r.json()["max_age_hours"] == 48 and r.json()["state"] == "disabled"
    assert (
        await client.patch(f"{API}/backups/{job['id']}", headers=auth, json={"max_age_hours": 0})
    ).status_code == 422
    reports = (await client.get(f"{API}/backups/{job['id']}/reports", headers=auth)).json()
    assert reports == []
    assert (await client.delete(f"{API}/backups/{job['id']}", headers=auth)).status_code == 200
    assert (await client.get(f"{API}/backups/{job['id']}", headers=auth)).status_code == 404


async def test_overview_counts_backup_problems(client, auth, mon):
    ok = (await make_job(client, auth))["id"]
    await make_job(client, auth, name="Offsite")  # never run
    await report(client, auth, ok)
    ov = (await client.get(f"{API}/overview", headers=auth)).json()["backups"]
    assert ov == {"total": 2, "ok": 1, "problem": 1}


async def test_overdue_backup_raises_alert_after_grace(app, mon, client, auth):
    from sqlalchemy import select

    from app.models import Alert
    from app.services.alert_engine import AlertEngine

    await mon.sample_host()
    eng = AlertEngine(app.state.ctx, mon, [])
    jid = (await make_job(client, auth, max_age_hours=24))["id"]
    now = datetime.now(UTC)
    for _ in range(3):
        await eng.evaluate(now)
    async with app.state.ctx.session_factory() as s:
        assert (await s.execute(select(Alert))).scalars().all() == []  # new job: grace period
        job = await s.get(BackupJob, jid)
        job.created_at = now - timedelta(days=3)
        await s.commit()
    for _ in range(2):
        await eng.evaluate(now)
    async with app.state.ctx.session_factory() as s:
        (a,) = (await s.execute(select(Alert))).scalars().all()
        assert a.type == "backup_overdue" and a.key == f"backup:{jid}:state"
    await report(client, auth, jid)
    await eng.evaluate(now)
    async with app.state.ctx.session_factory() as s:
        assert (await s.execute(select(Alert).where(Alert.status == "open"))).scalars().all() == []


def test_compute_state_priority():
    now = datetime.now(UTC)
    j = BackupJob(
        name="x", max_age_hours=24, verification_max_age_days=90, enabled=True, created_at=now
    )
    assert compute_state(j, now)[0] == "never_run"
    j.last_attempt_at = j.last_success_at = now - timedelta(hours=1)
    j.last_attempt_status = "success"
    assert compute_state(j, now)[0] == "reported_success"
    j.last_restore_test_at = j.last_restore_test_success_at = now
    j.last_restore_test_ok = True
    assert compute_state(j, now)[0] == "restore_verified"
    j.last_success_at = j.last_attempt_at = now - timedelta(hours=48)
    assert compute_state(j, now)[0] == "overdue"  # staleness trumps an old verification
