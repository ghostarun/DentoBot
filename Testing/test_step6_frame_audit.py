import math
import sys
from pathlib import Path

import numpy as np
import pytest

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


def test_axis_angles_ignore_column_norm_drift():
    """6 Oct: a Base matrix with ~4e-10 column-norm drift read as 0.0022 deg before normalising."""
    a = np.eye(4)
    b = np.eye(4)
    b[:3, :3] *= (1.0 - 4e-10)
    assert max(fa.axis_angles_deg(a, b)) < 1e-6


# ---- exact mesh separation (S6-AUDIT-D-01, 2026-10-06) ------------------------
def _triangle(z, size=10.0, shift=(0.0, 0.0)):
    v = np.array([[0, 0, z], [size, 0, z], [0, size, z]], float)
    v[:, 0] += shift[0]
    v[:, 1] += shift[1]
    return v, np.array([[0, 1, 2]])


def test_exact_separation_of_parallel_triangles_is_the_gap():
    va, fa_ = _triangle(0.0)
    vb, fb = _triangle(2.0, shift=(1.0, 1.0))
    out = fa.exact_mesh_separation(va, fa_, vb, fb)
    assert math.isclose(out["distance_mm"], 2.0, abs_tol=1e-9) and not out["intersecting"]


def test_exact_separation_finds_edge_edge_contact_that_vertex_sampling_misses():
    # Two long thin triangles crossing like an X, 0.3 mm apart at the middle of both edges.
    va = np.array([[-10, 0, 0], [10, 0, 0], [0, -0.01, -5]], float)
    vb = np.array([[0, -10, 0.3], [0, 10, 0.3], [0.01, 0, 5]], float)
    faces = np.array([[0, 1, 2]])
    out = fa.exact_mesh_separation(va, faces, vb, faces)
    assert math.isclose(out["distance_mm"], 0.3, abs_tol=1e-6)
    sampled = min(np.linalg.norm(p - q) for p in va for q in vb)
    assert sampled > 5.0  # vertex-to-vertex sampling sees > 5 mm where the true gap is 0.3 mm


def test_exact_separation_reports_intersection_and_out_of_range():
    va, fa_ = _triangle(0.0)
    vb = np.array([[2, 2, -1], [2, 2, 1], [3, 3, 1]], float)
    out = fa.exact_mesh_separation(va, fa_, vb, np.array([[0, 1, 2]]))
    assert out["intersecting"] and out["distance_mm"] == 0.0
    far_v, far_f = _triangle(10.0)
    far = fa.exact_mesh_separation(va, fa_, far_v, far_f, search_mm=3.0)
    assert far["distance_mm"] is None and far["search_mm"] == 3.0


def test_stl_mesh_reader_returns_triangles(tmp_path):
    import struct

    data = bytearray(80) + struct.pack("<I", 2)
    for tri in (((0, 0, 0), (1, 0, 0), (0, 1, 0)), ((1, 0, 0), (1, 1, 0), (0, 1, 0))):
        data += struct.pack("<3f", 0, 0, 1) + b"".join(struct.pack("<3f", *v) for v in tri) + b"\0\0"
    path = tmp_path / "m.stl"
    path.write_bytes(bytes(data))
    vertices, triangles = fa.read_binary_stl_mesh(path)
    assert vertices.shape == (4, 3) and triangles.shape == (2, 3)
    assert np.allclose(vertices[triangles[1]], [[1, 0, 0], [1, 1, 0], [0, 1, 0]])
    assert np.array_equal(fa.read_binary_stl(path), vertices)


def test_moveit_pairs_are_parsed_exactly_not_by_substring():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "DENTOWorkflow" / "Resources" / "Python"))
    template = "[Step 5C] DENTO Final Printable Template"
    reason = (f"MoveIt rejected the explicit static joint state; contacts={template}<->burr, "
              "dentobot_mouth_barrier_lip_slab<->pneumatic_spindle-Copy (and 2 more)")
    pairs = fa.moveit_pairs(reason)
    assert pairs == [sorted([template, "burr"]), ["dentobot_mouth_barrier_lip_slab", "pneumatic_spindle-Copy"]]
    # Substring presence would report spindle<->template; the exact pairs do not.
    assert "Template" in reason and "pneumatic_spindle" in reason
    assert not any(any("Template" in b for b in p) and any(b.startswith("pneumatic_spindle") for b in p) for p in pairs)
    wrapped = f"Approach corridor unavailable (axial corridor blocked 0.73 mm: x; contacts={template}<->pneumatic_spindle-Copy); direct"
    assert fa.moveit_pairs(wrapped) == [sorted([template, "pneumatic_spindle-Copy"])]


def test_model_world_polydata_applies_the_parent_jaw_transform():
    # S6-AUDIT-D-01 root cause: a lower-jaw template sits under the mouth-opening
    # transform; check D used its raw (closed-jaw) polydata.
    vtk = pytest.importorskip("vtk")

    source = vtk.vtkSphereSource()
    source.Update()

    class Parent:
        def GetTransformToWorld(self, transform):
            shift = vtk.vtkTransform()
            shift.Translate(0.0, 0.0, 24.0)
            transform.Concatenate(shift)

    class Model:
        def __init__(self, parent):
            self.parent = parent

        def GetPolyData(self):
            return source.GetOutput()

        def GetParentTransformNode(self):
            return self.parent

    raw = np.array(fa.model_world_polydata(Model(None)).GetCenter())
    opened = np.array(fa.model_world_polydata(Model(Parent())).GetCenter())
    assert np.allclose(opened - raw, [0.0, 0.0, 24.0])
    assert np.allclose(np.array(source.GetOutput().GetCenter()), raw)  # source untouched
