"""UI-independent orchestration boundary for DENTOBOT Step 6 simulation.

The legacy workflow panel and the application shell both call this façade.
Robot geometry, ROS 2, MoveIt, collision, and planning remain implemented by
the existing logic and bridge modules; this class only coordinates them and
returns structured presentation results.  It intentionally exposes no
hardware execution path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from math import degrees, isfinite, pi
from typing import Any, Callable, Mapping, Optional, Sequence

import DENTOROS2Bridge as _default_bridge
from DENTORobotPlacement import joint_positions_si_from_display
from DENTOStep6State import (
    DRILL_TOOL_FRAME_POLICY,
    SPINDLE_JOINT_NAME,
    SPINDLE_LOCKED_VALUE_RAD,
    SPINDLE_PLANNING_POLICY,
    build_motion_diagnostic_session,
    canonicalize_planning_joint_positions,
    canonical_json,
    fingerprint,
    parse_motion_diagnostic_session,
)


JOINT_DISPLAY_FIELDS = (
    "robotJoint1Deg",
    "robotJoint2Mm",
    "robotJoint3Deg",
    "robotJoint4Mm",
    "robotJoint5Deg",
    "robotJoint6Deg",
)
JOINT_LIMIT_FIELDS = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
)
JOINT_DISPLAY_UNITS = ("deg", "mm", "deg", "mm", "deg", "deg")
JOINT_NAMES = tuple(_default_bridge.ROS2_JOINT_SI_ORDER)
WORKSPACE_RUNTIME_VALIDATION_MAX_SAMPLES = 400
WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES = 13
WORKSPACE_RUNTIME_VALIDATION_STATUS = (
    "MoveItStaticStateValidity+BoundedHomeConnectivity"
)
WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION = "1.0"
GOAL1_CANONICAL_TOOL_ROLL_DEG = 0.0
# 6.3 evaluates at most thirteen Home-connected representatives.  Use every
# one as an IK seed, plus Task Home, so Stage 1 can discover distinct
# joints-1–5 branches before committing the immutable drilling frame.  These
# are arm-posture alternatives; J6 remains fixed and is never a route variable.
GOAL1_MAX_IK_SEEDS = WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES + 1
GOAL1_MAX_PLANNED_IK_CANDIDATES = GOAL1_MAX_IK_SEEDS
GOAL1_MAX_CLEARANCE_WAYPOINTS = 3
GOAL1_DIRECT_PLANNING_TIME_SEC = 5.0
GOAL1_CLEARANCE_PLANNING_TIME_SEC = 4.0


def _bounded_text(value: object, maximum_length: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= maximum_length:
        return text
    return text[: max(0, maximum_length - 3)] + "..."


def _bounded_even_indices(count: int, maximum_count: int) -> tuple[int, ...]:
    count = max(0, int(count))
    maximum_count = max(0, int(maximum_count))
    if count == 0 or maximum_count == 0:
        return ()
    if count <= maximum_count:
        return tuple(range(count))
    if maximum_count == 1:
        return (0,)
    last_index = count - 1
    return tuple(
        round(index * last_index / (maximum_count - 1))
        for index in range(maximum_count)
    )


@dataclass(frozen=True)
class RobotActionResult:
    """One deterministic façade action outcome suitable for either GUI."""

    success: bool
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    payload: Any = None


@dataclass(frozen=True)
class RobotCapabilities:
    """Read-only runtime capability snapshot; never saved with an MRML case."""

    simulation_only: bool
    stack_state: str
    description_ready: bool
    planning_ready: bool
    single_joint_state_source: bool
    connected: bool
    robot_loaded: bool
    move_group_available: bool
    planning_group: str
    tcp_link: str
    ik_available: bool
    collision_check_available: bool
    planning_scene_synchronized: bool
    planning_scene_object_count: int
    reason: str = ""


@dataclass(frozen=True)
class RobotWorkflowState:
    """Operator-unit view of the current Step 6 state."""

    scene_kind: str
    joint_names: tuple[str, ...]
    joint_display_values: tuple[float, ...]
    joint_display_units: tuple[str, ...]
    joint_positions_si: Mapping[str, float]
    base_node_id: str
    base_locked: bool
    ros_motion_active: bool
    has_motion_plan: bool
    preview_active: bool


@dataclass(frozen=True)
class PhasePlan:
    """Transient guarded simulation plan; never serialized in MRML."""

    success: bool
    message: str
    task_fingerprint: str
    requested_phase: str
    waypoint_joint_vectors_si: tuple[dict[str, float], ...]
    waypoint_phases: tuple[str, ...]
    waypoint_times_sec: tuple[float, ...] = ()
    cartesian_fraction: float = 0.0
    coordinate_frame: str = "base_link"
    start_position_error_mm: Optional[float] = None
    start_orientation_error_deg: Optional[float] = None
    strict_waypoint_count: int = 0
    axis_waypoint_count: int = 0
    contact_waypoint_count: int = 0
    source_waypoint_count: int = 0
    axial_roll_deg: float = 0.0
    tool_axis_ras: tuple[float, float, float] = ()
    tool_orientation_fingerprint: str = ""
    planner: str = "moveit+dentobot_phase_guard"


def _concatenate_waypoint_times(
    first: Sequence[float],
    second: Sequence[float],
) -> tuple[float, ...]:
    """Join independently timed trajectories into one monotonic timeline."""

    first_values = tuple(float(value) for value in first)
    second_values = tuple(float(value) for value in second)
    if not first_values:
        return second_values
    if not second_values:
        return first_values
    second_origin = second_values[0]
    relative_second = tuple(
        max(0.0, value - second_origin) for value in second_values
    )
    positive_steps = tuple(
        relative_second[index] - relative_second[index - 1]
        for index in range(1, len(relative_second))
        if relative_second[index] > relative_second[index - 1]
    )
    join_gap = min(positive_steps) if positive_steps else 0.001
    join_gap = max(0.001, float(join_gap))
    offset = max(0.0, first_values[-1]) + join_gap
    return first_values + tuple(offset + value for value in relative_second)


def _compact_guarded_waypoints(
    waypoints: Sequence[Mapping[str, float]],
    times_sec: Sequence[float],
    *,
    maximum_revolute_span_rad: float,
    maximum_prismatic_span_m: float,
    revolute_deviation_rad: float = 0.0017453292519943296,
    prismatic_deviation_m: float = 0.00005,
) -> tuple[tuple[dict[str, float], ...], tuple[float, ...]]:
    """Remove redundant time samples without weakening guard coverage.

    MoveIt may time-parameterize a simple geometric path into hundreds of
    closely spaced joint samples.  The ROS phase guard independently checks a
    linear joint interpolation between every pair of published checkpoints.
    This routine selects the farthest original checkpoint that (a) spans only
    a bounded number of guard samples and (b) keeps every omitted MoveIt point
    within a tight, unit-aware deviation of that interpolation.
    """

    if not waypoints:
        return (), ()
    vectors = tuple(
        tuple(float(point[name]) for name in JOINT_NAMES) for point in waypoints
    )
    if any(not isfinite(value) for vector in vectors for value in vector):
        raise ValueError("MoveIt preview waypoints must contain finite joint values.")
    if times_sec and len(times_sec) != len(vectors):
        raise ValueError("MoveIt preview waypoint/time counts do not match.")
    times = (
        tuple(float(value) for value in times_sec)
        if times_sec
        else tuple(float(index) for index in range(len(vectors)))
    )
    deviations = (
        float(revolute_deviation_rad),
        float(prismatic_deviation_m),
        float(revolute_deviation_rad),
        float(prismatic_deviation_m),
        float(revolute_deviation_rad),
        float(revolute_deviation_rad),
    )
    spans = (
        float(maximum_revolute_span_rad),
        float(maximum_prismatic_span_m),
        float(maximum_revolute_span_rad),
        float(maximum_prismatic_span_m),
        float(maximum_revolute_span_rad),
        float(maximum_revolute_span_rad),
    )
    if any(value <= 0.0 or not isfinite(value) for value in (*deviations, *spans)):
        raise ValueError("Guarded preview compaction tolerances must be finite and positive.")

    def span_is_bounded(start: int, end: int) -> bool:
        return all(
            abs(vectors[end][joint] - vectors[start][joint])
            <= spans[joint] + 1e-12
            for joint in range(len(JOINT_NAMES))
        )

    def follows_segment(start: int, end: int) -> bool:
        if end <= start + 1:
            return True
        a = tuple(vectors[start][joint] / deviations[joint] for joint in range(6))
        b = tuple(vectors[end][joint] / deviations[joint] for joint in range(6))
        direction = tuple(b[joint] - a[joint] for joint in range(6))
        length_squared = sum(value * value for value in direction)
        for index in range(start + 1, end):
            point = tuple(
                vectors[index][joint] / deviations[joint] for joint in range(6)
            )
            if length_squared <= 1e-18:
                projection = a
            else:
                fraction = sum(
                    (point[joint] - a[joint]) * direction[joint]
                    for joint in range(6)
                ) / length_squared
                fraction = min(1.0, max(0.0, fraction))
                projection = tuple(
                    a[joint] + fraction * direction[joint] for joint in range(6)
                )
            if sum(
                (point[joint] - projection[joint]) ** 2 for joint in range(6)
            ) > 1.0 + 1e-12:
                return False
        return True

    selected = [0]
    anchor = 0
    while anchor < len(vectors) - 1:
        last_valid = anchor + 1
        candidate = last_valid
        while candidate < len(vectors):
            if not span_is_bounded(anchor, candidate):
                break
            if not follows_segment(anchor, candidate):
                break
            last_valid = candidate
            candidate += 1
        selected.append(last_valid)
        anchor = last_valid
    compacted = tuple(
        {name: vectors[index][joint] for joint, name in enumerate(JOINT_NAMES)}
        for index in selected
    )
    compacted_times = tuple(times[index] for index in selected)
    return compacted, compacted_times


class DENTORobotWorkflowFacade:
    """Coordinate Step 6 services without depending on DENTOWorkflow widgets."""

    def __init__(
        self,
        logic,
        parameter_node_provider: Callable[[], Any],
        *,
        bridge=None,
    ) -> None:
        self._logic = logic
        self._parameter_node_provider = parameter_node_provider
        self._bridge = bridge or _default_bridge
        self._motion_plan = None
        self._preview_timer = None
        self._preview_index = 0
        self._preview_waypoint_in_flight = False
        self._display_sync_depth = 0
        self._planning_scene_object_count = 0
        self._planning_scene_synchronized = False
        self._phase_sequence = 0
        self._completed_phase = ""
        self._phase_guard_task_fingerprint = ""
        self._preview_exploratory_tool_contact = False
        self._preview_suppressed_tool_contact_samples = 0
        self._preflight_drilling_plan = None
        self._preflight_task_fingerprint = ""
        self._preflight_orientation_commitment: dict[str, object] = {}
        self._runtime_validated_task_home_key = ""
        self._runtime_task_home_evidence: dict[str, Any] = {}
        self._runtime_validated_workspace_key = ""
        self._diagnostic_candidate_paths: dict[int, dict[str, tuple]] = {}

    def setLogic(self, logic) -> None:
        self._logic = logic

    @property
    def motionPlan(self):
        return self._motion_plan

    @property
    def previewActive(self) -> bool:
        return self._preview_timer is not None

    @property
    def completedPhase(self) -> str:
        return self._completed_phase

    @property
    def drillingPreflightReady(self) -> bool:
        return self._preflight_drilling_plan is not None

    @property
    def displaySyncActive(self) -> bool:
        """True while accepted robot state is being mirrored into MRML/UI.

        Parameter-node GUI connectors emit the same spinbox signal for an
        operator edit and a programmatic write.  Callers use this flag to avoid
        interpreting accepted-state display synchronization as a new command.
        """

        return self._display_sync_depth > 0

    def clearTransientState(self) -> None:
        self.stopPreview()
        self._clear_phase_session()
        self._planning_scene_object_count = 0
        self._planning_scene_synchronized = False
        self._runtime_validated_task_home_key = ""
        self._runtime_task_home_evidence = {}
        self._runtime_validated_workspace_key = ""

    def invalidateMotionPlan(self) -> None:
        """Drop task/phase plans without discarding the connected scene audit."""

        self.stopPreview()
        self._clear_phase_session()

    def invalidateWorkspaceRuntimeValidation(self) -> None:
        """Invalidate live workspace evidence while preserving ROS/scene state."""

        self._runtime_validated_workspace_key = ""
        self.invalidateMotionPlan()

    def _clear_phase_session(self) -> None:
        """Invalidate all local state tied to one transient task-guard session."""

        clear_path = getattr(self._bridge, "clear_phase_plan_tcp_path", None)
        if callable(clear_path):
            try:
                clear_path()
            except Exception:
                # A display-only cleanup failure must never mask the state
                # invalidation that owns the actual planning/guard session.
                pass
        self._motion_plan = None
        self._phase_sequence = 0
        self._completed_phase = ""
        self._phase_guard_task_fingerprint = ""
        self._preflight_drilling_plan = None
        self._preflight_task_fingerprint = ""
        self._preflight_orientation_commitment = {}

    def _parameter_node(self):
        return self._parameter_node_provider()

    def _require_context(self):
        parameter_node = self._parameter_node()
        if parameter_node is None:
            raise RuntimeError("Step 6 parameter node is unavailable.")
        if self._logic is None:
            raise RuntimeError("DENTOBOT workflow logic is unavailable.")
        return parameter_node

    def _scene_kind(self, parameter_node) -> str:
        imported = bool(parameter_node.step6PlanningContextImported)
        phantom = bool(self._logic.draftPhantomModelNodes())
        if imported and phantom:
            return "conflict"
        if imported:
            return "case"
        if phantom:
            return "phantom"
        return "none"

    def _scene_preparation_issue(self, parameter_node) -> str:
        if self._scene_kind(parameter_node) != "case":
            return ""
        checker = getattr(self._logic, "step6CaseJawOpeningFreshnessIssues", None)
        if not callable(checker):
            return ""
        issues = checker(parameter_node)
        return " ".join(str(issue) for issue in issues if issue)

    def _scene_placement_issue(self, parameter_node) -> str:
        """Allow a governed target-jaw fallback only for placement operations."""
        if self._scene_kind(parameter_node) != "case":
            return ""
        checker = getattr(
            self._logic,
            "step6CaseJawPlacementFreshnessIssues",
            None,
        )
        if not callable(checker):
            return self._scene_preparation_issue(parameter_node)
        issues = checker(parameter_node)
        return " ".join(str(issue) for issue in issues if issue)

    @staticmethod
    def _display_values(parameter_node) -> tuple[float, ...]:
        return tuple(float(getattr(parameter_node, name)) for name in JOINT_DISPLAY_FIELDS)

    @staticmethod
    def _positions_si(display_values: Sequence[float]) -> dict[str, float]:
        return canonicalize_planning_joint_positions(
            joint_positions_si_from_display(*display_values)
        )

    @staticmethod
    def _task_home_runtime_key(record) -> str:
        if record is None:
            return ""
        return fingerprint(record.to_dict())

    def _strict_guard_policy_fingerprint(self) -> str:
        return fingerprint(
            {
                "channel": "strict",
                "minimumClearanceM": float(
                    self._bridge.ROS2_RESEARCH_MINIMUM_CLEARANCE_M
                ),
                "jointOrder": tuple(self._bridge.ROS2_JOINT_SI_ORDER),
                "planningGroup": self._bridge.ROS2_PLANNING_GROUP,
                "tcpLink": self._bridge.ROS2_TOOL_TCP_LINK,
                "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
            }
        )

    def _workspace_validation_policy_fingerprint(self) -> str:
        return fingerprint(
            {
                "service": "/check_state_validity",
                "planningGroup": self._bridge.ROS2_PLANNING_GROUP,
                "tcpLink": self._bridge.ROS2_TOOL_TCP_LINK,
                "tcpFkSource": "MoveItRobotState",
                "maximumRuntimeSamples": (
                    WORKSPACE_RUNTIME_VALIDATION_MAX_SAMPLES
                ),
                "maximumHomeConnectivitySamples": (
                    WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES
                ),
                "homeConnectivityPlanner": "MoveItExplicitTaskHomeStart",
                "homeConnectivityPlanningAttempts": 1,
                "homeConnectivityAllowedPlanningTimeSec": 2.0,
                "classification": (
                    "StaticCollisionValid+BoundedHomeConnectedSubset"
                ),
                "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
            }
        )

    def _joint_positions_match(
        self,
        expected: Mapping[str, float],
        observed: Mapping[str, float],
    ) -> tuple[bool, float, tuple[str, ...]]:
        missing = tuple(
            name
            for name in JOINT_NAMES
            if name not in expected or name not in observed
        )
        if missing:
            return False, float("inf"), missing
        maximum_error = 0.0
        mismatched = []
        for name in JOINT_NAMES:
            if name == SPINDLE_JOINT_NAME:
                continue
            error = abs(float(observed[name]) - float(expected[name]))
            maximum_error = max(maximum_error, error)
            tolerance = (
                float(self._bridge.ROS2_MONITORED_PRISMATIC_TOLERANCE_M)
                if "Slider" in name
                else float(self._bridge.ROS2_MONITORED_REVOLUTE_TOLERANCE_RAD)
            )
            if error > tolerance:
                mismatched.append(name)
        return not mismatched, maximum_error, tuple(mismatched)

    @staticmethod
    def _home_connectivity_sample_indices(
        samples: Sequence[Any],
        home_positions_si: Mapping[str, float],
    ) -> tuple[int, ...]:
        """Select a deterministic bounded set spanning joint-space evidence."""

        count = len(samples)
        if count == 0:
            return ()
        maximum = min(WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES, count)
        vectors = tuple(sample.joint_positions_si_dict() for sample in samples)
        spans = {
            name: max(float(vector[name]) for vector in vectors)
            - min(float(vector[name]) for vector in vectors)
            for name in JOINT_NAMES
        }
        nearest = min(
            range(count),
            key=lambda index: sum(
                (
                    (float(vectors[index][name]) - float(home_positions_si[name]))
                    / max(abs(spans[name]), 1e-9)
                )
                ** 2
                for name in JOINT_NAMES
            ),
        )
        selected = [nearest]
        for name in JOINT_NAMES:
            for index in (
                min(range(count), key=lambda item: float(vectors[item][name])),
                max(range(count), key=lambda item: float(vectors[item][name])),
            ):
                if index not in selected:
                    selected.append(index)
                if len(selected) >= maximum:
                    return tuple(selected)
        for index in _bounded_even_indices(count, maximum):
            if index not in selected:
                selected.append(index)
            if len(selected) >= maximum:
                break
        return tuple(selected)

    def taskHomeRuntimeValidated(self, parameter_node=None) -> bool:
        parameter_node = parameter_node or self._parameter_node()
        if parameter_node is None or self._logic is None:
            return False
        try:
            if self._logic.taskHomeFreshnessIssues(parameter_node):
                return False
            record = self._logic.taskHomeRecord(parameter_node)
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
        except (RuntimeError, ValueError, TypeError, KeyError):
            return False
        collision_fingerprint = (
            str(collision_audit.audit_fingerprint)
            if collision_audit is not None
            else ""
        )
        return bool(
            record is not None
            and str(getattr(record, "runtime_validation_status", "Unreviewed"))
            == "Validated"
            and str(getattr(record, "collision_audit_fingerprint", ""))
            == collision_fingerprint
            and str(getattr(record, "guard_policy_fingerprint", ""))
            == self._strict_guard_policy_fingerprint()
            and self._runtime_validated_task_home_key
            == self._task_home_runtime_key(record)
            and self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            )
        )

    def workspaceRuntimeValidated(self, parameter_node=None) -> bool:
        parameter_node = parameter_node or self._parameter_node()
        if (
            parameter_node is None
            or not self._runtime_validated_workspace_key
            or self._logic is None
            or not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            )
        ):
            return False
        try:
            payload = json.loads(
                str(parameter_node.step6AssistedLimitProposalJson or "")
            )
            home = self._logic.taskHomeRecord(parameter_node)
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            runtime_valid_count = int(
                payload.get("runtime_valid_sample_count", 0)
            )
            home_evaluated_count = int(
                payload.get("home_connectivity_evaluated_sample_count", 0)
            )
            home_connected_count = int(
                payload.get("home_connected_sample_count", 0)
            )
            accepted_evidence = payload.get("accepted_sample_evidence", ())
            evidence_static_valid_count = sum(
                1
                for sample in accepted_evidence
                if isinstance(sample, dict)
                and isinstance(sample.get("static_state_validity"), dict)
                and sample["static_state_validity"].get("status") == "Valid"
            )
            evidence_home_evaluated_count = sum(
                1
                for sample in accepted_evidence
                if isinstance(sample, dict)
                and isinstance(sample.get("home_connectivity"), dict)
                and sample["home_connectivity"].get("status")
                in {"HomeConnected", "PlanRejected"}
            )
            evidence_home_connected_count = sum(
                1
                for sample in accepted_evidence
                if isinstance(sample, dict)
                and isinstance(sample.get("home_connectivity"), dict)
                and sample["home_connectivity"].get("status")
                == "HomeConnected"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        collision_fingerprint = (
            str(collision_audit.audit_fingerprint)
            if collision_audit is not None
            else ""
        )
        return bool(
            payload.get("runtime_validation_status")
            == WORKSPACE_RUNTIME_VALIDATION_STATUS
            and payload.get("runtime_evidence_schema_version")
            == WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION
            and runtime_valid_count > 0
            and home_evaluated_count > 0
            and home_connected_count > 0
            and payload.get("home_connectivity_status")
            == "BoundedSubsetEvaluated"
            and isinstance(accepted_evidence, list)
            and len(accepted_evidence) == runtime_valid_count
            and evidence_static_valid_count == runtime_valid_count
            and evidence_home_evaluated_count == home_evaluated_count
            and evidence_home_connected_count == home_connected_count
            and self._runtime_validated_workspace_key == fingerprint(payload)
            and self.taskHomeRuntimeValidated(parameter_node)
            and home is not None
            and payload.get("task_home_fingerprint")
            == fingerprint(home.to_dict())
            and payload.get("collision_audit_fingerprint")
            == collision_fingerprint
            and payload.get("workspace_validation_policy_fingerprint")
            == self._workspace_validation_policy_fingerprint()
            and (
                self._scene_kind(parameter_node) != "case"
                or self._planning_scene_synchronized
            )
        )

    def _write_display_values(
        self,
        parameter_node,
        display_values: Sequence[float],
    ) -> None:
        self._display_sync_depth += 1
        modify_token = (
            parameter_node.StartModify()
            if hasattr(parameter_node, "StartModify")
            else None
        )
        try:
            for field_name, value in zip(JOINT_DISPLAY_FIELDS, display_values):
                setattr(parameter_node, field_name, float(value))
        finally:
            try:
                if modify_token is not None:
                    parameter_node.EndModify(modify_token)
            finally:
                self._display_sync_depth = max(0, self._display_sync_depth - 1)

    @staticmethod
    def _display_values_from_si(positions_si: Mapping[str, float]) -> tuple[float, ...]:
        return (
            degrees(float(positions_si[JOINT_NAMES[0]])),
            float(positions_si[JOINT_NAMES[1]]) * 1000.0,
            degrees(float(positions_si[JOINT_NAMES[2]])),
            float(positions_si[JOINT_NAMES[3]]) * 1000.0,
            degrees(float(positions_si[JOINT_NAMES[4]])),
            degrees(float(positions_si[JOINT_NAMES[5]])),
        )

    def capabilities(self) -> RobotCapabilities:
        parameter_node = self._parameter_node()
        stack_status = self._bridge.simulation_stack_status()
        connected = bool(
            parameter_node
            and self._logic
            and self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            )
        )
        mrml_robot_loaded = bool(self._logic and self._logic.robotModelNodes())
        planning_ready = bool(stack_status.planning_ready)
        return RobotCapabilities(
            simulation_only=True,
            stack_state=str(getattr(stack_status.state, "value", stack_status.state)),
            description_ready=bool(stack_status.description_ready),
            planning_ready=planning_ready,
            single_joint_state_source=stack_status.joint_state_publisher_count == 1,
            connected=connected,
            robot_loaded=connected or mrml_robot_loaded,
            move_group_available=planning_ready,
            planning_group=self._bridge.ROS2_PLANNING_GROUP,
            tcp_link=self._bridge.ROS2_TOOL_TCP_LINK,
            ik_available=connected and planning_ready,
            collision_check_available=connected and planning_ready,
            planning_scene_synchronized=self._planning_scene_synchronized,
            planning_scene_object_count=self._planning_scene_object_count,
            reason=str(stack_status.reason or ""),
        )

    def currentRobotState(self) -> RobotWorkflowState:
        parameter_node = self._require_context()
        display_values = self._display_values(parameter_node)
        base = parameter_node.robotBaseTransform
        base_id = base.GetID() if base is not None and hasattr(base, "GetID") else ""
        return RobotWorkflowState(
            scene_kind=self._scene_kind(parameter_node),
            joint_names=JOINT_NAMES,
            joint_display_values=display_values,
            joint_display_units=JOINT_DISPLAY_UNITS,
            joint_positions_si=self._positions_si(display_values),
            base_node_id=base_id,
            base_locked=bool(parameter_node.robotBaseMountLocked),
            ros_motion_active=bool(
                base is not None and self._logic.isRos2MotionControlActive(base)
            ),
            has_motion_plan=bool(
                self._motion_plan is not None
                and getattr(self._motion_plan, "success", False)
            ),
            preview_active=self._preview_timer is not None,
        )

    def connect(self, *, open_motion_module: bool = False) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            scene_kind = self._scene_kind(parameter_node)
            if scene_kind not in {"case", "phantom"}:
                return RobotActionResult(
                    False,
                    "scene_required",
                    "Choose a Step 6 case or draft phantom before connecting.",
                )
            preparation_issue = self._scene_preparation_issue(parameter_node)
            if preparation_issue:
                return RobotActionResult(
                    False,
                    "case_jaw_opening_required",
                    preparation_issue,
                )
            if not self._logic.robotModelNodes():
                return RobotActionResult(
                    False,
                    "local_robot_required",
                    "Load and place the local MRML robot before connecting ROS/MoveIt.",
                )
            if not bool(parameter_node.robotBaseMountLocked):
                return RobotActionResult(
                    False,
                    "base_lock_required",
                    "Provisionally lock the robot base before connecting ROS/MoveIt.",
                )
            base = self._logic.ensureRobotBaseTransform(
                parameter_node.robotBaseTransform
            )
            parameter_node.robotBaseTransform = base
            mrml_models = self._logic.robotModelNodes()
            # Step 6.1 owns runtime creation.  A fresh persistent Task Home is
            # the authoritative bootstrap candidate after case restore, but it
            # is not treated as live evidence: 6.2 must still validate it
            # against the newly connected MoveIt/collision runtime.  If no
            # current Home exists, retain the visible local candidate so a new
            # case can establish one in 6.2.
            bootstrap_source = "visible_joint_controls"
            task_home_revision = 0
            task_home_issues: tuple[str, ...] = ()
            task_home = None
            try:
                task_home_issues = tuple(
                    self._logic.taskHomeFreshnessIssues(parameter_node)
                )
                if not task_home_issues:
                    task_home = self._logic.taskHomeRecord(parameter_node)
            except (RuntimeError, ValueError, TypeError, KeyError) as exc:
                task_home_issues = (str(exc),)
            if task_home is not None:
                bootstrap_positions_si = dict(
                    zip(task_home.joint_names, task_home.joint_positions_si)
                )
                bootstrap_source = "saved_task_home"
                task_home_revision = int(task_home.revision)
            else:
                bootstrap_positions_si = self._positions_si(
                    self._display_values(parameter_node)
                )
            seeded_candidate = self._apply_positions_si(bootstrap_positions_si)
            if not seeded_candidate.success:
                return RobotActionResult(
                    False,
                    "runtime_candidate_seed_failed",
                    "Could not seed the local simulation candidate: "
                    + seeded_candidate.message,
                )
            robot_node, error = self._bridge.connect_dentobot_motion_control(
                base,
                hide_mrml_robot=bool(mrml_models),
                mrml_robot_models=mrml_models,
                open_motion_module=bool(open_motion_module),
                start_stack_if_needed=False,
                initial_joint_positions_si=bootstrap_positions_si,
            )
            if error or robot_node is None:
                return RobotActionResult(
                    False,
                    "connect_failed",
                    error or "ROS 2 robot node was not created.",
                )
            obstacle_count = 0
            if scene_kind == "case":
                try:
                    obstacle_count = self._logic.syncStep6MoveItPlanningScene(
                        parameter_node
                    )
                except (RuntimeError, ValueError, TypeError, OSError) as exc:
                    self._bridge.disconnect_dentobot_motion_control(mrml_models)
                    self._planning_scene_object_count = 0
                    self._planning_scene_synchronized = False
                    return RobotActionResult(
                        False,
                        "planning_scene_sync_failed",
                        "Connected ROS, but collision-scene audit/synchronization "
                        "failed before Task Home validation. The transient ROS "
                        "robot was disconnected. "
                        + str(exc),
                    )
                self._planning_scene_object_count = obstacle_count
                self._planning_scene_synchronized = True
                scene_ready, scene_message = self._bridge.wait_for_collision_guard_world(
                    obstacle_count
                )
                if not scene_ready:
                    self._bridge.disconnect_dentobot_motion_control(mrml_models)
                    self._planning_scene_object_count = 0
                    self._planning_scene_synchronized = False
                    return RobotActionResult(
                        False,
                        "planning_scene_not_acknowledged",
                        "The collision guard did not acknowledge the full case scene. "
                        + scene_message,
                    )
            self._planning_scene_object_count = obstacle_count
            self._planning_scene_synchronized = scene_kind == "case"
            self._clear_phase_session()
            self._runtime_validated_task_home_key = ""
            self._runtime_task_home_evidence = {}
            self._runtime_validated_workspace_key = ""
            candidate_result = self._apply_positions_si(bootstrap_positions_si)
            candidate_status = self.checkStateValidity()
            bootstrap_message = (
                " Seeded the transient robot from the fresh saved Task Home "
                "candidate; 6.2 must still validate it in this live runtime."
                if bootstrap_source == "saved_task_home"
                else " Seeded the transient robot from the visible joint "
                "candidate because no fresh saved Task Home was available."
            )
            return RobotActionResult(
                True,
                "connected",
                "Connected natively inside DENTOWorkflow, aligned the live robot "
                "to the locked base, and synchronized the simulation planning "
                "scene."
                + bootstrap_message
                + " Continue to 6.2 to validate Task Home against this live "
                "runtime.",
                details={
                    "obstacleCount": obstacle_count,
                    "bootstrapSource": bootstrap_source,
                    "savedTaskHomeRevision": task_home_revision,
                    "savedTaskHomeFreshnessIssues": list(task_home_issues),
                    "candidateAccepted": bool(
                        candidate_result.success and candidate_status.success
                    ),
                    "candidateStateMessage": (
                        candidate_status.message
                        if candidate_result.success
                        else candidate_result.message
                    ),
                    "taskHomeRuntimeValidated": False,
                },
                payload=robot_node,
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return RobotActionResult(False, "connect_failed", str(exc))

    def disconnect(self) -> RobotActionResult:
        try:
            self.stopPreview()
            mrml_models = self._logic.robotModelNodes() if self._logic else []
            ok, message = self._bridge.disconnect_dentobot_motion_control(mrml_models)
            if not ok:
                return RobotActionResult(False, "disconnect_failed", message)
            self._planning_scene_synchronized = False
            self._planning_scene_object_count = 0
            self._runtime_validated_task_home_key = ""
            self._runtime_task_home_evidence = {}
            self._runtime_validated_workspace_key = ""
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "disconnected",
                message or "Disconnected the ROS 2 robot; local MRML meshes are visible.",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "disconnect_failed", str(exc))

    def loadRobot(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) not in {"case", "phantom"}:
                return RobotActionResult(
                    False,
                    "scene_required",
                    "Choose a Step 6 case or draft phantom before loading the robot.",
                )
            preparation_issue = self._scene_placement_issue(parameter_node)
            if preparation_issue:
                return RobotActionResult(
                    False,
                    "case_jaw_opening_required",
                    preparation_issue,
                )
            base, models = self._logic.createOrUpdateRobotPlacement(
                parameter_node.robotBaseTransform,
                self._positions_si(self._display_values(parameter_node)),
            )
            parameter_node.robotBaseTransform = base
            phantom_models = self._logic.draftPhantomModelNodes()
            if phantom_models and not bool(parameter_node.robotBaseMountLocked):
                self._logic.positionRobotBaseNearResearchPhantom(base, phantom_models)
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "robot_loaded",
                f"Loaded or reused {len(models)} local robot link models.",
                details={"linkCount": len(models)},
                payload=(base, models),
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "robot_load_failed", str(exc))

    def requestJointValue(self, joint_id: int | str, display_value: float) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if isinstance(joint_id, str):
                try:
                    index = JOINT_NAMES.index(joint_id)
                except ValueError:
                    return RobotActionResult(False, "unknown_joint", f"Unknown joint: {joint_id}")
            else:
                index = int(joint_id)
                if 1 <= index <= len(JOINT_NAMES):
                    index -= 1
            if index < 0 or index >= len(JOINT_NAMES):
                return RobotActionResult(False, "unknown_joint", f"Unknown joint index: {joint_id}")
            value = float(display_value)
            if not isfinite(value):
                return RobotActionResult(False, "invalid_joint_value", "Joint value must be finite.")
            limits = self._logic.getTaskJointLimits(parameter_node)
            limit = getattr(limits, JOINT_LIMIT_FIELDS[index])
            if value < limit.minimum or value > limit.maximum:
                return RobotActionResult(
                    False,
                    "joint_limit",
                    f"{JOINT_NAMES[index]} must remain within {limit.minimum:g} to {limit.maximum:g} {JOINT_DISPLAY_UNITS[index]}.",
                )
            prior_display = list(self._display_values(parameter_node))
            requested_display = list(prior_display)
            requested_display[index] = value
            self._write_display_values(parameter_node, requested_display)
            positions_si = self._positions_si(requested_display)
            base = parameter_node.robotBaseTransform
            if base is not None and self._logic.isRos2MotionControlActive(base):
                ok, message = self._bridge.apply_joint_positions_si_to_motion_control(
                    positions_si
                )
                if not ok:
                    accepted = self._bridge.last_accepted_joint_positions_si()
                    restored = (
                        self._display_values_from_si(accepted)
                        if accepted and all(name in accepted for name in JOINT_NAMES)
                        else tuple(prior_display)
                    )
                    self._write_display_values(parameter_node, restored)
                    return RobotActionResult(False, "joint_rejected", message)
            elif self._logic.robotLinkTransformNodes():
                self._logic.updateRobotJointPoses(positions_si)
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "joint_accepted",
                f"{JOINT_NAMES[index]} set to {value:g} {JOINT_DISPLAY_UNITS[index]}.",
                details={"jointIndex": index, "displayValue": value},
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "joint_update_failed", str(exc))

    def requestCurrentJointState(self) -> RobotActionResult:
        """Validate/publish values already written by MRML GUI binding."""
        if self.displaySyncActive:
            return RobotActionResult(
                True,
                "display_sync_ignored",
                "Accepted robot state is being synchronized to the controls.",
            )
        try:
            parameter_node = self._require_context()
            requested_display = self._display_values(parameter_node)
            positions_si = self._positions_si(requested_display)
            base = parameter_node.robotBaseTransform
            if base is not None and self._logic.isRos2MotionControlActive(base):
                ok, message = self._bridge.apply_joint_positions_si_to_motion_control(
                    positions_si
                )
                if not ok:
                    accepted = self._bridge.last_accepted_joint_positions_si()
                    if accepted and all(name in accepted for name in JOINT_NAMES):
                        self._write_display_values(
                            parameter_node,
                            self._display_values_from_si(accepted),
                        )
                    return RobotActionResult(False, "joint_rejected", message)
            elif self._logic.robotLinkTransformNodes():
                self._logic.updateRobotJointPoses(positions_si)
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "joint_state_accepted",
                "Accepted the current six-joint simulation state.",
                payload=positions_si,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "joint_update_failed", str(exc))

    def setBasePose(self, matrix_world_ras_mm) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if parameter_node.robotBaseMountLocked:
                return RobotActionResult(False, "base_locked", "Unlock the robot base before moving it.")
            base = self._logic.ensureRobotBaseTransform(parameter_node.robotBaseTransform)
            parameter_node.robotBaseTransform = base
            base.SetAndObserveTransformNodeID(None)
            base.SetMatrixTransformToParent(matrix_world_ras_mm)
            base.SetAttribute(
                self._logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
                self._logic.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
            )
            base.SetAttribute("DENTOBOT.PlacementWarning", None)
            self._planning_scene_synchronized = False
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "base_pose_updated",
                "Updated the unreviewed Manual Simulation Base in world RAS millimetres.",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_pose_failed", str(exc))

    def lockBase(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) not in {"case", "phantom"}:
                return RobotActionResult(False, "scene_required", "Choose a Step 6 scene before locking the base.")
            preparation_issue = self._scene_placement_issue(parameter_node)
            if preparation_issue:
                return RobotActionResult(
                    False,
                    "case_jaw_opening_required",
                    preparation_issue,
                )
            if not (self._logic.robotModelNodes() or self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform)):
                return RobotActionResult(False, "robot_required", "Load the ROS robot or local fallback before locking the base.")
            self._logic.setRobotBaseMountLocked(parameter_node, True)
            obstacle_count = 0
            if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                obstacle_count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
                self._planning_scene_object_count = obstacle_count
                self._planning_scene_synchronized = True
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "base_locked",
                "Manual Simulation Base reviewed and locked for diagnostic use; "
                f"{obstacle_count} MoveIt collision surface(s) synchronized. "
                "This is not forehead or registration evidence.",
                details={"obstacleCount": obstacle_count},
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_lock_failed", str(exc))

    def unlockBase(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            self._logic.setRobotBaseMountLocked(parameter_node, False)
            self._planning_scene_synchronized = False
            self._runtime_validated_task_home_key = ""
            self._runtime_task_home_evidence = {}
            self._runtime_validated_workspace_key = ""
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "base_unlocked",
                "Manual Simulation Base unlocked for direct adjustment.",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_unlock_failed", str(exc))

    def syncPlanningScene(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            preparation_issue = self._scene_preparation_issue(parameter_node)
            if preparation_issue:
                return RobotActionResult(
                    False,
                    "case_jaw_opening_required",
                    preparation_issue,
                )
            if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                return RobotActionResult(False, "ros_required", "Connect ROS 2 Motion Control before syncing collision objects.")
            count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
            audit = self._logic.collisionSceneAuditRecord(parameter_node)
            self._planning_scene_object_count = count
            self._planning_scene_synchronized = True
            if not self.taskHomeRuntimeValidated(parameter_node):
                self._runtime_validated_workspace_key = ""
            return RobotActionResult(
                True,
                "planning_scene_synced",
                f"Audited {count} per-object Step 6 collision surface(s): "
                "the collision guard acknowledged matching MoveIt IDs and bounds.",
                details={
                    "obstacleCount": count,
                    "auditFingerprint": (
                        audit.audit_fingerprint if audit is not None else ""
                    ),
                    "runtimeAcknowledged": bool(
                        audit
                        and audit.runtime_acknowledgement.get("status")
                        == "Acknowledged"
                    ),
                },
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            self._planning_scene_synchronized = False
            return RobotActionResult(False, "planning_scene_failed", str(exc))

    def checkStateValidity(self) -> RobotActionResult:
        try:
            state = self.currentRobotState()
            if not state.ros_motion_active:
                return RobotActionResult(
                    True,
                    "draft_state_only",
                    "Local MRML state is available; MoveIt/FCL validity requires a ROS 2 connection.",
                    details={"authoritative": False},
                )
            status = self._bridge.joint_command_status()
            if status is None:
                return RobotActionResult(False, "status_unavailable", "No fresh MoveIt joint-validity status is available.")
            return RobotActionResult(
                bool(status.accepted),
                "state_valid" if status.accepted else "state_invalid",
                status.reason,
                details={
                    "authoritative": True,
                    "minimumClearanceMm": float(status.minimum_clearance_m) * 1000.0,
                    "minimumSelfDistanceMm": None if status.minimum_self_distance_m is None else float(status.minimum_self_distance_m) * 1000.0,
                    "minimumWorldDistanceMm": None if status.minimum_world_distance_m is None else float(status.minimum_world_distance_m) * 1000.0,
                    "firstBody": status.first_body,
                    "secondBody": status.second_body,
                    "worldObjectCount": status.world_object_count,
                },
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "state_check_failed", str(exc))

    def saveTaskHome(self) -> RobotActionResult:
        """Persist a live, collision-accepted, monitored pose as Task Home."""

        try:
            parameter_node = self._require_context()
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                return RobotActionResult(
                    False,
                    "runtime_required",
                    "Connect ROS/MoveIt in 6.1 before saving Task Home.",
                )
            if (
                self._scene_kind(parameter_node) == "case"
                and not self._planning_scene_synchronized
            ):
                return RobotActionResult(
                    False,
                    "planning_scene_required",
                    "Synchronize and audit the case collision scene before saving Task Home.",
                )
            candidate_positions = self._positions_si(
                self._display_values(parameter_node)
            )
            accepted = self._apply_positions_si(candidate_positions)
            if not accepted.success:
                return RobotActionResult(
                    False,
                    "task_home_collision_rejected",
                    "Task Home was not saved because the strict collision guard rejected it. "
                    + accepted.message,
                )
            state_validity = self.checkStateValidity()
            if not state_validity.success or not bool(
                state_validity.details.get("authoritative", False)
            ):
                return RobotActionResult(
                    False,
                    "task_home_state_invalid",
                    "Task Home was not saved because no authoritative accepted MoveIt/FCL state is current. "
                    + state_validity.message,
                )
            monitored_ok, monitored_message, monitored, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    candidate_positions
                )
            )
            if not monitored_ok:
                return RobotActionResult(
                    False,
                    "task_home_monitor_mismatch",
                    "Task Home was not saved. " + monitored_message,
                    details={
                        "expectedJointPositionsSi": dict(candidate_positions),
                        "monitoredJointPositionsSi": monitored,
                        "maximumJointError": monitored_error,
                    },
                )
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            collision_audit_fingerprint = (
                str(collision_audit.audit_fingerprint)
                if collision_audit is not None
                else ""
            )
            guard_policy_fingerprint = self._strict_guard_policy_fingerprint()
            record = self._logic.saveCurrentTaskHome(
                parameter_node,
                runtime_validation={
                    "runtimeValidationStatus": "Validated",
                    "collisionAuditFingerprint": collision_audit_fingerprint,
                    "guardPolicyFingerprint": guard_policy_fingerprint,
                    "validatedAtUtc": datetime.now(timezone.utc).isoformat(),
                    "minimumClearanceMm": state_validity.details.get(
                        "minimumClearanceMm"
                    ),
                    "worldObjectCount": state_validity.details.get(
                        "worldObjectCount", 0
                    ),
                },
            )
            self._runtime_validated_workspace_key = ""
            self._runtime_validated_task_home_key = self._task_home_runtime_key(record)
            self._runtime_task_home_evidence = {
                "jointPositionsSi": dict(candidate_positions),
                "monitoredJointPositionsSi": monitored,
                "maximumJointError": monitored_error,
                "minimumClearanceMm": state_validity.details.get(
                    "minimumClearanceMm"
                ),
                "worldObjectCount": state_validity.details.get(
                    "worldObjectCount"
                ),
            }
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "task_home_saved",
                f"Saved and live-validated Task Home revision {record.revision} "
                "against the synchronized simulation scene.",
                details={
                    "revision": record.revision,
                    "runtimeValidated": True,
                    **self._runtime_task_home_evidence,
                },
                payload=record,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "task_home_failed", str(exc))

    def applyTaskHome(self) -> RobotActionResult:
        """Plan current-to-Home in MoveIt, then apply it through the guard.

        MoveIt owns global path feasibility from the monitored current state.
        Every returned waypoint is then submitted to the strict simulation
        guard, which remains authoritative for joint bounds, self/world
        collision, and configured clearance. This is not actuator homing or
        hardware execution.
        """

        try:
            parameter_node = self._require_context()
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                return RobotActionResult(
                    False,
                    "runtime_required",
                    "Connect ROS/MoveIt in 6.1 before applying Task Home.",
                )
            if (
                self._scene_kind(parameter_node) == "case"
                and not self._planning_scene_synchronized
            ):
                return RobotActionResult(
                    False,
                    "planning_scene_required",
                    "Synchronize and audit the case collision scene before applying Task Home.",
                )
            issues = self._logic.taskHomeFreshnessIssues(parameter_node)
            if issues:
                return RobotActionResult(False, "task_home_stale", " ".join(issues))
            record = self._logic.taskHomeRecord(parameter_node)
            prior_home_fingerprint = fingerprint(record.to_dict())
            home_positions = dict(
                zip(record.joint_names, record.joint_positions_si)
            )
            monitored_reader = getattr(
                self._bridge, "monitored_joint_positions_si", None
            )
            monitored_start = (
                monitored_reader() if callable(monitored_reader) else {}
            )
            if not monitored_start or any(
                name not in monitored_start for name in JOINT_NAMES
            ):
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                return RobotActionResult(
                    False,
                    "task_home_start_state_unavailable",
                    "MoveIt did not provide a complete monitored current state; "
                    "Task Home planning was not attempted.",
                )
            already_at_home, start_home_error, start_mismatches = (
                self._joint_positions_match(home_positions, monitored_start)
            )
            plan = None
            planned_waypoints: tuple[Mapping[str, float], ...] = ()
            if already_at_home:
                planned_waypoints = (home_positions,)
            else:
                plan = self._bridge.plan_moveit_joint_goal(
                    start_joint_positions_si=monitored_start,
                    goal_joint_positions_si=home_positions,
                    planner_context="monitored_current_to_task_home",
                )
                if not plan.success or not plan.waypoint_joint_vectors_si:
                    self._runtime_validated_task_home_key = ""
                    self._runtime_task_home_evidence = {}
                    return RobotActionResult(
                        False,
                        "task_home_moveit_plan_failed",
                        "MoveIt could not plan a collision-aware transition from "
                        "the monitored current state to Task Home. "
                        + plan.message,
                        details={
                            "monitoredStartJointPositionsSi": monitored_start,
                            "taskHomeJointPositionsSi": home_positions,
                            "maximumStartHomeJointError": start_home_error,
                            "mismatchedJoints": start_mismatches,
                            "nativePlannerMessage": plan.native_planner_message,
                        },
                    )
                planned_waypoints = tuple(plan.waypoint_joint_vectors_si)
            for waypoint_index, waypoint in enumerate(planned_waypoints):
                result = self._apply_positions_si(waypoint)
                if not result.success:
                    self._runtime_validated_task_home_key = ""
                    self._runtime_task_home_evidence = {}
                    return RobotActionResult(
                        False,
                        "task_home_guard_rejected",
                        f"The strict simulation guard rejected MoveIt Task Home "
                        f"waypoint {waypoint_index + 1}/{len(planned_waypoints)}. "
                        + result.message,
                        details={
                            "rejectedWaypointIndex": waypoint_index,
                            "plannedWaypointCount": len(planned_waypoints),
                            "moveItPlanMessage": (
                                plan.message if plan is not None else "Already at Home."
                            ),
                        },
                    )
            monitored_ok, monitored_message, monitored, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(home_positions)
            )
            if not monitored_ok:
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                return RobotActionResult(
                    False,
                    "task_home_monitor_mismatch",
                    "The collision guard accepted Task Home, but MoveIt's monitored "
                    "current state did not converge to it. "
                    + monitored_message,
                    details={
                        "expectedJointPositionsSi": home_positions,
                        "monitoredJointPositionsSi": monitored,
                        "maximumJointError": monitored_error,
                    },
                )
            state_validity = self.checkStateValidity()
            if not state_validity.success or not bool(
                state_validity.details.get("authoritative", False)
            ):
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                return RobotActionResult(
                    False,
                    "task_home_state_invalid",
                    "Task Home did not retain an accepted authoritative runtime state. "
                    + state_validity.message,
                )
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            collision_audit_fingerprint = (
                str(collision_audit.audit_fingerprint)
                if collision_audit is not None
                else ""
            )
            guard_policy_fingerprint = self._strict_guard_policy_fingerprint()
            if (
                str(getattr(record, "runtime_validation_status", "Unreviewed"))
                != "Validated"
                or str(getattr(record, "collision_audit_fingerprint", ""))
                != collision_audit_fingerprint
                or str(getattr(record, "guard_policy_fingerprint", ""))
                != guard_policy_fingerprint
            ):
                record = self._logic.recordTaskHomeRuntimeValidation(
                    parameter_node,
                    runtime_validation={
                        "collisionAuditFingerprint": collision_audit_fingerprint,
                        "guardPolicyFingerprint": guard_policy_fingerprint,
                        "validatedAtUtc": datetime.now(timezone.utc).isoformat(),
                        "minimumClearanceMm": state_validity.details.get(
                            "minimumClearanceMm"
                        ),
                        "worldObjectCount": state_validity.details.get(
                            "worldObjectCount", 0
                        ),
                    },
                )
            if fingerprint(record.to_dict()) != prior_home_fingerprint:
                self._runtime_validated_workspace_key = ""
            self._runtime_validated_task_home_key = self._task_home_runtime_key(record)
            self._runtime_task_home_evidence = {
                "jointPositionsSi": home_positions,
                "monitoredStartJointPositionsSi": monitored_start,
                "monitoredJointPositionsSi": monitored,
                "maximumJointError": monitored_error,
                "maximumStartHomeJointError": start_home_error,
                "moveItPlanRequired": not already_at_home,
                "moveItPlanWaypointCount": len(planned_waypoints),
                "moveItPlanMessage": (
                    plan.message if plan is not None else "Already at Task Home."
                ),
                "minimumClearanceMm": state_validity.details.get(
                    "minimumClearanceMm"
                ),
                "worldObjectCount": state_validity.details.get(
                    "worldObjectCount"
                ),
            }
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "task_home_applied",
                (
                    "Task Home already matched the monitored MoveIt state; the "
                    "strict simulation guard revalidated it and retained the "
                    "authoritative state."
                    if already_at_home
                    else
                    "MoveIt planned the monitored-current-to-Home transition, "
                    "every waypoint passed the strict simulation guard, and the "
                    "monitored MoveIt state now matches Task Home."
                ),
                details={
                    "runtimeValidated": True,
                    **self._runtime_task_home_evidence,
                },
                payload=record,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "task_home_failed", str(exc))

    def reviewAssistedLimits(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                return RobotActionResult(
                    False,
                    "runtime_required",
                    "Connect ROS/MoveIt in 6.1 before reviewing workspace limits.",
                )
            if not self.taskHomeRuntimeValidated(parameter_node):
                return RobotActionResult(
                    False,
                    "task_home_runtime_validation_required",
                    "Validate Task Home in this runtime before reviewing workspace limits.",
                )
            try:
                proposal_evidence = json.loads(
                    str(parameter_node.step6AssistedLimitProposalJson or "")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                proposal_evidence = {}
            if (
                proposal_evidence.get("runtime_validation_status")
                != WORKSPACE_RUNTIME_VALIDATION_STATUS
            ):
                return RobotActionResult(
                    False,
                    "workspace_runtime_validation_required",
                    "Generate a MoveIt-validated workspace in 6.3 before reviewing its envelope.",
                )
            if not self.workspaceRuntimeValidated(parameter_node):
                return RobotActionResult(
                    False,
                    "workspace_runtime_revalidation_required",
                    "The saved workspace is not validated in this ROS/MoveIt "
                    "session. Revalidate the saved evidence in 6.3, or regenerate "
                    "it if replay fails, before review.",
                )
            # Parameter-node GUI connectors emit the same limit-spinbox signal
            # for operator edits and for these accepted programmatic writes.
            # Keep the display-sync guard active until all six values and the
            # reviewed proposal have been committed so the widget does not
            # delete the workspace it has just accepted.
            self._display_sync_depth += 1
            try:
                proposal = self._logic.reviewAndApplyAssistedTaskLimits(
                    parameter_node
                )
            finally:
                self._display_sync_depth = max(0, self._display_sync_depth - 1)
            self._runtime_validated_workspace_key = fingerprint(proposal)
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "assisted_limits_reviewed",
                "Reviewed and applied the workspace-assisted task limits.",
                payload=proposal,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "assisted_limits_failed", str(exc))

    def revalidateSavedWorkspace(self) -> RobotActionResult:
        """Replay persisted 6.3 evidence in the current ROS/MoveIt session.

        This deliberately does not regenerate Halton samples or change the
        reviewed assisted envelope.  It rechecks every retained static state,
        verifies authoritative TCP FK against the saved coordinates, and
        replans the previously evaluated Home-connectivity subset.
        """

        try:
            parameter_node = self._require_context()
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                raise ValueError("Connect ROS/MoveIt in 6.1 first.")
            if not self.taskHomeRuntimeValidated(parameter_node):
                raise ValueError(
                    "Apply and live-validate the saved Task Home in 6.2 first."
                )
            try:
                payload = json.loads(
                    str(parameter_node.step6AssistedLimitProposalJson or "")
                )
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("No valid saved 6.3 workspace evidence exists.") from exc
            evidence = payload.get("accepted_sample_evidence")
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(
                    "The saved package has no replayable workspace sample evidence; "
                    "generate 6.3 once."
                )
            home = self._logic.taskHomeRecord(parameter_node)
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            collision_fingerprint = (
                str(collision_audit.audit_fingerprint)
                if collision_audit is not None
                else ""
            )
            prerequisite_issues = []
            if payload.get("runtime_validation_status") != (
                WORKSPACE_RUNTIME_VALIDATION_STATUS
            ):
                prerequisite_issues.append("unsupported saved validation status")
            if payload.get("runtime_evidence_schema_version") != (
                WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION
            ):
                prerequisite_issues.append("unsupported workspace evidence schema")
            if home is None or payload.get("task_home_fingerprint") != fingerprint(
                home.to_dict()
            ):
                prerequisite_issues.append("saved evidence belongs to another Task Home")
            if payload.get("collision_audit_fingerprint") != collision_fingerprint:
                prerequisite_issues.append("saved evidence belongs to another collision scene")
            if payload.get("workspace_validation_policy_fingerprint") != (
                self._workspace_validation_policy_fingerprint()
            ):
                prerequisite_issues.append("workspace validation policy changed")
            if prerequisite_issues:
                raise ValueError(
                    "Saved workspace cannot be replayed safely: "
                    + "; ".join(prerequisite_issues)
                    + ". Regenerate 6.3."
                )
            home_positions = dict(zip(home.joint_names, home.joint_positions_si))
            static_valid_count = 0
            home_evaluated_count = 0
            home_connected_count = 0
            rejected_messages: list[str] = []
            scene_refreshed = False
            maximum_fk_difference_mm = 0.0
            for evidence_index, sample in enumerate(evidence):
                if not isinstance(sample, dict):
                    raise ValueError(
                        f"Saved workspace sample {evidence_index} is malformed."
                    )
                names = tuple(sample.get("joint_names", ()))
                values = tuple(sample.get("joint_positions_si", ()))
                if len(names) != len(JOINT_NAMES) or len(values) != len(JOINT_NAMES):
                    raise ValueError(
                        f"Saved workspace sample {evidence_index} lacks six joints."
                    )
                positions = {
                    str(name): float(value) for name, value in zip(names, values)
                }
                valid, validity_message, authoritative = (
                    self._bridge.check_moveit_static_joint_state(positions)
                )
                if not authoritative:
                    raise RuntimeError(
                        "MoveIt did not return authoritative state validity for "
                        f"saved sample {evidence_index}: {validity_message}"
                    )
                sample["static_state_validity"] = {
                    "status": "Valid" if valid else "RejectedOnReplay",
                    "authoritative": True,
                    "message": _bounded_text(validity_message),
                }
                if not valid:
                    rejected_messages.append(
                        f"sample {evidence_index}: {validity_message}"
                    )
                    continue
                fk_ok, fk_message, tcp_base_mm = (
                    self._bridge.compute_moveit_static_tcp_pose_base_mm(positions)
                )
                if not fk_ok or tcp_base_mm is None:
                    raise RuntimeError(
                        f"MoveIt TCP FK failed for saved sample {evidence_index}: "
                        + fk_message
                    )
                saved_tcp = tuple(float(value) for value in sample.get("tcp_base_mm", ()))
                if len(saved_tcp) != 3:
                    raise ValueError(
                        f"Saved workspace sample {evidence_index} lacks TCP coordinates."
                    )
                difference_mm = sum(
                    (float(tcp_base_mm[index]) - saved_tcp[index]) ** 2
                    for index in range(3)
                ) ** 0.5
                maximum_fk_difference_mm = max(
                    maximum_fk_difference_mm,
                    difference_mm,
                )
                if difference_mm > 1e-6:
                    raise ValueError(
                        "Saved workspace TCP geometry no longer matches MoveIt FK: "
                        f"sample {evidence_index} differs by {difference_mm:.9g} mm."
                    )
                sample["tcp_fk"] = {
                    "source": "MoveItRobotState",
                    "message": _bounded_text(fk_message),
                    "saved_difference_mm": difference_mm,
                }
                static_valid_count += 1
                connectivity = sample.get("home_connectivity")
                if not isinstance(connectivity, dict) or connectivity.get("status") not in {
                    "HomeConnected",
                    "PlanRejected",
                }:
                    continue
                home_evaluated_count += 1
                matches_home, maximum_delta, mismatched = (
                    self._joint_positions_match(home_positions, positions)
                )
                if matches_home:
                    connectivity.update(
                        {
                            "status": "HomeConnected",
                            "method": "IdentityAtTaskHomeReplay",
                            "maximum_start_goal_delta": maximum_delta,
                            "waypoint_count": 1,
                            "message": "Saved sample still matches live Task Home.",
                        }
                    )
                    home_connected_count += 1
                    continue
                path = self._bridge.plan_moveit_joint_goal(
                    start_joint_positions_si=home_positions,
                    goal_joint_positions_si=positions,
                    refresh_planning_scene=not scene_refreshed,
                    planning_attempts=1,
                    allowed_planning_time_sec=2.0,
                    planner_context="task_home_to_saved_workspace_sample_replay",
                )
                scene_refreshed = True
                connectivity.update(
                    {
                        "status": "HomeConnected" if path.success else "PlanRejected",
                        "method": "MoveItExplicitTaskHomeReplay",
                        "maximum_start_goal_delta": maximum_delta,
                        "mismatched_joints": list(mismatched),
                        "waypoint_count": len(path.waypoint_joint_vectors_si),
                        "planner_start_source": path.planner_start_source,
                        "message": _bounded_text(path.message),
                        "native_planner_message": _bounded_text(
                            path.native_planner_message
                        ),
                    }
                )
                if path.success:
                    home_connected_count += 1
                elif len(rejected_messages) < 8:
                    rejected_messages.append(
                        f"Home→sample {evidence_index}: {path.message}"
                    )
            if static_valid_count != len(evidence):
                raise RuntimeError(
                    f"Saved workspace replay rejected {len(evidence) - static_valid_count}/"
                    f"{len(evidence)} retained state(s). "
                    + "; ".join(rejected_messages[:8])
                )
            if home_evaluated_count <= 0 or home_connected_count <= 0:
                raise RuntimeError(
                    "Saved workspace replay found no current Home-connected sample. "
                    + "; ".join(rejected_messages[:8])
                )
            payload.update(
                {
                    "runtime_valid_sample_count": static_valid_count,
                    "home_connectivity_evaluated_sample_count": home_evaluated_count,
                    "home_connected_sample_count": home_connected_count,
                    "home_connectivity_rejected_sample_count": (
                        home_evaluated_count - home_connected_count
                    ),
                    "accepted_sample_evidence": evidence,
                    "maximum_local_moveit_fk_difference_mm": (
                        maximum_fk_difference_mm
                    ),
                    "revalidated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime_revalidation_method": "PersistedEvidenceReplay",
                }
            )
            parameter_node.step6AssistedLimitProposalJson = canonical_json(payload)
            self._runtime_validated_workspace_key = fingerprint(payload)
            self._logic.invalidateStep6TaskConfirmation(
                parameter_node,
                "Workspace evidence was replayed in a new ROS/MoveIt session; reconfirm 6.4.",
            )
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "saved_workspace_revalidated",
                f"Revalidated all {static_valid_count} saved workspace states and "
                f"reconfirmed {home_connected_count}/{home_evaluated_count} "
                "bounded Task-Home connections in the current MoveIt scene. "
                "The reviewed limits were preserved; reconfirm the immutable task in 6.4.",
                details={
                    "staticValidSampleCount": static_valid_count,
                    "homeConnectivityEvaluatedSampleCount": home_evaluated_count,
                    "homeConnectedSampleCount": home_connected_count,
                    "maximumSavedFkDifferenceMm": maximum_fk_difference_mm,
                    "reviewedLimitsPreserved": bool(payload.get("reviewed")),
                },
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            self._runtime_validated_workspace_key = ""
            self.invalidateMotionPlan()
            return RobotActionResult(False, "saved_workspace_revalidation_failed", str(exc))

    def confirmTask(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if not self.taskHomeRuntimeValidated(parameter_node):
                return RobotActionResult(
                    False,
                    "task_home_runtime_validation_required",
                    "Apply or save Task Home in the current ROS/MoveIt session before confirming the task.",
                )
            if not self._logic.assistedTaskLimitsReviewed(parameter_node):
                return RobotActionResult(
                    False,
                    "assisted_limits_required",
                    "Generate and review the live workspace-assisted limits before confirming the task.",
                )
            if not self.workspaceRuntimeValidated(parameter_node):
                return RobotActionResult(
                    False,
                    "workspace_runtime_revalidation_required",
                    "Revalidate or regenerate the workspace in the current "
                    "ROS/MoveIt session before task confirmation.",
                )
            try:
                workspace_evidence = json.loads(
                    str(parameter_node.step6AssistedLimitProposalJson or "")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                workspace_evidence = {}
            home = self._logic.taskHomeRecord(parameter_node)
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            expected_collision_fingerprint = (
                str(collision_audit.audit_fingerprint)
                if collision_audit is not None
                else ""
            )
            workspace_issues = []
            if (
                workspace_evidence.get("runtime_validation_status")
                != WORKSPACE_RUNTIME_VALIDATION_STATUS
            ):
                workspace_issues.append(
                    "Workspace samples lack current MoveIt static-validity and "
                    "bounded Home-connectivity evidence."
                )
            if int(
                workspace_evidence.get("home_connected_sample_count", 0) or 0
            ) <= 0:
                workspace_issues.append(
                    "Workspace evidence contains no sample planned successfully from Task Home."
                )
            if workspace_evidence.get("task_home_fingerprint") != fingerprint(
                home.to_dict()
            ):
                workspace_issues.append("Workspace evidence belongs to another Task Home.")
            if (
                workspace_evidence.get("collision_audit_fingerprint")
                != expected_collision_fingerprint
            ):
                workspace_issues.append(
                    "Workspace evidence belongs to another collision-scene audit."
                )
            if (
                workspace_evidence.get(
                    "workspace_validation_policy_fingerprint"
                )
                != self._workspace_validation_policy_fingerprint()
            ):
                workspace_issues.append(
                    "Workspace evidence uses another static-validation policy."
                )
            if workspace_issues:
                return RobotActionResult(
                    False,
                    "workspace_runtime_validation_stale",
                    " ".join(workspace_issues),
                )
            if (
                self._scene_kind(parameter_node) == "case"
                and not self._planning_scene_synchronized
            ):
                return RobotActionResult(
                    False,
                    "planning_scene_required",
                    "The audited collision scene is not current in this runtime.",
                )
            home_positions = dict(zip(home.joint_names, home.joint_positions_si))
            monitored_ok, monitored_message, monitored, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    home_positions,
                    timeout_sec=1.0,
                )
            )
            if not monitored_ok:
                return RobotActionResult(
                    False,
                    "task_home_monitor_mismatch",
                    "Task confirmation requires the live robot to be at Task Home. "
                    + monitored_message,
                    details={
                        "expectedJointPositionsSi": home_positions,
                        "monitoredJointPositionsSi": monitored,
                        "maximumJointError": monitored_error,
                    },
                )
            snapshot = self._logic.confirmStep6Task(parameter_node)
            self._clear_phase_session()
            return RobotActionResult(
                True,
                "task_confirmed",
                "Confirmed one immutable simulation task snapshot. Any geometry, base, home, limit, tool, or robot-resource change invalidates it.",
                details={"taskFingerprint": snapshot.snapshot_fingerprint},
                payload=snapshot,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "task_confirmation_failed", str(exc))

    def setTcpGoal(self, matrix_goal_parent) -> RobotActionResult:
        ok, message, goal_node = self._bridge.set_moveit_tcp_goal_matrix(
            matrix_goal_parent
        )
        return RobotActionResult(
            ok,
            "tcp_goal_updated" if ok else "tcp_goal_failed",
            message,
            payload=goal_node,
        )

    def ensureTcpGoal(self) -> RobotActionResult:
        ok, message, goal_node = self._bridge.ensure_moveit_tcp_goal_control()
        return RobotActionResult(
            ok,
            "tcp_goal_ready" if ok else "tcp_goal_failed",
            message,
            payload=goal_node,
        )

    def solveIk(self) -> RobotActionResult:
        ok, message, positions = self._bridge.solve_moveit_tcp_goal()
        return RobotActionResult(
            ok,
            "ik_solved" if ok else "ik_failed",
            message,
            payload=positions,
        )

    def planToGoal(self) -> RobotActionResult:
        self._clear_phase_session()
        result = self._bridge.plan_moveit_joint_goal()
        self._motion_plan = result if result.success else None
        return RobotActionResult(
            result.success,
            "goal_plan_ready" if result.success else "goal_plan_failed",
            result.message,
            details={"waypointCount": len(result.waypoint_joint_vectors_si)},
            payload=result,
        )

    def planAlongTrajectory(self) -> RobotActionResult:
        return self.planDrillingPhase()

    def showDiagnosticCandidate(self, candidate_index: int) -> RobotActionResult:
        """Show one retained last-valid state on the translucent goal robot."""
        try:
            parameter_node = self._require_context()
            payload = str(parameter_node.step6MotionDiagnosticJson or "").strip()
            if not payload:
                raise ValueError("No retained Step 6 motion diagnostic is available.")
            session = parse_motion_diagnostic_session(payload)
            index = int(candidate_index)
            if index < 0 or index >= len(session.candidate_records):
                raise ValueError("Diagnostic candidate index is out of range.")
            record = session.candidate_records[index]
            positions = record.get("last_valid_joint_positions_si")
            if not isinstance(positions, dict):
                return RobotActionResult(
                    False,
                    "diagnostic_state_unavailable",
                    "This candidate did not return a last-valid joint state.",
                    details=record,
                )
            ok, message = self._bridge.show_goal_robot_joint_positions(positions)
            evidence_ok, evidence_message = self._bridge.show_motion_diagnostic_evidence(
                first_invalid_ras_mm=record.get("first_invalid_ras_mm"),
                collision_pairs=record.get("first_invalid_collision_pairs", ()),
            )
            return RobotActionResult(
                ok and evidence_ok,
                (
                    "diagnostic_candidate_shown"
                    if ok and evidence_ok
                    else "diagnostic_candidate_failed"
                ),
                message + " " + evidence_message,
                details=record,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "diagnostic_candidate_failed", str(exc))

    def showDiagnosticCandidatePaths(self, candidate_index: int) -> RobotActionResult:
        """Show all retained display-only TCP paths for one live planner leg."""
        paths = self._diagnostic_candidate_paths.get(int(candidate_index), {})
        if not paths:
            return RobotActionResult(
                False,
                "diagnostic_path_unavailable",
                "This saved diagnostic has no live route waypoints; re-plan Goal 1 to inspect its path.",
            )
        parameter_node = self._require_context()
        results = []
        for stage in ("stage1", "stage2", "stage3"):
            waypoints = tuple(paths.get(stage, ()))
            if len(waypoints) < 2:
                continue
            results.append(
                self._bridge.show_phase_plan_tcp_path(
                    waypoints,
                    parameter_node.robotBaseTransform,
                    phase=stage,
                    clear_existing=not results,
                )
            )
        if not results:
            return RobotActionResult(False, "diagnostic_path_unavailable", "This planner leg retained no drawable path.")
        return RobotActionResult(
            all(ok for ok, _message in results),
            "diagnostic_paths_shown",
            " ".join(message for _ok, message in results)
            + " Failed stages stop at their last returned waypoint and remain non-authorizing.",
        )

    def previewDiagnosticCandidate(
        self,
        candidate_index: int,
        interval_ms: int = 50,
    ) -> RobotActionResult:
        """Animate one retained route on the translucent goal robot only."""
        paths = self._diagnostic_candidate_paths.get(int(candidate_index), {})
        waypoints = tuple(
            waypoint
            for stage in ("stage1", "stage2", "stage3")
            for waypoint in paths.get(stage, ())
        )
        if not waypoints:
            return RobotActionResult(False, "diagnostic_path_unavailable", "This planner leg retained no previewable waypoints.")
        try:
            import qt
        except ImportError:
            return RobotActionResult(False, "qt_unavailable", "Qt is unavailable for diagnostic preview timing.")
        self.stopPreview()
        self._preview_index = 0
        timer = qt.QTimer()
        timer.setInterval(max(20, int(interval_ms)))

        def advance() -> None:
            if self._preview_index >= len(waypoints):
                self.stopPreview()
                return
            self._bridge.show_goal_robot_joint_positions(waypoints[self._preview_index])
            self._preview_index += 1

        timer.timeout.connect(advance)
        timer.start()
        self._preview_timer = timer
        return RobotActionResult(
            True,
            "diagnostic_preview_started",
            f"Display-only preview started for {len(waypoints)} retained waypoint(s); failed legs stop at last-valid evidence.",
        )

    def reviewMotionDiagnostic(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            issues = self._logic.motionDiagnosticFreshnessIssues(parameter_node)
            if issues:
                raise ValueError(" ".join(issues))
            record = self._logic.motionDiagnosticRecord(parameter_node)
            reviewed = build_motion_diagnostic_session(
                state=record.state,
                stale_reason=record.stale_reason,
                task_fingerprint=record.task_fingerprint,
                base_fingerprint=record.base_fingerprint,
                trajectory_fingerprint=record.trajectory_fingerprint,
                robot_profile_fingerprint=record.robot_profile_fingerprint,
                collision_audit_fingerprint=record.collision_audit_fingerprint,
                planning_parameters_fingerprint=record.planning_parameters_fingerprint,
                candidate_records=record.candidate_records,
                selected_candidate_index=record.selected_candidate_index,
                failure_classification=record.failure_classification,
                operator_review_state="Reviewed",
                generated_at_utc=record.generated_at_utc,
                schema_version=record.schema_version,
                stage_outcomes=record.stage_outcomes,
                full_task_outcome=record.full_task_outcome,
            )
            parameter_node.step6MotionDiagnosticJson = canonical_json(
                reviewed.to_dict()
            )
            return RobotActionResult(
                True,
                "motion_diagnostic_reviewed",
                "Marked the current bounded diagnostic evidence as operator-reviewed; "
                "this does not authorize a partial path or hardware execution.",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "motion_diagnostic_review_failed", str(exc))

    def _configure_phase_guard(self, parameter_node, snapshot) -> tuple[bool, str]:
        """Start one fresh transient guard session for the synchronized scene."""

        target_object_id = self._logic.step6TargetCollisionObjectId(parameter_node)
        if not target_object_id:
            return False, "The selected target-tooth collision object is unavailable."
        guidance_object_ids = self._logic.step6GuidanceCollisionObjectIds(
            parameter_node
        )
        if not guidance_object_ids:
            return False, (
                "The approved final guide/template collision object is unavailable. "
                "Re-sync the verified Step 5C planning scene."
            )
        burr_proximity_object_ids = (
            self._logic.step6BurrProximityCollisionObjectIds(parameter_node)
        )
        if target_object_id not in burr_proximity_object_ids:
            return False, (
                "The selected target tooth is missing from the guarded task-anatomy set. "
                "Re-sync the Step 6 planning scene."
            )
        if any(
            object_id not in burr_proximity_object_ids
            for object_id in guidance_object_ids
        ):
            return False, (
                "The approved guide/template is missing from the guarded proximity set. "
                "Re-sync the Step 6 planning scene."
            )
        return self._bridge.configure_task_phase_guard(
            task_fingerprint=snapshot.snapshot_fingerprint,
            target_object_id=target_object_id,
            clearance_exempt_object_ids=burr_proximity_object_ids,
            base_transform=parameter_node.robotBaseTransform,
            entry_ras_mm=snapshot.entry_ras_mm,
            target_ras_mm=snapshot.target_ras_mm,
            corridor_radius_mm=snapshot.corridor_radius_mm,
            approach_standoff_mm=float(parameter_node.step6ApproachStandoffMm),
        )

    def _prepare_phase_guard(self, parameter_node, snapshot) -> tuple[bool, str]:
        count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
        self._planning_scene_object_count = count
        self._planning_scene_synchronized = True
        return self._configure_phase_guard(parameter_node, snapshot)

    def _guarded_preview_checkpoints(
        self,
        waypoints: Sequence[Mapping[str, float]],
        times_sec: Sequence[float],
    ) -> tuple[tuple[dict[str, float], ...], tuple[float, ...]]:
        samples = max(
            1,
            int(self._bridge.ROS2_GUARD_PREVIEW_MAX_INTERPOLATION_SAMPLES),
        )
        return _compact_guarded_waypoints(
            waypoints,
            times_sec,
            maximum_revolute_span_rad=(
                float(self._bridge.ROS2_GUARD_MAX_REVOLUTE_STEP_RAD) * samples
            ),
            maximum_prismatic_span_m=(
                float(self._bridge.ROS2_GUARD_MAX_PRISMATIC_STEP_M) * samples
            ),
        )

    def _motion_diagnostic_candidate_record(
        self,
        parameter_node,
        candidate_index: int,
        result,
    ) -> dict[str, object]:
        last_joint = result.last_valid_joint_positions_si
        margins = None
        minimum_margin = None
        if last_joint and all(name in last_joint for name in JOINT_NAMES):
            display = self._display_values_from_si(last_joint)
            limits = self._logic.getTaskJointLimits(parameter_node)
            minima = limits.as_display_vector()
            maxima = limits.as_display_max_vector()
            margins = [
                {
                    "joint": JOINT_NAMES[index],
                    "unit": JOINT_DISPLAY_UNITS[index],
                    "value": float(display[index]),
                    "to_minimum": float(display[index] - minima[index]),
                    "to_maximum": float(maxima[index] - display[index]),
                }
                for index in range(len(JOINT_NAMES))
            ]
            minimum_margin = min(
                min(item["to_minimum"], item["to_maximum"])
                for item in margins
            )
        return {
            "candidate_index": int(candidate_index),
            "stage": "entry_to_target_preflight",
            "planner_leg": "stage3_entry_to_target_cartesian",
            "route_type": "cartesian",
            "geometrically_distinct": False,
            "axial_roll_deg": GOAL1_CANONICAL_TOOL_ROLL_DEG,
            "success": bool(result.success),
            "message": str(result.message),
            "completion_fraction": max(0.0, min(1.0, float(result.fraction))),
            "completed_distance_mm": float(result.completed_distance_mm),
            "requested_distance_mm": float(result.requested_path_length_mm),
            "waypoint_count": len(result.waypoint_joint_vectors_si),
            "eef_step_mm": (
                float(result.eef_step_m) * 1000.0
                if result.eef_step_m is not None
                else None
            ),
            "last_valid_waypoint_index": int(result.last_valid_waypoint_index),
            "last_valid_joint_positions_si": (
                dict(last_joint) if last_joint else None
            ),
            "last_valid_joint_margins_display": margins,
            "minimum_joint_margin_display": minimum_margin,
            "first_invalid_requested_index": int(
                result.first_invalid_requested_index
            ),
            "first_invalid_ras_mm": (
                list(result.first_invalid_ras_mm)
                if result.first_invalid_ras_mm is not None
                else None
            ),
            "first_invalid_joint_positions_si": (
                dict(result.first_invalid_joint_positions_si)
                if result.first_invalid_joint_positions_si
                else None
            ),
            "collision_aware_ik_at_first_invalid": (
                result.collision_aware_ik_at_first_invalid
            ),
            "kinematics_only_ik_at_first_invalid": (
                result.kinematics_only_ik_at_first_invalid
            ),
            "start_position_error_mm": result.start_position_error_mm,
            "start_orientation_error_deg": result.start_orientation_error_deg,
            "failure_classification": str(
                result.failure_classification
                or ("none" if result.success else "unknown_moveit_failure")
            ),
            "first_invalid_collision_pairs": [
                list(pair) for pair in result.first_invalid_collision_pairs
            ],
            "collision_evidence": (
                "Kinematics-only IK succeeded while collision-aware IK failed."
                if result.failure_classification == "collision_induced_ik_failure"
                else None
            ),
            "shadow_query_authorizing": False,
        }

    def _persist_motion_diagnostic(
        self,
        parameter_node,
        snapshot,
        candidate_results: Sequence[object],
        selected_index: int,
    ):
        collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
        records = tuple(
            self._motion_diagnostic_candidate_record(
                parameter_node,
                index,
                result,
            )
            for index, result in enumerate(candidate_results)
        )
        selected = records[int(selected_index)]
        classification = str(selected["failure_classification"])
        planning_fingerprint = fingerprint(
            {
                "sampleCount": int(parameter_node.robotMotionPlanSampleCount),
                "approachStandoffMm": float(parameter_node.step6ApproachStandoffMm),
                "corridorRadiusMm": float(parameter_node.step6TrajectoryCorridorRadiusMm),
                "eefStepsM": tuple(self._bridge.ROS2_CARTESIAN_EEF_STEP_ATTEMPTS_M),
                "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
                "routePlannerRevision": "full-chain-v1",
            }
        )
        session = build_motion_diagnostic_session(
            state="Current",
            task_fingerprint=snapshot.snapshot_fingerprint,
            base_fingerprint=self._logic.robotBaseFingerprint(parameter_node),
            trajectory_fingerprint=self._logic.step6TrajectoryRevision(parameter_node),
            robot_profile_fingerprint=self._logic.robotProfileFingerprint(),
            collision_audit_fingerprint=collision_audit.audit_fingerprint,
            planning_parameters_fingerprint=planning_fingerprint,
            candidate_records=records,
            selected_candidate_index=int(selected_index),
            failure_classification=classification,
            operator_review_state="Unreviewed",
            stage_outcomes=(
                {
                    "stage": "stage3_drilling",
                    "status": "Passed" if result.success else "Failed",
                    "selected_candidate_index": int(selected_index),
                    "completion_fraction": float(result.fraction),
                    "failure_classification": classification,
                },
            ),
            full_task_outcome={
                "status": "PendingGoal1Assembly" if result.success else "Failed",
                "failure_stage": "" if result.success else "stage3_drilling",
            },
        )
        parameter_node.step6MotionDiagnosticJson = canonical_json(session.to_dict())
        return session

    def _plan_full_drilling_line(
        self,
        parameter_node,
        snapshot,
        start_positions: Mapping[str, float],
        *,
        start_axial_roll_deg: float = 0.0,
    ):
        """Plan Entry→Target with the exact tool frame committed at PreEntry."""

        fixed_roll_deg = float(start_axial_roll_deg)
        if not isfinite(fixed_roll_deg):
            raise ValueError("Committed drilling-frame roll must be finite.")
        result = self._bridge.plan_moveit_cartesian_path(
                entry_ras_mm=snapshot.entry_ras_mm,
                target_ras_mm=snapshot.target_ras_mm,
                sample_count=int(parameter_node.robotMotionPlanSampleCount),
                base_transform=parameter_node.robotBaseTransform,
                avoid_collisions=False,
                minimum_fraction=0.99,
                start_joint_positions_si=start_positions,
                axial_roll_start_deg=fixed_roll_deg,
                axial_roll_end_deg=fixed_roll_deg,
            )
        if not result.success:
            raise RuntimeError(
                "Full Entry-to-Target reachability failed with the external "
                "spindle locked at 0 rad. "
                + result.message
                + " The partial joint path and its last-valid/first-invalid "
                "boundary remain diagnostic evidence; this result does not "
                "yet prove collision, base placement, or workspace failure and "
                "cannot be previewed."
            )
        return result

    @staticmethod
    def _tool_orientation_commitment(
        pose,
        *,
        pre_entry_ras_mm: Sequence[float],
        entry_ras_mm: Sequence[float],
        axial_roll_deg: float,
    ) -> dict[str, object]:
        """Describe the immutable drilling frame selected by Stage 1.

        The trajectory fixes the tool Z axis.  The remaining rotation about
        that axis is obtained from the J6-locked FK solution and is important
        to the posture of arm joints 1–5 even though burr spin is external.
        """

        direction = tuple(
            float(entry_ras_mm[index]) - float(pre_entry_ras_mm[index])
            for index in range(3)
        )
        length = sum(value * value for value in direction) ** 0.5
        if length <= 1.0e-9:
            raise ValueError("PreEntry and Entry cannot define a drilling frame.")
        axis = tuple(value / length for value in direction)
        rotation = tuple(
            tuple(float(pose.GetElement(row, column)) for column in range(3))
            for row in range(3)
        )
        identity = {
            "policy": DRILL_TOOL_FRAME_POLICY,
            "toolAxisRas": axis,
            "rotationRas": rotation,
            "axialFrameRollDeg": float(axial_roll_deg),
            "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
            "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
        }
        return {**identity, "fingerprint": fingerprint(identity)}

    @staticmethod
    def _arm_path_motion_cost(*plans) -> float:
        """Return deterministic joints-1–5 travel for route comparison."""

        waypoints: list[Mapping[str, float]] = []
        for plan in plans:
            if plan is None:
                continue
            for waypoint in plan.waypoint_joint_vectors_si:
                if waypoints and all(
                    abs(float(waypoints[-1][name]) - float(waypoint[name])) <= 1.0e-12
                    for name in JOINT_NAMES[:-1]
                ):
                    continue
                waypoints.append(waypoint)
        return sum(
            sum(
                abs(float(current[name]) - float(previous[name]))
                / (
                    0.08
                    if name == "link-2_Slider-2"
                    else 0.075
                    if name == "link-4_Slider-4"
                    else 2.0 * pi
                )
                for name in JOINT_NAMES[:-1]
            )
            for previous, current in zip(waypoints, waypoints[1:])
        )

    def _goal1_candidate_chain_preflight(
        self,
        parameter_node,
        snapshot,
        candidate: Mapping[str, object],
        strict_plan,
        *,
        pre_entry: Sequence[float],
        entry: Sequence[float],
    ) -> dict[str, object]:
        """Evaluate one Stage-1 frame against the complete fixed-frame chain."""

        fixed_roll_deg = float(candidate["rollDeg"])
        stage1_end = (
            strict_plan.waypoint_joint_vectors_si[-1]
            if strict_plan.waypoint_joint_vectors_si
            else candidate["positions"]
        )
        # Stage 1 ends at the collision-free PreEntry state.  Stage 2 is one
        # immutable-frame Cartesian move from PreEntry to Entry.  MoveIt is
        # asked for the complete kinematic path here; the independent phase
        # guard below remains authoritative for bounds, self/world collision,
        # clearance, corridor progression, and the narrowly configured burr
        # contact exception.  Splitting this path at a guessed TCP distance
        # caused valid burr contact to stop MoveIt before the configured
        # terminal-contact policy could inspect it.
        terminal_plan = self._bridge.plan_moveit_cartesian_path(
            entry_ras_mm=pre_entry,
            target_ras_mm=entry,
            sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount)),
            base_transform=parameter_node.robotBaseTransform,
            avoid_collisions=False,
            minimum_fraction=0.99,
            start_joint_positions_si=stage1_end,
            axial_roll_start_deg=fixed_roll_deg,
            axial_roll_end_deg=fixed_roll_deg,
        )
        # Preserve the legacy axis/terminal fields without duplicating the
        # physical Stage-2 waypoints.  All Stage-2 samples live in terminalPlan.
        axis_plan = replace(
            terminal_plan,
            message=(
                "Stage 2 is validated as one fixed-axis terminal-contact path "
                "by the independent phase guard."
                if terminal_plan.success
                else terminal_plan.message
            ),
            waypoint_joint_vectors_si=(),
            waypoint_times_sec=(),
            requested_path_length_mm=0.0,
            completed_distance_mm=0.0,
            last_valid_waypoint_index=-1,
        )
        if not terminal_plan.success or not terminal_plan.waypoint_joint_vectors_si:
            return {
                "status": "BlockedStage2Cartesian",
                "axisPlan": axis_plan,
                "terminalPlan": terminal_plan,
                "drillingPlan": None,
                "guardValid": False,
                "guardMessage": "",
                "firstInvalidIndex": -1,
                "reason": str(terminal_plan.message),
                "score": (
                    4,
                    -float(terminal_plan.fraction),
                    self._arm_path_motion_cost(terminal_plan),
                    candidate["score"],
                ),
            }

        drilling_plan = self._bridge.plan_moveit_cartesian_path(
            entry_ras_mm=snapshot.entry_ras_mm,
            target_ras_mm=snapshot.target_ras_mm,
            sample_count=int(parameter_node.robotMotionPlanSampleCount),
            base_transform=parameter_node.robotBaseTransform,
            avoid_collisions=False,
            minimum_fraction=0.99,
            start_joint_positions_si=terminal_plan.waypoint_joint_vectors_si[-1],
            axial_roll_start_deg=fixed_roll_deg,
            axial_roll_end_deg=fixed_roll_deg,
        )
        if not drilling_plan.success:
            return {
                "status": "BlockedStage3Cartesian",
                "axisPlan": axis_plan,
                "terminalPlan": terminal_plan,
                "drillingPlan": drilling_plan,
                "guardValid": False,
                "guardMessage": "",
                "firstInvalidIndex": -1,
                "reason": str(drilling_plan.message),
                "score": (
                    2,
                    -float(drilling_plan.fraction),
                    self._arm_path_motion_cost(axis_plan, terminal_plan, drilling_plan),
                    candidate["score"],
                ),
            }

        guard_ready, guard_ready_message = self._configure_phase_guard(
            parameter_node, snapshot
        )
        if not guard_ready:
            return {
                "status": "BlockedPhaseGuardSetup",
                "axisPlan": axis_plan,
                "terminalPlan": terminal_plan,
                "drillingPlan": drilling_plan,
                "guardValid": False,
                "guardMessage": str(guard_ready_message),
                "firstInvalidIndex": -1,
                "reason": str(guard_ready_message),
                "score": (5, 0.0, 0.0, candidate["score"]),
            }

        waypoints = (
            tuple(strict_plan.waypoint_joint_vectors_si)
            + tuple(terminal_plan.waypoint_joint_vectors_si)
            + tuple(drilling_plan.waypoint_joint_vectors_si)
        )
        phases = (
            ("approach",) * len(strict_plan.waypoint_joint_vectors_si)
            + ("terminal_contact",) * len(terminal_plan.waypoint_joint_vectors_si)
            + ("drilling",) * len(drilling_plan.waypoint_joint_vectors_si)
        )
        validate_chain = getattr(
            self._bridge,
            "validate_task_phase_waypoints",
            _default_bridge.validate_task_phase_waypoints,
        )
        guard_valid, guard_message, invalid_index = validate_chain(
            waypoints,
            phases,
            task_fingerprint=snapshot.snapshot_fingerprint,
        )
        motion_cost = self._arm_path_motion_cost(terminal_plan, drilling_plan)
        stage1_count = len(strict_plan.waypoint_joint_vectors_si)
        stage2_count = len(terminal_plan.waypoint_joint_vectors_si)
        if guard_valid:
            status = "Complete"
            rank = 0
        elif invalid_index < 0:
            status = "BlockedPhaseGuard"
            rank = 5
        elif invalid_index < stage1_count:
            status = "BlockedStage1PhaseGuard"
            rank = 5
        elif invalid_index < stage1_count + stage2_count:
            status = "BlockedStage2PhaseGuard"
            rank = 3
        else:
            status = "BlockedStage3PhaseGuard"
            rank = 1
        return {
            "status": status,
            "axisPlan": axis_plan,
            "terminalPlan": terminal_plan,
            "drillingPlan": drilling_plan,
            "guardValid": bool(guard_valid),
            "guardMessage": str(guard_message),
            "firstInvalidIndex": int(invalid_index),
            "reason": "" if guard_valid else str(guard_message),
            # Complete, guard-accepted chains outrank every partial chain.
            # Among them, prefer the least joints-1–5 motion after PreEntry;
            # only then use the existing Stage-1 route score as a tie-break.
            "score": (
                rank,
                0.0,
                motion_cost,
                candidate["score"],
            ),
        }

    def _goal1_pre_entry_ik_candidates(
        self,
        parameter_node,
        pre_entry: Sequence[float],
        entry: Sequence[float],
        home_positions: Mapping[str, float],
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Return the canonical collision-aware PreEntry arm endpoint."""

        candidates: list[dict[str, object]] = []
        failures: list[str] = []
        joint_diagnostic_fn = getattr(
            self._bridge,
            "moveit_joint_goal_diagnostics",
            _default_bridge.moveit_joint_goal_diagnostics,
        )
        seeds: list[tuple[str, Mapping[str, float], Optional[int]]] = [
            ("direct", home_positions, None)
        ]
        try:
            proposal = json.loads(
                str(parameter_node.step6AssistedLimitProposalJson or "")
            )
        except (TypeError, json.JSONDecodeError):
            proposal = {}
        for evidence in proposal.get("accepted_sample_evidence", ()):
            if len(seeds) >= GOAL1_MAX_IK_SEEDS:
                break
            if not isinstance(evidence, dict):
                continue
            names = tuple(evidence.get("joint_names", ()))
            values = tuple(evidence.get("joint_positions_si", ()))
            connectivity = evidence.get("home_connectivity", {})
            if names != JOINT_NAMES or len(values) != len(JOINT_NAMES) or (
                not isinstance(connectivity, dict)
                or connectivity.get("status") != "HomeConnected"
            ):
                continue
            seeds.append(
                (
                    "seeded",
                    canonicalize_planning_joint_positions(dict(zip(names, values))),
                    int(evidence.get("sample_index", len(seeds))),
                )
            )
        seen_solutions: set[tuple[float, ...]] = set()
        for route_type, seed_positions, seed_sample_index in seeds:
            axial_roll_deg = GOAL1_CANONICAL_TOOL_ROLL_DEG
            pose = self._bridge.tool_pose_matrices_world_mm(
                pre_entry,
                entry,
                2,
                axial_roll_start_deg=axial_roll_deg,
                axial_roll_end_deg=axial_roll_deg,
            )[0]
            ok, message, _goal = self._bridge.set_moveit_tcp_goal_matrix(pose)
            if not ok:
                failures.append(f"spindle-locked goal: {message}")
                continue
            ok, message, positions = self._bridge.solve_moveit_tcp_goal(
                seed_joint_positions_si=seed_positions
            )
            if not ok:
                failures.append(f"spindle-locked IK: {message}")
                continue
            valid, validity_message, authoritative = (
                self._bridge.check_moveit_static_joint_state(positions)
            )
            if not authoritative:
                failures.append(
                    "spindle-locked IK state could not be audited: "
                    + validity_message
                )
                continue
            if not valid:
                failures.append(
                    "spindle-locked IK state is invalid after fixing J6 at 0 rad: "
                    + validity_message
                )
                continue
            ok, message, axial_roll_deg = (
                self._bridge.spindle_locked_tcp_roll_deg(
                    positions,
                    entry_ras_mm=pre_entry,
                    target_ras_mm=entry,
                    base_transform=parameter_node.robotBaseTransform,
                )
            )
            if not ok:
                failures.append(message)
                continue
            pose = self._bridge.tool_pose_matrices_world_mm(
                pre_entry,
                entry,
                2,
                axial_roll_start_deg=axial_roll_deg,
                axial_roll_end_deg=axial_roll_deg,
            )[0]
            orientation_commitment = self._tool_orientation_commitment(
                pose,
                pre_entry_ras_mm=pre_entry,
                entry_ras_mm=entry,
                axial_roll_deg=axial_roll_deg,
            )
            joint_diagnostic = joint_diagnostic_fn(home_positions, positions)
            canonical_solution = canonicalize_planning_joint_positions(
                joint_diagnostic["submitted_goal"]
            )
            solution_identity = tuple(
                round(canonical_solution[name], 9) for name in JOINT_NAMES[:-1]
            )
            if solution_identity in seen_solutions:
                continue
            seen_solutions.add(solution_identity)
            deltas = dict(joint_diagnostic["effective_deltas"])
            normalized_deltas = []
            for name in JOINT_NAMES:
                scale = (
                    0.08
                    if name == "link-2_Slider-2"
                    else 0.075
                    if name == "link-4_Slider-4"
                    else 2.0 * pi
                )
                normalized_deltas.append(float(deltas[name]) / scale)
            candidates.append(
                {
                    "rollDeg": float(axial_roll_deg),
                    "pose": pose,
                    "positions": canonicalize_planning_joint_positions(
                        joint_diagnostic["submitted_goal"]
                    ),
                    "routeType": route_type,
                    "seedSampleIndex": seed_sample_index,
                    "requestedPositions": dict(
                        joint_diagnostic["requested_goal"]
                    ),
                    "jointDiagnostic": joint_diagnostic,
                    "orientationCommitment": orientation_commitment,
                    "score": (
                        max(normalized_deltas, default=0.0),
                        sum(value * value for value in normalized_deltas),
                        0.0,
                    ),
                }
            )
        candidates.sort(key=lambda candidate: candidate["score"])
        return candidates, failures

    def _goal1_clearance_waypoints(
        self,
        parameter_node,
        home_positions: Mapping[str, float],
        goal_positions: Mapping[str, float],
    ) -> tuple[dict[str, object], ...]:
        """Return bounded, already Home-connected 6.3 states for a detour.

        These are not invented geometric waypoints.  Each returned state was
        retained by the current workspace proposal after authoritative MoveIt
        static-state validation and a successful Task-Home connection.  Goal 1
        replans both legs in the current scene before accepting the detour.
        """

        try:
            proposal = json.loads(
                str(parameter_node.step6AssistedLimitProposalJson or "")
            )
        except (TypeError, json.JSONDecodeError):
            return ()
        ranked: list[dict[str, object]] = []
        seen: set[tuple[float, ...]] = set()
        joint_diagnostic_fn = getattr(
            self._bridge,
            "moveit_joint_goal_diagnostics",
            _default_bridge.moveit_joint_goal_diagnostics,
        )
        for evidence_index, evidence in enumerate(
            proposal.get("accepted_sample_evidence", ())
        ):
            if not isinstance(evidence, dict):
                continue
            connectivity = evidence.get("home_connectivity")
            if not isinstance(connectivity, dict) or (
                connectivity.get("status") != "HomeConnected"
            ):
                continue
            names = tuple(evidence.get("joint_names", ()))
            values = tuple(evidence.get("joint_positions_si", ()))
            if len(names) != len(JOINT_NAMES) or len(values) != len(JOINT_NAMES):
                continue
            try:
                positions = {
                    str(name): float(value) for name, value in zip(names, values)
                }
                if set(positions) != set(JOINT_NAMES):
                    continue
                identity = tuple(round(positions[name], 12) for name in JOINT_NAMES)
                if identity in seen:
                    continue
                seen.add(identity)
                from_home = joint_diagnostic_fn(home_positions, positions)
                to_goal = joint_diagnostic_fn(positions, goal_positions)
            except (KeyError, TypeError, ValueError):
                continue
            # Prefer a modest, centrally useful bend over an extreme workspace
            # state.  The maximum term prevents one joint from dominating the
            # detour while the sum term gives deterministic tie-breaking.
            score = (
                float(to_goal["maximum_delta"]),
                float(from_home["maximum_delta"]),
                sum(
                    float(value) * float(value)
                    for value in to_goal["effective_deltas"].values()
                ),
                evidence_index,
            )
            ranked.append(
                {
                    "evidenceIndex": evidence_index,
                    "sampleIndex": int(evidence.get("sample_index", evidence_index)),
                    "positions": positions,
                    "tcpBaseMm": tuple(evidence.get("tcp_base_mm", ())),
                    "score": score,
                }
            )
        ranked.sort(key=lambda item: item["score"])
        return tuple(ranked[:GOAL1_MAX_CLEARANCE_WAYPOINTS])

    @staticmethod
    def _merge_goal1_joint_plans(first, second, *, planner_context: str):
        """Join two successful explicit-start MoveIt trajectories."""

        first_waypoints = tuple(first.waypoint_joint_vectors_si)
        second_waypoints = tuple(second.waypoint_joint_vectors_si)
        first_times = tuple(first.waypoint_times_sec)
        second_times = tuple(second.waypoint_times_sec)
        if first_waypoints and second_waypoints:
            duplicate = all(
                abs(
                    float(first_waypoints[-1][name])
                    - float(second_waypoints[0][name])
                )
                <= 1e-10
                for name in JOINT_NAMES
            )
            if duplicate:
                second_waypoints = second_waypoints[1:]
                second_times = second_times[1:]
        return replace(
            second,
            success=True,
            message=(
                "MoveIt planned a collision-aware two-leg Task-Home clearance "
                "route. " + first.message + " " + second.message
            ),
            waypoint_joint_vectors_si=first_waypoints + second_waypoints,
            waypoint_times_sec=_concatenate_waypoint_times(
                first_times,
                second_times,
            ),
            submitted_start_joint_positions_si=(
                first.submitted_start_joint_positions_si
            ),
            monitored_start_joint_positions_si=(
                first.monitored_start_joint_positions_si
            ),
            maximum_monitored_start_error=first.maximum_monitored_start_error,
            planner_start_source=planner_context,
        )

    def _goal1_diagnostic_record(
        self,
        candidate_index: int,
        *,
        stage: str,
        axial_roll_deg: float,
        result,
        route_type: str = "direct",
        clearance: Optional[Mapping[str, object]] = None,
        seed_sample_index: Optional[int] = None,
        segment=None,
    ) -> dict[str, object]:
        """Normalize one Goal 1 planner attempt for persistent diagnostics."""

        last_joint = (
            dict(result.waypoint_joint_vectors_si[-1])
            if result.waypoint_joint_vectors_si
            else None
        )
        collision_pairs = (
            tuple(segment.first_collision_pairs) if segment is not None else ()
        )
        first_collision_fraction = (
            segment.first_collision_fraction if segment is not None else None
        )
        classification = "none" if result.success else (
            "joint_segment_collision"
            if collision_pairs
            else "moveit_joint_plan_failure"
        )
        return {
            "candidate_index": int(candidate_index),
            "stage": str(stage),
            "axial_roll_deg": float(axial_roll_deg),
            "route_type": str(route_type),
            "planner_leg": str(stage),
            "geometrically_distinct": str(route_type) != "direct",
            "clearance_sample_index": (
                int(clearance["sampleIndex"]) if clearance is not None else None
            ),
            "ik_seed_sample_index": (
                int(seed_sample_index) if seed_sample_index is not None else None
            ),
            "success": bool(result.success),
            "message": _bounded_text(result.message),
            "native_planner_message": _bounded_text(
                result.native_planner_message
            ),
            "completion_fraction": 1.0 if result.success else 0.0,
            "completed_distance_mm": 0.0,
            "requested_distance_mm": 0.0,
            "waypoint_count": len(result.waypoint_joint_vectors_si),
            "last_valid_waypoint_index": (
                len(result.waypoint_joint_vectors_si) - 1
            ),
            "last_valid_joint_positions_si": last_joint,
            "first_invalid_requested_index": -1,
            "first_invalid_ras_mm": None,
            "first_invalid_joint_positions_si": None,
            "first_invalid_collision_pairs": [list(pair) for pair in collision_pairs],
            "first_collision_fraction": first_collision_fraction,
            "failure_classification": classification,
            "maximum_start_goal_delta": result.maximum_start_goal_delta,
            "maximum_start_goal_delta_joint": (
                result.maximum_start_goal_delta_joint
            ),
            "per_joint_start_goal_delta": dict(
                result.per_joint_start_goal_delta or {}
            ),
            "path_length_joint_si": sum(
                sum(
                    abs(float(current[name]) - float(previous[name]))
                    for name in JOINT_NAMES[:-1]
                )
                for previous, current in zip(
                    result.waypoint_joint_vectors_si,
                    result.waypoint_joint_vectors_si[1:],
                )
            ),
            "minimum_clearance_m": getattr(segment, "minimum_clearance_m", None),
            "continuous_joint_wrap_adjustments": (
                result.continuous_joint_wrap_adjustments
            ),
            "planner_start_source": result.planner_start_source,
            "shadow_query_authorizing": False,
        }

    def _persist_goal1_diagnostic(
        self,
        parameter_node,
        snapshot,
        records: Sequence[Mapping[str, object]],
        selected_index: int,
        *,
        stage2_status: str = "NotRun",
        stage3_status: str = "NotRun",
        full_task_status: str = "Failed",
        full_task_reason: str = "",
    ):
        collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
        selected = records[int(selected_index)]
        full_task_reason = _bounded_text(full_task_reason)
        failure_stage = str(selected.get("full_chain_failure_stage") or "")
        if not failure_stage:
            if not bool(selected.get("success")):
                failure_stage = "stage1_free_space"
            elif str(stage2_status) not in {"NotRun", "Passed"}:
                failure_stage = "stage2_fixed_axis_terminal"
            elif str(stage3_status) == "Failed":
                failure_stage = "stage3_drilling"
        invalid_composed_index = int(
            selected.get("full_chain_first_invalid_index", -1)
        )
        invalid_stage_index = int(
            selected.get("full_chain_first_invalid_stage_index", -1)
        )
        stage1_reason = (
            str(selected.get("message") or selected.get("failure_classification") or "")
            if not bool(selected.get("success"))
            else ""
        )
        if not full_task_reason and stage1_reason:
            full_task_reason = _bounded_text(stage1_reason)
        stage2_reason = (
            full_task_reason
            if failure_stage.startswith("stage2")
            or (
                str(stage2_status) not in {"NotRun", "Passed"}
                and bool(full_task_reason)
            )
            else ""
        )
        stage3_reason = (
            full_task_reason
            if failure_stage.startswith("stage3")
            or (str(stage3_status) == "Failed" and bool(full_task_reason))
            else ""
        )
        session = build_motion_diagnostic_session(
            state="Current",
            task_fingerprint=snapshot.snapshot_fingerprint,
            base_fingerprint=self._logic.robotBaseFingerprint(parameter_node),
            trajectory_fingerprint=self._logic.step6TrajectoryRevision(parameter_node),
            robot_profile_fingerprint=self._logic.robotProfileFingerprint(),
            collision_audit_fingerprint=collision_audit.audit_fingerprint,
            planning_parameters_fingerprint=fingerprint(
                {
                    "stage": "task_home_to_preentry",
                    "approachStandoffMm": float(
                        parameter_node.step6ApproachStandoffMm
                    ),
                    "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                    "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
                    "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                    "routePlannerRevision": "stage1-frame-full-chain-v4",
                    "stage2ContactPolicy": "phase_guard_evidence_based",
                    "maximumClearanceWaypoints": GOAL1_MAX_CLEARANCE_WAYPOINTS,
                    "maximumIkSeeds": GOAL1_MAX_IK_SEEDS,
                }
            ),
            candidate_records=records,
            selected_candidate_index=int(selected_index),
            failure_classification=str(selected["failure_classification"]),
            operator_review_state="Unreviewed",
            stage_outcomes=(
                {
                    "stage": "stage1_free_space",
                    "status": (
                        "Passed" if bool(selected.get("success")) else "Failed"
                    ),
                    "selected_candidate_index": int(selected_index),
                    "failure_classification": str(
                        selected["failure_classification"]
                    ),
                    "completion_fraction": float(
                        selected.get("completion_fraction", 0.0)
                    ),
                    "waypoint_count": int(selected.get("waypoint_count", 0)),
                    "reason": _bounded_text(stage1_reason),
                    "first_invalid_waypoint": (
                        invalid_stage_index
                        if failure_stage.startswith("stage1")
                        else -1
                    ),
                },
                {
                    "stage": "stage2_fixed_axis_terminal",
                    "status": str(stage2_status),
                    "completion_fraction": float(
                        selected.get("stage2_fraction", 0.0)
                    ),
                    "waypoint_count": int(
                        selected.get("stage2_waypoint_count", 0)
                    ),
                    "reason": _bounded_text(stage2_reason),
                    "first_invalid_waypoint": (
                        invalid_stage_index
                        if failure_stage.startswith("stage2")
                        else -1
                    ),
                },
                {
                    "stage": "stage3_drilling",
                    "status": str(stage3_status),
                    "completion_fraction": float(
                        selected.get("stage3_fraction", 0.0)
                    ),
                    "waypoint_count": int(
                        selected.get("stage3_waypoint_count", 0)
                    ),
                    "reason": _bounded_text(stage3_reason),
                    "first_invalid_waypoint": (
                        invalid_stage_index
                        if failure_stage.startswith("stage3")
                        else -1
                    ),
                },
            ),
            full_task_outcome={
                "status": str(full_task_status),
                "selected_candidate_index": int(selected_index),
                "spindle_planning_policy": SPINDLE_PLANNING_POLICY,
                "spindle_locked_value_rad": SPINDLE_LOCKED_VALUE_RAD,
                "drill_tool_frame_policy": DRILL_TOOL_FRAME_POLICY,
                "tool_orientation_fingerprint": str(
                    selected.get("tool_orientation_fingerprint") or ""
                ),
                "tool_axis_ras": list(selected.get("tool_axis_ras") or ()),
                "axial_frame_roll_deg": float(
                    selected.get("axial_roll_deg", GOAL1_CANONICAL_TOOL_ROLL_DEG)
                ),
                "blocked_stage": failure_stage,
                "first_invalid_composed_waypoint": invalid_composed_index,
                "first_invalid_stage_waypoint": invalid_stage_index,
                "first_invalid_cause": full_task_reason,
                "stage1_waypoint_count": int(
                    selected.get("stage1_waypoint_count", 0)
                ),
                "stage2_waypoint_count": int(
                    selected.get("stage2_waypoint_count", 0)
                ),
                "stage3_waypoint_count": int(
                    selected.get("stage3_waypoint_count", 0)
                ),
            },
        )
        parameter_node.step6MotionDiagnosticJson = canonical_json(session.to_dict())
        return session

    @staticmethod
    def _goal1_chain_diagnostic_fields(
        chain: Mapping[str, object],
        stage1_waypoint_count: int,
    ) -> dict[str, object]:
        """Return stage-local failure evidence for one full-chain candidate."""

        terminal_plan = chain.get("terminalPlan")
        drilling_plan = chain.get("drillingPlan")
        stage1_count = max(0, int(stage1_waypoint_count))
        stage2_count = len(
            terminal_plan.waypoint_joint_vectors_si
            if terminal_plan is not None
            else ()
        )
        stage3_count = len(
            drilling_plan.waypoint_joint_vectors_si
            if drilling_plan is not None
            else ()
        )
        status = str(chain.get("status") or "")
        if "Stage1" in status:
            failure_stage = "stage1_free_space"
        elif "Stage2" in status:
            failure_stage = "stage2_fixed_axis_terminal"
        elif "Stage3" in status:
            failure_stage = "stage3_drilling"
        elif status in {"BlockedPhaseGuard", "BlockedPhaseGuardSetup"}:
            failure_stage = "phase_guard_setup"
        else:
            failure_stage = ""
        invalid_composed = int(chain.get("firstInvalidIndex", -1))
        invalid_stage = -1
        if invalid_composed >= 0:
            if failure_stage == "stage1_free_space":
                invalid_stage = invalid_composed
            elif failure_stage == "stage2_fixed_axis_terminal":
                invalid_stage = invalid_composed - stage1_count
            elif failure_stage == "stage3_drilling":
                invalid_stage = invalid_composed - stage1_count - stage2_count
            invalid_stage = max(-1, invalid_stage)
        failed_plan = (
            drilling_plan
            if failure_stage == "stage3_drilling"
            else terminal_plan
            if failure_stage == "stage2_fixed_axis_terminal"
            else None
        )
        if (
            invalid_stage < 0
            and failed_plan is not None
            and int(failed_plan.first_invalid_requested_index) >= 0
        ):
            invalid_stage = int(failed_plan.first_invalid_requested_index)
            invalid_composed = (
                stage1_count
                + (stage2_count if failure_stage == "stage3_drilling" else 0)
                + invalid_stage
            )
        result = {
            "full_chain_candidate_status": status,
            "full_chain_failure_stage": failure_stage,
            "full_chain_failure_reason": _bounded_text(chain.get("reason") or ""),
            "full_chain_guard_message": _bounded_text(
                chain.get("guardMessage") or ""
            ),
            "full_chain_first_invalid_index": invalid_composed,
            "full_chain_first_invalid_stage_index": invalid_stage,
            "stage1_waypoint_count": stage1_count,
            "stage2_waypoint_count": stage2_count,
            "stage3_waypoint_count": stage3_count,
        }
        if failed_plan is not None:
            result.update(
                {
                    "failure_classification": str(
                        failed_plan.failure_classification or "unknown"
                    ),
                    "first_invalid_requested_index": int(
                        failed_plan.first_invalid_requested_index
                    ),
                    "first_invalid_ras_mm": failed_plan.first_invalid_ras_mm,
                    "first_invalid_joint_positions_si": (
                        failed_plan.first_invalid_joint_positions_si
                    ),
                    "first_invalid_collision_pairs": [
                        list(pair)
                        for pair in failed_plan.first_invalid_collision_pairs
                    ],
                    "last_valid_joint_positions_si": (
                        failed_plan.last_valid_joint_positions_si
                    ),
                    "completed_distance_mm": float(
                        failed_plan.completed_distance_mm
                    ),
                    "requested_distance_mm": float(
                        failed_plan.requested_path_length_mm
                    ),
                }
            )
        return result

    def planApproachPhase(self) -> RobotActionResult:
        """Plan strict current→pre-entry plus independently guarded contact."""

        try:
            parameter_node = self._require_context()
            self.stopPreview()
            self._diagnostic_candidate_paths = {}
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                raise ValueError("Task confirmation is missing or stale: " + ", ".join(issues))
            if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
            if not self.taskHomeRuntimeValidated(parameter_node):
                raise ValueError(
                    "Task Home is not validated in the current ROS/MoveIt session. "
                    "Return to 6.2 and apply it before planning Goal 1."
                )
            if not self.workspaceRuntimeValidated(parameter_node):
                raise ValueError(
                    "Workspace evidence is not validated in the current ROS/MoveIt "
                    "session. Return to 6.3, regenerate it, review its envelope, "
                    "and confirm the task again."
                )
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            home_record = self._logic.taskHomeRecord(parameter_node)
            home_positions = dict(
                zip(home_record.joint_names, home_record.joint_positions_si)
            )
            monitored_ok, monitored_message, monitored_positions, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    home_positions,
                    timeout_sec=1.0,
                )
            )
            if not monitored_ok:
                raise RuntimeError(
                    "Goal 1 requires MoveIt's monitored current state to equal "
                    "the immutable Task Home before planning. "
                    + monitored_message
                    + (
                        f" Maximum observed joint error: {monitored_error:.6g}."
                        if monitored_positions
                        else ""
                    )
                    + " Return to 6.2 and apply/validate Task Home."
                )
            guard_ok, guard_message = self._prepare_phase_guard(parameter_node, snapshot)
            if not guard_ok:
                raise RuntimeError(guard_message)
            # One guard session spans Goal 1 and Goal 2.  Re-planning Goal 1
            # explicitly starts a fresh sequence/corridor history; individual
            # waypoint commands must never reset that history.
            self._phase_guard_task_fingerprint = snapshot.snapshot_fingerprint
            self._phase_sequence = self._bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE
            self._completed_phase = ""
            pre_entry, entry = self._logic.step6ApproachPoints(parameter_node)
            approach_vector = tuple(
                float(entry[index] - pre_entry[index]) for index in range(3)
            )
            approach_length = sum(value * value for value in approach_vector) ** 0.5
            if approach_length <= 1e-9:
                raise RuntimeError("Goal 1 pre-entry and Entry points are coincident.")
            ik_candidates, ik_failures = self._goal1_pre_entry_ik_candidates(
                parameter_node,
                pre_entry,
                entry,
                home_positions,
            )
            if not ik_candidates:
                raise RuntimeError(
                    "Goal 1 found no collision-aware PreEntry IK endpoint for "
                    "the canonical arm orientation with the external spindle locked. "
                    + "; ".join(ik_failures)
                )
            strict_plan = None
            selected_candidate = None
            selected_axis_plan = None
            selected_chain_evaluation = None
            selected_goal1_diagnostic_index = -1
            plan_failures: list[dict[str, object]] = []
            diagnostic_records: list[dict[str, object]] = []
            planned_candidate_routes: list[dict[str, object]] = []
            for candidate_index, candidate in enumerate(
                ik_candidates[:GOAL1_MAX_PLANNED_IK_CANDIDATES]
            ):
                ok, message, _goal = self._bridge.set_moveit_tcp_goal_matrix(
                    candidate["pose"]
                )
                if not ok:
                    plan_failures.append(
                        {
                            "routeType": candidate.get("routeType", "direct"),
                            "message": "Goal display failed: " + message,
                        }
                    )
                    continue
                candidate_plan = self._bridge.plan_moveit_joint_goal(
                    start_joint_positions_si=home_positions,
                    goal_joint_positions_si=candidate["positions"],
                    refresh_planning_scene=(candidate_index == 0),
                    planning_attempts=1,
                    allowed_planning_time_sec=GOAL1_DIRECT_PLANNING_TIME_SEC,
                    planner_context=(
                        "task_home_to_preentry_"
                        + str(candidate.get("routeType") or "direct")
                    ),
                )
                segment = None
                if not candidate_plan.success:
                    diagnose_segment = getattr(
                        self._bridge,
                        "diagnose_moveit_joint_segment",
                        _default_bridge.diagnose_moveit_joint_segment,
                    )
                    segment = diagnose_segment(
                        home_positions,
                        candidate["positions"],
                    )
                diagnostic_records.append(
                    self._goal1_diagnostic_record(
                        len(diagnostic_records),
                        stage="task_home_to_preentry_direct",
                        axial_roll_deg=float(candidate["rollDeg"]),
                        result=candidate_plan,
                        route_type=str(candidate.get("routeType") or "direct"),
                        seed_sample_index=candidate.get("seedSampleIndex"),
                        segment=segment,
                    )
                )
                diagnostic_index = len(diagnostic_records) - 1
                self._diagnostic_candidate_paths[diagnostic_index] = {
                    "stage1": tuple(candidate_plan.waypoint_joint_vectors_si),
                }
                if candidate_plan.success:
                    # Stage 1 owns the complete drill-frame decision. Evaluate
                    # Stage 2 and Stage 3 with that exact frame before ranking
                    # this endpoint; a locally convenient PreEntry branch must
                    # not hide a branch with better full-chain continuity.
                    chain = self._goal1_candidate_chain_preflight(
                        parameter_node,
                        snapshot,
                        candidate,
                        candidate_plan,
                        pre_entry=pre_entry,
                        entry=entry,
                    )
                    orientation = dict(candidate["orientationCommitment"])
                    diagnostic_records[-1].update(
                        {
                            "tool_orientation_policy": DRILL_TOOL_FRAME_POLICY,
                            "tool_orientation_fingerprint": orientation["fingerprint"],
                            "tool_axis_ras": list(orientation["toolAxisRas"]),
                            "tool_rotation_ras": [
                                list(row) for row in orientation["rotationRas"]
                            ],
                            "stage2_fraction": float(chain["axisPlan"].fraction),
                            "stage3_fraction": (
                                float(chain["drillingPlan"].fraction)
                                if chain["drillingPlan"] is not None
                                else 0.0
                            ),
                            "post_preentry_arm_motion_cost": float(chain["score"][2]),
                            **self._goal1_chain_diagnostic_fields(
                                chain,
                                len(candidate_plan.waypoint_joint_vectors_si),
                            ),
                        }
                    )
                    self._diagnostic_candidate_paths[diagnostic_index].update(
                        {
                            "stage2": tuple(
                                chain["terminalPlan"].waypoint_joint_vectors_si
                            ),
                            "stage3": tuple(
                                chain["drillingPlan"].waypoint_joint_vectors_si
                                if chain["drillingPlan"] is not None
                                else ()
                            ),
                        }
                    )
                    planned_candidate_routes.append(
                        {
                            "candidate": candidate,
                            "strictPlan": candidate_plan,
                            "chain": chain,
                            "diagnosticIndex": len(diagnostic_records) - 1,
                        }
                    )
                    if chain["status"] != "Complete":
                        plan_failures.append(
                            {
                                "routeType": candidate.get("routeType", "direct"),
                                "stage": chain["status"],
                                "message": chain["reason"],
                                "fraction": float(chain["axisPlan"].fraction),
                                "orientationFingerprint": orientation["fingerprint"],
                            }
                        )
                    continue
                plan_failures.append(
                    {
                        "routeType": candidate.get("routeType", "direct"),
                        "maximumDelta": candidate_plan.maximum_start_goal_delta,
                        "maximumDeltaJoint": (
                            candidate_plan.maximum_start_goal_delta_joint
                        ),
                        "nativePlannerMessage": (
                            candidate_plan.native_planner_message
                        ),
                        "message": candidate_plan.message,
                        "firstCollisionFraction": (
                            segment.first_collision_fraction
                            if segment is not None
                            else None
                        ),
                        "firstCollisionPairs": (
                            segment.first_collision_pairs
                            if segment is not None
                            else ()
                        ),
                    }
                )
            if planned_candidate_routes:
                selected_route = min(
                    planned_candidate_routes,
                    key=lambda route: route["chain"]["score"],
                )
                strict_plan = selected_route["strictPlan"]
                selected_candidate = selected_route["candidate"]
                selected_chain_evaluation = selected_route["chain"]
                selected_axis_plan = selected_chain_evaluation["axisPlan"]
                selected_goal1_diagnostic_index = int(
                    selected_route["diagnosticIndex"]
                )
            selected_clearance = None
            if not any(
                route["chain"]["status"] == "Complete"
                for route in planned_candidate_routes
            ):
                # A valid endpoint plus a failed straight joint-space route is
                # not a proof that no route exists.  Reuse only the bounded
                # 6.3 samples already shown to be static-valid and connected
                # from Task Home, then independently replan both legs now.
                clearance_start_plans: dict[int, object] = {}
                clearance_candidate_routes: list[dict[str, object]] = []
                direct_candidate_ids = {
                    id(route["candidate"]) for route in planned_candidate_routes
                }
                for candidate in ik_candidates:
                    if id(candidate) in direct_candidate_ids:
                        # This detour changes only Stage 1 for an endpoint whose
                        # fixed-frame Stage 2/3 chain is already known.
                        continue
                    candidate_clearances = self._goal1_clearance_waypoints(
                        parameter_node,
                        home_positions,
                        candidate["positions"],
                    )
                    for clearance in candidate_clearances:
                        clearance_index = int(clearance["sampleIndex"])
                        first_leg = clearance_start_plans.get(clearance_index)
                        if first_leg is None:
                            first_leg = self._bridge.plan_moveit_joint_goal(
                                start_joint_positions_si=home_positions,
                                goal_joint_positions_si=clearance["positions"],
                                refresh_planning_scene=False,
                                planning_attempts=1,
                                allowed_planning_time_sec=(
                                    GOAL1_CLEARANCE_PLANNING_TIME_SEC
                                ),
                                planner_context=(
                                    "task_home_to_clearance_sample_"
                                    f"{clearance_index}"
                                ),
                            )
                            clearance_start_plans[clearance_index] = first_leg
                        if first_leg is None or not first_leg.success:
                            continue
                        second_leg = self._bridge.plan_moveit_joint_goal(
                            start_joint_positions_si=clearance["positions"],
                            goal_joint_positions_si=candidate["positions"],
                            refresh_planning_scene=False,
                            planning_attempts=1,
                            allowed_planning_time_sec=(
                                GOAL1_CLEARANCE_PLANNING_TIME_SEC
                            ),
                            planner_context=(
                                "clearance_sample_"
                                f"{int(clearance['sampleIndex'])}_to_preentry"
                            ),
                        )
                        segment = None
                        if not second_leg.success:
                            diagnose_segment = getattr(
                                self._bridge,
                                "diagnose_moveit_joint_segment",
                                _default_bridge.diagnose_moveit_joint_segment,
                            )
                            segment = diagnose_segment(
                                clearance["positions"],
                                candidate["positions"],
                            )
                        diagnostic_records.append(
                            self._goal1_diagnostic_record(
                                len(diagnostic_records),
                                stage="clearance_to_preentry",
                                axial_roll_deg=float(candidate["rollDeg"]),
                                result=second_leg,
                                route_type="clearance-detour",
                                clearance=clearance,
                                seed_sample_index=candidate.get("seedSampleIndex"),
                                segment=segment,
                            )
                        )
                        diagnostic_index = len(diagnostic_records) - 1
                        self._diagnostic_candidate_paths[diagnostic_index] = {
                            "stage1": (
                                tuple(first_leg.waypoint_joint_vectors_si)
                                + tuple(second_leg.waypoint_joint_vectors_si)
                            ),
                        }
                        if second_leg.success:
                            merged_plan = self._merge_goal1_joint_plans(
                                first_leg,
                                second_leg,
                                planner_context=(
                                    "task_home_via_workspace_clearance_to_preentry"
                                ),
                            )
                            chain = self._goal1_candidate_chain_preflight(
                                parameter_node,
                                snapshot,
                                candidate,
                                merged_plan,
                                pre_entry=pre_entry,
                                entry=entry,
                            )
                            orientation = dict(candidate["orientationCommitment"])
                            diagnostic_records[-1].update(
                                {
                                    "tool_orientation_policy": DRILL_TOOL_FRAME_POLICY,
                                    "tool_orientation_fingerprint": orientation[
                                        "fingerprint"
                                    ],
                                    "tool_axis_ras": list(orientation["toolAxisRas"]),
                                    "tool_rotation_ras": [
                                        list(row) for row in orientation["rotationRas"]
                                    ],
                                    "stage2_fraction": float(
                                        chain["axisPlan"].fraction
                                    ),
                                    "stage3_fraction": (
                                        float(chain["drillingPlan"].fraction)
                                        if chain["drillingPlan"] is not None
                                        else 0.0
                                    ),
                                    "post_preentry_arm_motion_cost": float(
                                        chain["score"][2]
                                    ),
                                    **self._goal1_chain_diagnostic_fields(
                                        chain,
                                        len(merged_plan.waypoint_joint_vectors_si),
                                    ),
                                }
                            )
                            self._diagnostic_candidate_paths[diagnostic_index] = {
                                "stage1": tuple(merged_plan.waypoint_joint_vectors_si),
                                "stage2": tuple(
                                    chain["terminalPlan"].waypoint_joint_vectors_si
                                ),
                                "stage3": tuple(
                                    chain["drillingPlan"].waypoint_joint_vectors_si
                                    if chain["drillingPlan"] is not None
                                    else ()
                                ),
                            }
                            clearance_candidate_routes.append(
                                {
                                    "candidate": candidate,
                                    "strictPlan": merged_plan,
                                    "chain": chain,
                                    "clearance": clearance,
                                    "diagnosticIndex": len(diagnostic_records) - 1,
                                }
                            )
                            if chain["status"] != "Complete":
                                plan_failures.append(
                                    {
                                        "routeType": "clearance-detour",
                                        "clearanceSampleIndex": clearance[
                                            "sampleIndex"
                                        ],
                                        "stage": chain["status"],
                                        "message": chain["reason"],
                                        "fraction": float(
                                            chain["axisPlan"].fraction
                                        ),
                                        "orientationFingerprint": orientation[
                                            "fingerprint"
                                        ],
                                    }
                                )
                            continue
                        plan_failures.append(
                            {
                                "routeType": "clearance-detour",
                                "clearanceSampleIndex": clearance["sampleIndex"],
                                "stage": "clearance_to_preentry",
                                "nativePlannerMessage": (
                                    second_leg.native_planner_message
                                ),
                                "message": second_leg.message,
                                "firstCollisionFraction": (
                                    segment.first_collision_fraction
                                    if segment is not None
                                    else None
                                ),
                                "firstCollisionPairs": (
                                    segment.first_collision_pairs
                                    if segment is not None
                                    else ()
                                ),
                            }
                        )
                if clearance_candidate_routes:
                    selected_route = min(
                        planned_candidate_routes + clearance_candidate_routes,
                        key=lambda route: route["chain"]["score"],
                    )
                    strict_plan = selected_route["strictPlan"]
                    selected_candidate = selected_route["candidate"]
                    selected_chain_evaluation = selected_route["chain"]
                    selected_axis_plan = selected_chain_evaluation["axisPlan"]
                    selected_clearance = selected_route["clearance"]
                    selected_goal1_diagnostic_index = int(
                        selected_route["diagnosticIndex"]
                    )
            if strict_plan is None or selected_candidate is None:
                best_candidate = ik_candidates[0]
                diagnose_segment = getattr(
                    self._bridge,
                    "diagnose_moveit_joint_segment",
                    _default_bridge.diagnose_moveit_joint_segment,
                )
                direct_segment = diagnose_segment(
                    home_positions,
                    best_candidate["positions"],
                )
                show_goal = getattr(
                    self._bridge,
                    "show_moveit_joint_goal",
                    _default_bridge.show_moveit_joint_goal,
                )
                show_goal(best_candidate["positions"])
                diagnostic = self._persist_goal1_diagnostic(
                    parameter_node,
                    snapshot,
                    diagnostic_records,
                    max(0, len(diagnostic_records) - 1),
                )
                self._clear_phase_session()
                best_joint_diagnostic = best_candidate["jointDiagnostic"]
                attempted_routes = ", ".join(
                    str(item.get("routeType") or item.get("stage") or "direct")
                    for item in plan_failures
                )
                return RobotActionResult(
                    False,
                    "approach_start_goal_plan_failed",
                    "Goal 1 found "
                    f"{len(ik_candidates)} collision-aware PreEntry IK endpoint(s), "
                    "but MoveIt could not connect Task Home to the top-ranked "
                    f"arm branch(es) via {attempted_routes or 'no submitted route'}. "
                    f"Best endpoint's largest effective joint change is "
                    f"{float(best_joint_diagnostic['maximum_delta']):.6g} on "
                    f"{best_joint_diagnostic['maximum_joint']}. "
                    + direct_segment.message
                    + " The translucent robot is an individually valid endpoint, "
                    "not proof of a collision-free connecting path. All bounded "
                    "direct arm route and retained 6.3 clearance-waypoint routes "
                    "were attempted; inspect motion diagnostic session "
                    f"{diagnostic.session_fingerprint[:12]} for the failing leg.",
                    details={
                        "collisionAwareIkCandidateCount": len(ik_candidates),
                        "ikFailures": tuple(ik_failures),
                        "planFailures": tuple(plan_failures),
                        "bestRouteType": best_candidate.get("routeType", "direct"),
                        "bestRequestedGoalJointPositionsSi": (
                            best_candidate["requestedPositions"]
                        ),
                        "bestSubmittedGoalJointPositionsSi": (
                            best_candidate["positions"]
                        ),
                        "bestPerJointStartGoalDelta": (
                            best_joint_diagnostic["effective_deltas"]
                        ),
                        "maximumStartGoalDelta": (
                            best_joint_diagnostic["maximum_delta"]
                        ),
                        "maximumStartGoalDeltaJoint": (
                            best_joint_diagnostic["maximum_joint"]
                        ),
                        "rawMaximumStartGoalDelta": (
                            best_joint_diagnostic["raw_maximum_delta"]
                        ),
                        "rawMaximumStartGoalDeltaJoint": (
                            best_joint_diagnostic["raw_maximum_joint"]
                        ),
                        "continuousJointWrapAdjustments": (
                            best_joint_diagnostic["continuous_adjustments"]
                        ),
                        "directSegmentSampleCount": direct_segment.sample_count,
                        "directSegmentFirstCollisionFraction": (
                            direct_segment.first_collision_fraction
                        ),
                        "directSegmentFirstCollisionPairs": (
                            direct_segment.first_collision_pairs
                        ),
                        "motionDiagnosticSessionFingerprint": (
                            diagnostic.session_fingerprint
                        ),
                    },
                    payload=tuple(plan_failures),
                )
            # Preserve the FK-derived orientation of the selected J6-locked
            # endpoint. Replacing this with the old canonical 0-degree roll
            # recreates an artificial Cartesian bridge at Stage 2 even though
            # the TCP position and trajectory axis are already continuous.
            selected_roll_deg = float(selected_candidate["rollDeg"])
            selected_orientation = dict(
                selected_candidate["orientationCommitment"]
            )
            if selected_goal1_diagnostic_index < 0:
                selected_goal1_diagnostic_index = len(diagnostic_records) - 1
            self._persist_goal1_diagnostic(
                parameter_node,
                snapshot,
                diagnostic_records,
                selected_goal1_diagnostic_index,
                full_task_status="PendingStage2",
            )
            show_goal = getattr(
                self._bridge,
                "show_moveit_joint_goal",
                _default_bridge.show_moveit_joint_goal,
            )
            show_goal(
                strict_plan.waypoint_joint_vectors_si[-1]
                if strict_plan.waypoint_joint_vectors_si
                else selected_candidate["positions"]
            )
            axis_plan = selected_axis_plan
            if axis_plan is None:
                fallback_terminal = self._bridge.plan_moveit_cartesian_path(
                    entry_ras_mm=pre_entry,
                    target_ras_mm=entry,
                    sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount)),
                    base_transform=parameter_node.robotBaseTransform,
                    avoid_collisions=False,
                    minimum_fraction=0.99,
                    start_joint_positions_si=(
                        strict_plan.waypoint_joint_vectors_si[-1]
                        if strict_plan.waypoint_joint_vectors_si
                        else None
                    ),
                    axial_roll_start_deg=selected_roll_deg,
                    axial_roll_end_deg=selected_roll_deg,
                )
                axis_plan = replace(
                    fallback_terminal,
                    waypoint_joint_vectors_si=(),
                    waypoint_times_sec=(),
                    requested_path_length_mm=0.0,
                    completed_distance_mm=0.0,
                    last_valid_waypoint_index=-1,
                )
            selected_chain_status = str(
                selected_chain_evaluation.get("status")
                if selected_chain_evaluation is not None
                else ""
            )
            if selected_chain_status in {
                "BlockedStage1PhaseGuard",
                "BlockedPhaseGuard",
                "BlockedPhaseGuardSetup",
            }:
                guard_failure_message = str(
                    selected_chain_evaluation.get("reason")
                    or "The authoritative phase guard could not validate Stage 1."
                )
                diagnostic = self._persist_goal1_diagnostic(
                    parameter_node,
                    snapshot,
                    diagnostic_records,
                    selected_goal1_diagnostic_index,
                    stage2_status="NotRun",
                    stage3_status="NotRun",
                    full_task_status="Blocked",
                    full_task_reason=guard_failure_message,
                )
                self._clear_phase_session()
                return RobotActionResult(
                    False,
                    "approach_phase_guard_failed",
                    guard_failure_message,
                    details={
                        "fullTaskStatus": "Blocked",
                        "blockedStage": "stage1_phase_guard",
                        "firstInvalidComposedWaypoint": int(
                            selected_chain_evaluation.get("firstInvalidIndex", -1)
                        ),
                        "motionDiagnosticSessionFingerprint": (
                            diagnostic.session_fingerprint
                        ),
                    },
                )
            stage2_guard_blocked = selected_chain_status in {
                "BlockedStage2PhaseGuard",
            }
            stage2_chain_blocked = stage2_guard_blocked or (
                selected_chain_status == "BlockedStage2Cartesian"
            )
            stage2_failure_message = (
                str(selected_chain_evaluation.get("reason") or "")
                if stage2_chain_blocked
                else str(axis_plan.message)
            )
            selected_invalid_index = (
                int(selected_chain_evaluation.get("firstInvalidIndex", -1))
                if selected_chain_evaluation is not None
                else -1
            )
            selected_stage1_count = len(strict_plan.waypoint_joint_vectors_si)
            selected_stage2_count = len(
                selected_chain_evaluation["terminalPlan"].waypoint_joint_vectors_si
                if selected_chain_evaluation is not None
                and selected_chain_evaluation.get("terminalPlan") is not None
                else ()
            )
            if (
                stage2_guard_blocked
                and selected_stage2_count > 0
                and selected_invalid_index >= selected_stage1_count
            ):
                stage2_failure_fraction = min(
                    1.0,
                    max(
                        0.0,
                        (
                            selected_invalid_index
                            - selected_stage1_count
                            + 1
                        )
                        / selected_stage2_count,
                    ),
                )
            elif stage2_chain_blocked and selected_chain_evaluation.get(
                "terminalPlan"
            ) is not None:
                stage2_failure_fraction = float(
                    selected_chain_evaluation["terminalPlan"].fraction
                )
            else:
                stage2_failure_fraction = float(axis_plan.fraction)
            if not axis_plan.success or stage2_chain_blocked:
                # A valid Home→PreEntry joint-space plan is still a complete
                # Goal-1 milestone for placement review. Keep that evidence
                # when the fixed-axis Stage-2 path is kinematically incomplete
                # or its independent guard rejects a later waypoint. Do not
                # manufacture Entry or weaken the reported collision policy.
                strict_source = tuple(strict_plan.waypoint_joint_vectors_si)
                strict_waypoints, strict_times = self._guarded_preview_checkpoints(
                    strict_source,
                    strict_plan.waypoint_times_sec,
                )
                self._preflight_drilling_plan = None
                self._preflight_task_fingerprint = ""
                self._preflight_orientation_commitment = {}
                deferred_diagnostic = self._persist_goal1_diagnostic(
                    parameter_node,
                    snapshot,
                    diagnostic_records,
                    selected_goal1_diagnostic_index,
                    stage2_status="DeferredAtPreEntry",
                    stage3_status="NotRun",
                    full_task_status="Blocked",
                    full_task_reason=stage2_failure_message,
                )
                preentry_plan = PhasePlan(
                    success=True,
                    message=(
                        f"Goal 1 PreEntry ready: {len(strict_waypoints)} "
                        "collision-free Task-Home waypoints are available for "
                        "guarded preview. The terminal axis segment toward Entry "
                        f"was rejected at {stage2_failure_fraction * 100.0:.1f}% "
                        f"({stage2_failure_message}); Entry and Goal 2 remain deferred."
                    ),
                    task_fingerprint=snapshot.snapshot_fingerprint,
                    requested_phase="approach",
                    waypoint_joint_vectors_si=strict_waypoints,
                    waypoint_phases=("approach",) * len(strict_waypoints),
                    waypoint_times_sec=strict_times,
                    cartesian_fraction=1.0,
                    coordinate_frame=self._bridge.ROS2_FIXED_FRAME,
                    strict_waypoint_count=len(strict_waypoints),
                    axis_waypoint_count=0,
                    contact_waypoint_count=0,
                    source_waypoint_count=len(strict_source),
                    axial_roll_deg=selected_roll_deg,
                    tool_axis_ras=tuple(selected_orientation["toolAxisRas"]),
                    tool_orientation_fingerprint=str(
                        selected_orientation["fingerprint"]
                    ),
                )
                self._motion_plan = preentry_plan
                path_view = getattr(
                    self._bridge,
                    "show_phase_plan_tcp_path",
                    None,
                )
                path_view_ok = False
                path_view_message = ""
                if callable(path_view):
                    path_view_ok, path_view_message = path_view(
                        strict_waypoints,
                        parameter_node.robotBaseTransform,
                        phase="approach",
                    )
                return RobotActionResult(
                    True,
                    "approach_provisional_plan_ready",
                    preentry_plan.message,
                    details={
                        "waypointCount": len(strict_waypoints),
                        "strictWaypointCount": len(strict_waypoints),
                        "axisWaypointCount": 0,
                        "terminalWaypointCount": 0,
                        "terminalPlanningDeferred": True,
                        "terminalPlanningError": stage2_failure_message,
                        "terminalPlanningFraction": stage2_failure_fraction,
                        "firstInvalidComposedWaypoint": selected_invalid_index,
                        "trajectoryPathDisplayed": bool(path_view_ok),
                        "trajectoryPathDisplayMessage": path_view_message,
                        "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
                        "collisionAwareIkCandidateCount": len(ik_candidates),
                        "plannedIkCandidateCount": min(
                            len(ik_candidates), GOAL1_MAX_PLANNED_IK_CANDIDATES
                        ),
                        "motionDiagnosticSessionFingerprint": (
                            deferred_diagnostic.session_fingerprint
                        ),
                        "fullTaskStatus": "Blocked",
                        "blockedStage": "stage2_phase_guard",
                        "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                        "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                        "toolAxisRas": tuple(selected_orientation["toolAxisRas"]),
                        "toolOrientationFingerprint": selected_orientation[
                            "fingerprint"
                        ],
                    },
                    payload=preentry_plan,
                )
            terminal = (
                selected_chain_evaluation["terminalPlan"]
                if selected_chain_evaluation is not None
                and selected_chain_evaluation.get("terminalPlan") is not None
                else self._bridge.plan_moveit_cartesian_path(
                    entry_ras_mm=pre_entry,
                    target_ras_mm=entry,
                    sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount)),
                    base_transform=parameter_node.robotBaseTransform,
                    avoid_collisions=False,
                    minimum_fraction=0.99,
                    start_joint_positions_si=(
                            strict_plan.waypoint_joint_vectors_si[-1]
                            if strict_plan.waypoint_joint_vectors_si
                            else selected_candidate["positions"]
                    ),
                    axial_roll_start_deg=selected_roll_deg,
                    axial_roll_end_deg=selected_roll_deg,
                )
            )
            if not terminal.success:
                diagnostic = self._persist_goal1_diagnostic(
                    parameter_node,
                    snapshot,
                    diagnostic_records,
                    selected_goal1_diagnostic_index,
                    stage2_status="FailedTerminalContact",
                    stage3_status="NotRun",
                    full_task_status="Blocked",
                    full_task_reason=terminal.message,
                )
                strict_waypoints, strict_times = self._guarded_preview_checkpoints(
                    tuple(strict_plan.waypoint_joint_vectors_si),
                    strict_plan.waypoint_times_sec,
                )
                axis_waypoints = tuple(axis_plan.waypoint_joint_vectors_si)
                provisional = PhasePlan(
                    success=True,
                    message=(
                        "Full task Blocked in Stage 2 terminal contact: "
                        + terminal.message
                        + " The collision-free Home→PreEntry evidence remains previewable."
                    ),
                    task_fingerprint=snapshot.snapshot_fingerprint,
                    requested_phase="approach",
                    waypoint_joint_vectors_si=strict_waypoints + axis_waypoints,
                    waypoint_phases=("approach",) * (
                        len(strict_waypoints) + len(axis_waypoints)
                    ),
                    waypoint_times_sec=_concatenate_waypoint_times(
                        strict_times, axis_plan.waypoint_times_sec
                    ),
                    cartesian_fraction=float(terminal.fraction),
                    strict_waypoint_count=len(strict_waypoints),
                    axis_waypoint_count=len(axis_waypoints),
                    source_waypoint_count=(
                        len(strict_plan.waypoint_joint_vectors_si)
                        + len(axis_plan.waypoint_joint_vectors_si)
                    ),
                    axial_roll_deg=selected_roll_deg,
                    tool_axis_ras=tuple(selected_orientation["toolAxisRas"]),
                    tool_orientation_fingerprint=str(
                        selected_orientation["fingerprint"]
                    ),
                )
                self._motion_plan = provisional
                self._preflight_drilling_plan = None
                self._preflight_task_fingerprint = ""
                self._preflight_orientation_commitment = {}
                return RobotActionResult(
                    True,
                    "approach_provisional_plan_ready",
                    provisional.message,
                    details={
                        "fullTaskStatus": "Blocked",
                        "blockedStage": "stage2_cartesian",
                        "firstInvalidCause": terminal.message,
                        "motionDiagnosticSessionFingerprint": diagnostic.session_fingerprint,
                        "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                        "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                        "toolAxisRas": tuple(selected_orientation["toolAxisRas"]),
                        "toolOrientationFingerprint": selected_orientation[
                            "fingerprint"
                        ],
                    },
                    payload=provisional,
                )
            if not terminal.waypoint_joint_vectors_si:
                raise RuntimeError(
                    "Goal 1 terminal plan did not provide an Entry joint state."
                )
            self._persist_goal1_diagnostic(
                parameter_node,
                snapshot,
                diagnostic_records,
                selected_goal1_diagnostic_index,
                stage2_status="Passed",
                full_task_status="PendingStage3Preflight",
            )
            # Goal 1 is an independently useful approach preview.  Do not let
            # the optional Entry→Target reachability preflight veto a valid
            # Home→PreEntry→Entry plan: Goal 2 has its own guarded planner
            # and may legitimately remain blocked while the operator studies
            # the approach.  Preserve the failure text in the diagnostic and
            # expose it in the result instead of silently treating it as a
            # successful drilling plan.
            drilling_preflight = (
                selected_chain_evaluation.get("drillingPlan")
                if selected_chain_evaluation is not None
                else None
            )
            drilling_preflight_error = (
                str(selected_chain_evaluation.get("reason") or "")
                if selected_chain_evaluation is not None
                and selected_chain_evaluation.get("status") != "Complete"
                else ""
            )
            try:
                if drilling_preflight is not None and not drilling_preflight.success:
                    raise RuntimeError(drilling_preflight_error or drilling_preflight.message)
                if drilling_preflight is None:
                    drilling_preflight = self._plan_full_drilling_line(
                        parameter_node,
                        snapshot,
                        terminal.waypoint_joint_vectors_si[-1],
                        start_axial_roll_deg=selected_roll_deg,
                    )
                preflight_waypoints = (
                    tuple(strict_plan.waypoint_joint_vectors_si)
                    + tuple(axis_plan.waypoint_joint_vectors_si)
                    + tuple(terminal.waypoint_joint_vectors_si)
                    + tuple(drilling_preflight.waypoint_joint_vectors_si)
                )
                preflight_phases = (
                    ("approach",) * len(strict_plan.waypoint_joint_vectors_si)
                    + ("approach",) * len(axis_plan.waypoint_joint_vectors_si)
                    + ("terminal_contact",) * len(terminal.waypoint_joint_vectors_si)
                    + ("drilling",) * len(drilling_preflight.waypoint_joint_vectors_si)
                )
                validate_chain = getattr(
                    self._bridge,
                    "validate_task_phase_waypoints",
                    _default_bridge.validate_task_phase_waypoints,
                )
                guard_ready, guard_ready_message = self._configure_phase_guard(
                    parameter_node, snapshot
                )
                if not guard_ready:
                    raise RuntimeError(guard_ready_message)
                guard_valid, guard_message, invalid_index = validate_chain(
                    preflight_waypoints,
                    preflight_phases,
                    task_fingerprint=snapshot.snapshot_fingerprint,
                )
                if not guard_valid:
                    raise RuntimeError(
                        guard_message
                        + f" First invalid composed waypoint: {invalid_index}."
                    )
            except (RuntimeError, ValueError, OSError) as exc:
                drilling_preflight_error = str(exc)
                drilling_preflight = None
                self._preflight_drilling_plan = None
                self._preflight_task_fingerprint = ""
                self._preflight_orientation_commitment = {}
            if drilling_preflight is not None:
                self._preflight_drilling_plan = drilling_preflight
                self._preflight_task_fingerprint = snapshot.snapshot_fingerprint
                self._preflight_orientation_commitment = selected_orientation
            # The successful Goal 1 route is the operator's current diagnostic
            # evidence.  A failed drilling preflight remains an explicit
            # deferred stage-3 outcome and never authorizes Goal 2.
            goal1_diagnostic = self._persist_goal1_diagnostic(
                parameter_node,
                snapshot,
                diagnostic_records,
                selected_goal1_diagnostic_index,
                stage2_status="Passed",
                stage3_status=(
                    "Passed"
                    if drilling_preflight is not None
                    else "Failed"
                ),
                full_task_status=(
                    "Complete" if drilling_preflight is not None else "Blocked"
                ),
                full_task_reason=drilling_preflight_error,
            )
            strict_source = tuple(strict_plan.waypoint_joint_vectors_si)
            axis_source = tuple(axis_plan.waypoint_joint_vectors_si)
            terminal_source = tuple(terminal.waypoint_joint_vectors_si)
            strict_waypoints, strict_times = self._guarded_preview_checkpoints(
                strict_source,
                strict_plan.waypoint_times_sec,
            )
            # Keep the fine Cartesian contact samples. Compaction replaces a
            # curved TCP segment with a longer joint-space chord; near the
            # anatomy that chord can regress or leave the approved corridor
            # even when every MoveIt Cartesian sample is ordered correctly.
            terminal_waypoints = terminal_source
            terminal_times = tuple(terminal.waypoint_times_sec)
            axis_waypoints = axis_source
            axis_times = tuple(axis_plan.waypoint_times_sec)
            source_count = (
                len(strict_source) + len(axis_source) + len(terminal_source)
            )
            plan = PhasePlan(
                success=True,
                message=(
                    f"Goal 1 ready: {len(strict_waypoints)} free-space, "
                    f"{len(terminal_waypoints)} fixed-axis Stage-2 checkpoint(s) "
                    f"from {source_count} MoveIt samples. "
                    "The independent phase guard keeps all non-tool collision "
                    "rules strict while suppressing only configured burr-to-task "
                    "contact; every suppression will be reported. "
                    "The pneumatic spindle remained locked at 0 rad; route "
                    "selection used only controllable arm joints"
                    + (
                        " through previously validated workspace clearance "
                        f"sample {int(selected_clearance['sampleIndex'])}. "
                        if selected_clearance is not None
                        else ". "
                    )
                    + (
                        "The complete Entry-to-Target drilling line passed the "
                        "spindle-locked reachability preflight."
                        if drilling_preflight is not None
                        else (
                            "Full-task status is Blocked at Stage 3; the provisional "
                            "Goal 1 approach preview remains available as historical "
                            "evidence and is not a drilling authorization."
                        )
                    )
                ),
                task_fingerprint=snapshot.snapshot_fingerprint,
                requested_phase="approach",
                waypoint_joint_vectors_si=(
                    strict_waypoints + axis_waypoints + terminal_waypoints
                ),
                waypoint_phases=("approach",) * len(strict_waypoints)
                + ("approach",) * len(axis_waypoints)
                + ("terminal_contact",) * len(terminal_waypoints),
                waypoint_times_sec=_concatenate_waypoint_times(
                    _concatenate_waypoint_times(strict_times, axis_times),
                    terminal_times,
                ),
                cartesian_fraction=float(terminal.fraction),
                coordinate_frame=str(terminal.coordinate_frame),
                start_position_error_mm=terminal.start_position_error_mm,
                start_orientation_error_deg=terminal.start_orientation_error_deg,
                strict_waypoint_count=len(strict_waypoints),
                axis_waypoint_count=len(axis_waypoints),
                contact_waypoint_count=len(terminal_waypoints),
                source_waypoint_count=source_count,
                axial_roll_deg=selected_roll_deg,
                tool_axis_ras=tuple(selected_orientation["toolAxisRas"]),
                tool_orientation_fingerprint=str(
                    selected_orientation["fingerprint"]
                ),
            )
            self._motion_plan = plan
            path_view = getattr(
                self._bridge,
                "show_phase_plan_tcp_path",
                None,
            )
            path_view_ok = False
            path_view_message = ""
            if callable(path_view):
                path_results = []
                path_results.append(path_view(
                    strict_waypoints,
                    parameter_node.robotBaseTransform,
                    phase="stage1",
                    clear_existing=True,
                ))
                path_results.append(path_view(
                    axis_waypoints + terminal_waypoints,
                    parameter_node.robotBaseTransform,
                    phase="stage2",
                    clear_existing=False,
                ))
                if drilling_preflight is not None:
                    path_results.append(path_view(
                        drilling_preflight.waypoint_joint_vectors_si,
                        parameter_node.robotBaseTransform,
                        phase="stage3",
                        clear_existing=False,
                    ))
                path_view_ok = all(result[0] for result in path_results)
                path_view_message = " ".join(result[1] for result in path_results)
            return RobotActionResult(
                True,
                (
                    "approach_full_chain_plan_ready"
                    if drilling_preflight is not None
                    else "approach_provisional_plan_ready"
                ),
                plan.message,
                details={
                    "waypointCount": len(plan.waypoint_joint_vectors_si),
                    "strictWaypointCount": len(strict_waypoints),
                    "axisWaypointCount": len(axis_waypoints),
                    "terminalWaypointCount": len(terminal_waypoints),
                    "terminalContactPolicy": "phase_guard_evidence_based",
                    "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
                    "selectedClearanceSampleIndex": (
                        int(selected_clearance["sampleIndex"])
                        if selected_clearance is not None
                        else None
                    ),
                    "collisionAwareIkCandidateCount": len(ik_candidates),
                    "plannedIkCandidateCount": min(
                        len(ik_candidates),
                        GOAL1_MAX_PLANNED_IK_CANDIDATES,
                    ),
                    "failedPlannedCandidates": tuple(plan_failures),
                    "sourceWaypointCount": source_count,
                    "cartesianFraction": float(terminal.fraction),
                    "coordinateFrame": str(terminal.coordinate_frame),
                    "startPositionErrorMm": terminal.start_position_error_mm,
                    "startOrientationErrorDeg": terminal.start_orientation_error_deg,
                    "drillingPreflightFraction": (
                        drilling_preflight.fraction
                        if drilling_preflight is not None
                        else None
                    ),
                    "drillingPreflightSpindleLocked": (
                        drilling_preflight is not None
                    ),
                    "drillingPreflightError": drilling_preflight_error,
                    "fullTaskStatus": (
                        "Complete" if drilling_preflight is not None else "Blocked"
                    ),
                    "spindlePlanningPolicy": SPINDLE_PLANNING_POLICY,
                    "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                    "toolAxisRas": tuple(selected_orientation["toolAxisRas"]),
                    "toolOrientationFingerprint": selected_orientation[
                        "fingerprint"
                    ],
                    "trajectoryPathDisplayed": bool(path_view_ok),
                    "trajectoryPathDisplayMessage": path_view_message,
                    "plannerStartSource": strict_plan.planner_start_source,
                    "submittedStartJointPositionsSi": (
                        strict_plan.submitted_start_joint_positions_si
                    ),
                    "submittedGoalJointPositionsSi": (
                        strict_plan.submitted_goal_joint_positions_si
                    ),
                    "monitoredStartJointPositionsSi": (
                        strict_plan.monitored_start_joint_positions_si
                    ),
                    "maximumStartGoalDelta": (
                        strict_plan.maximum_start_goal_delta
                    ),
                    "maximumStartGoalDeltaJoint": (
                        strict_plan.maximum_start_goal_delta_joint
                    ),
                    "rawMaximumStartGoalDelta": (
                        strict_plan.raw_maximum_start_goal_delta
                    ),
                    "rawMaximumStartGoalDeltaJoint": (
                        strict_plan.raw_maximum_start_goal_delta_joint
                    ),
                    "perJointStartGoalDelta": (
                        strict_plan.per_joint_start_goal_delta
                    ),
                    "continuousJointWrapAdjustments": (
                        strict_plan.continuous_joint_wrap_adjustments
                    ),
                    "maximumMonitoredStartError": (
                        strict_plan.maximum_monitored_start_error
                    ),
                    "nativePlannerMessage": strict_plan.native_planner_message,
                    "motionDiagnosticSessionFingerprint": (
                        goal1_diagnostic.session_fingerprint
                    ),
                },
                payload=plan,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._clear_phase_session()
            return RobotActionResult(False, "approach_plan_failed", str(exc))

    def planDrillingPhase(self) -> RobotActionResult:
        """Plan Entry→Target with solver collision-off but guard enforcement on."""

        try:
            parameter_node = self._require_context()
            self.stopPreview()
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                raise ValueError("Task confirmation is missing or stale: " + ", ".join(issues))
            if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
            if self._completed_phase != "approach":
                raise ValueError(
                    "Complete the guarded Goal 1 approach preview before planning Goal 2."
                )
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            if self._phase_guard_task_fingerprint != snapshot.snapshot_fingerprint:
                raise ValueError(
                    "The Goal 1 guard session is missing or belongs to another task. "
                    "Re-plan and preview Goal 1 before Goal 2."
                )
            start_positions = self._bridge.last_accepted_joint_positions_si()
            if not start_positions or any(
                name not in start_positions for name in JOINT_NAMES
            ):
                raise RuntimeError(
                    "The accepted Goal 1 endpoint is unavailable. Re-preview Goal 1."
                )
            if (
                self._preflight_drilling_plan is not None
                and self._preflight_task_fingerprint
                == snapshot.snapshot_fingerprint
            ):
                result = self._preflight_drilling_plan
            else:
                raise RuntimeError(
                    "The complete Home-to-PreEntry-to-Entry-to-Target preflight "
                    "is not current. Re-plan Goal 1; Goal 2 cannot independently "
                    "replan or promote a partial drilling path."
                )
            source_waypoints = tuple(result.waypoint_joint_vectors_si)
            orientation = dict(self._preflight_orientation_commitment)
            if (
                orientation.get("policy") != DRILL_TOOL_FRAME_POLICY
                or not orientation.get("fingerprint")
            ):
                raise RuntimeError(
                    "The Stage-1 drilling-frame commitment is unavailable. "
                    "Re-plan Goal 1 before Goal 2."
                )
            # Entry-to-Target is short and accuracy-dominant. Preserve every
            # fine MoveIt Cartesian sample so the guard never substitutes a
            # sparse joint-space chord for the requested TCP line.
            waypoints = source_waypoints
            waypoint_times = tuple(result.waypoint_times_sec)
            plan = PhasePlan(
                success=True,
                message=(
                    f"Goal 2 preview ready: {len(waypoints)} guarded Entry-to-Target "
                    f"checkpoint(s) from {len(source_waypoints)} MoveIt samples. "
                    "Spindle locked at 0 rad (external pressure/RPM; not planned). "
                    "Solver collision avoidance is disabled for this exploratory "
                    "Cartesian check. The independent guard may suppress only "
                    "configured burr-to-task-object contacts; non-tool collisions, "
                    "bounds, and corridor violations remain rejected."
                ),
                task_fingerprint=snapshot.snapshot_fingerprint,
                requested_phase="drilling",
                waypoint_joint_vectors_si=waypoints,
                waypoint_phases=("drilling",) * len(waypoints),
                waypoint_times_sec=waypoint_times,
                cartesian_fraction=float(result.fraction),
                coordinate_frame=str(result.coordinate_frame),
                start_position_error_mm=result.start_position_error_mm,
                start_orientation_error_deg=result.start_orientation_error_deg,
                contact_waypoint_count=len(waypoints),
                source_waypoint_count=len(source_waypoints),
                axial_roll_deg=float(result.axial_roll_deg),
                tool_axis_ras=tuple(orientation["toolAxisRas"]),
                tool_orientation_fingerprint=str(orientation["fingerprint"]),
            )
            self._motion_plan = plan
            return RobotActionResult(
                True,
                "drilling_plan_ready",
                plan.message,
                details={
                    "waypointCount": len(waypoints),
                    "sourceWaypointCount": len(source_waypoints),
                    "cartesianFraction": float(result.fraction),
                    "coordinateFrame": str(result.coordinate_frame),
                    "startPositionErrorMm": result.start_position_error_mm,
                    "startOrientationErrorDeg": result.start_orientation_error_deg,
                    "spindleLockedValueRad": SPINDLE_LOCKED_VALUE_RAD,
                    "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                    "toolAxisRas": tuple(orientation["toolAxisRas"]),
                    "toolOrientationFingerprint": orientation["fingerprint"],
                },
                payload=plan,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._motion_plan = None
            return RobotActionResult(False, "drilling_plan_failed", str(exc))

    def previewPhase(
        self,
        requested_phase: str,
        *,
        interval_ms: int = 250,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[RobotActionResult], None]] = None,
    ) -> RobotActionResult:
        plan = self._motion_plan
        if (
            not isinstance(plan, PhasePlan)
            or not plan.success
            or plan.requested_phase != str(requested_phase)
        ):
            return RobotActionResult(False, "phase_plan_required", "Create the matching guarded phase plan first.")
        if str(requested_phase) == "drilling" and self._completed_phase != "approach":
            if self._completed_phase == "drilling":
                return RobotActionResult(
                    False,
                    "phase_session_consumed",
                    "Goal 2 has already completed in this guard session. Re-plan Goal 1 to replay the task.",
                )
            return RobotActionResult(
                False,
                "approach_required",
                "Complete the guarded Goal 1 approach preview before Goal 2.",
            )
        try:
            parameter_node = self._require_context()
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                self._clear_phase_session()
                return RobotActionResult(False, "task_stale", "Task confirmation is stale: " + ", ".join(issues))
            if self._phase_guard_task_fingerprint != plan.task_fingerprint:
                return RobotActionResult(
                    False,
                    "phase_session_required",
                    "The matching task-guard session is unavailable. Re-plan Goal 1.",
                )
            if str(requested_phase) == "approach" and (
                self._phase_sequence
                != self._bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE
                or self._completed_phase
            ):
                return RobotActionResult(
                    False,
                    "phase_session_consumed",
                    "This Goal 1 guard session has already started. Re-plan Goal 1 before replaying it.",
                )
            import qt
        except (RuntimeError, ValueError, ImportError) as exc:
            return RobotActionResult(False, "phase_preview_failed", str(exc))
        self.stopPreview()
        self._preview_index = 0
        self._preview_exploratory_tool_contact = False
        self._preview_suppressed_tool_contact_samples = 0
        timer = qt.QTimer()
        timer.setInterval(max(20, int(interval_ms)))

        def advance() -> None:
            if self._preview_waypoint_in_flight:
                return
            if self._preview_index >= len(plan.waypoint_joint_vectors_si):
                completed_phase = plan.requested_phase
                self.stopPreview()
                self._completed_phase = completed_phase
                if on_finished:
                    if self._preview_exploratory_tool_contact:
                        on_finished(
                            RobotActionResult(
                                True,
                                "phase_preview_complete_exploratory_contact",
                                "Exploratory simulation preview complete. "
                                f"Configured burr contact was suppressed at "
                                f"{self._preview_suppressed_tool_contact_samples} "
                                "interpolated guard sample(s); this is not a "
                                "collision-safe or executable result.",
                                details={
                                    "exploratoryToolContactSuppressed": True,
                                    "suppressedToolContactSampleCount": (
                                        self._preview_suppressed_tool_contact_samples
                                    ),
                                },
                            )
                        )
                    else:
                        on_finished(
                            RobotActionResult(
                                True,
                                "phase_preview_complete",
                                "Guarded simulation phase preview complete; no "
                                "configured burr contact required suppression.",
                                details={
                                    "exploratoryToolContactSuppressed": False,
                                    "suppressedToolContactSampleCount": 0,
                                },
                            )
                        )
                return
            current_issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if current_issues:
                self.stopPreview()
                self._clear_phase_session()
                if on_finished:
                    on_finished(
                        RobotActionResult(
                            False,
                            "task_stale",
                            "Task changed during preview: "
                            + ", ".join(current_issues)
                            + " Re-plan Goal 1 to start a new guarded session.",
                        )
                    )
                return
            positions = plan.waypoint_joint_vectors_si[self._preview_index]
            phase = plan.waypoint_phases[self._preview_index]
            self._preview_waypoint_in_flight = True
            try:
                ok, message = self._bridge.apply_task_phase_joint_positions(
                    positions,
                    task_fingerprint=plan.task_fingerprint,
                    phase=phase,
                    sequence=self._phase_sequence,
                )
                if not ok:
                    self.stopPreview()
                    self._clear_phase_session()
                    if on_finished:
                        on_finished(
                            RobotActionResult(
                                False,
                                "phase_waypoint_rejected",
                                message
                                + " Re-plan Goal 1 to start a new guarded session.",
                            )
                        )
                    return
                status_getter = getattr(
                    self._bridge, "last_task_joint_status", None
                )
                status = status_getter() if callable(status_getter) else None
                if (
                    status is not None
                    and getattr(status, "task_fingerprint", "")
                    == plan.task_fingerprint
                    and getattr(status, "phase", "") == phase
                    and getattr(status, "sequence", -1) == self._phase_sequence
                    and bool(getattr(status, "accepted", False))
                    and bool(
                        getattr(
                            status,
                            "exploratory_tool_contact_suppressed",
                            False,
                        )
                    )
                ):
                    self._preview_exploratory_tool_contact = True
                    self._preview_suppressed_tool_contact_samples += int(
                        getattr(status, "suppressed_tool_contact_sample_count", 0)
                    )
                # Keep the re-entrancy latch held until the accepted sequence and
                # MRML display state have both advanced.  EndModify can process
                # widget refresh callbacks, which in turn may spin Qt and fire
                # this timer recursively.  Releasing the latch earlier allowed
                # the same guarded sequence to be published twice.
                self._preview_index += 1
                self._phase_sequence += 1
                self._write_display_values(
                    parameter_node,
                    self._display_values_from_si(positions),
                )
                if on_progress:
                    on_progress(
                        self._preview_index,
                        len(plan.waypoint_joint_vectors_si),
                    )
            finally:
                self._preview_waypoint_in_flight = False

        timer.timeout.connect(advance)
        timer.start()
        self._preview_timer = timer
        return RobotActionResult(
            True,
            "phase_preview_started",
            f"Guarded simulation preview started for {len(plan.waypoint_joint_vectors_si)} waypoint(s).",
        )

    def _apply_positions_si(self, positions_si: Mapping[str, float]) -> RobotActionResult:
        parameter_node = self._require_context()
        display_values = self._display_values_from_si(positions_si)
        prior_values = self._display_values(parameter_node)
        self._write_display_values(parameter_node, display_values)
        if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
            ok, message = self._bridge.apply_joint_positions_si_to_motion_control(
                positions_si
            )
            if not ok:
                accepted = self._bridge.last_accepted_joint_positions_si()
                restored = (
                    self._display_values_from_si(accepted)
                    if accepted and all(name in accepted for name in JOINT_NAMES)
                    else prior_values
                )
                self._write_display_values(parameter_node, restored)
                return RobotActionResult(False, "preview_rejected", message)
        elif self._logic.robotLinkTransformNodes():
            self._logic.updateRobotJointPoses(dict(positions_si))
        return RobotActionResult(True, "preview_waypoint", "Applied simulated preview waypoint.")

    def previewPlan(
        self,
        *,
        interval_ms: int = 250,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[RobotActionResult], None]] = None,
    ) -> RobotActionResult:
        plan = self._motion_plan
        waypoints = tuple(getattr(plan, "waypoint_joint_vectors_si", ()) or ())
        if not plan or not getattr(plan, "success", False) or not waypoints:
            return RobotActionResult(False, "plan_required", "Create a successful simulation plan before previewing it.")
        try:
            import qt
        except ImportError:
            return RobotActionResult(False, "qt_unavailable", "Qt is unavailable for simulated preview timing.")
        self.stopPreview()
        self._preview_index = 0
        timer = qt.QTimer()
        timer.setInterval(max(20, int(interval_ms)))

        def advance() -> None:
            if self._preview_waypoint_in_flight:
                return
            if self._preview_index >= len(waypoints):
                self.stopPreview()
                if on_finished:
                    on_finished(RobotActionResult(True, "preview_complete", "Simulated motion preview complete."))
                return
            self._preview_waypoint_in_flight = True
            try:
                result = self._apply_positions_si(waypoints[self._preview_index])
                if not result.success:
                    self.stopPreview()
                    if on_finished:
                        on_finished(result)
                    return
                self._preview_index += 1
                if on_progress:
                    on_progress(self._preview_index, len(waypoints))
            finally:
                self._preview_waypoint_in_flight = False

        timer.timeout.connect(advance)
        timer.start()
        self._preview_timer = timer
        return RobotActionResult(True, "preview_started", f"Previewing {len(waypoints)} simulated waypoint(s).")

    def stopPreview(self) -> RobotActionResult:
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer = None
        self._preview_index = 0
        self._preview_waypoint_in_flight = False
        return RobotActionResult(True, "preview_stopped", "Simulated preview stopped.")

    def generateWorkspaceCloud(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            self._runtime_validated_workspace_key = ""
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                return RobotActionResult(
                    False,
                    "runtime_required",
                    "Connect ROS/MoveIt in 6.1 before generating the workspace.",
                )
            if not self.taskHomeRuntimeValidated(parameter_node):
                return RobotActionResult(
                    False,
                    "task_home_runtime_validation_required",
                    "Save or apply a live-validated Task Home in 6.2 before generating the workspace.",
                )
            home = self._logic.taskHomeRecord(parameter_node)
            home_positions = dict(zip(home.joint_names, home.joint_positions_si))
            monitored_ok, monitored_message, monitored, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    home_positions,
                    timeout_sec=1.0,
                )
            )
            if not monitored_ok:
                return RobotActionResult(
                    False,
                    "workspace_start_state_mismatch",
                    "Workspace exploration must start from Task Home. "
                    + monitored_message,
                    details={
                        "expectedJointPositionsSi": home_positions,
                        "monitoredJointPositionsSi": monitored,
                        "maximumJointError": monitored_error,
                    },
                )
            model, report = self._logic.createOrUpdateRobotWorkspace(parameter_node)
            local_requested_count = report.requested_count
            locally_accepted_count = report.accepted_count
            local_self_rejections = report.self_collision_rejections
            local_environment_rejections = report.environment_rejections
            all_candidate_samples = tuple(report.accepted_samples)
            selected_indices = _bounded_even_indices(
                len(all_candidate_samples),
                WORKSPACE_RUNTIME_VALIDATION_MAX_SAMPLES,
            )
            candidate_samples = tuple(
                (source_index, all_candidate_samples[source_index])
                for source_index in selected_indices
            )
            runtime_accepted = []
            accepted_sample_evidence: list[dict[str, Any]] = []
            runtime_rejections: list[str] = []
            maximum_local_moveit_fk_difference_mm = 0.0
            for sample_index, (source_index, sample) in enumerate(candidate_samples):
                sample_positions = canonicalize_planning_joint_positions(
                    sample.joint_positions_si_dict()
                )
                valid, validity_message, authoritative = (
                    self._bridge.check_moveit_static_joint_state(
                        sample_positions
                    )
                )
                if not authoritative:
                    return RobotActionResult(
                        False,
                        "workspace_runtime_validation_unavailable",
                        "Workspace generation stopped because MoveIt did not "
                        "return authoritative static-state validity. "
                        + validity_message,
                        details={
                            "candidateIndex": sample_index,
                            "locallyAcceptedCandidateCount": locally_accepted_count,
                            "runtimeEvaluatedCandidateCount": len(candidate_samples),
                        },
                    )
                if valid:
                    fk_ok, fk_message, tcp_base_mm = (
                        self._bridge.compute_moveit_static_tcp_pose_base_mm(
                            sample_positions
                        )
                    )
                    if not fk_ok or tcp_base_mm is None:
                        return RobotActionResult(
                            False,
                            "workspace_moveit_fk_unavailable",
                            "Workspace generation stopped because MoveIt did not "
                            "return authoritative explicit-state TCP FK. "
                            + fk_message,
                            details={"candidateIndex": sample_index},
                        )
                    fk_difference_mm = sum(
                        (
                            float(tcp_base_mm[index])
                            - float(sample.tcp_base_mm[index])
                        )
                        ** 2
                        for index in range(3)
                    ) ** 0.5
                    maximum_local_moveit_fk_difference_mm = max(
                        maximum_local_moveit_fk_difference_mm,
                        fk_difference_mm,
                    )
                    runtime_accepted.append(
                        sample.__class__(
                            tcp_base_mm=tuple(tcp_base_mm),
                            joint_display=tuple(sample.joint_display[:-1]) + (0.0,),
                            joint_positions_si=tuple(
                                (name, float(sample_positions[name]))
                                for name in JOINT_NAMES
                            ),
                        )
                    )
                    accepted_sample_evidence.append(
                        {
                            "sample_index": len(runtime_accepted) - 1,
                            "source_candidate_index": source_index,
                            "tcp_base_mm": [float(value) for value in tcp_base_mm],
                            "joint_names": list(JOINT_NAMES),
                            "joint_positions_si": [
                                float(sample_positions[name])
                                for name in JOINT_NAMES
                            ],
                            "joint_display": [
                                float(value) for value in sample.joint_display
                            ],
                            "static_state_validity": {
                                "status": "Valid",
                                "authoritative": True,
                                "message": _bounded_text(validity_message),
                            },
                            "tcp_fk": {
                                "source": "MoveItRobotState",
                                "message": _bounded_text(fk_message),
                                "local_difference_mm": fk_difference_mm,
                            },
                            "home_connectivity": {
                                "status": "NotEvaluated"
                            },
                        }
                    )
                elif len(runtime_rejections) < 8:
                    runtime_rejections.append(
                        f"sample {source_index}: {validity_message}"
                    )
                if sample_index % 10 == 0:
                    try:
                        import slicer

                        slicer.app.processEvents()
                    except Exception:
                        pass
            if not runtime_accepted:
                return RobotActionResult(
                    False,
                    "workspace_no_moveit_valid_samples",
                    "MoveIt rejected every locally generated workspace candidate "
                    "against the synchronized PlanningScene.",
                    details={"sampleFailures": tuple(runtime_rejections)},
                )
            connectivity_indices = self._home_connectivity_sample_indices(
                runtime_accepted,
                home_positions,
            )
            home_connected_sample_count = 0
            home_connectivity_rejected_sample_count = 0
            connectivity_scene_refreshed = False
            for connectivity_order, accepted_index in enumerate(
                connectivity_indices
            ):
                sample = runtime_accepted[accepted_index]
                sample_positions = sample.joint_positions_si_dict()
                matches_home, maximum_delta, mismatched = (
                    self._joint_positions_match(home_positions, sample_positions)
                )
                connectivity = accepted_sample_evidence[accepted_index][
                    "home_connectivity"
                ]
                if matches_home:
                    connectivity.update(
                        {
                            "status": "HomeConnected",
                            "method": "IdentityAtTaskHome",
                            "maximum_start_goal_delta": maximum_delta,
                            "waypoint_count": 1,
                            "message": "Sample matches Task Home within monitored-state tolerances.",
                        }
                    )
                    home_connected_sample_count += 1
                else:
                    path = self._bridge.plan_moveit_joint_goal(
                        start_joint_positions_si=home_positions,
                        goal_joint_positions_si=sample_positions,
                        refresh_planning_scene=(
                            not connectivity_scene_refreshed
                        ),
                        planning_attempts=1,
                        allowed_planning_time_sec=2.0,
                        planner_context="task_home_to_workspace_sample",
                    )
                    connectivity_scene_refreshed = True
                    connectivity.update(
                        {
                            "status": (
                                "HomeConnected" if path.success else "PlanRejected"
                            ),
                            "method": "MoveItExplicitTaskHomeStart",
                            "maximum_start_goal_delta": maximum_delta,
                            "mismatched_joints": list(mismatched),
                            "waypoint_count": len(
                                path.waypoint_joint_vectors_si
                            ),
                            "planner_start_source": path.planner_start_source,
                            "message": _bounded_text(path.message),
                            "native_planner_message": _bounded_text(
                                path.native_planner_message
                            ),
                        }
                    )
                    if path.success:
                        home_connected_sample_count += 1
                    else:
                        home_connectivity_rejected_sample_count += 1
                if connectivity_order % 3 == 0:
                    try:
                        import slicer

                        slicer.app.processEvents()
                    except Exception:
                        pass
            if not connectivity_indices or home_connected_sample_count == 0:
                model.SetAttribute("DENTOBOT.WorkspaceRuntimeValidated", "false")
                return RobotActionResult(
                    False,
                    "workspace_no_home_connected_samples",
                    "MoveIt found static-valid workspace states, but none of the "
                    "bounded connectivity samples could be planned from Task Home. "
                    "Adjust Task Home, base placement, or task limits before review.",
                    details={
                        "staticValidSampleCount": len(runtime_accepted),
                        "homeConnectivityEvaluatedSampleCount": len(
                            connectivity_indices
                        ),
                        "homeConnectivityRejectedSampleCount": (
                            home_connectivity_rejected_sample_count
                        ),
                        "acceptedSampleEvidence": tuple(
                            accepted_sample_evidence[index]
                            for index in connectivity_indices
                        ),
                    },
                )
            report = report.__class__(
                requested_count=len(candidate_samples),
                accepted_samples=tuple(runtime_accepted),
                self_collision_rejections=0,
                environment_rejections=(
                    len(candidate_samples) - len(runtime_accepted)
                ),
                task_limits=report.task_limits,
                excluded_aabb_pairs=report.excluded_aabb_pairs,
            )
            import vtk

            points = vtk.vtkPoints()
            vertices = vtk.vtkCellArray()
            for sample in runtime_accepted:
                point_id = points.InsertNextPoint(*sample.tcp_base_mm)
                vertices.InsertNextCell(1)
                vertices.InsertCellPoint(point_id)
            polydata = vtk.vtkPolyData()
            polydata.SetPoints(points)
            polydata.SetVerts(vertices)
            model.SetAndObservePolyData(polydata)
            model.SetAttribute(
                "DENTOBOT.WorkspaceAlgorithm",
                "Halton6D+URDFFK+AABB+MoveItStaticStateValidity+BoundedHomeConnectivity",
            )
            model.SetAttribute("DENTOBOT.WorkspaceRuntimeValidated", "true")
            model.SetAttribute(
                "DENTOBOT.WorkspaceRuntimeEvaluated", str(report.requested_count)
            )
            model.SetAttribute(
                "DENTOBOT.WorkspaceAccepted", str(report.accepted_count)
            )
            model.SetAttribute(
                "DENTOBOT.WorkspaceHomeConnectivityEvaluated",
                str(len(connectivity_indices)),
            )
            model.SetAttribute(
                "DENTOBOT.WorkspaceHomeConnected",
                str(home_connected_sample_count),
            )
            proposal = self._logic.proposeAssistedTaskLimits(parameter_node, report)
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            proposal_payload = proposal.to_dict()
            proposal_payload.update(
                {
                    "runtime_validation_status": (
                        WORKSPACE_RUNTIME_VALIDATION_STATUS
                    ),
                    "runtime_evidence_schema_version": (
                        WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION
                    ),
                    "tcp_fk_source": "MoveItRobotState",
                    "task_home_fingerprint": fingerprint(home.to_dict()),
                    "collision_audit_fingerprint": (
                        str(collision_audit.audit_fingerprint)
                        if collision_audit is not None
                        else ""
                    ),
                    "workspace_validation_policy_fingerprint": (
                        self._workspace_validation_policy_fingerprint()
                    ),
                    "runtime_valid_sample_count": report.accepted_count,
                    "runtime_evaluated_sample_count": len(candidate_samples),
                    "locally_accepted_candidate_count": locally_accepted_count,
                    "local_requested_candidate_count": local_requested_count,
                    "runtime_rejected_sample_count": (
                        len(candidate_samples) - report.accepted_count
                    ),
                    "runtime_unevaluated_local_candidate_count": (
                        locally_accepted_count - len(candidate_samples)
                    ),
                    "home_connectivity_status": "BoundedSubsetEvaluated",
                    "home_connectivity_policy": (
                        "Nearest+JointExtrema+EvenCoverage"
                    ),
                    "home_connectivity_evaluated_sample_count": len(
                        connectivity_indices
                    ),
                    "home_connected_sample_count": home_connected_sample_count,
                    "home_connectivity_rejected_sample_count": (
                        home_connectivity_rejected_sample_count
                    ),
                    "home_connectivity_unevaluated_sample_count": (
                        report.accepted_count - len(connectivity_indices)
                    ),
                    "accepted_sample_evidence": accepted_sample_evidence,
                    "maximum_local_moveit_fk_difference_mm": (
                        maximum_local_moveit_fk_difference_mm
                    ),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
            parameter_node.step6AssistedLimitProposalJson = canonical_json(
                proposal_payload
            )
            self._runtime_validated_workspace_key = fingerprint(proposal_payload)
            return RobotActionResult(
                True,
                "workspace_ready",
                f"Generated {report.accepted_count}/{report.requested_count} "
                "sampled collision-valid configurations using deterministic FK "
                "candidates and MoveIt's synchronized static state-validity service; "
                f"{home_connected_sample_count}/{len(connectivity_indices)} bounded "
                "samples also planned successfully from Task Home. "
                "Review the sampled envelope before task confirmation; it does "
                "not imply every point inside the min/max box is valid or connected to Home.",
                details={
                    "requestedCount": report.requested_count,
                    "acceptedCount": report.accepted_count,
                    "moveItStaticValidityRejections": (
                        report.environment_rejections
                    ),
                    "localRequestedCandidates": local_requested_count,
                    "localSelfCollisionRejections": local_self_rejections,
                    "localEnvironmentRejections": local_environment_rejections,
                    "excludedAabbPairs": report.excluded_aabb_pairs,
                    "proposalReviewed": proposal.reviewed,
                    "runtimeValidationStatus": (
                        WORKSPACE_RUNTIME_VALIDATION_STATUS
                    ),
                    "runtimeEvaluatedSamples": len(candidate_samples),
                    "locallyAcceptedCandidates": locally_accepted_count,
                    "tcpFkSource": "MoveItRobotState",
                    "maximumLocalMoveItFkDifferenceMm": (
                        maximum_local_moveit_fk_difference_mm
                    ),
                    "runtimeRejectedSamples": (
                        len(candidate_samples) - report.accepted_count
                    ),
                    "runtimeUnevaluatedLocalCandidates": (
                        locally_accepted_count - len(candidate_samples)
                    ),
                    "homeConnectivityEvaluatedSamples": len(
                        connectivity_indices
                    ),
                    "homeConnectedSamples": home_connected_sample_count,
                    "homeConnectivityRejectedSamples": (
                        home_connectivity_rejected_sample_count
                    ),
                    "sampleFailures": tuple(runtime_rejections),
                },
                payload=(model, report, proposal),
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "workspace_failed", str(exc))
