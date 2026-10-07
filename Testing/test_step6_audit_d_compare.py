"""Pure checks of the S6-AUDIT-D-01 scene dump and offline comparison (no ROS/Slicer)."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import moveit_scene_dump as dump_tools  # noqa: E402
import step6_audit_d_compare as compare  # noqa: E402

SPINDLE = dump_tools.SPINDLE_LINK
TEMPLATE = "[Step 5C] DENTO Final Printable Template"


def test_acm_explicit_entry_wins_over_default():
    acm = {"entry_names": [SPINDLE, TEMPLATE], "entry_values": [[False, True], [True, False]],
           "default_entry_names": [TEMPLATE], "default_entry_values": [False]}
    assert compare.dump_tools.acm_lookup(acm, SPINDLE, TEMPLATE) == {"allowed": True, "source": "entry"}


def test_acm_default_entry_applies_when_pair_is_not_listed():
    acm = {"entry_names": [SPINDLE], "entry_values": [[False]],
           "default_entry_names": [TEMPLATE], "default_entry_values": [True]}
    assert dump_tools.acm_lookup(acm, SPINDLE, TEMPLATE) == {"allowed": True, "source": f"default:{TEMPLATE}"}
    assert dump_tools.acm_lookup({}, SPINDLE, TEMPLATE) == {"allowed": False, "source": "absent"}


def test_urdf_summary_detects_missing_spindle_collision():
    with_collision = (f'<robot name="r"><link name="{SPINDLE}"><collision><geometry>'
                      '<mesh filename="package://x/s.stl" scale="0.001 0.001 0.001"/></geometry></collision></link></robot>')
    without = f'<robot name="r"><link name="{SPINDLE}"><visual><geometry><box size="1 1 1"/></geometry></visual></link></robot>'
    assert dump_tools.urdf_collision_summary(with_collision)["spindle_has_collision"] is True
    assert dump_tools.urdf_collision_summary(without)["spindle_has_collision"] is False


def test_pose_matrix_and_object_mesh_compose_object_then_mesh_pose():
    half = math.sqrt(0.5)
    rotation = dump_tools.pose_matrix((1.0, 0.0, 0.0), (0.0, 0.0, half, half))  # +90 deg about z
    assert np.allclose(rotation[:3, :3] @ [1, 0, 0], [0, 1, 0])
    record = {"pose": rotation.tolist(),
              "meshes": [{"pose": dump_tools.pose_matrix((0, 0, 1), (0, 0, 0, 1)).tolist(),
                          "vertices": [[1, 0, 0], [0, 1, 0], [0, 0, 0]], "triangles": [[0, 1, 2]]}]}
    vertices, triangles = dump_tools.object_mesh_in_frame(record)
    assert np.allclose(vertices[0], [1, 1, 1])
    assert triangles.tolist() == [[0, 1, 2]]


def test_byte_fields_from_rclpy_are_integers():
    assert dump_tools.byte_int(b"\x00") == 0
    assert dump_tools.byte_int(b"\x02") == 2
    assert dump_tools.byte_int(3) == 3


def test_base_frame_vertices_map_to_world_mm():
    base = np.eye(4)
    base[:3, 3] = [10, 0, 0]
    assert np.allclose(compare.base_frame_to_world_mm(base, [[0.001, 0, 0]]), [[11, 0, 0]])


@pytest.mark.parametrize("acm, placed, closed, intersecting, valid, finding", [
    ({"allowed": True, "source": "entry"}, 0.0, None, True, True, "acm_allows_pair"),
    ({"allowed": False}, 2.0, 0.01, True, True, "moveit_template_at_closed_jaw"),
    ({"allowed": False}, 2.0, 2.0, True, True, "moveit_template_differs"),
    ({"allowed": False}, 0.01, None, False, True, "consistent_clear"),
    ({"allowed": False}, 0.01, None, False, False, "moveit_contact_not_reproduced"),
    ({"allowed": False}, 0.01, None, True, True, "checker_misses_intersection"),
    ({"allowed": False}, 0.01, None, True, False, "consistent"),
])
def test_classification_follows_the_agreed_table(acm, placed, closed, intersecting, valid, finding):
    dev = (lambda h: None if h is None else {"hausdorff_mm": h})
    result = compare.classify(acm, dev(placed), dev(closed), {"intersecting": intersecting}, valid)
    assert result["finding"] == finding


def test_mesh_deviation_detects_a_shift_bounds_alone_would_hide():
    pytest.importorskip("vtk")
    import step6_frame_audit as frame_audit

    grid = np.array([[x, y, 0.0] for x in range(5) for y in range(5)], float)
    triangles = []
    for x in range(4):
        for y in range(4):
            a = x * 5 + y
            triangles += [[a, a + 5, a + 1], [a + 1, a + 5, a + 6]]
    same = frame_audit.mesh_surface_deviation(grid, triangles, grid, triangles)
    assert same["hausdorff_mm"] == pytest.approx(0.0, abs=1e-9)
    lifted = grid + [0, 0, 0.3]
    moved = frame_audit.mesh_surface_deviation(grid, triangles, lifted, triangles)
    assert moved["hausdorff_mm"] == pytest.approx(0.3, abs=1e-6)
    assert moved["bounds_delta_mm"] == pytest.approx(0.3, abs=1e-9)


def test_world_objects_convert_rclpy_numpy_fields_to_json():
    import json
    from types import SimpleNamespace as N

    pose = N(position=N(x=0.0, y=0.0, z=0.0), orientation=N(x=0.0, y=0.0, z=0.0, w=1.0))
    mesh = N(vertices=[N(x=np.float64(1), y=0.0, z=0.0)] * 3,
             triangles=[N(vertex_indices=np.array([0, 1, 2], dtype=np.uint32))])
    obj = N(id=TEMPLATE, header=N(frame_id="base_link"), pose=pose, operation=b"\x00", meshes=[mesh],
            mesh_poses=[pose], primitives=[N(type=b"\x01", dimensions=np.array([1.0, 2.0, 3.0]))],
            primitive_poses=[pose], planes=[])
    objects = dump_tools.world_objects(N(world=N(collision_objects=[obj])))
    assert json.loads(json.dumps(objects))[0]["meshes"][0]["triangles"] == [[0, 1, 2]]
    assert objects[0]["primitives"][0]["type"] == 1
