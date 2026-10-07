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
