from __future__ import annotations

import hashlib
import math
import struct
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

import step6_collision_agreement as collision  # noqa: E402


LINKS = ("pneumatic_spindle-Copy", "burr", "link-5")
FACES = np.asarray([[0, 1, 2]], dtype=np.int64)
ROBOT_TRIANGLE = np.asarray([[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0]], dtype=float)
FAR_TRIANGLE = np.asarray([[1000, 1000, 1000], [1010, 1000, 1000], [1000, 1010, 1000]], dtype=float)


def _write_stl(path: Path, vertices):
    data = bytearray(80) + bytearray(struct.pack("<I", 1))
    data += struct.pack("<3f", 0.0, 0.0, 1.0)
    for vertex in vertices:
        data += struct.pack("<3f", *vertex)
    data += b"\0\0"
    path.write_bytes(data)


def _urdf_and_package(tmp_path):
    package = tmp_path / "dentobot_description"
    mesh_dir = package / "meshes"
    mesh_dir.mkdir(parents=True)
    links = ["base_link"]
    for link in LINKS:
        filename = f"meshes/{link}.stl"
        _write_stl(package / filename, ROBOT_TRIANGLE)
        links.append(
            f'<link name="{link}"><collision><geometry><mesh '
            f'filename="package://dentobot_description/{filename}"/>'
            f'</geometry></collision></link>'
        )
    urdf_text = """<robot name="collision-test">
<link name="base_link"/>
{links}
<joint name="j1" type="revolute"><parent link="base_link"/>
 <child link="pneumatic_spindle-Copy"/><origin xyz="0 0 0"/>
 <axis xyz="0 0 1"/></joint>
<joint name="j2" type="prismatic"><parent link="pneumatic_spindle-Copy"/>
 <child link="burr"/><origin xyz="0.1 0 0"/><axis xyz="1 0 0"/></joint>
<joint name="tool_offset" type="fixed"><parent link="burr"/><child link="link-5"/>
 <origin xyz="0.1 0 0"/></joint>
</robot>""".format(links="\n".join(links[1:]))
    urdf_path = tmp_path / "robot.urdf"
    urdf_path.write_text(urdf_text, encoding="utf-8")
    return urdf_path, package, urdf_text


class _Base:
    def __init__(self, vtk, matrix):
        self.vtk = vtk
        self.matrix = np.asarray(matrix, dtype=float)

    def GetMatrixTransformToWorld(self, target):
        for row in range(4):
            for col in range(4):
                target.SetElement(row, col, float(self.matrix[row, col]))


class _Bridge:
    def __init__(self, valid=True, reason="", authoritative=True):
        self.response = valid, reason, authoritative
        self.calls = []

    def check_moveit_static_joint_state(self, joints):
        self.calls.append(dict(joints))
        return self.response


def _namespace(tmp_path, vtk, *, valid=True, reason="", authoritative=True, base=None):
    urdf_path, package, urdf_text = _urdf_and_package(tmp_path)
    base_matrix = np.eye(4)
    base_matrix[:3, 3] = [10.0, 20.0, 30.0]
    base = base or _Base(vtk, base_matrix)
    logic = SimpleNamespace(robotDescriptionPaths=lambda: (str(urdf_path), str(package)))
    snapshot = {
        "captured_utc": "synthetic-test",
        "link_padding": {link: 0.0 for link in LINKS},
        "link_scale": {link: 1.0 for link in LINKS},
        "robot_description": {"sha256": hashlib.sha256(urdf_text.encode()).hexdigest()},
    }
    bridge = _Bridge(valid, reason, authoritative)
    namespace = {
        "logic": logic,
        "parameter_node": SimpleNamespace(robotBaseTransform=base),
        "scene_snapshot": snapshot,
        "acm": {},
        "bridge": bridge,
    }
    return namespace, bridge, base, package


def _far_body(role="lip"):
    return {"vertices_world_mm": FAR_TRIANGLE.copy(), "triangles": FACES.copy(), "role": role}


def _target_crossing_body():
    # Vertical triangle crosses the burr's horizontal triangle at j1=90°, j2=.03 m.
    return {
        "vertices_world_mm": np.asarray([[7, 153, 20], [7, 153, 40], [8, 154, 30]], dtype=float),
        "triangles": FACES.copy(),
        "role": "selected-target-tooth",
    }


@pytest.fixture
def empty_mesh_cache():
    collision._MESH_CACHE.clear()
    yield
    collision._MESH_CACHE.clear()


