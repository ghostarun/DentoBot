"""Focused host-only checks for the opt-in X11 screen recorder."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_slicer_screen as recorder_module


class _Input:
    def __init__(self):
        self.data = bytearray()

    def write(self, value):
        self.data.extend(value)

    def flush(self):
        pass

    def close(self):
        pass


class _FinishedProcess:
    def __init__(self, command, _kwargs):
        self.command = command
        self.stdin = _Input()
        Path(command[-1]).write_bytes(b"finalized-video")
        self.returncode = None
        self.signals = []
        self.waits = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waits += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def send_signal(self, signum):
        self.signals.append(signum)

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def _stub_display(monkeypatch):
    monkeypatch.setattr(
        recorder_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout="screen #0:\n  dimensions: 1920x1080 pixels (508x285 millimeters)\n"
        ),
    )


def test_records_full_display_and_writes_exact_hash_manifest(tmp_path, monkeypatch):
    _stub_display(monkeypatch)
    processes = []

    def popen(command, **kwargs):
        process = _FinishedProcess(command, kwargs)
        processes.append((process, kwargs))
        return process

    monkeypatch.setattr(recorder_module.subprocess, "Popen", popen)
    output = tmp_path / "headed-run" / "screen.mkv"
    recorder = recorder_module.ScreenRecorder(":7", output, fps=24).start()
    result = recorder.stop()

    process, kwargs = processes[0]
    assert "-n" in process.command
    assert process.command[process.command.index("-f") + 1] == "x11grab"
    assert process.command[process.command.index("-video_size") + 1] == "1920x1080"
    assert process.command[process.command.index("-framerate") + 1] == "24"
    assert process.command[process.command.index("-i") + 1] == ":7+0,0"
    assert process.command[-1] == str(output.resolve())
    assert kwargs["stdin"] == subprocess.PIPE
    assert process.stdin.data == b"q\n"
    manifest_path = output.with_name("screen.manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result == manifest
    assert manifest["status"] == "complete"
    assert manifest["exit_status"] == 0
    assert manifest["ffmpeg_exit_status"] == 0
    assert manifest["display"] == ":7"
    assert (manifest["width"], manifest["height"], manifest["fps"]) == (1920, 1080, 24)
    assert manifest["started_at_utc"].endswith("Z")
    assert manifest["ended_at_utc"].endswith("Z")
    assert manifest["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_refuses_existing_output_or_manifest_before_starting_ffmpeg(tmp_path, monkeypatch):
    run_dir = tmp_path / "existing-run"
    run_dir.mkdir()
    output = run_dir / "screen.mp4"
    output.write_bytes(b"keep")
    called = []
    monkeypatch.setattr(recorder_module.subprocess, "Popen", lambda *args, **kwargs: called.append(args))
    recorder = recorder_module.ScreenRecorder(":7", output)

    with pytest.raises(FileExistsError, match="already exists"):
        recorder.start()
    assert called == []


def test_refuses_nonempty_output_directory_before_starting_ffmpeg(tmp_path, monkeypatch):
    run_dir = tmp_path / "existing-run"
    run_dir.mkdir()
    (run_dir / "keep.txt").write_text("keep", encoding="utf-8")
    called = []
    monkeypatch.setattr(recorder_module.subprocess, "Popen", lambda *args, **kwargs: called.append(args))
    recorder = recorder_module.ScreenRecorder(":7", run_dir / "screen.mp4")

    with pytest.raises(FileExistsError, match="fresh and empty"):
        recorder.start()
    assert called == []


def test_forced_shutdown_is_partial_and_still_reaps_ffmpeg(tmp_path, monkeypatch):
    _stub_display(monkeypatch)

    class StuckProcess(_FinishedProcess):
        def wait(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("ffmpeg", timeout)
            self.returncode = -2
            return self.returncode

    process_holder = []

    def popen(command, **kwargs):
        process = StuckProcess(command, kwargs)
        process_holder.append(process)
        return process

    monkeypatch.setattr(recorder_module.subprocess, "Popen", popen)
    recorder = recorder_module.ScreenRecorder(":7", tmp_path / "stuck-run" / "screen.mp4", stop_timeout=0.01)
    result = recorder.start().stop()

    process = process_holder[0]
    assert process.signals == [recorder_module.signal.SIGINT]
    assert process.returncode == -2
    assert process.poll() == -2
    assert result["status"] == "partial"
    assert result["exit_status"] == 1
    assert result["ffmpeg_exit_status"] == -2
    assert result["output_sha256"] == hashlib.sha256(b"finalized-video").hexdigest()


def test_cli_exception_stops_and_reaps_running_ffmpeg(tmp_path, monkeypatch):
    _stub_display(monkeypatch)
    processes = []

    def popen(command, **kwargs):
        process = _FinishedProcess(command, kwargs)
        processes.append(process)
        return process

    def fail_sleep(_seconds):
        raise RuntimeError("automation step failed")

    monkeypatch.setattr(recorder_module.subprocess, "Popen", popen)
    monkeypatch.setattr(recorder_module.time, "sleep", fail_sleep)
    output = tmp_path / "cli-failure" / "screen.mkv"

    exit_status = recorder_module.main(
        ["--display", ":7", "--output", str(output), "--duration", "1"]
    )

    process = processes[0]
    manifest = json.loads(output.with_name("screen.manifest.json").read_text(encoding="utf-8"))
    assert exit_status == 1
    assert process.stdin.data == b"q\n"
    assert process.waits == 1
    assert process.poll() == 0
    assert manifest["status"] == "partial"
    assert manifest["exit_status"] == 1
    assert manifest["ffmpeg_exit_status"] == 0
    assert manifest["failure_reason"] == "screen recording failed"


def test_start_failure_after_popen_stops_child_before_raising(tmp_path, monkeypatch):
    _stub_display(monkeypatch)
    processes = []

    def popen(command, **kwargs):
        process = _FinishedProcess(command, kwargs)
        processes.append(process)
        return process

    def fail_register(_callback):
        raise RuntimeError("registration failed")

    monkeypatch.setattr(recorder_module.subprocess, "Popen", popen)
    monkeypatch.setattr(recorder_module.atexit, "register", fail_register)
    output = tmp_path / "start-failure" / "screen.mp4"
    recorder = recorder_module.ScreenRecorder(":7", output)

    with pytest.raises(RuntimeError, match="could not start screen recording"):
        recorder.start()

    process = processes[0]
    manifest = json.loads(output.with_name("screen.manifest.json").read_text(encoding="utf-8"))
    assert process.stdin.data == b"q\n"
    assert process.waits == 1
    assert process.poll() == 0
    assert manifest["status"] == "partial"
    assert manifest["exit_status"] == 1
    assert manifest["ffmpeg_exit_status"] == 0


def test_command_mode_records_nonzero_status_without_storing_argv(tmp_path, monkeypatch):
    events = []
    processes = []

    def run(command, **kwargs):
        if command[0] == "xdpyinfo":
            events.append("display-probe")
            return SimpleNamespace(
                stdout="screen #0:\n  dimensions: 1920x1080 pixels (508x285 millimeters)\n"
            )
        events.append("command")
        assert processes[0].stdin.data == b""
        assert kwargs["check"] is False
        return SimpleNamespace(returncode=23)

    def popen(command, **kwargs):
        events.append("recorder-start")
        process = _FinishedProcess(command, kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(recorder_module.subprocess, "run", run)
    monkeypatch.setattr(recorder_module.subprocess, "Popen", popen)
    output = tmp_path / "command-run" / "screen.mkv"
    command = ["fake-slicer-runner", "/private/sensitive/case.dentocase"]

    exit_status = recorder_module.main(
        ["--display", ":7", "--output", str(output), "--command", "--", *command]
    )

    process = processes[0]
    manifest_text = output.with_name("screen.manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert events == ["display-probe", "recorder-start", "command"]
    assert exit_status == 23
    assert process.stdin.data == b"q\n"
    assert process.waits == 1
    assert process.poll() == 0
    assert manifest["status"] == "partial"
    assert manifest["exit_status"] == 23
    assert manifest["command_exit_status"] == 23
    assert manifest["ffmpeg_exit_status"] == 0
    assert command[0] not in manifest_text
    assert command[1] not in manifest_text
