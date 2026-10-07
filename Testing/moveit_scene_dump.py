"""Read-only dump of MoveGroup's live PlanningScene (S6-AUDIT-D-01, 2026-10-07).

Captures what MoveIt actually checks against: every world collision object
(frame, pose, primitives, full mesh vertices/triangles), the AllowedCollisionMatrix
(entries and defaults), link padding/scale, the robot state, the loaded
robot_description identity, and optional /check_state_validity verdicts for
explicit joint states. Never publishes, applies or moves anything.

Run inside the container with ROS sourced (same ROS_DOMAIN_ID as the stack):

    python3 moveit_scene_dump.py --out DIR [--state name=joints.json ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

SPINDLE_LINK = "pneumatic_spindle-Copy"
PLANNING_GROUP = "dentobot_arm"
PARAMETERS = (
    "default_robot_padding",
    "robot_description_planning.default_robot_padding",
    "robot_description_planning.default_robot_scale",
    "robot_description_planning.default_object_padding",
)


# ---------------------------------------------------------------- pure helpers
def acm_lookup(acm: dict, a: str, b: str) -> dict:
    """Effective ACM verdict for one pair, MoveIt precedence: explicit entry, then default entry."""
    names = list(acm.get("entry_names") or ())
    rows = acm.get("entry_values") or ()
    if a in names and b in names:
        value = rows[names.index(a)][names.index(b)]
        return {"allowed": bool(value), "source": "entry"}
    defaults = dict(zip(acm.get("default_entry_names") or (), acm.get("default_entry_values") or ()))
    for name in (a, b):
        if name in defaults:
            return {"allowed": bool(defaults[name]), "source": f"default:{name}"}
    return {"allowed": False, "source": "absent"}


def urdf_collision_summary(urdf_text: str) -> dict:
    """Identity of a robot_description: sha256 and per-link collision geometry."""
    root = ET.fromstring(urdf_text)
    links = {}
    for link in root.findall("link"):
        geometries = []
        for element in link.findall("collision"):
            geometry = element.find("geometry")
            child = geometry[0] if geometry is not None and len(geometry) else None
            if child is not None:
                geometries.append({"type": child.tag, **{k: v for k, v in child.attrib.items()}})
        links[link.get("name")] = geometries
    return {"sha256": hashlib.sha256(urdf_text.encode("utf-8")).hexdigest(), "collision": links,
            "spindle_has_collision": bool(links.get(SPINDLE_LINK))}


def pose_matrix(position, orientation) -> np.ndarray:
    """4x4 from a geometry_msgs Pose given as (x, y, z) and quaternion (x, y, z, w)."""
    x, y, z, w = (float(v) for v in orientation)
    n = x * x + y * y + z * z + w * w
    s = 0.0 if n == 0 else 2.0 / n
    m = np.eye(4)
    m[:3, :3] = [
        [1 - s * (y * y + z * z), s * (x * y - z * w), s * (x * z + y * w)],
        [s * (x * y + z * w), 1 - s * (x * x + z * z), s * (y * z - x * w)],
        [s * (x * z - y * w), s * (y * z + x * w), 1 - s * (x * x + y * y)],
    ]
    m[:3, 3] = [float(v) for v in position]
    return m


def object_mesh_in_frame(record: dict, index: int = 0):
    """Vertices (object header frame, m) and triangles of one dumped mesh: object pose @ mesh pose."""
    mesh = record["meshes"][index]
    pose = np.asarray(record["pose"], float) @ np.asarray(mesh["pose"], float)
    vertices = np.asarray(mesh["vertices"], float)
    placed = (pose @ np.c_[vertices, np.ones(len(vertices))].T).T[:, :3]
    return placed, np.asarray(mesh["triangles"], int)


def byte_int(value) -> int:
    """rclpy maps ``byte`` fields to ``bytes`` of length 1."""
    return value[0] if isinstance(value, (bytes, bytearray)) else int(value)


def contacts_summary(contacts) -> list:
    return [{"a": c["contact_body_1"], "b": c["contact_body_2"], "depth_m": c["depth"]} for c in contacts]


# ---------------------------------------------------------------- message conversion
def _pose(msg) -> list:
    return pose_matrix((msg.position.x, msg.position.y, msg.position.z),
                       (msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w)).tolist()


def world_objects(scene) -> list:
    out = []
    for obj in scene.world.collision_objects:
        meshes = []
        for mesh, pose in zip(obj.meshes, obj.mesh_poses):
            meshes.append({"pose": _pose(pose),
                           "vertices": [[float(v.x), float(v.y), float(v.z)] for v in mesh.vertices],
                           "triangles": [[int(i) for i in t.vertex_indices] for t in mesh.triangles]})
        primitives = [{"type": byte_int(p.type), "dimensions": [float(d) for d in p.dimensions], "pose": _pose(q)}
                      for p, q in zip(obj.primitives, obj.primitive_poses)]
        out.append({"id": obj.id, "frame_id": obj.header.frame_id, "pose": _pose(obj.pose),
                    "operation": byte_int(obj.operation), "meshes": meshes, "primitives": primitives,
                    "planes": len(obj.planes)})
    return out


def acm_dict(acm) -> dict:
    return {"entry_names": list(acm.entry_names),
            "entry_values": [list(map(bool, row.enabled)) for row in acm.entry_values],
            "default_entry_names": list(acm.default_entry_names),
            "default_entry_values": list(map(bool, acm.default_entry_values))}


# ---------------------------------------------------------------- live (rclpy)
def _call(node, client, request, timeout):
    import rclpy

    if not client.wait_for_service(timeout_sec=timeout):
        raise RuntimeError(f"service {client.srv_name} unavailable")
    future = client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
    if future.result() is None:
        raise RuntimeError(f"service {client.srv_name} returned nothing")
    return future.result()


def _parameters(node, names, timeout) -> dict:
    from rcl_interfaces.srv import GetParameters

    client = node.create_client(GetParameters, "/move_group/get_parameters")
    request = GetParameters.Request()
    request.names = list(names)
    try:
        values = _call(node, client, request, timeout).values
    except RuntimeError as exc:
        return {name: f"unavailable: {exc}" for name in names}
    out = {}
    for name, value in zip(names, values):
        out[name] = {1: value.bool_value, 2: value.integer_value, 3: value.double_value,
                     4: value.string_value}.get(value.type, None)  # 0 = PARAMETER_NOT_SET
    return out


def dump(out_dir: Path, states: dict, timeout: float = 10.0) -> dict:
    import rclpy
    from moveit_msgs.msg import PlanningSceneComponents, RobotState
    from moveit_msgs.srv import GetPlanningScene, GetStateValidity

    out_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = rclpy.create_node("dentobot_scene_dump_readonly")
    try:
        request = GetPlanningScene.Request()
        c = PlanningSceneComponents
        request.components.components = (
            c.SCENE_SETTINGS | c.ROBOT_STATE | c.ROBOT_STATE_ATTACHED_OBJECTS | c.WORLD_OBJECT_NAMES
            | c.WORLD_OBJECT_GEOMETRY | c.OCTOMAP | c.TRANSFORMS | c.ALLOWED_COLLISION_MATRIX
            | c.LINK_PADDING_AND_SCALING | c.OBJECT_COLORS)
        scene = _call(node, node.create_client(GetPlanningScene, "/get_planning_scene"), request, timeout).scene
        objects = world_objects(scene)
        acm = acm_dict(scene.allowed_collision_matrix)
        params = _parameters(node, (*PARAMETERS, "robot_description", "robot_description_semantic"), timeout)
        urdf_text = params.pop("robot_description", None)
        srdf_text = params.pop("robot_description_semantic", None)
        report = {
            "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scene_name": scene.name, "planning_frame": scene.fixed_frame_transforms[0].header.frame_id
            if scene.fixed_frame_transforms else None,
            "robot_model_name": scene.robot_model_name, "is_diff": bool(scene.is_diff),
            "link_padding": {p.link_name: p.padding for p in scene.link_padding},
            "link_scale": {s.link_name: s.scale for s in scene.link_scale},
            "fixed_frame_transforms": [t.child_frame_id for t in scene.fixed_frame_transforms],
            "octomap_points": len(scene.world.octomap.octomap.data),
            "attached_objects": [a.object.id for a in scene.robot_state.attached_collision_objects],
            "robot_state": dict(zip(scene.robot_state.joint_state.name, scene.robot_state.joint_state.position)),
            "parameters": params,
            "robot_description": urdf_collision_summary(urdf_text) if isinstance(urdf_text, str) and urdf_text
            else {"status": "unavailable"},
            "robot_description_semantic_sha256": hashlib.sha256(srdf_text.encode()).hexdigest()
            if isinstance(srdf_text, str) and srdf_text else None,
            "objects": [{"id": o["id"], "frame_id": o["frame_id"], "meshes": len(o["meshes"]),
                         "vertices": sum(len(m["vertices"]) for m in o["meshes"]),
                         "triangles": sum(len(m["triangles"]) for m in o["meshes"]),
                         "primitives": len(o["primitives"]),
                         "acm_vs_spindle": acm_lookup(acm, SPINDLE_LINK, o["id"])} for o in objects],
            "acm_spindle_row": {name: acm_lookup(acm, SPINDLE_LINK, name) for name in acm["entry_names"]},
            "validity": {},
        }
        (out_dir / "acm.json").write_text(json.dumps(acm), encoding="utf-8")
        (out_dir / "world-objects.json").write_text(json.dumps(objects), encoding="utf-8")
        validity = node.create_client(GetStateValidity, "/check_state_validity")
        for label, joints in states.items():
            check = GetStateValidity.Request()
            check.group_name = PLANNING_GROUP
            check.robot_state = RobotState()
            check.robot_state.is_diff = True
            check.robot_state.joint_state.name = list(joints)
            check.robot_state.joint_state.position = [float(v) for v in joints.values()]
            response = _call(node, validity, check, timeout)
            report["validity"][label] = {
                "joints_si": joints, "valid": bool(response.valid),
                "contacts": contacts_summary([{"contact_body_1": x.contact_body_1, "contact_body_2": x.contact_body_2,
                                               "depth": x.depth} for x in response.contacts])}
        (out_dir / "scene-dump.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        return report
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--state", action="append", default=[], help="label=path/to/joints_si.json")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    states = {}
    for item in args.state:
        label, path = item.split("=", 1)
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        states[label] = payload.get("joints_si", payload)
    report = dump(args.out, states, args.timeout)
    print(json.dumps({k: report[k] for k in ("objects", "link_padding", "parameters", "validity")}, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
