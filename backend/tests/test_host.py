import asyncio
import os

from app.monitoring import host as host_mod
from app.monitoring.host import HostCollector, parse_net_dev, probe_path
from app.schemas.metrics import TemperatureReading

NET = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0
  eth0: 5000 50 0 0 0 0 0 0 7000 70 0 0 0 0 0 0
 veth1: 99 1 0 0 0 0 0 0 99 1 0 0 0 0 0 0
"""


def test_parse_net_dev():
    d = parse_net_dev(NET)
    assert d["eth0"] == (5000, 7000) and d["lo"] == (1000, 1000)


def test_collect_returns_real_values_and_none_for_unavailable_rates():
    c = HostCollector()
    first = c.collect()
    assert first.memory and 0 <= first.memory.percent <= 100
    assert first.network is not None and first.network.rx_bps is None  # no previous sample yet
    second = c.collect()
    assert second.network.rx_bps is None or second.network.rx_bps >= 0


def _fake_sys(tmp_path, rx=5000, tx=7000, extra=()):
    base = tmp_path / "sys" / "class" / "net"
    for name, r, t in [("eth0", rx, tx), ("lo", 9, 9), ("docker0", 5, 5), *extra]:
        d = base / name / "statistics"
        d.mkdir(parents=True)
        (d / "rx_bytes").write_text(str(r))
        (d / "tx_bytes").write_text(str(t))
    return str(tmp_path / "sys")


def test_zero_is_distinct_from_unavailable(tmp_path):
    c = HostCollector(sys_path=_fake_sys(tmp_path))
    c.collect()
    m = c.collect()
    assert m.network.rx_bps == 0.0 and m.network.interfaces == ["eth0"]  # measured zero, not null


def test_host_sysfs_counters_drive_rates_and_skip_virtual_ifaces(tmp_path):
    sysdir = _fake_sys(tmp_path, rx=1000, tx=1000)
    c = HostCollector(sys_path=sysdir)
    c.collect()
    (tmp_path / "sys/class/net/eth0/statistics/rx_bytes").write_text("101000")
    c._prev.t -= 10  # pretend the previous sample was 10s ago
    m = c.collect()
    assert 9000 < m.network.rx_bps < 11000 and m.network.tx_bps == 0.0
    assert m.network.rx_total_bytes == 101000  # docker0/lo excluded


def test_containerised_without_host_counters_reports_unavailable_not_container_traffic(tmp_path):
    (tmp_path / "net").mkdir()
    (tmp_path / "net" / "dev").write_text(NET)  # the *container's* view must be ignored
    c = HostCollector()
    c.proc_path = str(tmp_path)  # set directly: the constructor would repoint psutil globally
    m = c.collect()
    assert m.network is None


def test_proc1_net_dev_used_when_readable(tmp_path):
    (tmp_path / "1" / "net").mkdir(parents=True)
    (tmp_path / "1" / "net" / "dev").write_text(NET)
    c = HostCollector()
    c.proc_path = str(tmp_path)
    m = c.collect()
    assert m.network.rx_total_bytes == 5000 and m.network.interfaces == ["eth0"]


def test_cpu_temperature_selection_prefers_cpu_sensors():
    r = [
        TemperatureReading(label="nvme:Composite", current_c=60),
        TemperatureReading(label="coretemp:Core 0", current_c=45),
        TemperatureReading(label="coretemp:Package id 0", current_c=51),
    ]
    assert HostCollector.pick_cpu_temperature(r) == 51
    assert HostCollector.pick_cpu_temperature([r[0]]) is None  # NVMe is not the CPU
    assert HostCollector.pick_cpu_temperature([]) is None


def test_missing_sensors_do_not_break_collection(monkeypatch):
    monkeypatch.delattr("psutil.sensors_temperatures", raising=False)
    m = HostCollector().collect()
    assert m.temperature_c is None and m.temperatures == [] or isinstance(m.temperatures, list)


def test_probe_missing_and_not_directory(tmp_path):
    assert probe_path(str(tmp_path / "nope"), "external", True, None, "/")["state"] == "missing"
    f = tmp_path / "file"
    f.write_text("x")
    assert probe_path(str(f), "external", True, None, "/")["state"] == "missing"


def test_probe_plain_directory_is_not_a_mount(tmp_path):
    res = probe_path(str(tmp_path), "external", True, None, "/")
    assert res["state"] == "unmounted" and "mount point" in res["message"]


def test_probe_same_device_as_root_flagged_even_if_mountpoint_not_required(tmp_path):
    res = probe_path(str(tmp_path), "external", False, None, str(tmp_path.parent))
    assert res["state"] == "unmounted" and "same filesystem" in res["message"]


def test_probe_marker_file(tmp_path):
    res = probe_path(str(tmp_path), "data", False, ".mounted", "/")
    assert res["state"] == "unmounted" and "Marker" in res["message"]
    (tmp_path / ".mounted").write_text("")
    ok = probe_path(str(tmp_path), "data", False, ".mounted", "/")
    assert ok["state"] == "ok" and ok["total_bytes"] > 0 and 0 <= ok["percent"] <= 100


def test_probe_root_ok():
    assert probe_path("/", "root", False, None, "/")["state"] == "ok"


def test_probe_never_writes(tmp_path):
    before = set(os.listdir(tmp_path))
    probe_path(str(tmp_path), "data", False, ".mounted", "/")
    assert set(os.listdir(tmp_path)) == before


async def test_hung_filesystem_reported_unresponsive_without_blocking(monkeypatch):
    import threading

    release = threading.Event()
    monkeypatch.setattr(host_mod, "probe_path", lambda *a: release.wait(5) and {"state": "ok"})
    monkeypatch.setattr(host_mod, "VOLUME_TIMEOUT_SECONDS", 0.2)
    c = HostCollector()
    kw = dict(
        volume_id=1,
        name="usb",
        path="/mnt/usb",
        kind="external",
        required=True,
        require_mountpoint=True,
        marker_file=None,
        root_path="/",
    )
    t0 = asyncio.get_running_loop().time()
    res = await c.check_volume(**kw)
    assert res.state == "unresponsive" and asyncio.get_running_loop().time() - t0 < 2
    # While the earlier probe is stuck, further checks don't spawn more threads.
    assert (await c.check_volume(**kw)).state == "unresponsive"
    release.set()
    await asyncio.sleep(0.2)
    assert "/mnt/usb" not in c._hung
