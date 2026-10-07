from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


TESTING_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTING_DIR.parent
for _path in (TESTING_DIR, REPO_ROOT / "DENTOWorkflow" / "Resources" / "Python"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import step6_frame_audit as fa  # noqa: E402


TOY_URDF = """<robot name="frame-sync-test">
<link name="base_link"/><link name="a"/><link name="b"/><link name="tcp"/>
<joint name="j1" type="revolute"><parent link="base_link"/><child link="a"/>
  <origin xyz="0 0 0.1" rpy="0 0 0"/><axis xyz="0 0 1"/></joint>
<joint name="j2" type="prismatic"><parent link="a"/><child link="b"/>
  <origin xyz="0.2 0 0" rpy="0 0 0"/><axis xyz="1 0 0"/></joint>
<joint name="fixed_tcp" type="fixed"><parent link="b"/><child link="tcp"/>
  <origin xyz="0 0 -0.05" rpy="0 0 0"/></joint>
</robot>"""

JOINTS = {"j1": math.pi / 2.0, "j2": 0.03}
EXPECTED_WORLD = np.asarray(
    [[0.0, -1.0, 0.0, 10.0],
     [1.0,  0.0, 0.0, 250.0],
     [0.0,  0.0, 1.0, 80.0],
     [0.0,  0.0, 0.0, 1.0]],
)


class _VtkBase:
    def __init__(self, vtk, matrix):
        self.vtk = vtk
        self.matrix = np.asarray(matrix, dtype=float)

    def GetMatrixTransformToWorld(self, target):
        for row in range(4):
            for col in range(4):
                target.SetElement(row, col, float(self.matrix[row, col]))


class _Bridge:
    ROS2_TOOL_TCP_LINK = "tcp"

    def __init__(self, kdl_result, moveit_result):
        self.kdl_result = kdl_result
        self.moveit_result = moveit_result
        self.kdl_calls = []
        self.moveit_calls = []

    def compute_tcp_pose_world_ras_mm(self, joints, *, base_transform):
        self.kdl_calls.append((dict(joints), base_transform))
        return self.kdl_result

    def compute_moveit_tcp_pose_world_ras_mm(self, joints, *, base_transform):
        self.moveit_calls.append((dict(joints), base_transform))
        return self.moveit_result


def _namespace(tmp_path, vtk, *, kdl=None, moveit=None):
    urdf_path = tmp_path / "toy.urdf"
    urdf_path.write_text(TOY_URDF, encoding="utf-8")
    base_matrix = np.eye(4)
    base_matrix[:3, 3] = [10.0, 20.0, 30.0]
    base = _VtkBase(vtk, base_matrix)
    parameter_node = SimpleNamespace(robotBaseTransform=base)

    class Logic:
        def robotDescriptionPaths(self):
            return str(urdf_path), str(tmp_path)

    bridge = _Bridge(
        (True, "KDL ok", EXPECTED_WORLD.copy()) if kdl is None else kdl,
        (True, "MoveIt ok", EXPECTED_WORLD.copy()) if moveit is None else moveit,
    )
    return {"logic": Logic(), "parameter_node": parameter_node, "bridge": bridge}, bridge, base


def _yaw_offset(pose, delta_degrees):
    out = np.asarray(pose, dtype=float).copy()
    yaw = math.pi / 2.0 + math.radians(delta_degrees)
    out[:3, :3] = [
        [math.cos(yaw), -math.sin(yaw), 0.0],
        [math.sin(yaw), math.cos(yaw), 0.0],
        [0.0, 0.0, 1.0],
    ]
    return out


def _pose_result(matrix, message="ok"):
    return True, message, np.asarray(matrix, dtype=float)


def test_kinematics_rows_match_independent_urdf_kdl_and_moveit_answer(tmp_path):
    vtk = pytest.importorskip("vtk")
    namespace, bridge, base = _namespace(tmp_path, vtk)
    states = {name: dict(JOINTS) for name in ("preentry", "entry", "drilling_end")}

    rows = fa.kinematics_rows(namespace, states)

    assert [row["state"] for row in rows] == list(states)
    assert all(row["status"] == "PASS" and not row["issues"] for row in rows)
    for source in ("urdf", "kdl", "moveit"):
        assert np.allclose(rows[0]["posesWorldRasMm"][source], EXPECTED_WORLD, atol=1e-10)
    assert rows[0]["urdf_vs_kdl_mm"] == pytest.approx(0.0)
    assert rows[0]["urdf_vs_kdl_axis_deg"] == pytest.approx(0.0)
    assert rows[0]["urdf_vs_moveit_mm"] == pytest.approx(0.0)
    assert rows[0]["urdf_vs_moveit_axis_deg"] == pytest.approx(0.0)
    assert rows[0]["kdl_vs_moveit_mm"] == pytest.approx(0.0)
    assert rows[0]["kdl_vs_moveit_axis_deg"] == pytest.approx(0.0)
    assert bridge.kdl_calls[0] == (JOINTS, base)
    assert bridge.moveit_calls[0] == (JOINTS, base)
    assert fa.kinematics_rows(namespace, {}) == []


def test_known_small_kdl_and_moveit_axis_residuals_are_reported_and_pass(tmp_path):
    vtk = pytest.importorskip("vtk")
    namespace, _, _ = _namespace(
        tmp_path,
        vtk,
        kdl=_pose_result(_yaw_offset(EXPECTED_WORLD, 0.0022), "KDL residual"),
        moveit=_pose_result(_yaw_offset(EXPECTED_WORLD, 0.0027), "MoveIt residual"),
    )

    row = fa.kinematics_rows(namespace, {"preentry": JOINTS})[0]

    assert row["status"] == "PASS"
    assert row["urdf_vs_kdl_axis_deg"] == pytest.approx(0.0022, abs=0.0001)
    assert row["urdf_vs_moveit_axis_deg"] == pytest.approx(0.0027, abs=0.0001)
    assert row["kdl_vs_moveit_axis_deg"] == pytest.approx(0.0005, abs=0.0001)


def test_pose_error_above_position_and_axis_tolerances_fails(tmp_path):
    vtk = pytest.importorskip("vtk")
    bad_kdl = _yaw_offset(EXPECTED_WORLD, 0.02)
    bad_kdl[0, 3] += 0.02
    namespace, _, _ = _namespace(tmp_path, vtk, kdl=_pose_result(bad_kdl, "outside tolerance"))

    row = fa.kinematics_rows(namespace, {"entry": JOINTS})[0]

    assert row["status"] == "FAIL"
    assert row["urdf_vs_kdl_mm"] == pytest.approx(0.02)
    assert row["urdf_vs_kdl_axis_deg"] == pytest.approx(0.02, abs=0.0001)
    assert row["issues"]


@pytest.mark.parametrize(
    "kdl,moveit,issue",
    [
        ((False, "KDL unavailable", None), None, "KDL"),
        (None, (True, "bad shape", np.eye(3)), "MoveIt"),
        (_pose_result(np.full((4, 4), np.nan), "nonfinite"), None, "KDL"),
    ],
)
def test_unavailable_incomplete_or_nonfinite_fk_response_fails(tmp_path, kdl, moveit, issue):
    vtk = pytest.importorskip("vtk")
    namespace, _, _ = _namespace(tmp_path, vtk, kdl=kdl, moveit=moveit)

    row = fa.kinematics_rows(namespace, {"drilling_end": JOINTS})[0]

    assert row["status"] == "FAIL"
    assert row["issues"]
    assert any(issue.lower() in str(item).lower() for item in row["issues"])
