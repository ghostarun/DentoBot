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
