"""Container checks: ros2 CLI must work under Slicer's PYTHONHOME.

Host pytest skips this file when Jazzy is not installed. Run it inside
``dentobot-slicerros2`` to verify Start Stack's node-list probe.
"""

from pathlib import Path
import os
import subprocess
import sys

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTOROS2Bridge import ros2_cli_available, ros2_node_list, run_ros2_cli

JAZZY_SETUP = "/opt/ros/jazzy/setup.bash"
WORKSPACE_SETUP = "/workspace/ros2_ws/install/setup.bash"
SLICER_PYTHONHOME = "/opt/slicer/Slicer-SuperBuild/python-install"

pytestmark = pytest.mark.skipif(
    not os.path.isfile(JAZZY_SETUP) or not os.path.isfile(WORKSPACE_SETUP),
    reason="requires dentobot-slicerros2 Jazzy overlay",
)


def test_direct_ros2_help_fails_with_slicer_pythonhome() -> None:
    """Document why Connect reported 'ros2 CLI is not available'."""
    env = os.environ.copy()
    env["PYTHONHOME"] = SLICER_PYTHONHOME
    env["PYTHONPATH"] = (
        "/opt/slicer/Slicer-SuperBuild/Slicer-build/bin/Python:"
        + env.get("PYTHONPATH", "")
    )
    completed = subprocess.run(
        ["/opt/ros/jazzy/bin/ros2", "--help"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
        env=env,
    )
    assert completed.returncode != 0
    combined = (completed.stderr or "") + (completed.stdout or "")
    assert "librcl_action.so" in combined or "rclpy" in combined


def test_run_ros2_cli_succeeds_with_slicer_pythonhome(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONHOME", SLICER_PYTHONHOME)
    monkeypatch.setenv(
        "PYTHONPATH",
        "/opt/slicer/Slicer-SuperBuild/Slicer-build/bin/Python",
    )
    completed = run_ros2_cli(("--help",), timeout=8)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "usage: ros2" in (completed.stdout or "")
    assert ros2_cli_available() is True


def test_ros2_node_list_succeeds_with_slicer_pythonhome(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONHOME", SLICER_PYTHONHOME)
    monkeypatch.setenv(
        "PYTHONPATH",
        "/opt/slicer/Slicer-SuperBuild/Slicer-build/bin/Python",
    )
    ok, nodes, message = ros2_node_list()
    assert ok, message
    assert isinstance(nodes, list)
