"""Coordinate-system audit for Step 6 (operator request 2026-10-06, S6-LIVE-01).

"extensively diagnose, test, and confirm that there's no mismatch in coordinate
systems, extremely crucial for image guided interventions".

Every frame relationship is recomputed by an independent route and compared:

A. scene      Slicer source geometry -> world RAS -> robot base (computed here)
              vs MoveGroup's world objects (native /get_planning_scene).
B. kinematics TCP pose from (1) a pure-Python URDF FK written here, (2) Slicer's
              KDL FK and (3) MoveIt's FK service, all mapped to world RAS.
C. task       TCP position/axis at PreEntry/Entry/drilling end vs the planned
              Entry/Target points and drill axis.
D. collision  independent signed distance (spindle collision mesh posed by the
              URDF FK vs the template surface) vs MoveIt's validity verdict,
              along the drilling path and beyond the contact boundary.

Read-only: no motion, no scene or policy change. Simulation evidence only.
"""

from __future__ import annotations

import json
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

TOL_BOUNDS_MM = 0.05
TOL_FK_MM = 0.01
TOL_AXIS_DEG = 0.01
TOL_TASK_MM = 0.25  # existing endpoint tolerance
TOL_TASK_AXIS_DEG = 0.5


# ---------------------------------------------------------------- pure helpers
def _rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _origin(element):
    m = np.eye(4)
    if element is None:
        return m
    m[:3, :3] = _rpy(*map(float, element.get("rpy", "0 0 0").split()))
    m[:3, 3] = list(map(float, element.get("xyz", "0 0 0").split()))
    return m


def _axis_rotation(axis, angle):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    m = np.eye(4)
    m[:3, :3] = np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * k @ k
    return m


class UrdfFk:
    """Minimal independent URDF forward kinematics (revolute/continuous/prismatic/fixed)."""

    def __init__(self, urdf_text: str):
        root = ET.fromstring(urdf_text)
        self.joints = {j.find("child").get("link"): j for j in root.findall("joint")}
        self.links = {l.get("name"): l for l in root.findall("link")}

    def link_pose_m(self, link: str, q: dict) -> np.ndarray:
        if link not in self.joints:
            return np.eye(4)  # root (base_link)
        joint = self.joints[link]
        pose = self.link_pose_m(joint.find("parent").get("link"), q) @ _origin(joint.find("origin"))
        kind = joint.get("type")
        if kind in ("revolute", "continuous"):
            pose = pose @ _axis_rotation(list(map(float, joint.find("axis").get("xyz").split())), q[joint.get("name")])
        elif kind == "prismatic":
            axis = np.array(list(map(float, joint.find("axis").get("xyz").split())))
            shift = np.eye(4)
            shift[:3, 3] = axis / np.linalg.norm(axis) * q[joint.get("name")]
            pose = pose @ shift
        return pose

    def collision(self, link: str):
        """(origin 4x4, mesh filename, scale xyz) of the link's first collision mesh."""
        element = self.links[link].find("collision")
        mesh = element.find("geometry/mesh")
        scale = list(map(float, (mesh.get("scale") or "1 1 1").split()))
        return _origin(element.find("origin")), mesh.get("filename"), scale


def to_ras_mm(base_world_mm: np.ndarray, pose_m: np.ndarray) -> np.ndarray:
    """Robot base pose (m) -> world RAS (mm) through the locked Base matrix (mm)."""
    scaled = pose_m.copy()
    scaled[:3, 3] *= 1000.0
    return np.asarray(base_world_mm, float) @ scaled


def axis_angles_deg(a: np.ndarray, b: np.ndarray) -> list:
    """Per-axis angle; columns normalised (Base matrix column-norm drift ~1e-9 made a false 0.002 deg)."""
    out = []
    for i in range(3):
        u, v = a[:3, i] / np.linalg.norm(a[:3, i]), b[:3, i] / np.linalg.norm(b[:3, i])
        out.append(math.degrees(math.acos(max(-1.0, min(1.0, float(u @ v))))))
    return out


def bounds_of(points) -> list:
    p = np.asarray(points, float)
    return [float(v) for k in range(3) for v in (p[:, k].min(), p[:, k].max())]