def test_exact_mesh_separation_reports_intersection_touch_and_separation():
    horizontal = np.asarray([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=float)
    crossing = np.asarray([[2, 2, -5], [2, 2, 5], [4, 4, 0]], dtype=float)
    intersect = collision.audit.exact_mesh_separation(horizontal, FACES, crossing, FACES)
    assert intersect["intersecting"] and intersect["distance_mm"] == 0.0

    touching = np.asarray([[10, 0, 0], [20, 0, 0], [10, 10, 0]], dtype=float)
    touch = collision.audit.exact_mesh_separation(horizontal, FACES, touching, FACES)
    assert touch["distance_mm"] == 0.0  # Unsigned contact; do not infer penetration.

    separated = horizontal + np.asarray([0.0, 0.0, 2.0])
    gap = collision.audit.exact_mesh_separation(horizontal, FACES, separated, FACES)
    assert not gap["intersecting"]
    assert gap["distance_mm"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "exact,valid,named,authoritative,allowed,intended,expected",
    [
        ({"intersecting": False}, True, False, False, False, False, ("validity_unavailable", "FAIL")),
        ({"intersecting": False}, True, False, True, True, False, ("allowed_by_acm", "PASS")),
        ({"intersecting": True}, False, True, True, True, False, ("acm_contact_reported", "FAIL")),
        ({"intersecting": True}, True, False, True, False, True, ("intended_terminal_contact", "PASS")),
        ({"intersecting": True}, False, True, True, False, False, ("consistent_collision", "PASS")),
        ({"intersecting": False}, False, True, True, False, False, ("contact_not_reproduced", "FAIL")),
        ({"intersecting": True}, True, False, True, False, False, ("checker_misses_intersection", "FAIL")),
        ({"intersecting": True}, False, False, True, False, False, ("contact_not_reported", "FAIL")),
        ({"intersecting": False}, True, False, True, False, False, ("consistent_clear", "PASS")),
    ],
)
def test_classify_pair_covers_agreement_and_contact_policy_branches(
    exact, valid, named, authoritative, allowed, intended, expected
):
    assert collision.classify_pair(
        exact, valid=valid, named=named, authoritative=authoritative,
        allowed=allowed, intended=intended,
    ) == expected


def test_end_to_end_fake_scene_produces_three_clear_pass_rows(tmp_path, empty_mesh_cache):
    vtk = pytest.importorskip("vtk")
    namespace, bridge, _, _ = _namespace(tmp_path, vtk)

    report = collision.collision_agreement(namespace, {"j1": math.pi / 2, "j2": 0.03}, {"lip": _far_body()})

    assert report["status"] == "PASS"
    assert len(report["rows"]) == 3
    assert all(row["status"] == "PASS" and row["classification"] == "consistent_clear" for row in report["rows"])
    assert bridge.calls == [{"j1": math.pi / 2, "j2": 0.03}]


def test_collision_rows_recompute_joint_and_base_poses_independently(tmp_path, monkeypatch, empty_mesh_cache):
    vtk = pytest.importorskip("vtk")
    namespace, _, base, _ = _namespace(tmp_path, vtk)
    observed = []
    exact_mesh_separation = collision.audit.exact_mesh_separation

    def capture_robot_pose(robot_vertices, robot_triangles, body_vertices, body_triangles, **kwargs):
        observed.append(np.asarray(robot_vertices).copy())
        return exact_mesh_separation(robot_vertices, robot_triangles, body_vertices, body_triangles, **kwargs)

    monkeypatch.setattr(collision.audit, "exact_mesh_separation", capture_robot_pose)
    bodies = {"lip": _far_body()}
    first = collision.collision_agreement(namespace, {"j1": math.pi / 2, "j2": 0.03}, bodies)
    second = collision.collision_agreement(namespace, {"j1": 0.0, "j2": 0.05}, bodies)
    moved_base = np.eye(4)
    moved_base[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    moved_base[:3, 3] = [5, 6, 7]
    base.matrix = moved_base
    third = collision.collision_agreement(namespace, {"j1": math.pi / 2, "j2": 0.03}, bodies)

    assert all(report["status"] == "PASS" for report in (first, second, third))
    # The first vertex of link-5 follows FK, then Base: [10,250,30], [260,20,30], [-225,6,7].
    assert observed[2][0] == pytest.approx([10, 250, 30])
    assert observed[5][0] == pytest.approx([260, 20, 30])
    assert observed[8][0] == pytest.approx([-225, 6, 7])
    assert not np.allclose(observed[2], observed[5])
    assert not np.allclose(observed[5], observed[8])


def test_selected_target_contact_is_exempt_only_for_burr_at_drilling_end(tmp_path, empty_mesh_cache):
    vtk = pytest.importorskip("vtk")
    namespace, _, _, _ = _namespace(tmp_path, vtk, valid=True)
    target = {"DENTO target tooth 23": _target_crossing_body()}
    end = collision.collision_agreement(
        {**namespace, "phase": "drilling_end"}, {"j1": math.pi / 2, "j2": 0.03}, target
    )
    entry = collision.collision_agreement(
        {**namespace, "phase": "entry"}, {"j1": math.pi / 2, "j2": 0.03}, target
    )
    end_burr = next(row for row in end["rows"] if row["link"] == "burr")
    entry_burr = next(row for row in entry["rows"] if row["link"] == "burr")

    assert end_burr["exact"]["intersecting"]
    assert end_burr["intended_terminal_contact"] and end_burr["status"] == "PASS"
    assert end_burr["classification"] == "intended_terminal_contact"
    assert not entry_burr["intended_terminal_contact"] and entry_burr["status"] == "FAIL"
    assert entry_burr["classification"] == "checker_misses_intersection"


def test_moveit_contact_ids_are_matched_exactly_even_when_names_share_prefix(tmp_path, empty_mesh_cache):
    vtk = pytest.importorskip("vtk")
    first_id = "[Step 5C] DENTO Final Printable Template"
    prefix_id = first_id + " backup"
    reason = f"MoveIt invalid; contacts=burr<->{first_id}"
    namespace, _, _, _ = _namespace(tmp_path, vtk, valid=False, reason=reason)
    bodies = {
        first_id: {**_target_crossing_body(), "role": "template"},
        prefix_id: _far_body("template"),
    }

    report = collision.collision_agreement(namespace, {"j1": math.pi / 2, "j2": 0.03}, bodies)
    exact = next(row for row in report["rows"] if row["link"] == "burr" and row["body"] == first_id)
    prefix = next(row for row in report["rows"] if row["link"] == "burr" and row["body"] == prefix_id)

    assert report["status"] == "PASS"
    assert exact["moveit_named"] and exact["classification"] == "consistent_collision"
    assert not prefix["moveit_named"] and prefix["classification"] == "consistent_clear"


@pytest.mark.parametrize("case", ["empty_bodies", "missing_snapshot", "padding", "urdf_digest"])
def test_missing_scene_identity_or_nonzero_padding_fails(tmp_path, empty_mesh_cache, case):
    vtk = pytest.importorskip("vtk")
    namespace, _, _, _ = _namespace(tmp_path, vtk)
    bodies = {"lip": _far_body()}
    if case == "empty_bodies":
        bodies = {}
    elif case == "missing_snapshot":
        namespace.pop("scene_snapshot")
    elif case == "padding":
        namespace["scene_snapshot"]["link_padding"]["burr"] = 0.001
    else:
        namespace["scene_snapshot"]["robot_description"]["sha256"] = "wrong"

    report = collision.collision_agreement(namespace, {"j1": math.pi / 2, "j2": 0.03}, bodies)

    assert report["status"] == "FAIL"
    assert report["issues"]


@pytest.mark.parametrize(
    "valid,reason,issue",
    [
        (False, "invalid with no contacts", "no parseable"),
        (False, "invalid; contacts=burr<->unmapped-object", "outside audited"),
        (False, "invalid; contacts=burr<->lip (and 2 more)", "truncated"),
    ],
)
def test_invalid_missing_truncated_or_out_of_scope_contacts_fail(tmp_path, empty_mesh_cache, valid, reason, issue):
    vtk = pytest.importorskip("vtk")
    namespace, _, _, _ = _namespace(tmp_path, vtk, valid=valid, reason=reason)

    report = collision.collision_agreement(namespace, {"j1": math.pi / 2, "j2": 0.03}, {"lip": _far_body()})

    assert report["status"] == "FAIL"
    assert any(issue in item.lower() for item in report["issues"])


def test_stl_mesh_cache_reads_once_and_invalidates_on_changed_bytes(tmp_path, monkeypatch, empty_mesh_cache):
    vtk = pytest.importorskip("vtk")
    namespace, _, _, package = _namespace(tmp_path, vtk)
    calls = []
    read_mesh = collision.audit.read_binary_stl_mesh

    def count_reads(path):
        calls.append(Path(path).name)
        return read_mesh(path)

    monkeypatch.setattr(collision.audit, "read_binary_stl_mesh", count_reads)
    joints = {"j1": math.pi / 2, "j2": 0.03}
    assert collision.collision_agreement(namespace, joints, {"lip": _far_body()})["status"] == "PASS"
    assert collision.collision_agreement(namespace, joints, {"lip": _far_body()})["status"] == "PASS"
    assert len(calls) == 3

    changed = ROBOT_TRIANGLE.copy()
    changed[1, 0] += 0.002
    _write_stl(package / "meshes" / f"{LINKS[0]}.stl", changed)
    assert collision.collision_agreement(namespace, joints, {"lip": _far_body()})["status"] == "PASS"
    assert len(calls) == 4
