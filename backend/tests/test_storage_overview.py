from datetime import UTC, datetime

API = "/api/v1"


async def test_storage_requires_auth(client):
    assert (await client.get(f"{API}/storage")).status_code == 401
    assert (await client.post(f"{API}/storage/volumes", json={})).status_code == 401


async def test_missing_required_mount_is_reported_not_assumed_empty(client, auth, mon, tmp_path):
    r = await client.post(
        f"{API}/storage/volumes",
        headers=auth,
        json={
            "name": "Media HDD",
            "path": str(tmp_path / "usb"),
            "kind": "external",
            "marker_file": ".homelab-mounted",
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "path_not_allowed"


async def test_volume_states_via_api(app, client, auth, mon, tmp_path):
    app.state.ctx.settings.storage_allowed_roots.append(str(tmp_path))
    ok_dir = tmp_path / "disk"
    ok_dir.mkdir()
    (ok_dir / ".homelab-mounted").write_text("")
    for name, path, extra in [
        ("gone", str(tmp_path / "missing"), {}),
        (
            "healthy",
            str(ok_dir),
            {"require_mountpoint": False, "kind": "data", "marker_file": ".homelab-mounted"},
        ),
        (
            "wrongdisk",
            str(tmp_path),
            {"require_mountpoint": False, "kind": "data", "marker_file": ".nope"},
        ),
    ]:
        r = await client.post(
            f"{API}/storage/volumes", headers=auth, json={"name": name, "path": path, **extra}
        )
        assert r.status_code == 201, r.text
    st = (await client.get(f"{API}/storage", headers=auth)).json()
    by = {v["name"]: v for v in st["volumes"]}
    assert by["gone"]["state"] == "missing" and by["gone"]["percent"] is None
    assert by["healthy"]["state"] == "ok" and by["healthy"]["total_bytes"] > 0
    assert by["wrongdisk"]["state"] == "unmounted"
    assert st["root"]["kind"] == "root" and st["root"]["state"] == "ok"
    # nothing was created on disk
    assert not (tmp_path / "missing").exists()
    vols = (await client.get(f"{API}/storage/volumes", headers=auth)).json()
    r = await client.delete(f"{API}/storage/volumes/{vols[0]['id']}", headers=auth)
    assert r.status_code == 200 and "nothing on disk" in r.json()["message"]


async def test_volume_input_validation(client, auth):
    for body in [
        {"name": "x", "path": "relative/path"},
        {"name": "x", "path": "/mnt/../etc"},
        {"name": "x", "path": "/mnt/a", "marker_file": "../../etc/passwd"},
        {"name": "x", "path": "/etc", "kind": "root"},
        {"name": "x", "path": "/etc"},
    ]:
        r = await client.post(f"{API}/storage/volumes", headers=auth, json=body)
        assert r.status_code == 422, body


async def test_overview_composes_real_state(client, auth, mon, fake_docker):
    await mon.sample_host()
    await mon.refresh_docker()
    await client.post(
        f"{API}/services", headers=auth, json={"name": "Plex", "container_name": "plex"}
    )
    await client.post(
        f"{API}/services", headers=auth, json={"name": "Ghost", "container_name": "ghost"}
    )
    await client.post(
        f"{API}/services",
        headers=auth,
        json={"name": "Off", "container_name": "x", "enabled": False},
    )
    ov = (await client.get(f"{API}/overview", headers=auth)).json()
    assert ov["status"] == "healthy" and ov["stale"] is False
    assert ov["host"]["memory"]["percent"] >= 0 and ov["root_volume"]["state"] == "ok"
    assert ov["containers"] == {
        "available": True,
        "running": 4,
        "stopped": 1,
        "unhealthy": 0,
        "total": 5,
        "error": None,
    }
    assert (
        ov["services"]["healthy"] == 1
        and ov["services"]["unhealthy"] == 1
        and ov["services"]["disabled"] == 1
    )
    assert ov["refresh_seconds"] == 10 and ov["last_update"]
    datetime.fromisoformat(ov["generated_at"].replace("Z", "+00:00")).astimezone(UTC)


async def test_overview_without_any_data_is_unknown_not_fabricated(client, auth):
    ov = (await client.get(f"{API}/overview", headers=auth)).json()
    assert ov["status"] == "unknown" and ov["host"] is None and ov["last_update"] is None
    assert ov["containers"]["available"] is False


async def test_overview_requires_auth(client):
    assert (await client.get(f"{API}/overview")).status_code == 401
