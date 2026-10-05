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
    data = Path(path).read_bytes()
    count = int.from_bytes(data[80:84], "little")
    records = np.frombuffer(data[84:84 + count * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return np.unique(records["v"].reshape(-1, 3).astype(float), axis=0)


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
    template = node.finalPrintableTemplateModel
    implicit = vtk.vtkImplicitPolyDataDistance()
    implicit.SetInput(template.GetPolyData())
    origin, filename, scale = fk.collision("pneumatic_spindle-Copy")
    mesh = read_binary_stl(Path(package_root) / filename.split("package://dentobot_description/", 1)[-1])
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
        moveit_template = (not valid) and "Template" in reason and "pneumatic_spindle" in reason
        independent_contact = signed < 0.0
        d_rows.append({"state": name, "independent_min_signed_mm": round(float(signed), 4),
                       "independent_contact": independent_contact, "moveit_spindle_template_contact": moveit_template,
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
