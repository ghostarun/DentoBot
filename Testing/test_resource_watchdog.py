"""Pure counter and metadata checks for the external resource watchdog."""

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "Workspace/scripts/dentobot-resource-watchdog.py"
SPEC = importlib.util.spec_from_file_location("dentobot_resource_watchdog", SCRIPT)
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)


def _diskstats(sda_read, sda_write, sda_io, sda_weighted, sdb=False):
    rows = [
        f"8 0 sda 10 0 {sda_read} 0 20 0 {sda_write} 0 0 {sda_io} {sda_weighted}"
    ]
    if sdb:
        rows.append("8 16 sdb 1 0 10 0 2 0 20 0 0 40 80")
    return "\n".join(rows) + "\n"


def test_counter_deltas_use_pages_sectors_and_milliseconds(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    cgroup = tmp_path / "cgroup"
    proc.mkdir()
    cgroup.mkdir()
    monkeypatch.setattr(watchdog, "PROC", proc)
    monkeypatch.setattr(watchdog, "CGROUP", cgroup)

    (proc / "vmstat").write_text("pswpin 100\npswpout 50\npgmajfault 7\n")
    (proc / "diskstats").write_text(_diskstats(100, 200, 500, 1000, sdb=True))
    (cgroup / "io.stat").write_text("8:0 rbytes=100 wbytes=200 rios=3 wios=4\n")
    first, state = watchdog.resource_counters({}, 2.0)

    assert first["host_paging"]["page_size_bytes"] == watchdog.PAGE_SIZE
    assert first["host_paging"]["swap_in_pages_delta"] is None
    assert first["host_disk_io"]["devices"]["sda"]["read_bytes_per_second"] is None
    assert first["cgroup_io_stat"] == {"8:0": {"rbytes": 100, "wbytes": 200, "rios": 3, "wios": 4}}

    (proc / "vmstat").write_text("pswpin 104\npswpout 54\npgmajfault 13\n")
    (proc / "diskstats").write_text(_diskstats(110, 240, 510, 1016, sdb=True))
    second, _ = watchdog.resource_counters(state, 2.0)
    paging = second["host_paging"]
    disk = second["host_disk_io"]["devices"]["sda"]

    assert paging["swap_in_pages_delta"] == 4
    assert paging["swap_in_bytes_per_second"] == watchdog.PAGE_SIZE * 2
    assert paging["swap_out_pages_delta"] == 4
    assert paging["major_faults_delta"] == 6
    assert paging["major_faults_per_second"] == 3
    assert second["host_disk_io"]["sector_size_bytes"] == 512
    assert disk["read_bytes_per_second"] == 2560
    assert disk["write_bytes_per_second"] == 10240
    assert disk["io_time_ms_delta"] == 10
    assert disk["io_time_ms_per_second"] == 5
    assert disk["weighted_io_time_ms_delta"] == 16
    assert disk["weighted_io_time_ms_per_second"] == 8


def test_missing_reset_and_device_changes_never_create_negative_rates(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    proc.mkdir()
    monkeypatch.setattr(watchdog, "PROC", proc)
    monkeypatch.setattr(watchdog, "CGROUP", tmp_path / "missing-cgroup")
    (proc / "vmstat").write_text("pswpin 10\npswpout 20\npgmajfault 30\n")
    (proc / "diskstats").write_text(_diskstats(100, 200, 500, 1000, sdb=True))
    _, state = watchdog.resource_counters({}, 5.0)

    (proc / "vmstat").write_text("pswpin 9\npswpout 22\n")
    (proc / "diskstats").write_text(
        _diskstats(90, 210, 490, 980) + "8 32 sdc 1 0 5 0 1 0 8 0 0 20 40\n"
    )
    sample, _ = watchdog.resource_counters(state, 5.0)

    assert sample["host_paging"]["swap_in_pages_delta"] is None
    assert sample["host_paging"]["swap_out_pages_delta"] == 2
    assert sample["host_paging"]["major_faults_delta"] is None
    devices = sample["host_disk_io"]["devices"]
    assert "sdb" not in devices
    assert devices["sda"]["read_bytes_per_second"] is None
    assert devices["sda"]["write_bytes_per_second"] == 1024
    assert devices["sdc"]["read_bytes_per_second"] is None
    assert sample["cgroup_io_stat"] is None

    (proc / "vmstat").unlink()
    missing, _ = watchdog.resource_counters({}, 5.0)
    assert missing["host_paging"]["swap_out_bytes_per_second"] is None


def test_metadata_is_whitelisted_and_rejects_raw_paths():
    session_id = "85cd9d5a-8237-4766-93c2-9c1c96ea20bb"
    incoming = json.dumps({
        "session_id": session_id,
        "environment": "native-ubuntu",
        "source_checkout": "/home/tarun/private-checkout",
        "source_revision": "abc123abc123",
        "source_dirty": True,
        "source_dirty_fingerprint": "/secret/path",
        "slicer_version": "5.10",
        "image_id": "/var/lib/private-image",
        "native_module_identity": "/private/native/module",
        "patient_name": "must not escape",
    })
    sid, metadata = watchdog.sanitized_metadata(incoming, source_checkout="step6-integration")

    assert sid == session_id
    assert set(metadata) == set(watchdog.METADATA_KEYS)
    assert metadata["source_checkout"] == "step6-integration"
    assert metadata["environment"] == "native-ubuntu"
    assert all(watchdog.safe_checkout(value) is None for value in (".", "..", r"private\path"))
    assert metadata["source_revision"] == "abc123abc123"
    assert metadata["source_dirty"] is True
    assert metadata["source_dirty_fingerprint"] is None
    assert metadata["slicer_version"] == "5.10"
    assert metadata["image_id"] is None
    assert metadata["native_module_identity"] is None
    assert "patient_name" not in metadata


def test_environment_does_not_label_wsl_as_native_ubuntu(monkeypatch):
    monkeypatch.setenv("WSL_INTEROP", "1")
    assert watchdog.environment_label() is None


def test_handoff_uses_its_sibling_collector():
    handoff = SCRIPT.with_name("dentobot-simulation-slicer-handoff.bash").read_text()
    assert 'resource_watchdog_script="${script_directory}/dentobot-resource-watchdog.py"' in handoff
    assert 'python3 "${resource_watchdog_script}"' in handoff
    assert "python3 /workspace/ros2_ws/src/DentoBot/" not in handoff


PRESSURE_OK = "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"


def _pressure(some=0.0, full=0.0):
    return f"some avg10={some:.2f} avg60=0.00 avg300=0.00 total=0\nfull avg10={full:.2f} avg60=0.00 avg300=0.00 total=0\n"


def _host(mem_gib=6.0, swap_total_gib=10.0, swap_free_gib=8.0, cpu="", memory="", io="", load=(0.5, 0.5, 0.5), cpus=4):
    gib = 1024 * 1024
    return watchdog.host_alerts(
        int(mem_gib * gib), int(swap_total_gib * gib), int(swap_free_gib * gib),
        {"cpu": cpu or PRESSURE_OK, "memory": memory or PRESSURE_OK, "io": io or PRESSURE_OK},
        load, cpus,
    )


def test_host_alerts_are_quiet_on_a_healthy_host():
    assert _host() == []


def test_host_alerts_fire_on_the_conditions_seen_with_slicer_stalls():
    assert "host_mem_available_below_2_gib" in _host(mem_gib=1.5)
    assert "host_swap_used_above_75_percent" in _host(swap_free_gib=2.0)
    assert "host_memory_pressure_full_above_5_percent" in _host(memory=_pressure(full=5.0))
    assert "host_io_pressure_full_above_20_percent" in _host(io=_pressure(full=21.0))
    assert "host_cpu_pressure_some_above_80_percent" in _host(cpu=_pressure(some=85.0))
    assert "host_load_above_2x_cpu_count" in _host(load=(8.0, 2.0, 1.0), cpus=4)
    assert "host_io_pressure_full_above_20_percent" not in _host(io=_pressure(some=90.0, full=1.0))


def test_host_alerts_tolerate_missing_counters():
    assert watchdog.host_alerts(None, None, None, {}, (), 1) == []
    assert watchdog.host_alerts(8 * 1024 * 1024, 0, 0, {"memory": "garbage"}, (0.1, 0.1, 0.1), 2) == []


def test_counter_alerts_cover_swapping_zombies_and_a_starved_sampler():
    quiet = {"host_paging": {"swap_in_bytes_per_second": 0, "swap_out_bytes_per_second": None}}
    assert watchdog.counter_alerts({"zombie_count": 0, "sample_gap_seconds": 5.0}, quiet, 5) == []
    busy = {"host_paging": {"swap_in_bytes_per_second": 15 * 2**20, "swap_out_bytes_per_second": 6 * 2**20}}
    alerts = watchdog.counter_alerts({"zombie_count": 2, "sample_gap_seconds": 11.0}, busy, 5)
    assert alerts == [
        "host_swapping_above_20_mib_per_second",
        "zombie_processes_present",
        "sample_gap_over_twice_interval",
    ]


def test_slicer_rss_alerts_use_a_two_minute_growth_window():
    history = watchdog.deque()
    sample = lambda rss: {"slicer": {"rss_mib": rss}}
    assert watchdog.rss_growth_alert(history, 0, sample(2000)) == []
    assert watchdog.rss_growth_alert(history, 60, sample(2900)) == []
    assert watchdog.rss_growth_alert(history, 100, sample(3100)) == ["slicer_rss_growth_over_1_gib_in_2_min"]
    assert watchdog.rss_growth_alert(history, 400, sample(3200)) == []  # old samples left the window
    assert watchdog.rss_growth_alert(history, 460, sample(5200)) == [
        "slicer_rss_above_5_gib", "slicer_rss_growth_over_1_gib_in_2_min",
    ]
    assert watchdog.rss_growth_alert(history, 520, {"slicer": None}) == [] and not history


def test_run_id_comes_from_the_run_directory_not_shared_log_directories(tmp_path, monkeypatch):
    monkeypatch.delenv("DENTOBOT_RUN_ID", raising=False)
    assert watchdog.derive_run_id(tmp_path / "s6-live-01-r16" / "resources.jsonl") == "s6-live-01-r16"
    assert watchdog.derive_run_id(tmp_path / "ui-watchdog" / "resources-1.jsonl") is None
    assert watchdog.derive_run_id(tmp_path / "x" / "r.jsonl", explicit="chosen.1") == "chosen.1"
    monkeypatch.setenv("DENTOBOT_RUN_ID", "from-env")
    assert watchdog.derive_run_id(tmp_path / "x" / "r.jsonl") == "from-env"
    assert watchdog.derive_run_id(tmp_path / "x" / "r.jsonl", explicit="bad/id") == "from-env"


def test_directly_started_sampler_is_never_anonymous(tmp_path):
    """Run harnesses start the sampler bare; MONITOR_START must still identify the session and run."""
    import os
    import subprocess

    output = tmp_path / "s6-live-01-r99" / "resources.jsonl"
    environment = {
        key: value for key, value in os.environ.items()
        if key not in {"DENTOBOT_WATCHDOG_METADATA", "DENTOBOT_WATCHDOG_SESSION_ID", "DENTOBOT_RUN_ID"}
    }
    parent = subprocess.Popen(["sleep", "3"])
    try:
        subprocess.run(
            ["python3", str(SCRIPT), "--parent-pid", str(parent.pid), "--output-path", str(output),
             "--interval", "1"],
            env=environment, timeout=20, check=True, capture_output=True,
        )
    finally:
        parent.kill()
        parent.wait()
    records = [json.loads(line) for line in output.read_text().splitlines()]
    start = records[0]
    assert start["event"] == "MONITOR_START"
    assert start["run_id"] == "s6-live-01-r99"
    assert start["metadata_source"] == "sampler_derived"
    assert len(start["session_id"]) == 36 and start["metadata"]["session_id"] == start["session_id"]
    assert start["metadata"]["source_checkout"] == SCRIPT.parents[2].name
    sample = next(item for item in records if item["event"] == "RESOURCE_SAMPLE")
    assert {"slicer", "host_mem_total_kib", "host_swap_total_kib"} <= set(sample)
    assert all("vm_swap_mib" in item and "major_faults" in item for item in sample["top_processes"])


def test_launcher_metadata_is_preserved_and_labelled(tmp_path):
    import os
    import subprocess

    session_id = "85cd9d5a-8237-4766-93c2-9c1c96ea20bb"
    output = tmp_path / "run-a" / "resources.jsonl"
    environment = {**os.environ, "DENTOBOT_WATCHDOG_SESSION_ID": session_id,
                   "DENTOBOT_WATCHDOG_METADATA": json.dumps({"session_id": session_id, "slicer_version": "5.10"})}
    parent = subprocess.Popen(["sleep", "2"])
    try:
        subprocess.run(
            ["python3", str(SCRIPT), "--parent-pid", str(parent.pid), "--output-path", str(output),
             "--interval", "1", "--run-id", "explicit-1"],
            env=environment, timeout=20, check=True, capture_output=True,
        )
    finally:
        parent.kill()
        parent.wait()
    start = json.loads(output.read_text().splitlines()[0])
    assert start["session_id"] == session_id
    assert start["metadata_source"] == "launcher"
    assert start["run_id"] == "explicit-1"
    assert start["metadata"]["slicer_version"] == "5.10"


def test_zombie_parent_counts_as_exited(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    (proc / "10").mkdir(parents=True)
    (proc / "11").mkdir()
    (proc / "10" / "stat").write_text("10 (bash) S 1 10 10 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 1 0 0\n")
    (proc / "11" / "stat").write_text("11 (my) cmd) Z 1 11 11 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 1 0 0\n")
    monkeypatch.setattr(watchdog, "PROC", proc)
    assert watchdog.parent_alive(10)
    assert not watchdog.parent_alive(11)
    assert not watchdog.parent_alive(12)
