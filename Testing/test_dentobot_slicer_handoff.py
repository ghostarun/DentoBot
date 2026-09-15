"""Local-stub tests for the simulation-to-diagnostic handoff wrapper."""

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "Workspace/scripts/dentobot-simulation-slicer-handoff.bash"


STUB_ROS2 = r'''#!/usr/bin/env bash
set -euo pipefail

stub_log=${DENTOBOT_STUB_LOG:?}
case "${1:-}:${2:-}:${3:-}" in
  launch:dentobot_moveit_config:simulation.launch.py)
    printf '%s\n' stack_started >>"${stub_log}"
    stop_requested=false
    stop_stack() {
      printf 'stack_signal_%s\n' "${1}" >>"${stub_log}"
      stop_requested=true
    }
    trap - INT TERM
    trap 'stop_stack INT' INT
    trap 'stop_stack TERM' TERM
    while [[ ${stop_requested} == false ]]; do
      sleep 0.05 &
      child_pid=$!
      wait "${child_pid}" || true
    done
    exit 0
    ;;
  topic:echo:*)
    readiness_rc=${DENTOBOT_STUB_READINESS_RC:-0}
    if [[ ${readiness_rc} != 0 ]]; then
      exit "${readiness_rc}"
    fi
    if [[ ${DENTOBOT_STUB_READY:-true} == true ]]; then
      printf '%s\n---\n' '{"ready":true}'
    else
      printf '%s\n---\n' '{"ready":false}'
    fi
    ;;
  launch:slicer_ros2_module:slicer.launch.py)
    printf '%s\n' slicer_requested >>"${stub_log}"
    exit "${DENTOBOT_STUB_DIAGNOSTIC_RC:-0}"
    ;;
  *)
    printf 'unexpected ros2 stub argv: %s\n' "$*" >&2
    exit 91
    ;;
esac
'''


def _install_stub_ros2(tmp_path: Path) -> Path:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    ros2 = stub_dir / "ros2"
    ros2.write_text(STUB_ROS2, encoding="utf-8")
    ros2.chmod(ros2.stat().st_mode | stat.S_IXUSR)
    return stub_dir


def _run_handoff(tmp_path: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    stub_dir = _install_stub_ros2(tmp_path)
    stub_log = tmp_path / "stub.log"
    stack_log = tmp_path / "stack.log"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{stub_dir}:/usr/bin:/bin",
            "DENTOBOT_STUB_LOG": str(stub_log),
            "DENTOBOT_STUB_READY": "true",
            "DENTOBOT_STUB_READINESS_RC": "0",
            "DENTOBOT_STUB_DIAGNOSTIC_RC": "0",
        }
    )
    environment.update(extra_env)
    return subprocess.run(
        [
            "bash",
            str(HANDOFF),
            "--stack-log",
            str(stack_log),
            "--readiness-attempts",
            "1",
            "--readiness-interval",
            "0.01",
            "--",
            "ros2",
            "launch",
            "slicer_ros2_module",
            "slicer.launch.py",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def _stdout_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.splitlines() if line]


def test_ready_status_reaches_slicer_and_cleans_own_stack(tmp_path):
    result = _run_handoff(tmp_path)

    assert result.returncode == 0, result.stderr
    lines = _stdout_lines(result)
    stages = [line.split()[1].split("=", 1)[1] for line in lines]
    assert stages[:7] == [
        "stack_start",
        "stack_started",
        "readiness_observation",
        "readiness_accepted",
        "slicer_launch_request",
        "diagnostic_entry",
        "diagnostic_exit",
    ]
    assert stages[-1] == "cleanup_complete"
    assert stages[7] == "cleanup_begin"
    assert stages[8:-1]
    assert all(stage == "cleanup_signal" for stage in stages[8:-1])
    assert any("readiness_observation" in line and "rc=0" in line for line in lines)
    assert any("readiness_observation" in line and "ready=true" in line for line in lines)
    assert any("cleanup_complete" in line and "reason=diagnostic_exit" in line and "initiating_status=0" in line for line in lines)
    assert (tmp_path / "stub.log").read_text(encoding="utf-8").splitlines() == [
        "stack_started",
        "slicer_requested",
    ]
    stack_pid = int(next(line for line in lines if "stage=stack_started" in line).split("pid=", 1)[1])
    try:
        os.killpg(stack_pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError(f"handoff left stub process group {stack_pid} alive")


def test_readiness_command_failure_is_observed_and_blocks_slicer(tmp_path):
    result = _run_handoff(
        tmp_path,
        DENTOBOT_STUB_READINESS_RC="7",
    )

    assert result.returncode == 2, result.stderr
    lines = _stdout_lines(result)
    assert any(
        "readiness_observation" in line
        and "rc=7" in line
        and "ready=false" in line
        for line in lines
    )
    assert any("readiness_failed" in line and "attempts=1" in line for line in lines)
    assert any(
        "cleanup_complete" in line
        and "reason=readiness_failed" in line
        and "initiating_status=2" in line
        for line in lines
    )
    assert "slicer_requested" not in (tmp_path / "stub.log").read_text(encoding="utf-8")


def test_diagnostic_failure_status_survives_stack_cleanup(tmp_path):
    result = _run_handoff(
        tmp_path,
        DENTOBOT_STUB_DIAGNOSTIC_RC="23",
    )

    assert result.returncode == 23, result.stderr
    lines = _stdout_lines(result)
    assert any("diagnostic_exit" in line and "status=23" in line for line in lines)
    assert any(
        "cleanup_complete" in line
        and "reason=diagnostic_exit" in line
        and "initiating_status=23" in line
        for line in lines
    )
    assert "slicer_requested" in (tmp_path / "stub.log").read_text(encoding="utf-8")
