"""S6-AUDIT-D-01 offline analysis of one live scene dump (2026-10-07).

Inputs (all read-only evidence of one runtime):
* ``moveit_scene_dump.py`` output (world-objects.json, acm.json, scene-dump.json);
* the runner's same-state Slicer export (``<tag>-spindle-world.npz``,
  ``<tag>-template-world.vtp``, ``<tag>-frames.json``).

Answers, for the spindle <-> final template pair at the audited state:
1. is the pair allowed by MoveIt's ACM;
2. does MoveIt's template mesh match the Slicer template (mesh level), or the
   template at the closed-jaw position (lower-jaw opening not applied);
3. exact separation of the URDF spindle mesh from MoveIt's OWN template mesh;
4. MoveIt's verdict for the same state.

    python3 step6_audit_d_compare.py --dump DIR --slicer DIR --tag preentry --out FILE
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import moveit_scene_dump as dump_tools
import step6_frame_audit as frame_audit

MATCH_TOL_MM = 0.05


def base_frame_to_world_mm(base_world_mm, vertices_m) -> np.ndarray:
    """MoveIt base_link vertices (m) -> world RAS (mm) through the locked Base matrix (mm)."""
    h = np.c_[np.asarray(vertices_m, float) * 1000.0, np.ones(len(vertices_m))]
    return (np.asarray(base_world_mm, float) @ h.T).T[:, :3]


def apply_matrix(matrix, vertices) -> np.ndarray:
    h = np.c_[np.asarray(vertices, float), np.ones(len(vertices))]
    return (np.asarray(matrix, float) @ h.T).T[:, :3]


def classify(acm_verdict: dict, as_placed: dict, closed_jaw: dict | None, separation: dict,
             moveit_valid: bool | None) -> dict:
    """One finding from the four measurements (table agreed with the operator 2026-10-07)."""
    def matches(dev):
        return dev is not None and dev["hausdorff_mm"] <= MATCH_TOL_MM

    if acm_verdict.get("allowed"):
        return {"finding": "acm_allows_pair", "detail": f"ACM {acm_verdict['source']} allows spindle<->template"}
    if not matches(as_placed):
        if matches(closed_jaw):
            return {"finding": "moveit_template_at_closed_jaw",
                    "detail": "MoveIt's template matches the Slicer template without the lower-jaw opening"}
        return {"finding": "moveit_template_differs",
                "detail": f"MoveIt vs Slicer template Hausdorff {as_placed['hausdorff_mm']:.3f} mm" if as_placed
                else "no MoveIt template mesh"}
    if not separation.get("intersecting"):
        if moveit_valid:
            return {"finding": "consistent_clear", "detail": "no intersection with MoveIt's template; MoveIt Valid"}
        return {"finding": "moveit_contact_not_reproduced",
                "detail": "MoveIt reports Invalid but the spindle does not reach its template; inspect other pairs"}
    if moveit_valid:
        return {"finding": "checker_misses_intersection",
                "detail": "scene matches, pair not allowed, meshes intersect, MoveIt reports Valid"}
    return {"finding": "consistent", "detail": "MoveIt reports the intersection"}


def analyse(dump_dir: Path, slicer_dir: Path, tag: str) -> dict:
    import vtk

    objects = json.loads((dump_dir / "world-objects.json").read_text(encoding="utf-8"))
    acm = json.loads((dump_dir / "acm.json").read_text(encoding="utf-8"))
    scene = json.loads((dump_dir / "scene-dump.json").read_text(encoding="utf-8"))
    frames = json.loads((slicer_dir / f"{tag}-frames.json").read_text(encoding="utf-8"))
    spindle = np.load(slicer_dir / f"{tag}-spindle-world.npz")
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(str(slicer_dir / f"{tag}-template-world.vtp"))
    reader.Update()
    slicer_vertices, slicer_triangles = frame_audit.polydata_mesh(reader.GetOutput())

    templates = [o for o in objects if "Template" in o["id"]]
    report = {"tag": tag, "template_objects": [o["id"] for o in templates],
              "planning_frame": scene.get("planning_frame"), "link_padding": scene.get("link_padding"),
              "link_scale": scene.get("link_scale"), "parameters": scene.get("parameters"),
              "spindle_has_collision": (scene.get("robot_description") or {}).get("spindle_has_collision"),
              "validity": (scene.get("validity") or {}).get(tag)}
    if len(templates) != 1:
        report["finding"] = {"finding": "template_object_count", "detail": f"{len(templates)} template objects"}
        return report
    template = templates[0]
    report["template_frame_id"] = template["frame_id"]
    if template["frame_id"].lstrip("/") != "base_link" or not template["meshes"]:
        report["finding"] = {"finding": "template_object_unexpected",
                             "detail": f"frame {template['frame_id']!r}, meshes {len(template['meshes'])}"}
        return report
    parts = [dump_tools.object_mesh_in_frame(template, k) for k in range(len(template["meshes"]))]
    offsets = np.cumsum([0] + [len(v) for v, _ in parts[:-1]])
    moveit_vertices = base_frame_to_world_mm(frames["base_world_mm"], np.vstack([v for v, _ in parts]))
    moveit_triangles = np.vstack([t + o for (_, t), o in zip(parts, offsets)])
    acm_verdict = dump_tools.acm_lookup(acm, dump_tools.SPINDLE_LINK, template["id"])
    as_placed = frame_audit.mesh_surface_deviation(moveit_vertices, moveit_triangles, slicer_vertices, slicer_triangles)
    closed_jaw = None
    if frames.get("jaw_owner") == "MovingLower":
        closed = apply_matrix(np.linalg.inv(np.asarray(frames["jaw_world"], float)), slicer_vertices)
        closed_jaw = frame_audit.mesh_surface_deviation(moveit_vertices, moveit_triangles, closed, slicer_triangles)
    separation = frame_audit.exact_mesh_separation(spindle["vertices"], spindle["triangles"],
                                                   moveit_vertices, moveit_triangles)
    validity = report["validity"] or {}
    report.update(acm=acm_verdict, moveit_vs_slicer=as_placed, moveit_vs_slicer_closed_jaw=closed_jaw,
                  spindle_vs_moveit_template=separation,
                  finding=classify(acm_verdict, as_placed, closed_jaw, separation, validity.get("valid")))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump", required=True, type=Path)
    parser.add_argument("--slicer", required=True, type=Path)
    parser.add_argument("--tag", default="preentry")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = analyse(args.dump, args.slicer, args.tag)
    args.out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report.get("finding"), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
