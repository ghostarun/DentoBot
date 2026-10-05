import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import step6_frame_audit as fa  # noqa: E402

URDF = """<robot name="t">
<link name="base_link"/><link name="a"/><link name="b"/><link name="tcp"/>
<joint name="j1" type="revolute"><parent link="base_link"/><child link="a"/>
  <origin xyz="0 0 0.1" rpy="0 0 0"/><axis xyz="0 0 1"/></joint>
<joint name="j2" type="prismatic"><parent link="a"/><child link="b"/>
  <origin xyz="0.2 0 0" rpy="0 0 0"/><axis xyz="1 0 0"/></joint>
<joint name="f" type="fixed"><parent link="b"/><child link="tcp"/>
  <origin xyz="0 0 -0.05" rpy="0 0 0"/></joint></robot>"""


def test_independent_urdf_fk_matches_hand_computation():
    fk = fa.UrdfFk(URDF)
    pose = fk.link_pose_m("tcp", {"j1": math.pi / 2, "j2": 0.03})
    assert np.allclose(pose[:3, 3], [0.0, 0.23, 0.05])
    assert np.allclose(pose[:3, 0], [0, 1, 0])


def test_base_mapping_uses_mm_and_composes_base_first():
    base = np.eye(4)
    base[:3, 3] = [10, 20, 30]
    base[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    pose = np.eye(4)
    pose[:3, 3] = [0.001, 0, 0]  # 1 mm along base x
    ras = fa.to_ras_mm(base, pose)
    assert np.allclose(ras[:3, 3], [10, 21, 30])


def test_axis_angles_and_bounds_helpers():
    a = np.eye(4)
    b = np.eye(4)
    b[:3, :3] = [[math.cos(0.01), -math.sin(0.01), 0], [math.sin(0.01), math.cos(0.01), 0], [0, 0, 1]]
    angles = fa.axis_angles_deg(a, b)
    assert abs(angles[0] - math.degrees(0.01)) < 1e-9 and angles[2] < 1e-9
    assert fa.bounds_of([[0, 1, 2], [3, -1, 5]]) == [0, 3, -1, 1, 2, 5]
    assert fa.max_bounds_delta([0, 1], [0.02, 1]) == 0.02


def test_mesh_vertices_must_be_in_mm_for_the_ras_mapping():
    """2026-10-06 harness bug: metre vertices with mm translations collapse the mesh."""
    base = np.eye(4)
    pose = np.eye(4)
    ras = fa.to_ras_mm(base, pose)
    mesh_m = np.array([[0.0, 0, 0], [0.06, 0, 0]])
    mesh_mm = mesh_m * 1000.0
    pts = (ras @ np.c_[mesh_mm, np.ones(2)].T).T[:, :3]
    assert abs(np.ptp(pts[:, 0]) - 60.0) < 1e-9
