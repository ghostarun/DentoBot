"""UI-independent orchestration boundary for DENTOBOT Step 6 simulation.

The legacy workflow panel and the application shell both call this façade.
Robot geometry, ROS 2, MoveIt, collision, and planning remain implemented by
the existing logic and bridge modules; this class only coordinates them and
returns structured presentation results.  It intentionally exposes no
hardware execution path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import degrees, isfinite
from typing import Any, Callable, Mapping, Optional, Sequence

import DENTOROS2Bridge as _default_bridge
from DENTORobotPlacement import joint_positions_si_from_display
from DENTOStep6State import (
    build_motion_diagnostic_session,
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
        self._runtime_validated_task_home_key = ""
        self._runtime_task_home_evidence: dict[str, Any] = {}
        self._runtime_validated_workspace_key = ""

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

        self._motion_plan = None
        self._phase_sequence = 0
        self._completed_phase = ""
        self._phase_guard_task_fingerprint = ""
        self._preflight_drilling_plan = None
        self._preflight_task_fingerprint = ""

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
        return joint_positions_si_from_display(*display_values)

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
            # Step 6.1 owns runtime creation. Seed it from the visible local
            # candidate only; Task Home and assisted limits are downstream live
            # evidence and therefore must not be prerequisites for Connect.
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
            return RobotActionResult(
                True,
                "connected",
                "Connected natively inside DENTOWorkflow, aligned the live robot "
                "to the locked base, and synchronized the simulation planning "
                "scene. Continue to 6.2 to choose and validate Task Home against "
                "this live runtime.",
                details={
                    "obstacleCount": obstacle_count,
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
                    "The saved workspace is not validated in this ROS/MoveIt session. Regenerate it in 6.3 before review.",
                )
            proposal = self._logic.reviewAndApplyAssistedTaskLimits(parameter_node)
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
                    "Regenerate and review the workspace in the current ROS/MoveIt session before task confirmation.",
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

    def _prepare_phase_guard(self, parameter_node, snapshot) -> tuple[bool, str]:
        count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
        self._planning_scene_object_count = count
        self._planning_scene_synchronized = True
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
            "axial_roll_deg": float(result.axial_roll_deg),
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
                "axialRollCandidatesDeg": tuple(
                    float(result.axial_roll_deg) for result in candidate_results
                ),
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
        )
        parameter_node.step6MotionDiagnosticJson = canonical_json(session.to_dict())
        return session

    def _plan_full_drilling_line(
        self,
        parameter_node,
        snapshot,
        start_positions: Mapping[str, float],
    ):
        """Find a full line while varying only cylindrical-burr axial roll."""

        result = None
        best_result = None
        best_index = -1
        candidate_results = []
        axial_roll_candidates_deg = (
            0.0,
            45.0,
            -45.0,
            90.0,
            -90.0,
            135.0,
            -135.0,
            180.0,
        )
        for axial_roll_deg in axial_roll_candidates_deg:
            candidate = self._bridge.plan_moveit_cartesian_path(
                entry_ras_mm=snapshot.entry_ras_mm,
                target_ras_mm=snapshot.target_ras_mm,
                sample_count=int(parameter_node.robotMotionPlanSampleCount),
                base_transform=parameter_node.robotBaseTransform,
                avoid_collisions=False,
                minimum_fraction=0.99,
                start_joint_positions_si=start_positions,
                # The cylindrical burr axis and TCP centreline stay fixed;
                # only otherwise-irrelevant axial roll is varied to avoid a
                # false full-orientation IK dead end.
                axial_roll_start_deg=0.0,
                axial_roll_end_deg=axial_roll_deg,
            )
            candidate_results.append(candidate)
            if best_result is None or candidate.fraction > best_result.fraction:
                best_result = candidate
                best_index = len(candidate_results) - 1
            if candidate.success:
                result = candidate
                best_index = len(candidate_results) - 1
                break
        if result is None:
            result = best_result
        if result is None:
            raise RuntimeError("MoveIt returned no drilling-path result.")
        diagnostic = self._persist_motion_diagnostic(
            parameter_node,
            snapshot,
            candidate_results,
            best_index,
        )
        if not result.success:
            raise RuntimeError(
                "Full Entry-to-Target reachability failed for every bounded "
                "cylindrical-burr axial-roll candidate. Best result: "
                + result.message
                + " The partial joint path and its last-valid/first-invalid "
                f"boundary were retained in diagnostic session "
                f"{diagnostic.session_fingerprint[:12]}; this result does not "
                "yet prove collision, base placement, or workspace failure and "
                "cannot be previewed."
            )
        return result

    def planApproachPhase(self) -> RobotActionResult:
        """Plan strict current→pre-entry plus independently guarded contact."""

        try:
            parameter_node = self._require_context()
            self.stopPreview()
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
            pose = self._bridge.tool_pose_matrices_world_mm(pre_entry, entry, 2)[0]
            ok, message, _goal = self._bridge.set_moveit_tcp_goal_matrix(pose)
            if not ok:
                raise RuntimeError("Goal 1 pre-entry goal setup failed: " + message)
            ok, message, pre_entry_positions = self._bridge.solve_moveit_tcp_goal(
                seed_joint_positions_si=home_positions
            )
            if not ok:
                raise RuntimeError("Goal 1 pre-entry IK failed: " + message)
            strict_plan = self._bridge.plan_moveit_joint_goal(
                start_joint_positions_si=home_positions,
                goal_joint_positions_si=pre_entry_positions,
                planner_context="task_home_to_preentry",
            )
            if not strict_plan.success:
                self._clear_phase_session()
                return RobotActionResult(
                    False,
                    "approach_start_goal_plan_failed",
                    "Goal 1 strict Task-Home-to-PreEntry planning failed: "
                    + strict_plan.message,
                    details={
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
                        "maximumMonitoredStartError": (
                            strict_plan.maximum_monitored_start_error
                        ),
                        "nativePlannerMessage": (
                            strict_plan.native_planner_message
                        ),
                    },
                    payload=strict_plan,
                )
            approach_vector = tuple(
                float(entry[index] - pre_entry[index]) for index in range(3)
            )
            approach_length = sum(value * value for value in approach_vector) ** 0.5
            if approach_length <= 1e-9:
                raise RuntimeError("Goal 1 pre-entry and Entry points are coincident.")
            terminal_tolerance = min(
                max(0.05, float(parameter_node.step6TerminalContactToleranceMm)),
                approach_length,
            )
            contact_start = tuple(
                float(entry[index])
                - approach_vector[index] / approach_length * terminal_tolerance
                for index in range(3)
            )
            axis_plan = self._bridge.plan_moveit_cartesian_path(
                entry_ras_mm=pre_entry,
                target_ras_mm=contact_start,
                sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount)),
                base_transform=parameter_node.robotBaseTransform,
                avoid_collisions=True,
                minimum_fraction=0.99,
                start_joint_positions_si=(
                    strict_plan.waypoint_joint_vectors_si[-1]
                    if strict_plan.waypoint_joint_vectors_si
                    else None
                ),
            )
            if not axis_plan.success:
                raise RuntimeError(
                    "Goal 1 strict axis approach stopped before the terminal "
                    f"{terminal_tolerance:.2f} mm contact tolerance: "
                    + axis_plan.message
                )
            terminal = self._bridge.plan_moveit_cartesian_path(
                entry_ras_mm=contact_start,
                target_ras_mm=entry,
                sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount) // 2),
                base_transform=parameter_node.robotBaseTransform,
                avoid_collisions=False,
                minimum_fraction=0.99,
                start_joint_positions_si=(
                    axis_plan.waypoint_joint_vectors_si[-1]
                    if axis_plan.waypoint_joint_vectors_si
                    else None
                ),
            )
            if not terminal.success:
                raise RuntimeError(
                    "Goal 1 terminal pre-entry-to-Entry planning failed: "
                    + terminal.message
                )
            if not terminal.waypoint_joint_vectors_si:
                raise RuntimeError(
                    "Goal 1 terminal plan did not provide an Entry joint state."
                )
            drilling_preflight = self._plan_full_drilling_line(
                parameter_node,
                snapshot,
                terminal.waypoint_joint_vectors_si[-1],
            )
            self._preflight_drilling_plan = drilling_preflight
            self._preflight_task_fingerprint = snapshot.snapshot_fingerprint
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
                    f"{len(axis_waypoints)} strict axis, and "
                    f"{len(terminal_waypoints)} terminal-contact checkpoint(s) "
                    f"from {source_count} MoveIt samples. "
                    f"Only the final {terminal_tolerance:.2f} mm terminal preview "
                    "may suppress configured burr-to-task-object contact, and "
                    "every suppression will be reported. "
                    f"The complete drilling line passed reachability preflight at "
                    f"{drilling_preflight.axial_roll_deg:.1f}° axial roll."
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
            )
            self._motion_plan = plan
            return RobotActionResult(
                True,
                "approach_plan_ready",
                plan.message,
                details={
                    "waypointCount": len(plan.waypoint_joint_vectors_si),
                    "strictWaypointCount": len(strict_waypoints),
                    "axisWaypointCount": len(axis_waypoints),
                    "terminalWaypointCount": len(terminal_waypoints),
                    "terminalContactToleranceMm": terminal_tolerance,
                    "sourceWaypointCount": source_count,
                    "cartesianFraction": float(terminal.fraction),
                    "coordinateFrame": str(terminal.coordinate_frame),
                    "startPositionErrorMm": terminal.start_position_error_mm,
                    "startOrientationErrorDeg": terminal.start_orientation_error_deg,
                    "drillingPreflightFraction": drilling_preflight.fraction,
                    "drillingPreflightAxialRollDeg": (
                        drilling_preflight.axial_roll_deg
                    ),
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
                    "maximumMonitoredStartError": (
                        strict_plan.maximum_monitored_start_error
                    ),
                    "nativePlannerMessage": strict_plan.native_planner_message,
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
                result = self._plan_full_drilling_line(
                    parameter_node,
                    snapshot,
                    start_positions,
                )
            source_waypoints = tuple(result.waypoint_joint_vectors_si)
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
                    f"Selected cylindrical-burr axial roll: "
                    f"{result.axial_roll_deg:.1f}°. "
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
                    "axialRollDeg": float(result.axial_roll_deg),
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
                valid, validity_message, authoritative = (
                    self._bridge.check_moveit_static_joint_state(
                        sample.joint_positions_si_dict()
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
                            sample.joint_positions_si_dict()
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
                            joint_display=sample.joint_display,
                            joint_positions_si=sample.joint_positions_si,
                        )
                    )
                    accepted_sample_evidence.append(
                        {
                            "sample_index": len(runtime_accepted) - 1,
                            "source_candidate_index": source_index,
                            "tcp_base_mm": [float(value) for value in tcp_base_mm],
                            "joint_names": list(JOINT_NAMES),
                            "joint_positions_si": [
                                float(sample.joint_positions_si_dict()[name])
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