def max_bounds_delta(a, b) -> float:
    return max(abs(float(x) - float(y)) for x, y in zip(a, b))


def read_binary_stl(path) -> np.ndarray:
    return read_binary_stl_mesh(path)[0]


def read_binary_stl_mesh(path) -> tuple:
    """Unique vertices and triangle indices of a binary STL."""
    data = Path(path).read_bytes()
    count = int.from_bytes(data[80:84], "little")
    records = np.frombuffer(data[84:84 + count * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    vertices, inverse = np.unique(records["v"].reshape(-1, 3).astype(float), axis=0, return_inverse=True)
    return vertices, inverse.reshape(-1, 3)


# ---------------------------------------------------------------- exact mesh separation
# S6-AUDIT-D-01 (2026-10-06): vertex sampling is not mesh separation. The minimum
# distance between two non-intersecting triangles is attained at a vertex-face or
# an edge-edge pair, so testing all of them (plus edge-triangle intersection) is exact.
def _closest_point_triangle(p, a, b, c):
    """Closest points on triangles (a, b, c) to points p; all arrays (n, 3) (Ericson 5.1.5)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = 1.0 / (va + vb + vc)
        v_face, w_face = vb * denom, vc * denom
        out = a + ab * v_face[:, None] + ac * w_face[:, None]
        w_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        out = np.where(((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0))[:, None], b + w_bc[:, None] * (c - b), out)
        w_ac = d2 / (d2 - d6)
        out = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[:, None], a + w_ac[:, None] * ac, out)
        out = np.where(((d6 >= 0) & (d5 <= d6))[:, None], c, out)
        v_ab = d1 / (d1 - d3)
        out = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[:, None], a + v_ab[:, None] * ab, out)
    out = np.where(((d3 >= 0) & (d4 <= d3))[:, None], b, out)
    out = np.where(((d1 <= 0) & (d2 <= 0))[:, None], a, out)
    return out


def _segment_segment_distance(p1, q1, p2, q2):
    """Minimum distances between segments p1q1 and p2q2; arrays (n, 3) (Ericson 5.1.9)."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e = np.einsum("ij,ij->i", d1, d1), np.einsum("ij,ij->i", d2, d2)
    f, c = np.einsum("ij,ij->i", d2, r), np.einsum("ij,ij->i", d1, r)
    b = np.einsum("ij,ij->i", d1, d2)
    denom = a * e - b * b
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(denom > 1e-18, np.clip((b * f - c * e) / denom, 0.0, 1.0), 0.0)
        t = np.where(e > 1e-18, (b * s + f) / e, 0.0)
        s = np.where(t < 0.0, np.where(a > 1e-18, np.clip(-c / a, 0.0, 1.0), 0.0), s)
        s = np.where(t > 1.0, np.where(a > 1e-18, np.clip((b - c) / a, 0.0, 1.0), 0.0), s)
    t = np.clip(t, 0.0, 1.0)
    return np.linalg.norm((p1 + d1 * s[:, None]) - (p2 + d2 * t[:, None]), axis=1)


def _segment_hits_triangle(p, q, a, b, c, eps=1e-12):
    """True where segment pq crosses triangle (a, b, c) (Moller-Trumbore, t in [0, 1])."""
    direction = q - p
    e1, e2 = b - a, c - a
    h = np.cross(direction, e2)
    det = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(det) > eps
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = np.where(ok, 1.0 / det, 0.0)
        s = p - a
        u = inv * np.einsum("ij,ij->i", s, h)
        qv = np.cross(s, e1)
        v = inv * np.einsum("ij,ij->i", direction, qv)
        t = inv * np.einsum("ij,ij->i", e2, qv)
    return ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= 1)


def exact_mesh_separation(vertices_a, triangles_a, vertices_b, triangles_b, *, search_mm: float = 3.0,
                          chunk: int = 256) -> dict:
    """Exact minimum distance (mm) between two triangle meshes within ``search_mm``.

    Returns ``distance_mm`` (0.0 when the surfaces intersect), ``intersecting``,
    the closest triangle pair and how many pairs were evaluated. When no triangle
    pair lies within ``search_mm``, ``distance_mm`` is None and the separation is
    at least ``search_mm``. Interpenetration depth is not computed here.
    """
    ta = np.asarray(vertices_a, float)[np.asarray(triangles_a, int)]
    tb = np.asarray(vertices_b, float)[np.asarray(triangles_b, int)]
    lo_a, hi_a = ta.min(1) - search_mm, ta.max(1) + search_mm
    lo_b, hi_b = tb.min(1), tb.max(1)
    keep_a = np.all((lo_a <= hi_b.max(0)) & (hi_a >= lo_b.min(0)), axis=1)
    keep_b = np.all((lo_b <= hi_a.max(0)) & (hi_b >= lo_a.min(0)), axis=1)
    ia, ib = np.nonzero(keep_a)[0], np.nonzero(keep_b)[0]
    best = {"distance_mm": None, "intersecting": False, "intersecting_pairs": 0, "pairs_evaluated": 0,
            "closest_triangles": None, "search_mm": float(search_mm)}
    if not len(ia) or not len(ib):
        return best
    edges = ((0, 1), (1, 2), (2, 0))
    for start in range(0, len(ia), chunk):
        rows = ia[start:start + chunk]
        overlap = np.all((lo_a[rows, None, :] <= hi_b[None, ib, :]) & (hi_a[rows, None, :] >= lo_b[None, ib, :]), axis=2)
        pa, pb = np.nonzero(overlap)
        if not len(pa):
            continue
        i, j = rows[pa], ib[pb]
        A, B = ta[i], tb[j]
        best["pairs_evaluated"] += len(i)
        candidates = []
        for k in range(3):
            candidates.append(np.linalg.norm(A[:, k] - _closest_point_triangle(A[:, k], B[:, 0], B[:, 1], B[:, 2]), axis=1))
            candidates.append(np.linalg.norm(B[:, k] - _closest_point_triangle(B[:, k], A[:, 0], A[:, 1], A[:, 2]), axis=1))
        hits = np.zeros(len(i), bool)
        for s, e in edges:
            for s2, e2 in edges:
                candidates.append(_segment_segment_distance(A[:, s], A[:, e], B[:, s2], B[:, e2]))
            hits |= _segment_hits_triangle(A[:, s], A[:, e], B[:, 0], B[:, 1], B[:, 2])
            hits |= _segment_hits_triangle(B[:, s], B[:, e], A[:, 0], A[:, 1], A[:, 2])
        distance = np.min(np.vstack(candidates), axis=0)
        distance[hits] = 0.0
        best["intersecting_pairs"] += int(hits.sum())
        k = int(np.argmin(distance))
        if best["distance_mm"] is None or float(distance[k]) < best["distance_mm"]:
            best["distance_mm"] = float(distance[k])
            best["closest_triangles"] = [int(i[k]), int(j[k])]
    best["intersecting"] = best["intersecting_pairs"] > 0
    if best["distance_mm"] is not None and best["distance_mm"] > search_mm:
        best["distance_mm"] = None
    return best


def model_world_polydata(model):
    """A model's polydata in world RAS: every parent transform applied (never the raw node data)."""
    import vtk

    poly = vtk.vtkPolyData()
    poly.DeepCopy(model.GetPolyData())
    parent = model.GetParentTransformNode()
    if parent is None:
        return poly
    transform = vtk.vtkGeneralTransform()
    parent.GetTransformToWorld(transform)
    hardened = vtk.vtkTransformPolyDataFilter()
    hardened.SetInputData(poly)
    hardened.SetTransform(transform)
    hardened.Update()
    out = vtk.vtkPolyData()
    out.DeepCopy(hardened.GetOutput())
    return out


def polydata_mesh(poly) -> tuple:
    """Vertices (n, 3) and triangles (m, 3) of a vtkPolyData (triangulated first)."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputData(poly)
    triangles.PassVertsOff()
    triangles.PassLinesOff()
    triangles.Update()
    out = triangles.GetOutput()
    vertices = vtk_to_numpy(out.GetPoints().GetData()).astype(float)
    cells = vtk_to_numpy(out.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
    return vertices, cells.astype(int)


def _mesh_polydata(vertices, triangles):
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices, dtype=float), deep=True))
    tris = np.asarray(triangles, dtype=np.int64)
    cells = vtk.vtkCellArray()
    cells.SetCells(len(tris), numpy_to_vtkIdTypeArray(np.c_[np.full(len(tris), 3), tris].ravel(), deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetPolys(cells)
    return poly


def mesh_surface_deviation(vertices_a, triangles_a, vertices_b, triangles_b) -> dict:
    """Mesh-level comparison of two surfaces in one frame (S6-AUDIT-D-01 check A).

    Bounds/centroid deltas plus exact vertex-to-surface distances in both directions
    (closest point on the other mesh's triangles), so a decimated, shifted or
    different mesh with matching bounds is still detected.
    """
    import vtk

    a, b = np.asarray(vertices_a, float), np.asarray(vertices_b, float)

    def one_way(points, vertices, triangles):
        locator = vtk.vtkCellLocator()
        locator.SetDataSet(_mesh_polydata(vertices, triangles))
        locator.BuildLocator()
        closest, cell, sub, d2 = [0.0, 0.0, 0.0], vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)
        out = np.empty(len(points))
        for k, p in enumerate(points):
            locator.FindClosestPoint(p.tolist(), closest, cell, sub, d2)
            out[k] = math.sqrt(float(d2))
        return out

    ab, ba = one_way(a, b, triangles_b), one_way(b, a, triangles_a)

    def stats(d):
        return {"mean": float(d.mean()), "p95": float(np.percentile(d, 95)), "max": float(d.max())}

    return {"vertices": [len(a), len(b)], "triangles": [len(triangles_a), len(triangles_b)],
            "bounds_delta_mm": max_bounds_delta(bounds_of(a), bounds_of(b)),
            "centroid_delta_mm": float(np.linalg.norm(a.mean(0) - b.mean(0))),
            "a_to_b_mm": stats(ab), "b_to_a_mm": stats(ba),
            "hausdorff_mm": float(max(ab.max(), ba.max()))}


def moveit_pairs(reason) -> list:
    """Every ``A<->B`` pair MoveIt named (not substring presence)."""
    from dentobot_workflow.feasibility_advisor import pairs_from_text

    return pairs_from_text(reason)


# ---------------------------------------------------------------- runtime
def run_frame_audit(namespace: dict, out_dir, label: str, *, extrapolate_steps: int = 12) -> dict:
    import slicer
    import vtk
    import DENTOROS2Bridge as B

    widget, panel, facade, logic, node = (namespace[k] for k in ("widget", "panel", "facade", "logic", "parameter_node"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {"label": label, "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checks": {}}

    base_vtk = vtk.vtkMatrix4x4()
    node.robotBaseTransform.GetMatrixTransformToWorld(base_vtk)
    base = np.array([[base_vtk.GetElement(r, c) for c in range(4)] for r in range(4)])
    base_inv = np.linalg.inv(base)
    urdf_path, package_root = logic.robotDescriptionPaths()
    fk = UrdfFk(Path(urdf_path).read_text(encoding="utf-8"))
    report["base_world_mm"] = base.tolist()
    report["urdf"] = str(urdf_path)

    # ---- A. scene -------------------------------------------------------
    ok, message, objects = B.read_moveit_world_object_bounds()
    moveit = {o["id"]: o for o in objects} if ok else {}
    audit = logic.collisionSceneAuditRecord(node)
    jaw = getattr(node, "step6CaseJawTransform", None)
    jaw_m = None
    if jaw is not None:
        jm = vtk.vtkMatrix4x4()
        jaw.GetMatrixTransformToWorld(jm)
        jaw_m = np.array([[jm.GetElement(r, c) for c in range(4)] for r in range(4)])
    scene_rows = []
    for record in audit.object_records:
        object_id = str(record["outgoing_collision_object_id"])
        source = str(record.get("source_id") or "")
        points = None
        route = ""
        if source.startswith("vtkMRMLModelNode"):
            model = slicer.mrmlScene.GetNodeByID(source)
            poly = vtk.vtkPolyData()
            poly.DeepCopy(model.GetPolyData())
            if model.GetParentTransformNode() is not None:
                t = vtk.vtkGeneralTransform()
                model.GetParentTransformNode().GetTransformToWorld(t)
                f = vtk.vtkTransformPolyDataFilter()
                f.SetInputData(poly)
                f.SetTransform(t)
                f.Update()
                poly = f.GetOutput()
            points = np.array([poly.GetPoint(i) for i in range(poly.GetNumberOfPoints())])
            route = "model node -> world"
        elif ":anatomy:" in source or ":target:" in source:
            segment_id = source.split(":", 2)[2]
            seg = slicer.mrmlScene.GetNodeByID(source.split(":", 1)[0])
            if seg is not None:
                seg.CreateClosedSurfaceRepresentation()
            poly = vtk.vtkPolyData()
            if seg is not None and seg.GetClosedSurfaceInternalRepresentation(segment_id) is not None:
                poly.DeepCopy(seg.GetClosedSurfaceInternalRepresentation(segment_id))
                t = vtk.vtkGeneralTransform()
                if seg.GetParentTransformNode() is not None:
                    seg.GetParentTransformNode().GetTransformToWorld(t)
                points = np.array([t.TransformPoint(poly.GetPoint(i)) for i in range(poly.GetNumberOfPoints())])
                route = "segment closed surface -> world"
                if int(record.get("jaw_transform_application_count") or 0) > 0 and jaw_m is not None:
                    h = np.c_[points, np.ones(len(points))]
                    points = (jaw_m @ h.T).T[:, :3]
                    route += " -> jaw opening"
        elif ":mouth-barrier:" in source:
            # Generated in world RAS from the canine landmarks/opened jaw; the
            # frame step (world -> base) is still checked independently here.
            # logic.step6MouthBarrier() is read-only (the polydata helper also
            # refreshes the display).
            part_name = source.split(":mouth-barrier:", 1)[1]
            barrier = logic.step6MouthBarrier(node)
            part = next((p for p in (barrier.parts if barrier else ()) if p.name == part_name), None)
            if part is not None:
                points = np.array([[float(v) for v in pt] for pt in part.points_mm])
                route = "barrier part (world RAS, generated)"
        if points is None or not len(points):
            scene_rows.append({"id": object_id, "route": "no independent source (generated geometry)",
                               "status": "SKIP"})
            continue
        h = np.c_[points, np.ones(len(points))]
        independent = bounds_of((base_inv @ h.T).T[:, :3])
        observed = moveit.get(object_id, {}).get("bounds_mm")
        delta = max_bounds_delta(independent, observed) if observed else None
        scene_rows.append({"id": object_id, "route": route + " -> base (inverse Base matrix)",
                           "delta_mm": None if delta is None else round(delta, 4),
                           "status": "PASS" if delta is not None and delta <= TOL_BOUNDS_MM else "FAIL"})
    report["jaw_transform"] = None if jaw is None else jaw.GetName()
    report["checks"]["A_scene"] = {
        "moveit_read": message, "objects": len(objects), "rows": scene_rows,
        "status": "PASS" if ok and all(r["status"] in ("PASS", "SKIP") for r in scene_rows)
        and any(r["status"] == "PASS" for r in scene_rows) else "FAIL",
    }

    # ---- states ---------------------------------------------------------
    home = logic.taskHomeRecord(node)
    states = {"home": dict(zip(home.joint_names, home.joint_positions_si))}
    chain = getattr(facade, "_step6_stage_diagnostic_chain", None) or {}
    stages = chain.get("stages") or {}
    p1 = (stages.get("P1") or {}).get("path") or []
    for i in np.linspace(0, len(p1) - 1, min(10, len(p1))).astype(int) if p1 else []:
        states[f"p1_{i:03d}"] = dict(p1[i])
    for name, phase in (("preentry", "P1"), ("entry", "P2"), ("drilling_end", "P3")):
        end = (stages.get(phase) or {}).get("end")
        if end:
            states[name] = dict(end)
    p3 = list((stages.get("P3") or {}).get("path") or [])

    # ---- B. kinematics + C. task ---------------------------------------
    _logic, _robot, _goal, _err = B._dentobot_native_motion_context(initialize_goal=False, require_goal=False)
    motion = slicer.mrmlScene.GetNodeByID(_logic.getParameterNode().motionControlNodeID)
    tcp = B.ROS2_TOOL_TCP_LINK

    def three_fk(q):
        urdf = to_ras_mm(base, fk.link_pose_m(tcp, q))
        ok_k, _m, kdl = B.compute_tcp_pose_world_ras_mm(q, base_transform=node.robotBaseTransform)
        mv = motion.ComputeMoveItForwardKinematics(B.ROS2_PLANNING_GROUP, list(B.ROS2_JOINT_SI_ORDER),
                                                   B.joint_si_vector(q), tcp, 2.0)
        moveit_world = None
        if mv is not None:
            moveit_world = base @ np.array([[mv.GetElement(r, c) for c in range(4)] for r in range(4)])
        return urdf, (np.array(kdl) if ok_k else None), moveit_world

    fk_rows = []
    poses = {}
    for name, q in states.items():
        urdf, kdl, mv = three_fk(q)
        poses[name] = urdf
        row = {"state": name}
        for other_name, other in (("kdl", kdl), ("moveit", mv)):
            if other is None:
                row[f"urdf_vs_{other_name}"] = "unavailable"
                continue
            row[f"urdf_vs_{other_name}_mm"] = round(float(np.linalg.norm(urdf[:3, 3] - other[:3, 3])), 6)
            row[f"urdf_vs_{other_name}_axis_deg"] = round(max(axis_angles_deg(urdf, other)), 6)
        row["status"] = "PASS" if all(
            row.get(f"urdf_vs_{n}_mm", 1e9) <= TOL_FK_MM and row.get(f"urdf_vs_{n}_axis_deg", 1e9) <= TOL_AXIS_DEG
            for n in ("kdl", "moveit")) else "FAIL"
        fk_rows.append(row)
    report["checks"]["B_kinematics"] = {"tcp_link": tcp, "rows": fk_rows,
                                        "status": "PASS" if fk_rows and all(r["status"] == "PASS" for r in fk_rows) else "FAIL"}

    snapshot = logic.confirmedTaskRecord(node)
    entry = np.array(snapshot.entry_ras_mm, float)
    target = np.array(snapshot.target_ras_mm, float)
    drill_axis = (target - entry) / np.linalg.norm(target - entry)
    task_rows = []
    truncation = getattr(facade, "_drilling_truncation", None) or {}
    effective = np.array(truncation.get("effective_target_ras_mm") or target, float)
    for name, expected in (("entry", entry), ("drilling_end", effective)):
        if name not in poses:
            continue
        p = poses[name]
        z_angle = math.degrees(math.acos(max(-1.0, min(1.0, abs(float(p[:3, 2] @ drill_axis))))))
        task_rows.append({"state": name, "position_error_mm": round(float(np.linalg.norm(p[:3, 3] - expected)), 4),
                          "tcp_z_vs_drill_axis_deg": round(z_angle, 4),
                          "status": "PASS" if np.linalg.norm(p[:3, 3] - expected) <= TOL_TASK_MM and z_angle <= TOL_TASK_AXIS_DEG else "FAIL"})
    if "preentry" in poses:
        p = poses["preentry"]
        off = p[:3, 3] - entry
        lateral = float(np.linalg.norm(off - (off @ drill_axis) * drill_axis))
        task_rows.append({"state": "preentry", "on_axis_lateral_mm": round(lateral, 4),
                          "standoff_mm": round(float(-(off @ drill_axis)), 4),
                          "status": "PASS" if lateral <= TOL_TASK_MM else "FAIL"})
    report["checks"]["C_task"] = {"rows": task_rows,
                                  "status": "NOT_RUN" if not task_rows else
                                  "PASS" if all(r["status"] == "PASS" for r in task_rows) else "FAIL"}

    # ---- D. collision agreement ----------------------------------------
    # World geometry (parent transforms applied): a lower-jaw template sits under the
    # TMJ mouth-opening transform; its raw polydata is the closed-jaw position
    # (S6-AUDIT-D-01 root cause, 2026-10-07).
    template_world = model_world_polydata(node.finalPrintableTemplateModel)
    implicit = vtk.vtkImplicitPolyDataDistance()
    implicit.SetInput(template_world)
    template_vertices, template_triangles = polydata_mesh(template_world)
    origin, filename, scale = fk.collision("pneumatic_spindle-Copy")
    mesh, mesh_triangles = read_binary_stl_mesh(
        Path(package_root) / filename.split("package://dentobot_description/", 1)[-1])
    # Vertices in mm: to_ras_mm() yields mm translations, so geometry must be in mm too.
    mesh_mm = mesh * np.array(scale) * 1000.0
    sequence = [("p3_%02d" % i, dict(q)) for i, q in enumerate(p3)]
    distinct = []
    for q in p3:
        if not distinct or any(abs(a - b) > 1e-12 for a, b in zip(B.joint_si_vector(q), B.joint_si_vector(distinct[-1]))):
            distinct.append(q)
    if len(distinct) >= 2:
        first, last = np.array(B.joint_si_vector(distinct[0])), np.array(B.joint_si_vector(distinct[-1]))
        step = (last - first) / (len(distinct) - 1)  # mean drilling step, continued past the boundary
        for k in range(1, extrapolate_steps + 1):
            values = last + k * step
            sequence.append(("beyond_%02d" % k, dict(zip(B.ROS2_JOINT_SI_ORDER, values.tolist()))))
    d_rows = []
    for name, q in sequence:
        pose = to_ras_mm(base, fk.link_pose_m("pneumatic_spindle-Copy", q) @ origin)
        pts = (pose @ np.c_[mesh_mm, np.ones(len(mesh_mm))].T).T[:, :3]
        signed = min(implicit.EvaluateFunction(tuple(p)) for p in pts)
        valid, reason, authoritative = B.check_moveit_static_joint_state(q)
        # Exact pair parsing (S6-AUDIT-D-01): the spindle and a template body in one pair.
        pairs = moveit_pairs(reason)
        moveit_template = (not valid) and any(
            any(b.startswith("pneumatic_spindle") for b in pair) and any("Template" in b for b in pair)
            for pair in pairs)
        independent_contact = signed < 0.0
        exact = exact_mesh_separation(pts, mesh_triangles, template_vertices, template_triangles)
        d_rows.append({"state": name, "independent_min_signed_mm": round(float(signed), 4),
                       "independent_method": "spindle vertices -> template surface (sampled)",
                       "exact_distance_mm": None if exact["distance_mm"] is None else round(exact["distance_mm"], 4),
                       "exact_intersecting": exact["intersecting"],
                       "exact_lower_bound_mm": exact["search_mm"] if exact["distance_mm"] is None else None,
                       "independent_contact": independent_contact, "moveit_spindle_template_contact": moveit_template,
                       "moveit_pairs": pairs, "moveit_valid": bool(valid), "moveit_authoritative": bool(authoritative),
                       "moveit_reason": str(reason)[-120:], "agree": independent_contact == moveit_template
                       or abs(signed) <= 0.05})
    transitions = {
        "independent_first_contact": next((r["state"] for r in d_rows if r["independent_contact"]), None),
        "moveit_first_contact": next((r["state"] for r in d_rows if r["moveit_spindle_template_contact"]), None),
    }
    report["checks"]["D_collision"] = {"pair": "pneumatic_spindle-Copy vs final template", "rows": d_rows,
                                       **transitions,
                                       "status": "NOT_RUN" if not d_rows else
                                       "PASS" if all(r["agree"] for r in d_rows)
                                       and transitions["moveit_first_contact"] is not None else "FAIL"}

    statuses = [c["status"] for c in report["checks"].values()]
    # Missing data (no planned chain) is NOT_RUN, never a coordinate failure.
    report["status"] = ("FAIL" if "FAIL" in statuses else "PASS" if all(s == "PASS" for s in statuses)
                        else "PARTIAL")
    report["duration_sec"] = round(time.monotonic() - started, 1)
    (out / "frame-audit.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report
