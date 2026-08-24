"""Step 6 planning helpers: context import, task limits, coarse collision, motion plan.

Pure Python with optional NumPy/SciPy. No Slicer imports. Simulation-only:
does not command hardware or claim MoveIt/clinical safety validation.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from math import degrees, isfinite, radians, sqrt
from pathlib import Path
from typing import Callable, Mapping, Sequence
from xml.etree import ElementTree

import numpy as np

from DENTORobotPlacement import (
    burr_origin_base_m,
    joint_positions_si_from_display,
)


REQUIRED_PLANNING_ROLES = (
    "inputVolume",
    "teethSegmentation",
    "trajectoryLine",
    "targetDockingAssemblyModel",
    "finalPrintableTemplateModel",
)

OPTIONAL_PLANNING_ROLES = (
    "draftTemplateSupportModel",
    "visibleTemplateSupportModel",
    "targetToothBoundsRoi",
)

CASE_VIEW_ROLES = (
    "inputVolume",
    "teethSegmentation",
    "trajectoryLine",
    "targetDockingAssemblyModel",
    "finalPrintableTemplateModel",
    "targetToothBoundsRoi",
)

# These two non-adjacent pairs overlap for every tested configuration only in
# the axis-aligned boxes of the imported CAD meshes. MoveIt/FCL accepts the
# verified nonzero smoke-test pose, so keeping them in the coarse gate makes
# the fallback planner and workspace explorer reject the entire joint space.
# This is a narrowly scoped draft exception, not an Allowed Collision Matrix
# claim for the physical robot; exact MoveIt collision checking remains the
# authoritative path whenever the ROS stack is active.
DRAFT_AABB_FALSE_POSITIVE_PAIRS = frozenset(
    {
        frozenset(("link-3", "link-5")),
        frozenset(("link-3", "pneumatic_spindle-Copy")),
    }
)


@dataclass(frozen=True)
class PlanningContextReport:
    ready: bool
    missing_required: tuple[str, ...]
    present: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class JointLimitPair:
    minimum: float
    maximum: float
    unit: str


@dataclass(frozen=True)
class TaskJointLimits:
    joint_1: JointLimitPair
    joint_2: JointLimitPair
    joint_3: JointLimitPair
    joint_4: JointLimitPair
    joint_5: JointLimitPair
    joint_6: JointLimitPair

    def as_display_vector(self) -> tuple[float, float, float, float, float, float]:
        return (
            self.joint_1.minimum,
            self.joint_2.minimum,
            self.joint_3.minimum,
            self.joint_4.minimum,
            self.joint_5.minimum,
            self.joint_6.minimum,
        )

    def as_display_max_vector(self) -> tuple[float, float, float, float, float, float]:
        return (
            self.joint_1.maximum,
            self.joint_2.maximum,
            self.joint_3.maximum,
            self.joint_4.maximum,
            self.joint_5.maximum,
            self.joint_6.maximum,
        )


@dataclass(frozen=True)
class MotionPlanResult:
    success: bool
    message: str
    waypoint_joint_vectors_si: tuple[dict[str, float], ...] = ()
    self_collision_indices: tuple[int, ...] = ()
    environment_collision_indices: tuple[int, ...] = ()
    burr_world_mm: tuple[tuple[float, float, float], ...] = ()
    planner: str = "draft_scipy_position_ik"
    cartesian_fraction: float = 0.0
    waypoint_times_sec: tuple[float, ...] = ()


@dataclass(frozen=True)
class WorkspaceSampleResult:
    """Filtered provisional-TCP samples expressed in robot-base millimetres."""

    requested_count: int
    accepted_tcp_base_mm: tuple[tuple[float, float, float], ...]
    self_collision_rejections: int
    environment_rejections: int
    task_limits: TaskJointLimits
    excluded_aabb_pairs: int = len(DRAFT_AABB_FALSE_POSITIVE_PAIRS)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_tcp_base_mm)


def validate_planning_context(
    role_to_node_id: Mapping[str, str | None],
) -> PlanningContextReport:
    """Return whether upstream workflow artifacts needed for Step 6 are present."""
    missing = tuple(
        role
        for role in REQUIRED_PLANNING_ROLES
        if not (role_to_node_id.get(role) or "").strip()
    )
    present = tuple(
        role for role in REQUIRED_PLANNING_ROLES if role not in missing
    )
    if missing:
        labels = ", ".join(missing)
        return PlanningContextReport(
            ready=False,
            missing_required=missing,
            present=present,
            message=(
                "Planning package incomplete. Missing required workflow nodes: "
                f"{labels}."
            ),
        )
    return PlanningContextReport(
        ready=True,
        missing_required=(),
        present=present,
        message=(
            "Planning package ready: CBCT volume, segmentation, trajectory, "
            "docking assembly, and printable template are linked."
        ),
    )


def case_view_present_roles(
    role_to_node_id: Mapping[str, str | None],
) -> tuple[str, ...]:
    """Return planning-package roles that should appear in the Step 6 case view."""
    return tuple(
        role
        for role in CASE_VIEW_ROLES
        if (role_to_node_id.get(role) or "").strip()
    )


def combine_ras_bounds(
    bounds_list: Sequence[Sequence[float]],
) -> tuple[float, ...] | None:
    """Union axis-aligned world-RAS boxes ``[xmin, xmax, ymin, ymax, zmin, zmax]``.

    Degenerate or non-finite boxes are ignored so an empty segmentation or
    unset ROI cannot pull the camera to the origin.
    """
    finite: list[tuple[float, float, float, float, float, float]] = []
    for bounds in bounds_list:
        if len(bounds) != 6:
            continue
        values = tuple(float(value) for value in bounds)
        if not all(isfinite(value) for value in values):
            continue
        if not all(values[2 * axis + 1] > values[2 * axis] for axis in range(3)):
            continue
        finite.append(values)
    if not finite:
        return None
    return (
        min(item[0] for item in finite),
        max(item[1] for item in finite),
        min(item[2] for item in finite),
        max(item[3] for item in finite),
        min(item[4] for item in finite),
        max(item[5] for item in finite),
    )


def step6_motion_plan_robot_ready(
    *,
    ros_motion_active: bool,
    mrml_link_count: int,
) -> bool:
    """True when either the SlicerROS2 robot or MRML STL chain is present."""
    return bool(ros_motion_active) or int(mrml_link_count) > 0


def _movable_joint_specs(robot_description: str) -> list[tuple[str, str, float, float]]:
    root = ElementTree.fromstring(robot_description)
    specs: list[tuple[str, str, float, float]] = []
    for joint in root.findall("joint"):
        joint_type = joint.get("type", "")
        if joint_type in {"fixed", "floating", "planar"}:
            continue
        name = joint.get("name", "").strip()
        if joint_type == "continuous":
            lower, upper = -180.0, 180.0
            unit = "deg"
        elif joint_type == "prismatic":
            limit = joint.find("limit")
            if limit is None:
                raise ValueError(f"joint {name} is missing limits")
            lower = float(limit.get("lower")) * 1000.0
            upper = float(limit.get("upper")) * 1000.0
            unit = "mm"
        else:
            limit = joint.find("limit")
            if limit is None:
                raise ValueError(f"joint {name} is missing limits")
            lower = degrees(float(limit.get("lower")))
            upper = degrees(float(limit.get("upper")))
            unit = "deg"
        if lower > upper:
            lower, upper = upper, lower
        specs.append((name, unit, lower, upper))
    if len(specs) != 6:
        raise ValueError(f"expected six movable joints, found {len(specs)}")
    return specs


def default_task_joint_limits_from_urdf(urdf_path: str | Path) -> TaskJointLimits:
    specs = _movable_joint_specs(Path(urdf_path).read_text(encoding="utf-8"))
    pairs = tuple(
        JointLimitPair(minimum=lo, maximum=hi, unit=unit)
        for _name, unit, lo, hi in specs
    )
    return TaskJointLimits(*pairs)


def build_task_joint_limits_from_parameter_values(
    *,
    j1_min: float,
    j1_max: float,
    j2_min: float,
    j2_max: float,
    j3_min: float,
    j3_max: float,
    j4_min: float,
    j4_max: float,
    j5_min: float,
    j5_max: float,
    j6_min: float,
    j6_max: float,
) -> TaskJointLimits:
    return TaskJointLimits(
        JointLimitPair(j1_min, j1_max, "deg"),
        JointLimitPair(j2_min, j2_max, "mm"),
        JointLimitPair(j3_min, j3_max, "deg"),
        JointLimitPair(j4_min, j4_max, "mm"),
        JointLimitPair(j5_min, j5_max, "deg"),
        JointLimitPair(j6_min, j6_max, "deg"),
    )


def apply_task_joint_limits_to_display_ranges(
    limits: TaskJointLimits,
    urdf_limits: TaskJointLimits,
) -> TaskJointLimits:
    """Clamp task limits to mechanical URDF bounds."""
    clamped = []
    for task, mechanical in (
        (limits.joint_1, urdf_limits.joint_1),
        (limits.joint_2, urdf_limits.joint_2),
        (limits.joint_3, urdf_limits.joint_3),
        (limits.joint_4, urdf_limits.joint_4),
        (limits.joint_5, urdf_limits.joint_5),
        (limits.joint_6, urdf_limits.joint_6),
    ):
        lo = max(task.minimum, mechanical.minimum)
        hi = min(task.maximum, mechanical.maximum)
        if lo > hi:
            raise ValueError(
                f"Task joint limit [{lo}, {hi}] {task.unit} exceeds mechanical range "
                f"[{mechanical.minimum}, {mechanical.maximum}] {mechanical.unit}."
            )
        clamped.append(JointLimitPair(lo, hi, task.unit))
    return TaskJointLimits(*clamped)


def apply_task_limit_range_to_value(
    value: float,
    joint_limit: JointLimitPair,
) -> tuple[float, float, float]:
    """Return ``(minimum, maximum, clamped_value)`` for a merged min/value/max row."""
    lo = float(joint_limit.minimum)
    hi = float(joint_limit.maximum)
    if lo > hi:
        raise ValueError(
            f"Task joint limit [{lo}, {hi}] {joint_limit.unit} is inverted."
        )
    return lo, hi, min(max(float(value), lo), hi)


def sample_trajectory_world_mm(
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    sample_count: int,
) -> list[tuple[float, float, float]]:
    if sample_count < 2:
        raise ValueError("sample_count must be at least 2")
    start = np.asarray(entry_ras_mm, dtype=float)
    end = np.asarray(target_ras_mm, dtype=float)
    if start.shape != (3,) or end.shape != (3,) or not np.all(np.isfinite(start + end)):
        raise ValueError("entry and target must be finite RAS triplets")
    alphas = np.linspace(0.0, 1.0, sample_count)
    return [tuple(point) for point in (start + alpha * (end - start) for alpha in alphas)]


def halton_value(index: int, base: int) -> float:
    """Return one deterministic low-discrepancy Halton coordinate in [0, 1)."""
    if index < 0:
        raise ValueError("Halton index must be non-negative")
    if base < 2:
        raise ValueError("Halton base must be at least 2")
    fraction = 1.0
    value = 0.0
    remaining = int(index)
    while remaining:
        fraction /= float(base)
        remaining, digit = divmod(remaining, base)
        value += fraction * float(digit)
    return value


def deterministic_joint_workspace_samples_display(
    limits: TaskJointLimits,
    sample_count: int,
    current_display_joints: Sequence[float] | None = None,
) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """Sample all six task ranges without random-state or repeated IK solves.

    The current pose is included first when supplied. Remaining samples use a
    six-dimensional Halton sequence, which spreads a small draft sample budget
    more uniformly than a Cartesian grid or pseudorandom points.
    """
    count = int(sample_count)
    if count < 1:
        raise ValueError("workspace sample_count must be at least 1")
    minimums = np.asarray(limits.as_display_vector(), dtype=float)
    maximums = np.asarray(limits.as_display_max_vector(), dtype=float)
    if not np.all(np.isfinite(minimums + maximums)) or np.any(maximums < minimums):
        raise ValueError("workspace task limits must be finite and ordered")
    samples: list[tuple[float, float, float, float, float, float]] = []
    if current_display_joints is not None:
        samples.append(_clamp_display_vector(current_display_joints, limits))
    bases = (2, 3, 5, 7, 11, 13)
    index = 1
    while len(samples) < count:
        unit = np.asarray(
            [halton_value(index, base) for base in bases],
            dtype=float,
        )
        display = minimums + unit * (maximums - minimums)
        samples.append(tuple(float(value) for value in display))
        index += 1
    return tuple(samples)


def sample_filtered_tcp_workspace(
    *,
    limits: TaskJointLimits,
    sample_count: int,
    current_display_joints: Sequence[float] | None,
    urdf_path: Path,
    package_root: Path,
    base_world_matrix: np.ndarray,
    coarse_self_clearance_mm: float,
    environment_points_mm: np.ndarray | None,
    environment_clearance_mm: float,
) -> WorkspaceSampleResult:
    """Return deterministic joint-space FK samples that pass draft guards.

    This is a design-exploration envelope, not an IK reachability proof. Each
    task-limited joint vector is evaluated by forward kinematics. Non-adjacent
    robot-link AABBs enforce the configured self-clearance and the provisional
    TCP origin is rejected when it is too close to the subsampled environment.
    """
    base_world = np.asarray(base_world_matrix, dtype=float)
    if base_world.shape != (4, 4) or not np.all(np.isfinite(base_world)):
        raise ValueError("base_world_matrix must be a finite 4x4 matrix")
    inverse_base_world = np.linalg.inv(base_world)
    environment = (
        np.zeros((0, 3), dtype=float)
        if environment_points_mm is None
        else _environment_points_from_polydata(environment_points_mm)
    )
    coarse_model = _load_coarse_kinematic_model(urdf_path, package_root)
    accepted: list[tuple[float, float, float]] = []
    self_rejections = 0
    environment_rejections = 0
    for display in deterministic_joint_workspace_samples_display(
        limits,
        sample_count,
        current_display_joints,
    ):
        joints_si = _display_to_si_vector(display)
        ok, reason, tcp_world = evaluate_motion_configuration(
            joints_si,
            urdf_path=urdf_path,
            package_root=package_root,
            base_world_matrix=base_world,
            coarse_clearance_mm=coarse_self_clearance_mm,
            environment_points_mm=environment,
            environment_clearance_mm=environment_clearance_mm,
            coarse_model=coarse_model,
        )
        if not ok:
            if "self-collision" in reason or "AABB" in reason:
                self_rejections += 1
            else:
                environment_rejections += 1
            continue
        tcp_base = inverse_base_world @ np.asarray([*tcp_world, 1.0], dtype=float)
        accepted.append(tuple(float(value) for value in tcp_base[:3]))
    return WorkspaceSampleResult(
        requested_count=int(sample_count),
        accepted_tcp_base_mm=tuple(accepted),
        self_collision_rejections=self_rejections,
        environment_rejections=environment_rejections,
        task_limits=limits,
    )


def _load_coarse_kinematic_model(urdf_path: Path, package_root: Path):
    publisher_path = package_root / "scripts" / "manual_joint_state_publisher.py"
    if not publisher_path.is_file():
        raise RuntimeError(
            f"Coarse kinematic model script is missing: {publisher_path}"
        )
    spec = importlib.util.spec_from_file_location(
        "dentobot_manual_joint_state_publisher_planning",
        publisher_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load coarse kinematic model from {publisher_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CoarseKinematicModel(
        urdf_path.read_text(encoding="utf-8"),
        package_root,
    )


def _world_from_base_mm(base_world_matrix: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    matrix = np.asarray(base_world_matrix, dtype=float)
    if matrix.shape != (4, 4):
        raise ValueError("base_world_matrix must be 4x4")

    def transform(point_base_mm: np.ndarray) -> np.ndarray:
        homogeneous = np.array(
            [point_base_mm[0], point_base_mm[1], point_base_mm[2], 1.0],
            dtype=float,
        )
        world = matrix @ homogeneous
        return world[:3]

    return transform


def burr_world_mm_from_joints(
    joint_positions_si: Mapping[str, float],
    urdf_path: Path,
    package_root: Path,
    base_world_matrix: np.ndarray,
) -> tuple[float, float, float]:
    burr_base_m = burr_origin_base_m(joint_positions_si, urdf_path, package_root)
    burr_base_mm = burr_base_m * 1000.0
    world = _world_from_base_mm(base_world_matrix)(burr_base_mm)
    return float(world[0]), float(world[1]), float(world[2])


def _distance_point_to_polydata_mm(
    point_ras_mm: Sequence[float],
    points_mm: np.ndarray,
) -> float:
    """Return minimum distance from a point to a point cloud (mm)."""
    if points_mm.size == 0:
        return float("inf")
    point = np.asarray(point_ras_mm, dtype=float)
    deltas = points_mm - point
    return float(np.min(np.linalg.norm(deltas, axis=1)))


def _environment_points_from_polydata(polydata_points: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(list(polydata_points), dtype=float)
    if array.size == 0:
        return np.zeros((0, 3), dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("environment polydata samples must be Nx3")
    return array


def evaluate_motion_configuration(
    joint_positions_si: Mapping[str, float],
    *,
    urdf_path: Path,
    package_root: Path,
    base_world_matrix: np.ndarray,
    coarse_clearance_mm: float,
    environment_points_mm: np.ndarray | None,
    environment_clearance_mm: float,
    coarse_model=None,
) -> tuple[bool, str, tuple[float, float, float]]:
    model = coarse_model or _load_coarse_kinematic_model(urdf_path, package_root)
    evaluation = model.evaluate(dict(joint_positions_si), coarse_clearance_mm / 1000.0)
    actionable_violations = tuple(
        violation
        for violation in evaluation.violations
        if frozenset((violation.first_link, violation.second_link))
        not in DRAFT_AABB_FALSE_POSITIVE_PAIRS
    )
    if actionable_violations:
        first = actionable_violations[0]
        return (
            False,
            (
                f"Coarse self-collision between {first.first_link} and "
                f"{first.second_link} at {first.distance_m * 1000.0:.2f} mm separation "
                f"(draft AABB, not exact mesh contact)."
            ),
            tuple(value * 1000.0 for value in evaluation.burr_origin_m),
        )
    burr_world = burr_world_mm_from_joints(
        joint_positions_si,
        urdf_path,
        package_root,
        base_world_matrix,
    )
    if environment_points_mm is not None and environment_points_mm.size:
        distance = _distance_point_to_polydata_mm(burr_world, environment_points_mm)
        if distance < environment_clearance_mm:
            return (
                False,
                (
                    f"Environment clearance {distance:.2f} mm is below "
                    f"{environment_clearance_mm:.2f} mm at the burr origin "
                    "(point-cloud sampling, not swept-volume)."
                ),
                burr_world,
            )
    return True, "", burr_world


def _display_to_si_vector(values: Sequence[float]) -> dict[str, float]:
    return joint_positions_si_from_display(*[float(value) for value in values])


def _clamp_display_vector(
    values: Sequence[float],
    limits: TaskJointLimits,
) -> tuple[float, float, float, float, float, float]:
    mins = limits.as_display_vector()
    maxs = limits.as_display_max_vector()
    clamped = []
    for value, lo, hi in zip(values, mins, maxs):
        clamped.append(min(max(float(value), lo), hi))
    return tuple(clamped)  # type: ignore[return-value]


def _solve_position_ik_display(
    target_world_mm: Sequence[float],
    seed_display: Sequence[float],
    limits: TaskJointLimits,
    *,
    urdf_path: Path,
    package_root: Path,
    base_world_matrix: np.ndarray,
) -> tuple[float, float, float, float, float, float]:
    from scipy.optimize import minimize

    base_world = np.asarray(base_world_matrix, dtype=float)
    base_world_inv = np.linalg.inv(base_world)
    target_h = np.array([*target_world_mm, 1.0], dtype=float)
    target_base_mm = (base_world_inv @ target_h)[:3]

    mins = np.asarray(limits.as_display_vector(), dtype=float)
    maxs = np.asarray(limits.as_display_max_vector(), dtype=float)
    seed = np.asarray(_clamp_display_vector(seed_display, limits), dtype=float)

    def objective(display_vector: np.ndarray) -> float:
        clamped = np.clip(display_vector, mins, maxs)
        joint_si = _display_to_si_vector(clamped)
        burr_base_m = burr_origin_base_m(joint_si, urdf_path, package_root)
        burr_base_mm = burr_base_m * 1000.0
        delta = burr_base_mm - target_base_mm
        return float(np.dot(delta, delta))

    result = minimize(
        objective,
        seed,
        method="L-BFGS-B",
        bounds=list(zip(mins, maxs, strict=True)),
        options={"maxiter": 200, "ftol": 1e-9},
    )
    if not result.success and result.fun > 25.0:
        raise RuntimeError(
            f"IK did not converge for target {tuple(target_world_mm)}: {result.message}"
        )
    return tuple(float(value) for value in np.clip(result.x, mins, maxs))


def plan_trajectory_motion(
    *,
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    start_display_joints: Sequence[float],
    limits: TaskJointLimits,
    urdf_path: Path,
    package_root: Path,
    base_world_matrix: np.ndarray,
    sample_count: int,
    coarse_self_clearance_mm: float,
    environment_points_mm: np.ndarray | None,
    environment_clearance_mm: float,
) -> MotionPlanResult:
    """Plan a joint-space path along the trajectory with coarse collision gates."""
    samples = sample_trajectory_world_mm(entry_ras_mm, target_ras_mm, sample_count)
    coarse_model = _load_coarse_kinematic_model(urdf_path, package_root)
    waypoints_si: list[dict[str, float]] = []
    burr_points: list[tuple[float, float, float]] = []
    seed = start_display_joints
    self_hits: list[int] = []
    env_hits: list[int] = []

    for index, world_point in enumerate(samples):
        try:
            display = _solve_position_ik_display(
                world_point,
                seed,
                limits,
                urdf_path=urdf_path,
                package_root=package_root,
                base_world_matrix=base_world_matrix,
            )
        except RuntimeError as exc:
            return MotionPlanResult(
                success=False,
                message=f"Waypoint {index + 1}/{len(samples)} IK failed: {exc}",
                waypoint_joint_vectors_si=tuple(waypoints_si),
                burr_world_mm=tuple(burr_points),
            )
        joint_si = _display_to_si_vector(display)
        ok, reason, burr_world = evaluate_motion_configuration(
            joint_si,
            urdf_path=urdf_path,
            package_root=package_root,
            base_world_matrix=base_world_matrix,
            coarse_clearance_mm=coarse_self_clearance_mm,
            environment_points_mm=environment_points_mm,
            environment_clearance_mm=environment_clearance_mm,
            coarse_model=coarse_model,
        )
        if not ok:
            if "self-collision" in reason or "AABB" in reason:
                self_hits.append(index)
            else:
                env_hits.append(index)
            return MotionPlanResult(
                success=False,
                message=f"Waypoint {index + 1}/{len(samples)} rejected: {reason}",
                waypoint_joint_vectors_si=tuple(waypoints_si),
                self_collision_indices=tuple(self_hits),
                environment_collision_indices=tuple(env_hits),
                burr_world_mm=tuple(burr_points),
            )
        waypoints_si.append(joint_si)
        burr_points.append(burr_world)
        seed = display

    return MotionPlanResult(
        success=True,
        message=(
            f"Motion plan accepted for {len(samples)} trajectory samples with coarse "
            "self-collision and environment clearance checks. Simulation only."
        ),
        waypoint_joint_vectors_si=tuple(waypoints_si),
        burr_world_mm=tuple(burr_points),
    )
