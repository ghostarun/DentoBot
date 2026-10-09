"""Compare all exported Slicer world meshes with a MoveIt scene dump.

Distances are sampled at every mesh vertex and triangle centroid in both
directions. They are a discrete surface check, not a proof over every point of
the continuous surfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np


TESTING_DIR = Path(__file__).resolve().parent
PYTHON_RESOURCES = TESTING_DIR.parent / "DENTOWorkflow" / "Resources" / "Python"
for _path in (str(TESTING_DIR), str(PYTHON_RESOURCES)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import moveit_scene_dump as scene_dump  # noqa: E402
import step6_frame_audit as frame_audit  # noqa: E402


FRAME = "base_link"
UNITS = "mm"
MAX_HAUSDORFF_MM = 0.05


def _read_json(path: Path, description: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {description} at {path}: {exc}") from exc


def _identity_and_pose_matrix(value, description: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{description} must be a finite 4x4 matrix")
    return matrix


def _mesh_arrays(vertices, triangles, description: str) -> tuple[np.ndarray, np.ndarray]:
    raw_vertices = np.asarray(vertices)
    raw_triangles = np.asarray(triangles)
    if raw_vertices.ndim != 2 or raw_vertices.shape[1:] != (3,) or raw_vertices.shape[0] < 3:
        raise ValueError(f"{description} vertices must have shape (N, 3), N >= 3")
    if not np.issubdtype(raw_vertices.dtype, np.number):
        raise ValueError(f"{description} vertices must be numeric")
    vertices = np.asarray(raw_vertices, dtype=np.float64)
    if not np.isfinite(vertices).all():
        raise ValueError(f"{description} vertices contain nonfinite values")

    if raw_triangles.ndim != 2 or raw_triangles.shape[1:] != (3,) or raw_triangles.shape[0] < 1:
        raise ValueError(f"{description} triangles must have shape (M, 3), M >= 1")
    if not np.issubdtype(raw_triangles.dtype, np.integer):
        raise ValueError(f"{description} triangle indices must have an integer dtype")
    triangles = np.asarray(raw_triangles, dtype=np.int64)
    if triangles.min() < 0 or triangles.max() >= len(vertices):
        raise ValueError(f"{description} triangle indices are outside the vertex array")
    areas2 = np.linalg.norm(
        np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]],
                 vertices[triangles[:, 2]] - vertices[triangles[:, 0]]),
        axis=1,
    )
    if not np.isfinite(areas2).all() or not np.any(areas2 > 1e-12):
        raise ValueError(f"{description} has no usable nondegenerate triangles")
    return np.ascontiguousarray(vertices), np.ascontiguousarray(triangles)


def _load_export_mesh(export_dir: Path, entry: dict) -> tuple[np.ndarray, np.ndarray]:
    object_id = entry["id"]
    filename = entry.get("file")
    if not isinstance(filename, str) or not filename:
        raise ValueError(f"Slicer object {object_id!r} has no mesh file")
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Slicer object {object_id!r} has an unsafe mesh path: {filename!r}")
    export_root = export_dir.resolve()
    mesh_path = (export_root / relative).resolve()
    try:
        mesh_path.relative_to(export_root)
    except ValueError as exc:
        raise ValueError(f"Slicer object {object_id!r} mesh path escapes the export directory") from exc

    try:
        payload_bytes = mesh_path.read_bytes()
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        expected_hash = entry.get("sha256")
        if not isinstance(expected_hash, str) or expected_hash.lower() != payload_hash:
            raise ValueError(f"Slicer object {object_id!r} NPZ sha256 is missing or does not match its manifest")
        with np.load(io.BytesIO(payload_bytes), allow_pickle=False) as payload:
            if not {"vertices", "triangles"}.issubset(payload.files):
                raise ValueError(f"Slicer object {object_id!r} NPZ needs vertices and triangles arrays")
            vertices, triangles = _mesh_arrays(
                payload["vertices"], payload["triangles"], f"Slicer object {object_id!r}"
            )
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Slicer object"):
            raise
        raise ValueError(f"cannot read Slicer object {object_id!r} mesh at {mesh_path}: {exc}") from exc
    if (not isinstance(entry.get("vertices"), int) or isinstance(entry.get("vertices"), bool)
            or not isinstance(entry.get("triangles"), int) or isinstance(entry.get("triangles"), bool)
            or entry["vertices"] != len(vertices) or entry["triangles"] != len(triangles)):
        raise ValueError(f"Slicer object {object_id!r} vertex/triangle counts do not match its manifest")
    return vertices, triangles


def _moveit_mesh(record: dict) -> tuple[np.ndarray, np.ndarray]:
    object_id = record.get("id", "<missing id>")
    frame_id = record.get("frame_id")
    if not isinstance(frame_id, str) or frame_id.lstrip("/") != FRAME:
        raise ValueError(f"MoveIt object {object_id!r} has unsupported frame_id {frame_id!r}; expected {FRAME}")
    primitives = record.get("primitives", [])
    if not isinstance(primitives, list):
        raise ValueError(f"MoveIt object {object_id!r} primitives field is malformed")
    if primitives:
        raise ValueError(f"MoveIt object {object_id!r} contains unsupported primitives")
    planes = record.get("planes", 0)
    if isinstance(planes, list):
        has_planes = len(planes) > 0
    elif isinstance(planes, (int, np.integer)) and not isinstance(planes, bool):
        if planes < 0:
            raise ValueError(f"MoveIt object {object_id!r} planes field is malformed")
        has_planes = planes > 0
    else:
        raise ValueError(f"MoveIt object {object_id!r} planes field is malformed")
    if has_planes:
        raise ValueError(f"MoveIt object {object_id!r} contains unsupported planes")

    meshes = record.get("meshes")
    if not isinstance(meshes, list) or not meshes:
        raise ValueError(f"MoveIt object {object_id!r} has no usable mesh")
    _identity_and_pose_matrix(record.get("pose"), f"MoveIt object {object_id!r} pose")

    vertex_parts = []
    triangle_parts = []
    offset = 0
    for part_index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise ValueError(f"MoveIt object {object_id!r} mesh part {part_index} is malformed")
        _identity_and_pose_matrix(mesh.get("pose"), f"MoveIt object {object_id!r} mesh pose")
        vertices, triangles = _mesh_arrays(
            mesh.get("vertices"), mesh.get("triangles"),
            f"MoveIt object {object_id!r} mesh part {part_index}",
        )
        placed, placed_triangles = scene_dump.object_mesh_in_frame(record, part_index)
        placed, placed_triangles = _mesh_arrays(
            placed, placed_triangles, f"MoveIt object {object_id!r} placed mesh part {part_index}"
        )
        if len(placed) != len(vertices) or not np.array_equal(placed_triangles, triangles):
            raise ValueError(f"MoveIt object {object_id!r} mesh placement changed its topology")
        vertex_parts.append(placed)
        triangle_parts.append(triangles + offset)
        offset += len(vertices)

    vertices_mm = np.vstack(vertex_parts) * 1000.0
    triangles = np.vstack(triangle_parts)
    return _mesh_arrays(vertices_mm, triangles, f"MoveIt object {object_id!r} combined mesh")


def _sample_points(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    centroids = vertices[triangles].mean(axis=1)
    samples = np.vstack((vertices, centroids))
    if not np.isfinite(samples).all():
        raise ValueError("surface samples contain nonfinite values")
    return np.ascontiguousarray(samples, dtype=np.float64)


def _directed_distances(samples: np.ndarray, target_vertices: np.ndarray,
                        target_triangles: np.ndarray) -> np.ndarray:
    # Exact point-to-triangle distances. The former vtkDistancePolyDataFilter path
    # (vtkCellLocator.FindClosestPoint) returned wrong finite distances on zero-area
    # faces, failing 12 of 34 objects whose meshes matched to about 1e-5 mm.
    values = frame_audit.nearest_surface_distance(samples, target_vertices, target_triangles)
    if values.shape != (len(samples),) or not np.isfinite(values).all():
        raise ValueError("surface distances have an invalid shape or nonfinite values")
    return values


def _distance_summary(slicer_vertices, slicer_triangles, moveit_vertices, moveit_triangles):
    slicer_samples = _sample_points(slicer_vertices, slicer_triangles)
    moveit_samples = _sample_points(moveit_vertices, moveit_triangles)
    slicer_to_moveit = _directed_distances(slicer_samples, moveit_vertices, moveit_triangles)
    moveit_to_slicer = _directed_distances(moveit_samples, slicer_vertices, slicer_triangles)
    combined = np.concatenate((slicer_to_moveit, moveit_to_slicer))
    if not np.isfinite(combined).all():
        raise ValueError("two-way surface distances contain nonfinite values")

    def summary(values):
        return {
            "samples": int(len(values)),
            "p95_mm": float(np.percentile(values, 95)),
            "max_mm": float(values.max()),
        }

    return {
        "sample_method": "vertices plus triangle centroids; discrete samples, not a continuous-surface proof",
        "slicer_to_moveit": summary(slicer_to_moveit),
        "moveit_to_slicer": summary(moveit_to_slicer),
        "two_way_p95_mm": float(np.percentile(combined, 95)),
        "sampled_hausdorff_mm": float(max(slicer_to_moveit.max(), moveit_to_slicer.max())),
    }


def _object_comparison(slicer_vertices, slicer_triangles, moveit_vertices, moveit_triangles):
    slicer_bounds = np.stack((slicer_vertices.min(axis=0), slicer_vertices.max(axis=0)))
    moveit_bounds = np.stack((moveit_vertices.min(axis=0), moveit_vertices.max(axis=0)))
    bounds_delta = np.abs(slicer_bounds - moveit_bounds)
    slicer_centroid = slicer_vertices.mean(axis=0)
    moveit_centroid = moveit_vertices.mean(axis=0)
    distances = _distance_summary(slicer_vertices, slicer_triangles, moveit_vertices, moveit_triangles)
    return {
        "vertex_count": {"slicer": int(len(slicer_vertices)), "moveit": int(len(moveit_vertices)),
                         "match": len(slicer_vertices) == len(moveit_vertices)},
        "triangle_count": {"slicer": int(len(slicer_triangles)), "moveit": int(len(moveit_triangles)),
                           "match": len(slicer_triangles) == len(moveit_triangles)},
        "bounds_mm": {
            "slicer_min": slicer_bounds[0].tolist(), "slicer_max": slicer_bounds[1].tolist(),
            "moveit_min": moveit_bounds[0].tolist(), "moveit_max": moveit_bounds[1].tolist(),
            "delta_max_mm": float(bounds_delta.max()),
        },
        "centroid_mm": {
            "slicer": slicer_centroid.tolist(), "moveit": moveit_centroid.tolist(),
            "delta_vector_mm": (slicer_centroid - moveit_centroid).tolist(),
            "delta_mm": float(np.linalg.norm(slicer_centroid - moveit_centroid)),
        },
        **distances,
    }


def _entries_by_id(entries, description: str) -> dict:
    if not isinstance(entries, list):
        raise ValueError(f"{description} must be a list")
    result = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{description}[{index}] must be an object")
        object_id = entry.get("id")
        if not isinstance(object_id, str) or not object_id:
            raise ValueError(f"{description}[{index}] has no nonempty string id")
        if object_id in result:
            raise ValueError(f"{description} contains duplicate object id {object_id!r}")
        result[object_id] = entry
    return result


def analyse_scene(dump_dir, slicer_export_dir) -> dict:
    """Compare every MoveIt object with its base_link/mm Slicer export.

    Missing/extra IDs and numerical mismatches are returned as ``status=FAIL``.
    Unsupported geometry, malformed files, or invalid arrays raise ValueError.
    """
    dump_dir = Path(dump_dir)
    slicer_export_dir = Path(slicer_export_dir)
    moveit_entries = _entries_by_id(
        _read_json(dump_dir / "world-objects.json", "MoveIt world objects"),
        "MoveIt world objects",
    )
    manifest = _read_json(slicer_export_dir / "manifest.json", "Slicer export manifest")
    if not isinstance(manifest, dict):
        raise ValueError("Slicer export manifest must be an object")
    if str(manifest.get("schema_version")) != "1.0":
        raise ValueError(f"unsupported Slicer export schema_version {manifest.get('schema_version')!r}")
    if manifest.get("coordinate_frame") != FRAME or manifest.get("units") != UNITS:
        raise ValueError("Slicer export must declare coordinate_frame='base_link' and units='mm'")
    if manifest.get("status") != "PASS":
        raise ValueError(f"Slicer export manifest status is {manifest.get('status')!r}; refusing incomplete export")
    slicer_entries = _entries_by_id(manifest.get("objects"), "Slicer export objects")

    report = {
        "status": "PASS",
        "coordinate_frame": FRAME,
        "units": UNITS,
        "hausdorff_limit_mm": MAX_HAUSDORFF_MM,
        "surface_metric": "sampled two-way distance at vertices and triangle centroids",
        "objects": {},
        "failures": [],
    }
    if not moveit_entries and not slicer_entries:
        report["failures"].append({"reason": "both scene exports contain zero objects"})

    missing = sorted(set(moveit_entries) - set(slicer_entries))
    extra = sorted(set(slicer_entries) - set(moveit_entries))
    if missing:
        report["failures"].append({"reason": "MoveIt objects missing from Slicer export", "object_ids": missing})
    if extra:
        report["failures"].append({"reason": "Slicer export contains extra objects", "object_ids": extra})

    for object_id in sorted(set(moveit_entries) & set(slicer_entries)):
        moveit_record = moveit_entries[object_id]
        slicer_record = slicer_entries[object_id]
        if slicer_record.get("status") != "PASS":
            raise ValueError(
                f"Slicer export object {object_id!r} status is {slicer_record.get('status')!r}; refusing incomplete object"
            )
        source_id = slicer_record.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"Slicer export object {object_id!r} has no source_id")
        moveit_vertices, moveit_triangles = _moveit_mesh(moveit_record)
        slicer_vertices, slicer_triangles = _load_export_mesh(slicer_export_dir, slicer_record)
        comparison = _object_comparison(
            slicer_vertices, slicer_triangles, moveit_vertices, moveit_triangles
        )
        reasons = []
        if not comparison["vertex_count"]["match"]:
            reasons.append("vertex counts differ")
        if not comparison["triangle_count"]["match"]:
            reasons.append("triangle counts differ")
        if comparison["sampled_hausdorff_mm"] > MAX_HAUSDORFF_MM:
            reasons.append(
                f"sampled Hausdorff {comparison['sampled_hausdorff_mm']:.6g} mm exceeds {MAX_HAUSDORFF_MM:.6g} mm"
            )
        comparison.update({"source_id": source_id, "status": "FAIL" if reasons else "PASS", "reasons": reasons})
        report["objects"][object_id] = comparison
        if reasons:
            report["failures"].append({"object_id": object_id, "reasons": reasons})

    if report["failures"]:
        report["status"] = "FAIL"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump", required=True, type=Path, help="moveit_scene_dump output directory")
    parser.add_argument("--slicer", required=True, type=Path, help="Slicer base_link/mm export directory")
    parser.add_argument("--out", required=True, type=Path, help="JSON report path")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"refusing to overwrite existing report: {args.out}")
    try:
        report = analyse_scene(args.dump, args.slicer)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        report = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "failures": report.get("failures", []),
                      "error": report.get("error")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
