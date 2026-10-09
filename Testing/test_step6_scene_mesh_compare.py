from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest


TESTING_DIR = Path(__file__).resolve().parent
if str(TESTING_DIR) not in sys.path:
    sys.path.insert(0, str(TESTING_DIR))

import step6_scene_mesh_compare as compare  # noqa: E402


def _tetrahedron():
    vertices = np.asarray(
        [[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=float
    )
    triangles = np.asarray([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64)
    return vertices, triangles


def _moveit_record(object_id, parts):
    identity = np.eye(4).tolist()
    return {
        "id": object_id,
        "frame_id": "base_link",
        "pose": identity,
        "meshes": [
            {"pose": identity, "vertices": (vertices / 1000.0).tolist(), "triangles": triangles.tolist()}
            for vertices, triangles in parts
        ],
        "primitives": [],
        "planes": 0,
    }


def _write_fixture(tmp_path, slicer_meshes, moveit_meshes=None, *, record_changes=None,
                   manifest_changes=None, object_changes=None):
    case_dir = tmp_path / f"case-{len(list(tmp_path.iterdir())):02d}"
    case_dir.mkdir()
    dump_dir = case_dir / "dump"
    export_dir = case_dir / "slicer"
    dump_dir.mkdir()
    export_dir.mkdir()
    if moveit_meshes is None:
        moveit_meshes = slicer_meshes

    export_entries = []
    for index, (object_id, mesh) in enumerate(slicer_meshes.items()):
        vertices, triangles = mesh
        filename = f"mesh-{index:03d}.npz"
        mesh_path = export_dir / filename
        np.savez_compressed(mesh_path, vertices=vertices, triangles=triangles)
        entry = {
            "id": object_id,
            "source_id": f"source:{object_id}",
            "file": filename,
            "vertices": len(vertices),
            "triangles": len(triangles),
            "sha256": hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
            "status": "PASS",
            "jaw_transform_application_count": 0,
        }
        if object_changes and object_id in object_changes:
            entry.update(object_changes[object_id])
        export_entries.append(entry)

    moveit_entries = []
    for object_id, geometry in moveit_meshes.items():
        parts = geometry if isinstance(geometry, list) else [geometry]
        moveit_entries.append(_moveit_record(object_id, parts))
    if record_changes:
        for record in moveit_entries:
            record.update(record_changes.get(record["id"], {}))

    manifest = {
        "schema_version": "1.0",
        "coordinate_frame": "base_link",
        "units": "mm",
        "status": "PASS",
        "objects": export_entries,
    }
    if manifest_changes:
        manifest.update(manifest_changes)
    (export_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (dump_dir / "world-objects.json").write_text(json.dumps(moveit_entries), encoding="utf-8")
    return dump_dir, export_dir


def test_identical_mesh_scene_passes_with_sampled_surface_metrics(tmp_path):
    mesh = _tetrahedron()
    dump_dir, export_dir = _write_fixture(tmp_path, {"jaw": mesh})

    report = compare.analyse_scene(dump_dir, export_dir)

    assert report["status"] == "PASS"
    assert report["objects"]["jaw"]["vertex_count"]["match"]
    assert report["objects"]["jaw"]["triangle_count"]["match"]
    assert report["objects"]["jaw"]["sampled_hausdorff_mm"] <= 0.05
    assert "not a continuous-surface proof" in report["objects"]["jaw"]["sample_method"]


def test_shifted_mesh_fails_and_names_object(tmp_path):
    vertices, triangles = _tetrahedron()
    shifted = (vertices + np.asarray([0.3, 0.0, 0.0]), triangles)
    dump_dir, export_dir = _write_fixture(
        tmp_path, {"template-17": (vertices, triangles)}, {"template-17": shifted}
    )

    report = compare.analyse_scene(dump_dir, export_dir)

    assert report["status"] == "FAIL"
    assert report["objects"]["template-17"]["sampled_hausdorff_mm"] == pytest.approx(0.3, abs=1e-5)
    assert any(failure.get("object_id") == "template-17" for failure in report["failures"])


def test_decimated_same_bounds_mesh_fails_on_count_mismatch(tmp_path):
    corners = np.asarray([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]], dtype=float)
    moveit_triangles = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    moveit_mesh = corners, moveit_triangles
    center = np.asarray([[5, 5, 0]], dtype=float)
    slicer_vertices = np.vstack((corners, center))
    slicer_triangles = np.asarray([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], dtype=np.int64)
    dump_dir, export_dir = _write_fixture(
        tmp_path,
        {"flat-jaw": (slicer_vertices, slicer_triangles)},
        {"flat-jaw": moveit_mesh},
    )

    report = compare.analyse_scene(dump_dir, export_dir)
    result = report["objects"]["flat-jaw"]

    assert report["status"] == "FAIL"
    assert result["bounds_mm"]["delta_max_mm"] == pytest.approx(0.0)
    assert result["sampled_hausdorff_mm"] <= 0.05
    assert not result["vertex_count"]["match"]
    assert not result["triangle_count"]["match"]


@pytest.mark.parametrize(
    "slicer_ids,moveit_ids,reason",
    [
        (("jaw",), ("jaw", "lip"), "missing from Slicer export"),
        (("jaw", "lip"), ("jaw",), "extra objects"),
    ],
)
def test_missing_or_extra_object_id_fails(tmp_path, slicer_ids, moveit_ids, reason):
    mesh = _tetrahedron()
    dump_dir, export_dir = _write_fixture(
        tmp_path,
        {object_id: mesh for object_id in slicer_ids},
        {object_id: mesh for object_id in moveit_ids},
    )

    report = compare.analyse_scene(dump_dir, export_dir)

    assert report["status"] == "FAIL"
    assert any(reason in failure["reason"] for failure in report["failures"])


def test_moveit_frame_and_unsupported_primitive_are_rejected(tmp_path):
    mesh = _tetrahedron()
    dump_dir, export_dir = _write_fixture(
        tmp_path, {"jaw": mesh}, record_changes={"jaw": {"frame_id": "map"}}
    )
    with pytest.raises(ValueError, match="frame_id"):
        compare.analyse_scene(dump_dir, export_dir)

    dump_dir, export_dir = _write_fixture(
        tmp_path, {"jaw": mesh}, record_changes={"jaw": {"primitives": [{"type": 1}]}}
    )
    with pytest.raises(ValueError, match="unsupported primitives"):
        compare.analyse_scene(dump_dir, export_dir)

    dump_dir, export_dir = _write_fixture(
        tmp_path, {"jaw": mesh}, record_changes={"jaw": {"planes": 1}}
    )
    with pytest.raises(ValueError, match="unsupported planes"):
        compare.analyse_scene(dump_dir, export_dir)

    dump_dir, export_dir = _write_fixture(
        tmp_path, {"jaw": mesh}, record_changes={"jaw": {"meshes": []}}
    )
    with pytest.raises(ValueError, match="no usable mesh"):
        compare.analyse_scene(dump_dir, export_dir)


def test_changed_connectivity_is_detected_by_triangle_centroid_samples(tmp_path):
    vertices = np.asarray([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 8]], dtype=float)
    slicer_triangles = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    moveit_triangles = np.asarray([[0, 1, 3], [1, 2, 3]], dtype=np.int64)
    dump_dir, export_dir = _write_fixture(
        tmp_path,
        {"warped-panel": (vertices, slicer_triangles)},
        {"warped-panel": (vertices, moveit_triangles)},
    )

    report = compare.analyse_scene(dump_dir, export_dir)
    result = report["objects"]["warped-panel"]

    assert result["vertex_count"]["match"]
    assert result["triangle_count"]["match"]
    assert result["sampled_hausdorff_mm"] > 0.05
    assert report["status"] == "FAIL"


def test_mesh_parts_are_combined_with_vertex_offsets(tmp_path):
    vertices, triangles = _tetrahedron()
    second_vertices = vertices + np.asarray([20.0, 0.0, 0.0])
    combined_vertices = np.vstack((vertices, second_vertices))
    combined_triangles = np.vstack((triangles, triangles + len(vertices)))
    dump_dir, export_dir = _write_fixture(
        tmp_path,
        {"two-parts": (combined_vertices, combined_triangles)},
        {"two-parts": [(vertices, triangles), (second_vertices, triangles)]},
    )

    report = compare.analyse_scene(dump_dir, export_dir)

    assert report["status"] == "PASS"
    assert report["objects"]["two-parts"]["vertex_count"]["moveit"] == 8
    assert report["objects"]["two-parts"]["triangle_count"]["moveit"] == 8


def test_failed_manifest_is_refused_without_using_partial_files(tmp_path):
    mesh = _tetrahedron()
    dump_dir, export_dir = _write_fixture(tmp_path, {"jaw": mesh}, manifest_changes={"status": "FAIL"})

    with pytest.raises(ValueError, match="manifest status is 'FAIL'"):
        compare.analyse_scene(dump_dir, export_dir)


@pytest.mark.parametrize(
    "metadata,reason",
    [({"sha256": "0" * 64}, "sha256"), ({"vertices": 99}, "counts")],
)
def test_export_manifest_hash_and_counts_are_checked(tmp_path, metadata, reason):
    dump_dir, export_dir = _write_fixture(
        tmp_path, {"jaw": _tetrahedron()}, object_changes={"jaw": metadata}
    )

    with pytest.raises(ValueError, match=reason):
        compare.analyse_scene(dump_dir, export_dir)


def test_nonfinite_export_mesh_is_rejected(tmp_path):
    vertices, triangles = _tetrahedron()
    vertices[1, 0] = np.nan
    dump_dir, export_dir = _write_fixture(tmp_path, {"jaw": (vertices, triangles)})

    with pytest.raises(ValueError, match="nonfinite"):
        compare.analyse_scene(dump_dir, export_dir)


@pytest.mark.parametrize("shift,expected", [(0.0, 0), (0.3, 1)])
def test_cli_writes_json_and_exits_zero_only_for_pass(tmp_path, shift, expected):
    vertices, triangles = _tetrahedron()
    slicer_vertices = vertices + np.asarray([shift, 0.0, 0.0])
    dump_dir, export_dir = _write_fixture(tmp_path, {"jaw": (slicer_vertices, triangles)},
                                           {"jaw": (vertices, triangles)})
    output = tmp_path / "comparison.json"

    result = compare.main(["--dump", str(dump_dir), "--slicer", str(export_dir), "--out", str(output)])

    assert result == expected
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == ("PASS" if expected == 0 else "FAIL")


# A zero-area face (three nearly collinear vertices, full float precision) from the
# S6-FRAME-SYNC-01 L2 triage, plus one ordinary far-away triangle because the comparator
# rejects objects with no usable triangle. Both meshes are identical, so every sample lies
# on the surface. vtkCellLocator.FindClosestPoint reported 1.159 and 4.410 mm for vertices 0
# and 2 (true distance 0). A copy rounded to six decimals does not reproduce the failure.
SLIVER_VERTICES = np.asarray([
    [6.089701165113102, -8.995953590745787, -10.388018550851388],
    [5.252089806538405, -7.83704009364123, -11.249073400999587],
    [2.06470318973593, -3.4269931991143077, -14.52567021120208],
    [30.0, 0.0, 0.0],
    [31.0, 0.0, 0.0],
    [30.0, 1.0, 0.0],
])
SLIVER_TRIANGLES = np.asarray([[0, 1, 2], [3, 4, 5]], dtype=np.int64)


def test_zero_area_face_vertices_lie_on_the_surface(tmp_path):
    dump_dir, export_dir = _write_fixture(tmp_path, {"sliver": (SLIVER_VERTICES, SLIVER_TRIANGLES)})

    report = compare.analyse_scene(dump_dir, export_dir)

    assert report["status"] == "PASS"
    assert report["objects"]["sliver"]["sampled_hausdorff_mm"] <= 1e-9


def test_point_triangle_distance_is_exact_for_faces_and_zero_area_faces():
    import step6_frame_audit as frame_audit

    rng = np.random.default_rng(3)
    points = rng.normal(size=(300, 3)) * 5
    a, b, c = rng.normal(size=(3, 300, 3)) * 5
    closest = frame_audit._closest_point_triangle(points, a, b, c)
    np.testing.assert_allclose(frame_audit.point_triangle_distance(points, a, b, c),
                               np.linalg.norm(points - closest, axis=1), rtol=0, atol=1e-9)

    # Collinear triangle on the x-axis from 0 to 10: the nearest point is the clamped x.
    origin = np.zeros((300, 3))
    far_end = np.zeros((300, 3))
    far_end[:, 0] = 10.0
    middle = np.zeros((300, 3))
    middle[:, 0] = 4.0
    clamped = np.clip(points[:, 0], 0.0, 10.0)
    expected = np.sqrt((points[:, 0] - clamped) ** 2 + points[:, 1] ** 2 + points[:, 2] ** 2)
    np.testing.assert_allclose(frame_audit.point_triangle_distance(points, origin, far_end, middle),
                               expected, rtol=0, atol=1e-9)


def test_near_degenerate_faces_are_silent_and_bounded_by_their_edges():
    import warnings

    import step6_frame_audit as frame_audit

    rng = np.random.default_rng(11)
    a = rng.normal(size=(400, 3)) * 5
    direction = rng.normal(size=(400, 3))
    direction /= np.linalg.norm(direction, axis=1)[:, None]
    b = a + direction * 4.0
    # Nearly collinear faces: the perpendicular offset is about 1e-8 of the edge length.
    c = a + direction * 7.0 + rng.normal(size=(400, 3)) * 1e-7
    points = rng.normal(size=(400, 3)) * 5
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        got = frame_audit.point_triangle_distance(points, a, b, c)
    edges = np.minimum(np.minimum(frame_audit._segment_distance(points, a, b),
                                  frame_audit._segment_distance(points, b, c)),
                       frame_audit._segment_distance(points, c, a))
    assert np.isfinite(got).all()
    assert np.all(got <= edges + 1e-5)   # a face's distance is never above its nearest edge
    assert np.all(got >= edges - 1e-5)   # and differs from the edges only by the sliver's width


def test_nearest_surface_distance_matches_brute_force_with_zero_area_faces():
    import step6_frame_audit as frame_audit

    rng = np.random.default_rng(5)
    base = rng.normal(size=(50, 3)) * 5
    faces = rng.integers(0, 50, size=(80, 3))
    sliver_tips = base[faces[:20, 0]] + rng.normal(size=(20, 1)) * rng.normal(size=(20, 3))
    vertices = np.vstack([base, sliver_tips])
    faces = np.vstack([faces, np.c_[faces[:20, 0], np.arange(50, 70), np.arange(50, 70)]])
    points = rng.normal(size=(60, 3)) * 6

    fast = frame_audit.nearest_surface_distance(points, vertices, faces)
    brute = np.asarray([
        frame_audit.point_triangle_distance(np.repeat(p[None], len(faces), 0),
                                            vertices[faces[:, 0]], vertices[faces[:, 1]],
                                            vertices[faces[:, 2]]).min()
        for p in points
    ])
    np.testing.assert_allclose(fast, brute, rtol=0, atol=1e-12)


def test_shifted_zero_area_face_still_reports_its_shift(tmp_path):
    dump_dir, export_dir = _write_fixture(
        tmp_path, {"sliver": (SLIVER_VERTICES, SLIVER_TRIANGLES)},
        {"sliver": (SLIVER_VERTICES + [0.0, 0.0, 0.2], SLIVER_TRIANGLES)},
    )

    report = compare.analyse_scene(dump_dir, export_dir)

    assert report["status"] == "FAIL"
    assert report["objects"]["sliver"]["sampled_hausdorff_mm"] == pytest.approx(0.2, abs=1e-6)
