"""Iterative forehead-plane Base placement by IK reachability preflight.

Pure numpy, no Slicer/ROS. Simulation planning aid only: a kinematic pass
means the drill stroke is reachable inside joint limits from the Task Home
seed; it is NOT collision, planner or physical-mount evidence. The connected
check (MoveIt IK with collisions, Home validity, P1 plan) is a separate stage.

Search space (world RAS mm), relative to a reference Base seated on the
virtual forehead plane F (axes x_hat, y_hat in-plane, z_hat = depth/normal):

    candidate = F @ T(u*x + v*y + n*z) @ R(rx, ry, rz) @ F^-1 @ reference

- u, v: in-plane slide, iterated outward from the plane centre (active).
- n:    depth along the plane normal (LOCKED to 0 by default).
- rx, ry, rz: rotation about the forehead axes, pivoting at the reference
        Base origin (LOCKED to 0 by default).

The locked dimensions are fully implemented so a later decision can unlock
them by changing ``ForeheadPlacementSearchConfig`` ranges; with the defaults
they contribute exactly one value (0) and therefore no extra candidates.

The IK solver replicates the native damped-least-squares position+axis solver
(slicer_ros2_module MRML/vtkMRMLROS2RobotNode.cxx): same tolerances, damping,
step caps, bound clamping and 120-iteration budget, so a kinematic PASS
predicts what the native Home-seeded PreEntry check will do.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

POSITION_TOLERANCE_M = 0.00025
AXIS_TOLERANCE_RAD = math.radians(0.5)
NATIVE_MAX_ITERATIONS = 120
DAMPING = 1.0e-3
PRISMATIC_STEP_M = 0.002
REVOLUTE_STEP_RAD = 0.10
ROOT_LINK = "base_link"
TIP_LINK = "dentobot_drill_tcp"


# --------------------------------------------------------------------------
# Kinematic model (URDF chain + native-identical DLS position/axis IK)
# --------------------------------------------------------------------------

def rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def axis_angle_matrix(axis: np.ndarray, angle: float) -> np.ndarray:
    x, y, z = axis
    c, s, v = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    return np.array([
        [x * x * v + c, x * y * v - z * s, x * z * v + y * s],
        [y * x * v + z * s, y * y * v + c, y * z * v - x * s],
        [z * x * v - y * s, z * y * v + x * s, z * z * v + c],
    ])


def homogeneous(rotation: np.ndarray, translation) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix


@dataclass(frozen=True)
class Joint:
    name: str
    kind: str
    origin: np.ndarray
    axis: np.ndarray
    lower: float
    upper: float


class Chain:
    """Serial chain from ``root`` to ``tip`` parsed from a URDF."""

    def __init__(self, joints: list[Joint]):
        self.joints = joints
        self.active = [j for j in joints if j.kind in ("revolute", "prismatic", "continuous")]
        self.names = [j.name for j in self.active]

    @classmethod
    def from_urdf(cls, path, root: str = ROOT_LINK, tip: str = TIP_LINK) -> "Chain":
        robot = ET.parse(str(path)).getroot()
        by_child = {}
        for element in robot.findall("joint"):
            child = element.find("child").get("link")
            parent = element.find("parent").get("link")
            origin = element.find("origin")
            xyz = [float(v) for v in (origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split()]
            rpy = [float(v) for v in (origin.get("rpy", "0 0 0") if origin is not None else "0 0 0").split()]
            axis_element = element.find("axis")
            axis = (np.array([float(v) for v in axis_element.get("xyz").split()])
                    if axis_element is not None else np.array([0.0, 0.0, 1.0]))
            axis = axis / np.linalg.norm(axis)
            limit = element.find("limit")
            kind = element.get("type")
            bounded = limit is not None and kind != "continuous"
            lower = float(limit.get("lower", "-inf")) if bounded else -math.inf
            upper = float(limit.get("upper", "inf")) if bounded else math.inf
            by_child[child] = (parent, Joint(element.get("name"), kind,
                                             homogeneous(rpy_matrix(*rpy), xyz), axis, lower, upper))
        joints, link = [], tip
        while link != root:
            if link not in by_child:
                raise ValueError(f"URDF has no joint chain from {root} to {tip}")
            parent, joint = by_child[link]
            joints.append(joint)
            link = parent
        return cls(list(reversed(joints)))

    def bounds(self, relax: frozenset[str] = frozenset()) -> tuple[np.ndarray, np.ndarray]:
        lower = np.array([-math.inf if j.name in relax else j.lower for j in self.active])
        upper = np.array([math.inf if j.name in relax else j.upper for j in self.active])
        return lower, upper

    def forward(self, q: np.ndarray):
        """Return tip transform (base frame, metres) and active-joint frames."""
        transform = np.eye(4)
        frames = []
        index = 0
        for joint in self.joints:
            transform = transform @ joint.origin
            if joint in self.active:
                frames.append((transform[:3, :3] @ joint.axis, transform[:3, 3].copy(), joint.kind))
                if joint.kind == "prismatic":
                    motion = homogeneous(np.eye(3), joint.axis * q[index])
                else:
                    motion = homogeneous(axis_angle_matrix(joint.axis, q[index]), [0, 0, 0])
                transform = transform @ motion
                index += 1
        return transform, frames

    def jacobian(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        tip, frames = self.forward(q)
        position = tip[:3, 3]
        jac = np.zeros((6, len(self.active)))
        for column, (axis, origin, kind) in enumerate(frames):
            if kind == "prismatic":
                jac[:3, column] = axis
            else:
                jac[:3, column] = np.cross(axis, position - origin)
                jac[3:, column] = axis
        return tip, jac


def _clamp(chain: Chain, q: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    q = np.minimum(np.maximum(q, lower), upper)
    for index, joint in enumerate(chain.active):
        if joint.kind == "continuous" and math.isinf(lower[index]):
            q[index] = math.atan2(math.sin(q[index]), math.cos(q[index]))
    return q


def residuals(chain: Chain, q, target_position, target_axis) -> tuple[float, float]:
    tip, _ = chain.forward(np.asarray(q, dtype=float))
    axis = tip[:3, 2] / np.linalg.norm(tip[:3, 2])
    return (float(np.linalg.norm(target_position - tip[:3, 3])),
            float(math.acos(max(-1.0, min(1.0, float(axis @ target_axis))))))


def solve(chain: Chain, seed, target_position, target_axis, *,
          iterations: int = NATIVE_MAX_ITERATIONS, relax: frozenset[str] = frozenset()) -> dict:
    """Native-identical DLS position+axis solve (axial roll free)."""
    lower, upper = chain.bounds(relax)
    q = _clamp(chain, np.array(seed, dtype=float), lower, upper)
    projector = np.eye(3) - np.outer(target_axis, target_axis)
    best = {"score": math.inf}
    termination = "iteration_limit"
    count = 0
    for iteration in range(iterations):
        count = iteration + 1
        tip, jac = chain.jacobian(q)
        axis = tip[:3, 2] / np.linalg.norm(tip[:3, 2])
        position_error = target_position - tip[:3, 3]
        p_err = float(np.linalg.norm(position_error))
        a_err = float(math.acos(max(-1.0, min(1.0, float(axis @ target_axis)))))
        score = (p_err / POSITION_TOLERANCE_M) ** 2 + (a_err / AXIS_TOLERANCE_RAD) ** 2
        if score < best["score"]:
            best = {"score": score, "q": q.copy(), "position_m": p_err, "axis_rad": a_err}
        if p_err <= POSITION_TOLERANCE_M and a_err <= AXIS_TOLERANCE_RAD:
            termination = "converged"
            break
        task_jac = np.vstack([jac[:3] / POSITION_TOLERANCE_M, projector @ jac[3:] / AXIS_TOLERANCE_RAD])
        task_err = np.concatenate([position_error / POSITION_TOLERANCE_M,
                                   np.cross(axis, target_axis) / AXIS_TOLERANCE_RAD])
        normal = task_jac.T @ task_jac + DAMPING ** 2 * np.eye(len(q))
        delta = np.linalg.solve(normal, task_jac.T @ task_err)
        if not np.all(np.isfinite(delta)):
            termination = "nonfinite_step"
            break
        scale = 1.0
        for index, joint in enumerate(chain.active):
            limit = PRISMATIC_STEP_M if joint.kind == "prismatic" else REVOLUTE_STEP_RAD
            if abs(delta[index]) > limit:
                scale = min(scale, limit / abs(delta[index]))
        if np.linalg.norm(delta) * scale < 1.0e-12:
            termination = "stalled"
            break
        q = _clamp(chain, q + scale * delta, lower, upper)
    return {
        "termination": termination,
        "iterations": count,
        "q": [float(v) for v in best["q"]],
        "position_residual_mm": best["position_m"] * 1000.0,
        "axis_residual_deg": math.degrees(best["axis_rad"]),
    }


def joint_margins(chain: Chain, q) -> dict[str, float]:
    """Distance to the nearer mechanical limit (mm for sliders, deg for revolute)."""
    out = {}
    for joint, value in zip(chain.active, q):
        if joint.kind == "continuous":
            continue
        scale = 1000.0 if joint.kind == "prismatic" else 180.0 / math.pi
        out[joint.name] = min(value - joint.lower, joint.upper - value) * scale
    return out


# --------------------------------------------------------------------------
# Forehead-plane candidate generation
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ForeheadPlacementSearchConfig:
    # Active: in-plane slide around the forehead-plane centre (mm).
    in_plane_range_mm: float = 30.0
    coarse_step_mm: float = 5.0
    refine_step_mm: float = 1.0
    refine_radius_mm: float = 4.0
    # LOCKED: depth along the plane normal. Unlock later by e.g. (-10.0, 10.0, 5.0)
    # as (min, max, step); (0.0, 0.0, 0.0) means the single value 0.
    depth_range_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # LOCKED: rotations about forehead x/y/z axes (deg), pivot = reference Base
    # origin. Unlock later by e.g. (-10.0, 10.0, 5.0) per axis.
    rotation_x_range_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_y_range_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_z_range_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Drill stroke sampling and acceptance thresholds.
    stroke_station_step_mm: float = 2.0
    minimum_slider_margin_mm: float = 1.0
    minimum_revolute_margin_deg: float = 1.0
    top_candidates: int = 10


def _values(spec: tuple[float, float, float]) -> list[float]:
    low, high, step = (float(v) for v in spec)
    if step <= 0.0 or high <= low:
        return [0.0] if low <= 0.0 <= high else [low]
    count = int(math.floor((high - low) / step + 1e-9)) + 1
    return [low + i * step for i in range(count)]


def _grid(radius: float, step: float, centre=(0.0, 0.0)) -> list[tuple[float, float]]:
    offsets = np.arange(-radius, radius + 1e-9, step)
    points = [(centre[0] + a, centre[1] + b) for a in offsets for b in offsets]
    # Iterate outward from the centre: nearest candidates are evaluated first.
    return sorted(points, key=lambda p: (math.hypot(p[0], p[1]), p[0], p[1]))


def _rotation_about_axes_deg(frame: np.ndarray, rx: float, ry: float, rz: float) -> np.ndarray:
    rotation = np.eye(3)
    for axis, angle in ((frame[:3, 0], rx), (frame[:3, 1], ry), (frame[:3, 2], rz)):
        if angle:
            rotation = axis_angle_matrix(axis / np.linalg.norm(axis), math.radians(angle)) @ rotation
    return rotation


def candidate_base_matrix(forehead_world: np.ndarray, reference_base_world: np.ndarray,
                          u_mm: float, v_mm: float, n_mm: float = 0.0,
                          rx_deg: float = 0.0, ry_deg: float = 0.0, rz_deg: float = 0.0) -> np.ndarray:
    """Reference Base slid in the forehead plane (and, if unlocked, depth/rotation)."""
    frame = np.asarray(forehead_world, dtype=float)
    reference = np.asarray(reference_base_world, dtype=float)
    shift = u_mm * frame[:3, 0] + v_mm * frame[:3, 1] + n_mm * frame[:3, 2]
    out = reference.copy()
    if rx_deg or ry_deg or rz_deg:
        # Locked by default. Rotate about forehead axes around the Base origin.
        rotation = _rotation_about_axes_deg(frame, rx_deg, ry_deg, rz_deg)
        out[:3, :3] = rotation @ reference[:3, :3]
    out[:3, 3] = reference[:3, 3] + shift
    return out


@dataclass
class PlacementTask:
    """Drill stroke in world RAS mm (PreEntry -> Entry -> Target) and Home seed."""

    pre_entry_mm: np.ndarray
    entry_mm: np.ndarray
    target_mm: np.ndarray
    home_q: list[float]
    stations_mm: list[np.ndarray] = field(default_factory=list)

    def axis(self) -> np.ndarray:
        vector = np.asarray(self.target_mm, float) - np.asarray(self.entry_mm, float)
        return vector / np.linalg.norm(vector)


def stroke_stations(task: PlacementTask, step_mm: float) -> list[tuple[str, np.ndarray]]:
    axis = task.axis()
    entry = np.asarray(task.entry_mm, float)
    pre = float(np.linalg.norm(np.asarray(task.pre_entry_mm, float) - entry))
    depth = float(np.linalg.norm(np.asarray(task.target_mm, float) - entry))
    stations = [("pre_entry", entry - axis * pre), ("entry", entry)]
    s = step_mm
    while s < depth - 1e-6:
        stations.append((f"s{s:g}mm", entry + axis * s))
        s += step_mm
    stations.append(("target", np.asarray(task.target_mm, float)))
    return stations


def evaluate_base(chain: Chain, base_world: np.ndarray, task: PlacementTask,
                  config: ForeheadPlacementSearchConfig) -> dict:
    """Native-replica reachability of the whole stroke for one Base pose.

    PreEntry is seeded from Task Home (as the native PreEntry check is); each
    deeper station is seeded from the previous solution, mirroring the
    continuous P2/P3 insertion.
    """
    inverse = np.linalg.inv(np.asarray(base_world, float))
    axis_base = inverse[:3, :3] @ task.axis()
    seed = list(task.home_q)
    pre_entry_q = None
    stations = []
    worst_slider, worst_revolute = math.inf, math.inf
    reachable = True
    for name, point_world in stroke_stations(task, config.stroke_station_step_mm):
        point_base_m = (inverse @ np.append(point_world, 1.0))[:3] / 1000.0
        result = solve(chain, seed, point_base_m, axis_base)
        margins = joint_margins(chain, result["q"])
        converged = result["termination"] == "converged"
        slider = min((v for k, v in margins.items() if "Slider" in k), default=math.inf)
        revolute = min((v for k, v in margins.items() if "Slider" not in k), default=math.inf)
        stations.append({"station": name, "termination": result["termination"],
                         "position_residual_mm": result["position_residual_mm"],
                         "axis_residual_deg": result["axis_residual_deg"],
                         "minimum_slider_margin_mm": slider, "minimum_revolute_margin_deg": revolute})
        if not converged:
            reachable = False
            break
        worst_slider, worst_revolute = min(worst_slider, slider), min(worst_revolute, revolute)
        if pre_entry_q is None:
            pre_entry_q = list(result["q"])
        seed = result["q"]
    feasible = bool(reachable
                    and worst_slider >= config.minimum_slider_margin_mm
                    and worst_revolute >= config.minimum_revolute_margin_deg)
    return {"reachable": reachable, "feasible": feasible,
            "minimum_slider_margin_mm": worst_slider if reachable else None,
            "minimum_revolute_margin_deg": worst_revolute if reachable else None,
            "first_failed_station": None if reachable else stations[-1]["station"],
            "pre_entry_q": pre_entry_q,
            "stations": stations}


def search_forehead_base_placement(chain: Chain, forehead_world: np.ndarray,
                                   reference_base_world: np.ndarray, task: PlacementTask,
                                   config: ForeheadPlacementSearchConfig | None = None,
                                   progress=None) -> dict:
    """Iterate outward over the forehead plane; return ranked feasible Bases.

    Ranking: feasible first, then smallest in-plane displacement from the
    plane centre (stay closest to the anatomical prior), then larger margins.
    """
    config = config or ForeheadPlacementSearchConfig()
    depths = _values(config.depth_range_mm)
    rotations = [(rx, ry, rz) for rx in _values(config.rotation_x_range_deg)
                 for ry in _values(config.rotation_y_range_deg)
                 for rz in _values(config.rotation_z_range_deg)]
    evaluated: dict[tuple, dict] = {}

    def run(points):
        total = len(points) * len(depths) * len(rotations)
        done = 0
        for u, v in points:
            for n in depths:
                for rx, ry, rz in rotations:
                    key = (round(u, 6), round(v, 6), n, rx, ry, rz)
                    done += 1
                    if key in evaluated:
                        continue
                    matrix = candidate_base_matrix(forehead_world, reference_base_world,
                                                   u, v, n, rx, ry, rz)
                    record = evaluate_base(chain, matrix, task, config)
                    record.update({"u_mm": u, "v_mm": v, "depth_mm": n,
                                   "rotation_deg": [rx, ry, rz],
                                   "displacement_mm": math.sqrt(u * u + v * v + n * n),
                                   "matrix_world_ras_mm": matrix.reshape(-1).tolist()})
                    evaluated[key] = record
                    if progress is not None:
                        progress(done, total)

    run(_grid(config.in_plane_range_mm, config.coarse_step_mm))
    coarse_feasible = [r for r in evaluated.values() if r["feasible"]]
    if coarse_feasible:
        anchor = min(coarse_feasible, key=lambda r: r["displacement_mm"])
        refine = [p for p in _grid(config.refine_radius_mm, config.refine_step_mm,
                                   (anchor["u_mm"], anchor["v_mm"]))
                  if abs(p[0]) <= config.in_plane_range_mm + 1e-9
                  and abs(p[1]) <= config.in_plane_range_mm + 1e-9]
        run(refine)

    records = list(evaluated.values())
    feasible = sorted((r for r in records if r["feasible"]),
                      key=lambda r: (round(r["displacement_mm"], 3),
                                     -(r["minimum_slider_margin_mm"] or 0.0)))
    centre = evaluated.get((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    return {
        "schema": "dentobot.base_placement_search/1",
        "evidence_level": "kinematic_only_native_replica",
        "config": asdict(config),
        "locked_dimensions": {"depth": len(depths) == 1, "orientation": len(rotations) == 1},
        "evaluated": len(records),
        "feasible_count": len(feasible),
        "centre": centre,
        "best": feasible[0] if feasible else None,
        "ranked": feasible[: config.top_candidates],
        "ranked_all": feasible,
        "grid": [{k: r[k] for k in ("u_mm", "v_mm", "depth_mm", "reachable", "feasible",
                                     "first_failed_station", "minimum_slider_margin_mm")}
                 for r in records],
        "verdict": ("feasible_base_found" if feasible else
                    "no_reachable_base_in_locked_search_space"),
    }


DEPTH_FALLBACK_RANGE_MM = (-10.0, 10.0, 5.0)


def search_with_depth_fallback(chain: Chain, forehead_world: np.ndarray,
                               reference_base_world: np.ndarray, task: PlacementTask,
                               config: ForeheadPlacementSearchConfig | None = None,
                               progress=None) -> dict:
    """In-plane search first; only if nothing is feasible, unlock depth +-10 mm.

    Orientation stays locked. The report states whether the fallback ran so a
    depth-shifted Base is never mistaken for an in-plane result.
    """
    from dataclasses import replace

    config = config or ForeheadPlacementSearchConfig()
    report = search_forehead_base_placement(chain, forehead_world, reference_base_world,
                                            task, config, progress)
    report["depth_fallback"] = {"ran": False}
    if report["best"] is not None or len(_values(config.depth_range_mm)) > 1:
        return report
    widened = replace(config, depth_range_mm=DEPTH_FALLBACK_RANGE_MM)
    fallback = search_forehead_base_placement(chain, forehead_world, reference_base_world,
                                              task, widened, progress)
    fallback["depth_fallback"] = {
        "ran": True,
        "depth_range_mm": list(DEPTH_FALLBACK_RANGE_MM),
        "in_plane_evaluated": report["evaluated"],
        "in_plane_verdict": report["verdict"],
    }
    return fallback


def select_path_clear_candidate(report: dict, check, limit: int = 12) -> dict:
    """Prefer the nearest feasible Base whose straight Home->PreEntry path is clear.

    ``check(record) -> dict`` returns at least ``{"clear": bool}`` (see
    ``path_clearance.ToolMeshSweep.straight_path``). Candidates are tried in
    ranking order (nearest first). If none is clear the kinematic best is kept
    and flagged, because a planner may still detour around the obstacle.
    """
    feasible = sorted((r for r in report.get("ranked_all", report.get("ranked", []))),
                      key=lambda r: (round(r["displacement_mm"], 3),
                                     -(r["minimum_slider_margin_mm"] or 0.0)))
    tried = []
    for record in feasible[:limit]:
        result = dict(check(record))
        tried.append({"u_mm": record["u_mm"], "v_mm": record["v_mm"],
                      "depth_mm": record.get("depth_mm", 0.0), **result})
        if result.get("clear"):
            report["path_preflight"] = {"selected": "path_clear", "tried": tried}
            report["best"] = record
            return report
    report["path_preflight"] = {"selected": "kinematic_best_path_blocked" if tried else "not_run",
                                "tried": tried}
    return report
