#!/usr/bin/env python3
"""Offline Step 6 PreEntry reachability attribution (host only, numpy).

Separates solver budget, joint-limit reach and base placement for the
position+axis (roll-free) TCP task recorded by a headed-run evidence JSON.
It replicates the native damped-least-squares solver in
``slicer_ros2_module/MRML/vtkMRMLROS2RobotNode.cxx`` and never contacts
Slicer, ROS or MoveIt. Collision is NOT evaluated here; a kinematic pass only
means the pose is reachable inside joint limits.
"""

from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np

POSITION_TOLERANCE_M = 0.00025
AXIS_TOLERANCE_RAD = math.radians(0.5)
NATIVE_MAX_ITERATIONS = 120
DAMPING = 1.0e-3
PRISMATIC_STEP_M = 0.002
REVOLUTE_STEP_RAD = 0.10
TIP_LINK = "dentobot_drill_tcp"
ROOT_LINK = "base_link"
J2 = "link-2_Slider-2"


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
    def from_urdf(cls, path: Path, root: str = ROOT_LINK, tip: str = TIP_LINK) -> "Chain":
        robot = ET.parse(path).getroot()
        by_child = {}
        for element in robot.findall("joint"):
            child = element.find("child").get("link")
            parent = element.find("parent").get("link")
            origin = element.find("origin")
            xyz = [float(v) for v in (origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split()]
            rpy = [float(v) for v in (origin.get("rpy", "0 0 0") if origin is not None else "0 0 0").split()]
            axis_element = element.find("axis")
            axis = np.array([float(v) for v in axis_element.get("xyz").split()]) if axis_element is not None else np.array([0.0, 0.0, 1.0])
            axis = axis / np.linalg.norm(axis)
            limit = element.find("limit")
            kind = element.get("type")
            lower = float(limit.get("lower", "-inf")) if limit is not None and kind != "continuous" else -math.inf
            upper = float(limit.get("upper", "inf")) if limit is not None and kind != "continuous" else math.inf
            by_child[child] = (parent, Joint(element.get("name"), kind, homogeneous(rpy_matrix(*rpy), xyz), axis, lower, upper))
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
        """Return tip transform and per-active-joint (world axis, origin) pairs."""
        transform = np.eye(4)
        frames = []
        index = 0
        for joint in self.joints:
            transform = transform @ joint.origin
            if joint in self.active:
                world_axis = transform[:3, :3] @ joint.axis
                frames.append((world_axis, transform[:3, 3].copy(), joint.kind))
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


def clamp(chain: Chain, q: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    q = np.minimum(np.maximum(q, lower), upper)
    for index, joint in enumerate(chain.active):
        if joint.kind == "continuous" and math.isinf(lower[index]):
            q[index] = math.atan2(math.sin(q[index]), math.cos(q[index]))
    return q


def residuals(chain: Chain, q, target_position, target_axis) -> tuple[float, float]:
    tip, _ = chain.forward(np.asarray(q, dtype=float))
    axis = tip[:3, 2] / np.linalg.norm(tip[:3, 2])
    position_error = float(np.linalg.norm(target_position - tip[:3, 3]))
    axis_error = float(math.acos(max(-1.0, min(1.0, float(axis @ target_axis)))))
    return position_error, axis_error


def solve(chain: Chain, seed, target_position, target_axis, *, iterations=NATIVE_MAX_ITERATIONS,
          relax: frozenset[str] = frozenset()) -> dict:
    """Native-identical DLS position+axis solve; returns best state and termination."""
    lower, upper = chain.bounds(relax)
    q = clamp(chain, np.array(seed, dtype=float), lower, upper)
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
        q = clamp(chain, q + scale * delta, lower, upper)
    return {
        "termination": termination,
        "iterations": count,
        "q": [float(v) for v in best["q"]],
        "position_residual_mm": best["position_m"] * 1000.0,
        "axis_residual_deg": math.degrees(best["axis_rad"]),
    }


def margins(chain: Chain, q) -> dict[str, float]:
    out = {}
    for joint, value in zip(chain.active, q):
        if joint.kind == "continuous":
            continue
        scale = 1000.0 if joint.kind == "prismatic" else 180.0 / math.pi
        out[joint.name] = min(value - joint.lower, joint.upper - value) * scale
    return out


def multi_seed(chain: Chain, target_position, target_axis, seeds, *, iterations, relax, rng, random_count):
    lower, upper = chain.bounds()
    finite_lower = np.where(np.isfinite(lower), lower, -math.pi)
    finite_upper = np.where(np.isfinite(upper), upper, math.pi)
    candidates = [np.array(s, dtype=float) for s in seeds]
    candidates += [rng.uniform(finite_lower, finite_upper) for _ in range(random_count)]
    results = [solve(chain, s, target_position, target_axis, iterations=iterations, relax=relax) for s in candidates]
    converged = [r for r in results if r["termination"] == "converged"]
    best = min(results, key=lambda r: (r["position_residual_mm"] / 0.25) ** 2 + (r["axis_residual_deg"] / 0.5) ** 2)
    return {
        "seeds": len(candidates),
        "converged": len(converged),
        "best": best,
        "converged_examples": converged[:5],
    }


def load_task(evidence_path: Path) -> dict:
    report = json.loads(evidence_path.read_text())
    probe = report["items"]["full_chain_interruption"]["probe_evidence"]
    session = probe["preentry_diagnostic_session"]
    conditioning = session["full_task_outcome"]["target_conditioning"]
    text = json.dumps(report)
    start = text.find('"accepted_matrix_world_ras_mm": [')
    matrix = json.loads(text[start + len('"accepted_matrix_world_ras_mm": '):].split("]", 1)[0] + "]")
    return {
        "entry": np.array(conditioning["entry_base_m"]),
        "pre_entry": np.array(conditioning["pre_entry_base_m"]),
        "target": np.array(conditioning["target_base_m"]),
        "axis": np.array(conditioning["drilling_axis_base_unit"]) / np.linalg.norm(conditioning["drilling_axis_base_unit"]),
        "standoff_mm": float(conditioning["standoff_mm"]),
        "depth_mm": float(conditioning["drilling_length_base_mm"]),
        "world_matrix": np.array(matrix).reshape(4, 4),
        "records": session["candidate_records"],
    }


def analyze(urdf: Path, evidence: Path, *, random_seeds=300, iterations=2000, rng_seed=7) -> dict:
    chain = Chain.from_urdf(urdf)
    task = load_task(evidence)
    rng = np.random.default_rng(rng_seed)
    order = chain.names
    recorded = [r for r in task["records"]]
    seeds = [[r["seed_joint_positions_si"][n] for n in order] for r in recorded]

    # 1. Model validation: recorded best states must reproduce recorded residuals.
    validation = []
    for record in recorded[:2]:
        q = [record["best_joint_positions_si"][n] for n in order]
        p, a = residuals(chain, q, task["pre_entry"], task["axis"])
        validation.append({
            "candidate_index": record["candidate_index"],
            "recorded_mm": record["position_residual_mm"], "model_mm": p * 1000.0,
            "recorded_deg": record["drilling_axis_residual_deg"], "model_deg": math.degrees(a),
        })
    model_valid = all(abs(v["recorded_mm"] - v["model_mm"]) <= 0.01 and abs(v["recorded_deg"] - v["model_deg"]) <= 0.01
                      for v in validation)

    # 2. Native replica on the recorded Home seed.
    native = solve(chain, seeds[0], task["pre_entry"], task["axis"])
    replica = {
        "termination": native["termination"],
        "position_residual_mm": native["position_residual_mm"],
        "axis_residual_deg": native["axis_residual_deg"],
        "recorded_position_residual_mm": recorded[0]["position_residual_mm"],
        "recorded_axis_residual_deg": recorded[0]["drilling_axis_residual_deg"],
    }
    replica_valid = (native["termination"] == recorded[0]["termination_reason"]
                     and abs(native["position_residual_mm"] - recorded[0]["position_residual_mm"]) <= 0.01
                     and abs(native["axis_residual_deg"] - recorded[0]["drilling_axis_residual_deg"]) <= 0.01)

    out = {"chain": order, "model_validation": validation, "model_valid": model_valid,
           "native_replica": replica, "native_replica_valid": replica_valid}
    if not model_valid:
        out["verdict"] = "STOP: kinematic model does not reproduce recorded residuals"
        return out

    # 3. Reach along the drill axis under three limit regimes.
    sliders = frozenset(j.name for j in chain.active if j.kind == "prismatic")
    everything = frozenset(chain.names)
    regimes = {"A_mechanical": frozenset(), "B_sliders_unbounded": sliders, "C_all_unbounded": everything}
    stations = sorted({-4.0, -task["standoff_mm"], -1.0, 0.0, 2.0, 4.0, 6.0, 8.0, task["depth_mm"], 12.0})
    sweep = []
    for s_mm in stations:
        point = task["entry"] + task["axis"] * (s_mm / 1000.0)
        row = {"s_mm": s_mm}
        for label, relax in regimes.items():
            result = multi_seed(chain, point, task["axis"], seeds, iterations=iterations, relax=relax,
                                rng=rng, random_count=random_seeds if label == "A_mechanical" else 60)
            best = result["best"]
            row[label] = {
                "converged": result["converged"], "seeds": result["seeds"],
                "best_position_residual_mm": best["position_residual_mm"],
                "best_axis_residual_deg": best["axis_residual_deg"],
                "best_q": dict(zip(order, best["q"])),
            }
            if label != "A_mechanical" and result["converged_examples"]:
                j2 = [dict(zip(order, r["q"]))[J2] * 1000.0 for r in result["converged_examples"]]
                row[label]["converged_J2_mm"] = j2
        row["A_mechanical"]["margins"] = margins(chain, row["A_mechanical"]["best_q"].values())
        sweep.append(row)
    out["axis_sweep"] = sweep

    # 4. Placement: base translation along the J2 axis is exactly a J2 offset.
    a_pre = next(r for r in sweep if abs(r["s_mm"] + task["standoff_mm"]) < 1e-9)
    b_pre = a_pre["B_sliders_unbounded"]
    # The whole PreEntry->Target stroke must fit inside the J2 range, not just PreEntry.
    span = [r for r in sweep if -task["standoff_mm"] - 1e-9 <= r["s_mm"] <= task["depth_mm"] + 1e-9]
    placement = {"applicable": False}
    if a_pre["A_mechanical"]["converged"] == 0 and all(r["B_sliders_unbounded"]["converged"] > 0 for r in span):
        required = min(min(r["B_sliders_unbounded"]["converged_J2_mm"]) for r in span)
        margin_mm = 1.0
        shift_m = (margin_mm - required) / 1000.0  # J2 must increase by this amount
        q_ref = np.array(list(b_pre["best_q"].values()))
        _, frames = chain.forward(q_ref)
        j2_axis_base = frames[order.index(J2)][0]
        # Moving the base by -d along the J2 axis is the same as J2 += d.
        base_shift_base_m = -j2_axis_base * shift_m
        world_offset_mm = task["world_matrix"][:3, :3] @ (base_shift_base_m * 1000.0)
        checks = {}
        stations = [("pre_entry", task["pre_entry"]), ("entry", task["entry"])]
        stations += [(f"s_{r['s_mm']:g}mm", task["entry"] + task["axis"] * (r["s_mm"] / 1000.0))
                     for r in span if 0.0 < r["s_mm"] < task["depth_mm"] - 1e-9]
        stations.append(("target", task["target"]))
        for name, point in stations:
            shifted = point - base_shift_base_m
            native_home = solve(chain, seeds[0], shifted, task["axis"])
            multi = multi_seed(chain, shifted, task["axis"], seeds, iterations=iterations, relax=frozenset(),
                               rng=rng, random_count=60)
            checks[name] = {
                "native_home_seed": native_home["termination"],
                "native_home_position_residual_mm": native_home["position_residual_mm"],
                "native_home_axis_residual_deg": native_home["axis_residual_deg"],
                "native_home_margins": margins(chain, native_home["q"]),
                "multi_seed_converged": multi["converged"],
            }
        placement = {
            "applicable": True,
            "sizing": "minimum J2 over PreEntry..Target stroke, plus margin",
            "required_J2_mm_without_shift": required,
            "target_J2_margin_mm": margin_mm,
            "base_shift_norm_mm": abs(shift_m) * 1000.0,
            "base_shift_base_frame_mm": (base_shift_base_m * 1000.0).tolist(),
            "world_offset_ras_mm": world_offset_mm.tolist(),
            "within_20mm_envelope": bool(abs(shift_m) * 1000.0 <= 20.0),
            "checks": checks,
        }
    out["placement"] = placement
    out["verdict"] = verdict(out)
    return out


def verdict(out: dict) -> str:
    sweep = out["axis_sweep"]
    pre = next(r for r in sweep if r["s_mm"] < 0 and abs(r["s_mm"] + 2.0) < 1e-6) if any(abs(r["s_mm"] + 2.0) < 1e-6 for r in sweep) else sweep[1]
    if pre["A_mechanical"]["converged"] > 0:
        return "SOLVER: an in-limit PreEntry solution exists; native budget/seeding missed it"
    placement = out["placement"]
    if placement.get("applicable") and placement["within_20mm_envelope"] and all(
            c["native_home_seed"] == "converged" for c in placement["checks"].values()):
        return "PLACEMENT: unreachable inside joint limits at this base; a small base translation fixes reach (collision not yet evaluated)"
    if placement.get("applicable") and placement["within_20mm_envelope"]:
        return "PLACEMENT+SOLVER: a translation makes the task reachable but the native Home seed does not converge everywhere"
    return "DESIGN: no in-limit solution within the evaluated base envelope"


def write_markdown(out: dict, path: Path) -> None:
    lines = ["# PreEntry reachability attribution (offline, kinematic only)", "",
             f"Verdict: **{out['verdict']}**", "",
             f"Model valid: {out['model_valid']}; native replica valid: {out['native_replica_valid']}", "",
             "Collision is not evaluated here.", "", "## Axis sweep (s = mm from Entry along drill axis)", "",
             "| s mm | A converged/seeds | A best pos mm / axis deg | A best J2 mm | B converged (J2 mm) | C converged |",
             "|---|---|---|---|---|---|"]
    for row in out.get("axis_sweep", []):
        a, b, c = row["A_mechanical"], row["B_sliders_unbounded"], row["C_all_unbounded"]
        j2 = a["best_q"][J2] * 1000.0
        bj2 = ", ".join(f"{v:.2f}" for v in b.get("converged_J2_mm", [])[:3])
        lines.append(f"| {row['s_mm']:.3f} | {a['converged']}/{a['seeds']} | {a['best_position_residual_mm']:.3f} / "
                     f"{a['best_axis_residual_deg']:.3f} | {j2:.3f} | {b['converged']} ({bj2}) | {c['converged']} |")
    placement = out.get("placement", {})
    lines += ["", "## Placement", "", "```json", json.dumps(placement, indent=2), "```"]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--random-seeds", type=int, default=300)
    parser.add_argument("--iterations", type=int, default=2000)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    out = analyze(args.urdf, args.evidence, random_seeds=args.random_seeds, iterations=args.iterations)
    (args.out / "reachability.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    write_markdown(out, args.out / "reachability.md")
    print(out["verdict"])
    return 0 if out["model_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
