"""UI-independent orchestration boundary for DENTOBOT Step 6 simulation.

The legacy workflow panel and the application shell both call this façade.
Robot geometry, ROS 2, MoveIt, collision, and planning remain implemented by
the existing logic and bridge modules; this class only coordinates them and
returns structured presentation results.  It intentionally exposes no
hardware execution path.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from math import acos, atan2, ceil, cos, degrees, isfinite, pi, sin, sqrt
from numbers import Real
from time import monotonic, monotonic_ns, sleep
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import uuid4

import DENTOROS2Bridge as _default_bridge
from DENTORobotPlacement import joint_positions_si_from_display
from DENTOStep6Planning import (
    TaskSpaceRoi,
    WorkspaceAcceptedSample,
    WorkspaceSampleResult,
    default_task_joint_limits_from_urdf,
    default_task_space_roi_from_incisors,
    deterministic_task_space_tcp_candidates,
    joint_limit_margin_evidence,
)
from DENTOStep6State import (
    DRILL_TOOL_FRAME_POLICY,
    build_manual_simulation_record,
    SIMULATION_TARGET_DEPTH_POLICY,
    build_motion_diagnostic_session,
    canonicalize_planning_joint_positions,
    canonical_json,
    fingerprint,
    motion_diagnostic_plan_selection,
    parse_motion_diagnostic_session,
    PLANNER_COMPARISON_IDS,
    planner_comparison_scene_fingerprint,
    task_snapshot_invalidation_reasons,
    update_motion_diagnostic_plan_selection,
)


JOINT_DISPLAY_FIELDS = (
    "robotJoint1Deg",
    "robotJoint2Mm",
    "robotJoint3Deg",
    "robotJoint4Mm",
    "robotJoint5Deg",
)
JOINT_LIMIT_FIELDS = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
)
JOINT_DISPLAY_UNITS = ("deg", "mm", "deg", "mm", "deg")
JOINT_NAMES = tuple(_default_bridge.ROS2_JOINT_SI_ORDER)
MANUAL_JOINT_POLICY_ID = _default_bridge.ROS2_MANUAL_JOINT_POLICY_ID
WORKSPACE_RUNTIME_VALIDATION_MAX_SAMPLES = 400
WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES = 13
WORKSPACE_RUNTIME_VALIDATION_STATUS = (
    "MoveItStaticStateValidity+BoundedHomeConnectivity"
)
WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION = "2.0"
HISTORICAL_TEMPLATE_OVERRIDE_ENV = "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE"
MANUAL_BASE_REVIEW_MATRIX_TOLERANCE = 1.0e-6
# Compatibility-only display value for diagnostics that predate the
# authoritative-FK frame policy. Goal 1 never constrains planning to this roll.
LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG = 0.0
# 6.3 evaluates at most thirteen Home-connected representatives. Use every
# one as an IK seed, plus Task Home, so Stage 1 can discover distinct
# five-joint branches before committing the immutable drilling frame.
GOAL1_MAX_IK_SEEDS = WORKSPACE_HOME_CONNECTIVITY_MAX_SAMPLES + 1
GOAL1_MAX_PLANNED_IK_CANDIDATES = GOAL1_MAX_IK_SEEDS
GOAL1_MAX_CLEARANCE_WAYPOINTS = 3
STEP6_APPROACH_CORRIDOR_MM = 12.0  # operator 2026-10-02: axis-aligned final approach
# Shortest collision-free axial corridor kept before falling back to the direct plan
# (operator 2026-10-04: adjust corridor distance to what is clear).
STEP6_APPROACH_CORRIDOR_MIN_MM = 1.0
GOAL1_DIRECT_PLANNING_TIME_SEC = 10.0  # operator 2026-10-02: robustness for marginal P1
GOAL1_CLEARANCE_PLANNING_TIME_SEC = 4.0
STEP6_JOINT_PLANNER_ID = "RRTConnectkConfigDefault"
# Sanity bound (2x MoveIt's default 1e-4 joint-goal tolerance) for snapping a
# planned Home-draft end onto the exact draft; the strict guard still validates it.
HOME_DRAFT_SNAP_TOLERANCE_SI = 2.0e-4
STEP6_JOINT_PLANNER_ALGORITHM = "geometric::RRTConnect"
STEP6_JOINT_PLANNER_ALGORITHMS = {
    STEP6_JOINT_PLANNER_ID: STEP6_JOINT_PLANNER_ALGORITHM,
    "RRTkConfigDefault": "geometric::RRT",
    "RRTstarkConfigDefault": "geometric::RRTstar",
}
STEP6_JOINT_PLANNING_ATTEMPTS = 5  # operator 2026-10-02: sampling planner retries
# Independent sequential re-plans of the Home -> PreEntry free-space leg when the
# sampling planner returns no trajectory (S6-LIVE-01 2026-10-05: one call misses an
# existing route ~1 in 30; MoveIt's parallel attempts share one time budget).
# Every returned plan is still guarded and validated; no rule is relaxed.
STEP6_JOINT_PLAN_RETRIES = 8
# Bounded wait for MoveGroup to apply a scene re-sync before the scene gate re-compares.
STEP6_SCENE_RESYNC_WAIT_SEC = 5.0
STEP6_SCENE_REPAIR_ROUNDS = 3
STEP6_APPROXIMATE_IK_ENABLED = False
STEP6_CARTESIAN_PLANNING_ENABLED = True
# The operator-selected simulation burr mesh is approximately 1 mm across. This is a physical
# fit check only; exploratory guard policy may still suppress burr-to-guide
# contact so simulation can inspect the arm path independently.
PROVISIONAL_BURR_DIAMETER_MM = 1.0
# CAD/URDF audit: the nearest upstream spindle-housing mesh lies 7.0 mm behind
# the canonical burr-tip TCP along its drilling axis. The guide/shell allowance
# is an operator-specified provisional envelope; it is not a shell measurement.
PROVISIONAL_EFFECTIVE_TOOL_PROTRUSION_MM = 7.0
PROVISIONAL_AXIAL_CLEARANCE_MM = 0.1
PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM = 0.5
PROVISIONAL_MAXIMUM_COMBINED_INSERTION_MM = 6.5
PROVISIONAL_REMAINING_VISIBLE_PROTRUSION_MM = 0.5


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
    return_home_required: bool = False


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
    )
    spans = (
        float(maximum_revolute_span_rad),
        float(maximum_prismatic_span_m),
        float(maximum_revolute_span_rad),
        float(maximum_prismatic_span_m),
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
        a = tuple(
            vectors[start][joint] / deviations[joint]
            for joint in range(len(JOINT_NAMES))
        )
        b = tuple(
            vectors[end][joint] / deviations[joint]
            for joint in range(len(JOINT_NAMES))
        )
        direction = tuple(
            b[joint] - a[joint] for joint in range(len(JOINT_NAMES))
        )
        length_squared = sum(value * value for value in direction)
        for index in range(start + 1, end):
            point = tuple(
                vectors[index][joint] / deviations[joint]
                for joint in range(len(JOINT_NAMES))
            )
            if length_squared <= 1e-18:
                projection = a
            else:
                fraction = sum(
                    (point[joint] - a[joint]) * direction[joint]
                    for joint in range(len(JOINT_NAMES))
                ) / length_squared
                fraction = min(1.0, max(0.0, fraction))
                projection = tuple(
                    a[joint] + fraction * direction[joint]
                    for joint in range(len(JOINT_NAMES))
                )
            if sum(
                (point[joint] - projection[joint]) ** 2
                for joint in range(len(JOINT_NAMES))
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


def _dev_fast_mode_stamp(evaluation) -> str:
    """Stamp for the development-only first-complete route mode (operator 2026-10-03)."""
    if not evaluation or evaluation.get("mode") != "dev_first_complete":
        return ""
    return (
        "DEVELOPMENT FAST MODE: "
        f"{int(evaluation.get('notEvaluated', 0))} of {int(evaluation.get('total', 0))} "
        "candidates not evaluated; not for acceptance or case comparison. "
    )


def _drilling_truncation_warning(truncation) -> str:
    """Operator 2026-10-02 (S6-TRUNCATION-WARNING): truncated drilling is a warning."""
    pair = truncation.get("blocking_pair") or ()
    pair_text = f" ({pair[0]} ↔ {pair[1]})" if len(pair) >= 2 else ""
    return (
        "WARNING: drilling shortened by a spindle-housing collision"
        f"{pair_text}: {float(truncation['completed_depth_mm']):.2f} of "
        f"{float(truncation['requested_depth_mm']):.2f} mm planned. The remaining "
        f"{float(truncation['remaining_depth_mm']):.2f} mm (orange-red in the 3D view) "
        "was not completed because of collision/invalid states."
        + (
            f" Why: {truncation['feedback']['why']} To drill further: "
            + " / ".join(truncation["feedback"]["what_to_change"])
            if isinstance(truncation.get("feedback"), dict) else ""
        )
    )


def _truncation_feedback(truncation) -> Optional[dict]:
    """Advisory why/what-to-change text; never allowed to break planning."""
    try:
        from dentobot_workflow.base_diagnosis import truncation_feedback

        return truncation_feedback(truncation, effective_protrusion_mm=PROVISIONAL_EFFECTIVE_TOOL_PROTRUSION_MM)
    except Exception:  # noqa: BLE001 - feedback is display-only
        return None


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
        # Operator 2026-10-03: development-only fast route mode. Default off;
        # every result made with it is stamped and never used for acceptance.
        self._dev_first_complete_route = (
            os.environ.get("DENTOBOT_STEP6_DEV_FIRST_COMPLETE_ROUTE", "") == "1"
        )
        self._candidate_evaluation: dict[str, object] = {}
        self._preview_timer = None
        self._diagnostic_preview_timer = None
        self._preview_index = 0
        self._preview_waypoint_in_flight = False
        self._guarded_preview_active = False
        self._guarded_preview_phase = ""
        self._guarded_preview_task_fingerprint = ""
        self._guarded_preview_request: Optional[dict[str, object]] = None
        self._incomplete_preview_evidence: Optional[dict[str, object]] = None
        self._preview_last_display_monotonic = 0.0
        self._robot_away_from_home = False
        self._display_sync_depth = 0
        self._planning_scene_object_count = 0
        self._planning_scene_synchronized = False
        self._template_collision_exclusion_active = False
        self._template_collision_excluded_object_ids: tuple[str, ...] = ()
        self._phase_sequence = 0
        self._completed_phase = ""
        self._phase_guard_task_fingerprint = ""
        self._phase_guard_session_id = ""
        self._phase_stream_paused = False
        self._preview_exploratory_tool_contact = False
        self._preview_suppressed_tool_contact_samples = 0
        self._preview_guide_clearance_warnings: list[dict[str, object]] = []
        self._preflight_drilling_plan = None
        self._drilling_truncation = None
        self._preflight_task_fingerprint = ""
        self._preflight_orientation_commitment: dict[str, object] = {}
        self._preflight_complete_approach_evidence: Optional[dict[str, object]] = None
        self._runtime_validated_task_home_key = ""
        self._runtime_task_home_evidence: dict[str, Any] = {}
        self._runtime_validated_workspace_key = ""
        self._diagnostic_candidate_paths: dict[int, dict[str, tuple]] = {}
        self._diagnostic_plan_selection_override: Optional[dict[str, object]] = None
        self._step6_preentry_candidate_cache: Optional[dict[str, object]] = None
        self._step6_stage_diagnostic_chain: dict[str, object] = {}
        self._accepted_motion_history: list[dict[str, object]] = []
        self._motion_history_task_fingerprint = ""
        self._manual_jog_in_progress = False
        self._manual_jog_reconciliation_required = False
        self._manual_jog_uncertainty: Optional[dict[str, object]] = None
        self._manual_jog_session_id = uuid4().hex
        self._manual_base_review: Optional[dict[str, object]] = None
        self._manual_base_review_failure: Optional[dict[str, object]] = None
        self._manual_base_acceptance_uncertain = ""
        self._manual_base_acceptance_in_progress = False
        self._manual_task_home_review: Optional[dict[str, object]] = None
        self._manual_task_home_review_failure: Optional[dict[str, object]] = None
        self._manual_task_home_review_status = "review"
        self._manual_task_home_acceptance_uncertain = ""
        self._manual_task_home_acceptance_in_progress = False
        self._manual_task_home_reconciliation_in_progress = False
        self._manual_simulation_identity: Optional[dict[str, str]] = None
        self._manual_simulation_events: list[dict[str, object]] = []
        # ponytail: snapshots live for this façade session; cap/archive only if long sessions show memory growth.
        self._manual_simulation_completed_records: list[dict[str, object]] = []
        self._joint_planner_id = STEP6_JOINT_PLANNER_ID
        self._effective_joint_planner_id = ""
        self._joint_planning_attempts = STEP6_JOINT_PLANNING_ATTEMPTS
        self._approach_corridor_margin_samples = 0
        self._joint_planning_time_sec = GOAL1_DIRECT_PLANNING_TIME_SEC

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
    def incompletePreviewEvidence(self):
        """Review evidence retained after an interrupted guarded phase."""

        return deepcopy(self._incomplete_preview_evidence)

    @property
    def returnHomeRequired(self) -> bool:
        """Whether the robot has accepted motion away from Task Home."""

        return bool(self._robot_away_from_home)

    @property
    def previewIndex(self) -> int:
        return int(self._preview_index)

    @property
    def currentPreviewPhase(self) -> str:
        plan = self._motion_plan
        if isinstance(plan, PhasePlan) and plan.waypoint_phases:
            index = min(max(0, self._preview_index), len(plan.waypoint_phases) - 1)
            return str(plan.waypoint_phases[index])
        return ""

    @property
    def drillingPreflightReady(self) -> bool:
        evidence = self._preflight_complete_approach_evidence
        approach_plan = evidence.get("plan") if isinstance(evidence, Mapping) else None
        orientation = self._preflight_orientation_commitment
        if not (
            self._preflight_drilling_plan is not None
            and evidence is not None
            and bool(getattr(self._preflight_drilling_plan, "success", False))
            and bool(
                getattr(self._preflight_drilling_plan, "waypoint_joint_vectors_si", ())
            )
            and isinstance(approach_plan, PhasePlan)
            and approach_plan.success
            and approach_plan.requested_phase == "approach"
            and evidence.get("taskFingerprint")
            == self._preflight_task_fingerprint
            and self._phase_guard_task_fingerprint
            == self._preflight_task_fingerprint
            and bool(evidence.get("guardSessionId"))
            and evidence.get("guardSessionId") == self._phase_guard_session_id
            and isinstance(orientation, Mapping)
            and orientation.get("policy") == DRILL_TOOL_FRAME_POLICY
            and orientation.get("fingerprint")
            == approach_plan.tool_orientation_fingerprint
        ):
            return False
        try:
            parameter_node = self._require_context()
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            identity_reader = getattr(
                self._bridge,
                "current_task_guard_identity",
                _default_bridge.current_task_guard_identity,
            )
            identity = identity_reader()
            policy_fingerprint = self._strict_guard_policy_fingerprint()
        except (RuntimeError, ValueError, TypeError, OSError, AttributeError):
            return False
        return bool(
            snapshot is not None
            and snapshot.snapshot_fingerprint == self._preflight_task_fingerprint
            and isinstance(identity, Mapping)
            and identity.get("task_fingerprint") == self._preflight_task_fingerprint
            and identity.get("guard_session_id") == evidence.get("guardSessionId")
            and identity.get("collision_scene_policy_fingerprint")
            == policy_fingerprint
            and evidence.get("policyFingerprint") == policy_fingerprint
        )

    @property
    def templateCollisionExclusionActive(self) -> bool:
        """Whether this process uses the explicit historical x4 override."""

        return bool(
            self._template_collision_exclusion_active
            and self.historicalTemplateOverrideEnabled
        )

    @property
    def historicalTemplateOverrideEnabled(self) -> bool:
        """Whether the retired case-specific bypass was explicitly enabled."""

        return os.environ.get(HISTORICAL_TEMPLATE_OVERRIDE_ENV, "") == "1"

    @property
    def anatomyReviewState(self) -> Mapping[str, Any]:
        """Session-only manual anatomy-review state, never package authority."""

        try:
            parameter_node = self._require_context()
            state = self._logic.step6AnatomyReviewState(parameter_node)
        except (RuntimeError, ValueError, AttributeError):
            return {"exists": False, "active": False}
        values = {
            key: value
            for key, value in state.items()
            if key != "proxyNode"
        }
        # A restored proxy may still carry its old active flag.  It is not
        # authoritative unless the explicitly opt-in historical review mode is
        # enabled for this process.
        if "effectiveActive" in values:
            values["active"] = bool(values["effectiveActive"])
        return values

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
        self._template_collision_exclusion_active = False
        self._template_collision_excluded_object_ids = ()
        self._runtime_validated_task_home_key = ""
        self._runtime_task_home_evidence = {}
        self._runtime_validated_workspace_key = ""
        if self._incomplete_preview_evidence is None:
            self._robot_away_from_home = False

    def invalidateMotionPlan(self) -> None:
        """Drop task/phase plans without discarding the connected scene audit."""

        self.stopPreview()
        self._clear_phase_session()

    def plannerComparisonIdentity(self) -> dict[str, str]:
        """Freeze the exact branch and live planning inputs for one comparison."""

        parameter_node = self._require_context()
        registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
        branch_id = str(registry.get("selected_branch_id") or "")
        snapshot = self._logic.confirmedTaskRecord(parameter_node)
        collision = self._logic.collisionSceneAuditRecord(parameter_node)
        if not branch_id or snapshot is None or collision is None:
            raise ValueError("Select a verified branch and confirm the current Step 6 task first.")
        return {
            "branch_id": branch_id,
            "task": snapshot.snapshot_fingerprint,
            "base": self._logic.robotBaseFingerprint(parameter_node),
            "home": snapshot.home_fingerprint,
            "trajectory": self._logic.step6TrajectoryRevision(parameter_node),
            "robot_profile": self._logic.robotProfileFingerprint(),
            "collision_audit": planner_comparison_scene_fingerprint(collision),
        }

    def capturePlannerComparisonAttempt(self, planner_id: str, result) -> dict[str, object]:
        """Copy one trial's diagnostic and representative path before the next trial."""

        if planner_id not in PLANNER_COMPARISON_IDS:
            raise ValueError("The comparison planner is not configured.")
        session = None
        paths = {}
        expected = result.details.get("motionDiagnosticSessionFingerprint")
        if expected:
            record = self._logic.motionDiagnosticRecord(self._require_context())
            if record is None or record.session_fingerprint != expected:
                raise ValueError("The trial diagnostic changed before capture.")
            audit = self._logic.collisionSceneAuditRecord(self._require_context())
            if audit is None or record.collision_audit_fingerprint != audit.audit_fingerprint:
                raise ValueError("The trial diagnostic belongs to another collision audit.")
            session = record.to_dict()
            paths = {
                stage: list(self._diagnostic_candidate_paths.get(
                    record.selected_candidate_index, {}
                ).get(stage, ()))
                for stage in ("stage1", "stage2", "stage3")
            }
        outcome = (session or {}).get("full_task_outcome", {})
        return {
            "planner_id": planner_id,
            "status": (
                "Pass" if result.success and outcome.get("status") in
                {"Complete", "CompletedWithWarnings"} else "Fail"
            ),
            "message": str(result.message),
            "session": session,
            "paths": paths,
        }

    def invalidateWorkspaceRuntimeValidation(
        self, invalidate_motion_plan: bool = True
    ) -> None:
        """Invalidate live workspace evidence while preserving ROS/scene state."""

        self._runtime_validated_workspace_key = ""
        model_reader = getattr(self._logic, "robotWorkspaceModelNode", None)
        try:
            model = model_reader() if callable(model_reader) else None
        except Exception:
            model = None
        if model is not None:
            setter = getattr(model, "SetAttribute", None)
            if callable(setter):
                setter("DENTOBOT.WorkspaceRuntimeValidated", "false")
                setter("DENTOBOT.WorkspaceState", "Stale")
        if invalidate_motion_plan:
            self.invalidateMotionPlan()

    def invalidateTargetRuntimeState(self) -> None:
        """Drop target-bound runtime state without changing shared Home state."""

        self.stopPreview()
        self._clear_phase_session()
        self._planning_scene_object_count = 0
        self._planning_scene_synchronized = False
        self._template_collision_exclusion_active = False
        self._template_collision_excluded_object_ids = ()
        self._runtime_validated_workspace_key = ""
        self._diagnostic_candidate_paths = {}

    def setTemplateCollisionExclusionForFunctionalSimulation(
        self,
        enabled: bool,
    ) -> RobotActionResult:
        """Toggle a historical, non-authoritative final-template exclusion.

        The setting is deliberately held only by this façade instance.  It is
        retired from the normal baseline, never written to MRML or a DentoCase
        package, and the complete template is restored by ordinary scene
        synchronization when disabled.
        """

        try:
            parameter_node = self._require_context()
            enabled = bool(enabled)
            if enabled and not self.historicalTemplateOverrideEnabled:
                raise ValueError(
                    "The historical Step 5C template-collision bypass is retired "
                    f"from the baseline. Set {HISTORICAL_TEMPLATE_OVERRIDE_ENV}=1 "
                    "only for an explicitly documented legacy diagnostic."
                )
            if self.previewActive:
                raise ValueError("Stop the guarded preview before changing collision scope.")
            if self._robot_away_from_home:
                raise ValueError(
                    "Return to Task Home before changing the template collision scope."
                )
            if enabled and parameter_node.finalPrintableTemplateModel is None:
                raise ValueError(
                    "The explicit override requires the unresolved Step 5C final template."
                )
            self.invalidateMotionPlan()
            self._template_collision_exclusion_active = enabled
            self._template_collision_excluded_object_ids = ()
            if (
                not enabled
                and self._logic.isRos2MotionControlActive(
                    parameter_node.robotBaseTransform
                )
            ):
                self._planning_scene_object_count = (
                    self._logic.syncStep6MoveItPlanningScene(parameter_node)
                )
                self._planning_scene_synchronized = True
            return RobotActionResult(
                True,
                (
                    "template_collision_exclusion_enabled"
                    if enabled
                    else "template_collision_exclusion_disabled"
                ),
                (
                    "FUNCTIONAL SIMULATION ONLY: the unresolved Step 5C final "
                    "template will remain visible but will be removed from "
                    "MoveIt collision evaluation for the next x4 plan. All "
                    "anatomy, self-collision, bounds, corridor, endpoint, and "
                    "phase-guard checks remain active. This is not physical "
                    "collision-valid evidence."
                    if enabled
                    else "Restored the complete authoritative collision scene; "
                    "the Step 5C final template is collision checked again."
                ),
                details={"active": enabled, "persistent": False},
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return RobotActionResult(
                False,
                "template_collision_exclusion_failed",
                str(exc),
            )

    def beginSessionAnatomyReview(self, segment_id: str) -> RobotActionResult:
        """Create an inactive editable copy of one non-target anatomy segment."""

        try:
            parameter_node = self._require_context()
            if self.previewActive:
                raise ValueError("Stop the guarded preview before reviewing anatomy.")
            if self._robot_away_from_home:
                raise ValueError("Return to Task Home before reviewing anatomy.")
            state = self._logic.beginStep6AnatomyReview(parameter_node, segment_id)
            return RobotActionResult(
                True,
                "anatomy_review_copy_created",
                (
                    "Created an inactive session-only review copy. Edit only the "
                    "local suspected artifact in Segment Editor; the source CBCT "
                    "segmentation remains unchanged and collision planning still "
                    "uses it until explicit confirmation."
                ),
                details={key: value for key, value in state.items() if key != "proxyNode"},
                payload=state,
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return RobotActionResult(False, "anatomy_review_copy_failed", str(exc))

    def activateSessionAnatomyReviewProxy(self, active: bool) -> RobotActionResult:
        """Apply or withdraw an explicitly confirmed session-only proxy.

        Activating it is an anatomy/collision-scene change: transient phases
        are discarded and task confirmation must be repeated after a fresh
        acknowledged collision-scene synchronization.
        """

        try:
            parameter_node = self._require_context()
            if self.previewActive:
                raise ValueError("Stop the guarded preview before changing anatomy review.")
            if self._robot_away_from_home:
                raise ValueError("Return to Task Home before changing anatomy review.")
            state = self._logic.setStep6AnatomyReviewProxyActive(
                parameter_node, bool(active)
            )
            self._runtime_validated_task_home_key = ""
            self._runtime_task_home_evidence = {}
            self._runtime_validated_workspace_key = ""
            self.invalidateMotionPlan()
            self._planning_scene_synchronized = False
            self._planning_scene_object_count = 0
            self._logic.invalidateStep6TaskConfirmation(
                parameter_node,
                "Research simulation anatomy override changed; re-sync and reconfirm the task.",
            )
            if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                self._planning_scene_object_count = self._logic.syncStep6MoveItPlanningScene(
                    parameter_node
                )
                self._planning_scene_synchronized = True
            return RobotActionResult(
                True,
                (
                    "anatomy_review_proxy_activated"
                    if active
                    else "anatomy_review_proxy_deactivated"
                ),
                (
                    "RESEARCH SIMULATION ANATOMY OVERRIDE ACTIVE: only the "
                    "explicitly reviewed local proxy is used for this process. "
                    "Source anatomy is unchanged; re-confirm the task before planning."
                    if active
                    else "Returned to source anatomy collision geometry; re-confirm the task before planning."
                ),
                details={key: value for key, value in state.items() if key != "proxyNode"},
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return RobotActionResult(False, "anatomy_review_proxy_failed", str(exc))

    def discardSessionAnatomyReview(self) -> RobotActionResult:
        """Discard the editable proxy without touching source anatomy."""

        try:
            parameter_node = self._require_context()
            if self.previewActive:
                raise ValueError("Stop the guarded preview before discarding anatomy review.")
            if self._robot_away_from_home:
                raise ValueError("Return to Task Home before discarding anatomy review.")
            previous = self._logic.step6AnatomyReviewState(parameter_node)
            discarded = self._logic.discardStep6AnatomyReview(parameter_node)
            if not discarded:
                return RobotActionResult(True, "anatomy_review_already_absent", "No session anatomy-review copy exists.")
            self.invalidateMotionPlan()
            self._planning_scene_synchronized = False
            self._planning_scene_object_count = 0
            if previous.get("active"):
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                self._runtime_validated_workspace_key = ""
                self._logic.invalidateStep6TaskConfirmation(
                    parameter_node,
                    "Research simulation anatomy override was discarded; re-sync and reconfirm the task.",
                )
                if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                    self._planning_scene_object_count = self._logic.syncStep6MoveItPlanningScene(
                        parameter_node
                    )
                    self._planning_scene_synchronized = True
            return RobotActionResult(
                True,
                "anatomy_review_discarded",
                "Discarded the session-only review copy. Source anatomy was never changed.",
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return RobotActionResult(False, "anatomy_review_discard_failed", str(exc))

    def _clear_phase_session(self) -> None:
        """Invalidate all local state tied to one transient task-guard session."""

        if self._guarded_preview_active:
            self._latch_incomplete_preview(
                "The guarded phase session was cleared before endpoint verification."
            )
            self._stop_preview_timer()
            self._guarded_preview_active = False

        if self._phase_stream_paused:
            resume_stream = getattr(
                self._bridge, "resume_slicer_joint_command_stream", None
            )
            try:
                if callable(resume_stream):
                    resume_stream()
            finally:
                self._phase_stream_paused = False
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
        self._phase_guard_session_id = ""
        self._preflight_drilling_plan = None
        self._preflight_task_fingerprint = ""
        self._preflight_orientation_commitment = {}
        self._preflight_complete_approach_evidence = None
        self._step6_preentry_candidate_cache = None
        self._step6_stage_diagnostic_chain = {}
        self._accepted_motion_history = []
        self._motion_history_task_fingerprint = ""

    @staticmethod
    def _normalize_guide_clearance_warnings(records) -> tuple[dict[str, object], ...]:
        normalized = []
        for record in tuple(records or ())[:256]:
            if not isinstance(record, Mapping):
                continue
            minimum = record.get("minimum_guide_clearance_warning_m")
            try:
                minimum = None if minimum is None else float(minimum)
            except (TypeError, ValueError):
                minimum = None
            normalized.append(
                {
                    "phase": str(record.get("phase") or ""),
                    "sequence": int(record.get("sequence", -1)),
                    "waypoint_index": int(record.get("waypoint_index", -1)),
                    "guide_clearance_warning_sample_count": max(
                        0, int(record.get("guide_clearance_warning_sample_count", 0))
                    ),
                    "minimum_guide_clearance_warning_m": minimum,
                    "guide_clearance_warning_robot_link": str(
                        record.get("guide_clearance_warning_robot_link") or ""
                    ),
                    "guide_clearance_warning_object_id": str(
                        record.get("guide_clearance_warning_object_id") or ""
                    ),
                    "guide_warning_kind": str(record.get("guide_warning_kind") or ""),
                    "guide_clearance_warning_contact_penetration_m": (
                        None
                        if record.get("guide_clearance_warning_contact_penetration_m") is None
                        else float(record.get("guide_clearance_warning_contact_penetration_m"))
                    ),
                    "guide_clearance_warning_contact_sample_count": max(
                        0,
                        int(record.get("guide_clearance_warning_contact_sample_count", 0)),
                    ),
                    "guide_clearance_warning_contact_position_base_m": (
                        tuple(float(value) for value in record.get(
                            "guide_clearance_warning_contact_position_base_m"
                        ))
                        if record.get("guide_clearance_warning_contact_position_base_m")
                        is not None
                        else None
                    ),
                    "reason": _bounded_text(record.get("reason") or ""),
                }
            )
        return tuple(normalized)

    @classmethod
    def _guide_clearance_warning_summary(
        cls, records
    ) -> dict[str, object]:
        warnings = cls._normalize_guide_clearance_warnings(records)
        minimums = tuple(
            float(record["minimum_guide_clearance_warning_m"])
            for record in warnings
            if record["minimum_guide_clearance_warning_m"] is not None
        )
        pairs = []
        for record in warnings:
            pair = (
                record["guide_clearance_warning_robot_link"],
                record["guide_clearance_warning_object_id"],
            )
            if pair not in pairs:
                pairs.append(pair)
        return {
            "guideClearanceWarnings": [dict(record) for record in warnings],
            "guideClearanceWarningCount": len(warnings),
            "minimumGuideClearanceWarningM": min(minimums) if minimums else None,
            "guideClearanceWarningPairs": [list(pair) for pair in pairs],
            "guideClearanceWarningKinds": sorted(
                {
                    str(record.get("guide_warning_kind") or "")
                    for record in warnings
                    if record.get("guide_warning_kind")
                }
            ),
            "guideClearanceWarningContactPenetrationMm": [
                float(record["guide_clearance_warning_contact_penetration_m"]) * 1000.0
                for record in warnings
                if record.get("guide_clearance_warning_contact_penetration_m") is not None
            ],
            "guideClearanceWarningContactCount": sum(
                int(record.get("guide_clearance_warning_contact_sample_count", 0))
                for record in warnings
            ),
        }

    def _capture_motion_history_home(self, positions, task_fingerprint: str) -> None:
        self._accepted_motion_history = [
            {"positions": dict(positions), "phase": "home"}
        ]
        self._motion_history_task_fingerprint = str(task_fingerprint)

    def _append_motion_history_waypoint(
        self, positions, phase: str, task_fingerprint: str
    ) -> None:
        if self._motion_history_task_fingerprint != str(task_fingerprint):
            return
        if not self._accepted_motion_history:
            return
        self._accepted_motion_history.append(
            {"positions": dict(positions), "phase": str(phase)}
        )

    @staticmethod
    def _preview_positions_snapshot(positions):
        if not isinstance(positions, Mapping):
            return None
        try:
            return {str(name): float(value) for name, value in positions.items()}
        except (TypeError, ValueError):
            return None

    def _preview_request_status(self, request, *, accepted: bool, message: str):
        status = None
        getter = getattr(self._bridge, "last_task_joint_status", None)
        try:
            status = getter() if callable(getter) else None
        except Exception:
            status = None
        identity_matches = bool(
            status is not None
            and getattr(status, "task_fingerprint", "")
            == request.get("taskFingerprint")
            and getattr(status, "phase", "") == request.get("phase")
            and getattr(status, "sequence", -1) == request.get("sequence")
            and (
                not request.get("guardSessionId")
                or getattr(status, "guard_session_id", "")
                == request.get("guardSessionId")
            )
        )
        status_shape_matches = bool(
            identity_matches
            and bool(getattr(status, "accepted", False)) is bool(accepted)
            and not bool(getattr(status, "validate_only", False))
        )
        status_reason = str(getattr(status, "reason", "") or "")
        if accepted:
            message_matches_status = bool(status_reason and message == status_reason)
        else:
            pair = (
                f" ({getattr(status, 'first_body', '') or '?'} ↔ "
                f"{getattr(status, 'second_body', '') or '?'})"
                if getattr(status, "first_body", "")
                or getattr(status, "second_body", "")
                else ""
            )
            expected_message = (
                f"Task guard rejected {request.get('phase')} sequence "
                f"{int(request.get('sequence', -1))}: {status_reason}{pair}"
            )
            message_matches_status = bool(status_reason and message == expected_message)
        current_status_matches = bool(status_shape_matches and message_matches_status)
        evaluated = None
        if current_status_matches:
            raw_evaluated = tuple(getattr(status, "evaluated_positions", ()) or ())
            if len(raw_evaluated) == len(JOINT_NAMES):
                try:
                    evaluated = {
                        name: float(value)
                        for name, value in zip(JOINT_NAMES, raw_evaluated)
                    }
                except (TypeError, ValueError):
                    evaluated = None
        return {
            "statusIdentityMatched": identity_matches,
            "statusMessageMatched": message_matches_status,
            "evaluatedStateStatus": "known" if evaluated is not None else "unknown",
            "evaluatedPositionsSi": evaluated,
            "evaluatedSampleIndex": (
                getattr(status, "evaluated_sample_index", None)
                if current_status_matches else None
            ),
            "firstRejectionInterpolationFraction": (
                getattr(status, "first_rejection_interpolation_fraction", None)
                if current_status_matches and not accepted else None
            ),
            "firstBody": (
                str(getattr(status, "first_body", "") or "")
                if current_status_matches and not accepted else ""
            ),
            "secondBody": (
                str(getattr(status, "second_body", "") or "")
                if current_status_matches and not accepted else ""
            ),
            "nativeReason": (
                _bounded_text(status_reason)
                if current_status_matches else _bounded_text(message)
            ),
        }

    def _preview_prefix_snapshot(self):
        prefix = []
        for record in tuple(self._accepted_motion_history or ()):
            positions = self._preview_positions_snapshot(record.get("positions"))
            if positions is None:
                continue
            prefix.append(
                {"phase": str(record.get("phase") or ""), "positionsSi": positions}
            )
        return prefix

    def _latch_incomplete_preview(
        self, reason: str, *, request=None, first_rejected=None
    ):
        evidence = self._incomplete_preview_evidence
        if evidence is None:
            prefix = self._preview_prefix_snapshot()
            captured_home = prefix[0]["positionsSi"] if prefix else None
            last_accepted = prefix[-1]["positionsSi"] if prefix else None
            bridge_accepted = None
            monitored = None
            for attribute, target in (
                ("last_accepted_joint_positions_si", "accepted"),
                ("monitored_joint_positions_si", "monitored"),
            ):
                reader = getattr(self._bridge, attribute, None)
                try:
                    value = reader() if callable(reader) else None
                except Exception:
                    value = None
                snapshot = self._preview_positions_snapshot(value)
                if target == "accepted":
                    bridge_accepted = snapshot
                else:
                    monitored = snapshot
            evidence = {
                "status": "Incomplete",
                "endpointVerified": False,
                "reason": _bounded_text(reason),
                "taskFingerprint": str(self._guarded_preview_task_fingerprint or ""),
                "phase": str(self._guarded_preview_phase or ""),
                "capturedHomePositionsSi": captured_home,
                "acceptedPrefix": prefix,
                "acceptedWaypointCount": max(0, len(prefix) - 1),
                "lastAcceptedHistoryPositionsSi": last_accepted,
                "lastAcceptedPositionsSi": bridge_accepted,
                "lastMonitoredPositionsSi": monitored,
                "firstRejected": first_rejected,
                "pendingRequest": None,
                "pendingRequestOutcome": None,
            }
            self._incomplete_preview_evidence = evidence
        if request is not None:
            evidence["pendingRequest"] = {
                "phase": str(request.get("phase") or ""),
                "sequence": int(request.get("sequence", -1)),
                "waypointIndex": int(request.get("waypointIndex", -1)),
                "requestedPositionsSi": dict(
                    request.get("requestedPositionsSi") or {}
                ),
            }
        if first_rejected is not None and evidence.get("firstRejected") is None:
            evidence["firstRejected"] = first_rejected
        return evidence

    def _record_incomplete_preview_request_result(
        self, request, *, accepted: bool, message: str
    ):
        evidence = self._incomplete_preview_evidence
        if evidence is None:
            return
        status_evidence = self._preview_request_status(
            request, accepted=accepted, message=message
        )
        evidence["pendingRequestOutcome"] = {
            "accepted": bool(accepted),
            "message": _bounded_text(message),
            **status_evidence,
        }
        if not accepted and evidence.get("firstRejected") is None:
            evidence["firstRejected"] = {
                "phase": str(request.get("phase") or ""),
                "sequence": int(request.get("sequence", -1)),
                "waypointIndex": int(request.get("waypointIndex", -1)),
                "requestedPositionsSi": dict(
                    request.get("requestedPositionsSi") or {}
                ),
                **status_evidence,
            }
        if accepted:
            live_prefix = self._preview_prefix_snapshot()
            expected_prefix_count = int(request.get("acceptedPrefixCount", -1))
            if (
                self._motion_history_task_fingerprint
                == request.get("taskFingerprint")
                and len(live_prefix) - 1 > expected_prefix_count
                and live_prefix[-1]["phase"] == str(request.get("phase") or "")
                and live_prefix[-1]["positionsSi"]
                == self._preview_positions_snapshot(
                    request.get("requestedPositionsSi")
                )
            ):
                evidence["acceptedPrefix"] = live_prefix
                evidence["acceptedWaypointCount"] = max(0, len(live_prefix) - 1)
                evidence["lastAcceptedHistoryPositionsSi"] = live_prefix[-1][
                    "positionsSi"
                ]
                expected_prefix_count = -1
            prefix = list(evidence.get("acceptedPrefix") or ())
            if len(prefix) - 1 == expected_prefix_count:
                positions = self._preview_positions_snapshot(
                    request.get("requestedPositionsSi")
                )
                if positions is not None:
                    prefix.append(
                        {"phase": str(request.get("phase") or ""), "positionsSi": positions}
                    )
                    evidence["acceptedPrefix"] = prefix
                    evidence["acceptedWaypointCount"] = max(0, len(prefix) - 1)
                    evidence["lastAcceptedHistoryPositionsSi"] = positions
        reader = getattr(self._bridge, "last_accepted_joint_positions_si", None)
        try:
            evidence["lastAcceptedPositionsSi"] = self._preview_positions_snapshot(
                reader() if callable(reader) else None
            )
        except Exception:
            evidence["lastAcceptedPositionsSi"] = None
        reader = getattr(self._bridge, "monitored_joint_positions_si", None)
        try:
            evidence["lastMonitoredPositionsSi"] = self._preview_positions_snapshot(
                reader() if callable(reader) else None
            )
        except Exception:
            evidence["lastMonitoredPositionsSi"] = None

    def _incomplete_preview_block(self, code: str, message: str) -> RobotActionResult:
        return RobotActionResult(
            False,
            code,
            message,
            details={"incompletePreview": deepcopy(self._incomplete_preview_evidence)},
        )

    @property
    def manualBaseAcceptanceInProgress(self) -> bool:
        """True while Accept/Reconcile Base owns a sanctioned Base pose change."""
        return bool(self._manual_base_acceptance_in_progress)

    def _parameter_node(self):
        return self._parameter_node_provider()

    def checkStraightJointPath(
        self,
        start_si: Mapping[str, float],
        goal_si: Mapping[str, float],
        *,
        max_revolute_step_rad: float = 0.02,
        max_prismatic_step_m: float = 0.0005,
    ) -> RobotActionResult:
        """Read-only diagnostic: is the straight joint-space path collision-free?

        Samples the linear J1-J5 interpolation (shortest angle for the
        continuous J5) and queries MoveIt static state validity, which includes
        collision against the synchronized PlanningScene, at every sample. It
        never moves the robot and grants no route or preview authority. A clear
        straight path that the planner still fails to return points at the
        planner/configuration, not at the robot or the scene.
        """
        names = [name for name in start_si if name in goal_si]
        if not names:
            return RobotActionResult(False, "straight_path_invalid_input", "No common joints.")
        deltas = {}
        for name in names:
            delta = float(goal_si[name]) - float(start_si[name])
            if name.endswith("Revolute-5"):
                delta = atan2(sin(delta), cos(delta))
            deltas[name] = delta
        steps = 1
        for name, delta in deltas.items():
            limit = max_prismatic_step_m if "Slider" in name else max_revolute_step_rad
            steps = max(steps, int(ceil(abs(delta) / limit)))
        checker = getattr(self._bridge, "check_moveit_static_joint_state", None)
        if not callable(checker):
            return RobotActionResult(False, "straight_path_unavailable", "MoveIt state validity is unavailable.")
        for index in range(steps + 1):
            fraction = index / steps
            sample = {name: float(start_si[name]) + deltas[name] * fraction for name in names}
            valid, message, authoritative = checker(sample)
            if not authoritative:
                return RobotActionResult(
                    False, "straight_path_unknown",
                    "State validity was not authoritative: " + str(message),
                    details={"samples_checked": index, "steps": steps, "fraction": fraction,
                             "route_authority": "none"},
                )
            if not valid:
                return RobotActionResult(
                    False, "straight_path_blocked",
                    f"Straight joint path is invalid at {fraction:.3f}: {message}",
                    details={"samples_checked": index + 1, "steps": steps,
                             "first_invalid_fraction": fraction,
                             "first_invalid_state_si": sample, "message": str(message),
                             "joint_deltas": deltas, "route_authority": "none"},
                )
        return RobotActionResult(
            True, "straight_path_clear",
            f"Straight joint path is collision-free and valid at all {steps + 1} samples.",
            details={"samples_checked": steps + 1, "steps": steps, "joint_deltas": deltas,
                     "route_authority": "none"},
        )

    def _motionControlNodeIdentity(self) -> tuple[str, str]:
        """Return (robot node ID, motion-control node ID) from the motion module.

        These IDs live on the motion-control logic's own parameter node, not on
        the workflow parameter node. Fail closed when they cannot be read.
        """
        getter = getattr(self._bridge, "get_motion_control_logic", None)
        motion_logic = getter() if callable(getter) else None
        motion_parameter = (
            motion_logic.getParameterNode() if motion_logic is not None else None
        )
        robot_id = str(getattr(motion_parameter, "robotNodeID", "") or "")
        motion_id = str(getattr(motion_parameter, "motionControlNodeID", "") or "")
        if not robot_id or not motion_id:
            raise ValueError("Workspace motion-control node identity is unavailable.")
        return robot_id, motion_id

    def _require_context(self):
        parameter_node = self._parameter_node()
        if parameter_node is None:
            raise RuntimeError("Step 6 parameter node is unavailable.")
        if self._logic is None:
            raise RuntimeError("DENTOBOT workflow logic is unavailable.")
        return parameter_node

    def _scene_kind(self, parameter_node) -> str:
        if parameter_node.inputVolume and parameter_node.teethSegmentation:
            return "case"
        return "none"

    def _scene_preparation_issue(self, parameter_node) -> str:
        if self._scene_kind(parameter_node) != "case":
            return ""
        checker = getattr(self._logic, "step6CaseJawOpeningFreshnessIssues", None)
        if not callable(checker):
            return ""
        issues = checker(parameter_node)
        return " ".join(str(issue) for issue in issues if issue)


    @staticmethod
    def _guide_fit_evidence(parameter_node) -> dict[str, object]:
        """Report guide/burr dimensional fit separately from simulation safety."""

        bore_values = []
        for field_name in ("templateChannelDiameterMm", "templateSleeveInnerDiameterMm"):
            try:
                value = float(getattr(parameter_node, field_name))
            except (AttributeError, TypeError, ValueError):
                continue
            if isfinite(value) and value > 0.0:
                bore_values.append((field_name, value))
        if not bore_values:
            return {
                "status": "Unknown",
                "burrDiameterMm": PROVISIONAL_BURR_DIAMETER_MM,
                "guideBoreDiameterMm": None,
                "physicalFitFailure": False,
                "message": "Guide bore is unavailable; physical fit was not evaluated.",
            }
        source, bore = min(bore_values, key=lambda item: item[1])
        fits = PROVISIONAL_BURR_DIAMETER_MM <= bore + 1.0e-9
        return {
            "status": "Pass" if fits else "PhysicalFitFailure",
            "burrDiameterMm": PROVISIONAL_BURR_DIAMETER_MM,
            "guideBoreDiameterMm": bore,
            "guideBoreSource": source,
            "physicalFitFailure": not fits,
            "message": (
                f"Physical fit pass: {PROVISIONAL_BURR_DIAMETER_MM:.2f} mm burr "
                f"≤ {bore:.2f} mm guide bore."
                if fits
                else
                f"PHYSICAL-FIT FAILURE: {PROVISIONAL_BURR_DIAMETER_MM:.2f} mm "
                f"burr exceeds the {bore:.2f} mm guide bore ({source}). "
                "Exploratory simulation may continue under the explicit burr/guide "
                "exception, but this is not a printable or executable fit."
            ),
        }

    @staticmethod
    def _tool_insertion_evidence(
        entry_ras_mm: Sequence[float], target_ras_mm: Sequence[float]
    ) -> dict[str, object]:
        """Return the provisional drilling-plus-guide insertion envelope."""

        requested_depth_mm = sqrt(
            sum(
                (float(target_ras_mm[index]) - float(entry_ras_mm[index])) ** 2
                for index in range(3)
            )
        )
        requested_combined_mm = (
            requested_depth_mm + PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM
        )
        maximum_combined_mm = PROVISIONAL_MAXIMUM_COMBINED_INSERTION_MM
        remaining_margin_mm = maximum_combined_mm - requested_combined_mm
        within_provisional_envelope = requested_combined_mm <= maximum_combined_mm + 1.0e-9
        return {
            "status": "Pass" if within_provisional_envelope else "Warning",
            "code": "" if within_provisional_envelope else "PROVISIONAL_INSERTION_ENVELOPE_WARNING",
            "planningAllowed": True,
            "requestedDrillingDepthMm": requested_depth_mm,
            "guideShellTraversalAllowanceMm": PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM,
            "requestedCombinedInsertionMm": requested_combined_mm,
            "maximumCombinedInsertionMm": maximum_combined_mm,
            "effectiveToolProtrusionMm": PROVISIONAL_EFFECTIVE_TOOL_PROTRUSION_MM,
            "remainingVisibleProtrusionMm": PROVISIONAL_REMAINING_VISIBLE_PROTRUSION_MM,
            # Compatibility aliases for older diagnostic consumers.
            "reservedAxialClearanceMm": PROVISIONAL_AXIAL_CLEARANCE_MM,
            "maximumAllowedDrillingDepthMm": None,
            "requestedTargetPreserved": True,
            "remainingInsertionMarginMm": remaining_margin_mm,
            "message": (
                "Combined insertion envelope PASS (provisional operator-specified "
                "guide/shell allowance; no shell measurement or calibration): "
                f"requested drilling depth {requested_depth_mm:.3f} mm + guide/shell "
                f"traversal allowance {PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM:.3f} "
                f"mm = requested combined insertion {requested_combined_mm:.3f} mm; "
                f"maximum combined insertion {maximum_combined_mm:.3f} mm, effective "
                f"tool protrusion {PROVISIONAL_EFFECTIVE_TOOL_PROTRUSION_MM:.3f} mm, "
                f"remaining visible/protrusion clearance "
                f"{PROVISIONAL_REMAINING_VISIBLE_PROTRUSION_MM:.3f} mm."
                if within_provisional_envelope
                else "WARNING: requested "
                f"combined insertion {requested_combined_mm:.3f} mm (drilling depth "
                f"{requested_depth_mm:.3f} mm + provisional guide/shell allowance "
                f"{PROVISIONAL_GUIDE_SHELL_TRAVERSAL_ALLOWANCE_MM:.3f} mm) exceeds "
                f"the provisional combined insertion envelope {maximum_combined_mm:.3f} mm by "
                f"{-remaining_margin_mm:.3f} mm. Effective tool protrusion is "
                f"{PROVISIONAL_EFFECTIVE_TOOL_PROTRUSION_MM:.3f} mm with "
                f"{PROVISIONAL_REMAINING_VISIBLE_PROTRUSION_MM:.3f} mm remaining "
                "visible/protrusion clearance; no shell measurement or calibration "
                "is claimed. The exact approved Entry→Target line will be planned; "
                "it was not shortened or moved."
            ),
        }
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
                "contactPolicy": "selected-target-burr-only-v1",
                "minimumClearanceM": float(
                    self._bridge.ROS2_RESEARCH_MINIMUM_CLEARANCE_M
                ),
                "jointOrder": tuple(self._bridge.ROS2_JOINT_SI_ORDER),
                "planningGroup": self._bridge.ROS2_PLANNING_GROUP,
                "tcpLink": self._bridge.ROS2_TOOL_TCP_LINK,
                # Only present when enabled, so default identities are unchanged.
                **({"spindleGuideContactToleranceM": 0.0005}
                   if self._spindle_guide_contact_allowed() else {}),
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
                    "ROIPositionAxisIK+MoveItStaticCollisionValid+BoundedHomeConnectedSubset"
                ),
                "candidateSampler": "ROI3D+PositionAxisIK",
            }
        )

    def _joint_positions_match(
        self,
        expected: Mapping[str, float],
        observed: Mapping[str, float],
    ) -> tuple[bool, float, tuple[str, ...]]:
        if set(expected) != set(JOINT_NAMES) or set(observed) != set(JOINT_NAMES):
            return False, float("inf"), tuple(JOINT_NAMES)
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

    def setJointPlanningPolicy(self, planner_id, planning_attempts, planning_time_sec) -> None:
        """Set the Home -> PreEntry joint-planning policy used by planning and Diagnose."""
        if planner_id not in STEP6_JOINT_PLANNER_ALGORITHMS:
            raise ValueError(f"Planner '{planner_id}' is not configured for DENTOBOT.")
        self._joint_planner_id = planner_id
        self._effective_joint_planner_id = ""
        self._joint_planning_attempts = max(1, min(10, int(planning_attempts)))
        self._joint_planning_time_sec = max(0.5, min(60.0, float(planning_time_sec)))

    def setApproachCorridorMarginSamples(self, samples: int) -> None:
        """Adaptive-corridor margin samples (restored per PreparedBranch)."""
        self._approach_corridor_margin_samples = max(0, int(samples))

    def approachCorridorMarginSamples(self) -> int:
        return int(self._approach_corridor_margin_samples or 0)

    def jointPlanningPolicy(self) -> dict:
        """The joint-planning policy Diagnose and P1 will actually use."""
        return {
            "planner_id": self._joint_planner_id,
            "planning_attempts": int(self._joint_planning_attempts),
            "planning_time_sec": float(self._joint_planning_time_sec),
            "independent_replans": STEP6_JOINT_PLAN_RETRIES,
        }

    def taskHomeValidationGap(self, parameter_node=None) -> str:
        """Say why Task Home is not runtime-validated ('' when it is).

        Mirrors the clauses of ``taskHomeRuntimeValidated`` so the UI can name the
        exact cause instead of a generic "validate Home" prompt.
        """

        parameter_node = parameter_node or self._parameter_node()
        if parameter_node is None or self._logic is None:
            return "No Step 6 context is available."
        try:
            freshness = self._logic.taskHomeFreshnessIssues(parameter_node)
            record = self._logic.taskHomeRecord(parameter_node)
            audit = self._logic.collisionSceneAuditRecord(parameter_node)
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            return f"Task Home state could not be read: {exc}"
        if freshness:
            return "Task Home is stale: " + " ".join(str(i) for i in freshness)
        if record is None:
            return "Save a case/base-specific Task Home in 6.2 (Review Draft, then Accept and Validate)."
        if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
            return "Connect ROS + MoveIt in 6.1; Task Home validation needs the live runtime."
        if str(getattr(record, "runtime_validation_status", "Unreviewed")) != "Validated":
            return "Task Home is saved but not live-validated: use Accept and Validate in 6.2."
        if str(getattr(record, "collision_audit_fingerprint", "")) != (
            str(audit.audit_fingerprint) if audit is not None else ""
        ):
            return (
                "The collision scene changed since Task Home was validated. "
                "Re-validate it in 6.2 (Review Draft, then Accept and Validate)."
            )
        if str(getattr(record, "guard_policy_fingerprint", "")) != self._strict_guard_policy_fingerprint():
            return (
                "Task Home was validated under a different guard policy (for example the "
                "spindle-housing contact option was changed). Re-validate it in 6.2 "
                "(Review Draft, then Accept and Validate), or restore the option."
            )
        if self._runtime_validated_task_home_key != self._task_home_runtime_key(record):
            return "Task Home validation was cleared by a later robot action; re-validate it in 6.2."
        return ""

    def workspaceRoiMatchesSavedEvidence(
        self,
        roi: TaskSpaceRoi,
        roi_source: Mapping[str, object],
        parameter_node=None,
    ) -> bool:
        """Check saved workspace ROI identity without changing workflow state."""

        try:
            parameter_node = parameter_node or self._parameter_node()
            if (
                parameter_node is None
                or not isinstance(roi, TaskSpaceRoi)
                or not isinstance(roi_source, Mapping)
            ):
                return False
            fields = {"openingRevision", "gapLineNodeId"}
            if set(roi_source) != fields:
                return False
            revision = roi_source["openingRevision"]
            gap_line_id = roi_source["gapLineNodeId"]
            if (
                isinstance(revision, bool)
                or not isinstance(revision, int)
                or revision < 0
                or not isinstance(gap_line_id, str)
                or not gap_line_id.strip()
                or gap_line_id != gap_line_id.strip()
            ):
                return False
            source = {
                "openingRevision": revision,
                "gapLineNodeId": gap_line_id,
            }
            payload = json.loads(
                str(parameter_node.step6AssistedLimitProposalJson or "")
            )
            if not isinstance(payload, Mapping):
                return False
            saved_source = payload.get("roi_source")
            saved_roi_payload = payload.get("roi")
            if (
                not isinstance(saved_source, Mapping)
                or set(saved_source) != fields
                or not isinstance(saved_roi_payload, Mapping)
                or set(saved_roi_payload)
                != {"center_world_ras_mm", "dimensions_mm"}
            ):
                return False
            saved_revision = saved_source["openingRevision"]
            saved_gap_line_id = saved_source["gapLineNodeId"]
            if (
                isinstance(saved_revision, bool)
                or not isinstance(saved_revision, int)
                or saved_revision < 0
                or not isinstance(saved_gap_line_id, str)
                or not saved_gap_line_id.strip()
                or saved_gap_line_id != saved_gap_line_id.strip()
                or dict(saved_source) != source
            ):
                return False
            source_fingerprint = fingerprint(source)
            if payload.get("roi_source_fingerprint") != source_fingerprint:
                return False
            saved_roi = TaskSpaceRoi(
                center_world_ras_mm=saved_roi_payload["center_world_ras_mm"],
                dimensions_mm=saved_roi_payload["dimensions_mm"],
            )
            if saved_roi_payload != {
                "center_world_ras_mm": list(saved_roi.center_world_ras_mm),
                "dimensions_mm": list(saved_roi.dimensions_mm),
            }:
                return False
            expected_roi_fingerprint = fingerprint(
                {
                    "center_world_ras_mm": roi.center_world_ras_mm,
                    "dimensions_mm": roi.dimensions_mm,
                    "source_fingerprint": source_fingerprint,
                }
            )
            return (
                saved_roi == roi
                and payload.get("roi_fingerprint") == expected_roi_fingerprint
            )
        except Exception:
            return False

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
            current_roi_result = self.defaultTaskSpaceRoi()
            if (
                not current_roi_result.success
                or not isinstance(current_roi_result.payload, Mapping)
            ):
                return False
            current_roi_payload = current_roi_result.payload
            current_revision = current_roi_payload.get("openingRevision")
            current_gap_id = current_roi_payload.get("gapLineNodeId")
            if (
                isinstance(current_revision, bool)
                or not isinstance(current_revision, int)
                or not isinstance(current_gap_id, str)
                or not current_gap_id.strip()
            ):
                return False
            current_roi_source = {
                "openingRevision": current_revision,
                "gapLineNodeId": current_gap_id.strip(),
            }
            saved_roi_source = payload.get("roi_source")
            saved_revision = (
                saved_roi_source.get("openingRevision")
                if isinstance(saved_roi_source, Mapping)
                else None
            )
            saved_gap_id = (
                saved_roi_source.get("gapLineNodeId")
                if isinstance(saved_roi_source, Mapping)
                else None
            )
            if (
                isinstance(saved_revision, bool)
                or not isinstance(saved_revision, int)
                or not isinstance(saved_gap_id, str)
                or not saved_gap_id.strip()
                or {
                    "openingRevision": saved_revision,
                    "gapLineNodeId": saved_gap_id.strip(),
                }
                != current_roi_source
            ):
                return False
            roi_source_fingerprint = fingerprint(current_roi_source)
            if payload.get("roi_source_fingerprint") != roi_source_fingerprint:
                return False
            saved_roi_payload = payload.get("roi")
            if not isinstance(saved_roi_payload, Mapping):
                return False
            saved_roi = TaskSpaceRoi(
                center_world_ras_mm=saved_roi_payload["center_world_ras_mm"],
                dimensions_mm=saved_roi_payload["dimensions_mm"],
            )
            roi_fingerprint = fingerprint(
                {
                    "center_world_ras_mm": saved_roi.center_world_ras_mm,
                    "dimensions_mm": saved_roi.dimensions_mm,
                    "source_fingerprint": roi_source_fingerprint,
                }
            )
            if payload.get("roi_fingerprint") != roi_fingerprint:
                return False

            trajectory_issues = self._logic.step6PlanningContextFreshnessIssues(
                parameter_node
            )
            trajectory = self._logic.step6TrajectorySummary(parameter_node)
            trajectory_fingerprint = str(
                self._logic.step6TrajectoryRevision(parameter_node) or ""
            )
            if (
                trajectory_issues
                or not isinstance(trajectory, Mapping)
                or not trajectory.get("isValid")
                or not trajectory_fingerprint
                or payload.get("trajectory_fingerprint") != trajectory_fingerprint
            ):
                return False
            entry = tuple(float(value) for value in trajectory["entryRas"])
            target = tuple(float(value) for value in trajectory["targetRas"])
            if (
                len(entry) != 3
                or len(target) != 3
                or not all(isfinite(value) for value in entry + target)
            ):
                return False
            axis_status = "ProvisionalSelectedTrajectory"
            axis_entry, axis_target = entry, target
            task_fingerprint = ""
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            if (
                snapshot is not None
                and not self._logic.confirmedTaskFreshnessIssues(parameter_node)
                and str(snapshot.trajectory_revision or "")
                == trajectory_fingerprint
            ):
                snapshot_entry = tuple(float(value) for value in snapshot.entry_ras_mm)
                snapshot_target = tuple(float(value) for value in snapshot.target_ras_mm)
                if (
                    tuple(round(value, 9) for value in snapshot_entry)
                    == tuple(round(value, 9) for value in entry)
                    and tuple(round(value, 9) for value in snapshot_target)
                    == tuple(round(value, 9) for value in target)
                ):
                    axis_status = "ConfirmedCurrent"
                    axis_entry, axis_target = snapshot_entry, snapshot_target
                    task_fingerprint = str(snapshot.snapshot_fingerprint or "")
            axis_fingerprint = fingerprint(
                {
                    "status": axis_status,
                    "entry_ras_mm": axis_entry,
                    "target_ras_mm": axis_target,
                    "trajectory_fingerprint": trajectory_fingerprint,
                    "task_fingerprint": task_fingerprint,
                }
            )
            if (
                payload.get("task_axis_status") != axis_status
                or payload.get("task_axis_fingerprint") != axis_fingerprint
                or payload.get("task_fingerprint", "") != task_fingerprint
            ):
                return False
        except (
            RuntimeError,
            TypeError,
            ValueError,
            KeyError,
            OverflowError,
            json.JSONDecodeError,
        ):
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
            return_home_required=self._robot_away_from_home,
        )

    def connect(
        self, *, open_motion_module: bool = False, progress=None
    ) -> RobotActionResult:
        try:
            if progress:
                progress("Checking Case Foundation and prepared branch")
            parameter_node = self._require_context()
            scene_kind = self._scene_kind(parameter_node)
            if scene_kind != "case":
                return RobotActionResult(
                    False,
                    "scene_required",
                    "Open a case and establish its Case Foundation before connecting.",
                )
            foundation = self._logic.evaluateCaseFoundationEligibility(parameter_node)
            if not foundation["pose"]["eligible"]:
                return RobotActionResult(
                    False,
                    str(foundation["pose"]["code"]).lower(),
                    str(foundation["pose"]["message"]),
                )
            branch = self._logic.evaluatePreparedBranchEligibility(parameter_node)
            if not branch["eligible"]:
                return RobotActionResult(
                    False,
                    str(branch["reason"]).lower(),
                    str(branch["message"]),
                )
            if not bool(parameter_node.step6PlanningContextImported):
                return RobotActionResult(
                    False,
                    "prepared_branch_activation_required",
                    "Activate the verified PreparedBranch for Step 6 first.",
                )
            if not foundation["base"]["eligible"]:
                return RobotActionResult(
                    False,
                    str(foundation["base"]["code"]).lower(),
                    str(foundation["base"]["message"]),
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
            if progress:
                progress("Creating ROS 2 robot and initializing MoveIt")
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
                    if progress:
                        progress("Preparing collision-scene audit")
                    obstacle_count = self._logic.syncStep6MoveItPlanningScene(
                        parameter_node,
                        **({"progress": progress} if progress else {}),
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
                if progress:
                    progress("Waiting for collision guard acknowledgement")
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
            if progress:
                progress("Checking connected robot candidate")
            candidate_result = self._apply_positions_si(bootstrap_positions_si)
            candidate_status = self._checkStateValidity()
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

    def disconnect(self, progress=None) -> RobotActionResult:
        try:
            if progress:
                progress("Stopping simulation preview")
            self.stopPreview()
            mrml_models = self._logic.robotModelNodes() if self._logic else []
            if progress:
                ok, message = self._bridge.disconnect_dentobot_motion_control(
                    mrml_models, progress=progress
                )
            else:
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
            foundation = self._logic.evaluateCaseFoundationEligibility(parameter_node)
            if foundation["base"]["code"] == "ROBOT_PROFILE_MISMATCH":
                self._logic.invalidateCaseFoundationBase(
                    parameter_node,
                    "The installed robot profile changed after base review.",
                )
            if not foundation["pose"]["eligible"]:
                return RobotActionResult(
                    False,
                    str(foundation["pose"]["code"]).lower(),
                    str(foundation["pose"]["message"]),
                )
            base, models = self._logic.createOrUpdateRobotPlacement(
                parameter_node.robotBaseTransform,
                self._positions_si(self._display_values(parameter_node)),
            )
            parameter_node.robotBaseTransform = base
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
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Joint jogging is blocked because a guarded preview stopped before endpoint verification.",
            )
        if self._manual_jog_reconciliation_required:
            return RobotActionResult(
                False,
                "manual_jog_reconciliation_required",
                "A prior submitted manual jog has unresolved state; use Reconcile State before jogging again.",
                details={
                    "manualJogReconciliationRequired": True,
                    "manualJogStatus": "unknown",
                    "manualJogUncertainty": deepcopy(self._manual_jog_uncertainty),
                },
            )
        if isinstance(joint_id, str):
            try:
                index = JOINT_NAMES.index(joint_id)
            except ValueError:
                return RobotActionResult(False, "unknown_joint", f"Unknown joint: {joint_id}")
        else:
            try:
                index = int(joint_id)
            except (TypeError, ValueError, OverflowError):
                return RobotActionResult(False, "unknown_joint", f"Unknown joint index: {joint_id}")
            if 1 <= index <= len(JOINT_NAMES):
                index -= 1
        if index < 0 or index >= len(JOINT_NAMES):
            return RobotActionResult(False, "unknown_joint", f"Unknown joint index: {joint_id}")
        return RobotActionResult(
            False,
            "guarded_manual_jog_required",
            "Legacy single-joint updates are disabled; submit the complete pose through the guarded manual-jog API.",
        )

    def _manual_jog_current_identity(
        self, expected_parameter_node=None, *, for_task_home_review: bool = False
    ) -> dict[str, str]:
        """Return the exact current confirmed or unconfirmed manual identity."""

        parameter_node = self._require_context()
        if expected_parameter_node is not None and parameter_node is not expected_parameter_node:
            raise ValueError("The active Step 6 parameter node changed during the jog.")
        if self.previewActive or self._guarded_preview_active:
            raise ValueError("Stop the guarded preview before manually jogging the robot.")
        if self._incomplete_preview_evidence is not None or self._robot_away_from_home:
            raise ValueError(
                "Manual jogging is blocked until the incomplete or away-from-Home state is resolved."
            )
        if self._scene_kind(parameter_node) != "case":
            raise ValueError("A current case collision scene is required for manual jogging.")
        if not bool(parameter_node.step6PlanningContextImported):
            raise ValueError("Import the current Step 6 planning context before manual jogging.")
        if not self._planning_scene_synchronized or self._planning_scene_object_count <= 0:
            raise ValueError("Synchronize the current collision scene before manual jogging.")
        if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
            raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
        snapshot = self._logic.confirmedTaskRecord(parameter_node)
        freshness_issues = self._step6_read_only_freshness_issues(
            parameter_node, include_home=snapshot is not None
        )
        if freshness_issues:
            raise ValueError("Planning inputs are stale: " + "; ".join(freshness_issues))

        task_home_json = str(parameter_node.step6TaskHomeJson or "")
        home = self._logic.taskHomeRecord(parameter_node)
        audit = self._logic.collisionSceneAuditRecord(parameter_node)
        if audit is None:
            raise ValueError("A current collision scene is required.")
        if snapshot is not None and home is None:
            raise ValueError("A current Task Home is required for confirmed-task jogging.")
        registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
        branch_id = str(registry.get("selected_branch_id") or "")
        branches = registry.get("prepared_branches")
        if (
            not branch_id
            or not isinstance(branches, Mapping)
            or branch_id not in branches
        ):
            raise ValueError("An active selected PreparedBranch is required.")
        branch = self._logic.evaluatePreparedBranchEligibility(
            parameter_node, branch_id, registry=registry
        )
        if not branch.get("eligible"):
            raise ValueError(str(branch.get("message") or branch.get("reason") or "PreparedBranch is stale."))
        acknowledgement = audit.runtime_acknowledgement
        if (
            audit.status != "Acknowledged"
            or acknowledgement.get("status") != "Acknowledged"
        ):
            raise ValueError("The current collision scene has no runtime acknowledgement.")
        base_fingerprint = self._logic.robotBaseFingerprint(parameter_node)
        home_fingerprint = fingerprint(home.to_dict()) if home is not None else ""
        trajectory_revision = self._logic.step6TrajectoryRevision(parameter_node)
        limits_fingerprint = self._logic.step6TaskLimitsFingerprint(parameter_node)
        robot_profile_fingerprint = self._logic.robotProfileFingerprint()
        scene_fingerprint = planner_comparison_scene_fingerprint(audit)
        if snapshot is None:
            if not for_task_home_review:
                reviewed_limits = getattr(self._logic, "assistedTaskLimitsReviewed", None)
                if not callable(reviewed_limits) or not reviewed_limits(parameter_node):
                    raise ValueError("Review the current assisted joint limits before manual jogging.")
            unconfirmed_home = "unconfirmed_home:" + fingerprint(
                {
                    "base": base_fingerprint,
                    "task_home_status": "present" if home is not None else "absent",
                    "task_home_content": task_home_json or None,
                }
            )
            unconfirmed_inputs = {
                "branch_id": branch_id,
                "trajectory": trajectory_revision,
                "base": base_fingerprint,
                "home": unconfirmed_home,
                "limits": limits_fingerprint,
                "robot_profile": robot_profile_fingerprint,
                "collision_audit": scene_fingerprint,
            }
            if any(not value for value in unconfirmed_inputs.values()):
                raise ValueError("The unconfirmed branch identity is incomplete.")
            identity = {
                "branch_id": branch_id,
                "task": "unconfirmed:" + fingerprint(unconfirmed_inputs),
                "base": base_fingerprint,
                "home": unconfirmed_home,
                "trajectory": trajectory_revision,
                "robot_profile": robot_profile_fingerprint,
                "collision_audit": scene_fingerprint,
            }
        else:
            task_issues = task_snapshot_invalidation_reasons(
                snapshot,
                target_segment_id=str(parameter_node.targetToothSegmentId or ""),
                trajectory_revision=trajectory_revision,
                base_fingerprint=base_fingerprint,
                home_fingerprint=home_fingerprint,
                limits_fingerprint=limits_fingerprint,
                robot_profile_fingerprint=robot_profile_fingerprint,
                tool_frame=str(parameter_node.step6ToolFrame),
            )
            if task_issues:
                raise ValueError("Confirmed task inputs are stale: " + "; ".join(task_issues))

            identity = self.plannerComparisonIdentity()
            expected_identity = {
                "branch_id": branch_id,
                "task": snapshot.snapshot_fingerprint,
                "base": base_fingerprint,
                "home": snapshot.home_fingerprint,
                "trajectory": trajectory_revision,
                "robot_profile": robot_profile_fingerprint,
                "collision_audit": scene_fingerprint,
            }
            if identity != expected_identity or any(not value for value in identity.values()):
                raise ValueError("Task, branch, base, Home, profile, or scene identity changed.")
        return {
            **identity,
            "limits": limits_fingerprint,
        }

    @staticmethod
    def _manual_simulation_identity_from_jog_identity(
        identity: Mapping[str, str],
    ) -> dict[str, str]:
        return {
            "prepared_branch_id": identity["branch_id"],
            "task_fingerprint": identity["task"],
            "base_fingerprint": identity["base"],
            "home_fingerprint": identity["home"],
            "trajectory_fingerprint": identity["trajectory"],
            "robot_profile_fingerprint": identity["robot_profile"],
            "scene_fingerprint": identity["collision_audit"],
        }

    def _manual_simulation_record_dict(self) -> dict[str, object]:
        if self._manual_simulation_identity is None:
            raise RuntimeError("No complete manual simulation identity is available.")
        return build_manual_simulation_record(
            identity=self._manual_simulation_identity,
            events=self._manual_simulation_events,
        )

    def _manual_simulation_freeze(self) -> Optional[dict[str, object]]:
        if self._manual_simulation_identity is None:
            return None
        record = self._manual_simulation_record_dict()
        if self._manual_simulation_events:
            self._manual_simulation_completed_records.append(deepcopy(record))
        self._manual_simulation_identity = None
        self._manual_simulation_events = []
        return record

    def _manual_simulation_begin(self, identity: Mapping[str, str]) -> None:
        clean_identity = self._manual_simulation_identity_from_jog_identity(identity)
        if self._manual_simulation_identity == clean_identity:
            return
        self._manual_simulation_freeze()
        self._manual_simulation_identity = clean_identity
        self._manual_simulation_events = []

    def _manual_simulation_prepare_current_identity(self) -> str:
        try:
            identity = self._manual_jog_current_identity()
            self._manual_simulation_begin(identity)
            return ""
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, AttributeError) as exc:
            self._manual_simulation_freeze()
            return _bounded_text(exc)

    def _manual_simulation_append_event(self, event: Mapping[str, object]) -> bool:
        if self._manual_simulation_identity is None:
            return False
        self._manual_simulation_events.append(dict(event))
        return True

    @staticmethod
    def _manual_simulation_json_safe(value: object) -> object:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if isfinite(value) else None
        if isinstance(value, Mapping):
            return {
                str(key): DENTORobotWorkflowFacade._manual_simulation_json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (tuple, list)):
            return [DENTORobotWorkflowFacade._manual_simulation_json_safe(item) for item in value]
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return DENTORobotWorkflowFacade._manual_simulation_json_safe(item())
            except (TypeError, ValueError, OverflowError):
                pass
        return _bounded_text(value)

    def _manual_jog_record_tcp_geometry(
        self,
        positions: Mapping[str, float],
        details: Mapping[str, object],
    ) -> tuple[Optional[dict[str, object]], str]:
        """Read optional FK only while the same manual identity and Base remain current."""

        try:
            expected = details.get("identityBefore")
            identity_after_guard = details.get("identityAfter")
            if (
                not isinstance(expected, Mapping)
                or details.get("identityStatus") != "current"
                or not isinstance(identity_after_guard, Mapping)
                or dict(identity_after_guard) != dict(expected)
            ):
                return None, "The manual jog identity is unavailable or stale."

            parameter_node = self._require_context()
            base = parameter_node.robotBaseTransform
            if base is None:
                return None, "The accepted robot Base is unavailable for FK."
            identity_before_fk = self._manual_jog_current_identity(parameter_node)
            if identity_before_fk != dict(expected):
                return None, "The manual jog identity changed before FK."
            base_matrix_before_fk = tuple(
                self._manual_simulation_base_matrix(parameter_node)
            )
            compute_fk = getattr(self._bridge, "compute_tcp_pose_world_ras_mm", None)
            if not callable(compute_fk):
                return None, "The bridge TCP FK helper is unavailable."
            try:
                ok, message, pose = compute_fk(positions, base_transform=base)
            except Exception as exc:
                ok, message, pose = False, _bounded_text(exc), None
            identity_after_fk = self._manual_jog_current_identity(parameter_node)
            base_matrix_after_fk = tuple(
                self._manual_simulation_base_matrix(parameter_node)
            )
            if (
                identity_after_fk != identity_before_fk
                or base_matrix_after_fk != base_matrix_before_fk
                or self._require_context() is not parameter_node
                or parameter_node.robotBaseTransform is not base
            ):
                return None, "The manual jog identity or accepted Base changed during FK."
            if not ok or pose is None:
                return None, _bounded_text(message or "TCP FK is unavailable.")
            rows = tuple(tuple(float(value) for value in row) for row in pose)
            if len(rows) != 4 or any(len(row) != 4 for row in rows):
                return None, "TCP FK did not return a 4×4 pose."
            flat = tuple(value for row in rows for value in row)
            if not all(isfinite(value) for value in flat):
                return None, "TCP FK returned a non-finite pose."

            axis = (flat[2], flat[6], flat[10])
            axis_length = sqrt(sum(value * value for value in axis))
            if not isfinite(axis_length) or axis_length <= 0.0:
                return None, "TCP FK returned a drill axis that cannot be normalized."
            return {
                "tcp_pose_world_ras_mm": list(flat),
                "tcp_point_ras_mm": [flat[3], flat[7], flat[11]],
                "drill_axis_world_ras_unit": [value / axis_length for value in axis],
            }, ""
        except Exception as exc:
            # Recording is optional evidence and must never change the jog result.
            return None, _bounded_text(exc)

    def _record_manual_jog_outcome(
        self,
        code: str,
        message: str,
        details: Mapping[str, object],
    ) -> None:
        if self._manual_simulation_identity is None:
            return
        requested = details.get("requestedJointPositionsSi")
        if not isinstance(requested, Mapping) or set(requested) != set(JOINT_NAMES):
            return
        native = self._manual_simulation_json_safe(
            details.get("nativeGuardEvidence") or {}
        )
        native = native if isinstance(native, Mapping) else {}
        policy_id = str(native.get("policyId") or "unknown")
        event_details = {
            "guard_policy_fingerprint": "unknown",
            "guard_policy_id": policy_id,
            "guard_policy_identity_status": "manual_policy_id_correlated"
            if policy_id == MANUAL_JOINT_POLICY_ID
            else "unknown",
            "guard_request_id": str(native.get("requestId") or "unknown"),
            "guard_session_id": str(native.get("sessionId") or "unknown"),
            "simulation_only": True,
            "route_authority": "none",
            "outcome_code": str(code),
            "outcome_message": _bounded_text(message),
            "identity_status": str(details.get("identityStatus") or "unknown"),
            "identity_before": self._manual_simulation_json_safe(
                details.get("identityBefore")
            ),
            "identity_after": self._manual_simulation_json_safe(
                details.get("identityAfter")
            ),
            "raw_guard_outcome": str(details.get("rawGuardOutcome") or "unknown"),
            "guard_accepted": details.get("guardAccepted"),
            "accepted_state_may_have_advanced": bool(
                details.get("acceptedStateMayHaveAdvanced")
            ),
            "monitored_state_status": str(
                details.get("monitoredStateStatus") or "unavailable/unknown"
            ),
            "native_guard_evidence": dict(native),
            # minimum_clearance_m is the configured threshold; distance fields
            # are native measurements and remain separate below.
            "configured_clearance_threshold_m": native.get("minimumClearanceM"),
            "measured_minimum_self_distance_m": native.get("minimumSelfDistanceM"),
            "measured_minimum_world_distance_m": native.get("minimumWorldDistanceM"),
            "first_pair": [native.get("firstBody", ""), native.get("secondBody", "")],
        }
        requested_joints = {name: float(requested[name]) for name in JOINT_NAMES}
        monitored_joints = None
        monitored = details.get("monitoredJointPositionsSi")
        if isinstance(monitored, Mapping) and set(monitored) == set(JOINT_NAMES):
            try:
                candidate = {name: float(monitored[name]) for name in JOINT_NAMES}
                if all(isfinite(value) for value in candidate.values()):
                    monitored_joints = candidate
            except (TypeError, ValueError, OverflowError):
                pass
        event_ns = monotonic_ns()
        accepted = details.get("acceptedJointPositionsSi")
        if (
            code == "manual_jog_accepted"
            and details.get("guardAccepted") is True
            and details.get("identityStatus") == "current"
            and isinstance(accepted, Mapping)
            and set(accepted) == set(JOINT_NAMES)
            and all(float(accepted[name]) == requested_joints[name] for name in JOINT_NAMES)
        ):
            geometry, geometry_reason = self._manual_jog_record_tcp_geometry(
                accepted, details
            )
            event_details["geometry_status"] = "accepted" if geometry else "unavailable"
            if geometry_reason:
                event_details["geometry_unavailable_reason"] = geometry_reason
            event = {
                "kind": "guard_accepted",
                "monotonic_ns": event_ns,
                "requested_joints": requested_joints,
                "accepted_joints": {name: float(accepted[name]) for name in JOINT_NAMES},
                "details": event_details,
            }
            if monitored_joints is not None:
                event["monitored_joints"] = monitored_joints
            if geometry is not None:
                event.update(geometry)
            self._manual_simulation_append_event(event)
            return

        accepted_before = details.get("currentAcceptedJointPositionsSiBefore")
        if (
            code == "manual_jog_rejected"
            and details.get("guardAccepted") is False
            and details.get("rawGuardOutcome") == "rejected"
            and isinstance(accepted_before, Mapping)
            and set(accepted_before) == set(JOINT_NAMES)
        ):
            geometry, geometry_reason = self._manual_jog_record_tcp_geometry(
                requested_joints, details
            )
            event_details["geometry_status"] = (
                "rejected_candidate" if geometry else "unavailable"
            )
            if geometry_reason:
                event_details["geometry_unavailable_reason"] = geometry_reason
            event = {
                "kind": "guard_rejected",
                "monotonic_ns": event_ns,
                "requested_joints": requested_joints,
                "accepted_joints": {
                    name: float(accepted_before[name]) for name in JOINT_NAMES
                },
                "native_failure_evidence": {
                    "guard_outcome": "rejected",
                    "message": _bounded_text(message),
                    "native": dict(native),
                },
                "details": event_details,
            }
            if monitored_joints is not None:
                event["monitored_joints"] = monitored_joints
            # This FK belongs to the rejected requested candidate, never to an
            # accepted path or to the unchanged accepted joint state.
            if geometry is not None:
                event.update(geometry)
            self._manual_simulation_append_event(event)
            return

        diagnostic: dict[str, object] = {
            "code": str(code),
            "message": _bounded_text(message),
            "identity_status": str(details.get("identityStatus") or "unknown"),
            "guard_accepted": details.get("guardAccepted"),
            "raw_guard_outcome": str(details.get("rawGuardOutcome") or "unknown"),
            "accepted_state_may_have_advanced": bool(
                details.get("acceptedStateMayHaveAdvanced")
            ),
            "monitored_state_status": str(
                details.get("monitoredStateStatus") or "unavailable/unknown"
            ),
            "guard_policy_fingerprint": "unknown",
            "guard_policy_identity_status": event_details[
                "guard_policy_identity_status"
            ],
            "geometry_status": "unavailable",
            "geometry_unavailable_reason": "The guard outcome or identity is unresolved.",
        }
        event_details["geometry_status"] = "unavailable"
        event_details["geometry_unavailable_reason"] = (
            "The guard outcome or identity is unresolved."
        )
        event: dict[str, object] = {
            "kind": "diagnostic",
            "monotonic_ns": event_ns,
            "diagnostic": diagnostic,
            "details": event_details,
        }
        if monitored_joints is not None:
            event["monitored_joints"] = monitored_joints
        if native:
            event["native_failure_evidence"] = {"native": dict(native)}
        self._manual_simulation_append_event(event)

    def _manual_simulation_base_matrix(
        self, parameter_node
    ) -> list[float]:
        matrix = self._logic._worldMatrixFromTransform(parameter_node.robotBaseTransform)
        return [
            float(matrix.GetElement(row, column))
            for row in range(4)
            for column in range(4)
        ]

    def _manual_simulation_recording_unavailable(
        self, result: RobotActionResult, reason: str
    ) -> RobotActionResult:
        return replace(
            result,
            details={
                **dict(result.details),
                "manualSimulationRecordStatus": "unavailable",
                "manualSimulationRecordUnavailableReason": (
                    reason or "A complete pre-commit recording identity was unavailable."
                ),
            },
        )

    def _manual_simulation_finish_acceptance(
        self,
        result: RobotActionResult,
        *,
        review_event: Mapping[str, object],
        acceptance_event: Mapping[str, object],
        unavailable_reason: str,
    ) -> RobotActionResult:
        if self._manual_simulation_identity is None:
            return self._manual_simulation_recording_unavailable(result, unavailable_reason)
        event_count = len(self._manual_simulation_events)
        try:
            self._manual_simulation_append_event(review_event)
            self._manual_simulation_append_event(acceptance_event)
            record = self._manual_simulation_record_dict()
        except (RuntimeError, ValueError, TypeError, OverflowError) as exc:
            del self._manual_simulation_events[event_count:]
            return self._manual_simulation_recording_unavailable(result, _bounded_text(exc))
        self._manual_simulation_completed_records.append(deepcopy(record))
        self._manual_simulation_identity = None
        self._manual_simulation_events = []
        self._manual_simulation_prepare_current_identity()
        return replace(
            result,
            details={
                **dict(result.details),
                "manualSimulationRecordStatus": "available",
                "manualSimulationRecord": record,
            },
        )

    def manualSimulationRecord(self) -> dict[str, object]:
        """Return the validated display-only current or most-recent record."""

        unavailable = self._manual_simulation_prepare_current_identity()
        if (
            self._manual_simulation_identity is not None
            and self._manual_simulation_events
        ):
            return self._manual_simulation_record_dict()
        if self._manual_simulation_completed_records:
            return deepcopy(self._manual_simulation_completed_records[-1])
        raise RuntimeError(
            "Manual simulation recording is unavailable: no event-bearing "
            "complete identity or completed record is available. " + unavailable
        )

    def manualSimulationCompletedRecords(self) -> tuple[dict[str, object], ...]:
        """Return frozen schema-built records for export after Base/Home acceptance."""

        return tuple(deepcopy(record) for record in self._manual_simulation_completed_records)

    def guardManualRobotJog(
        self, joint_positions_si: Mapping[str, float]
    ) -> RobotActionResult:
        """Apply one J1–J5 jog only after a correlated simulation guard reply."""

        details = {
            "guardAccepted": None,
            "identityStatus": "unknown",
            "manualJogStatus": "unknown",
            "rawGuardOutcome": "not_submitted",
            "requestedJointPositionsSi": None,
            "acceptedJointPositionsSi": None,
            "monitoredStateStatus": "unavailable/unknown",
            "nativeGuardEvidence": None,
            "limitMargins": None,
            "identityBefore": None,
            "identityAfter": None,
            "acceptedStateMayHaveAdvanced": False,
            "manualJogReconciliationRequired": self._manual_jog_reconciliation_required,
            "simulationOnly": True,
            "routeAuthority": "none",
        }
        recording = {"active": False, "outcomeRecorded": False}
        command_submitted = {"value": False}

        def outcome(code, message, success=False):
            if command_submitted["value"] and code.endswith(("_unknown", "_stale")):
                self._manual_jog_reconciliation_required = True
                identity = details.get("identityBefore")
                requested = details.get("requestedJointPositionsSi")
                if (
                    isinstance(identity, Mapping)
                    and isinstance(requested, Mapping)
                    and set(requested) == set(JOINT_NAMES)
                    and details.get("requestId")
                    and details.get("sessionId") == self._manual_jog_session_id
                ):
                    self._manual_jog_uncertainty = {
                        "identity": dict(identity),
                        "requested": {name: float(requested[name]) for name in JOINT_NAMES},
                        "requestId": str(details["requestId"]),
                        "sessionId": self._manual_jog_session_id,
                    }
                if code.endswith("_unknown"):
                    details["acceptedStateMayHaveAdvanced"] = True
            details["manualJogReconciliationRequired"] = (
                self._manual_jog_reconciliation_required
            )
            details["message"] = _bounded_text(message)
            if recording["active"] and not recording["outcomeRecorded"]:
                try:
                    self._record_manual_jog_outcome(code, message, details)
                except (RuntimeError, ValueError, TypeError, OverflowError) as exc:
                    details["manualSimulationRecordStatus"] = "unavailable"
                    details["manualSimulationRecordUnavailableReason"] = _bounded_text(exc)
                recording["outcomeRecorded"] = True
            return RobotActionResult(success, code, message, details=dict(details))

        if self._manual_jog_reconciliation_required:
            details["manualJogStatus"] = "unknown"
            details["manualJogUncertainty"] = deepcopy(
                self._manual_jog_uncertainty
            )
            return outcome(
                "manual_jog_reconciliation_required",
                "A prior submitted manual jog has unresolved state; use Reconcile State before jogging again.",
            )
        if self._manual_task_home_acceptance_in_progress:
            return outcome(
                "manual_task_home_review_busy",
                "A Task Home save or reconciliation is in progress.",
            )
        if self._manual_jog_in_progress:
            return outcome(
                "manual_jog_reentrant",
                "Another manual jog request is already waiting for its guard result.",
            )
        self._manual_jog_in_progress = True
        try:
            if not isinstance(joint_positions_si, Mapping) or set(joint_positions_si) != set(JOINT_NAMES):
                details["manualJogStatus"] = "rejected"
                return outcome(
                    "manual_jog_invalid_request",
                    "A manual jog must contain exactly the five canonical J1–J5 values.",
                )
            requested = {}
            for name in JOINT_NAMES:
                value = joint_positions_si[name]
                if isinstance(value, bool) or not isfinite(float(value)):
                    raise ValueError(f"{name} must be a finite SI joint value.")
                requested[name] = float(value)
            requested_vector = tuple(requested[name] for name in JOINT_NAMES)
            details["requestedJointPositionsSi"] = dict(requested)

            parameter_node = self._require_context()
            identity_before = self._manual_jog_current_identity(parameter_node)
            details.update(identityBefore=dict(identity_before), identityStatus="current")
            self._manual_simulation_begin(identity_before)
            recording["active"] = self._manual_simulation_append_event(
                {
                    "kind": "requested",
                    "monotonic_ns": monotonic_ns(),
                    "requested_joints": dict(requested),
                }
            )
            mechanical = default_task_joint_limits_from_urdf(
                self._logic.robotDescriptionPaths()[0]
            )
            margins = joint_limit_margin_evidence(
                requested,
                joint_names=JOINT_NAMES,
                joint_limit_fields=JOINT_LIMIT_FIELDS[: len(JOINT_NAMES)],
                display_units=JOINT_DISPLAY_UNITS[: len(JOINT_NAMES)],
                mechanical_limits=mechanical,
                task_limits=self._logic.getTaskJointLimits(parameter_node),
            )
            details["limitMargins"] = margins
            if margins is None or any(
                not row["mechanical_within_limits"]
                or not row["reviewed_task_within_limits"]
                for row in margins.values()
            ):
                details["manualJogStatus"] = "rejected"
                return outcome(
                    "manual_jog_joint_limit",
                    "J1–J5 must stay inside mechanical and reviewed task limits.",
                )

            displayed = self.currentRobotState().joint_positions_si
            accepted_reader = getattr(self._bridge, "last_accepted_joint_positions_si", None)
            accepted_before = accepted_reader() if callable(accepted_reader) else None
            if not isinstance(accepted_before, Mapping) or any(
                name not in accepted_before for name in JOINT_NAMES
            ):
                return outcome("manual_jog_state_unknown", "The accepted simulation state is unavailable.")
            accepted_before = tuple(float(accepted_before[name]) for name in JOINT_NAMES)
            details["currentAcceptedJointPositionsSiBefore"] = {
                name: accepted_before[index] for index, name in enumerate(JOINT_NAMES)
            }
            if not all(isfinite(value) for value in accepted_before) or any(
                abs(float(displayed[name]) - accepted_before[index]) > 1.0e-9
                for index, name in enumerate(JOINT_NAMES)
            ):
                return outcome(
                    "manual_jog_state_unknown",
                    "The displayed robot does not match the accepted simulation state.",
                )

            apply_guard = getattr(self._bridge, "apply_manual_joint_positions_si", None)
            if not callable(apply_guard):
                return outcome("manual_jog_guard_unavailable", "The correlated manual simulation guard is unavailable.")
            request_id = uuid4().hex
            session_id = self._manual_jog_session_id
            details.update(requestId=request_id, sessionId=session_id)
            command_submitted["value"] = True
            apply_message = "The manual guard returned an invalid response."
            try:
                response = apply_guard(requested, request_id, session_id)
            except Exception as exc:
                response = None
                apply_message = f"The manual guard request failed: {exc}"
            if (
                isinstance(response, (tuple, list))
                and len(response) == 3
                and (response[0] is None or isinstance(response[0], bool))
            ):
                apply_ok, apply_message, status = response
                apply_message = str(apply_message or "")
            else:
                apply_ok, status = None, None

            def vector(field):
                try:
                    values = tuple(float(value) for value in getattr(status, field, ()))
                except (TypeError, ValueError, OverflowError):
                    return None
                return values if len(values) == len(JOINT_NAMES) and all(isfinite(value) for value in values) else None

            native_requested = vector("requested_positions")
            native_accepted = vector("accepted_positions")
            objects = tuple(getattr(status, "world_objects", ()) or ())
            world_objects_valid = all(
                isinstance(item, Mapping)
                and isinstance(item.get("id"), str)
                and bool(item["id"])
                for item in objects
            )
            object_ids = (
                tuple(sorted(item["id"] for item in objects))
                if world_objects_valid
                else ()
            )
            acknowledgement = self._logic.collisionSceneAuditRecord(parameter_node).runtime_acknowledgement
            expected_ids = tuple(sorted(str(value) for value in acknowledgement.get("acknowledged_object_ids", ()) if str(value)))
            native_accepted_flag = getattr(status, "accepted", None)
            if not isinstance(native_accepted_flag, bool):
                native_accepted_flag = None
            command_valid = getattr(status, "command_valid", None)
            if not isinstance(command_valid, bool):
                command_valid = None
            native_request_id = getattr(status, "request_id", None)
            native_session_id = getattr(status, "session_id", None)
            native_policy_id = getattr(status, "policy_id", None)
            response_correlated = bool(
                status is not None
                and native_request_id == request_id
                and native_session_id == session_id
                and native_policy_id == MANUAL_JOINT_POLICY_ID
                and native_requested == requested_vector
            )
            details["nativeGuardEvidence"] = {
                "responseObserved": status is not None,
                "responseCorrelated": response_correlated,
                "requestId": str(native_request_id or ""),
                "sessionId": str(native_session_id or ""),
                "policyId": str(native_policy_id or ""),
                "commandValid": command_valid,
                "accepted": native_accepted_flag if isinstance(native_accepted_flag, bool) else None,
                "reason": _bounded_text(getattr(status, "reason", "") or apply_message),
                "requestedPositionsSi": native_requested,
                "acceptedPositionsSi": native_accepted,
                "checkedSamples": int(getattr(status, "checked_samples", 0) or 0),
                "minimumClearanceM": getattr(status, "minimum_clearance_m", None),
                "minimumSelfDistanceM": getattr(status, "minimum_self_distance_m", None),
                "minimumWorldDistanceM": getattr(status, "minimum_world_distance_m", None),
                "firstBody": str(getattr(status, "first_body", "") or ""),
                "secondBody": str(getattr(status, "second_body", "") or ""),
                "worldObjectCount": int(getattr(status, "world_object_count", 0) or 0),
                "worldObjectEvidencePresent": bool(getattr(status, "world_object_evidence_present", False)),
                "worldObjectIds": object_ids,
                "collisionScenePolicyFingerprint": str(getattr(status, "collision_scene_policy_fingerprint", "") or ""),
                "collisionScenePolicyIdentityStatus": "manual_policy_id_correlated"
                if native_policy_id == MANUAL_JOINT_POLICY_ID
                else "unknown",
                "bridgeReturnedAccepted": apply_ok,
            }
            details["rawGuardOutcome"] = (
                "accepted" if native_accepted_flag is True else
                "rejected" if native_accepted_flag is False else "unknown"
            )
            if native_accepted_flag is True or apply_ok is True:
                details["acceptedStateMayHaveAdvanced"] = True

            accepted_after = accepted_reader() if callable(accepted_reader) else None
            accepted_after = (
                tuple(float(accepted_after[name]) for name in JOINT_NAMES)
                if isinstance(accepted_after, Mapping) and all(name in accepted_after for name in JOINT_NAMES)
                else None
            )
            monitored_reader = getattr(self._bridge, "monitored_joint_positions_si", None)
            monitored = monitored_reader() if callable(monitored_reader) else None
            if isinstance(monitored, Mapping) and all(name in monitored for name in JOINT_NAMES):
                monitored_values = tuple(float(monitored[name]) for name in JOINT_NAMES)
                if all(isfinite(value) for value in monitored_values):
                    details["monitoredJointPositionsSi"] = dict(zip(JOINT_NAMES, monitored_values))
                    details["monitoredStateStatus"] = (
                        "matched" if native_accepted is not None and all(
                            abs(actual - expected) <= 1.0e-9
                            for actual, expected in zip(monitored_values, native_accepted)
                        ) else "not_converged"
                    )

            try:
                identity_after = self._manual_jog_current_identity(parameter_node)
                details["identityAfter"] = dict(identity_after)
                details["identityStatus"] = "current" if identity_after == identity_before else "stale"
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, AttributeError) as exc:
                details["identityAfter"] = {"status": _bounded_text(exc)}
                details["identityStatus"] = "stale"

            evidence = details["nativeGuardEvidence"]
            correlated = bool(
                evidence["responseCorrelated"]
                and command_valid is not None
                and isinstance(native_accepted_flag, bool)
                and (native_accepted_flag is False or command_valid is True)
                and apply_ok is native_accepted_flag
                and evidence["worldObjectEvidencePresent"]
                and evidence["worldObjectCount"] == self._planning_scene_object_count
                and world_objects_valid
                and object_ids == expected_ids
                and len(expected_ids) == self._planning_scene_object_count
                and len(set(expected_ids)) == len(expected_ids)
            )
            if not correlated:
                return outcome("manual_jog_guard_unknown", apply_message or "The raw guard response was missing, stale, or mismatched.")
            if native_accepted_flag is False:
                if native_accepted != accepted_before or accepted_after != accepted_before:
                    details["acceptedStateMayHaveAdvanced"] = accepted_after != accepted_before
                    return outcome(
                        "manual_jog_guard_unknown",
                        "The raw guard rejected the jog but the accepted-state echo changed.",
                    )
                details["guardAccepted"] = False
                details["manualJogStatus"] = "rejected"
                return outcome("manual_jog_rejected", evidence["reason"] or apply_message)
            if native_accepted != requested_vector or accepted_after != requested_vector:
                details.update(manualJogStatus="unknown", acceptedStateMayHaveAdvanced=True)
                return outcome("manual_jog_guard_unknown", "The acknowledged accepted-state echo did not exactly match J1–J5.")
            details["acceptedStateMayHaveAdvanced"] = True
            if details["identityStatus"] != "current":
                return outcome("manual_jog_identity_stale", "The accepted jog belongs to a task, branch, base, Home, limits, or scene identity that changed during the request.")

            self.invalidateMotionPlan()
            details.update(
                guardAccepted=True,
                manualJogStatus="accepted",
                acceptedJointPositionsSi=dict(zip(JOINT_NAMES, native_accepted)),
            )
            return outcome("manual_jog_accepted", "The simulation-only raw collision guard acknowledged the exact J1–J5 jog.", success=True)
        except Exception as exc:
            details["identityStatus"] = "unknown"
            details["manualJogStatus"] = "unknown"
            return outcome("manual_jog_unknown", str(exc))
        finally:
            self._manual_jog_in_progress = False

    def reconcileManualRobotJog(self) -> RobotActionResult:
        """Read back the native accepted state and clear only a verified jog latch."""
        details: dict[str, object] = {
            "manualJogReconciliationRequired": self._manual_jog_reconciliation_required,
            "manualJogStatus": "unknown",
            "identityStatus": "unknown",
            "monitoredStateStatus": "unavailable/unknown",
            "nativeGuardEvidence": None,
            "acceptedJointPositionsSi": None,
            "simulationOnly": True,
            "routeAuthority": "none",
        }

        def finish(code: str, message: str, success: bool = False):
            details["manualJogReconciliationRequired"] = (
                self._manual_jog_reconciliation_required
            )
            details["message"] = _bounded_text(message)
            return RobotActionResult(success, code, message, details=dict(details))

        if not self._manual_jog_reconciliation_required:
            return finish(
                "manual_jog_reconciliation_not_required",
                "There is no unresolved submitted manual jog to reconcile.",
            )
        if self._manual_jog_in_progress:
            return finish(
                "manual_jog_reentrant",
                "A manual-jog request is already waiting for its result.",
            )

        self._manual_jog_in_progress = True
        try:
            uncertainty = self._manual_jog_uncertainty
            if not isinstance(uncertainty, Mapping):
                return finish(
                    "manual_jog_reconciliation_unavailable",
                    "The submitted jog identity is unavailable; accepted state remains unresolved.",
                )
            expected_identity = uncertainty.get("identity")
            requested = uncertainty.get("requested")
            if (
                not isinstance(expected_identity, Mapping)
                or not isinstance(requested, Mapping)
                or set(requested) != set(JOINT_NAMES)
                or uncertainty.get("sessionId") != self._manual_jog_session_id
            ):
                return finish(
                    "manual_jog_reconciliation_unavailable",
                    "The submitted jog identity is incomplete or belongs to another façade session.",
                )
            echo = {}
            for name in JOINT_NAMES:
                value = requested[name]
                if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
                    return finish(
                        "manual_jog_reconciliation_unavailable",
                        "The submitted J1–J5 echo is not a finite numeric vector.",
                    )
                echo[name] = float(value)
            echo_vector = tuple(echo[name] for name in JOINT_NAMES)
            parameter_node = self._require_context()
            identity_before = self._manual_jog_current_identity(
                parameter_node, for_task_home_review=uncertainty.get("forTaskHomeReview") is True
            )
            details["identityBefore"] = dict(identity_before)
            if identity_before != dict(expected_identity):
                details["identityStatus"] = "stale"
                return finish(
                    "manual_jog_reconciliation_stale",
                    "Task, branch, base, Home, limits, profile, or scene identity changed since the uncertain jog.",
                )

            def audit_object_ids(audit):
                acknowledgement = getattr(audit, "runtime_acknowledgement", None)
                if not isinstance(acknowledgement, Mapping):
                    return None
                raw_ids = acknowledgement.get("acknowledged_object_ids")
                if not isinstance(raw_ids, (tuple, list)) or any(
                    not isinstance(value, str) or not value for value in raw_ids
                ):
                    return None
                ids = tuple(sorted(raw_ids))
                return ids if len(set(ids)) == len(ids) else None

            audit_before = self._logic.collisionSceneAuditRecord(parameter_node)
            expected_ids_before = audit_object_ids(audit_before)
            if (
                expected_ids_before is None
                or not expected_ids_before
                or len(expected_ids_before) != self._planning_scene_object_count
            ):
                return finish(
                    "manual_jog_reconciliation_scene_unknown",
                    "The acknowledged collision-scene object identity is unavailable.",
                )

            query_id = uuid4().hex
            session_id = self._manual_jog_session_id
            details.update(queryRequestId=query_id, sessionId=session_id)
            query = getattr(self._bridge, "query_manual_joint_state_si", None)
            if not callable(query):
                return finish(
                    "manual_jog_reconciliation_unavailable",
                    "The read-only native accepted-state query is unavailable.",
                )
            try:
                response = query(echo, query_id, session_id)
            except Exception as exc:
                response = None
                query_message = f"Native state query failed: {exc}"
            else:
                query_message = "The native state query returned an invalid response."
            if (
                isinstance(response, (tuple, list))
                and len(response) == 2
            ):
                status, query_message = response
                query_message = str(query_message or "")
            else:
                status = None

            def vector(values):
                if not isinstance(values, (tuple, list)) or len(values) != len(JOINT_NAMES):
                    return None
                result = []
                for value in values:
                    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
                        return None
                    result.append(float(value))
                return tuple(result)

            native_echo = vector(getattr(status, "requested_positions", None))
            native_accepted = vector(getattr(status, "accepted_positions", None))
            operation = getattr(status, "operation", None)
            query_only = getattr(status, "query_only", None)
            command_valid = getattr(status, "command_valid", None)
            static_validity = getattr(status, "accepted", None)
            native_ids = tuple(
                sorted(
                    item["id"]
                    for item in (getattr(status, "world_objects", ()) or ())
                    if isinstance(item, Mapping)
                    and isinstance(item.get("id"), str)
                    and item["id"]
                )
            )
            objects = tuple(getattr(status, "world_objects", ()) or ())
            world_evidence_present = getattr(
                status, "world_object_evidence_present", False
            ) is True
            world_count = getattr(status, "world_object_count", None)
            world_objects_valid = (
                isinstance(world_count, int)
                and not isinstance(world_count, bool)
                and len(objects) == world_count
                and all(
                    isinstance(item, Mapping)
                    and isinstance(item.get("id"), str)
                    and bool(item["id"])
                    for item in objects
                )
            )
            response_correlated = bool(
                status is not None
                and getattr(status, "request_id", None) == query_id
                and getattr(status, "session_id", None) == session_id
                and getattr(status, "policy_id", None) == MANUAL_JOINT_POLICY_ID
                and operation == "state_query"
                and query_only is True
                and native_echo == echo_vector
                and command_valid is True
                and isinstance(static_validity, bool)
                and native_accepted is not None
            )
            details["nativeGuardEvidence"] = {
                "responseObserved": status is not None,
                "responseCorrelated": response_correlated,
                "operation": operation,
                "queryOnly": query_only,
                "requestId": str(getattr(status, "request_id", "") or ""),
                "sessionId": str(getattr(status, "session_id", "") or ""),
                "policyId": str(getattr(status, "policy_id", "") or ""),
                "commandValid": command_valid if isinstance(command_valid, bool) else None,
                "staticStateValid": static_validity if isinstance(static_validity, bool) else None,
                "reason": _bounded_text(getattr(status, "reason", "") or query_message),
                "requestedPositionsSi": native_echo,
                "acceptedPositionsSi": native_accepted,
                "checkedSamples": int(getattr(status, "checked_samples", 0) or 0),
                "minimumClearanceM": getattr(status, "minimum_clearance_m", None),
                "minimumSelfDistanceM": getattr(status, "minimum_self_distance_m", None),
                "minimumWorldDistanceM": getattr(status, "minimum_world_distance_m", None),
                "firstBody": str(getattr(status, "first_body", "") or ""),
                "secondBody": str(getattr(status, "second_body", "") or ""),
                "worldObjectCount": world_count,
                "worldObjectEvidencePresent": world_evidence_present,
                "worldObjectIds": native_ids,
                "collisionScenePolicyFingerprint": str(
                    getattr(status, "collision_scene_policy_fingerprint", "") or ""
                ),
            }
            if not response_correlated:
                return finish(
                    "manual_jog_reconciliation_unknown",
                    query_message or "The read-only native reply was missing, stale, or mismatched.",
                )
            if (
                not world_evidence_present
                or not world_objects_valid
                or world_count != self._planning_scene_object_count
                or len(native_ids) != world_count
                or len(set(native_ids)) != len(native_ids)
                or native_ids != expected_ids_before
            ):
                return finish(
                    "manual_jog_reconciliation_scene_stale",
                    "Native and acknowledged collision-scene object IDs do not match.",
                )

            accepted = dict(zip(JOINT_NAMES, native_accepted))
            details["acceptedJointPositionsSi"] = dict(accepted)
            wait_for_state = getattr(
                self._bridge, "wait_for_monitored_joint_positions_si", None
            )
            if not callable(wait_for_state):
                return finish(
                    "manual_jog_reconciliation_monitor_unavailable",
                    "The fresh ROS/MoveIt monitored-state reader is unavailable.",
                )
            try:
                monitored_result = wait_for_state(accepted)
            except Exception as exc:
                monitored_result = None
                monitor_message = f"Monitored-state read failed: {exc}"
            else:
                monitor_message = "The monitored-state reader returned an invalid response."
            if isinstance(monitored_result, (tuple, list)) and len(monitored_result) == 4:
                monitored_ok, monitor_message, monitored, maximum_error = monitored_result
                monitor_message = str(monitor_message or "")
            else:
                monitored_ok, monitored, maximum_error = False, {}, float("inf")
            monitored_vector = tuple(
                float(monitored[name]) for name in JOINT_NAMES
            ) if isinstance(monitored, Mapping) and set(monitored) == set(JOINT_NAMES) and all(
                not isinstance(monitored[name], bool)
                and isinstance(monitored[name], Real)
                and isfinite(float(monitored[name]))
                for name in JOINT_NAMES
            ) else None
            details.update(
                monitoredStateStatus="matched" if monitored_ok is True else "not_converged",
                monitoredJointPositionsSi=(
                    dict(zip(JOINT_NAMES, monitored_vector))
                    if monitored_vector is not None
                    else None
                ),
                monitoredMaximumError=maximum_error,
            )
            if monitored_ok is not True or monitored_vector is None:
                return finish(
                    "manual_jog_reconciliation_monitor_mismatch",
                    monitor_message or "ROS/MoveIt monitored state does not match the native accepted vector.",
                )

            try:
                identity_after = self._manual_jog_current_identity(
                    parameter_node, for_task_home_review=uncertainty.get("forTaskHomeReview") is True
                )
                audit_after = self._logic.collisionSceneAuditRecord(parameter_node)
                expected_ids_after = audit_object_ids(audit_after)
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, AttributeError) as exc:
                details["identityAfter"] = {"status": _bounded_text(exc)}
                details["identityStatus"] = "stale"
                return finish(
                    "manual_jog_reconciliation_stale",
                    "Task, branch, base, Home, limits, profile, or scene identity became unavailable after the state query.",
                )
            details["identityAfter"] = dict(identity_after)
            details["worldObjectIdsBefore"] = expected_ids_before
            details["worldObjectIdsAfter"] = expected_ids_after
            details["identityStatus"] = (
                "current"
                if identity_after == identity_before == dict(expected_identity)
                and expected_ids_after == expected_ids_before
                else "stale"
            )
            if details["identityStatus"] != "current":
                return finish(
                    "manual_jog_reconciliation_stale",
                    "Task, branch, base, Home, limits, or scene identity changed during reconciliation.",
                )

            commit = getattr(
                self._bridge, "accept_manual_joint_state_reconciliation", None
            )
            if not callable(commit):
                return finish(
                    "manual_jog_reconciliation_unavailable",
                    "The bridge cannot commit a verified reconciliation.",
                )
            try:
                committed = commit(status, echo, query_id, session_id)
            except Exception as exc:
                committed = (False, f"Could not commit reconciled state: {exc}")
            if not (
                isinstance(committed, (tuple, list))
                and len(committed) == 2
                and committed[0] is True
            ):
                commit_message = (
                    str(committed[1])
                    if isinstance(committed, (tuple, list)) and len(committed) == 2
                    else "Could not commit reconciled native state."
                )
                return finish("manual_jog_reconciliation_unknown", commit_message)

            self.invalidateMotionPlan()
            self._manual_jog_reconciliation_required = False
            self._manual_jog_uncertainty = None
            details.update(
                manualJogReconciliationRequired=False,
                manualJogStatus="reconciled",
                collisionStatus="valid" if static_validity else "invalid",
                acceptedJointPositionsSi=dict(accepted),
            )
            return finish(
                "manual_jog_reconciled",
                "Native accepted J1–J5 state was reconciled with ROS/MoveIt monitored state. "
                + ("The static collision check passed." if static_validity else "The known accepted state currently fails static collision validity."),
                success=True,
            )
        except Exception as exc:
            details["identityStatus"] = "unknown"
            return finish("manual_jog_reconciliation_unknown", str(exc))
        finally:
            self._manual_jog_in_progress = False

    def requestCurrentJointState(self) -> RobotActionResult:
        """Validate/publish values already written by MRML GUI binding."""
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Joint-state requests are blocked because a guarded preview stopped before endpoint verification.",
            )
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
                "Accepted the current five-joint positioning state.",
                payload=positions_si,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "joint_update_failed", str(exc))

    def setBasePose(self, matrix_world_ras_mm) -> RobotActionResult:
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Base pose changes are blocked because a guarded preview stopped before endpoint verification.",
            )
        try:
            parameter_node = self._require_context()
            record_unavailable = self._manual_simulation_prepare_current_identity()
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
            result = RobotActionResult(
                True,
                "base_pose_updated",
                "Updated the unreviewed Manual Simulation Base in world RAS millimetres.",
            )
            try:
                candidate_matrix = self._manual_simulation_base_matrix(parameter_node)
                if not self._manual_simulation_append_event(
                    {
                        "kind": "review_base",
                        "monotonic_ns": monotonic_ns(),
                        "details": {
                            "candidate_matrix_world_ras_mm": candidate_matrix,
                            "guard_policy_fingerprint": "unknown",
                        },
                    }
                ):
                    return self._manual_simulation_recording_unavailable(
                        result, record_unavailable
                    )
            except (RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
                return self._manual_simulation_recording_unavailable(
                    result, _bounded_text(exc)
                )
            return replace(
                result,
                details={"manualSimulationRecordStatus": "active"},
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_pose_failed", str(exc))

    @staticmethod
    def _manual_base_review_matrix(value: object) -> list[float]:
        """Return a finite proper rigid transform as sixteen row-major values."""

        if isinstance(value, (str, bytes, Mapping)):
            raise ValueError("Base review pose must be a finite rigid 4×4 matrix.")
        get_element = getattr(value, "GetElement", None)
        if callable(get_element):
            raw = [get_element(row, column) for row in range(4) for column in range(4)]
        else:
            try:
                outer = tuple(value)  # type: ignore[arg-type]
                if len(outer) == 4 and all(
                    not isinstance(row, (str, bytes, Mapping))
                    and len(tuple(row)) == 4
                    for row in outer
                ):
                    raw = [item for row in outer for item in row]
                else:
                    raw = list(outer)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Base review pose must be a finite rigid 4×4 matrix."
                ) from exc
        if len(raw) != 16 or any(isinstance(item, bool) for item in raw):
            raise ValueError("Base review pose must contain sixteen finite matrix values.")
        try:
            matrix = [float(item) for item in raw]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Base review pose must contain sixteen finite matrix values.") from exc
        if not all(isfinite(item) for item in matrix):
            raise ValueError("Base review pose must contain sixteen finite matrix values.")
        tolerance = MANUAL_BASE_REVIEW_MATRIX_TOLERANCE
        if any(abs(matrix[12 + index] - expected) > tolerance for index, expected in enumerate((0.0, 0.0, 0.0, 1.0))):
            raise ValueError("Base review pose must use a rigid homogeneous 4×4 matrix.")
        rotation = tuple(
            tuple(matrix[row * 4 + column] for column in range(3))
            for row in range(3)
        )
        for first in range(3):
            for second in range(3):
                dot = sum(rotation[row][first] * rotation[row][second] for row in range(3))
                if abs(dot - (1.0 if first == second else 0.0)) > tolerance:
                    raise ValueError("Base review pose rotation must be orthonormal with no scale.")
        determinant = (
            rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
            - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
            + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
        )
        if abs(determinant - 1.0) > tolerance:
            raise ValueError("Base review pose rotation must be right-handed with no reflection.")
        return matrix

    @staticmethod
    def _manual_base_review_node_token(node) -> str:
        if node is None:
            return "none"
        getter = getattr(node, "GetID", None)
        try:
            node_id = str(getter() or "") if callable(getter) else ""
        except RuntimeError:
            node_id = ""
        if not node_id:
            node_id = f"python-object:{id(node)}"
        scene_getter = getattr(node, "GetScene", None)
        try:
            scene = scene_getter() if callable(scene_getter) else None
        except RuntimeError:
            scene = None
        if scene is None:
            return node_id
        address_getter = getattr(scene, "GetAddressAsString", None)
        try:
            scene_id = str(address_getter("") or "") if callable(address_getter) else ""
        except RuntimeError:
            scene_id = ""
        return f"{scene_id or f'python-scene:{id(scene)}'}:{node_id}"

    def _manual_base_review_identity(self, parameter_node, base) -> dict[str, object]:
        attribute_names = (
            getattr(self._logic, "ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE", "DENTOBOT.RobotBasePlacementAuthority"),
            "DENTOBOT.CaseFoundationFingerprint",
            "DENTOBOT.RobotProfileFingerprint",
        )
        get_attribute = getattr(base, "GetAttribute", None)
        attributes = {}
        for name in attribute_names:
            try:
                attributes[name] = get_attribute(name) if callable(get_attribute) else None
            except RuntimeError as exc:
                raise RuntimeError("The reviewed robot Base is no longer available.") from exc
        get_parent = getattr(base, "GetTransformNodeID", None)
        parent_id = str(get_parent() or "") if callable(get_parent) else ""
        node_revisions = {}
        for name in ("inputVolume", "teethSegmentation"):
            node = getattr(parameter_node, name, None)
            get_mtime = getattr(node, "GetMTime", None)
            try:
                node_revisions[name] = int(get_mtime()) if callable(get_mtime) else None
            except (RuntimeError, TypeError, ValueError) as exc:
                if node is not None:
                    raise RuntimeError(f"The current case {name} is no longer available.") from exc
                node_revisions[name] = None
        profile = getattr(self._logic, "robotProfileFingerprint", None)
        return {
            "parameterNode": self._manual_base_review_node_token(parameter_node),
            "baseNode": self._manual_base_review_node_token(base),
            "inputVolume": self._manual_base_review_node_token(
                getattr(parameter_node, "inputVolume", None)
            ),
            "teethSegmentation": self._manual_base_review_node_token(
                getattr(parameter_node, "teethSegmentation", None)
            ),
            "baseParent": parent_id,
            "baseAttributes": attributes,
            "placementRevision": getattr(parameter_node, "step6BasePlacementRevision", None),
            "caseNodeRevisions": node_revisions,
            "robotProfileFingerprint": str(profile() or "") if callable(profile) else "",
        }

    def _manual_base_review_context(self):
        parameter_node = self._require_context()
        base = parameter_node.robotBaseTransform
        if base is None:
            raise RuntimeError("Load the Step 6 robot Base before reviewing a candidate pose.")
        is_base = getattr(self._logic, "isRobotBaseTransformNode", None)
        if callable(is_base) and not is_base(base):
            raise ValueError("The selected transform is not the Step 6 robot Base.")
        identity = self._manual_base_review_identity(parameter_node, base)
        if identity["baseParent"]:
            raise ValueError("Detach the robot Base from parent transforms before manual review.")
        current_matrix = self._manual_base_review_matrix(
            self._manual_simulation_base_matrix(parameter_node)
        )
        return parameter_node, base, identity, current_matrix

    def _manual_base_review_details(
        self, *, candidate=None, accepted=None, staged=False, identity_status="current"
    ) -> dict[str, object]:
        review = self._manual_base_review
        details = {
            "candidateMatrixWorldRasMm": list(candidate) if candidate is not None else None,
            "acceptedMatrixWorldRasMm": list(accepted) if accepted is not None else None,
            "acceptedBaselineMatrixWorldRasMm": (
                list(review["acceptedBaselineMatrixWorldRasMm"])
                if review is not None
                else list(accepted) if accepted is not None else None
            ),
            "staged": bool(staged),
            "identityStatus": str(identity_status),
        }
        if self._manual_base_review_failure is not None:
            details["failureEvidence"] = deepcopy(self._manual_base_review_failure)
        if self._manual_base_acceptance_uncertain:
            details["acceptanceStatus"] = "unknown"
            details["acceptanceUncertainty"] = self._manual_base_acceptance_uncertain
        return details

    def _manual_base_review_is_current(self, parameter_node, base, current_matrix):
        review = self._manual_base_review
        if review is None:
            return False, "no_candidate"
        try:
            identity = self._manual_base_review_identity(parameter_node, base)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            return False, _bounded_text(exc)
        if identity != review["identity"]:
            return False, "case_or_base_identity_changed"
        if bool(parameter_node.robotBaseMountLocked):
            return False, "base_locked"
        baseline = review["acceptedBaselineMatrixWorldRasMm"]
        if any(abs(float(a) - float(b)) > 1.0e-9 for a, b in zip(current_matrix, baseline)):
            return False, "accepted_base_pose_changed"
        return True, "current"

    def _manual_base_record_acceptance_failure(
        self, code: str, message: str, stage: str, rollback_status: str
    ) -> None:
        if self._manual_simulation_prepare_current_identity():
            return
        if self._manual_simulation_identity is None:
            return
        self._manual_simulation_append_event(
            {
                "kind": "diagnostic",
                "monotonic_ns": monotonic_ns(),
                "diagnostic": {
                    "code": str(code),
                    "message": _bounded_text(message),
                    "identity_status": "current",
                    "guard_accepted": None,
                    "raw_guard_outcome": "unknown",
                    "accepted_state_may_have_advanced": rollback_status == "unknown",
                    "monitored_state_status": "not_applicable",
                },
                "details": {
                    "source": "manual_base_acceptance",
                    "stage": str(stage),
                    "rollback_status": str(rollback_status),
                    "route_authority": "none",
                },
            }
        )

    def manualBaseReview(self) -> RobotActionResult:
        """Read the detached Base draft and current accepted pose without mutation."""

        try:
            parameter_node, _base, identity, accepted = self._manual_base_review_context()
        except (AttributeError, RuntimeError, TypeError, ValueError, OSError) as exc:
            return RobotActionResult(
                False,
                "manual_base_review_unavailable",
                _bounded_text(exc),
                details=self._manual_base_review_details(
                    candidate=(self._manual_base_review or {}).get("candidateMatrixWorldRasMm"),
                    staged=self._manual_base_review is not None,
                    identity_status="unavailable",
                ),
            )
        if self._manual_base_review is None:
            return RobotActionResult(
                True,
                "manual_base_review_empty",
                "No detached Manual Simulation Base candidate is staged.",
                details=self._manual_base_review_details(accepted=accepted),
            )
        current, status = self._manual_base_review_is_current(
            parameter_node,
            self._require_context().robotBaseTransform,
            accepted,
        )
        result = RobotActionResult(
            current,
            "manual_base_review_current" if current else "manual_base_review_stale",
            "Detached Base candidate is current." if current else "Detached Base candidate is stale: " + status,
            details=self._manual_base_review_details(
                candidate=self._manual_base_review["candidateMatrixWorldRasMm"],
                accepted=accepted,
                staged=True,
                identity_status="current" if current else status,
            ),
        )
        return result

    def stageManualBaseReview(self, matrix_world_ras_mm) -> RobotActionResult:
        """Stage a finite rigid Base pose without changing MRML or scene state."""

        if self._manual_base_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_base_acceptance_unknown",
                "Keep the staged Base candidate until uncertain native state is reconciled.",
                details=self._manual_base_review_details(
                    candidate=(self._manual_base_review or {}).get(
                        "candidateMatrixWorldRasMm"
                    ),
                    staged=self._manual_base_review is not None,
                    identity_status="unknown",
                ),
            )
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Base review is blocked because a guarded preview stopped before endpoint verification.",
            )
        if self._guarded_preview_active or self.previewActive:
            return RobotActionResult(False, "preview_active", "Stop the active preview before reviewing a Base candidate.")
        try:
            candidate = self._manual_base_review_matrix(matrix_world_ras_mm)
            parameter_node, _base, identity, accepted = self._manual_base_review_context()
            if self._scene_kind(parameter_node) != "case":
                return RobotActionResult(False, "scene_required", "Open a case before staging a Manual Simulation Base candidate.")
            if self._manual_base_review is not None:
                current, stale_reason = self._manual_base_review_is_current(
                    parameter_node, _base, accepted
                )
                if not current:
                    message = "The existing Base draft is stale; cancel it before staging a candidate for the current case. Reason: " + stale_reason
                    return RobotActionResult(
                        False,
                        "manual_base_review_stale",
                        message,
                        details={
                            **self._manual_base_review_details(
                                candidate=self._manual_base_review[
                                    "candidateMatrixWorldRasMm"
                                ],
                                accepted=accepted,
                                staged=True,
                                identity_status=stale_reason,
                            ),
                            "restageRejection": {
                                "code": "manual_base_review_stale",
                                "message": message,
                            },
                        },
                    )
            if bool(parameter_node.robotBaseMountLocked):
                return RobotActionResult(False, "base_locked", "Unlock the accepted Base before staging a review candidate.")
            self._manual_base_review = {
                "identity": identity,
                "candidateMatrixWorldRasMm": candidate,
                "acceptedBaselineMatrixWorldRasMm": accepted,
            }
            return RobotActionResult(
                True,
                "manual_base_review_staged",
                "Staged a detached Manual Simulation Base candidate; the accepted Base is unchanged.",
                details=self._manual_base_review_details(
                    candidate=candidate,
                    accepted=accepted,
                    staged=True,
                ),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "manual_base_review_rejected", _bounded_text(exc))

    def cancelManualBaseReview(self) -> RobotActionResult:
        """Clear a detached candidate only when native acceptance is certain."""

        if self._manual_base_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_base_acceptance_unknown",
                "Keep the staged Base candidate until uncertain native state is reconciled.",
                details=self._manual_base_review_details(
                    candidate=(self._manual_base_review or {}).get(
                        "candidateMatrixWorldRasMm"
                    ),
                    staged=self._manual_base_review is not None,
                    identity_status="unknown",
                ),
            )
        self._manual_base_review = None
        return RobotActionResult(
            True,
            "manual_base_review_cancelled",
            "Cleared the detached Manual Simulation Base candidate.",
            details=self._manual_base_review_details(),
        )

    def _manual_base_acceptance_preflight(self, parameter_node, base) -> Optional[RobotActionResult]:
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Base acceptance is blocked because a guarded preview stopped before endpoint verification.",
            )
        if self._guarded_preview_active or self.previewActive:
            return RobotActionResult(False, "preview_active", "Stop the active preview before accepting a Base candidate.")
        if self._motion_plan is not None or self._completed_phase or self._phase_sequence:
            return RobotActionResult(
                False,
                "phase_state_requires_reset",
                "Clear the existing Step 6 phase session before accepting a changed Base candidate.",
            )
        if bool(parameter_node.robotBaseMountLocked):
            return RobotActionResult(False, "base_locked", "The accepted Base is already locked.")
        if self._scene_kind(parameter_node) != "case":
            return RobotActionResult(False, "scene_required", "Open a case and establish its Case Foundation before accepting the Base.")
        issue = self._scene_placement_issue(parameter_node)
        if issue:
            return RobotActionResult(False, "case_jaw_opening_required", issue)
        if not (
            self._logic.robotModelNodes()
            or self._logic.isRos2MotionControlActive(base)
        ):
            return RobotActionResult(False, "robot_required", "Load the ROS robot or local fallback before accepting the Base.")
        require_foundation = getattr(self._logic, "requireCaseFoundationPose", None)
        if callable(require_foundation):
            try:
                require_foundation(parameter_node)
            except (RuntimeError, ValueError, TypeError, OSError) as exc:
                return RobotActionResult(False, "case_foundation_required", _bounded_text(exc))
        is_base = getattr(self._logic, "isRobotBaseTransformNode", None)
        if callable(is_base) and not is_base(base):
            return RobotActionResult(False, "robot_base_required", "The selected transform is not the Step 6 robot Base.")
        authority = str(
            base.GetAttribute(
                getattr(self._logic, "ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE", "DENTOBOT.RobotBasePlacementAuthority")
            )
            or ""
        )
        circular_authority = getattr(self._logic, "ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY", "QuarantinedCircularMountPlane")
        if authority == circular_authority:
            return RobotActionResult(False, "base_authority_rejected", "The quarantined circular-snap Base cannot be accepted.")
        return None

    def _manual_base_acceptance_snapshot(self, parameter_node, base) -> dict[str, object]:
        matrix = self._logic._worldMatrixFromTransform(base)
        matrix_values = self._manual_base_review_matrix(
            [matrix.GetElement(row, column) for row in range(4) for column in range(4)]
        )
        attribute_names = (
            getattr(self._logic, "ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE", "DENTOBOT.RobotBasePlacementAuthority"),
            "DENTOBOT.PlacementWarning",
            "DENTOBOT.CaseFoundationFingerprint",
            "DENTOBOT.RobotProfileFingerprint",
        )
        get_attribute = getattr(base, "GetAttribute", None)
        attributes = {
            name: (get_attribute(name) if callable(get_attribute) else None)
            for name in attribute_names
        }
        parameters = {
            name: getattr(parameter_node, name)
            for name in (
                "robotBaseMountLocked",
                "step6BasePlacementStatus",
                "step6BasePlacementSource",
                "step6BasePlacementRevision",
            )
            if hasattr(parameter_node, name)
        }
        return {
            "matrixObject": matrix,
            "matrixValues": matrix_values,
            "attributes": attributes,
            "parameters": parameters,
            "parentId": str(getattr(base, "GetTransformNodeID", lambda: "")() or ""),
            "planningSceneSynchronized": self._planning_scene_synchronized,
            "planningSceneObjectCount": self._planning_scene_object_count,
        }

    def _manual_base_restore_after_failed_acceptance(
        self, parameter_node, base, snapshot, *, lock_attempted: bool
    ) -> tuple[bool, str]:
        failures = []
        try:
            base.SetAndObserveTransformNodeID(snapshot["parentId"] or None)
            base.SetMatrixTransformToParent(snapshot["matrixObject"])
            for name, value in snapshot["attributes"].items():
                base.SetAttribute(name, value)
            for name, value in snapshot["parameters"].items():
                setattr(parameter_node, name, value)
            if lock_attempted:
                restore_interaction = getattr(
                    self._logic, "_applyRobotBaseMountInteractionState", None
                )
                if callable(restore_interaction):
                    restore_interaction(parameter_node, bool(snapshot["parameters"].get("robotBaseMountLocked", False)))
                self._planning_scene_synchronized = False
                self._planning_scene_object_count = 0
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                self._runtime_validated_workspace_key = ""
            else:
                self._planning_scene_synchronized = bool(snapshot["planningSceneSynchronized"])
                self._planning_scene_object_count = int(snapshot["planningSceneObjectCount"])
        except Exception as exc:
            failures.append(_bounded_text(exc))
        try:
            restored = self._manual_base_review_matrix(
                self._manual_simulation_base_matrix(parameter_node)
            )
            if any(abs(float(a) - float(b)) > 1.0e-9 for a, b in zip(restored, snapshot["matrixValues"])):
                failures.append("The Base transform did not restore to its accepted matrix.")
            if bool(parameter_node.robotBaseMountLocked) != bool(snapshot["parameters"].get("robotBaseMountLocked", False)):
                failures.append("The Base lock state did not restore.")
            get_attribute = getattr(base, "GetAttribute", None)
            if callable(get_attribute) and any(
                get_attribute(name) != value for name, value in snapshot["attributes"].items()
            ):
                failures.append("Base placement attributes did not restore exactly.")
        except Exception as exc:
            failures.append(_bounded_text(exc))
        # lockBase may have partly synchronized MoveIt or invalidated task evidence;
        # those effects cannot be proven reversible from this façade.
        proven = not failures and not lock_attempted
        return proven, "; ".join(failures) or (
            "Base data restored; native scene/task side effects remain uncertain."
            if lock_attempted
            else "Base data restored."
        )

    def acceptManualBaseReview(self) -> RobotActionResult:
        """Commit the staged Base only through setBasePose and lockBase owners."""

        if self._manual_base_acceptance_in_progress:
            return RobotActionResult(False, "manual_base_acceptance_reentrant", "Another Base acceptance is already in progress.")
        if self._manual_base_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_base_acceptance_unknown",
                "A prior Base acceptance may have changed native scene state; further acceptance is blocked.",
                details=self._manual_base_review_details(
                    candidate=(self._manual_base_review or {}).get("candidateMatrixWorldRasMm"),
                    staged=self._manual_base_review is not None,
                    identity_status="unknown",
                ),
            )
        if self._manual_base_review is None:
            return RobotActionResult(False, "manual_base_candidate_required", "Stage a detached Base candidate before accepting it.")
        try:
            parameter_node, base, identity, accepted = self._manual_base_review_context()
        except (AttributeError, RuntimeError, TypeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "manual_base_review_stale", _bounded_text(exc))
        current, stale_reason = self._manual_base_review_is_current(
            parameter_node, base, accepted
        )
        if not current:
            result = RobotActionResult(
                False,
                "manual_base_review_stale",
                "Detached Base candidate cannot be accepted: " + stale_reason,
                details=self._manual_base_review_details(
                    candidate=self._manual_base_review["candidateMatrixWorldRasMm"],
                    accepted=accepted,
                    staged=True,
                    identity_status=stale_reason,
                ),
            )
            self._manual_base_review_failure = {
                "code": result.code,
                "message": result.message,
                "identityStatus": stale_reason,
            }
            return replace(
                result,
                details=self._manual_base_review_details(
                    candidate=self._manual_base_review["candidateMatrixWorldRasMm"],
                    accepted=accepted,
                    staged=True,
                    identity_status=stale_reason,
                ),
            )
        preflight = self._manual_base_acceptance_preflight(parameter_node, base)
        if preflight is not None:
            self._manual_base_review_failure = {
                "code": preflight.code,
                "message": preflight.message,
                "stage": "preflight",
            }
            self._manual_base_record_acceptance_failure(
                preflight.code, preflight.message, "preflight", "not_attempted"
            )
            return replace(
                preflight,
                details={
                    **dict(preflight.details),
                    **self._manual_base_review_details(
                        candidate=self._manual_base_review["candidateMatrixWorldRasMm"],
                        accepted=accepted,
                        staged=True,
                        identity_status="current",
                    ),
                },
            )
        snapshot = self._manual_base_acceptance_snapshot(parameter_node, base)
        candidate = list(self._manual_base_review["candidateMatrixWorldRasMm"])
        self._manual_base_acceptance_in_progress = True
        lock_attempted = False
        try:
            to_vtk = getattr(self._logic, "_vtkFromNumpyMatrix", None)
            candidate_matrix = (
                to_vtk([candidate[row * 4 : row * 4 + 4] for row in range(4)])
                if callable(to_vtk)
                else [candidate[row * 4 : row * 4 + 4] for row in range(4)]
            )
            pose_result = self.setBasePose(candidate_matrix)
            if not pose_result.success:
                failure = pose_result
            else:
                lock_attempted = True
                failure = self.lockBase()
            if not failure.success:
                restored, rollback_message = self._manual_base_restore_after_failed_acceptance(
                    parameter_node, base, snapshot, lock_attempted=lock_attempted
                )
                self._manual_base_acceptance_uncertain = (
                    "Base acceptance reached lock/scene synchronization, then failed. "
                    + rollback_message
                    if not restored
                    else ""
                )
                self._manual_base_review_failure = {
                    "code": failure.code,
                    "message": failure.message,
                    "stage": "lock" if lock_attempted else "pose",
                    "rollbackStatus": "proven" if restored else "unknown",
                    "rollbackEvidence": rollback_message,
                }
                code = "manual_base_acceptance_failed" if restored else "manual_base_acceptance_unknown"
                self._manual_base_record_acceptance_failure(
                    failure.code,
                    failure.message,
                    "lock" if lock_attempted else "pose",
                    "proven" if restored else "unknown",
                )
                return RobotActionResult(
                    False,
                    code,
                    failure.message + " Base rollback: " + rollback_message,
                    details=self._manual_base_review_details(
                        candidate=candidate,
                        accepted=snapshot["matrixValues"],
                        staged=True,
                        identity_status="current",
                    ),
                )
            accepted_matrix = self._manual_base_review_matrix(
                self._manual_simulation_base_matrix(parameter_node)
            )
            reviewed_authority = getattr(self._logic, "ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY", "ManualSimulationBaseReviewed")
            authority_name = getattr(self._logic, "ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE", "DENTOBOT.RobotBasePlacementAuthority")
            current_base = parameter_node.robotBaseTransform
            observed_authority = str(base.GetAttribute(authority_name) or "")
            max_matrix_delta = max(
                (abs(a - b) for a, b in zip(accepted_matrix, candidate)), default=0.0
            )
            verification = {
                "baseLocked": bool(parameter_node.robotBaseMountLocked),
                "observedAuthority": observed_authority,
                "expectedAuthority": str(reviewed_authority),
                "currentBaseAuthority": str(
                    current_base.GetAttribute(authority_name) or ""
                ) if current_base is not None else "",
                "baseNodeReplaced": current_base is not base,
                "maxMatrixDelta": float(max_matrix_delta),
                "acceptedMatrixWorldRasMm": list(accepted_matrix),
                "candidateMatrixWorldRasMm": list(candidate),
            }
            failed_checks = [
                name for name, failed in (
                    ("not_locked", not verification["baseLocked"]),
                    ("authority_mismatch", observed_authority != str(reviewed_authority)),
                    ("matrix_mismatch", max_matrix_delta > 1.0e-9),
                ) if failed
            ]
            verification["failedChecks"] = failed_checks
            if failed_checks:
                restored, rollback_message = self._manual_base_restore_after_failed_acceptance(
                    parameter_node, base, snapshot, lock_attempted=True
                )
                self._manual_base_acceptance_uncertain = (
                    "lockBase reported success without verifiable accepted Base state "
                    f"(failed checks: {', '.join(failed_checks)}). "
                    + rollback_message
                )
                self._manual_base_review_failure = {
                    "code": "manual_base_acceptance_unknown",
                    "message": "lockBase reported success without verifiable accepted Base state.",
                    "stage": "verification",
                    "rollbackStatus": "unknown",
                    "rollbackEvidence": rollback_message,
                    "rollbackDataRestored": bool(restored),
                    "verificationEvidence": verification,
                }
                self._manual_base_record_acceptance_failure(
                    "manual_base_acceptance_unknown",
                    self._manual_base_acceptance_uncertain,
                    "verification",
                    "unknown",
                )
                return RobotActionResult(
                    False,
                    "manual_base_acceptance_unknown",
                    self._manual_base_acceptance_uncertain,
                    details=self._manual_base_review_details(
                        candidate=candidate,
                        accepted=accepted_matrix,
                        staged=True,
                        identity_status="unknown",
                    ),
                )
            lock_result = failure
            self._manual_base_review = None
            self._manual_base_acceptance_uncertain = ""
            self._manual_base_review_failure = None  # superseded by this acceptance
            return replace(
                lock_result,
                details={
                    **dict(lock_result.details),
                    **self._manual_base_review_details(
                        candidate=None,
                        accepted=accepted_matrix,
                        staged=False,
                        identity_status="accepted",
                    ),
                    "acceptanceStatus": "accepted",
                },
            )
        except Exception as exc:
            restored, rollback_message = self._manual_base_restore_after_failed_acceptance(
                parameter_node, base, snapshot, lock_attempted=lock_attempted
            )
            self._manual_base_acceptance_uncertain = (
                "Base acceptance raised after entering the commit sequence. "
                + rollback_message
                if not restored
                else ""
            )
            self._manual_base_review_failure = {
                "code": "manual_base_acceptance_failed" if restored else "manual_base_acceptance_unknown",
                "message": _bounded_text(exc),
                "stage": "lock" if lock_attempted else "pose",
                "rollbackStatus": "proven" if restored else "unknown",
                "rollbackEvidence": rollback_message,
            }
            self._manual_base_record_acceptance_failure(
                "manual_base_acceptance_failed" if restored else "manual_base_acceptance_unknown",
                str(exc),
                "lock" if lock_attempted else "pose",
                "proven" if restored else "unknown",
            )
            return RobotActionResult(
                False,
                "manual_base_acceptance_failed" if restored else "manual_base_acceptance_unknown",
                _bounded_text(exc) + " Base rollback: " + rollback_message,
                details=self._manual_base_review_details(
                    candidate=candidate,
                    accepted=snapshot["matrixValues"],
                    staged=True,
                    identity_status="current",
                ),
            )
        finally:
            self._manual_base_acceptance_in_progress = False

    def reconcileManualBaseAcceptance(self) -> RobotActionResult:
        """Re-sync the accepted baseline after uncertain Base acceptance."""

        review = self._manual_base_review
        if not self._manual_base_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_base_reconciliation_not_required",
                "There is no uncertain Base acceptance to reconcile.",
            )
        if self._manual_base_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_base_reconciliation_reentrant",
                "Another Base acceptance or reconciliation is already in progress.",
            )

        sync_attempted = False

        def failed(code: str, message: str, identity_status: str = "unknown"):
            if sync_attempted:
                self._planning_scene_synchronized = False
                self._planning_scene_object_count = 0
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                self._runtime_validated_workspace_key = ""
            return RobotActionResult(
                False,
                code,
                message,
                details={
                    **self._manual_base_review_details(
                        candidate=(self._manual_base_review or {}).get(
                            "candidateMatrixWorldRasMm"
                        ),
                        staged=self._manual_base_review is not None,
                        identity_status=identity_status,
                    ),
                    "reconciliationStatus": "failed",
                },
            )

        if review is None:
            return failed(
                "manual_base_review_required",
                "A staged Base review is required to verify its frozen accepted baseline.",
            )
        if self._incomplete_preview_evidence is not None:
            return failed(
                "incomplete_preview_blocks_motion",
                "Base reconciliation is blocked because a guarded preview stopped before endpoint verification.",
            )
        if self._guarded_preview_active or self.previewActive:
            return failed(
                "preview_active",
                "Stop the active preview before reconciling the accepted Base.",
            )
        if self._motion_plan is not None or self._completed_phase or self._phase_sequence:
            return failed(
                "phase_state_requires_reset",
                "Clear the existing Step 6 phase session before reconciling the Base.",
            )

        try:
            parameter_node, base, identity_before, accepted_before = (
                self._manual_base_review_context()
            )
            baseline = self._manual_base_review_matrix(
                review["acceptedBaselineMatrixWorldRasMm"]
            )
            if self._scene_kind(parameter_node) != "case":
                return failed(
                    "scene_required",
                    "Open a case before reconciling the accepted Base.",
                    "case_changed",
                )
            current, stale_reason = self._manual_base_review_is_current(
                parameter_node, base, accepted_before
            )
            if not current or identity_before != review["identity"]:
                return failed(
                    "manual_base_review_stale",
                    "The accepted Base no longer matches the staged review baseline: "
                    + (stale_reason if not current else "case_or_base_identity_changed"),
                    stale_reason if not current else "case_or_base_identity_changed",
                )
            if any(
                abs(float(value) - float(expected)) > 1.0e-9
                for value, expected in zip(accepted_before, baseline)
            ):
                return failed(
                    "manual_base_review_stale",
                    "The accepted Base matrix differs from the frozen review baseline.",
                    "accepted_base_pose_changed",
                )
            is_active = getattr(self._logic, "isRos2MotionControlActive", None)
            if not callable(is_active) or not is_active(base):
                return failed(
                    "ros_required",
                    "Connect ROS 2 Motion Control before reconciling the accepted Base.",
                )
            if bool(parameter_node.robotBaseMountLocked):
                return failed(
                    "base_locked",
                    "Unlock the accepted Base before reconciling its scene state.",
                )
            review_snapshot = deepcopy(review)
            uncertainty = self._manual_base_acceptance_uncertain
        except Exception as exc:
            return failed("manual_base_review_stale", _bounded_text(exc))

        self._manual_base_acceptance_in_progress = True
        try:
            # Sync can change the audit used by runtime Home/workspace validation.
            self._runtime_validated_task_home_key = ""
            self._runtime_task_home_evidence = {}
            self._runtime_validated_workspace_key = ""
            sync_attempted = True
            sync_result = self.syncPlanningScene()
            if not sync_result.success:
                return failed(
                    "manual_base_reconciliation_failed",
                    "Accepted Base scene synchronization failed: " + sync_result.message,
                )

            count = sync_result.details.get("obstacleCount")
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count <= 0
                or not self._planning_scene_synchronized
                or self._planning_scene_object_count != count
            ):
                return failed(
                    "manual_base_reconciliation_failed",
                    "Scene synchronization did not return a complete positive object count.",
                )

            audit = self._logic.collisionSceneAuditRecord(parameter_node)
            if audit is None or getattr(audit, "status", "") != "Acknowledged":
                return failed(
                    "manual_base_reconciliation_unacknowledged",
                    "A fresh acknowledged collision-scene audit is required.",
                )
            audit_fingerprint = str(
                getattr(audit, "audit_fingerprint", "") or ""
            )
            if not audit_fingerprint:
                return failed(
                    "manual_base_reconciliation_unacknowledged",
                    "Collision-scene audit fingerprint is missing.",
                )
            acknowledgement = getattr(audit, "runtime_acknowledgement", None)
            if (
                not isinstance(acknowledgement, Mapping)
                or acknowledgement.get("status") != "Acknowledged"
            ):
                return failed(
                    "manual_base_reconciliation_unacknowledged",
                    "MoveIt did not acknowledge the synchronized collision scene.",
                )

            base_fingerprint = str(
                self._logic.robotBaseFingerprint(parameter_node) or ""
            )
            if (
                not base_fingerprint
                or getattr(audit, "base_fingerprint", "") != base_fingerprint
            ):
                return failed(
                    "manual_base_reconciliation_stale",
                    "Collision-scene evidence belongs to a different Base fingerprint.",
                )

            records = tuple(getattr(audit, "object_records", ()) or ())
            if any(not isinstance(record, Mapping) for record in records):
                return failed(
                    "manual_base_reconciliation_unacknowledged",
                    "Collision-scene audit object evidence is incomplete.",
                )
            object_ids = tuple(
                str(record.get("outgoing_collision_object_id") or "").strip()
                for record in records
            )
            raw_acknowledged_ids = acknowledgement.get("acknowledged_object_ids")
            if isinstance(raw_acknowledged_ids, (str, bytes)):
                raw_acknowledged_ids = None
            try:
                acknowledged_ids = tuple(
                    str(value or "").strip()
                    for value in raw_acknowledged_ids
                )
            except TypeError:
                acknowledged_ids = ()
            if (
                len(records) != count
                or not object_ids
                or any(not value for value in object_ids)
                or len(set(object_ids)) != count
                or len(acknowledged_ids) != count
                or any(not value for value in acknowledged_ids)
                or len(set(acknowledged_ids)) != count
                or set(acknowledged_ids) != set(object_ids)
            ):
                return failed(
                    "manual_base_reconciliation_unacknowledged",
                    "MoveIt acknowledgement does not uniquely cover every synchronized collision object.",
                )

            parameter_after, base_after, identity_after, accepted_after = (
                self._manual_base_review_context()
            )
            current_after, stale_after = self._manual_base_review_is_current(
                parameter_after, base_after, accepted_after
            )
            base_fingerprint_after = str(
                self._logic.robotBaseFingerprint(parameter_after) or ""
            )
            if (
                self._manual_base_review != review_snapshot
                or self._manual_base_acceptance_uncertain != uncertainty
                or not current_after
                or base_fingerprint_after != base_fingerprint
                or identity_after != identity_before
                or parameter_after is not parameter_node
                or base_after is not base
                or self._scene_kind(parameter_after) != "case"
                or any(
                    abs(float(value) - float(expected)) > 1.0e-9
                    for value, expected in zip(accepted_after, baseline)
                )
                or bool(parameter_after.robotBaseMountLocked)
                or not is_active(base_after)
                or self._incomplete_preview_evidence is not None
                or self._guarded_preview_active
                or self.previewActive
                or self._motion_plan is not None
                or self._completed_phase
                or self._phase_sequence
            ):
                return failed(
                    "manual_base_reconciliation_stale",
                    "The staged review, accepted Base, or simulation state changed during scene synchronization."
                    + (" " + stale_after if not current_after else ""),
                    stale_after if not current_after else "post_sync_state_changed",
                )

            self._runtime_validated_task_home_key = ""
            self._runtime_task_home_evidence = {}
            self._runtime_validated_workspace_key = ""
            self._manual_base_acceptance_uncertain = ""
            return RobotActionResult(
                True,
                "manual_base_acceptance_reconciled",
                "The accepted Base baseline was re-synchronized and acknowledged; the staged candidate remains unchanged.",
                details={
                    **self._manual_base_review_details(
                        candidate=review_snapshot["candidateMatrixWorldRasMm"],
                        accepted=accepted_after,
                        staged=True,
                        identity_status="reconciled",
                    ),
                    "reconciliationStatus": "acknowledged",
                    "obstacleCount": count,
                    "auditFingerprint": audit_fingerprint,
                    "acknowledgedObjectIds": acknowledged_ids,
                },
            )
        except Exception as exc:
            return failed(
                "manual_base_reconciliation_failed",
                "Accepted Base scene reconciliation failed: " + _bounded_text(exc),
            )
        finally:
            self._manual_base_acceptance_in_progress = False

    def lockBase(self) -> RobotActionResult:
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Base lock changes are blocked because a guarded preview stopped before endpoint verification.",
            )
        try:
            parameter_node = self._require_context()
            record_unavailable = self._manual_simulation_prepare_current_identity()
            if self._scene_kind(parameter_node) != "case":
                return RobotActionResult(False, "scene_required", "Open a case and establish its Case Foundation before locking the base.")
            preparation_issue = self._scene_placement_issue(parameter_node)
            if preparation_issue:
                return RobotActionResult(
                    False,
                    "case_jaw_opening_required",
                    preparation_issue,
                )
            if not (self._logic.robotModelNodes() or self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform)):
                return RobotActionResult(False, "robot_required", "Load the ROS robot or local fallback before locking the base.")
            candidate_matrix = None
            try:
                candidate_matrix = self._manual_simulation_base_matrix(parameter_node)
            except (RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
                record_unavailable = record_unavailable or _bounded_text(exc)
            self._logic.setRobotBaseMountLocked(parameter_node, True)
            obstacle_count = 0
            if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                obstacle_count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
                self._planning_scene_object_count = obstacle_count
                self._planning_scene_synchronized = True
            self._clear_phase_session()
            accepted_matrix = None
            accepted_fingerprint = ""
            try:
                accepted_matrix = self._manual_simulation_base_matrix(parameter_node)
                accepted_fingerprint = str(
                    self._logic.robotBaseFingerprint(parameter_node) or ""
                )
            except (RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
                record_unavailable = record_unavailable or _bounded_text(exc)
            result = RobotActionResult(
                True,
                "base_locked",
                "Manual Simulation Base reviewed and locked for diagnostic use; "
                f"{obstacle_count} MoveIt collision surface(s) synchronized. "
                "This is not forehead or registration evidence.",
                details={
                    "obstacleCount": obstacle_count,
                    "manualSimulationBaseCandidateMatrixWorldRasMm": candidate_matrix,
                    "manualSimulationBaseAcceptedFingerprint": accepted_fingerprint,
                    "manualSimulationBaseAcceptedMatrixWorldRasMm": accepted_matrix,
                },
            )
            if candidate_matrix is None or accepted_matrix is None or not accepted_fingerprint:
                return self._manual_simulation_recording_unavailable(
                    result,
                    "The Base lock succeeded, but a complete pre-commit record "
                    "could not be built. "
                    + (
                        record_unavailable
                        or "A valid accepted Base matrix and fingerprint were unavailable."
                    ),
                )
            return self._manual_simulation_finish_acceptance(
                result,
                review_event={
                    "kind": "review_base",
                    "monotonic_ns": monotonic_ns(),
                    "details": {
                        "candidate_matrix_world_ras_mm": candidate_matrix,
                        "guard_policy_fingerprint": "unknown",
                    },
                },
                acceptance_event={
                    "kind": "accept_base",
                    "monotonic_ns": monotonic_ns(),
                    "details": {
                        "accepted_fingerprint": str(accepted_fingerprint or ""),
                        "accepted_matrix_world_ras_mm": accepted_matrix,
                        "guard_policy_fingerprint": "unknown",
                    },
                },
                unavailable_reason=(
                    "The Base lock succeeded, but no complete pre-commit "
                    "recording identity was available. " + record_unavailable
                ),
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_lock_failed", str(exc))

    def unlockBase(self) -> RobotActionResult:
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Base lock changes are blocked because a guarded preview stopped before endpoint verification.",
            )
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
        """Check the latest guard result and inspect the current review vector."""

        return self._checkStateValidity(include_manual_endpoint=True)

    def _checkStateValidity(
        self, *, include_manual_endpoint: bool = False
    ) -> RobotActionResult:
        try:
            state = self.currentRobotState()
            if not state.ros_motion_active:
                result = RobotActionResult(
                    True,
                    "draft_state_only",
                    "Local MRML state is available; MoveIt/FCL validity requires a ROS 2 connection.",
                    details={"authoritative": False},
                )
            else:
                status = self._bridge.joint_command_status()
                if status is None:
                    result = RobotActionResult(
                        False,
                        "status_unavailable",
                        "No fresh MoveIt joint-validity status is available.",
                    )
                else:
                    result = RobotActionResult(
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
            state = None
            result = RobotActionResult(False, "state_check_failed", str(exc))

        if not include_manual_endpoint:
            return result

        manual_evaluation = self._manualStateEndpointEvaluation(state)

        endpoint = manual_evaluation["endpoint_evaluation"]
        static_status = str(
            (endpoint.get("static_state_validity") or {}).get(
                "status", "not_reached"
            )
        )
        summary = (
            "Manual endpoint diagnostic (separate from the latest command-guard "
            f"status; static endpoint/FK only): current-state static={static_status}, "
            f"target endpoint={manual_evaluation['target_endpoint_status']}"
        )
        position_residual = endpoint.get("position_residual_mm")
        if position_residual is not None:
            summary += f", position residual={float(position_residual):.3f} mm"
        axis_residual = endpoint.get("drilling_axis_residual_deg")
        if axis_residual is not None:
            summary += f", axis residual={float(axis_residual):.3f}°"
        if manual_evaluation.get("stale"):
            summary += " (stale; measurements retained)"
        elif manual_evaluation["status"] == "not_reached":
            summary += f" (not reached: {manual_evaluation['reason']})"

        details = dict(result.details)
        details["manual_state_evaluation"] = manual_evaluation
        return replace(result, message=f"{result.message} {summary}", details=details)

    def checkManualRobotDraftState(
        self, joint_positions_si: Mapping[str, float]
    ) -> RobotActionResult:
        """Evaluate one captured J1–J5 review pose without accepting it."""

        reason = ""
        requested = {}
        if not isinstance(joint_positions_si, Mapping):
            reason = "A manual draft must be a joint-position mapping."
        elif set(joint_positions_si) != set(JOINT_NAMES):
            reason = "A manual draft must contain exactly the five canonical J1–J5 values."
        else:
            try:
                for name in JOINT_NAMES:
                    value = joint_positions_si[name]
                    if isinstance(value, bool) or not isinstance(value, Real):
                        raise ValueError(f"{name} must be a finite numeric SI value.")
                    numeric = float(value)
                    if not isfinite(numeric):
                        raise ValueError(f"{name} must be a finite numeric SI value.")
                    requested[name] = numeric
            except (TypeError, ValueError, OverflowError) as exc:
                reason = str(exc)

        if reason:
            evaluation = self._manualStateEndpointEvaluation(
                None, review_positions_si={}
            )
            evaluation.update(
                input_status="invalid",
                input_joint_positions_si=None,
                requestedJointPositionsSi=None,
                reason=reason,
            )
            evaluation["endpoint_evaluation"]["static_state_validity"]["message"] = reason
            evaluation["endpoint_evaluation"]["fk"]["message"] = reason
            return RobotActionResult(
                False,
                "manual_draft_invalid_request",
                reason,
                details={
                    "authoritative": False,
                    "routeAuthority": "none",
                    "simulationOnly": True,
                    "draftWithinCommandLimits": None,
                    "limitMargins": None,
                    "limitViolations": [],
                    "limitAssessmentAuthoritative": False,
                    "manual_state_evaluation": evaluation,
                },
            )

        parameter_node = None
        identity_before = None
        identity_after = None
        limit_margins = None

        def incomplete(message, *, stale=None):
            evaluation = self._manualStateEndpointEvaluation(
                None, review_positions_si=requested
            )
            evaluation.update(
                status="unknown",
                target_endpoint_status="not_reached",
                stale=stale,
                identity_status=(
                    "current" if stale is False and identity_before is not None
                    else "stale" if stale is True
                    else "unknown"
                ),
                identity_before=(
                    dict(identity_before) if isinstance(identity_before, Mapping) else None
                ),
                identity_after=(
                    dict(identity_after) if isinstance(identity_after, Mapping) else None
                ),
                reason=message,
                requestedJointPositionsSi=dict(requested),
                limitMargins=limit_margins,
                draftWithinCommandLimits=None,
                limitViolations=[],
                limitAssessmentAuthoritative=False,
            )
            return RobotActionResult(
                False,
                "manual_draft_evaluation_incomplete",
                "Manual draft evaluation is unknown: " + message,
                details={
                    "authoritative": False,
                    "routeAuthority": "none",
                    "simulationOnly": True,
                    "draftWithinCommandLimits": None,
                    "limitMargins": limit_margins,
                    "limitViolations": [],
                    "limitAssessmentAuthoritative": False,
                    "manual_state_evaluation": evaluation,
                },
            )

        try:
            parameter_node = self._require_context()
            identity_before = self._manual_jog_current_identity(parameter_node)
        except Exception as exc:
            return incomplete(
                "Current task identity is unavailable; static, FK, and target evaluation were not reached. "
                + _bounded_text(exc)
            )

        try:
            mechanical_limits = default_task_joint_limits_from_urdf(
                self._logic.robotDescriptionPaths()[0]
            )
            task_limits = self._logic.getTaskJointLimits(parameter_node)
            limit_margins = joint_limit_margin_evidence(
                requested,
                joint_names=JOINT_NAMES,
                joint_limit_fields=JOINT_LIMIT_FIELDS[: len(JOINT_NAMES)],
                display_units=JOINT_DISPLAY_UNITS[: len(JOINT_NAMES)],
                mechanical_limits=mechanical_limits,
                task_limits=task_limits,
            )
            if (not isinstance(limit_margins, Mapping)
                    or set(limit_margins) != set(JOINT_NAMES)):
                raise ValueError("Mechanical or reviewed J1–J5 limits are incomplete.")
            for name in JOINT_NAMES:
                row = limit_margins[name]
                if (not isinstance(row, Mapping)
                        or not isinstance(row.get("mechanical_within_limits"), bool)
                        or not isinstance(row.get("reviewed_task_within_limits"), bool)):
                    raise ValueError(f"Joint limit evidence for {name} is incomplete.")
        except Exception as exc:
            try:
                identity_after = self._manual_jog_current_identity(parameter_node)
            except Exception as identity_exc:
                return incomplete(
                    "Joint limits and current task identity are unavailable; static, FK, and target evaluation were not reached. "
                    + _bounded_text(identity_exc)
                )
            if identity_after != identity_before:
                return incomplete(
                    "Task identity changed while reading mechanical/reviewed limits; static, FK, and target evaluation were not reached.",
                    stale=True,
                )
            return incomplete(
                "Mechanical or reviewed J1–J5 limits are unavailable; static, FK, and target evaluation were not reached. "
                + _bounded_text(exc),
                stale=False,
            )

        try:
            identity_after = self._manual_jog_current_identity(parameter_node)
        except Exception as exc:
            return incomplete(
                "Current task identity became unavailable while checking limits; static, FK, and target evaluation were not reached. "
                + _bounded_text(exc)
            )
        if identity_after != identity_before:
            return incomplete(
                "Task identity changed while checking limits; static, FK, and target evaluation were not reached.",
                stale=True,
            )

        limit_violations = []
        for joint_index, (name, field_name) in enumerate(zip(
            JOINT_NAMES, JOINT_LIMIT_FIELDS[: len(JOINT_NAMES)]
        ), start=1):
            row = limit_margins[name]
            for source, within_key, lower_margin_key, upper_margin_key, limits in (
                (
                    "mechanical",
                    "mechanical_within_limits",
                    "mechanical_lower_margin",
                    "mechanical_upper_margin",
                    mechanical_limits,
                ),
                (
                    "reviewed_task",
                    "reviewed_task_within_limits",
                    "reviewed_task_lower_margin",
                    "reviewed_task_upper_margin",
                    task_limits,
                ),
            ):
                if row[within_key]:
                    continue
                lower_margin = float(row[lower_margin_key])
                upper_margin = float(row[upper_margin_key])
                pair = getattr(limits, field_name)
                if lower_margin < -1.0e-8:
                    bound, limit_value, margin = "minimum", float(pair.minimum), lower_margin
                elif upper_margin < -1.0e-8:
                    bound, limit_value, margin = "maximum", float(pair.maximum), upper_margin
                else:
                    return incomplete(
                        f"Limit evidence for {name} is inconsistent; static, FK, and target evaluation were not reached.",
                        stale=False,
                    )
                limit_violations.append(
                    {
                        "jointLabel": f"J{joint_index}",
                        "jointName": name,
                        "limitSource": source,
                        "bound": bound,
                        "boundDisplayValue": limit_value,
                        "candidateDisplayValue": float(row["value_display"]),
                        "unit": str(row["unit"]),
                        "margin": margin,
                    }
                )

        if limit_violations:
            summary = "; ".join(
                f"{item['jointLabel']} ({item['jointName']}) "
                f"{item['limitSource']} {item['bound']} bound "
                f"{item['boundDisplayValue']:g} {item['unit']} "
                f"(candidate {item['candidateDisplayValue']:g} {item['unit']})"
                for item in limit_violations
            )
            message = (
                "Manual draft exceeds command joint limits: " + summary
                + ". Static, FK, and target evaluation were not reached; the draft was not accepted."
            )
            evaluation = self._manualStateEndpointEvaluation(
                None, review_positions_si=requested
            )
            evaluation.update(
                status="failed",
                target_endpoint_status="not_reached",
                stale=False,
                identity_status="current",
                identity_before=dict(identity_before),
                identity_after=dict(identity_after),
                reason=message,
                requestedJointPositionsSi=dict(requested),
                limitMargins=dict(limit_margins),
                draftWithinCommandLimits=False,
                limitViolations=limit_violations,
                limitAssessmentAuthoritative=True,
            )
            evaluation["endpoint_evaluation"].update(
                status="not_reached",
                static_state_validity={
                    "status": "not_reached",
                    "authoritative": False,
                    "message": "Static evaluation was not reached because the draft exceeds command joint limits.",
                },
                collision={"status": "not_reached", "pairs": None},
                fk={
                    "status": "not_reached",
                    "message": "FK was not reached because the draft exceeds command joint limits.",
                    "pose_world_ras_mm": None,
                },
            )
            return RobotActionResult(
                False,
                "manual_draft_state_invalid",
                message,
                details={
                    "authoritative": False,
                    "routeAuthority": "none",
                    "simulationOnly": True,
                    "draftWithinCommandLimits": False,
                    "limitMargins": dict(limit_margins),
                    "limitViolations": limit_violations,
                    "limitAssessmentAuthoritative": True,
                    "manual_state_evaluation": evaluation,
                },
            )

        try:
            state = self.currentRobotState()
        except Exception:
            state = None
        evaluation = self._manualStateEndpointEvaluation(
            state, review_positions_si=requested
        )
        evaluation["limitMargins"] = dict(limit_margins)
        evaluation["draftWithinCommandLimits"] = True
        evaluation["limitViolations"] = []
        evaluation["limitAssessmentAuthoritative"] = True
        evaluation["limitIdentityBefore"] = dict(identity_before)
        evaluation["limitIdentityAfter"] = dict(identity_after)
        try:
            identity_after_evaluation = self._manual_jog_current_identity(parameter_node)
        except Exception as exc:
            identity_after_evaluation = None
            evaluation["limitIdentityAfterEvaluationError"] = _bounded_text(exc)
        evaluation_identity = evaluation.get("identity_before")
        evaluation_identity_matches = bool(
            isinstance(evaluation_identity, Mapping)
            and set(evaluation_identity).issubset(identity_before)
            and all(identity_before[key] == value for key, value in evaluation_identity.items())
        )
        final_identity_current = identity_after_evaluation == identity_before
        if not evaluation_identity_matches or not final_identity_current:
            evaluation.update(
                status="unknown",
                target_endpoint_status="unknown",
                stale=True if identity_after_evaluation is not None else None,
                identity_status="stale" if identity_after_evaluation is not None else "unknown",
                reason="Task identity changed or could not be confirmed during limit/static evaluation.",
            )
        evaluation.update(
            requestedJointPositionsSi=dict(requested),
            routeAuthority="none",
            simulationOnly=True,
        )
        static = evaluation["endpoint_evaluation"].get("static_state_validity") or {}
        static_status = str(static.get("status") or "unknown")
        static_authoritative = static.get("authoritative") is True
        identity_current = evaluation["identity_status"] == "current"
        safe_static_pass = (
            evaluation["status"] == "passed"
            and static_status == "passed"
            and static_authoritative
            and identity_current
        )
        static_rejection = (
            evaluation["status"] == "failed"
            and static_status == "failed"
            and static_authoritative
            and identity_current
        )
        result_message = (
            "Read-only authoritative static evaluation passed; the candidate remains a review state and was not accepted."
            if safe_static_pass else
            "The captured draft failed authoritative static validity: "
            + str(static.get("message") or "MoveIt rejected the static state.")
            + ". FK was not reached; the draft was not accepted."
            if static_rejection else
            "Manual draft evaluation is "
            + str(evaluation.get("status") or "unknown")
            + ": "
            + str(evaluation.get("reason") or "Required evidence is unavailable.")
        )
        return RobotActionResult(
            safe_static_pass,
            "manual_draft_evaluated"
            if safe_static_pass
            else "manual_draft_state_invalid"
            if static_rejection
            else "manual_draft_evaluation_incomplete",
            result_message,
            details={
                "authoritative": bool(
                    static.get("authoritative")
                    and evaluation.get("identity_status") == "current"
                    and evaluation.get("status") in {"passed", "failed"}
                ),
                "routeAuthority": "none",
                "simulationOnly": True,
                "draftWithinCommandLimits": True,
                "limitMargins": dict(limit_margins),
                "limitViolations": [],
                "limitAssessmentAuthoritative": True,
                "manual_state_evaluation": evaluation,
            },
        )

    def _step6_read_only_freshness_issues(
        self, parameter_node, *, include_home: bool = True
    ) -> tuple[str, ...]:
        """Check read-only Step 6 freshness without registry sync."""

        issues: list[str] = []
        checks = (
            ("anatomy review", "step6AnatomyReviewFreshnessIssues"),
            ("Case Foundation jaw opening", "step6CaseJawOpeningFreshnessIssues"),
            ("base placement", "step6BasePlacementFreshnessIssues"),
        )
        if include_home:
            checks += (("Task Home", "taskHomeFreshnessIssues"),)
        for label, method_name in checks:
            checker = getattr(self._logic, method_name, None)
            if not callable(checker):
                issues.append(f"{label} freshness check is unavailable.")
                continue
            found = checker(parameter_node)
            issues.extend(str(issue) for issue in (found or ()))
        return tuple(dict.fromkeys(issue for issue in issues if issue))

    def _manualStateEndpointEvaluation(
        self, state, *, review_positions_si: Optional[Mapping[str, float]] = None
    ) -> dict[str, object]:
        """Return read-only endpoint evidence for current or captured review joints."""

        review_mode = review_positions_si is not None
        input_positions = (
            dict(review_positions_si)
            if review_mode
            else dict(state.joint_positions_si) if state is not None else None
        )
        unavailable = {
            "status": "not_reached",
            "static_state_validity": {
                "status": "not_reached",
                "authoritative": False,
                "message": "Prerequisite unavailable.",
            },
            "collision": {"status": "not_reached", "pairs": None},
            "fk": {
                "status": "not_reached",
                "message": "Prerequisite unavailable.",
                "pose_world_ras_mm": None,
            },
            "position_residual_mm": None,
            "drilling_axis_residual_deg": None,
        }
        evaluation = {
            "status": "not_reached",
            "target_endpoint_status": "not_reached",
            "scope": "single_state_endpoint_only",
            "stale": None,
            "identity_status": "unknown",
            "input_status": "captured_review" if review_mode else "not_reached",
            **({"input_source": "captured_review"} if review_mode else {}),
            "input_joint_positions_si": input_positions,
            "input_joint_positions_si_after": None,
            "target_ras_mm": None,
            "drilling_axis_world_ras_unit": None,
            "identity_before": None,
            "identity_after": None,
            "endpoint_evaluation": unavailable,
            "routeAuthority": "none",
            "simulationOnly": True,
            "reason": "A current eligible PreparedBranch and synchronized scene are required.",
        }
        if review_mode:
            evaluation["requestedJointPositionsSi"] = dict(input_positions)
        if state is None:
            evaluation["reason"] = "The displayed joint state is unavailable."
            return evaluation

        try:
            parameter_node = self._require_context()
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            if not state.ros_motion_active:
                evaluation["reason"] = "The simulation-only ROS/MoveIt runtime is not active."
            elif self._scene_kind(parameter_node) != "case" or not self._planning_scene_synchronized:
                evaluation["reason"] = "A synchronized case collision scene is required."
            elif snapshot is None:
                try:
                    identity_before = self._manual_jog_current_identity(parameter_node)
                except (RuntimeError, ValueError, TypeError, OSError, KeyError, AttributeError) as exc:
                    evaluation["status"] = "unknown"
                    evaluation["reason"] = _bounded_text(exc)
                else:
                    evaluation["identity_before"] = dict(identity_before)
                    if not str(identity_before.get("task") or "").startswith("unconfirmed:"):
                        evaluation.update(
                            status="unknown",
                            stale=True,
                            identity_status="stale",
                            reason="A task was confirmed before the unconfirmed review began.",
                        )
                    else:
                        evaluation["scope"] = "single_state_static_and_fk_only"
                        endpoint_error = ""
                        try:
                            evaluation["endpoint_evaluation"] = self._evaluate_step6_tcp_endpoint(
                                parameter_node, input_positions
                            )
                        except Exception as exc:
                            endpoint_error = _bounded_text(exc)
                            evaluation["endpoint_evaluation"] = {
                                **unavailable,
                                "status": "unknown",
                                "static_state_validity": {
                                    "status": "unknown",
                                    "authoritative": False,
                                    "message": endpoint_error,
                                },
                                "collision": {"status": "unknown", "pairs": None},
                                "fk": {
                                    "status": "unknown",
                                    "message": endpoint_error,
                                    "pose_world_ras_mm": None,
                                },
                            }
                        try:
                            identity_after = self._manual_jog_current_identity(parameter_node)
                            evaluation["identity_after"] = dict(identity_after)
                        except (RuntimeError, ValueError, TypeError, OSError, KeyError, AttributeError) as exc:
                            identity_after = None
                            evaluation["identity_after_error"] = _bounded_text(exc)
                        evaluation["identity_status"] = (
                            "unknown" if identity_after is None
                            else "current" if identity_before == identity_after
                            else "stale"
                        )
                        if review_mode:
                            evaluation["input_status"] = "captured_review"
                        else:
                            try:
                                positions_after = dict(self.currentRobotState().joint_positions_si)
                                evaluation["input_joint_positions_si_after"] = positions_after
                                evaluation["input_status"] = (
                                    "current" if input_positions == positions_after else "stale"
                                )
                            except Exception as exc:
                                evaluation["input_status"] = "unknown"
                                evaluation["input_after_error"] = _bounded_text(exc)
                        input_status = evaluation["input_status"]
                        identity_status = evaluation["identity_status"]
                        stale = "stale" in (identity_status, input_status)
                        current = identity_status == "current" and input_status in {
                            "current", "captured_review"
                        }
                        evaluation["stale"] = True if stale else False if current else None
                        static = evaluation["endpoint_evaluation"].get(
                            "static_state_validity"
                        ) or {}
                        static_status = str(static.get("status") or "unknown")
                        evaluation["status"] = (
                            static_status if current and not stale else "unknown"
                        )
                        evaluation["reason"] = (
                            "The unconfirmed task identity changed during the query; the result is unknown."
                            if stale else
                            "The unconfirmed task identity could not be confirmed after the query."
                            if not current else
                            "Static evaluation failed; FK was not reached: "
                            + str(static.get("message") or "static state invalid.")
                            if static_status == "failed" else
                            "Read-only static validity and FK completed; target endpoint was not evaluated."
                            if static_status == "passed" and not endpoint_error else
                            "Read-only static evaluation was unavailable: "
                            + str(static.get("message") or endpoint_error or "required evidence unavailable.")
                        )
            else:
                collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
                home = self._logic.taskHomeRecord(parameter_node)
                registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
                branch_id = str(registry.get("selected_branch_id") or "")
                branches = registry.get("prepared_branches")
                if not bool(parameter_node.step6PlanningContextImported) or not branch_id:
                    evaluation["reason"] = "No active selected PreparedBranch is available."
                elif collision_audit is None or home is None:
                    evaluation["reason"] = "A current Task Home and collision-scene audit are required."
                elif collision_audit.runtime_acknowledgement.get("status") != "Acknowledged":
                    evaluation["reason"] = "The collision scene has no runtime acknowledgement."
                elif not isinstance(branches, Mapping) or branch_id not in branches:
                    evaluation["reason"] = "The selected PreparedBranch is unavailable."
                else:
                    read_only_freshness_issues = self._step6_read_only_freshness_issues(
                        parameter_node
                    )
                    branch = self._logic.evaluatePreparedBranchEligibility(
                        parameter_node, branch_id, registry=registry
                    )
                    task_issues = task_snapshot_invalidation_reasons(
                        snapshot,
                        target_segment_id=str(parameter_node.targetToothSegmentId or ""),
                        trajectory_revision=self._logic.step6TrajectoryRevision(parameter_node),
                        base_fingerprint=self._logic.robotBaseFingerprint(parameter_node),
                        home_fingerprint=fingerprint(home.to_dict()),
                        limits_fingerprint=self._logic.step6TaskLimitsFingerprint(parameter_node),
                        robot_profile_fingerprint=self._logic.robotProfileFingerprint(),
                        tool_frame=str(parameter_node.step6ToolFrame),
                    )
                    if not branch.get("eligible") or task_issues or read_only_freshness_issues:
                        stale_issues = (
                            tuple(read_only_freshness_issues)
                            + tuple(task_issues)
                            + (() if branch.get("eligible") else (str(branch.get("message") or branch.get("reason") or "PreparedBranch is stale."),))
                        )
                        evaluation.update(
                            status="unknown",
                            target_endpoint_status="unknown",
                            stale=True,
                            identity_status="stale",
                            reason=(
                                "The selected task/branch or its anatomy/base/Home prerequisites are stale: "
                                + ", ".join(stale_issues)
                            ),
                        )
                    else:
                        entry = tuple(float(value) for value in snapshot.entry_ras_mm)
                        target = tuple(float(value) for value in snapshot.target_ras_mm)
                        evaluation["target_ras_mm"] = target
                        direction = tuple(target[i] - entry[i] for i in range(3))
                        axis_length = sqrt(sum(value * value for value in direction))
                        if axis_length <= 1.0e-12:
                            evaluation.update(
                                status="unknown",
                                target_endpoint_status="unknown",
                                reason="The confirmed Entry-to-Target axis is degenerate.",
                            )
                        else:
                            drill_axis = tuple(value / axis_length for value in direction)
                            evaluation["drilling_axis_world_ras_unit"] = drill_axis
                            identity_before = self.plannerComparisonIdentity()
                            evaluation["identity_before"] = dict(identity_before)
                            expected_identity = {
                                "branch_id": branch_id,
                                "task": snapshot.snapshot_fingerprint,
                                "base": self._logic.robotBaseFingerprint(parameter_node),
                                "home": snapshot.home_fingerprint,
                                "trajectory": self._logic.step6TrajectoryRevision(parameter_node),
                                "robot_profile": self._logic.robotProfileFingerprint(),
                                "collision_audit": planner_comparison_scene_fingerprint(
                                    collision_audit
                                ),
                            }
                            if identity_before != expected_identity:
                                evaluation["identity_after"] = dict(
                                    self.plannerComparisonIdentity()
                                )
                                evaluation.update(
                                    status="unknown",
                                    target_endpoint_status="unknown",
                                    stale=True,
                                    identity_status="stale",
                                    reason=(
                                        "The task, branch, or scene changed after prerequisite checks; "
                                        "endpoint evaluation was not reached."
                                    ),
                                )
                                return evaluation
                            try:
                                evaluation["endpoint_evaluation"] = self._evaluate_step6_tcp_endpoint(
                                    parameter_node,
                                    input_positions,
                                    expected_tcp_world_ras_mm=target,
                                    expected_drill_axis_world_ras_unit=drill_axis,
                                )
                            except Exception as exc:
                                endpoint_error = str(exc)
                                evaluation["endpoint_evaluation"] = {
                                    "status": "unknown",
                                    "static_state_validity": {
                                        "status": "unknown",
                                        "authoritative": False,
                                        "message": endpoint_error,
                                    },
                                    "collision": {"status": "unknown", "pairs": None},
                                    "fk": {
                                        "status": "unknown",
                                        "message": endpoint_error,
                                        "pose_world_ras_mm": None,
                                    },
                                    "position_residual_mm": None,
                                    "drilling_axis_residual_deg": None,
                                }
                            else:
                                endpoint_error = ""
                            finally:
                                try:
                                    evaluation["identity_after"] = dict(self.plannerComparisonIdentity())
                                except Exception as exc:
                                    evaluation["identity_after_error"] = str(exc)
                            if not review_mode:
                                try:
                                    positions_after = dict(self.currentRobotState().joint_positions_si)
                                    evaluation["input_joint_positions_si_after"] = positions_after
                                except Exception as exc:
                                    evaluation["input_after_error"] = str(exc)

                            identity_after = evaluation.get("identity_after")
                            evaluation["identity_status"] = (
                                "unknown" if not isinstance(identity_after, Mapping)
                                else "current" if identity_before == identity_after
                                else "stale"
                            )
                            if review_mode:
                                evaluation["input_status"] = "captured_review"
                                stale = evaluation["identity_status"] == "stale"
                                current = evaluation["identity_status"] == "current"
                            else:
                                positions_after = evaluation.get("input_joint_positions_si_after")
                                evaluation["input_status"] = (
                                    "unknown" if not isinstance(positions_after, Mapping)
                                    else "current" if input_positions == positions_after
                                    else "stale"
                                )
                                stale = "stale" in (evaluation["identity_status"], evaluation["input_status"])
                                current = evaluation["identity_status"] == evaluation["input_status"] == "current"
                            evaluation["stale"] = True if stale else False if current else None
                            endpoint = evaluation["endpoint_evaluation"]
                            endpoint_status = str(endpoint.get("status") or "unknown")
                            static_status = str(
                                (endpoint.get("static_state_validity") or {}).get(
                                    "status", "unknown"
                                )
                            )
                            evaluation["status"] = (
                                "unknown" if stale or not current else static_status
                            )
                            evaluation["target_endpoint_status"] = (
                                "unknown" if stale or not current else endpoint_status
                            )
                            evaluation["reason"] = (
                                "The planner identity changed during the query; captured measurements are retained as stale."
                                if stale and review_mode else
                                "The joint vector or planner identity changed during the query; captured measurements are retained as stale."
                                if stale else
                                "The joint vector or planner identity could not be confirmed after the query."
                                if not current else
                                "The read-only endpoint evaluation failed: " + endpoint_error
                                if endpoint_error else
                                "Static evaluation failed; FK was not reached: "
                                + str((endpoint.get("static_state_validity") or {}).get("message") or "static state invalid.")
                                if static_status == "failed" else
                                "Read-only static endpoint and FK evaluation completed for the captured review input."
                                if review_mode else
                                "Read-only static endpoint and FK evaluation completed for the current input."
                            )
        except Exception as exc:
            evaluation["status"] = "unknown"
            if evaluation["target_endpoint_status"] == "not_reached":
                evaluation["target_endpoint_status"] = "unknown"
            evaluation["reason"] = "Manual endpoint evaluation was unavailable: " + str(exc)
        return evaluation

    @staticmethod
    def _manual_task_home_review_vector(value) -> dict[str, float]:
        if isinstance(value, Mapping):
            if set(value) != set(JOINT_NAMES):
                raise ValueError("Task Home review accepts exactly five canonical J1–J5 values.")
            values = tuple(value[name] for name in JOINT_NAMES)
        elif isinstance(value, (str, bytes)):
            raise ValueError("Task Home review accepts exactly five finite J1–J5 SI values.")
        else:
            try:
                values = tuple(value)
            except TypeError as exc:
                raise ValueError("Task Home review accepts exactly five finite J1–J5 SI values.") from exc
        if len(values) != len(JOINT_NAMES) or any(isinstance(item, bool) for item in values):
            raise ValueError("Task Home review accepts exactly five finite J1–J5 SI values.")
        try:
            vector = tuple(float(item) for item in values)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Task Home review accepts exactly five finite J1–J5 SI values.") from exc
        if not all(isfinite(item) for item in vector):
            raise ValueError("Task Home review accepts exactly five finite J1–J5 SI values.")
        return dict(zip(JOINT_NAMES, vector))

    def _manual_task_home_accepted_positions(self):
        reader = getattr(self._bridge, "last_accepted_joint_positions_si", None)
        try:
            return self._manual_task_home_review_vector(reader()) if callable(reader) else None
        except Exception:
            return None

    def taskHomeJointIdentity(self) -> dict:
        """Read-only: the accepted, monitored and displayed J1–J5 vectors (SI) that the Task Home accept path compares.

        Each entry is a canonical five-joint mapping or ``None`` when that source is unavailable. It changes
        nothing and never moves the robot (S6-ADVISOR-GUI-01 consent-gated Home revalidation).
        """

        monitored = displayed = None
        reader = getattr(self._bridge, "monitored_joint_positions_si", None)
        try:
            monitored = self._manual_task_home_review_vector(reader()) if callable(reader) else None
        except Exception:
            monitored = None
        try:
            state = self.currentRobotState().joint_positions_si
            displayed = self._manual_task_home_review_vector({name: state[name] for name in JOINT_NAMES})
        except Exception:
            displayed = None
        return {"accepted": self._manual_task_home_accepted_positions(), "monitored": monitored, "displayed": displayed}

    @staticmethod
    def _manual_task_home_non_home_identity(identity) -> dict[str, str]:
        keys = ("branch_id", "base", "trajectory", "robot_profile", "collision_audit", "limits")
        if not isinstance(identity, Mapping):
            raise ValueError("The frozen manual identity is unavailable.")
        result = {key: str(identity.get(key) or "") for key in keys}
        if any(not value for value in result.values()):
            raise ValueError("The frozen non-Home manual identity is incomplete.")
        return result

    def _manual_task_home_record_snapshot(self, parameter_node):
        raw_json = str(parameter_node.step6TaskHomeJson or "")
        record = self._logic.taskHomeRecord(parameter_node)
        revision = 0 if record is None else getattr(record, "revision", None)
        if isinstance(revision, bool) or not isinstance(revision, int):
            revision = None
        return {
            "rawJsonFingerprint": fingerprint({"rawJson": raw_json}),
            "recordFingerprint": self._task_home_runtime_key(record),
            "revision": revision,
        }, record

    def _manual_task_home_setup_mode(self, parameter_node) -> str:
        checker = getattr(self._logic, "isRos2MotionControlActive", None)
        if not callable(checker):
            raise RuntimeError("The robot connection state is unavailable.")
        return "connected" if checker(parameter_node.robotBaseTransform) else "offline"

    def _manual_task_home_offline_identity(
        self, parameter_node, *, allow_acceptance_in_progress: bool = False
    ) -> dict[str, object]:
        if self._scene_kind(parameter_node) != "case":
            raise ValueError("Load the active case before configuring Task Home.")
        if (
            self.previewActive
            or self._guarded_preview_active
            or self._incomplete_preview_evidence is not None
            or self._motion_plan is not None
            or self._completed_phase
            or self._phase_sequence
            or self._phase_guard_session_id
        ):
            raise ValueError("Stop and resolve the active preview or phase before configuring Task Home.")
        if (
            self._manual_base_acceptance_uncertain
            or self._manual_base_acceptance_in_progress
            or self._manual_task_home_acceptance_uncertain
            or (self._manual_task_home_acceptance_in_progress and not allow_acceptance_in_progress)
            or self._manual_task_home_reconciliation_in_progress
            or self._manual_jog_in_progress
            or self._manual_jog_reconciliation_required
            or self._manual_jog_uncertainty is not None
        ):
            raise ValueError("Resolve the outstanding Base, Home, or manual-jog uncertainty first.")
        if self._manual_task_home_setup_mode(parameter_node) != "offline":
            raise ValueError("The robot connection changed; review Task Home in the connected setup mode.")

        base = parameter_node.robotBaseTransform
        is_base = getattr(self._logic, "isRobotBaseTransformNode", None)
        if not callable(is_base) or not is_base(base):
            raise ValueError("Load the local Step 6 robot before configuring Task Home.")
        models = getattr(self._logic, "robotModelNodes", None)
        if not callable(models) or not models():
            raise ValueError("The local Step 6 robot model is unavailable.")
        base_issues = self._logic.step6BasePlacementFreshnessIssues(parameter_node)
        if base_issues:
            raise ValueError("The reviewed locked robot Base is not current: " + "; ".join(base_issues))

        foundation = self._logic.evaluateCaseFoundationEligibility(parameter_node)
        if not foundation.get("pose", {}).get("eligible"):
            raise ValueError(str(foundation.get("pose", {}).get("message") or "The current Case Foundation is not eligible."))
        if not foundation.get("base", {}).get("eligible"):
            raise ValueError(str(foundation.get("base", {}).get("message") or "The reviewed robot Base is not eligible."))
        snapshot = self._logic.buildCaseFoundationSnapshot(parameter_node)
        snapshot_data = snapshot.to_dict()
        snapshot_data.pop("task_home_configuration", None)
        snapshot_data.pop("environment_fingerprint", None)
        robot_profile = str(self._logic.robotProfileFingerprint() or "")
        base_fingerprint = str(self._logic.robotBaseFingerprint(parameter_node) or "")
        trajectory_revision = str(self._logic.step6TrajectoryRevision(parameter_node) or "")
        if not robot_profile or not base_fingerprint or not trajectory_revision:
            raise ValueError("The current robot profile, reviewed Base, or selected trajectory identity is incomplete.")

        registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
        branch_id = str(registry.get("selected_branch_id") or "")
        branches = registry.get("prepared_branches")
        if not branch_id or not isinstance(branches, Mapping) or branch_id not in branches:
            raise ValueError("Select a current verified PreparedBranch before configuring Task Home.")
        eligibility = self._logic.evaluatePreparedBranchEligibility(
            parameter_node, branch_id, registry=registry
        )
        if not eligibility.get("eligible"):
            raise ValueError(str(eligibility.get("message") or eligibility.get("reason") or "The selected PreparedBranch is stale."))
        branch = eligibility.get("branch")
        branch = branch if isinstance(branch, Mapping) else branches[branch_id]
        trajectory = parameter_node.trajectoryLine
        get_attribute = getattr(trajectory, "GetAttribute", None)
        trajectory_id = str(
            get_attribute(getattr(self._logic, "REGISTRY_TRAJECTORY_ID_ATTRIBUTE", "DENTOBOT.RegistryTrajectoryID"))
            or ""
        ) if callable(get_attribute) else ""
        if (
            not trajectory_id
            or trajectory_id != str(branch.get("primary_trajectory_id") or "")
            or trajectory_id not in tuple(str(value) for value in branch.get("trajectory_ids", ()))
        ):
            raise ValueError("The selected trajectory does not match the current PreparedBranch references.")

        base_identity = self._manual_base_review_identity(parameter_node, base)
        home_snapshot, _home_record = self._manual_task_home_record_snapshot(parameter_node)
        return {
            "setupMode": "offline",
            "parameterIdentity": base_identity["parameterNode"],
            "baseIdentity": base_identity,
            "caseIdentity": str(getattr(snapshot, "case_identity", "") or ""),
            "caseFoundationFingerprint": str(getattr(snapshot, "foundation_fingerprint", "") or ""),
            "caseFoundationSnapshot": fingerprint(snapshot_data),
            "branchId": branch_id,
            "branchRevision": str(branch.get("revision") or ""),
            "branchVerificationRevision": str(branch.get("verification_revision") or ""),
            "trajectoryId": trajectory_id,
            "trajectoryRevision": trajectory_revision,
            "baseFingerprint": base_fingerprint,
            "robotProfileFingerprint": robot_profile,
            "homeSnapshot": home_snapshot,
        }

    def _manual_task_home_candidate_within_mechanical_limits(self, candidate) -> None:
        paths = self._logic.robotDescriptionPaths()
        if not paths or not paths[0]:
            raise ValueError("The local robot URDF is unavailable for mechanical joint limits.")
        limits = default_task_joint_limits_from_urdf(paths[0])
        ranges = tuple(getattr(limits, name) for name in JOINT_LIMIT_FIELDS)
        for index, name in enumerate(JOINT_NAMES):
            display_value = (
                degrees(candidate[name])
                if JOINT_DISPLAY_UNITS[index] == "deg"
                else candidate[name] * 1000.0
            )
            minimum = float(ranges[index].minimum)
            maximum = float(ranges[index].maximum)
            if (
                not isfinite(display_value)
                or not isfinite(minimum)
                or not isfinite(maximum)
                or display_value < minimum
                or display_value > maximum
            ):
                raise ValueError(f"Task Home candidate {name} is outside the local robot's mechanical limits.")

    def _manual_task_home_configuration_ready(self, parameter_node, identity) -> bool:
        try:
            record = self._logic.taskHomeRecord(parameter_node)
            return bool(
                record is not None
                and record.base_fingerprint == identity.get("baseFingerprint")
                and record.robot_profile_fingerprint == identity.get("robotProfileFingerprint")
                and tuple(record.joint_names) == JOINT_NAMES
                and not self._logic.taskHomeFreshnessIssues(parameter_node)
            )
        except Exception:
            return False

    @staticmethod
    def _manual_task_home_offline_non_home_identity(identity):
        return {
            key: value
            for key, value in dict(identity or {}).items()
            if key != "homeSnapshot"
        }

    def _accept_manual_task_home_offline(self, parameter_node, review) -> RobotActionResult:
        candidate = review["candidateJointPositionsSi"]
        try:
            self._manual_task_home_candidate_within_mechanical_limits(candidate)
            identity_before = self._manual_task_home_offline_identity(parameter_node)
        except Exception as exc:
            message = _bounded_text(exc)
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_offline_identity_unavailable",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                message,
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        if identity_before != review.get("identity"):
            message = "The offline Task Home candidate is stale; cancel and review the current case and references again."
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_review_stale",
                "message": message,
                "identityBefore": deepcopy(review.get("identity")),
                "identityCurrent": deepcopy(identity_before),
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_stale",
                message,
                details=self._manual_task_home_review_details(identity_status="stale"),
            )

        before_home = deepcopy(identity_before["homeSnapshot"])
        expected_revision = (before_home.get("revision") or 0) + 1
        self._manual_task_home_acceptance_in_progress = True
        try:
            owner_error = ""
            try:
                self._logic.saveCurrentTaskHome(
                    parameter_node,
                    runtime_validation={"runtimeValidationStatus": "Unreviewed"},
                    joint_positions_si=dict(candidate),
                )
            except Exception as exc:
                owner_error = _bounded_text(exc)

            try:
                home_after, saved_home = self._manual_task_home_record_snapshot(parameter_node)
                saved_positions = (
                    dict(zip(saved_home.joint_names, saved_home.joint_positions_si))
                    if saved_home is not None
                    else None
                )
                exact_record = bool(
                    saved_home is not None
                    and saved_home.revision == expected_revision
                    and tuple(saved_home.joint_names) == JOINT_NAMES
                    and saved_positions == candidate
                    and saved_home.base_fingerprint == identity_before["baseFingerprint"]
                    and saved_home.robot_profile_fingerprint == identity_before["robotProfileFingerprint"]
                    and saved_home.runtime_validation_status == "Unreviewed"
                    and home_after["rawJsonFingerprint"] != before_home["rawJsonFingerprint"]
                )
                identity_after = self._manual_task_home_offline_identity(
                    parameter_node, allow_acceptance_in_progress=True
                )
                identity_matches = (
                    self._manual_task_home_offline_non_home_identity(identity_after)
                    == self._manual_task_home_offline_non_home_identity(identity_before)
                )
            except Exception as exc:
                home_after = {"rawJsonFingerprint": "", "recordFingerprint": "", "revision": None}
                saved_positions = None
                exact_record = False
                identity_after = None
                identity_matches = False
                readback_error = _bounded_text(exc)
            else:
                readback_error = ""

            write_may_have_occurred = bool(
                home_after.get("rawJsonFingerprint")
                != before_home.get("rawJsonFingerprint")
            ) or identity_after is None
            authority_invalidation_error = ""
            if write_may_have_occurred:
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                self._runtime_validated_workspace_key = ""
                try:
                    self.invalidateWorkspaceRuntimeValidation()
                except Exception as exc:
                    authority_invalidation_error = _bounded_text(exc)
                    try:
                        self.invalidateMotionPlan()
                    except Exception as cleanup_exc:
                        authority_invalidation_error += "; plan invalidation failed: " + _bounded_text(cleanup_exc)

            if (
                not exact_record
                or not identity_matches
                or bool(owner_error)
                or bool(authority_invalidation_error)
            ):
                unknown = write_may_have_occurred or bool(authority_invalidation_error)
                code = "manual_task_home_acceptance_unknown" if unknown else "manual_task_home_review_rejected"
                message = (
                    "Offline Task Home write outcome is uncertain; retain the candidate and resolve the saved record before retrying."
                    if unknown
                    else owner_error or "The saved Task Home record did not match the reviewed offline candidate."
                )
                self._manual_task_home_review_status = "unknown" if unknown else "rejected"
                if unknown:
                    self._manual_task_home_acceptance_uncertain = message
                self._manual_task_home_review_failure = {
                    "code": code,
                    "message": message,
                    "ownerError": owner_error,
                    "readbackError": readback_error,
                    "authorityInvalidationError": authority_invalidation_error,
                    "identityBefore": deepcopy(identity_before),
                    "identityAfter": deepcopy(identity_after),
                    "homeBefore": before_home,
                    "homeAfter": home_after,
                    "candidateJointPositionsSi": dict(candidate),
                    "savedJointPositionsSi": saved_positions,
                    "exactSavedRecord": exact_record,
                }
                return RobotActionResult(
                    False,
                    code,
                    message,
                    details=self._manual_task_home_review_details(
                        identity_status="unknown" if unknown else "current"
                    ),
                )

            self._manual_task_home_review = None
            self._manual_task_home_review_failure = None
            self._manual_task_home_review_status = "configuration_saved"
            self._manual_task_home_acceptance_uncertain = ""
            result_details = self._manual_task_home_review_details(identity_status="current")
            result_details.update(
                {
                    "setupMode": "offline",
                    "configurationReady": True,
                    "runtimeValidated": False,
                    "acceptanceStatus": "configuration_saved",
                    "homeConfigurationSaveResult": {
                        "revision": expected_revision,
                        "acknowledgementReceived": not bool(owner_error),
                        "exactRecordReadback": True,
                    },
                }
            )
            return RobotActionResult(
                True,
                "manual_task_home_configuration_saved",
                "Saved the reviewed Task Home configuration for the current offline Base; live runtime validation remains pending.",
                details=result_details,
                payload=saved_home,
            )

        finally:
            self._manual_task_home_acceptance_in_progress = False

    @staticmethod
    def _manual_task_home_acknowledged_object_ids(audit, object_count):
        acknowledgement = getattr(audit, "runtime_acknowledgement", None)
        if (
            getattr(audit, "status", None) != "Acknowledged"
            or not isinstance(acknowledgement, Mapping)
            or acknowledgement.get("status") != "Acknowledged"
        ):
            return None
        raw_ids = acknowledgement.get("acknowledged_object_ids")
        if (
            not isinstance(raw_ids, (tuple, list))
            or any(not isinstance(value, str) or not value for value in raw_ids)
        ):
            return None
        ids = tuple(sorted(raw_ids))
        if not ids or len(set(ids)) != len(ids) or len(ids) != object_count:
            return None
        return ids

    def _manual_task_home_review_details(self, *, identity_status="unknown"):
        review = self._manual_task_home_review or {}
        try:
            parameter_node = self._require_context()
            setup_mode = self._manual_task_home_setup_mode(parameter_node)
        except Exception:
            parameter_node = None
            setup_mode = "unknown"
        accepted = (
            self._manual_task_home_accepted_positions()
            if setup_mode == "connected"
            else None
        )
        configured = None
        configuration_ready = False
        try:
            record = self._logic.taskHomeRecord(parameter_node) if parameter_node is not None else None
            if record is not None:
                configured = dict(zip(record.joint_names, record.joint_positions_si))
            if setup_mode == "offline" and parameter_node is not None:
                identity = self._manual_task_home_offline_identity(parameter_node)
                configuration_ready = self._manual_task_home_configuration_ready(
                    parameter_node, identity
                )
            elif setup_mode == "connected" and parameter_node is not None:
                configuration_ready = bool(
                    record is not None
                    and not self._logic.taskHomeFreshnessIssues(parameter_node)
                )
        except Exception:
            configuration_ready = False
        try:
            runtime_validated = bool(
                self.taskHomeRuntimeValidated(parameter_node)
            ) if setup_mode == "connected" and parameter_node is not None else False
        except Exception:
            runtime_validated = False
        acceptance_status = (
            "unknown"
            if self._manual_task_home_acceptance_uncertain
            else self._manual_task_home_review_status
        )
        if (
            setup_mode == "connected"
            and self._manual_task_home_review is None
            and acceptance_status == "configuration_saved"
        ):
            acceptance_status = "review"
        details = {
            "staged": self._manual_task_home_review is not None,
            "setupMode": setup_mode,
            "candidateSetupMode": str(review.get("setupMode") or ""),
            "candidateJointPositionsSi": deepcopy(
                (self._manual_task_home_review or {}).get("candidateJointPositionsSi")
            ),
            "acceptedJointPositionsSi": accepted,
            "configuredJointPositionsSi": configured,
            "configurationReady": bool(configuration_ready),
            "runtimeValidated": runtime_validated,
            "identityStatus": str(identity_status),
            "acceptanceStatus": acceptance_status,
        }
        if self._manual_task_home_review_failure is not None:
            details["failureEvidence"] = deepcopy(self._manual_task_home_review_failure)
        if self._manual_task_home_acceptance_uncertain:
            details["acceptanceUncertainty"] = self._manual_task_home_acceptance_uncertain
        return details

    def manualTaskHomeReview(self) -> RobotActionResult:
        """Read the detached J1–J5 candidate and current Home setup state."""

        try:
            parameter_node = self._require_context()
            setup_mode = self._manual_task_home_setup_mode(parameter_node)
            review = self._manual_task_home_review
            if review is not None and review.get("setupMode") != setup_mode:
                return RobotActionResult(
                    False,
                    "manual_task_home_review_stale",
                    "The staged Task Home candidate belongs to another setup mode; cancel it before reviewing again.",
                    details=self._manual_task_home_review_details(identity_status="stale"),
                )
            identity = (
                self._manual_task_home_offline_identity(parameter_node)
                if setup_mode == "offline"
                else self._manual_jog_current_identity(
                    parameter_node, for_task_home_review=True
                )
            )
        except Exception as exc:
            return RobotActionResult(
                False,
                "manual_task_home_review_unavailable",
                _bounded_text(exc),
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        review = self._manual_task_home_review
        current = review is None or identity == review["identity"]
        identity_status = "current" if current else "stale"
        return RobotActionResult(
            current,
            "manual_task_home_review_current" if current else "manual_task_home_review_stale",
            "Detached Task Home candidate is current."
            if current
            else "Detached Task Home candidate is stale; cancel it before staging a new candidate.",
            details=self._manual_task_home_review_details(identity_status=identity_status),
        )

    def stageManualTaskHomeReview(self, joint_positions_si) -> RobotActionResult:
        """Stage a finite detached J1–J5 candidate without publishing or changing Home."""

        try:
            candidate = self._manual_task_home_review_vector(joint_positions_si)
            parameter_node = self._require_context()
            setup_mode = self._manual_task_home_setup_mode(parameter_node)
            existing_review = self._manual_task_home_review
            if existing_review is not None and existing_review.get("setupMode") != setup_mode:
                return RobotActionResult(
                    False,
                    "manual_task_home_review_stale",
                    "The existing Task Home candidate belongs to another setup mode; cancel it before staging a new candidate.",
                    details=self._manual_task_home_review_details(identity_status="stale"),
                )
            if setup_mode == "offline":
                self._manual_task_home_candidate_within_mechanical_limits(candidate)
                identity = self._manual_task_home_offline_identity(parameter_node)
            else:
                identity = self._manual_jog_current_identity(
                    parameter_node, for_task_home_review=True
                )
        except Exception as exc:
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                _bounded_text(exc),
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "Task Home acceptance is already in progress.",
                details=self._manual_task_home_review_details(identity_status="current"),
            )
        if self._manual_task_home_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_task_home_acceptance_unknown",
                self._manual_task_home_acceptance_uncertain,
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        review = self._manual_task_home_review
        if review is not None and identity != review["identity"]:
            return RobotActionResult(
                False,
                "manual_task_home_review_stale",
                "The existing Task Home candidate is stale; cancel it before staging a candidate for the current identity.",
                details=self._manual_task_home_review_details(identity_status="stale"),
            )
        self._manual_task_home_review = {
            "identity": dict(identity),
            "candidateJointPositionsSi": candidate,
            "setupMode": setup_mode,
        }
        self._manual_task_home_review_status = "review"
        self._manual_task_home_review_failure = None
        return RobotActionResult(
            True,
            "manual_task_home_review_staged",
            "Staged a detached J1–J5 Task Home candidate; the accepted robot and saved Home are unchanged.",
            details=self._manual_task_home_review_details(identity_status="current"),
        )

    def cancelManualTaskHomeReview(self) -> RobotActionResult:
        """Clear only the detached candidate and retain acceptance evidence."""

        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "Task Home acceptance is already in progress.",
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        if self._manual_task_home_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_task_home_acceptance_unknown",
                self._manual_task_home_acceptance_uncertain,
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        self._manual_task_home_review = None
        return RobotActionResult(
            True,
            "manual_task_home_review_cancelled",
            "Cleared the detached Task Home candidate.",
            details=self._manual_task_home_review_details(identity_status="current"),
        )

    def acceptManualTaskHomeReview(self) -> RobotActionResult:
        """Accept only the already-current pose through the existing live Home owner."""

        review = self._manual_task_home_review
        if review is None:
            return RobotActionResult(
                False,
                "manual_task_home_review_missing",
                "Stage a detached Task Home candidate before accepting it.",
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "Task Home acceptance is already in progress.",
                details=self._manual_task_home_review_details(identity_status="current"),
            )
        if self._manual_task_home_acceptance_uncertain:
            return RobotActionResult(
                False,
                "manual_task_home_acceptance_unknown",
                self._manual_task_home_acceptance_uncertain,
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        if self._manual_jog_reconciliation_required or self._manual_jog_in_progress:
            message = "Resolve the outstanding manual jog before accepting Task Home."
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_jog_reconciliation_required",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                message,
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        try:
            parameter_node = self._require_context()
            setup_mode = self._manual_task_home_setup_mode(parameter_node)
            if review.get("setupMode") != setup_mode:
                message = "The staged Task Home candidate belongs to another setup mode; cancel it before accepting it."
                self._manual_task_home_review_status = "rejected"
                self._manual_task_home_review_failure = {
                    "code": "manual_task_home_review_stale",
                    "message": message,
                    "candidateSetupMode": str(review.get("setupMode") or ""),
                    "setupMode": setup_mode,
                }
                return RobotActionResult(
                    False,
                    "manual_task_home_review_stale",
                    message,
                    details=self._manual_task_home_review_details(identity_status="stale"),
                )
            if setup_mode == "offline":
                return self._accept_manual_task_home_offline(parameter_node, review)
            identity = self._manual_jog_current_identity(
                parameter_node, for_task_home_review=True
            )
        except Exception as exc:
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_identity_unavailable",
                "message": _bounded_text(exc),
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                _bounded_text(exc),
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        if identity != review["identity"]:
            message = "The staged Task Home candidate is stale; cancel and review the current identity again."
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_review_stale",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_stale",
                message,
                details=self._manual_task_home_review_details(identity_status="stale"),
            )

        candidate = review["candidateJointPositionsSi"]
        accepted = self._manual_task_home_accepted_positions()
        monitored_reader = getattr(self._bridge, "monitored_joint_positions_si", None)
        try:
            monitored = (
                self._manual_task_home_review_vector(monitored_reader())
                if callable(monitored_reader)
                else None
            )
            displayed_state = self.currentRobotState().joint_positions_si
            displayed = self._manual_task_home_review_vector(
                {name: displayed_state[name] for name in JOINT_NAMES}
            )
        except Exception:
            monitored = None
            displayed = None
        vectors = (accepted, monitored, displayed)
        tolerance = 1.0e-12
        if any(vector is None for vector in vectors):
            message = "The accepted, monitored, or displayed J1–J5 state is unavailable; Task Home was not saved."
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_state_unavailable",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                message,
                details=self._manual_task_home_review_details(identity_status="current"),
            )
        if any(
            abs(candidate[name] - accepted[name]) > tolerance
            for name in JOINT_NAMES
        ):
            message = "The candidate differs from the accepted robot pose; perform a separately guarded individual jog first."
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_candidate_requires_jog",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                message,
                details=self._manual_task_home_review_details(identity_status="current"),
            )
        if any(
            abs(candidate[name] - current[name]) > tolerance
            for current in (monitored, displayed)
            for name in JOINT_NAMES
        ):
            message = "The candidate does not match both monitored and displayed J1–J5 state; Task Home was not saved."
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_state_mismatch",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                message,
                details=self._manual_task_home_review_details(identity_status="current"),
            )

        home_identity_before = identity.get("home", "")
        try:
            home_before, previous_home = self._manual_task_home_record_snapshot(
                parameter_node
            )
            non_home_identity = self._manual_task_home_non_home_identity(identity)
        except Exception as exc:
            message = "Could not freeze the pre-save Task Home identity: " + _bounded_text(exc)
            self._manual_task_home_review_status = "rejected"
            self._manual_task_home_review_failure = {
                "code": "manual_task_home_freeze_failed",
                "message": message,
            }
            return RobotActionResult(
                False,
                "manual_task_home_review_rejected",
                message,
                details=self._manual_task_home_review_details(identity_status="unknown"),
            )
        expected_revision = (
            1
            if previous_home is None
            else home_before["revision"] + 1
            if home_before["revision"] is not None
            else None
        )
        acceptance_freeze = {
            "candidateJointPositionsSi": dict(candidate),
            "nonHomeIdentity": non_home_identity,
            "homeBefore": home_before,
            "expectedRevision": expected_revision,
        }
        self._manual_task_home_acceptance_in_progress = True
        try:
            try:
                owner_result = self.saveTaskHome()
            except Exception as exc:
                owner_result = RobotActionResult(False, "task_home_failed", _bounded_text(exc))
        finally:
            self._manual_task_home_acceptance_in_progress = False

        if owner_result.success and owner_result.code == "task_home_saved":
            self._manual_task_home_review = None
            self._manual_task_home_review_failure = None
            self._manual_task_home_review_status = "accepted"
            self._manual_task_home_acceptance_uncertain = ""
            return RobotActionResult(
                True,
                "manual_task_home_review_accepted",
                owner_result.message,
                details={
                    **self._manual_task_home_review_details(identity_status="current"),
                    "homeAcceptanceResult": {
                        "code": owner_result.code,
                        "details": deepcopy(owner_result.details),
                    },
                },
                payload=owner_result.payload,
            )

        try:
            identity_after = self._manual_jog_current_identity(
                parameter_node, for_task_home_review=True
            )
            identity_status = "current" if identity_after == identity else "stale"
            home_identity_after = identity_after.get("home", "")
        except Exception as exc:
            identity_after = None
            identity_status = "unknown"
            home_identity_after = None
            identity_error = _bounded_text(exc)
        else:
            identity_error = ""
        try:
            home_after, _current_home = self._manual_task_home_record_snapshot(
                parameter_node
            )
            home_snapshot_error = ""
        except Exception as exc:
            home_after = {
                "rawJsonFingerprint": fingerprint(
                    {"rawJson": str(parameter_node.step6TaskHomeJson or "")}
                ),
                "recordFingerprint": "",
                "revision": None,
            }
            home_snapshot_error = _bounded_text(exc)
        may_have_committed = (
            home_identity_after is None
            or home_identity_after != home_identity_before
            or home_after["rawJsonFingerprint"] != home_before["rawJsonFingerprint"]
        )
        code = "manual_task_home_acceptance_unknown" if may_have_committed else "manual_task_home_review_rejected"
        message = (
            "Task Home save did not return a successful owner acknowledgement, and Home state may have changed; retain this candidate for manual reconciliation."
            if may_have_committed
            else owner_result.message or "The Task Home owner rejected the candidate."
        )
        self._manual_task_home_review_status = "unknown" if may_have_committed else "rejected"
        if may_have_committed:
            self._manual_task_home_acceptance_uncertain = message
        self._manual_task_home_review_failure = {
            "code": owner_result.code,
            "message": _bounded_text(owner_result.message),
            "ownerDetails": deepcopy(owner_result.details),
            "homeIdentityBefore": home_identity_before,
            "homeIdentityAfter": home_identity_after,
            "reconciliationFreeze": {
                **acceptance_freeze,
                "homeAfter": home_after,
                "homeSnapshotError": home_snapshot_error,
            },
            "identityAfter": deepcopy(identity_after),
            "identityError": identity_error,
        }
        return RobotActionResult(
            False,
            code,
            message,
            details=self._manual_task_home_review_details(identity_status=identity_status),
        )

    def reconcileManualTaskHomeAcceptance(self) -> RobotActionResult:
        """Clear an uncertain Home save only after read-only native proof."""

        reconciliation: dict[str, object] = {"simulationOnly": True, "routeAuthority": "none"}

        def finish(code, message, success=False, identity_status="unknown"):
            details = self._manual_task_home_review_details(identity_status=identity_status)
            details.update(deepcopy(reconciliation))
            return RobotActionResult(success, code, message, details=details)

        if not self._manual_task_home_acceptance_uncertain:
            return finish(
                "manual_task_home_reconciliation_not_required",
                "There is no uncertain Task Home save to reconcile.",
            )

        def unresolved(code, message, identity_status="unknown"):
            evidence = deepcopy(self._manual_task_home_review_failure or {})
            evidence["reconciliationFailure"] = {
                "code": code,
                "message": _bounded_text(message),
            }
            self._manual_task_home_review_failure = evidence
            self._manual_task_home_review_status = "unknown"
            return finish(
                "manual_task_home_acceptance_unknown", message, identity_status=identity_status
            )

        if (
            isinstance(self._manual_task_home_review, Mapping)
            and self._manual_task_home_review.get("setupMode") == "offline"
        ):
            return unresolved(
                "offline_task_home_configuration_unknown",
                "Offline Task Home writes cannot be reconciled through connected native-state evidence; retain the saved-record evidence for explicit resolution.",
            )

        if self._manual_task_home_acceptance_in_progress:
            return unresolved(
                "manual_task_home_review_busy",
                "Task Home acceptance is already in progress.",
            )
        if self._manual_jog_in_progress or self._manual_jog_reconciliation_required:
            return unresolved(
                "manual_jog_reconciliation_required",
                "Resolve the outstanding manual jog before reconciling Task Home.",
            )
        if (
            self.previewActive
            or self._guarded_preview_active
            or self._incomplete_preview_evidence is not None
            or self._motion_plan is not None
            or self._completed_phase
            or self._phase_sequence
            or self._phase_guard_session_id
        ):
            return unresolved(
                "manual_task_home_phase_active",
                "Stop and resolve the active preview or phase before reconciling Task Home.",
            )

        review = self._manual_task_home_review
        evidence = self._manual_task_home_review_failure
        frozen = evidence.get("reconciliationFreeze") if isinstance(evidence, Mapping) else None
        try:
            if not isinstance(review, Mapping) or not isinstance(frozen, Mapping):
                raise ValueError("The staged candidate or pre-save Home evidence is unavailable.")
            candidate = self._manual_task_home_review_vector(
                review.get("candidateJointPositionsSi")
            )
            frozen_candidate = self._manual_task_home_review_vector(
                frozen.get("candidateJointPositionsSi")
            )
            expected_identity = self._manual_task_home_non_home_identity(
                frozen.get("nonHomeIdentity")
            )
            home_before = frozen.get("homeBefore")
            expected_revision = frozen.get("expectedRevision")
            if candidate != frozen_candidate or not isinstance(home_before, Mapping):
                raise ValueError("The staged candidate no longer matches its frozen acceptance evidence.")
            if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
                raise ValueError("The expected next Task Home revision is unavailable.")
        except Exception as exc:
            return unresolved("manual_task_home_reconciliation_evidence_missing", _bounded_text(exc))

        self._manual_task_home_acceptance_in_progress = True
        self._manual_task_home_reconciliation_in_progress = True
        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) != "case":
                return unresolved("manual_task_home_reconciliation_stale", "A current case scene is required.")
            if self._manual_jog_in_progress or self._manual_jog_reconciliation_required:
                return unresolved("manual_jog_reconciliation_required", "Resolve the outstanding manual jog before reconciling Task Home.")

            identity_before = self._manual_task_home_non_home_identity(
                self._manual_jog_current_identity(
                    parameter_node, for_task_home_review=True
                )
            )
            if identity_before != expected_identity:
                return unresolved(
                    "manual_task_home_reconciliation_stale",
                    "Branch, Base, trajectory, profile, scene, or limits changed since the uncertain save.",
                    "stale",
                )

            home_before_query, saved_home = self._manual_task_home_record_snapshot(parameter_node)
            if (
                saved_home is None
                or home_before_query["rawJsonFingerprint"] == home_before.get("rawJsonFingerprint")
                or home_before_query["recordFingerprint"] == home_before.get("recordFingerprint")
                or home_before_query["recordFingerprint"] == ""
                or home_before_query["revision"] != expected_revision
            ):
                return unresolved(
                    "manual_task_home_record_uncommitted",
                    "The saved Task Home does not prove the expected new revision; acceptance remains unknown.",
                )

            audit_before = self._logic.collisionSceneAuditRecord(parameter_node)
            object_ids_before = self._manual_task_home_acknowledged_object_ids(
                audit_before, self._planning_scene_object_count
            )
            audit_fingerprint = str(getattr(audit_before, "audit_fingerprint", "") or "")
            guard_policy_fingerprint = self._strict_guard_policy_fingerprint()
            saved_positions = self._manual_task_home_review_vector(
                dict(zip(saved_home.joint_names, saved_home.joint_positions_si))
            )
            if (
                not self._planning_scene_synchronized
                or self._planning_scene_object_count <= 0
                or object_ids_before is None
                or not audit_fingerprint
                or not guard_policy_fingerprint
                or saved_positions != candidate
                or saved_home.runtime_validation_status != "Validated"
                or saved_home.base_fingerprint != self._logic.robotBaseFingerprint(parameter_node)
                or saved_home.robot_profile_fingerprint != self._logic.robotProfileFingerprint()
                or saved_home.collision_audit_fingerprint != audit_fingerprint
                or saved_home.guard_policy_fingerprint != guard_policy_fingerprint
                or saved_home.world_object_count != self._planning_scene_object_count
            ):
                return unresolved(
                    "manual_task_home_saved_record_invalid",
                    "The new Task Home is not validated for the current Base, profile, acknowledged scene, and strict guard policy.",
                )

            query_id = uuid4().hex
            session_id = uuid4().hex
            reconciliation.update(requestId=query_id, sessionId=session_id)
            query = getattr(self._bridge, "query_manual_joint_state_si", None)
            if not callable(query):
                return unresolved(
                    "manual_task_home_reconciliation_unavailable",
                    "The read-only native accepted-state query is unavailable.",
                )
            try:
                status, query_message = query(candidate, query_id, session_id)
            except Exception as exc:
                status, query_message = None, f"Native state query failed: {exc}"
            if status is None:
                return unresolved(
                    "manual_task_home_reconciliation_unknown",
                    query_message or "The native read-only query returned no correlated state.",
                )
            requested = None
            accepted = None
            try:
                requested = self._manual_task_home_review_vector(
                    getattr(status, "requested_positions", None)
                )
                accepted = self._manual_task_home_review_vector(
                    getattr(status, "accepted_positions", None)
                )
            except Exception:
                pass
            objects = tuple(getattr(status, "world_objects", ()) or ())
            world_count = getattr(status, "world_object_count", None)
            native_ids = tuple(
                sorted(
                    item["id"]
                    for item in objects
                    if isinstance(item, Mapping)
                    and isinstance(item.get("id"), str)
                    and item["id"]
                )
            )
            world_evidence = getattr(status, "world_object_evidence_present", False) is True
            world_objects_valid = (
                isinstance(world_count, int)
                and not isinstance(world_count, bool)
                and len(objects) == world_count
                and all(
                    isinstance(item, Mapping)
                    and isinstance(item.get("id"), str)
                    and bool(item["id"])
                    for item in objects
                )
                and len(set(native_ids)) == len(native_ids)
            )
            native_proof = {
                "operation": getattr(status, "operation", None),
                "queryOnly": getattr(status, "query_only", None),
                "requestId": str(getattr(status, "request_id", "") or ""),
                "sessionId": str(getattr(status, "session_id", "") or ""),
                "policyId": str(getattr(status, "policy_id", "") or ""),
                "commandValid": getattr(status, "command_valid", None),
                "staticStateValid": getattr(status, "accepted", None),
                "requestedPositionsSi": requested,
                "acceptedPositionsSi": accepted,
                "worldObjectCount": world_count,
                "worldObjectEvidencePresent": world_evidence,
                "worldObjectIds": native_ids,
                "collisionScenePolicyFingerprint": str(
                    getattr(status, "collision_scene_policy_fingerprint", "") or ""
                ),
            }
            reconciliation["nativeGuardEvidence"] = native_proof
            if not (
                status is not None
                and native_proof["operation"] == "state_query"
                and native_proof["queryOnly"] is True
                and native_proof["requestId"] == query_id
                and native_proof["sessionId"] == session_id
                and native_proof["policyId"] == MANUAL_JOINT_POLICY_ID
                and native_proof["commandValid"] is True
                and native_proof["staticStateValid"] is True
                and requested == candidate
                and accepted == candidate
            ):
                return unresolved(
                    "manual_task_home_native_state_mismatch",
                    query_message or "Native accepted J1–J5 state did not exactly match the staged candidate.",
                )
            if (
                not world_evidence
                or not world_objects_valid
                or world_count != self._planning_scene_object_count
                or native_ids != object_ids_before
            ):
                return unresolved(
                    "manual_task_home_scene_mismatch",
                    "Native and acknowledged collision-scene object IDs or counts do not match.",
                )

            wait_for_state = getattr(
                self._bridge, "wait_for_monitored_joint_positions_si", None
            )
            if not callable(wait_for_state):
                return unresolved(
                    "manual_task_home_monitor_unavailable",
                    "The fresh ROS/MoveIt monitored-state reader is unavailable.",
                )
            try:
                monitored_result = wait_for_state(candidate)
            except Exception as exc:
                return unresolved(
                    "manual_task_home_monitor_mismatch",
                    f"Monitored-state read failed: {exc}",
                )
            if not isinstance(monitored_result, (tuple, list)) or len(monitored_result) != 4:
                return unresolved(
                    "manual_task_home_monitor_mismatch",
                    "The monitored-state reader returned an invalid response.",
                )
            monitored_ok, monitored_message, monitored, monitored_error = monitored_result
            try:
                monitored_positions = self._manual_task_home_review_vector(monitored)
            except Exception:
                monitored_positions = None
            if (
                monitored_ok is not True
                or monitored_positions != candidate
                or isinstance(monitored_error, bool)
                or not isinstance(monitored_error, Real)
                or not isfinite(float(monitored_error))
                or float(monitored_error) > 1.0e-12
            ):
                return unresolved(
                    "manual_task_home_monitor_mismatch",
                    str(monitored_message or "Fresh monitored state did not exactly match the staged candidate."),
                )
            reconciliation["monitoredJointPositionsSi"] = dict(monitored_positions)
            reconciliation["monitoredMaximumError"] = float(monitored_error)

            try:
                displayed_state = self.currentRobotState().joint_positions_si
                displayed = self._manual_task_home_review_vector(
                    {name: displayed_state[name] for name in JOINT_NAMES}
                )
            except Exception as exc:
                return unresolved(
                    "manual_task_home_display_mismatch",
                    f"Displayed current state is unavailable: {exc}",
                )
            if displayed != candidate:
                return unresolved(
                    "manual_task_home_display_mismatch",
                    "Displayed current J1–J5 state does not exactly match the staged candidate.",
                )

            identity_after = self._manual_task_home_non_home_identity(
                self._manual_jog_current_identity(
                    parameter_node, for_task_home_review=True
                )
            )
            home_after_query, queried_home = self._manual_task_home_record_snapshot(parameter_node)
            audit_after = self._logic.collisionSceneAuditRecord(parameter_node)
            object_ids_after = self._manual_task_home_acknowledged_object_ids(
                audit_after, self._planning_scene_object_count
            )
            if (
                identity_after != expected_identity
                or identity_after != identity_before
                or queried_home is None
                or home_after_query != home_before_query
                or object_ids_after != object_ids_before
                or str(getattr(audit_after, "audit_fingerprint", "") or "")
                != audit_fingerprint
                or self._strict_guard_policy_fingerprint() != guard_policy_fingerprint
                or self._manual_jog_in_progress
                or self._manual_jog_reconciliation_required
                or self.previewActive
                or self._guarded_preview_active
                or self._incomplete_preview_evidence is not None
                or self._motion_plan is not None
                or self._completed_phase
                or self._phase_sequence
                or self._phase_guard_session_id
            ):
                return unresolved(
                    "manual_task_home_reconciliation_stale",
                    "Identity, saved Home, acknowledged scene, or guard policy changed during the read-only query.",
                    "stale",
                )

            commit = getattr(
                self._bridge, "accept_manual_joint_state_reconciliation", None
            )
            if not callable(commit):
                return unresolved(
                    "manual_task_home_reconciliation_unavailable",
                    "The bridge cannot commit a verified read-only reconciliation.",
                )
            try:
                committed = commit(status, candidate, query_id, session_id)
            except Exception as exc:
                committed = (False, f"Could not commit reconciled Home state: {exc}")
            if not (
                isinstance(committed, (tuple, list))
                and len(committed) == 2
                and committed[0] is True
            ):
                message = (
                    str(committed[1])
                    if isinstance(committed, (tuple, list)) and len(committed) == 2
                    else "Could not commit reconciled Home state."
                )
                return unresolved("manual_task_home_reconciliation_unknown", message)

            self._runtime_validated_task_home_key = self._task_home_runtime_key(queried_home)
            self._runtime_task_home_evidence = {
                "jointPositionsSi": dict(candidate),
                "monitoredJointPositionsSi": dict(monitored_positions),
                "maximumJointError": float(monitored_error),
                "minimumClearanceMm": getattr(queried_home, "minimum_clearance_mm", None),
                "worldObjectCount": queried_home.world_object_count,
            }
            self._manual_task_home_review = None
            self._manual_task_home_review_status = "reconciled"
            self._manual_task_home_acceptance_uncertain = ""
            reconciliation["homeRevision"] = queried_home.revision
            reconciliation["acceptedJointPositionsSi"] = dict(candidate)
            return finish(
                "manual_task_home_reconciled",
                "The saved Task Home, native accepted state, monitored state, and displayed state were reconciled.",
                success=True,
                identity_status="current",
            )
        except Exception as exc:
            return unresolved(
                "manual_task_home_reconciliation_unknown",
                "Task Home reconciliation proof was unavailable: " + _bounded_text(exc),
            )
        finally:
            self._manual_task_home_acceptance_in_progress = False
            self._manual_task_home_reconciliation_in_progress = False

    def saveTaskHome(self) -> RobotActionResult:
        """Persist a live, collision-accepted, monitored pose as Task Home."""

        if self._manual_task_home_reconciliation_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "Task Home reconciliation is in progress.",
            )
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Saving Task Home is blocked because a guarded preview stopped before endpoint verification.",
            )
        try:
            parameter_node = self._require_context()
            record_unavailable = self._manual_simulation_prepare_current_identity()
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
            state_validity = self._checkStateValidity()
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
            self._robot_away_from_home = False
            result = RobotActionResult(
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
            accepted_fingerprint = fingerprint(record.to_dict())
            accepted_joints = dict(candidate_positions)
            event_details = {
                "accepted_fingerprint": accepted_fingerprint,
                "guard_policy_fingerprint": (
                    str(record.guard_policy_fingerprint or "unknown")
                ),
            }
            return self._manual_simulation_finish_acceptance(
                result,
                review_event={
                    "kind": "review_task_home",
                    "monotonic_ns": monotonic_ns(),
                    "requested_joints": accepted_joints,
                    "details": {
                        "guard_policy_fingerprint": event_details[
                            "guard_policy_fingerprint"
                        ],
                    },
                },
                acceptance_event={
                    "kind": "accept_task_home",
                    "monotonic_ns": monotonic_ns(),
                    "accepted_joints": accepted_joints,
                    "details": event_details,
                },
                unavailable_reason=(
                    "Task Home was saved successfully, but no complete "
                    "pre-commit recording identity was available. " + record_unavailable
                ),
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "task_home_failed", str(exc))

    def applyTaskHomeDraft(self, joint_positions_si: Mapping[str, float]) -> RobotActionResult:
        """Plan/apply a captured Home draft without saving or validating Home."""
        details = {"simulationOnly": True, "runtimeValidated": False,
                   "homeSaved": False, "appliedWaypointCount": 0}
        identity = None
        submitted = False

        def finish(success, code, message):
            details["manualJogReconciliationRequired"] = self._manual_jog_reconciliation_required
            if self._manual_jog_reconciliation_required:
                message += " Use Reconcile State in 6.3 Manual before further Home actions."
            return RobotActionResult(success, code, message, details=dict(details))

        if (self._manual_jog_in_progress or self._manual_jog_reconciliation_required
                or self._manual_task_home_acceptance_in_progress
                or self._manual_task_home_acceptance_uncertain):
            return finish(False, "task_home_draft_busy",
                          "Cancel the Home review or reconcile outstanding state before applying a new Home draft.")
        try:
            if not isinstance(joint_positions_si, Mapping) or set(joint_positions_si) != set(JOINT_NAMES):
                raise ValueError("A Home draft requires exactly the five canonical J1–J5 SI values.")
            if any(isinstance(value, bool) or not isfinite(float(value)) for value in joint_positions_si.values()):
                raise ValueError("Home draft joint values must be finite SI numbers.")
            goal = {name: float(joint_positions_si[name]) for name in JOINT_NAMES}
            parameter_node = self._require_context()
            identity = self._manual_jog_current_identity(parameter_node, for_task_home_review=True)
            review = self._manual_task_home_review
            if review is not None and (
                review.get("identity") != identity or review.get("setupMode") != "connected"
                or self._manual_task_home_review_status != "review"
                or review.get("candidateJointPositionsSi") != goal
            ):
                raise ValueError("The Home draft differs from its current review; cancel and review the exact draft again.")
            start = self._bridge.monitored_joint_positions_si()
            accepted = self._bridge.last_accepted_joint_positions_si()
            displayed = self.currentRobotState().joint_positions_si
            if any(not isinstance(vector, Mapping) or set(vector) != set(JOINT_NAMES)
                   or any(isinstance(v, bool) or not isfinite(float(v)) for v in vector.values())
                   for vector in (start, accepted, displayed)):
                raise ValueError("A complete finite accepted, monitored and displayed start state is required.")
            if not all(self._joint_positions_match(start, positions)[0] for positions in (accepted, displayed)):
                raise ValueError("Accepted, monitored and displayed robot state must agree before Home-draft planning.")
            details.update(requestedJointPositionsSi=dict(goal), monitoredStartJointPositionsSi=dict(start))
            self._manual_jog_in_progress = True
            # Already at the draft (e.g. it was applied, then Plan + Apply pressed
            # again): MoveIt rightly rejects an equal start/goal, so re-apply only
            # the exact draft as one guarded waypoint, as applyTaskHome does.
            already_at_draft = self._joint_positions_match(goal, start)[0]
            if already_at_draft and all(abs(start[name] - goal[name]) <= 1.0e-12 for name in JOINT_NAMES):
                details["alreadyAtDraft"] = True  # exact: no motion, validation state untouched
                return finish(True, "task_home_draft_applied",
                              "The robot is already exactly at the Home draft; nothing was planned "
                              "or applied. Review and Accept & Validate to save it as Task Home.")
            if already_at_draft:
                details["alreadyAtDraft"] = True
                waypoints = (dict(goal),)
            else:
                plan = self._bridge.plan_moveit_joint_goal(
                    start_joint_positions_si=start, goal_joint_positions_si=goal,
                    planner_id=STEP6_JOINT_PLANNER_ID,
                    planner_context="monitored_current_to_task_home_draft",
                )
                if not plan.success or not plan.waypoint_joint_vectors_si:
                    return finish(False, "task_home_draft_moveit_plan_failed",
                                  "MoveIt could not plan from the monitored state to the Home draft. " + plan.message)
                waypoints = tuple(plan.waypoint_joint_vectors_si)
                for waypoint in waypoints:
                    if (not isinstance(waypoint, Mapping) or set(waypoint) != set(JOINT_NAMES)
                            or any(isinstance(v, bool) or not isfinite(float(v)) for v in waypoint.values())):
                        raise ValueError("MoveIt returned an incomplete or nonfinite Home-draft waypoint.")
                # MoveIt ends inside its joint-goal tolerance (~1e-4), never exactly on
                # the goal, yet Accept needs the accepted state to equal the draft.
                # Snap with one extra final waypoint; it is guarded like all others.
                final_error = max(abs(float(waypoints[-1][name]) - goal[name]) for name in JOINT_NAMES)
                if final_error > HOME_DRAFT_SNAP_TOLERANCE_SI:
                    raise ValueError(
                        f"MoveIt ended {final_error:.3g} (SI units) from the requested Home "
                        "draft, beyond the goal tolerance; nothing was applied."
                    )
                if final_error > 1.0e-12:
                    waypoints += (dict(goal),)
                    details["finalSnapSi"] = final_error
            details["plannedWaypointCount"] = len(waypoints)
            for index, waypoint in enumerate(waypoints):
                if self._manual_jog_current_identity(parameter_node, for_task_home_review=True) != identity:
                    raise ValueError("Home-draft planning identity changed; application stopped.")
                # Once submitted, uncertain/partial execution must be reconciled
                # through the existing read-only native accepted-state query.
                self._manual_jog_uncertainty = {
                    "identity": dict(identity), "requested": dict(goal),
                    "sessionId": self._manual_jog_session_id, "forTaskHomeReview": True,
                }
                self._manual_jog_reconciliation_required = True
                submitted = True
                applied = self._apply_positions_si(waypoint)
                if not applied.success:
                    details["rejectedWaypointIndex"] = index
                    return finish(False, "task_home_draft_guard_rejected",
                                  "The strict guard rejected Home-draft waypoint "
                                  f"{index + 1}/{len(waypoints)}. " + applied.message)
                self.invalidateMotionPlan()
                details["appliedWaypointCount"] += 1
            matched, message, monitored, error = self._bridge.wait_for_monitored_joint_positions_si(goal)
            accepted = self._bridge.last_accepted_joint_positions_si()
            displayed = self.currentRobotState().joint_positions_si
            validity = self._checkStateValidity()
            finite_state = all(
                isinstance(vector, Mapping) and set(vector) == set(JOINT_NAMES)
                and all(not isinstance(v, bool) and isfinite(float(v)) for v in vector.values())
                for vector in (accepted, displayed, monitored)
            )
            if (not finite_state or matched is not True or not self._joint_positions_match(goal, accepted)[0]
                    or not self._joint_positions_match(goal, displayed)[0]
                    or not validity.success or not validity.details.get("authoritative")
                    or self._manual_jog_current_identity(parameter_node, for_task_home_review=True) != identity):
                return finish(False, "task_home_draft_state_unknown",
                              "Home-draft state was not authoritatively confirmed; use Reconcile State in 6.3 Manual. " + message)
            self._manual_jog_reconciliation_required = False
            self._manual_jog_uncertainty = None
            details.update(acceptedJointPositionsSi=dict(accepted),
                           monitoredJointPositionsSi=dict(monitored), maximumJointError=error)
            return finish(True, "task_home_draft_applied",
                          ("The robot was already at the Home draft; the exact draft passed the "
                           "strict guard and the monitored robot matches it."
                           if already_at_draft else
                           "MoveIt planned the Home draft, every waypoint passed the strict guard, "
                           "and the monitored robot matches it.")
                          + " Review and Accept & Validate to save it as Task Home.")
        except (AttributeError, RuntimeError, ValueError, TypeError, OverflowError, OSError, KeyError) as exc:
            return finish(False, "task_home_draft_failed", str(exc))
        finally:
            if submitted:
                self._runtime_validated_task_home_key = ""
                self._runtime_task_home_evidence = {}
                self.invalidateMotionPlan()
            if identity is not None:
                self._manual_jog_in_progress = False

    def applyTaskHome(self) -> RobotActionResult:
        """Plan current-to-Home in MoveIt, then apply it through the guard.

        MoveIt owns global path feasibility from the monitored current state.
        Every returned waypoint is then submitted to the strict simulation
        guard, which remains authoritative for joint bounds, self/world
        collision, and configured clearance. This is not actuator homing or
        hardware execution.
        """

        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "A Task Home save or reconciliation is in progress.",
            )
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "Applying Task Home is blocked because a guarded preview stopped before endpoint verification.",
            )
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
                    planner_id=STEP6_JOINT_PLANNER_ID,
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
            state_validity = self._checkStateValidity()
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
            # Keep the display-sync guard active until all five values and the
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
                        f"Saved workspace sample {evidence_index} lacks five planning joints."
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
                    planner_id=STEP6_JOINT_PLANNER_ID,
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
            home = self._logic.taskHomeRecord(parameter_node)
            if home is None:
                return RobotActionResult(
                    False,
                    "task_home_required",
                    "Save a case/base-specific Task Home before confirming the task.",
                )
            if not self.taskHomeRuntimeValidated(parameter_node):
                return RobotActionResult(
                    False,
                    "task_home_runtime_validation_required",
                    "Apply or save Task Home in the current ROS/MoveIt session before confirming the task.",
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
            provisional_workspace = None
            try:
                proposal = json.loads(
                    str(parameter_node.step6AssistedLimitProposalJson or "")
                )
                if not isinstance(proposal, dict):
                    self._runtime_validated_workspace_key = ""
                elif proposal.get("task_axis_status") == "ProvisionalSelectedTrajectory":
                    if (
                        "task_fingerprint" in proposal
                        and proposal["task_fingerprint"] == ""
                        and self.workspaceRuntimeValidated(parameter_node)
                    ):
                        provisional_workspace = proposal
                    else:
                        self._runtime_validated_workspace_key = ""
            except (
                AttributeError,
                KeyError,
                OSError,
                OverflowError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                self._runtime_validated_workspace_key = ""
            snapshot = self._logic.confirmStep6Task(parameter_node)
            if provisional_workspace is not None:
                try:
                    proposal = json.loads(
                        str(parameter_node.step6AssistedLimitProposalJson or "")
                    )
                    trajectory = self._logic.step6TrajectorySummary(parameter_node)
                    trajectory_fingerprint = str(
                        self._logic.step6TrajectoryRevision(parameter_node) or ""
                    )
                    current_snapshot = self._logic.confirmedTaskRecord(
                        parameter_node
                    )
                    snapshot_fingerprint = str(snapshot.snapshot_fingerprint or "")
                    entry = tuple(float(value) for value in trajectory["entryRas"])
                    target = tuple(float(value) for value in trajectory["targetRas"])
                    snapshot_entry = tuple(float(value) for value in snapshot.entry_ras_mm)
                    snapshot_target = tuple(float(value) for value in snapshot.target_ras_mm)
                    if (
                        isinstance(proposal, dict)
                        and proposal == provisional_workspace
                        and snapshot_fingerprint
                        and current_snapshot is not None
                        and str(current_snapshot.snapshot_fingerprint or "")
                        == snapshot_fingerprint
                        and not self._logic.confirmedTaskFreshnessIssues(
                            parameter_node
                        )
                        and trajectory_fingerprint
                        == str(
                            provisional_workspace.get("trajectory_fingerprint") or ""
                        )
                        and str(snapshot.trajectory_revision or "")
                        == trajectory_fingerprint
                        and len(entry) == len(target) == len(snapshot_entry) == len(snapshot_target) == 3
                        and all(
                            isfinite(value)
                            for value in entry + target + snapshot_entry + snapshot_target
                        )
                        and tuple(round(value, 9) for value in snapshot_entry)
                        == tuple(round(value, 9) for value in entry)
                        and tuple(round(value, 9) for value in snapshot_target)
                        == tuple(round(value, 9) for value in target)
                    ):
                        proposal["task_axis_status"] = "ConfirmedCurrent"
                        proposal["task_fingerprint"] = snapshot_fingerprint
                        proposal["task_axis_fingerprint"] = fingerprint(
                            {
                                "status": "ConfirmedCurrent",
                                "entry_ras_mm": snapshot_entry,
                                "target_ras_mm": snapshot_target,
                                "trajectory_fingerprint": trajectory_fingerprint,
                                "task_fingerprint": snapshot_fingerprint,
                            }
                        )
                        parameter_node.step6AssistedLimitProposalJson = canonical_json(
                            proposal
                        )
                        self._runtime_validated_workspace_key = fingerprint(proposal)
                    else:
                        self._runtime_validated_workspace_key = ""
                except (
                    AttributeError,
                    KeyError,
                    OSError,
                    OverflowError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    self._runtime_validated_workspace_key = ""
            self._clear_phase_session()
            effective_entry = tuple(float(value) for value in snapshot.entry_ras_mm)
            effective_target = tuple(float(value) for value in snapshot.target_ras_mm)
            effective_depth = sqrt(
                sum(
                    (effective_target[index] - effective_entry[index]) ** 2
                    for index in range(3)
                )
            )
            return RobotActionResult(
                True,
                "task_confirmed",
                (
                    "Confirmed one immutable SIMULATION task snapshot with "
                    "the exact requested Entry-to-Target depth without a software cap. "
                    f"Effective Entry={effective_entry}, Target={effective_target}, "
                    f"depth={effective_depth:.3f} mm. The source trajectory remains "
                    "unchanged; this Target is not claimed to be pulp. "
                    "Any geometry, base, home, limit, tool, or robot-resource "
                    "change invalidates it."
                ),
                details={
                    "taskFingerprint": snapshot.snapshot_fingerprint,
                    "simulationTargetDepthPolicy": SIMULATION_TARGET_DEPTH_POLICY,
                    "effectiveEntryRasMm": effective_entry,
                    "effectiveTargetRasMm": effective_target,
                    "effectiveDepthMm": effective_depth,
                    "sourceTrajectoryUnchanged": True,
                    "requestedTargetPreserved": True,
                    "effectiveTargetIsPulpClaim": False,
                },
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

    def setTcpDragEnabled(self, enabled: bool) -> RobotActionResult:
        if not isinstance(enabled, bool):
            return RobotActionResult(
                False,
                "tcp_drag_toggle_invalid",
                "TCP drag state must be an explicit on/off value.",
            )
        ok, message, goal_node = self._bridge.set_moveit_tcp_goal_drag_enabled(
            enabled
        )
        return RobotActionResult(
            bool(ok),
            "tcp_drag_enabled" if ok and enabled else (
                "tcp_drag_disabled" if ok else "tcp_drag_toggle_failed"
            ),
            str(message),
            details={"dragEnabled": enabled if ok else None},
            payload=goal_node,
        )

    def nudgeTcpGoal(self, payload: Mapping[str, Any]) -> RobotActionResult:
        expected = {
            "translation_ras_mm",
            "rotation_local_rpy_deg",
            "source",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            return RobotActionResult(
                False,
                "tcp_nudge_invalid",
                "A TCP nudge must contain translation_ras_mm, "
                "rotation_local_rpy_deg, and source.",
            )
        source = str(payload.get("source") or "").strip()
        if not source or len(source) > 80:
            return RobotActionResult(
                False,
                "tcp_nudge_invalid",
                "A TCP nudge requires a short, non-empty source label.",
            )
        translation = payload["translation_ras_mm"]
        rotation = payload["rotation_local_rpy_deg"]
        try:
            ok, message, goal_node, current_pose = (
                self._bridge.nudge_moveit_tcp_goal(
                    translation,
                    rotation,
                )
            )
        except (TypeError, ValueError, IndexError, OverflowError) as exc:
            return RobotActionResult(False, "tcp_nudge_invalid", str(exc))
        return RobotActionResult(
            bool(ok),
            "tcp_goal_nudged" if ok else "tcp_nudge_rejected",
            str(message),
            details={
                "source": source,
                "translationRasMm": translation,
                "rotationLocalRpyDeg": rotation,
                "routeAuthority": False,
                "acceptedRobotStateChanged": False,
            },
            payload={
                "goalNode": goal_node,
                "currentPoseParent": current_pose,
            },
        )

    def ensureTcpGoal(self) -> RobotActionResult:
        ok, message, goal_node = self._bridge.ensure_moveit_tcp_goal_transform()
        return RobotActionResult(
            ok,
            "tcp_goal_ready" if ok else "tcp_goal_failed",
            message,
            payload=goal_node,
        )

    def proposeAutoTaskHome(self, *, depth_mm: float = 0.0) -> RobotActionResult:
        """Propose a biting-edge midpoint Home; caller may stage the draft only."""
        from dentobot_workflow.auto_task_home import propose_auto_task_home

        return propose_auto_task_home(
            self, RobotActionResult, _default_bridge, depth_mm=depth_mm
        )

    def solveIk(self) -> RobotActionResult:
        try:
            ok, message, positions = self._bridge.solve_moveit_tcp_goal()
        except Exception as exc:
            return RobotActionResult(
                False,
                "ik_failed",
                f"Collision-aware TCP IK failed before authoritative validation: {exc}",
                details={
                    "collisionAwareValidated": False,
                    "authoritativeStaticValidity": False,
                },
            )
        candidate = None
        if isinstance(positions, Mapping) and set(positions) == set(JOINT_NAMES):
            try:
                candidate = {name: float(positions[name]) for name in JOINT_NAMES}
            except (TypeError, ValueError, OverflowError):
                candidate = None
        exact_finite_joints = bool(
            candidate is not None
            and all(isfinite(value) for value in candidate.values())
        )
        success = ok is True and exact_finite_joints
        if ok is True and not exact_finite_joints:
            message = (
                str(message)
                + " MoveIt returned no complete, finite J1–J5 result; the candidate "
                "was rejected and was not staged."
            )
        return RobotActionResult(
            success,
            "ik_solved" if success else "ik_failed",
            message,
            details={
                "collisionAwareValidated": success,
                "authoritativeStaticValidity": success,
                "candidateJointPositionsSi": candidate,
            },
            payload=candidate if success else None,
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

    def _verify_preview_endpoint(self, plan: PhasePlan) -> RobotActionResult:
        """Confirm monitored joints and FK TCP endpoint after every preview."""

        parameter_node = self._require_context()
        expected = dict(plan.waypoint_joint_vectors_si[-1])
        ok, message, monitored, maximum_error = (
            self._bridge.wait_for_monitored_joint_positions_si(expected)
        )
        if not ok:
            return RobotActionResult(
                False,
                "preview_endpoint_monitor_mismatch",
                "Preview accepted its final guard waypoint, but the monitored "
                "MoveIt state did not converge. " + str(message),
                details={
                    "expectedJointPositionsSi": expected,
                    "monitoredJointPositionsSi": monitored,
                    "maximumJointError": maximum_error,
                },
            )
        snapshot = self._logic.confirmedTaskRecord(parameter_node)
        expected_ras = (
            tuple(snapshot.entry_ras_mm)
            if str(plan.requested_phase) == "approach"
            else tuple(snapshot.target_ras_mm)
        )
        truncation = getattr(self, "_drilling_truncation", None)
        if (
            str(plan.requested_phase) != "approach"
            and isinstance(truncation, Mapping)
            and truncation.get("task_fingerprint") == str(snapshot.snapshot_fingerprint)
            and all(
                abs(float(expected.get(name, float("nan"))) - float(value)) <= 1.0e-12
                for name, value in dict(truncation.get("last_joint_positions_si") or {}).items()
            )
        ):
            # Shortened drilling plan: its effective target is the planned endpoint.
            expected_ras = tuple(float(v) for v in truncation["effective_target_ras_mm"])
        fk = getattr(self._bridge, "compute_tcp_position_world_ras_mm", None)
        if not callable(fk):
            return RobotActionResult(
                False,
                "preview_endpoint_fk_unavailable",
                "The preview endpoint cannot be confirmed because authoritative "
                "world-RAS TCP FK is unavailable.",
            )
        fk_ok, fk_message, actual_ras = fk(
            expected,
            base_transform=parameter_node.robotBaseTransform,
        )
        if not fk_ok or actual_ras is None:
            return RobotActionResult(
                False,
                "preview_endpoint_fk_failed",
                str(fk_message),
            )
        error_mm = sqrt(
            sum(
                (float(actual_ras[index]) - float(expected_ras[index])) ** 2
                for index in range(3)
            )
        )
        tolerance_mm = float(
            getattr(_default_bridge, "CARTESIAN_START_POSITION_TOLERANCE_MM", 0.25)
        )
        if error_mm > tolerance_mm:
            return RobotActionResult(
                False,
                "preview_endpoint_tcp_mismatch",
                f"Preview endpoint TCP is {error_mm:.3f} mm from the requested "
                f"{str(plan.requested_phase)} endpoint (limit {tolerance_mm:.3f} mm).",
                details={
                    "actualTcpRasMm": tuple(actual_ras),
                    "expectedTcpRasMm": expected_ras,
                    "tcpPositionErrorMm": error_mm,
                },
            )
        return RobotActionResult(
            True,
            "preview_endpoint_verified",
            f"Monitored joints and TCP endpoint verified at {error_mm:.3f} mm "
            f"from the requested {str(plan.requested_phase)} point.",
            details={
                "actualTcpRasMm": tuple(actual_ras),
                "expectedTcpRasMm": expected_ras,
                "tcpPositionErrorMm": error_mm,
                "monitoredJointPositionsSi": monitored,
                "maximumJointError": maximum_error,
            },
        )

    @staticmethod
    def _goal1_route_key(value: Mapping[str, object]) -> dict[str, object]:
        """Return the stable identity used to reselect a route after reload."""

        candidate = value.get("candidate")
        source = candidate if isinstance(candidate, Mapping) else value
        clearance = source.get("clearance")
        if not isinstance(clearance, Mapping):
            clearance = value.get("clearance")
        if not isinstance(clearance, Mapping):
            clearance = {}
        route_type = (
            "clearance-detour"
            if isinstance(value.get("clearance"), Mapping)
            else source.get("routeType", source.get("route_type", "direct"))
        )
        seed = source.get("seedSampleIndex", source.get("ik_seed_sample_index"))
        clearance_index = source.get(
            "clearance_sample_index",
            clearance.get("sampleIndex"),
        )
        return {
            "route_type": str(route_type or "direct"),
            "ik_seed_sample_index": None if seed is None else int(seed),
            "clearance_sample_index": (
                None if clearance_index is None else int(clearance_index)
            ),
            "axial_roll_deg": round(
                float(source.get("rollDeg", source.get("axial_roll_deg", 0.0))),
                9,
            ),
        }

    def _current_diagnostic_plan_selection(self, parameter_node):
        payload = str(parameter_node.step6MotionDiagnosticJson or "").strip()
        if not payload:
            return None
        try:
            session = parse_motion_diagnostic_session(payload)
            if session.full_task_outcome.get("diagnostic_kind") == "preentry_ik":
                return None
            if self._logic.motionDiagnosticFreshnessIssues(parameter_node):
                return None
        except (RuntimeError, ValueError, OSError, KeyError):
            return None
        selection = motion_diagnostic_plan_selection(session)
        if selection["state"] not in {"selected", "locked"}:
            return None
        if not selection.get("route_key"):
            return None
        return selection

    def selectDiagnosticCandidate(
        self,
        candidate_index: int,
        *,
        lock: bool = False,
    ) -> RobotActionResult:
        """Persist an alternate route choice; planning remains transient."""

        try:
            parameter_node = self._require_context()
            issues = self._logic.motionDiagnosticFreshnessIssues(parameter_node)
            if issues:
                raise ValueError(" ".join(issues))
            session = self._logic.motionDiagnosticRecord(parameter_node)
            if session is None:
                raise ValueError("No current Step 6 motion diagnostic is available.")
            if session.full_task_outcome.get("diagnostic_kind") == "preentry_ik":
                raise ValueError(
                    "PreEntry IK endpoint diagnostics cannot be selected as planner routes."
                )
            index = int(candidate_index)
            if index < 0 or index >= len(session.candidate_records):
                raise ValueError("Diagnostic candidate index is out of range.")
            if str(
                session.candidate_records[index].get("full_chain_candidate_status") or ""
            ) != "Complete":
                raise ValueError(
                    "Only a complete full-chain candidate can become the active route."
                )
            current = motion_diagnostic_plan_selection(session)
            if current["state"] == "locked" and index != int(
                current["candidate_index"]
            ):
                raise ValueError(
                    "A different route is locked. Unlock it before selecting another route."
                )
            route_key = self._goal1_route_key(session.candidate_records[index])
            updated = update_motion_diagnostic_plan_selection(
                session,
                index,
                state="locked" if lock else "selected",
                route_key=route_key,
            )
            parameter_node.step6MotionDiagnosticJson = canonical_json(
                updated.to_dict()
            )
            selection = motion_diagnostic_plan_selection(updated)
            self._diagnostic_plan_selection_override = selection
            return RobotActionResult(
                True,
                "motion_diagnostic_plan_locked"
                if lock
                else "motion_diagnostic_plan_selected",
                (
                    f"Selected planner route {index + 1} and saved its route identity. "
                    + (
                        "It is locked to this route identity; re-planning remains required "
                        "after restore or any transient runtime reset."
                        if lock
                        else "Plan Approach again to apply this route to the transient guarded plan."
                    )
                ),
                details={"planSelection": selection},
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(
                False, "motion_diagnostic_plan_selection_failed", str(exc)
            )

    def _capture_route_activation_state(self, parameter_node) -> dict[str, object]:
        """Capture the small transient state needed for atomic route apply."""

        return {
            "diagnostic_json": str(parameter_node.step6MotionDiagnosticJson or ""),
            "motion_plan": self._motion_plan,
            "phase_sequence": self._phase_sequence,
            "completed_phase": self._completed_phase,
            "phase_guard_task_fingerprint": self._phase_guard_task_fingerprint,
            "preflight_drilling_plan": self._preflight_drilling_plan,
            "preflight_task_fingerprint": self._preflight_task_fingerprint,
            "preflight_orientation_commitment": self._preflight_orientation_commitment,
            "preflight_complete_approach_evidence": self._preflight_complete_approach_evidence,
            "accepted_motion_history": self._accepted_motion_history,
            "motion_history_task_fingerprint": self._motion_history_task_fingerprint,
            "diagnostic_candidate_paths": self._diagnostic_candidate_paths,
            "diagnostic_plan_selection_override": self._diagnostic_plan_selection_override,
            "planning_scene_object_count": self._planning_scene_object_count,
            "planning_scene_synchronized": self._planning_scene_synchronized,
            "robot_away_from_home": self._robot_away_from_home,
        }

    def _restore_route_activation_state(
        self,
        parameter_node,
        state: Mapping[str, object],
    ) -> None:
        """Restore the prior route when an alternate cannot be activated."""

        parameter_node.step6MotionDiagnosticJson = str(
            state.get("diagnostic_json") or ""
        )
        self._motion_plan = state.get("motion_plan")
        self._phase_sequence = int(state.get("phase_sequence", 0))
        self._completed_phase = str(state.get("completed_phase") or "")
        self._phase_guard_task_fingerprint = str(
            state.get("phase_guard_task_fingerprint") or ""
        )
        self._preflight_drilling_plan = state.get("preflight_drilling_plan")
        self._preflight_task_fingerprint = str(
            state.get("preflight_task_fingerprint") or ""
        )
        self._preflight_orientation_commitment = state.get(
            "preflight_orientation_commitment", {}
        )
        self._preflight_complete_approach_evidence = state.get(
            "preflight_complete_approach_evidence"
        )
        self._accepted_motion_history = state.get("accepted_motion_history", [])
        self._motion_history_task_fingerprint = str(
            state.get("motion_history_task_fingerprint") or ""
        )
        self._diagnostic_candidate_paths = state.get(
            "diagnostic_candidate_paths", {}
        )
        self._diagnostic_plan_selection_override = state.get(
            "diagnostic_plan_selection_override"
        )
        self._planning_scene_object_count = int(
            state.get("planning_scene_object_count", 0)
        )
        self._planning_scene_synchronized = bool(
            state.get("planning_scene_synchronized", False)
        )
        self._robot_away_from_home = bool(state.get("robot_away_from_home", False))

    def applyDiagnosticCandidate(
        self,
        candidate_index: int,
        *,
        lock: bool = False,
    ) -> RobotActionResult:
        """Save a route choice and regenerate the current guarded plan from it."""

        try:
            parameter_node = self._require_context()
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(
                False,
                "motion_diagnostic_plan_apply_failed",
                str(exc),
            )
        prior_state = self._capture_route_activation_state(parameter_node)
        selection = self.selectDiagnosticCandidate(candidate_index, lock=lock)
        if not selection.success:
            return selection
        try:
            planned = self.planApproachPhase()
        except (RuntimeError, ValueError, OSError) as exc:
            self._restore_route_activation_state(parameter_node, prior_state)
            return RobotActionResult(
                False,
                "motion_diagnostic_plan_apply_failed",
                "Alternate route was not activated. " + str(exc),
                details={"activationPreserved": True},
            )
        if not planned.success:
            self._restore_route_activation_state(parameter_node, prior_state)
            details = dict(planned.details)
            details.update(
                {
                    "planSelection": selection.details.get("planSelection", {}),
                    "activationPreserved": True,
                }
            )
            return RobotActionResult(
                False,
                planned.code,
                selection.message + " Alternate route was not activated. " + planned.message,
                details=details,
                payload=planned.payload,
            )
        details = dict(planned.details)
        details["planSelection"] = selection.details.get("planSelection", {})
        return RobotActionResult(
            True,
            "motion_diagnostic_plan_applied",
            selection.message + " " + planned.message,
            details=details,
            payload=planned.payload,
        )

    def unlockDiagnosticCandidate(self) -> RobotActionResult:
        """Release a saved route lock without selecting a different route."""

        try:
            parameter_node = self._require_context()
            issues = self._logic.motionDiagnosticFreshnessIssues(parameter_node)
            if issues:
                raise ValueError(" ".join(issues))
            session = self._logic.motionDiagnosticRecord(parameter_node)
            if session is None:
                raise ValueError("No current Step 6 motion diagnostic is available.")
            if session.full_task_outcome.get("diagnostic_kind") == "preentry_ik":
                raise ValueError(
                    "PreEntry IK endpoint diagnostics contain no saved route lock."
                )
            selection = motion_diagnostic_plan_selection(session)
            if selection["state"] != "locked":
                return RobotActionResult(
                    True,
                    "motion_diagnostic_plan_already_unlocked",
                    "The retained planner route is not locked.",
                )
            updated = update_motion_diagnostic_plan_selection(
                session,
                int(selection["candidate_index"]),
                state="selected",
                route_key=selection["route_key"],
            )
            parameter_node.step6MotionDiagnosticJson = canonical_json(
                updated.to_dict()
            )
            self._diagnostic_plan_selection_override = motion_diagnostic_plan_selection(
                updated
            )
            return RobotActionResult(
                True,
                "motion_diagnostic_plan_unlocked",
                "Released the saved route lock. Re-plan Approach to choose or apply another route.",
                details={"planSelection": self._diagnostic_plan_selection_override},
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(
                False, "motion_diagnostic_plan_unlock_failed", str(exc)
            )

    def showDiagnosticCandidate(self, candidate_index: int) -> RobotActionResult:
        """Show one retained last-valid state on the translucent goal robot."""
        try:
            parameter_node = self._require_context()
            payload = str(parameter_node.step6MotionDiagnosticJson or "").strip()
            if not payload:
                raise ValueError("No retained Step 6 motion diagnostic is available.")
            session = parse_motion_diagnostic_session(payload)

            def freshness_issues() -> tuple[str, ...]:
                issues = []
                try:
                    if self._parameter_node() is not parameter_node:
                        issues.append("The active case changed during diagnostic inspection.")
                except Exception as exc:
                    issues.append(f"The active case identity could not be verified: {exc}")
                try:
                    current_payload = str(
                        parameter_node.step6MotionDiagnosticJson or ""
                    ).strip()
                except Exception as exc:
                    current_payload = ""
                    issues.append(f"The retained diagnostic session could not be read: {exc}")
                if current_payload not in {
                    payload,
                    inspection_payload,
                }:
                    issues.append("The retained diagnostic session changed during inspection.")
                if getattr(session, "state", "") != "Current":
                    issues.append("The retained motion diagnostic is not Current.")
                stale_reason = str(getattr(session, "stale_reason", "") or "").strip()
                if stale_reason:
                    issues.append(stale_reason)
                checker = getattr(self._logic, "motionDiagnosticFreshnessIssues", None)
                if not callable(checker):
                    issues.append("Current motion-diagnostic identity could not be verified.")
                else:
                    try:
                        issues.extend(str(issue) for issue in checker(parameter_node))
                    except Exception as exc:
                        issues.append(f"Current motion-diagnostic identity could not be verified: {exc}")
                return tuple(dict.fromkeys(issue for issue in issues if issue))

            inspection_payload = None

            def stale_result(issues, inspection=None):
                reason = "; ".join(issues)
                details = {
                    "staleReason": str(getattr(session, "stale_reason", "") or ""),
                    "freshnessIssues": tuple(issues),
                }
                if inspection is not None:
                    details["diagnosticInspection"] = inspection
                return RobotActionResult(
                    False,
                    "diagnostic_candidate_stale",
                    "The retained diagnostic is stale or no longer matches the current scene. "
                    "Re-run Step 6 diagnostics before inspecting or displaying this candidate. "
                    + reason,
                    details=details,
                )

            def discard_inspection(issues, message):
                if (
                    inspection_payload is not None
                    and parameter_node.step6MotionDiagnosticJson == inspection_payload
                ):
                    parameter_node.step6MotionDiagnosticJson = payload
                return stale_result(
                    issues,
                    {"status": "discarded", "message": message},
                )

            initial_issues = freshness_issues()
            if initial_issues:
                return stale_result(initial_issues)
            if self.previewActive or self._guarded_preview_active:
                return RobotActionResult(
                    False,
                    "diagnostic_candidate_display_blocked",
                    "Stop or finish the active preview before inspecting or displaying a diagnostic candidate.",
                )
            index = int(candidate_index)
            if index < 0 or index >= len(session.candidate_records):
                raise ValueError("Diagnostic candidate index is out of range.")
            record = dict(session.candidate_records[index])
            positions = record.get("last_valid_joint_positions_si")
            display_only_best_failed_ik = False
            inspection = None
            if not isinstance(positions, dict):
                preentry_ik_session = (
                    isinstance(session.full_task_outcome, Mapping)
                    and session.full_task_outcome.get("diagnostic_kind")
                    == "preentry_ik"
                )
                if (
                    record.get("full_chain_failure_stage") != "preentry_ik"
                    and not preentry_ik_session
                ) or record.get("solver_success") is True:
                    return RobotActionResult(
                        False,
                        "diagnostic_state_unavailable",
                        "This candidate did not return a displayable failed PreEntry IK state.",
                        details=record,
                    )
                positions = record.get("best_joint_positions_si")
                try:
                    valid_best_state = (
                        isinstance(positions, Mapping)
                        and set(positions) == set(JOINT_NAMES)
                        and all(
                            isinstance(positions[name], Real)
                            and not isinstance(positions[name], bool)
                            and isfinite(float(positions[name]))
                            for name in JOINT_NAMES
                        )
                    )
                except (TypeError, ValueError, OverflowError):
                    valid_best_state = False
                if not valid_best_state:
                    return RobotActionResult(
                        False,
                        "diagnostic_state_unavailable",
                        "This PreEntry IK diagnostic has no exact finite best J1–J5 state to display.",
                        details=record,
                    )
                display_only_best_failed_ik = True
                conditioning = session.full_task_outcome.get("target_conditioning")
                if not isinstance(conditioning, Mapping):
                    return RobotActionResult(
                        False,
                        "diagnostic_state_unavailable",
                        "The retained PreEntry diagnostic has no exact target pose and drilling axis for inspection.",
                        details=record,
                    )
                try:
                    expected_position = tuple(
                        float(value)
                        for value in conditioning["pre_entry_world_ras_mm"]
                    )
                    expected_axis = tuple(
                        float(value)
                        for value in conditioning["drilling_axis_world_unit"]
                    )
                    expected_axis_length = sqrt(
                        sum(value * value for value in expected_axis)
                    )
                    if (
                        len(expected_position) != 3
                        or len(expected_axis) != 3
                        or not all(isfinite(value) for value in (*expected_position, *expected_axis))
                        or not isfinite(expected_axis_length)
                        or expected_axis_length <= 1.0e-12
                    ):
                        raise ValueError("retained PreEntry target is incomplete")
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    return RobotActionResult(
                        False,
                        "diagnostic_state_unavailable",
                        f"The retained PreEntry diagnostic target is invalid: {exc}",
                        details=record,
                    )

                static_check = getattr(
                    self._bridge, "check_moveit_static_joint_state", None
                )
                try:
                    if not callable(static_check):
                        raise RuntimeError("MoveIt static-state validity is unavailable.")
                    static_valid, static_message, static_authoritative = static_check(
                        positions
                    )
                    static_authoritative = (
                        static_authoritative is True
                        and isinstance(static_valid, bool)
                    )
                    static_state = {
                        "status": (
                            "valid"
                            if static_authoritative and static_valid is True
                            else "invalid"
                            if static_authoritative and static_valid is False
                            else "unavailable"
                        ),
                        "authoritative": static_authoritative,
                        "message": str(static_message or ""),
                    }
                except Exception as exc:
                    static_state = {
                        "status": "unavailable",
                        "authoritative": False,
                        "message": str(exc),
                    }

                issues = freshness_issues()
                if issues:
                    return discard_inspection(
                        issues,
                        "Scene identity changed after static-state inspection.",
                    )

                try:
                    endpoint = self._evaluate_step6_tcp_endpoint(
                        parameter_node,
                        positions,
                        expected_tcp_world_ras_mm=expected_position,
                        expected_drill_axis_world_ras_unit=expected_axis,
                        check_static=False,
                    )
                except Exception as exc:
                    endpoint = {
                        "status": "unknown",
                        "fk": {
                            "status": "unknown",
                            "message": str(exc),
                            "pose_world_ras_mm": None,
                        },
                        "position_residual_mm": None,
                        "drilling_axis_residual_deg": None,
                    }

                issues = freshness_issues()
                if issues:
                    return discard_inspection(
                        issues,
                        "Scene identity changed after FK inspection.",
                    )

                fk = endpoint.get("fk", {})
                pose = fk.get("pose_world_ras_mm")
                actual_axis = None
                if fk.get("status") == "passed" and pose is not None:
                    actual_axis_values = tuple(float(pose[row][2]) for row in range(3))
                    axis_length = sqrt(sum(value * value for value in actual_axis_values))
                    if axis_length > 1.0e-12 and all(
                        isfinite(value) for value in actual_axis_values
                    ):
                        actual_axis = tuple(value / axis_length for value in actual_axis_values)
                inspection = {
                    "status": "current",
                    "static_state_validity": static_state,
                    "fk": {
                        "status": str(fk.get("status") or "unknown"),
                        "message": str(fk.get("message") or ""),
                        "pose_world_ras_mm": pose,
                        "drilling_axis_world_ras_unit": actual_axis,
                    },
                    "expected": {
                        "tcp_world_ras_mm": expected_position,
                        "drilling_axis_world_ras_unit": expected_axis,
                    },
                    "position_residual_mm": endpoint.get("position_residual_mm"),
                    "drilling_axis_residual_deg": endpoint.get(
                        "drilling_axis_residual_deg"
                    ),
                    "native": {
                        "message": str(record.get("solver_message") or ""),
                        "termination_reason": str(
                            record.get("termination_reason") or "unknown"
                        ),
                        "collision_check_status": str(
                            record.get("collision_check_status") or "unknown"
                        ),
                        "position_residual_mm": record.get("position_residual_mm"),
                        "drilling_axis_residual_deg": record.get(
                            "drilling_axis_residual_deg"
                        ),
                    },
                }
                fk_status = str(fk.get("status") or "unknown")
                position_residual = endpoint.get("position_residual_mm")
                axis_residual = endpoint.get("drilling_axis_residual_deg")
                authoritative_fk_status = (
                    "Failed"
                    if fk_status != "passed" or position_residual is None or axis_residual is None
                    else "OutsideTolerance"
                    if endpoint.get("status") == "failed"
                    else "Passed"
                )
                record.update(
                    {
                        "static_state_validity_status": {
                            "valid": "Valid",
                            "invalid": "Invalid",
                            "unavailable": "Unavailable",
                        }[static_state["status"]],
                        "static_state_validity_message": static_state["message"],
                        "authoritative_fk_status": authoritative_fk_status,
                        "authoritative_fk_message": str(fk.get("message") or ""),
                        "authoritative_position_residual_mm": position_residual,
                        "authoritative_drilling_axis_residual_deg": axis_residual,
                        "authoritative_tcp_pose_world_ras_mm": pose,
                        "authoritative_drilling_axis_world_ras_unit": actual_axis,
                    }
                )
                updated_records = [dict(candidate) for candidate in session.candidate_records]
                updated_records[index] = record
                updated_session = build_motion_diagnostic_session(
                    state=session.state,
                    stale_reason=session.stale_reason,
                    task_fingerprint=session.task_fingerprint,
                    base_fingerprint=session.base_fingerprint,
                    trajectory_fingerprint=session.trajectory_fingerprint,
                    robot_profile_fingerprint=session.robot_profile_fingerprint,
                    collision_audit_fingerprint=session.collision_audit_fingerprint,
                    planning_parameters_fingerprint=session.planning_parameters_fingerprint,
                    candidate_records=updated_records,
                    selected_candidate_index=session.selected_candidate_index,
                    failure_classification=session.failure_classification,
                    operator_review_state=session.operator_review_state,
                    generated_at_utc=session.generated_at_utc,
                    schema_version=session.schema_version,
                    stage_outcomes=session.stage_outcomes,
                    full_task_outcome=session.full_task_outcome,
                )
                updated_payload = canonical_json(updated_session.to_dict())
                parameter_node.step6MotionDiagnosticJson = updated_payload
                inspection_payload = updated_payload
                session = updated_session
                issues = freshness_issues()
                if issues:
                    return discard_inspection(
                        issues,
                        "Scene identity changed before display.",
                    )

            issues = freshness_issues()
            if issues:
                return discard_inspection(
                    issues, "Scene identity changed before display."
                )
            evidence_ok, evidence_message = self._bridge.show_motion_diagnostic_evidence(
                first_invalid_ras_mm=record.get("first_invalid_ras_mm"),
                collision_pairs=record.get("first_invalid_collision_pairs", ()),
            )
            issues = freshness_issues()
            if issues:
                clear_display = getattr(
                    self._bridge, "clear_motion_diagnostic_display", None
                )
                if callable(clear_display):
                    clear_display()
                return discard_inspection(
                    issues, "Scene identity changed during evidence display."
                )
            ok, message = self._bridge.show_goal_robot_joint_positions(
                positions, diagnostic=True
            )
            issues = freshness_issues()
            if issues:
                clear_display = getattr(
                    self._bridge, "clear_motion_diagnostic_display", None
                )
                if callable(clear_display):
                    clear_display()
                return discard_inspection(
                    issues, "Scene identity changed during candidate display."
                )
            if display_only_best_failed_ik:
                message = (
                    "Best failed PreEntry IK state inspected for visualization only. "
                    "Static validity and FK remain independent; no IK success, accepted-state, guard, or route authority is implied. "
                    + ("Displayed. " if ok else "Display was blocked. ")
                    + message
                )
            details = dict(record)
            if inspection is not None:
                details["diagnosticInspection"] = inspection
            return RobotActionResult(
                ok and evidence_ok,
                (
                    "diagnostic_candidate_shown"
                    if ok and evidence_ok
                    else "diagnostic_candidate_display_blocked"
                    if "TCP Drag" in str(message)
                    else "diagnostic_candidate_failed"
                ),
                message + " " + evidence_message,
                details=details,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "diagnostic_candidate_failed", str(exc))

    def clearDiagnosticDisplay(self) -> RobotActionResult:
        """Stop only this façade's diagnostic timer and clear owned display evidence."""
        diagnostic_timer = self._diagnostic_preview_timer
        if diagnostic_timer is not None:
            if (
                self._preview_timer is diagnostic_timer
                and not self._guarded_preview_active
            ):
                try:
                    diagnostic_timer.stop()
                except Exception as exc:
                    return RobotActionResult(
                        False,
                        "diagnostic_display_cleanup_failed",
                        f"Could not stop the diagnostic preview timer: {exc}",
                    )
                self._preview_timer = None
                if not self._preview_waypoint_in_flight:
                    self._preview_index = 0
                self._diagnostic_preview_timer = None
            elif self._preview_timer is not diagnostic_timer:
                self._diagnostic_preview_timer = None
        clear = getattr(self._bridge, "clear_motion_diagnostic_display", None)
        if not callable(clear):
            return RobotActionResult(
                False,
                "diagnostic_display_cleanup_unavailable",
                "The ROS bridge does not expose diagnostic display cleanup.",
            )
        try:
            if self._guarded_preview_active:
                ok, message = clear(hide_goal=False)
            else:
                ok, message = clear()
        except Exception as exc:
            return RobotActionResult(
                False,
                "diagnostic_display_cleanup_failed",
                str(exc),
            )
        return RobotActionResult(
            bool(ok),
            "diagnostic_display_cleared" if ok else "diagnostic_display_cleanup_failed",
            str(message),
        )

    def showDiagnosticCandidatePaths(self, candidate_index: int) -> RobotActionResult:
        """Show all retained display-only TCP paths for one live planner leg."""
        paths = self._diagnostic_candidate_paths.get(int(candidate_index), {})
        if not paths:
            return RobotActionResult(
                False,
                "diagnostic_path_unavailable",
                "This saved diagnostic has no live route waypoints; re-plan Approach to inspect its path.",
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
        if self.previewActive or self._guarded_preview_active:
            return RobotActionResult(
                False,
                "guarded_preview_active",
                "Stop or finish the guarded live preview before starting a diagnostic leg preview.",
            )
        parameter_node = self._parameter_node()
        if parameter_node is not None:
            try:
                session = self._logic.motionDiagnosticRecord(parameter_node)
            except (ValueError, json.JSONDecodeError):
                session = None
            if (
                session is not None
                and session.full_task_outcome.get("diagnostic_kind") == "preentry_ik"
            ):
                return RobotActionResult(
                    False,
                    "diagnostic_preview_unavailable",
                    "PreEntry IK endpoint diagnostics contain no previewable route.",
                )
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
            self._bridge.show_goal_robot_joint_positions(
                waypoints[self._preview_index], diagnostic=True
            )
            self._preview_index += 1

        timer.timeout.connect(advance)
        timer.start()
        self._preview_timer = timer
        self._diagnostic_preview_timer = timer
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

    def _configure_phase_guard(
        self,
        parameter_node,
        snapshot,
        *,
        static_only: bool = False,
        preflight_start_positions_si: Optional[Mapping[str, float]] = None,
    ) -> tuple[bool, str]:
        """Start one fresh transient guard session for the synchronized scene."""

        if (
            self._template_collision_exclusion_active
            and not self.historicalTemplateOverrideEnabled
        ):
            return False, (
                "Historical template exclusion authorization changed. Disable the "
                "override and re-synchronize the complete collision scene before planning."
            )
        target_object_id = self._logic.step6TargetCollisionObjectId(parameter_node)
        if not target_object_id:
            return False, "The selected target-tooth collision object is unavailable."
        guidance_object_ids = self._logic.step6GuidanceCollisionObjectIds(
            parameter_node,
            allow_deferred_static_ack=(
                bool(static_only) or preflight_start_positions_si is not None
            ),
        )
        if not guidance_object_ids and not self._template_collision_exclusion_active:
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
        return self._bridge.configure_task_phase_guard(
            task_fingerprint=snapshot.snapshot_fingerprint,
            target_object_id=target_object_id,
            clearance_exempt_object_ids=burr_proximity_object_ids,
            base_transform=parameter_node.robotBaseTransform,
            entry_ras_mm=snapshot.entry_ras_mm,
            target_ras_mm=snapshot.target_ras_mm,
            corridor_radius_mm=snapshot.corridor_radius_mm,
            approach_standoff_mm=float(parameter_node.step6ApproachStandoffMm),
            # Preserve the exact current scene identities. The native guard
            # applies the narrower simulation-only margin only to burr-guide
            # distance pairs; actual collisions remain authoritative.
            simulation_guide_clearance_object_ids=guidance_object_ids,
            collision_scene_policy_fingerprint=self._strict_guard_policy_fingerprint(),
            static_only=bool(static_only),
            preflight_start_positions_si=preflight_start_positions_si,
            allow_spindle_guide_contact=self._spindle_guide_contact_allowed(),
        )

    def _spindle_guide_contact_allowed(self) -> bool:
        """Advanced option (Step 4C / 6.3): 0.5 mm spindle-template tolerance; default off."""
        try:
            return bool(getattr(self._parameter_node(), "step6AllowSpindleGuideContact", False))
        except Exception:
            return False

    def _prepare_phase_guard(self, parameter_node, snapshot) -> tuple[bool, str]:
        pause_stream = getattr(
            self._bridge, "pause_slicer_joint_command_stream", None
        )
        if callable(pause_stream):
            self._phase_stream_paused = bool(pause_stream())
        count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
        self._planning_scene_object_count = count
        self._planning_scene_synchronized = True
        self._template_collision_excluded_object_ids = ()
        self._phase_guard_session_id = ""
        result = self._configure_phase_guard(parameter_node, snapshot)
        if result[0]:
            status_getter = getattr(self._bridge, "last_task_joint_status", None)
            try:
                status = status_getter() if callable(status_getter) else None
            except Exception:
                status = None
            if (
                status is not None
                and getattr(status, "task_fingerprint", "")
                == snapshot.snapshot_fingerprint
                and getattr(status, "phase", "") == "approach"
                and getattr(status, "sequence", -1) == 0
                and bool(getattr(status, "accepted", False))
                and not bool(getattr(status, "validate_only", False))
            ):
                self._phase_guard_session_id = str(
                    getattr(status, "guard_session_id", "") or ""
                )
        return result

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
            "axial_roll_deg": LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG,
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
            "first_invalid_joint_limit_blockers": [
                dict(item)
                for item in getattr(result, "first_invalid_joint_limit_blockers", ())
            ],
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
            "sequential_ik_recovery_attempted": bool(
                result.sequential_ik_recovery_attempted
            ),
            "sequential_ik_failure_index": int(result.sequential_ik_failure_index),
            "sequential_ik_failure_message": _bounded_text(
                result.sequential_ik_failure_message
            ),
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
                "routePlannerRevision": "full-chain-v2-sequential-ik",
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
        fixed_rotation_ras: Optional[Sequence[Sequence[float]]] = None,
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
                fixed_rotation_ras=fixed_rotation_ras,
                position_axis_only=True,
            )
        if not result.success:
            raise RuntimeError(
                "Full Entry-to-Target reachability failed for the canonical "
                "non-spinning TCP. "
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
        entry_ras_mm: Sequence[float],
        target_ras_mm: Sequence[float],
        axial_roll_deg: float,
    ) -> dict[str, object]:
        """Describe the immutable drilling axis selected by Stage 1.

        Axial roll is unconstrained because the five-DOF arm does not control it.
        Stages 2 and 3 keep this exact +Z axis and select a continuous joint state.
        """

        direction = tuple(
            float(target_ras_mm[index]) - float(entry_ras_mm[index])
            for index in range(3)
        )
        length = sum(value * value for value in direction) ** 0.5
        if length <= 1.0e-9:
            raise ValueError("Entry and Target cannot define a drilling frame.")
        axis = tuple(value / length for value in direction)
        element = (
            pose.GetElement
            if hasattr(pose, "GetElement")
            else lambda row, column: pose[row][column]
        )
        rotation = tuple(
            tuple(float(element(row, column)) for column in range(3))
            for row in range(3)
        )
        identity = {
            "policy": DRILL_TOOL_FRAME_POLICY,
            "toolAxisRas": axis,
            "rotationRas": rotation,
            "axialFrameRollDeg": float(axial_roll_deg),
            "orientationConstraint": "position-plus-drilling-axis-only",
        }
        return {**identity, "fingerprint": fingerprint(identity)}

    @staticmethod
    def _derived_axial_roll_deg(
        rotation_ras: Sequence[Sequence[float]],
        tool_axis_ras: Sequence[float],
    ) -> float:
        """Return display-only housing roll relative to the trajectory frame."""

        axis = tuple(float(value) for value in tool_axis_ras)
        reference = (1.0, 0.0, 0.0)
        if abs(sum(a * b for a, b in zip(reference, axis))) > 0.9:
            reference = (0.0, 1.0, 0.0)
        projection = sum(a * b for a, b in zip(reference, axis))
        frame_x = tuple(reference[index] - projection * axis[index] for index in range(3))
        frame_x_length = sqrt(sum(value * value for value in frame_x))
        frame_x = tuple(value / frame_x_length for value in frame_x)
        frame_y = (
            axis[1] * frame_x[2] - axis[2] * frame_x[1],
            axis[2] * frame_x[0] - axis[0] * frame_x[2],
            axis[0] * frame_x[1] - axis[1] * frame_x[0],
        )
        actual_x = tuple(float(rotation_ras[row][0]) for row in range(3))
        return degrees(
            atan2(
                sum(a * b for a, b in zip(actual_x, frame_y)),
                sum(a * b for a, b in zip(actual_x, frame_x)),
            )
        )

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
                    for name in JOINT_NAMES
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
                for name in JOINT_NAMES
            )
            for previous, current in zip(waypoints, waypoints[1:])
        )

    SPINDLE_HOUSING_LINK = "pneumatic_spindle-Copy"

    @classmethod
    def _spindle_template_pair(cls, bodies) -> bool:
        """Truncation trigger: spindle housing against the template/guide only.

        Spindle-to-tooth (or any other) collisions are not truncated; they fail.
        """
        names = [str(body) for body in bodies if body]
        if cls.SPINDLE_HOUSING_LINK not in names or len(names) != 2:
            return False
        other = names[1] if names[0] == cls.SPINDLE_HOUSING_LINK else names[0]
        return any(key in other for key in ("Template", "Docking", "Support", "Guide"))

    @property
    def drillingTruncation(self):
        """Current shortened-drilling diagnostics (None when the full line is planned)."""
        return dict(self._drilling_truncation) if self._drilling_truncation else None

    def _truncate_drilling_for_spindle_collision(
        self,
        parameter_node,
        snapshot,
        prefix_waypoints,
        prefix_phases,
        drilling_plan,
        drilling_offset: int,
        invalid_index: int,
        guard_bodies,
        *,
        validate_chain,
        entry: Sequence[float],
        target: Sequence[float],
        revalidate: bool = True,
    ):
        """Shorten the drilling route to its last spindle-collision-free waypoint.

        Operator policy 2026-10-02: when the spindle housing blocks the drafted
        drilling line, the last collision-free drilling waypoint becomes the
        effective target and the shortened route is a normal planned outcome.
        The rest of the drafted line is reported as diagnostics. Returns
        ``(plan, truncation)`` or ``(None, reason)``.
        """
        if not self._spindle_template_pair(guard_bodies):
            return None, "The Stage 3 guard blocker is not a spindle-housing/template collision."
        drilling = tuple(drilling_plan.waypoint_joint_vectors_si)
        keep = int(invalid_index) - int(drilling_offset)
        if keep < 2 or keep > len(drilling):
            return None, "No spindle-collision-free drilling advance precedes the blocked waypoint."
        shortened = drilling[:keep]
        if revalidate:
            # The guard sequence is per session: re-validating in the same session is
            # rejected as "Phased command sequence is stale or duplicated" (r8), so
            # the shortened chain is checked in a fresh guard session.
            guard_ready, guard_ready_message = self._configure_phase_guard(parameter_node, snapshot)
            if not guard_ready:
                return None, "Phase guard could not be re-armed for the shortened route: " + str(guard_ready_message)
            guard_valid, guard_message, second_invalid = validate_chain(
                tuple(prefix_waypoints) + shortened,
                tuple(prefix_phases) + ("drilling",) * len(shortened),
                task_fingerprint=snapshot.snapshot_fingerprint,
            )
            if not guard_valid:
                return None, "The shortened drilling route is still rejected: " + str(guard_message)
        # revalidate=False (candidate ranking, operator 2026-10-03 option A): the
        # shortened chain is exactly the prefix the same guard session has just
        # accepted (waypoints before the first invalid index), so replaying it
        # adds no information. The selected chain is still fully re-validated.
        fk_ok, fk_message, effective = self._bridge.compute_tcp_position_world_ras_mm(
            shortened[-1], base_transform=parameter_node.robotBaseTransform
        )
        if not fk_ok or effective is None:
            return None, "Effective target FK unavailable: " + str(fk_message)
        effective = tuple(float(value) for value in effective)
        axis = tuple(float(target[i]) - float(entry[i]) for i in range(3))
        requested = sqrt(sum(value * value for value in axis))
        unit = tuple(value / requested for value in axis) if requested > 0 else (0.0, 0.0, 0.0)
        completed = sum((effective[i] - float(entry[i])) * unit[i] for i in range(3))
        times = tuple(drilling_plan.waypoint_times_sec or ())[:keep]
        plan = replace(
            drilling_plan,
            success=True,
            message=(
                f"Drilling shortened by spindle-housing collision: {completed:.3f} of "
                f"{requested:.3f} mm reachable."
            ),
            fraction=max(0.0, min(1.0, completed / requested if requested > 0 else 0.0)),
            waypoint_joint_vectors_si=shortened,
            waypoint_times_sec=times,
            completed_distance_mm=float(completed),
            last_valid_waypoint_index=keep - 1,
            last_valid_joint_positions_si=dict(shortened[-1]),
        )
        truncation = {
            "policy": "spindle_housing_truncation_v1",
            "blocking_pair": [str(body) for body in guard_bodies],
            "first_blocked_drilling_index": keep,
            "kept_waypoint_count": keep,
            "drafted_waypoint_count": len(drilling),
            "requested_depth_mm": float(requested),
            "completed_depth_mm": float(completed),
            "remaining_depth_mm": float(max(0.0, requested - completed)),
            "effective_target_ras_mm": list(effective),
            "original_target_ras_mm": [float(value) for value in target],
            "unreachable_segment_ras_mm": [list(effective), [float(v) for v in target]],
            "last_joint_positions_si": dict(shortened[-1]),
            "task_fingerprint": str(snapshot.snapshot_fingerprint),
        }
        truncation["feedback"] = _truncation_feedback(truncation)
        return plan, truncation

    # "report": evaluate and record the mouth-portal gate without blocking;
    # "enforce": reject plans that fail it. Report-only until the operator
    # decides the anterior-tooth geometry (incisor Entry lies anterior to the
    # canine portal plane in the FDI11 case, 2026-10-02 evidence).
    MOUTH_PORTAL_GATE_MODE = "enforce"  # operator 2026-10-02: option A lip line + (b) 5 mm enlargement

    def _mouth_portal_blocks(self, evidence) -> bool:
        return bool(
            evidence is not None
            and evidence.get("status") not in ("passed", "skipped")  # skipped: barrier edges Off
            and self.MOUTH_PORTAL_GATE_MODE == "enforce"
        )

    def _plan_joint_goal_with_retries(self, **kwargs):
        """Sequential independent re-plans while the planner returns no route."""
        plan = None
        for attempt in range(1, STEP6_JOINT_PLAN_RETRIES + 1):
            plan = self._bridge.plan_moveit_joint_goal(**kwargs)
            if plan.success and (plan.waypoint_joint_vectors_si or ()):
                if attempt > 1:
                    plan = replace(plan, message=f"{plan.message} (planned on re-plan {attempt} of {STEP6_JOINT_PLAN_RETRIES})")
                return plan
        return replace(plan, message=f"{plan.message} (no route in {STEP6_JOINT_PLAN_RETRIES} independent re-plans)")

    def _measure_approach_corridor(
        self,
        parameter_node,
        preentry_positions,
        *,
        pre_entry,
        entry,
        target,
        fixed_rotation_ras,
        roll_deg: float,
    ) -> dict:
        """Axial approach-corridor clearance behind PreEntry; read-only, no planning.

        Shared by P1 and the Feasibility Advisor (S6-MULTI-TARGET-01 2026-10-06)
        so both apply the same STEP6_APPROACH_CORRIDOR_MIN_MM rule. ``status`` is
        ``available`` (``back`` is the kept collision-free prefix), ``blocked``
        (shorter than the minimum) or ``unavailable`` (no straight back-out).
        """
        axis = tuple(float(target[i]) - float(entry[i]) for i in range(3))
        length = sqrt(sum(value * value for value in axis))
        unit = tuple(value / length for value in axis) if length > 0 else (0.0, 0.0, 0.0)
        approach = tuple(float(pre_entry[i]) - STEP6_APPROACH_CORRIDOR_MM * unit[i] for i in range(3))
        back_out = self._bridge.plan_moveit_cartesian_path(
            entry_ras_mm=tuple(float(v) for v in pre_entry),
            target_ras_mm=approach,
            sample_count=max(3, int(parameter_node.robotMotionPlanSampleCount)),
            base_transform=parameter_node.robotBaseTransform,
            avoid_collisions=False,
            minimum_fraction=0.99,
            start_joint_positions_si=dict(preentry_positions),
            axial_roll_start_deg=float(roll_deg),
            axial_roll_end_deg=float(roll_deg),
            fixed_rotation_ras=fixed_rotation_ras,
            position_axis_only=True,
            reverse_travel=True,
        )
        back = tuple(dict(point) for point in (back_out.waypoint_joint_vectors_si or ()))
        result = {
            "status": "available",
            "reason": "",
            "corridor_mm": STEP6_APPROACH_CORRIDOR_MM,
            "requested_mm": STEP6_APPROACH_CORRIDOR_MM,
            "minimum_mm": STEP6_APPROACH_CORRIDOR_MIN_MM,
            "margin_samples": max(0, int(self._approach_corridor_margin_samples)),
            "sample_count": len(back),
            "valid_count": len(back),
            "validity_authoritative": False,
            "blocked_message": "",
            "first_blocked_state": None,
            "back": back,
            "back_out": back_out,
        }
        if not back_out.success or len(back) < 2:
            result.update(status="unavailable", corridor_mm=0.0, valid_count=0,
                          reason="straight back-out failed: " + str(back_out.message))
            return result
        # The back-out is built without collision checking, so A may lie inside
        # anatomy or the mouth barrier (S6-LIVE-01 2026-10-04: lower canine and
        # lip slab from ~1.5 mm). Keep the longest collision-free prefix.
        checker = getattr(self._bridge, "check_moveit_static_joint_state", None)
        if callable(checker):
            result["validity_authoritative"] = True
            valid_count = 0
            for state in back:
                valid, validity_message, authoritative = checker(state)
                if not authoritative:
                    result["validity_authoritative"] = False
                    valid_count = len(back)
                    break
                if not valid:
                    result["blocked_message"] = str(validity_message)
                    result["first_blocked_state"] = dict(state)
                    break
                valid_count += 1
            if valid_count < len(back):
                # Optional margin (operator 2026-10-05 lever): stop short of the
                # first contact so A is not at zero clearance. Default 0.
                valid_count = max(1, valid_count - result["margin_samples"])
                corridor_mm = STEP6_APPROACH_CORRIDOR_MM * max(valid_count - 1, 0) / (len(back) - 1)
                result.update(corridor_mm=corridor_mm, valid_count=valid_count, back=back[:valid_count])
                if corridor_mm < STEP6_APPROACH_CORRIDOR_MIN_MM:
                    result.update(
                        status="blocked",
                        reason=(
                            f"axial corridor blocked {corridor_mm:.2f} mm behind PreEntry: "
                            + result["blocked_message"]
                        ),
                    )
        return result

    def checkApproachCorridorClearance(self) -> RobotActionResult:
        """Read-only P1 corridor clearance at the same-instance PreEntry endpoint.

        Feasibility Advisor screen (S6-MULTI-TARGET-01 2026-10-06): runs the
        exact P1 corridor measurement without planning, so an endpoint pass is
        not mistaken for a route. Creates no plan, route or MRML change.
        """
        try:
            context = self._step6_stage_context()
            cache = self._step6_preentry_candidate_cache
            if not isinstance(cache, Mapping) or cache.get("identity") != context["identity"]:
                raise ValueError("Run PreEntry IK for the current inputs first.")
            candidates = tuple(cache.get("candidates") or ())
            if not candidates:
                raise ValueError("PreEntry IK produced no collision-checked endpoint candidate.")
            candidate = candidates[0]
            measured = self._measure_approach_corridor(
                context["parameter_node"],
                dict(candidate["positions"]),
                pre_entry=context["pre_entry"],
                entry=context["entry"],
                target=context["target"],
                fixed_rotation_ras=candidate["orientation"].get("rotationRas"),
                roll_deg=float(candidate["roll_deg"]),
            )
        except (RuntimeError, ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
            return RobotActionResult(False, "approach_corridor_check_failed", str(exc))
        details = {
            key: value for key, value in measured.items() if key not in ("back", "back_out")
        }
        details["identity"] = dict(context["identity"])
        details["preentry_positions_si"] = dict(candidate["positions"])
        if measured["status"] == "available":
            return RobotActionResult(
                True,
                "approach_corridor_clear",
                f"Axial approach corridor {measured['corridor_mm']:.2f} mm "
                f"(minimum {STEP6_APPROACH_CORRIDOR_MIN_MM:.2f} mm).",
                details=details,
            )
        return RobotActionResult(False, "approach_corridor_" + measured["status"], measured["reason"], details=details)

    def _plan_home_to_preentry_with_corridor(
        self,
        parameter_node,
        home_positions,
        preentry_positions,
        *,
        pre_entry,
        entry,
        target,
        fixed_rotation_ras,
        roll_deg: float,
        planner_context: str,
        refresh_planning_scene: bool = True,
    ):
        """P1 approach corridor (operator 2026-10-02).

        Free-space joint plan Home -> approach point A (STEP6_APPROACH_CORRIDOR_MM
        back from PreEntry along the drill axis), then the straight fixed-frame
        line A -> PreEntry. A's joint state comes from planning the straight
        line backwards from the PreEntry state, so no separate IK is needed. If
        the corridor cannot be built, the direct Home->PreEntry plan is used and
        both outcomes are reported in ``plan.message``.
        """
        def direct(reason):
            plan = self._plan_joint_goal_with_retries(
                start_joint_positions_si=home_positions,
                goal_joint_positions_si=preentry_positions,
                refresh_planning_scene=refresh_planning_scene,
                planning_attempts=self._joint_planning_attempts,
                allowed_planning_time_sec=self._joint_planning_time_sec,
                planner_id=self._joint_planner_id,
                planner_context=planner_context,
            )
            return replace(plan, message=f"Approach corridor unavailable ({reason}); direct plan: {plan.message}")

        corridor = self._measure_approach_corridor(
            parameter_node, preentry_positions, pre_entry=pre_entry, entry=entry, target=target,
            fixed_rotation_ras=fixed_rotation_ras, roll_deg=roll_deg)
        if corridor["status"] != "available":
            return direct(corridor["reason"])
        back = corridor["back"]
        back_out = corridor["back_out"]
        corridor_mm = corridor["corridor_mm"]
        approach_positions = back[-1]
        to_approach = self._plan_joint_goal_with_retries(
            start_joint_positions_si=home_positions,
            goal_joint_positions_si=approach_positions,
            refresh_planning_scene=refresh_planning_scene,
            planning_attempts=self._joint_planning_attempts,
            allowed_planning_time_sec=self._joint_planning_time_sec,
            planner_id=self._joint_planner_id,
            planner_context=planner_context + "_corridor",
        )
        free = tuple(dict(point) for point in (to_approach.waypoint_joint_vectors_si or ()))
        if not to_approach.success or not free:
            return direct("Home to approach point failed: " + str(to_approach.message))
        descend = tuple(reversed(back))[1:]
        times = list(to_approach.waypoint_times_sec or ())
        last = times[-1] if times else 0.0
        back_times = list(back_out.waypoint_times_sec or ())
        if len(back_times) >= len(back):
            total = back_times[len(back) - 1]
            times += [last + (total - back_times[len(back) - 2 - i]) for i in range(len(descend))]
        else:
            times += [last + 0.1 * (i + 1) for i in range(len(descend))]
        return replace(
            to_approach,
            waypoint_joint_vectors_si=free + descend,
            waypoint_times_sec=tuple(times),
            message=(
                f"Approach corridor: free-space Home -> approach point "
                f"{corridor_mm:.2f} mm out along the drill axis, then straight "
                f"into PreEntry ({len(free)} + {len(descend)} waypoints)."
            ),
        )

    @staticmethod
    def _reach_envelope_sentence(envelope) -> str:
        """One plain sentence on the visual reach envelope and the task stations."""
        stations = (envelope or {}).get("stations_inside") or {}
        if not stations:
            return ""
        parts = [
            f"{name} {'inside' if value.get('inside') else 'outside'}"
            + ("" if value.get("inside") else f" ({value.get('nearest_sample_mm')} mm from the nearest sample)")
            for name, value in stations.items()
        ]
        return (" Reach envelope (display only): " + ", ".join(parts) + ".")

    def _step6_mouth_portal_gate(self, parameter_node, joint_path) -> Optional[dict]:
        """Prefix gate (operator 2026-10-02): the Home->PreEntry TCP path must enter
        the mouth through the canine portal. Returns None when the logic has no
        portal support (host fakes); otherwise passed/failed evidence. An
        unbuildable portal fails closed."""
        gate = getattr(self._logic, "checkStep6MouthPortalGate", None)
        if not callable(gate):
            return None
        tcp_path = []
        for state in joint_path:
            fk_ok, fk_message, position = self._bridge.compute_tcp_position_world_ras_mm(
                state, base_transform=parameter_node.robotBaseTransform
            )
            if not fk_ok or position is None:
                return {"status": "failed", "reason": "tcp_fk_unavailable", "message": str(fk_message)}
            tcp_path.append(tuple(float(value) for value in position))
        try:
            return gate(parameter_node, tcp_path)
        except (OSError, RuntimeError, ValueError) as exc:
            return {"status": "failed", "reason": "portal_unavailable", "message": str(exc)}

    def _truncate_p3_stage_for_spindle_collision(self, context, path_by_phase, path, guard):
        """P3 diagnostic counterpart of the spindle-housing truncation policy."""
        if guard.get("status") != "failed" or not self._spindle_template_pair(guard.get("named_pair") or []):
            return None
        offset = len(path_by_phase.get("P1", ())) + len(path_by_phase.get("P2", ()))
        first_invalid = guard.get("first_invalid_index")
        keep = (int(first_invalid) - offset) if first_invalid is not None else -1
        if keep < 2 or keep > len(path):
            return None
        shortened = tuple(path[:keep])
        trial_paths = {**path_by_phase, "P3": shortened}
        trial_guard = self._step6_stage_guard_evidence(context, trial_paths)
        if trial_guard.get("status") != "passed":
            return None
        parameter_node = context["parameter_node"]
        fk_ok, _message, effective = self._bridge.compute_tcp_position_world_ras_mm(
            shortened[-1], base_transform=parameter_node.robotBaseTransform
        )
        if not fk_ok or effective is None:
            return None
        effective = tuple(float(value) for value in effective)
        # The phase guard (authoritative; measures guide-contact penetration)
        # accepted this shortened route, so only FK pose evidence is re-checked.
        endpoint = self._evaluate_step6_tcp_endpoint(
            parameter_node,
            shortened[-1],
            expected_tcp_world_ras_mm=effective,
            expected_drill_axis_world_ras_unit=context["drill_axis"],
            check_static=False,
        )
        if endpoint.get("status") != "passed":
            return None
        entry, target = context["entry"], context["target"]
        axis = tuple(float(target[i]) - float(entry[i]) for i in range(3))
        requested = sqrt(sum(value * value for value in axis))
        unit = tuple(value / requested for value in axis) if requested > 0 else (0.0, 0.0, 0.0)
        completed = sum((effective[i] - float(entry[i])) * unit[i] for i in range(3))
        snapshot = self._logic.confirmedTaskRecord(parameter_node)
        truncation = {
            "policy": "spindle_housing_truncation_v1",
            "blocking_pair": list(guard.get("named_pair") or []),
            "first_blocked_drilling_index": keep,
            "kept_waypoint_count": keep,
            "drafted_waypoint_count": len(path),
            "requested_depth_mm": float(requested),
            "completed_depth_mm": float(completed),
            "remaining_depth_mm": float(max(0.0, requested - completed)),
            "effective_target_ras_mm": list(effective),
            "original_target_ras_mm": [float(value) for value in target],
            "unreachable_segment_ras_mm": [list(effective), [float(v) for v in target]],
            "last_joint_positions_si": dict(shortened[-1]),
            "task_fingerprint": str(getattr(snapshot, "snapshot_fingerprint", "") or ""),
        }
        truncation["feedback"] = _truncation_feedback(truncation)
        return shortened, trial_paths, trial_guard, endpoint, truncation

    def _goal1_candidate_chain_preflight(
        self,
        parameter_node,
        snapshot,
        candidate: Mapping[str, object],
        strict_plan,
        *,
        pre_entry: Sequence[float],
        entry: Sequence[float],
        target: Sequence[float],
    ) -> dict[str, object]:
        """Evaluate one Stage-1 frame against the complete fixed-frame chain."""

        mouth_portal = self._step6_mouth_portal_gate(
            parameter_node, tuple(strict_plan.waypoint_joint_vectors_si or ())
        )
        if self._mouth_portal_blocks(mouth_portal):
            # Empty (not None) Stage-2 plans: callers summarise every candidate's
            # fraction/waypoints, and a None crashed Plan Approach (r10).
            not_planned = _default_bridge.MoveItCartesianResult(
                False, "Not planned: the mouth portal gate rejected Stage 1."
            )
            return {
                "status": "BlockedMouthPortalGate",
                "mouthPortalGate": mouth_portal,
                "axisPlan": not_planned,
                "terminalPlan": not_planned,
                "drillingPlan": None,
                "guardValid": False,
                "guardMessage": "",
                "firstInvalidIndex": -1,
                "reason": "Mouth portal gate: " + str(mouth_portal.get("reason") or "failed"),
                "score": (4, 0.0, 0.0, candidate["score"]),
            }

        fixed_roll_deg = float(candidate["rollDeg"])
        fixed_rotation_ras = candidate["orientationCommitment"]["rotationRas"]
        stage1_end = (
            strict_plan.waypoint_joint_vectors_si[-1]
            if strict_plan.waypoint_joint_vectors_si
            else candidate["positions"]
        )
        # The local continuity seed is normally best. If it reaches a
        # prismatic end-stop, allow the fallback to try only the deterministic
        # Home-connected postures already accepted by 6.3. These seeds are
        # branch evidence, not new workspace samples or relaxed constraints.
        continuity_seeds = []
        try:
            proposal = json.loads(
                str(parameter_node.step6AssistedLimitProposalJson or "")
            )
        except (TypeError, json.JSONDecodeError):
            proposal = {}
        for evidence in proposal.get("accepted_sample_evidence", ()):
            if len(continuity_seeds) >= GOAL1_MAX_IK_SEEDS:
                break
            if not isinstance(evidence, dict):
                continue
            names = tuple(evidence.get("joint_names", ()))
            values = tuple(evidence.get("joint_positions_si", ()))
            connectivity = evidence.get("home_connectivity", {})
            if (
                names != JOINT_NAMES
                or len(values) != len(JOINT_NAMES)
                or not isinstance(connectivity, dict)
                or connectivity.get("status") != "HomeConnected"
            ):
                continue
            try:
                continuity_seeds.append(
                    canonicalize_planning_joint_positions(
                        dict(zip(names, (float(value) for value in values)))
                    )
                )
            except (TypeError, ValueError, KeyError):
                continue
        target_axis = tuple(
            float(target[index]) - float(entry[index]) for index in range(3)
        )
        target_axis_length = sqrt(sum(value * value for value in target_axis))
        if target_axis_length <= 1.0e-12:
            not_planned = _default_bridge.MoveItCartesianResult(
                False, "Not planned: Entry and Target do not define a drilling axis."
            )
            return {
                "status": "BlockedStage3Cartesian",
                "axisPlan": not_planned,
                "terminalPlan": not_planned,
                "drillingPlan": None,
                "guardValid": False,
                "guardMessage": "Entry and Target do not define a drilling axis.",
                "firstInvalidIndex": -1,
                "reason": "Entry and Target do not define a drilling axis.",
                "score": (2, 0.0, 0.0, candidate["score"]),
            }
        target_axis = tuple(value / target_axis_length for value in target_axis)

        def endpoint_position_axis_error(plan, expected_point):
            if plan is None or not plan.waypoint_joint_vectors_si:
                return False, "No waypoint was returned for endpoint FK validation.", None
            fk_ok, fk_message, actual_pose = self._bridge.compute_tcp_pose_world_ras_mm(
                plan.waypoint_joint_vectors_si[-1],
                base_transform=parameter_node.robotBaseTransform,
            )
            if not fk_ok or actual_pose is None:
                return False, str(fk_message), None
            position_error = sqrt(
                sum(
                    (
                        float(actual_pose[index][3]) - float(expected_point[index])
                    )
                    ** 2
                    for index in range(3)
                )
            )
            actual_axis = tuple(float(actual_pose[index][2]) for index in range(3))
            actual_axis_length = sqrt(sum(value * value for value in actual_axis))
            if actual_axis_length <= 1.0e-12:
                return False, "Authoritative endpoint FK returned a degenerate tool axis.", None
            axis_cosine = max(
                -1.0,
                min(
                    1.0,
                    sum(actual_axis[index] * target_axis[index] for index in range(3))
                    / actual_axis_length,
                ),
            )
            axis_error = degrees(acos(axis_cosine))
            return (
                position_error <= _default_bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
                and axis_error <= _default_bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG,
                "Authoritative endpoint FK residual is "
                f"{position_error:.6g} mm / {axis_error:.6g} deg.",
                {
                    "position_mm": position_error,
                    "axis_deg": axis_error,
                },
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
            fixed_rotation_ras=fixed_rotation_ras,
            position_axis_only=True,
            continuity_seed_positions_si=continuity_seeds,
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
        stage2_endpoint_ok, stage2_endpoint_message, _stage2_endpoint_error = (
            endpoint_position_axis_error(terminal_plan, entry)
        )
        if not stage2_endpoint_ok:
            return {
                "status": "BlockedStage2Cartesian",
                "axisPlan": axis_plan,
                "terminalPlan": terminal_plan,
                "drillingPlan": None,
                "guardValid": False,
                "guardMessage": "",
                "firstInvalidIndex": -1,
                "reason": "Stage 2 endpoint FK validation failed: "
                + stage2_endpoint_message,
                "score": (
                    3,
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
            fixed_rotation_ras=fixed_rotation_ras,
            position_axis_only=True,
            continuity_seed_positions_si=continuity_seeds,
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
        stage3_endpoint_ok, stage3_endpoint_message, _stage3_endpoint_error = (
            endpoint_position_axis_error(drilling_plan, target)
        )
        if not stage3_endpoint_ok:
            return {
                "status": "BlockedStage3Cartesian",
                "axisPlan": axis_plan,
                "terminalPlan": terminal_plan,
                "drillingPlan": drilling_plan,
                "guardValid": False,
                "guardMessage": "",
                "firstInvalidIndex": -1,
                "reason": "Stage 3 endpoint FK validation failed: "
                + stage3_endpoint_message,
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
        warning_reader = getattr(
            self._bridge, "last_task_phase_validation_warnings", None
        )
        guide_warnings = self._normalize_guide_clearance_warnings(
            warning_reader() if callable(warning_reader) else ()
        )
        guard_status_getter = getattr(
            self._bridge,
            "last_task_joint_status",
            _default_bridge.last_task_joint_status,
        )
        guard_status = guard_status_getter()
        first_invalid_joint_positions = (
            dict(waypoints[invalid_index])
            if 0 <= int(invalid_index) < len(waypoints)
            else None
        )
        first_invalid_tcp_ras_mm = None
        if first_invalid_joint_positions is not None:
            fk_ok, _fk_message, fk_position = (
                self._bridge.compute_tcp_position_world_ras_mm(
                    first_invalid_joint_positions,
                    base_transform=parameter_node.robotBaseTransform,
                )
            )
            if fk_ok and fk_position is not None:
                first_invalid_tcp_ras_mm = tuple(float(value) for value in fk_position)
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
        drilling_truncation = None
        if status == "BlockedStage3PhaseGuard":
            shortened, truncation_or_reason = self._truncate_drilling_for_spindle_collision(
                parameter_node,
                snapshot,
                tuple(strict_plan.waypoint_joint_vectors_si)
                + tuple(terminal_plan.waypoint_joint_vectors_si),
                ("approach",) * stage1_count + ("terminal_contact",) * stage2_count,
                drilling_plan,
                stage1_count + stage2_count,
                invalid_index,
                (getattr(guard_status, "first_body", ""), getattr(guard_status, "second_body", "")),
                validate_chain=validate_chain,
                entry=snapshot.entry_ras_mm,
                target=target,
                revalidate=False,
            )
            if shortened is not None:
                drilling_truncation = truncation_or_reason
                drilling_plan = shortened
                guard_valid = True
                guard_message = shortened.message
                status = "Complete"
                rank = 0
        return {
            "status": status,
            "drillingTruncation": drilling_truncation,
            "mouthPortalGate": mouth_portal,
            "axisPlan": axis_plan,
            "terminalPlan": terminal_plan,
            "drillingPlan": drilling_plan,
            "guardValid": bool(guard_valid),
            "guardMessage": str(guard_message),
            "firstInvalidIndex": int(invalid_index),
            "firstInvalidJointPositionsSi": first_invalid_joint_positions,
            "firstInvalidTcpRasMm": first_invalid_tcp_ras_mm,
            "guardFirstBody": str(getattr(guard_status, "first_body", "") or ""),
            "guardSecondBody": str(getattr(guard_status, "second_body", "") or ""),
            "guardMinimumWorldDistanceM": getattr(
                guard_status, "minimum_world_distance_m", None
            ),
            "guardNearestPointFirstBaseM": getattr(
                guard_status, "nearest_point_first_base_m", None
            ),
            "guardNearestPointSecondBaseM": getattr(
                guard_status, "nearest_point_second_base_m", None
            ),
            **self._guide_clearance_warning_summary(guide_warnings),
            "reason": "" if guard_valid else str(guard_message),
            # Complete, guard-accepted chains outrank every partial chain.
            # Operator 2026-10-03: among them prefer the deepest drilling
            # (a spindle-truncated chain is Complete under policy 2b), then the
            # least joints-1–5 motion after PreEntry, then the Stage-1 score.
            "score": (
                rank,
                -self._complete_chain_drilled_depth_mm(
                    status, drilling_truncation, drilling_plan, snapshot.entry_ras_mm, target
                ),
                motion_cost,
                candidate["score"],
            ),
        }

    @staticmethod
    def _complete_chain_drilled_depth_mm(status, truncation, drilling_plan, entry, target) -> float:
        """Drilled depth of a Complete chain, rounded to 0.01 mm; 0.0 otherwise.

        Rounding keeps numerically equal depths tied so arm motion decides.
        """
        if status != "Complete":
            return 0.0
        if isinstance(truncation, Mapping):
            return round(float(truncation.get("completed_depth_mm", 0.0)), 2)
        requested = sqrt(sum((float(target[i]) - float(entry[i])) ** 2 for i in range(3)))
        fraction = float(getattr(drilling_plan, "fraction", 1.0) or 0.0)
        return round(requested * max(0.0, min(1.0, fraction)), 2)

    def checkPreEntryIK(self, *, progress=None) -> RobotActionResult:
        """Persist endpoint-only PreEntry IK evidence; this creates no plan."""

        self._step6_preentry_candidate_cache = None
        self._step6_stage_diagnostic_chain = {}
        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) != "case":
                raise ValueError("Open the current case before checking PreEntry IK.")
            if self.previewActive or self._robot_away_from_home:
                raise ValueError(
                    "Stop preview and return to Task Home before checking PreEntry IK."
                )
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                raise ValueError(
                    "Task confirmation is missing or stale: "
                    + ", ".join(str(issue) for issue in issues)
                )
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            home = self._logic.taskHomeRecord(parameter_node)
            audit = self._logic.collisionSceneAuditRecord(parameter_node)
            if snapshot is None or home is None or audit is None:
                raise ValueError(
                    "A current confirmed task, Task Home, and collision scene are required."
                )
            identity = self.plannerComparisonIdentity()
            scene_fingerprint = planner_comparison_scene_fingerprint(audit)
            expected = {
                "task": snapshot.snapshot_fingerprint,
                "base": snapshot.base_fingerprint,
                "home": snapshot.home_fingerprint,
                "trajectory": snapshot.trajectory_revision,
                "robot_profile": snapshot.robot_profile_fingerprint,
                "collision_audit": scene_fingerprint,
            }
            if any(identity.get(key) != value for key, value in expected.items()):
                raise ValueError(
                    "The confirmed task, base, Home, profile, trajectory, or "
                    "acknowledged collision scene changed. Reconfirm before checking IK."
                )
            if (
                home.base_fingerprint != identity["base"]
                or home.robot_profile_fingerprint != identity["robot_profile"]
                or fingerprint(home.to_dict()) != identity["home"]
            ):
                raise ValueError(
                    "Task Home does not match the current base, profile, and task."
                )
            if not self._planning_scene_synchronized:
                raise ValueError(
                    "The acknowledged collision scene is not synchronized in this runtime."
                )
            if not self.taskHomeRuntimeValidated(parameter_node):
                raise ValueError(
                    "Task Home is not validated in the current ROS/MoveIt session. "
                    "Return to 6.2 and apply/validate it before checking IK."
                )
            home_positions = dict(zip(home.joint_names, home.joint_positions_si))
            monitored_ok, monitored_message, monitored_positions, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    home_positions, timeout_sec=1.0
                )
            )
            if not monitored_ok:
                raise ValueError(
                    "Live monitored joints do not match Task Home. "
                    + str(monitored_message)
                )
            if progress:
                progress("Checking confirmed task, scene, and live Task Home")

            pre_entry, entry = self._logic.step6ApproachPoints(parameter_node, snapshot)
            target = snapshot.target_ras_mm
            approach = tuple(float(entry[i]) - float(pre_entry[i]) for i in range(3))
            drill = tuple(float(target[i]) - float(entry[i]) for i in range(3))
            approach_length = sqrt(sum(value * value for value in approach))
            drill_length = sqrt(sum(value * value for value in drill))
            if approach_length <= 1.0e-9 or drill_length <= 1.0e-9:
                raise ValueError("PreEntry, Entry, and Target must define non-zero axes.")
            world_to_base = getattr(
                self._bridge,
                "world_ras_mm_to_base_m",
                _default_bridge.world_ras_mm_to_base_m,
            )
            base_points = {
                name: tuple(world_to_base(point, parameter_node.robotBaseTransform))
                for name, point in (
                    ("pre_entry", pre_entry), ("entry", entry), ("target", target)
                )
            }
            base_drill = tuple(
                base_points["target"][i] - base_points["entry"][i]
                for i in range(3)
            )
            base_drill_length = sqrt(sum(value * value for value in base_drill))
            if base_drill_length <= 1.0e-12:
                raise ValueError("Base-frame Entry-to-Target axis is degenerate.")

            proposal = {}
            try:
                proposal = json.loads(
                    str(parameter_node.step6AssistedLimitProposalJson or "{}")
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
            workspace_identity = {
                "active_case_parameter_node": self._scene_kind(parameter_node) == "case",
                "task_home_fingerprint_matches": (
                    proposal.get("task_home_fingerprint") == fingerprint(home.to_dict())
                ),
                "base_fingerprint_matches_via_home": (
                    home.base_fingerprint == identity["base"]
                ),
                "robot_profile_fingerprint_matches_via_home": (
                    home.robot_profile_fingerprint == identity["robot_profile"]
                ),
                "collision_audit_fingerprint_matches": (
                    proposal.get("collision_audit_fingerprint") == audit.audit_fingerprint
                ),
                "workspace_policy_matches": (
                    proposal.get("workspace_validation_policy_fingerprint")
                    == self._workspace_validation_policy_fingerprint()
                ),
                "evidence_schema_matches": (
                    proposal.get("runtime_evidence_schema_version")
                    == WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION
                ),
                "runtime_validation_status_matches": (
                    proposal.get("runtime_validation_status")
                    == WORKSPACE_RUNTIME_VALIDATION_STATUS
                ),
            }
            historical_hints: list[dict[str, object]] = []
            if all(workspace_identity.values()):
                for evidence in proposal.get("accepted_sample_evidence", ()):
                    if len(historical_hints) >= GOAL1_MAX_IK_SEEDS - 1:
                        break
                    if not isinstance(evidence, dict):
                        continue
                    names = tuple(evidence.get("joint_names", ()))
                    values = tuple(evidence.get("joint_positions_si", ()))
                    static = evidence.get("static_state_validity", {})
                    historical_home = evidence.get("home_connectivity", {})
                    if (
                        names == JOINT_NAMES
                        and len(values) == len(JOINT_NAMES)
                        and isinstance(static, dict)
                        and static.get("status") == "Valid"
                        and isinstance(historical_home, dict)
                        and historical_home.get("status") == "HomeConnected"
                    ):
                        historical_hints.append(
                            {
                                "joint_names": names,
                                "joint_positions_si": values,
                                "sample_index": int(
                                    evidence.get("sample_index", len(historical_hints))
                                ),
                                "historical_evidence_identity_match": True,
                                "historical_home_connectivity_status": "HomeConnected",
                            }
                        )

            task_limits = self._logic.getTaskJointLimits(parameter_node)
            mechanical_limits = default_task_joint_limits_from_urdf(
                self._logic.robotDescriptionPaths()[0]
            )

            seed_records: list[dict[str, object]] = []
            if progress:
                progress("Solving position-axis IK and checking endpoints")
            _ik_candidates, failures = self._goal1_pre_entry_ik_candidates(
                parameter_node,
                pre_entry,
                entry,
                target,
                home_positions,
                include_workspace_seeds=False,
                avoid_collisions=True,
                require_generic_static=True,
                progress=progress,
                workspace_seed_evidence=historical_hints,
                seed_collector=seed_records.append,
            )
            for record in seed_records:
                positions = record.get("best_joint_positions_si") or record.get(
                    "returned_joint_positions_si"
                )
                margins = joint_limit_margin_evidence(
                    positions,
                    joint_names=JOINT_NAMES,
                    joint_limit_fields=JOINT_LIMIT_FIELDS[: len(JOINT_NAMES)],
                    display_units=JOINT_DISPLAY_UNITS[: len(JOINT_NAMES)],
                    mechanical_limits=mechanical_limits,
                    task_limits=task_limits,
                )
                record["mechanical_joint_limit_margins"] = margins
                record["reviewed_task_joint_limit_margins"] = margins
                if isinstance(positions, Mapping) and all(
                    name in positions for name in JOINT_NAMES
                ):
                    display_values = self._display_values_from_si(positions)
                    record["best_joint_positions_display"] = {
                        name: {
                            "value": float(display_values[index]),
                            "unit": JOINT_DISPLAY_UNITS[index],
                        }
                        for index, name in enumerate(JOINT_NAMES)
                    }
                else:
                    record["best_joint_positions_display"] = None
                record["route_authority"] = "none"
                if record.get("seed_provenance") == "historical_workspace_hint":
                    record["current_home_connectivity_status"] = "NotEvaluated"
                    record["historical_evidence_identity_match"] = dict(
                        workspace_identity
                    )
                else:
                    record["current_home_connectivity_status"] = (
                        "NotRequiredForIKOnlyDiagnostic"
                    )
            if not seed_records:
                raise RuntimeError("No seed result was produced; no report was saved.")

            target_conditioning = {
                "world_frame": "RAS_mm",
                "base_frame": "robot_base_m",
                "pre_entry_world_ras_mm": tuple(float(v) for v in pre_entry),
                "entry_world_ras_mm": tuple(float(v) for v in entry),
                "target_world_ras_mm": tuple(float(v) for v in target),
                "standoff_mm": float(parameter_node.step6ApproachStandoffMm),
                "pre_entry_base_m": base_points["pre_entry"],
                "entry_base_m": base_points["entry"],
                "target_base_m": base_points["target"],
                "approach_axis_world_unit": tuple(v / approach_length for v in approach),
                "drilling_axis_world_unit": tuple(v / drill_length for v in drill),
                "drilling_axis_base_unit": tuple(v / base_drill_length for v in base_drill),
                "approach_length_world_mm": approach_length,
                "drilling_length_world_mm": drill_length,
                "drilling_length_base_mm": base_drill_length * 1000.0,
            }
            session_candidates = [
                {
                    "candidate_index": int(record["candidate_index"]),
                    "axial_roll_deg": float(LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG),
                    # Keep the shared route-success bit false: no route was planned.
                    "success": False,
                    "completion_fraction": 0.0,
                    "completed_distance_mm": 0.0,
                    "requested_distance_mm": 0.0,
                    "waypoint_count": 0,
                    "failure_classification": str(
                        record.get("failure_classification") or "unknown"
                    ),
                    **record,
                }
                for record in seed_records
            ]
            report_status = (
                "EndpointChecksPassed"
                if any(r.get("endpoint_check_status") == "Passed" for r in seed_records)
                else "EndpointChecksUnverified"
                if any(r.get("endpoint_check_status") == "Unverified" for r in seed_records)
                else "NoEndpointPassed"
            )
            planning_fingerprint = fingerprint(
                {
                    "diagnostic_kind": "preentry_ik",
                    "method": "canonical_position_axis_ik_static_fk",
                    "avoid_collisions": True,
                    "require_generic_static": True,
                    "historical_workspace_hint_identity": workspace_identity,
                }
            )
            outcome = {
                "diagnostic_kind": "preentry_ik",
                "preentry_ik_diagnostic_schema_version": "1.0",
                "diagnostic_status": report_status,
                "status": "NotRun",
                "failure_stage": "PreEntry IK endpoint diagnostic (before P1)",
                "stage1_p1_status": "NotRun",
                "stage2_status": "NotRun",
                "stage3_status": "NotRun",
                "guard_status": "NotRun",
                "route_status": "NotRun",
                "preview_status": "NotRun",
                "motion_application_status": "NotRun",
                "waypoint_count": 0,
                "plan_authority": False,
                "executable": False,
                "route_selection_allowed": False,
                "task_identity_fingerprint": identity["task"],
                "base_identity_fingerprint": identity["base"],
                "home_identity_fingerprint": identity["home"],
                "robot_profile_identity_fingerprint": identity["robot_profile"],
                "trajectory_identity_fingerprint": identity["trajectory"],
                "collision_scene_identity_fingerprint": scene_fingerprint,
                "collision_audit_fingerprint": audit.audit_fingerprint,
                "collision_scene_acknowledged": True,
                "branch_id": identity["branch_id"],
                "task_home_fingerprint": fingerprint(home.to_dict()),
                "monitored_home_positions_si": dict(monitored_positions),
                "maximum_monitored_home_error": float(monitored_error),
                "monitored_home_message": str(monitored_message),
                "target_conditioning": target_conditioning,
                "historical_workspace_hint_identity": workspace_identity,
                "historical_workspace_case_identity_evidence": (
                    "Associated with the active case parameter node; the saved "
                    "workspace evidence contains no independent case ID."
                ),
                "historical_workspace_hint_count": len(historical_hints),
                "historical_workspace_hints_are_current_home_connected": False,
                "solver_failure_messages": list(failures),
                "candidate_count": len(seed_records),
            }
            session = build_motion_diagnostic_session(
                state="Current",
                stale_reason="",
                task_fingerprint=snapshot.snapshot_fingerprint,
                base_fingerprint=identity["base"],
                trajectory_fingerprint=identity["trajectory"],
                robot_profile_fingerprint=identity["robot_profile"],
                collision_audit_fingerprint=audit.audit_fingerprint,
                planning_parameters_fingerprint=planning_fingerprint,
                candidate_records=session_candidates,
                selected_candidate_index=0,
                failure_classification="preentry_ik_endpoint_diagnostic_only",
                operator_review_state="Unreviewed",
                stage_outcomes=(),
                full_task_outcome=outcome,
            )
            parameter_node.step6MotionDiagnosticJson = canonical_json(
                session.to_dict()
            )
            self._step6_preentry_candidate_cache = {
                "identity": dict(identity),
                "candidate_records_fingerprint": fingerprint(
                    session.to_dict()["candidate_records"]
                ),
                "pre_entry_ras_mm": tuple(float(value) for value in pre_entry),
                "entry_ras_mm": tuple(float(value) for value in entry),
                "target_ras_mm": tuple(float(value) for value in target),
                "candidates": tuple(
                    {
                        "positions": dict(candidate["positions"]),
                        "roll_deg": float(candidate["rollDeg"]),
                        "route_type": str(candidate.get("routeType") or "direct"),
                        "seed_sample_index": candidate.get("seedSampleIndex"),
                        "orientation": dict(candidate["orientationCommitment"]),
                    }
                    for candidate in _ik_candidates
                ),
            }
            return RobotActionResult(
                True,
                "preentry_ik_diagnostic_complete",
                f"Saved read-only PreEntry IK evidence for {len(seed_records)} seed(s). "
                f"Outcome: {report_status}; no P1 route or motion authority was created.",
                details={
                    "diagnosticStatus": report_status,
                    "candidateCount": len(seed_records),
                    "historicalHintCount": len(historical_hints),
                    "motionDiagnosticSessionFingerprint": session.session_fingerprint,
                },
                payload=session,
            )
        except (
            RuntimeError,
            ValueError,
            OSError,
            TypeError,
            KeyError,
            AttributeError,
        ) as exc:
            return RobotActionResult(False, "preentry_ik_diagnostic_failed", str(exc))

    def _step6_stage_context(self) -> dict[str, object]:
        """Read current prerequisites without syncing or changing MRML state."""

        parameter_node = self._require_context()
        if self._scene_kind(parameter_node) != "case":
            raise ValueError("Open the current case before checking a planning stage.")
        if self.previewActive or self._robot_away_from_home or self._incomplete_preview_evidence:
            raise ValueError(
                "Stop preview and complete a guarded Return Home before stage diagnostics."
            )
        if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
            raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
        freshness_issues = self._step6_read_only_freshness_issues(parameter_node)
        if freshness_issues:
            raise ValueError("Planning inputs are stale: " + "; ".join(freshness_issues))

        snapshot = self._logic.confirmedTaskRecord(parameter_node)
        home = self._logic.taskHomeRecord(parameter_node)
        audit = self._logic.collisionSceneAuditRecord(parameter_node)
        if snapshot is None or home is None or audit is None:
            raise ValueError("A current confirmed task, Task Home, and collision scene are required.")
        registry = json.loads(str(parameter_node.step6TrajectoryRegistryJson or "{}"))
        branch_id = str(registry.get("selected_branch_id") or "")
        branches = registry.get("prepared_branches")
        if (
            not bool(parameter_node.step6PlanningContextImported)
            or not branch_id
            or not isinstance(branches, Mapping)
            or branch_id not in branches
        ):
            raise ValueError("An active selected PreparedBranch is required.")
        branch = self._logic.evaluatePreparedBranchEligibility(
            parameter_node, branch_id, registry=registry
        )
        if not branch.get("eligible"):
            raise ValueError(str(branch.get("message") or branch.get("reason") or "PreparedBranch is stale."))
        task_issues = task_snapshot_invalidation_reasons(
            snapshot,
            target_segment_id=str(parameter_node.targetToothSegmentId or ""),
            trajectory_revision=self._logic.step6TrajectoryRevision(parameter_node),
            base_fingerprint=self._logic.robotBaseFingerprint(parameter_node),
            home_fingerprint=fingerprint(home.to_dict()),
            limits_fingerprint=self._logic.step6TaskLimitsFingerprint(parameter_node),
            robot_profile_fingerprint=self._logic.robotProfileFingerprint(),
            tool_frame=str(parameter_node.step6ToolFrame),
        )
        if task_issues:
            raise ValueError("Confirmed task inputs are stale: " + "; ".join(task_issues))
        if (
            home.base_fingerprint != self._logic.robotBaseFingerprint(parameter_node)
            or home.robot_profile_fingerprint != self._logic.robotProfileFingerprint()
        ):
            raise ValueError("Task Home does not match the current base and robot profile.")
        if audit.runtime_acknowledgement.get("status") != "Acknowledged":
            raise ValueError("The collision scene has no runtime acknowledgement.")
        if not self._planning_scene_synchronized:
            raise ValueError("The acknowledged collision scene is not synchronized in this runtime.")
        if not self.taskHomeRuntimeValidated(parameter_node):
            raise ValueError("Task Home is not validated in the current ROS/MoveIt session.")

        identity = self.plannerComparisonIdentity()
        expected_identity = {
            "branch_id": branch_id,
            "task": snapshot.snapshot_fingerprint,
            "base": self._logic.robotBaseFingerprint(parameter_node),
            "home": snapshot.home_fingerprint,
            "trajectory": self._logic.step6TrajectoryRevision(parameter_node),
            "robot_profile": self._logic.robotProfileFingerprint(),
            "collision_audit": planner_comparison_scene_fingerprint(audit),
        }
        if identity != expected_identity:
            raise ValueError("Task, branch, base, Home, profile, or scene identity changed.")
        if (
            self._motion_plan is not None
            and bool(getattr(self._motion_plan, "success", False))
            and str(getattr(self._motion_plan, "task_fingerprint", ""))
            == snapshot.snapshot_fingerprint
        ) or (
            self._preflight_drilling_plan is not None
            and self._preflight_task_fingerprint == snapshot.snapshot_fingerprint
        ) or (
            bool(self._phase_guard_session_id)
            and self._phase_guard_task_fingerprint == snapshot.snapshot_fingerprint
        ):
            raise ValueError(
                "A current preview route or phase-guard session exists. Invalidate it before configuring the diagnostic guard."
            )

        home_positions = dict(zip(home.joint_names, home.joint_positions_si))
        monitored_ok, monitored_message, monitored_positions, monitored_error = (
            self._bridge.wait_for_monitored_joint_positions_si(
                home_positions, timeout_sec=1.0
            )
        )
        if not monitored_ok:
            raise ValueError(
                "MoveIt monitored joints do not match Task Home. "
                + str(monitored_message)
            )
        pre_entry, entry = self._logic.step6ApproachPoints(parameter_node, snapshot)
        target = tuple(float(value) for value in snapshot.target_ras_mm)
        drill_axis = tuple(float(target[i]) - float(entry[i]) for i in range(3))
        drill_length = sqrt(sum(value * value for value in drill_axis))
        if drill_length <= 1.0e-12:
            raise ValueError("Entry and Target do not define a drilling axis.")
        drill_axis = tuple(value / drill_length for value in drill_axis)
        return {
            "parameter_node": parameter_node,
            "snapshot": snapshot,
            "home": home,
            "collision_audit": audit,
            "identity": identity,
            "home_positions": home_positions,
            "monitored_positions": dict(monitored_positions),
            "monitored_error": float(monitored_error),
            "pre_entry": tuple(float(value) for value in pre_entry),
            "entry": tuple(float(value) for value in entry),
            "target": target,
            "drill_axis": drill_axis,
        }

    def _replace_step6_stage_outcomes(
        self,
        parameter_node,
        outcome: Optional[Mapping[str, object]],
        *,
        expected_identity: Optional[Mapping[str, object]] = None,
        clear_all: bool = False,
    ) -> bool:
        """Update only additive schema-2.2 stage evidence on a PreEntry report."""

        payload = str(parameter_node.step6MotionDiagnosticJson or "").strip()
        if not payload:
            return False
        session = parse_motion_diagnostic_session(payload)
        if (
            session.schema_version != "2.2"
            or session.full_task_outcome.get("diagnostic_kind") != "preentry_ik"
        ):
            return False
        if expected_identity is not None:
            if (
                session.state != "Current"
                or session.task_fingerprint != expected_identity.get("task")
                or session.base_fingerprint != expected_identity.get("base")
                or session.trajectory_fingerprint != expected_identity.get("trajectory")
                or session.robot_profile_fingerprint != expected_identity.get("robot_profile")
                or session.collision_audit_fingerprint
                != self._logic.collisionSceneAuditRecord(parameter_node).audit_fingerprint
            ):
                return False
            full = session.full_task_outcome
            if any(
                full.get(field) != expected_identity.get(key)
                for field, key in (
                    ("task_identity_fingerprint", "task"),
                    ("base_identity_fingerprint", "base"),
                    ("home_identity_fingerprint", "home"),
                    ("trajectory_identity_fingerprint", "trajectory"),
                    ("robot_profile_identity_fingerprint", "robot_profile"),
                    ("collision_scene_identity_fingerprint", "collision_audit"),
                    ("branch_id", "branch_id"),
                )
            ):
                return False
        phases = ("P1", "P2", "P3")
        replaced_phase = str((outcome or {}).get("phase_id") or "")
        replaced_index = phases.index(replaced_phase) if replaced_phase in phases else len(phases)
        stages = [] if clear_all else [
            dict(stage)
            for stage in session.stage_outcomes
            if str(stage.get("phase_id") or "") in phases
            and phases.index(str(stage.get("phase_id"))) < replaced_index
        ]
        if outcome is not None:
            if str(outcome.get("phase_id") or "") not in phases:
                return False
            stages.append(dict(outcome))
        stages.sort(key=lambda stage: phases.index(str(stage.get("phase_id") or "P3")))
        updated = build_motion_diagnostic_session(
            state=session.state,
            stale_reason=session.stale_reason,
            task_fingerprint=session.task_fingerprint,
            base_fingerprint=session.base_fingerprint,
            trajectory_fingerprint=session.trajectory_fingerprint,
            robot_profile_fingerprint=session.robot_profile_fingerprint,
            collision_audit_fingerprint=session.collision_audit_fingerprint,
            planning_parameters_fingerprint=session.planning_parameters_fingerprint,
            candidate_records=session.candidate_records,
            selected_candidate_index=session.selected_candidate_index,
            failure_classification=session.failure_classification,
            operator_review_state=(
                "Unreviewed" if outcome is not None else session.operator_review_state
            ),
            schema_version=session.schema_version,
            stage_outcomes=stages,
            full_task_outcome=session.full_task_outcome,
        )
        parameter_node.step6MotionDiagnosticJson = canonical_json(updated.to_dict())
        return True

    def _step6_stage_guard_evidence(
        self,
        context: Mapping[str, object],
        path_by_phase: Mapping[str, Sequence[Mapping[str, float]]],
    ) -> dict[str, object]:
        """Guard the exact Home-rooted prefix in validate-only mode."""

        phase_names = {
            "P1": "approach",
            "P2": "terminal_contact",
            "P3": "drilling",
        }
        waypoints: list[dict[str, float]] = []
        phases: list[str] = []
        for phase_id in ("P1", "P2", "P3"):
            for waypoint in path_by_phase.get(phase_id, ()):
                waypoints.append(
                    {name: float(waypoint[name]) for name in JOINT_NAMES}
                )
                phases.append(phase_names[phase_id])
        if not waypoints:
            return {
                "status": "not_reached",
                "reason": "No requested waypoint was available for phase guarding.",
                "first_invalid_index": None,
                "first_invalid_requested": {"status": "not_reached", "state": None},
                "first_invalid_evaluated": {"status": "unknown", "state": None},
                "last_valid": {"status": "not_reached", "state": None},
                "named_pair": None,
                "clearance": {"status": "unknown", "minimum_world_distance_m": None},
            }

        parameter_node = context["parameter_node"]
        snapshot = context["snapshot"]
        configured, configure_message = self._configure_phase_guard(
            parameter_node,
            snapshot,
            preflight_start_positions_si=context["home_positions"],
        )
        if not configured:
            return {
                "status": "unknown",
                "reason": str(configure_message),
                "first_invalid_index": None,
                "first_invalid_requested": {"status": "not_reached", "state": None},
                "first_invalid_evaluated": {"status": "unknown", "state": None},
                "last_valid": {"status": "not_reached", "state": None},
                "named_pair": None,
                "clearance": {"status": "unknown", "minimum_world_distance_m": None},
            }
        guard_identity_reader = getattr(
            self._bridge,
            "current_task_guard_identity",
            _default_bridge.current_task_guard_identity,
        )
        guard_identity = guard_identity_reader()
        guard_policy_fingerprint = self._strict_guard_policy_fingerprint()
        if (
            not isinstance(guard_identity, Mapping)
            or guard_identity.get("task_fingerprint") != snapshot.snapshot_fingerprint
            or not guard_identity.get("guard_session_id")
            or guard_identity.get("collision_scene_policy_fingerprint")
            != guard_policy_fingerprint
        ):
            return {
                "status": "unknown",
                "reason": "The configured phase-guard task/session/policy identity is unavailable or mismatched.",
                "first_invalid_index": None,
                "first_invalid_requested": {"status": "not_reached", "state": None},
                "first_invalid_evaluated": {"status": "unknown", "state": None},
                "last_valid": {"status": "not_reached", "state": None},
                "named_pair": None,
                "clearance": {"status": "unknown", "minimum_world_distance_m": None},
            }
        request_id_prefix = uuid4().hex
        validate = getattr(
            self._bridge,
            "validate_task_phase_waypoints",
            _default_bridge.validate_task_phase_waypoints,
        )
        guard_ok, guard_message, invalid_index = validate(
            waypoints,
            phases,
            task_fingerprint=snapshot.snapshot_fingerprint,
            request_id_prefix=request_id_prefix,
        )
        invalid_index = int(invalid_index)
        status_getter = getattr(
            self._bridge, "last_task_joint_status", _default_bridge.last_task_joint_status
        )
        status = status_getter()
        expected_index = invalid_index if invalid_index >= 0 else len(waypoints) - 1
        expected_phase = phases[expected_index]
        requested_positions = (
            getattr(status, "requested_positions", ()) if status is not None else ()
        )
        requested_vector = (
            tuple(float(value) for value in requested_positions)
            if len(requested_positions) == len(JOINT_NAMES)
            else ()
        )
        expected_vector = tuple(
            float(waypoints[expected_index][name]) for name in JOINT_NAMES
        )
        expected_request_id = f"{request_id_prefix}:{expected_index}"
        matches = bool(
            (guard_ok or invalid_index >= 0)
            and
            status is not None
            and getattr(status, "task_fingerprint", "") == snapshot.snapshot_fingerprint
            and getattr(status, "guard_session_id", "")
            == guard_identity.get("guard_session_id")
            and getattr(status, "collision_scene_policy_fingerprint", "")
            == guard_policy_fingerprint
            and getattr(status, "request_id", "")
            == expected_request_id
            and getattr(status, "validation_kind", "") == "transition"
            and str(getattr(status, "phase", "")) == expected_phase
            and int(getattr(status, "sequence", -1))
            == int(
                getattr(
                    self._bridge,
                    "ROS2_TASK_GUARD_INITIAL_SEQUENCE",
                    _default_bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE,
                )
            ) + expected_index
            and bool(getattr(status, "validate_only", False))
            and len(requested_vector) == len(expected_vector)
            and all(
                abs(actual - expected) <= 1.0e-12
                for actual, expected in zip(requested_vector, expected_vector)
            )
        )
        if guard_ok and matches and bool(getattr(status, "accepted", False)):
            guard_status = "passed"
        elif (
            invalid_index >= 0
            and matches
            and not bool(getattr(status, "accepted", False))
            and int(getattr(status, "checked_samples", 0)) > 0
        ):
            guard_status = "failed"
        else:
            guard_status = "unknown"
        requested_state = (
            dict(waypoints[invalid_index])
            if 0 <= invalid_index < len(waypoints)
            else None
        )
        evaluated_vector = getattr(status, "evaluated_positions", ()) if matches else ()
        evaluated_state = (
            dict(zip(JOINT_NAMES, (float(value) for value in evaluated_vector)))
            if len(evaluated_vector) == len(JOINT_NAMES)
            else None
        )
        last_valid_index = (
            invalid_index - 1
            if invalid_index >= 0
            else len(waypoints) - 1
            if guard_ok
            else -1
        )
        last_valid_request = (
            dict(waypoints[last_valid_index])
            if 0 <= last_valid_index < len(waypoints)
            else None
        )
        pair = None
        if matches and (
            getattr(status, "first_body", "") or getattr(status, "second_body", "")
        ):
            pair = [
                str(getattr(status, "first_body", "") or ""),
                str(getattr(status, "second_body", "") or ""),
            ]
        world_distance = (
            getattr(status, "minimum_world_distance_m", None) if matches else None
        )
        clearance = {
            "status": "measured" if world_distance is not None else "unknown",
            "minimum_world_distance_m": (
                None if world_distance is None else float(world_distance)
            ),
            "configured_minimum_m": (
                float(status.minimum_clearance_m) if matches else None
            ),
            "nearest_pair": pair,
        }
        warning_reader = getattr(self._bridge, "last_task_phase_validation_warnings", None)
        warnings = self._normalize_guide_clearance_warnings(
            warning_reader() if callable(warning_reader) else ()
        )
        return {
            "status": guard_status,
            "reason": str(guard_message or ""),
            "first_invalid_index": invalid_index if invalid_index >= 0 else None,
            "first_invalid_requested": {
                "status": "failed" if requested_state is not None else "not_reached",
                "state": requested_state,
                "phase": phases[invalid_index] if 0 <= invalid_index < len(phases) else None,
            },
            "first_invalid_evaluated": {
                "status": "failed" if evaluated_state is not None and guard_status == "failed" else "unknown",
                "state": evaluated_state,
                "phase": expected_phase if matches else None,
                "sequence": int(getattr(status, "sequence", -1)) if matches else None,
                "guard_session_id": (
                    str(guard_identity["guard_session_id"]) if matches else None
                ),
                "request_id": expected_request_id if matches else None,
            },
            "last_valid": {
                "status": "passed" if last_valid_request is not None else "not_reached",
                "requested_state": last_valid_request,
                "evaluated_state": (
                    evaluated_state if guard_ok and last_valid_index == expected_index else None
                ),
            },
            "named_pair": pair,
            "clearance": clearance,
            "checked_samples": int(getattr(status, "checked_samples", 0)) if matches else None,
            "collision_scene_policy_fingerprint": guard_policy_fingerprint,
            "guide_clearance_warnings": [dict(item) for item in warnings],
        }

    def diagnoseBase(self, *, progress=None) -> RobotActionResult:
        """Diagnose This Base (operator 2026-10-02, ``S6-BASE-DIAGNOSE``).

        Runs the existing checks in order and stops at the first failure:
        stroke reach, PreEntry endpoint, P1, P2, P3. Diagnostic only; no route
        or preview authority and no gate change.
        """
        from dentobot_workflow import base_diagnosis

        rows = []
        # Raw stage outcomes stay available as display-only evidence (e.g. the
        # first invalid state for the case evidence package); no authority.
        stage_outcomes = {}
        self._last_base_diagnosis_stage_outcomes = stage_outcomes

        def step(text):
            if progress:
                progress(text)

        try:
            parameter_node = self._require_context()
            step("Diagnose 0/5: MoveIt planning scene matches Slicer")
            scene_status = self.ensureMoveItSceneMatches()
            if scene_status["state"] != "not_checked":
                comparison = scene_status["comparison"] or {}
                row = base_diagnosis.scene_row(
                    comparison if "expected_count" in comparison else None,
                    unavailable_reason=str(comparison.get("summary") or ""),
                )
                if scene_status["state"] == "resynced":
                    row["detail"] += " MoveIt differed at first and was re-synchronized from Slicer."
                rows.append(row)
            step("Diagnose 1/5: whole-stroke reach at the accepted Base")
            stroke_check = getattr(self._logic, "step6CurrentBaseStrokeReachability", None)
            stroke = stroke_check(parameter_node) if callable(stroke_check) else None
            if not rows or rows[-1]["status"] != base_diagnosis.FAIL:
                rows.append(base_diagnosis.stroke_row(stroke))
            if rows[-1]["status"] != base_diagnosis.FAIL:
                step("Diagnose 2/5: PreEntry endpoint IK and collision")
                preentry = self.checkPreEntryIK(progress=progress)
                records = ()
                to_dict = getattr(preentry.payload, "to_dict", None)
                if callable(to_dict):
                    records = tuple(to_dict().get("candidate_records") or ())
                details = dict(preentry.details or {})
                status = str(details.get("diagnosticStatus") or "")
                if not preentry.success and not status:
                    status = _bounded_text(preentry.message)
                rows.append(base_diagnosis.preentry_row(status, records))
            for number, phase_id in ((3, "P1"), (4, "P2"), (5, "P3")):
                if rows[-1]["status"] == base_diagnosis.FAIL:
                    break
                step(f"Diagnose {number}/5: {phase_id} stage check")
                result = self.checkPlanningStage(phase_id, progress=progress)
                outcome = result.payload if isinstance(result.payload, Mapping) else (
                    (result.details or {}).get("stageOutcome")
                )
                if not isinstance(outcome, Mapping):
                    outcome = {"diagnostic_status": "unknown", "reason": _bounded_text(result.message)}
                stage_outcomes[phase_id] = outcome
                rows.append(base_diagnosis.stage_row(phase_id, outcome))
        except (RuntimeError, ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
            done = {row["check"] for row in rows}
            pending = next(
                (check for check in base_diagnosis.CHECK_ORDER
                 if check not in done and check != "scene_match"), None
            )
            if pending is not None:
                rows.append(base_diagnosis._row(
                    pending, base_diagnosis.FAIL, f"Check could not run: {_bounded_text(str(exc))}", "unknown"
                ))
        frame_states = self._frame_check_states()
        if frame_states:
            step("Diagnose 6: Slicer KDL vs MoveIt FK at each available state")
            rows.append(base_diagnosis.frame_row(self.frameConsistency(frame_states)))
        summary = base_diagnosis.summarize(rows)
        self._last_base_diagnosis = summary
        return RobotActionResult(
            summary["status"] != base_diagnosis.FAIL,
            "base_diagnosis_" + summary["status"].lower().replace(" ", "_"),
            "Diagnose This Base — " + summary["verdict"],
            details={"baseDiagnosis": summary},
            payload=summary,
        )

    def checkPlanningStage(
        self,
        phase_id: str,
        *,
        progress=None,
    ) -> RobotActionResult:
        """Run P1, P2, or P3 as non-executable planning evidence only."""

        phase_id = str(phase_id)
        if phase_id not in {"P1", "P2", "P3"}:
            return RobotActionResult(
                False,
                "planning_stage_invalid",
                "Planning stage must be P1, P2, or P3.",
                details={"phase_id": phase_id, "status": "unknown"},
            )
        stage_started = monotonic()
        scene_status = self.ensureMoveItSceneMatches()
        if scene_status["refuse"]:
            return RobotActionResult(
                False,
                "moveit_scene_mismatch",
                f"{phase_id} check refused: " + scene_status["message"],
                details={"phase_id": phase_id, "status": "unknown", "moveItSceneStatus": scene_status},
                payload={"diagnostic_status": "unknown", "reason": scene_status["message"]},
            )
        if phase_id == "P1":
            self._step6_stage_diagnostic_chain = {}
            try:
                parameter_node = self._require_context()
                self._replace_step6_stage_outcomes(
                    parameter_node, None, clear_all=True
                )
            except (RuntimeError, ValueError, OSError, TypeError, KeyError):
                parameter_node = None
        else:
            parameter_node = None

        try:
            context = self._step6_stage_context()
            parameter_node = context["parameter_node"]
            identity = context["identity"]
            cache = self._step6_preentry_candidate_cache
            if not isinstance(cache, Mapping):
                raise ValueError(
                    "Run PreEntry IK in this façade instance first; saved reports cannot restore its endpoint candidates."
                )
            if cache.get("identity") != identity:
                self._step6_preentry_candidate_cache = None
                self._step6_stage_diagnostic_chain = {}
                raise ValueError("The PreEntry candidate cache belongs to changed inputs.")
            session = parse_motion_diagnostic_session(
                str(parameter_node.step6MotionDiagnosticJson or "")
            )
            cached_records_fingerprint = cache.get("candidate_records_fingerprint")
            if (
                session.schema_version != "2.2"
                or session.state != "Current"
                or session.full_task_outcome.get("diagnostic_kind") != "preentry_ik"
                or fingerprint(session.to_dict()["candidate_records"])
                != cached_records_fingerprint
                or session.task_fingerprint != identity["task"]
                or session.base_fingerprint != identity["base"]
                or session.trajectory_fingerprint != identity["trajectory"]
                or session.robot_profile_fingerprint != identity["robot_profile"]
                or session.collision_audit_fingerprint
                != context["collision_audit"].audit_fingerprint
            ):
                self._step6_preentry_candidate_cache = None
                self._step6_stage_diagnostic_chain = {}
                raise ValueError("The same-instance PreEntry endpoint evidence is stale or replaced.")
            if phase_id == "P1":
                path_by_phase: dict[str, tuple[dict[str, float], ...]] = {}
                predecessor = None
                candidates = tuple(cache.get("candidates") or ())
                if not candidates:
                    outcome = {
                        "stage": "stage1_free_space",
                        "phase_id": "P1",
                        "status": "NotRun",
                        "diagnostic_status": "not_reached",
                        "reason": "PreEntry IK produced no collision-checked endpoint candidate.",
                        "route_authority": "none",
                        "endpoint_evidence": {
                            "status": "not_reached",
                            "input_identity_fingerprints": dict(identity),
                            "first_invalid_requested_state": {"status": "not_reached", "state": None},
                            "first_invalid_evaluated_state": {"status": "unknown", "state": None},
                        },
                    }
                    self._replace_step6_stage_outcomes(
                        parameter_node, outcome, expected_identity=identity
                    )
                    return RobotActionResult(
                        False, "planning_stage_blocked", outcome["reason"],
                        details={"phase_id": phase_id, "status": outcome["diagnostic_status"], "stageOutcome": outcome},
                        payload=outcome,
                    )
                candidate = candidates[0]
                start = dict(context["home_positions"])
                requested_goal = dict(candidate["positions"])
                if progress:
                    progress("P1: planning Task Home to the selected PreEntry endpoint")
                plan = self._plan_home_to_preentry_with_corridor(
                    parameter_node,
                    start,
                    requested_goal,
                    pre_entry=context["pre_entry"],
                    entry=context["entry"],
                    target=context["target"],
                    fixed_rotation_ras=candidate["orientation"].get("rotationRas"),
                    roll_deg=float(candidate["roll_deg"]),
                    planner_context="step6_diagnostic_p1_home_to_preentry",
                )
                path = tuple(
                    {name: float(point[name]) for name in JOINT_NAMES}
                    for point in (plan.waypoint_joint_vectors_si or ())
                )
                path_by_phase["P1"] = path
                plan_evidence = {
                    "status": "passed" if plan.success and path else "failed",
                    "success": bool(plan.success),
                    "message": _bounded_text(plan.message),
                    "native_message": _bounded_text(plan.native_planner_message),
                    "planner_id": str(getattr(plan, "effective_planner_id", "") or self._joint_planner_id),
                    "waypoint_count": len(path),
                    "waypoint_times_sec": [float(value) for value in plan.waypoint_times_sec],
                    "path_joint_positions_si": [dict(point) for point in path],
                }
                expected_tcp = context["pre_entry"]
                fixed_rotation = candidate["orientation"].get("rotationRas")
                roll_deg = float(candidate["roll_deg"])
                orientation_fingerprint = str(candidate["orientation"].get("fingerprint") or "")
                selected_candidate = dict(candidate)
            else:
                expected_predecessor = "P1" if phase_id == "P2" else "P2"
                chain = self._step6_stage_diagnostic_chain
                stages = chain.get("stages") if isinstance(chain, Mapping) else None
                if (
                    not isinstance(chain, Mapping)
                    or chain.get("identity") != identity
                    or not isinstance(stages, Mapping)
                    or expected_predecessor not in stages
                    or stages[expected_predecessor].get("diagnostic_status") != "passed"
                ):
                    if isinstance(chain, Mapping) and chain.get("identity") != identity:
                        self._step6_stage_diagnostic_chain = {}
                    outcome = {
                        "stage": "stage2_fixed_axis_terminal" if phase_id == "P2" else "stage3_drilling",
                        "phase_id": phase_id,
                        "status": "NotRun",
                        "diagnostic_status": "unknown",
                        "reason": f"{phase_id} requires a fresh, passed {expected_predecessor} result from this façade instance.",
                        "route_authority": "none",
                        "endpoint_evidence": {
                            "input_identity_fingerprints": dict(identity),
                            "first_invalid_requested_state": {"status": "not_reached", "state": None},
                            "first_invalid_evaluated_state": {"status": "unknown", "state": None},
                        },
                    }
                    self._replace_step6_stage_outcomes(
                        parameter_node, outcome, expected_identity=identity
                    )
                    return RobotActionResult(
                        False, "planning_stage_blocked", outcome["reason"],
                        details={"phase_id": phase_id, "status": "unknown", "stageOutcome": outcome},
                        payload=outcome,
                    )
                # A rerun invalidates this phase and every dependent phase.
                stages = {key: value for key, value in stages.items() if key < phase_id}
                self._step6_stage_diagnostic_chain = {**dict(chain), "stages": stages}
                selected_candidate = dict(chain["candidate"])
                path_by_phase = {
                    key: tuple(value["path"])
                    for key, value in stages.items()
                }
                predecessor_path = tuple(stages[expected_predecessor]["path"])
                if not predecessor_path:
                    raise ValueError(f"{expected_predecessor} has no retained path endpoint.")
                start = dict(predecessor_path[-1])
                if phase_id == "P2":
                    start_tcp = context["pre_entry"]
                    expected_tcp = context["entry"]
                    phase_name = "terminal_contact"
                else:
                    start_tcp = context["entry"]
                    expected_tcp = context["target"]
                    phase_name = "drilling"
                fixed_rotation = selected_candidate["orientation"].get("rotationRas")
                roll_deg = float(selected_candidate["roll_deg"])
                orientation_fingerprint = str(selected_candidate["orientation"].get("fingerprint") or "")
                if progress:
                    progress(f"{phase_id}: planning the exact {expected_predecessor} endpoint to {phase_name} endpoint")
                plan = self._bridge.plan_moveit_cartesian_path(
                    entry_ras_mm=start_tcp,
                    target_ras_mm=expected_tcp,
                    sample_count=max(3, int(context["parameter_node"].robotMotionPlanSampleCount)),
                    base_transform=context["parameter_node"].robotBaseTransform,
                    avoid_collisions=False,
                    minimum_fraction=0.99,
                    start_joint_positions_si=start,
                    axial_roll_start_deg=roll_deg,
                    axial_roll_end_deg=roll_deg,
                    fixed_rotation_ras=fixed_rotation,
                    position_axis_only=True,
                )
                path = tuple(
                    {name: float(point[name]) for name in JOINT_NAMES}
                    for point in (plan.waypoint_joint_vectors_si or ())
                )
                path_by_phase[phase_id] = path
                plan_evidence = {
                    "status": "passed" if plan.success and path else "failed",
                    "success": bool(plan.success),
                    "message": _bounded_text(plan.message),
                    "completion_fraction": float(plan.fraction),
                    "coordinate_frame": str(plan.coordinate_frame),
                    "start_position_error_mm": plan.start_position_error_mm,
                    "start_orientation_error_deg": plan.start_orientation_error_deg,
                    "last_valid_waypoint_index": int(plan.last_valid_waypoint_index),
                    "last_valid_joint_positions_si": plan.last_valid_joint_positions_si,
                    "first_invalid_requested_index": int(plan.first_invalid_requested_index),
                    "first_invalid_tcp_world_ras_mm": plan.first_invalid_ras_mm,
                    "first_invalid_joint_positions_si": plan.first_invalid_joint_positions_si,
                    "first_invalid_collision_pairs": [list(pair) for pair in plan.first_invalid_collision_pairs],
                    "failure_classification": str(plan.failure_classification or "unknown"),
                    "waypoint_count": len(path),
                    "waypoint_times_sec": [float(value) for value in plan.waypoint_times_sec],
                    "path_joint_positions_si": [dict(point) for point in path],
                }

            end_state = dict(path[-1]) if path else None
            endpoint_evaluation = (
                self._evaluate_step6_tcp_endpoint(
                    context["parameter_node"],
                    end_state,
                    expected_tcp_world_ras_mm=expected_tcp,
                    expected_drill_axis_world_ras_unit=context["drill_axis"],
                    # Burr may touch the target tooth at Entry and while drilling
                    # (same pair the native contact-phase guard allows).
                    allowed_contact_pairs=self._step6_contact_phase_allowed_pairs(
                        context["parameter_node"], phase_id
                    ),
                )
                if end_state is not None
                else {"status": "not_reached", "position_residual_mm": None, "drilling_axis_residual_deg": None}
            )
            if phase_id == "P1":
                path_by_phase = {"P1": path}
            guard = self._step6_stage_guard_evidence(context, path_by_phase)
            if phase_id == "P3":
                shortened_stage = self._truncate_p3_stage_for_spindle_collision(
                    context, path_by_phase, path, guard
                )
                if shortened_stage is not None:
                    path, path_by_phase, guard, endpoint_evaluation, truncation = shortened_stage
                    end_state = dict(path[-1])
                    plan_evidence.update({
                        "waypoint_count": len(path),
                        "completion_fraction": truncation["completed_depth_mm"]
                        / truncation["requested_depth_mm"]
                        if truncation["requested_depth_mm"] > 0 else 0.0,
                        "path_joint_positions_si": [dict(point) for point in path],
                        "drilling_truncation": truncation,
                    })
                    self._drilling_truncation = dict(truncation)
                    show_remainder = getattr(self._bridge, "show_unreachable_drilling_remainder", None)
                    if callable(show_remainder):
                        show_remainder(*truncation["unreachable_segment_ras_mm"])
            mouth_portal = (
                self._step6_mouth_portal_gate(context["parameter_node"], path)
                if phase_id == "P1" and path
                else None
            )
            identity_after = self.plannerComparisonIdentity()
            identity_current = identity_after == identity
            if not identity_current:
                self._step6_preentry_candidate_cache = None
                self._step6_stage_diagnostic_chain = {}
            plan_passed = bool(plan.success and path) and not self._mouth_portal_blocks(mouth_portal)
            if not identity_current or endpoint_evaluation.get("status") == "unknown" or guard.get("status") == "unknown":
                diagnostic_status = "unknown"
            elif not plan_passed or endpoint_evaluation.get("status") != "passed" or guard.get("status") != "passed":
                diagnostic_status = "failed"
            else:
                diagnostic_status = "passed"
            label = {
                "P1": "stage1_free_space",
                "P2": "stage2_fixed_axis_terminal",
                "P3": "stage3_drilling",
            }[phase_id]
            reason = (
                "The requested stage path, endpoint FK, and composed-prefix guard all passed."
                if diagnostic_status == "passed"
                else "Input identity changed during planning; retained measurements are stale."
                if not identity_current
                else (
                    "Mouth portal gate failed: "
                    + str(mouth_portal.get("reason") or mouth_portal.get("message") or "")
                )
                if self._mouth_portal_blocks(mouth_portal)
                else str(plan.message or guard.get("reason") or "Stage checks did not pass.")
            )
            guard_invalid = guard.get("first_invalid_requested")
            guard_evaluated = guard.get("first_invalid_evaluated")
            first_invalid_requested = (
                guard_invalid
                if isinstance(guard_invalid, Mapping)
                and guard_invalid.get("status") == "failed"
                else {
                    "status": "failed" if plan_evidence.get("first_invalid_requested_index", -1) >= 0 or plan_evidence.get("first_invalid_tcp_world_ras_mm") is not None else "not_reached",
                    "state": {
                        "cartesian_waypoint_index": plan_evidence.get("first_invalid_requested_index"),
                        "tcp_world_ras_mm": plan_evidence.get("first_invalid_tcp_world_ras_mm"),
                    }
                    if plan_evidence.get("first_invalid_requested_index", -1) >= 0 or plan_evidence.get("first_invalid_tcp_world_ras_mm") is not None
                    else None,
                }
            )
            first_invalid_evaluated = (
                guard_evaluated
                if isinstance(guard_evaluated, Mapping)
                and guard_evaluated.get("status") == "failed"
                else {"status": "unknown", "state": None}
            )
            path_fingerprint = fingerprint([dict(point) for point in path])
            endpoint_fingerprint = fingerprint(
                {
                    "start": start,
                    "requested_goal": requested_goal if phase_id == "P1" else expected_tcp,
                    "end": end_state,
                    "orientation": orientation_fingerprint,
                }
            )
            endpoint_evidence = {
                "status": diagnostic_status,
                "input_identity_fingerprints": dict(identity),
                "identity_after": dict(identity_after),
                "phase_start_joint_positions_si": dict(start),
                "requested_goal": (
                    {"joint_positions_si": dict(requested_goal), "tcp_world_ras_mm": expected_tcp}
                    if phase_id == "P1"
                    else {"tcp_world_ras_mm": expected_tcp}
                ),
                "phase_end_joint_positions_si": end_state if plan_passed else None,
                "last_valid": guard.get("last_valid"),
                "first_invalid_requested_state": first_invalid_requested,
                "first_invalid_evaluated_state": first_invalid_evaluated,
                "endpoint_fk": endpoint_evaluation,
                "phase_guard": guard,
                "plan": plan_evidence,
                "mouth_portal_gate": mouth_portal,
                "path_joint_positions_si": [dict(point) for point in path],
                "path_fingerprint": path_fingerprint,
                "endpoint_fingerprint": endpoint_fingerprint,
                "orientation_fingerprint": orientation_fingerprint,
                "guard_policy_fingerprint": self._strict_guard_policy_fingerprint(),
                "duration_sec": max(0.0, monotonic() - stage_started),
                "route_authority": "none",
            }
            outcome = {
                "stage": label,
                "phase_id": phase_id,
                "status": {
                    "passed": "Passed",
                    "failed": "Failed",
                    "unknown": "Unknown",
                    "not_reached": "NotRun",
                }[diagnostic_status],
                "diagnostic_status": diagnostic_status,
                "reason": _bounded_text(reason),
                "waypoint_count": len(path),
                "completion_fraction": float(getattr(plan, "fraction", 1.0 if plan.success else 0.0)),
                "route_authority": "none",
                "endpoint_evidence": endpoint_evidence,
            }
            if identity_current:
                if diagnostic_status == "passed":
                    chain = self._step6_stage_diagnostic_chain
                    if phase_id == "P1" or not isinstance(chain, Mapping):
                        chain = {"identity": dict(identity), "candidate": selected_candidate, "stages": {}}
                    stages = dict(chain.get("stages") or {})
                    stages[phase_id] = {
                        "diagnostic_status": diagnostic_status,
                        "route_authority": "none",
                        "path": path,
                        "end": end_state,
                        "endpoint_evidence": endpoint_evidence,
                    }
                    self._step6_stage_diagnostic_chain = {
                        **dict(chain), "identity": dict(identity), "candidate": selected_candidate, "stages": stages
                    }
                self._replace_step6_stage_outcomes(
                    parameter_node, outcome, expected_identity=identity
                )
            return RobotActionResult(
                diagnostic_status == "passed",
                "planning_stage_passed" if diagnostic_status == "passed" else "planning_stage_incomplete",
                f"{phase_id}: {reason}",
                details={"phase_id": phase_id, "status": diagnostic_status, "stageOutcome": outcome},
                payload=outcome,
            )
        except (RuntimeError, ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
            try:
                current_identity = self.plannerComparisonIdentity()
                cache = self._step6_preentry_candidate_cache
                chain = self._step6_stage_diagnostic_chain
                if isinstance(cache, Mapping) and cache.get("identity") != current_identity:
                    self._step6_preentry_candidate_cache = None
                if isinstance(chain, Mapping) and chain.get("identity") != current_identity:
                    self._step6_stage_diagnostic_chain = {}
            except Exception:
                self._step6_stage_diagnostic_chain = {}
                self._step6_preentry_candidate_cache = None
            return RobotActionResult(
                False,
                "planning_stage_blocked",
                str(exc),
                details={"phase_id": phase_id, "status": "unknown"},
            )

    def _step6_contact_phase_allowed_pairs(self, parameter_node, phase_id: str) -> tuple:
        """Burr<->target-tooth only, and only for P2 (Entry) and P3 (drilling)."""
        if phase_id not in ("P2", "P3"):
            return ()
        name_of = getattr(self._logic, "step6TargetCollisionObjectName", None)
        target = str(name_of(parameter_node) or "") if callable(name_of) else ""
        return (("burr", target),) if target else ()

    @staticmethod
    def _allowed_only_static_contacts(message: str, allowed_contact_pairs) -> Optional[list]:
        """Return reported contacts if all are allowed pairs, else None."""
        allowed = {frozenset((str(a), str(b))) for a, b in allowed_contact_pairs}
        if not allowed or "contacts=" not in message or "more)" in message:
            return None
        pairs = []
        for item in message.split("contacts=", 1)[1].split(", "):
            bodies = item.strip().split("<->")
            if len(bodies) != 2 or frozenset(bodies) not in allowed:
                return None
            pairs.append(bodies)
        return pairs or None

    def _evaluate_step6_tcp_endpoint(
        self,
        parameter_node,
        positions_si: Mapping[str, float],
        *,
        expected_tcp_world_ras_mm: Optional[Sequence[float]] = None,
        expected_drill_axis_world_ras_unit: Optional[Sequence[float]] = None,
        check_static: bool = True,
        allowed_contact_pairs: Sequence[Sequence[str]] = (),
    ) -> dict[str, object]:
        """Evaluate static validity and FK, plus exact world-RAS endpoint evidence when supplied.

        ``allowed_contact_pairs`` (operator policy 2026-10-02): for terminal
        contact/drilling endpoints the burr may touch the target tooth. If MoveIt
        rejects the static state and every reported contact is an allowed pair
        (and the contact list is not truncated), the endpoint continues to FK as
        ``allowed_contact``. Any other contact still fails.
        """

        evaluation: dict[str, object] = {
            "step6_tcp_endpoint_evaluation_schema_version": "1.0",
            "status": "not_reached",
            "static_state_validity": {
                "status": "not_reached",
                "authoritative": False,
                "message": "Static joint-state validity was not requested.",
            },
            "collision": {"status": "not_reached", "pairs": None},
            "fk": {
                "status": "not_reached",
                "message": "FK was not reached.",
                "pose_world_ras_mm": None,
            },
            "position_residual_mm": None,
            "drilling_axis_residual_deg": None,
        }
        if (
            expected_tcp_world_ras_mm is None
            and expected_drill_axis_world_ras_unit is None
            and not check_static
        ):
            evaluation["status"] = "unknown"
            evaluation["fk"]["message"] = (
                "FK not reached: static validity was not requested."
            )
            return evaluation
        if check_static:
            valid, message, authoritative = (
                self._bridge.check_moveit_static_joint_state(positions_si)
            )
            validity_status = (
                "unknown"
                if not authoritative
                else "passed"
                if valid
                else "failed"
            )
            evaluation["static_state_validity"] = {
                "status": validity_status,
                "authoritative": bool(authoritative),
                "message": str(message or ""),
            }
            if not authoritative:
                evaluation["status"] = "unknown"
                evaluation["collision"] = {"status": "unknown", "pairs": None}
                evaluation["fk"]["message"] = (
                    "FK not reached: static validity unavailable."
                )
                return evaluation
            if not valid:
                contact_pairs = self._allowed_only_static_contacts(
                    str(message or ""), allowed_contact_pairs
                )
                if contact_pairs is None:
                    evaluation["status"] = "failed"
                    evaluation["collision"] = {"status": "unknown", "pairs": None}
                    evaluation["fk"]["message"] = "FK not reached: static state invalid."
                    return evaluation
                evaluation["static_state_validity"]["status"] = "allowed_contact"
                evaluation["collision"] = {"status": "allowed_contact", "pairs": contact_pairs}
            else:
                evaluation["collision"] = {"status": "clear", "pairs": []}

        fk_ok, fk_message, raw_pose = self._bridge.compute_tcp_pose_world_ras_mm(
            positions_si,
            base_transform=parameter_node.robotBaseTransform,
        )
        fk_message = str(fk_message or "")
        if not fk_ok or raw_pose is None:
            evaluation["status"] = "unknown"
            evaluation["fk"].update(
                status="unknown",
                message=fk_message or "Authoritative TCP FK unavailable.",
            )
            return evaluation
        pose = tuple(
            tuple(float(raw_pose[row][column]) for column in range(4))
            for row in range(4)
        )
        if not all(isfinite(value) for row in pose for value in row):
            evaluation["status"] = "unknown"
            evaluation["fk"].update(
                status="unknown",
                message=fk_message or "Authoritative TCP FK returned a non-finite pose.",
            )
            return evaluation

        evaluation["fk"].update(
            status="passed", message=fk_message, pose_world_ras_mm=pose
        )
        if expected_tcp_world_ras_mm is None and expected_drill_axis_world_ras_unit is None:
            evaluation["status"] = (
                "passed"
                if evaluation["static_state_validity"]["status"] == "passed"
                else "unknown"
            )
            return evaluation
        if expected_tcp_world_ras_mm is None or expected_drill_axis_world_ras_unit is None:
            evaluation["status"] = "unknown"
            return evaluation
        expected_position = tuple(
            float(expected_tcp_world_ras_mm[i]) for i in range(3)
        )
        expected_axis = tuple(
            float(expected_drill_axis_world_ras_unit[i]) for i in range(3)
        )
        if not all(isfinite(value) for value in (*expected_position, *expected_axis)):
            evaluation["status"] = "unknown"
            return evaluation

        position_residual_mm = sqrt(
            sum(
                (pose[index][3] - expected_position[index]) ** 2
                for index in range(3)
            )
        )
        if not isfinite(position_residual_mm):
            evaluation["status"] = "unknown"
            return evaluation
        evaluation["position_residual_mm"] = float(position_residual_mm)
        expected_axis_length = sqrt(sum(value * value for value in expected_axis))
        actual_axis = tuple(pose[row][2] for row in range(3))
        actual_axis_length = sqrt(sum(value * value for value in actual_axis))
        if expected_axis_length <= 1.0e-12 or actual_axis_length <= 1.0e-12:
            evaluation["status"] = "failed"
            evaluation["fk"].update(
                status="failed", failure_reason="invalid_tool_axis"
            )
            return evaluation
        axis_cosine = max(
            -1.0,
            min(
                1.0,
                sum(a * e for a, e in zip(actual_axis, expected_axis))
                / (actual_axis_length * expected_axis_length),
            ),
        )
        axis_residual_deg = degrees(acos(axis_cosine))
        if not isfinite(axis_residual_deg):
            evaluation["status"] = "unknown"
            return evaluation
        evaluation["drilling_axis_residual_deg"] = float(axis_residual_deg)
        evaluation["status"] = (
            "failed"
            if (
                position_residual_mm
                > _default_bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
                or axis_residual_deg
                > _default_bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
            )
            else "passed"
        )
        return evaluation

    def _goal1_pre_entry_ik_candidates(
        self,
        parameter_node,
        pre_entry: Sequence[float],
        entry: Sequence[float],
        target: Sequence[float],
        home_positions: Mapping[str, float],
        *,
        include_workspace_seeds: bool = True,
        avoid_collisions: bool = True,
        require_generic_static: bool = True,
        fixed_rotation_ras: Optional[Sequence[Sequence[float]]] = None,
        progress=None,
        workspace_seed_evidence: Optional[Sequence[Mapping[str, object]]] = None,
        seed_collector: Optional[Callable[[dict[str, object]], None]] = None,
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Return bounded PreEntry endpoints for the five-DOF drill task.

        Routine Goal 1 retains its collision-aware direct-plus-workspace search.
        Optional historical hints and the collector are used only by the
        standalone endpoint diagnostic; the ordinary planning defaults and
        seed search are unchanged.
        """

        candidates: list[dict[str, object]] = []
        failures: list[str] = []
        joint_diagnostic_fn = getattr(
            self._bridge,
            "moveit_joint_goal_diagnostics",
            _default_bridge.moveit_joint_goal_diagnostics,
        )
        seeds: list[
            tuple[str, Mapping[str, float], Optional[int], str, Mapping[str, object]]
        ] = [
            ("direct", home_positions, None, "task_home", {})
        ]
        if workspace_seed_evidence is not None:
            for evidence in workspace_seed_evidence:
                if len(seeds) >= GOAL1_MAX_IK_SEEDS:
                    break
                names = tuple(evidence.get("joint_names", ()))
                values = tuple(evidence.get("joint_positions_si", ()))
                if names != JOINT_NAMES or len(values) != len(JOINT_NAMES):
                    continue
                seeds.append(
                    (
                        "historical_workspace_hint",
                        canonicalize_planning_joint_positions(
                            dict(zip(names, values))
                        ),
                        int(evidence.get("sample_index", len(seeds))),
                        "historical_workspace_hint",
                        {
                            "historical_evidence_identity_match": bool(
                                evidence.get("historical_evidence_identity_match")
                            ),
                            "historical_home_connectivity_status": str(
                                evidence.get("historical_home_connectivity_status")
                                or "unknown"
                            ),
                            "current_home_connectivity_status": "NotEvaluated",
                        },
                    )
                )
        elif include_workspace_seeds:
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
                        "workspace_seed",
                        {},
                    )
                )
        seen_solutions: set[tuple[float, ...]] = set()
        for seed_index, (
            route_type,
            seed_positions,
            seed_sample_index,
            seed_provenance,
            seed_metadata,
        ) in enumerate(seeds):
            if progress:
                progress("Searching collision-aware PreEntry IK", seed_index, len(seeds))
            seed_record: dict[str, object] = {
                "candidate_index": int(seed_index),
                "seed_provenance": str(seed_provenance),
                "route_type": str(route_type),
                "sample_index": seed_sample_index,
                "seed_joint_positions_si": {
                    name: float(seed_positions[name]) for name in JOINT_NAMES
                },
                **dict(seed_metadata),
                "solver_success": False,
                "solver_message": "",
                "termination_reason": "not_attempted",
                "iteration_count": None,
                "collision_check_status": "not_attempted",
                "task_jacobian_condition_ratio": None,
                "position_residual_mm": None,
                "drilling_axis_residual_deg": None,
                "collision_pairs": [],
                "best_joint_positions_si": None,
                "static_state_validity_status": "not_attempted",
                "static_state_validity_message": "",
                "authoritative_fk_status": "not_attempted",
                "authoritative_position_residual_mm": None,
                "authoritative_drilling_axis_residual_deg": None,
                "mechanical_joint_limit_margins": None,
                "reviewed_task_joint_limit_margins": None,
                "endpoint_collision_clear": False,
                "endpoint_check_status": "NotRun",
                "plan_authority": False,
                "waypoint_count": 0,
            }

            def finish_seed(classification: str) -> None:
                seed_record["failure_classification"] = str(classification)
                if seed_collector is not None:
                    seed_collector(seed_record)

            axial_roll_deg = LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG
            pose = self._bridge.tool_pose_matrices_world_mm(
                entry,
                target,
                2,
                axial_roll_start_deg=axial_roll_deg,
                axial_roll_end_deg=axial_roll_deg,
                fixed_rotation_ras=fixed_rotation_ras,
            )[0]
            for index, value in enumerate(pre_entry):
                pose.SetElement(index, 3, float(value))
            ok, message, _goal = self._bridge.set_moveit_tcp_goal_matrix(pose)
            if not ok:
                failures.append(f"canonical TCP goal: {message}")
                seed_record["solver_message"] = str(message)
                finish_seed("canonical_tcp_goal_rejected")
                continue
            solve_position_axis = getattr(
                self._bridge,
                "solve_moveit_tcp_position_axis_goal",
                _default_bridge.solve_moveit_tcp_position_axis_goal,
            )
            ok, message, positions, ik_diagnostic = solve_position_axis(
                seed_joint_positions_si=seed_positions,
                avoid_collisions=bool(avoid_collisions),
            )
            if not isinstance(ik_diagnostic, Mapping):
                ik_diagnostic = {}
            seed_record.update(
                {
                    "solver_success": bool(ok),
                    "solver_message": str(message or ""),
                    "termination_reason": str(
                        ik_diagnostic.get("termination_reason") or "unknown"
                    ),
                    "iteration_count": ik_diagnostic.get("iteration_count"),
                    "collision_check_status": str(
                        ik_diagnostic.get("collision_check_status") or "unknown"
                    ),
                    "task_jacobian_condition_ratio": ik_diagnostic.get(
                        "task_jacobian_condition_ratio"
                    ),
                    "position_residual_mm": ik_diagnostic.get(
                        "position_residual_mm"
                    ),
                    "drilling_axis_residual_deg": ik_diagnostic.get(
                        "drilling_axis_residual_deg"
                    ),
                    "collision_pairs": [
                        list(pair)
                        for pair in ik_diagnostic.get("collision_pairs", ())
                    ],
                    "best_joint_positions_si": (
                        dict(ik_diagnostic["best_joint_positions_si"])
                        if isinstance(
                            ik_diagnostic.get("best_joint_positions_si"), Mapping
                        )
                        else None
                    ),
                }
            )
            if not ok:
                residual = ""
                if ik_diagnostic:
                    residual = (
                        f" (best position={ik_diagnostic.get('position_residual_mm')} mm, "
                        f"axis={ik_diagnostic.get('drilling_axis_residual_deg')} deg, "
                        f"collisions={ik_diagnostic.get('collision_pairs') or ()})"
                    )
                failures.append(f"canonical TCP position-axis IK: {message}{residual}")
                finish_seed("position_axis_ik_failed")
                continue
            direction = tuple(
                float(target[index]) - float(entry[index])
                for index in range(3)
            )
            direction_length = sqrt(sum(value * value for value in direction))
            tool_axis = (
                tuple(value / direction_length for value in direction)
                if direction_length > 1.0e-12
                else (0.0, 0.0, 0.0)
            )
            endpoint_evaluation = self._evaluate_step6_tcp_endpoint(
                parameter_node,
                positions,
                expected_tcp_world_ras_mm=pre_entry,
                expected_drill_axis_world_ras_unit=tool_axis,
                check_static=require_generic_static,
            )
            seed_record["endpoint_evaluation"] = endpoint_evaluation
            static_validity = endpoint_evaluation["static_state_validity"]
            if require_generic_static:
                validity_message = str(static_validity["message"] or "")
                if not static_validity["authoritative"]:
                    failures.append(
                        "canonical TCP IK state could not be audited: "
                        + validity_message
                    )
                    seed_record["static_state_validity_status"] = "Unavailable"
                    seed_record["static_state_validity_message"] = validity_message
                    finish_seed("static_state_validity_unavailable")
                    continue
                if static_validity["status"] != "passed":
                    failures.append(
                        "canonical TCP IK state is invalid: " + validity_message
                    )
                    seed_record["static_state_validity_status"] = "Invalid"
                    seed_record["static_state_validity_message"] = validity_message
                    finish_seed("static_state_invalid")
                    continue
                seed_record["static_state_validity_status"] = "Valid"
                seed_record["static_state_validity_message"] = validity_message
            else:
                seed_record["static_state_validity_status"] = "NotRequested"
            seed_record["returned_joint_positions_si"] = dict(positions)
            fk = endpoint_evaluation["fk"]
            fk_message = str(fk["message"] or "")
            authoritative_pose = fk["pose_world_ras_mm"]
            if fk.get("failure_reason") == "invalid_tool_axis":
                failures.append(
                    "canonical TCP IK authoritative FK has no tool axis."
                )
                seed_record["authoritative_fk_status"] = "InvalidToolAxis"
                seed_record["authoritative_fk_message"] = fk_message
                finish_seed("authoritative_fk_invalid_tool_axis")
                continue
            if fk["status"] != "passed" or authoritative_pose is None:
                failures.append(
                    "canonical TCP IK authoritative FK failed: " + fk_message
                )
                seed_record["authoritative_fk_status"] = "Failed"
                seed_record["authoritative_fk_message"] = fk_message
                finish_seed("authoritative_fk_failed")
                continue
            seed_record["authoritative_fk_status"] = "Passed"
            seed_record["authoritative_fk_message"] = fk_message
            rotation = tuple(
                tuple(float(authoritative_pose[row][column]) for column in range(3))
                for row in range(3)
            )
            position_residual_mm = endpoint_evaluation["position_residual_mm"]
            axis_residual_deg = endpoint_evaluation[
                "drilling_axis_residual_deg"
            ]
            if position_residual_mm is None or axis_residual_deg is None:
                failures.append(
                    "canonical TCP IK authoritative FK residuals are unavailable."
                )
                seed_record["authoritative_fk_status"] = "Failed"
                finish_seed("authoritative_fk_failed")
                continue
            seed_record["authoritative_position_residual_mm"] = float(
                position_residual_mm
            )
            seed_record["authoritative_drilling_axis_residual_deg"] = float(
                axis_residual_deg
            )
            if endpoint_evaluation["status"] == "failed":
                failures.append(
                    "canonical TCP IK authoritative FK exceeds tolerance: "
                    f"position={position_residual_mm:.6g} mm, "
                    f"axis={axis_residual_deg:.6g} deg."
                )
                seed_record["authoritative_fk_status"] = "OutsideTolerance"
                finish_seed("authoritative_fk_outside_tolerance")
                continue
            if endpoint_evaluation["status"] != "passed":
                failures.append(
                    "canonical TCP IK authoritative FK residuals are unavailable."
                )
                seed_record["authoritative_fk_status"] = "Failed"
                finish_seed("authoritative_fk_failed")
                continue
            ik_diagnostic = {
                **dict(ik_diagnostic),
                "authoritative_position_residual_mm": position_residual_mm,
                "authoritative_drilling_axis_residual_deg": axis_residual_deg,
            }
            axial_roll_deg = self._derived_axial_roll_deg(rotation, tool_axis)
            orientation_commitment = self._tool_orientation_commitment(
                authoritative_pose,
                entry_ras_mm=entry,
                target_ras_mm=target,
                axial_roll_deg=axial_roll_deg,
            )
            joint_diagnostic = joint_diagnostic_fn(home_positions, positions)
            canonical_solution = canonicalize_planning_joint_positions(
                joint_diagnostic["submitted_goal"]
            )
            solution_identity = tuple(
                round(canonical_solution[name], 9) for name in JOINT_NAMES
            )
            if solution_identity in seen_solutions:
                seed_record["endpoint_check_status"] = "DuplicateSolution"
                finish_seed("duplicate_solution")
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
                    "pose": authoritative_pose,
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
                    "positionAxisIkDiagnostic": dict(ik_diagnostic),
                    "score": (
                        max(normalized_deltas, default=0.0),
                        sum(value * value for value in normalized_deltas),
                        0.0,
                    ),
                }
            )
            seed_record["endpoint_collision_clear"] = bool(
                seed_record["collision_check_status"] == "clear"
            )
            seed_record["endpoint_check_status"] = (
                "Passed"
                if seed_record["static_state_validity_status"] == "Valid"
                and seed_record["endpoint_collision_clear"]
                else "Unverified"
                if seed_record["static_state_validity_status"] == "Valid"
                else "StaticCheckNotRequested"
            )
            seed_record["failure_classification"] = (
                "preentry_ik_endpoint_checks_pass_route_not_run"
                if seed_record["endpoint_check_status"] == "Passed"
                else "preentry_ik_endpoint_collision_check_unverified"
                if seed_record["endpoint_check_status"] == "Unverified"
                else "preentry_ik_static_check_not_requested"
            )
            if seed_collector is not None:
                seed_collector(seed_record)
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
                    for name in JOINT_NAMES
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

    def _goal1_identity_fields(self) -> dict[str, object]:
        """Input identity of a planned route (same fields as PreEntry IK evidence)."""
        try:
            identity = self.plannerComparisonIdentity()
        except (RuntimeError, ValueError, KeyError, TypeError, AttributeError):
            return {}
        return {
            "task_identity_fingerprint": identity.get("task"),
            "base_identity_fingerprint": identity.get("base"),
            "home_identity_fingerprint": identity.get("home"),
            "trajectory_identity_fingerprint": identity.get("trajectory"),
            "robot_profile_identity_fingerprint": identity.get("robot_profile"),
            "collision_scene_identity_fingerprint": identity.get("collision_audit"),
            "branch_id": identity.get("branch_id"),
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
        pre_entry, entry = self._logic.step6ApproachPoints(parameter_node, snapshot)
        target_conditioning = {
            "world_frame": "RAS_mm",
            "pre_entry_world_ras_mm": tuple(float(value) for value in pre_entry),
            "entry_world_ras_mm": tuple(float(value) for value in entry),
            "target_world_ras_mm": tuple(
                float(value) for value in snapshot.target_ras_mm
            ),
            "standoff_mm": float(parameter_node.step6ApproachStandoffMm),
        }
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
        warning_summary = self._guide_clearance_warning_summary(
            selected.get("guideClearanceWarnings", ())
        )
        warning_status = (
            "CompletedWithWarnings"
            if str(full_task_status) == "Complete"
            and warning_summary["guideClearanceWarningCount"]
            else str(full_task_status)
        )
        current_route_key = self._goal1_route_key(selected)
        plan_selection = self._diagnostic_plan_selection_override
        if plan_selection is None:
            plan_selection_payload = {
                "state": "auto",
                "candidate_index": int(selected_index),
                "route_key": current_route_key,
            }
        else:
            plan_selection_payload = dict(plan_selection)
            if not plan_selection_payload.get("route_key"):
                plan_selection_payload["route_key"] = current_route_key
            if plan_selection_payload.get("route_key") == current_route_key:
                plan_selection_payload["candidate_index"] = int(selected_index)
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
                    "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                    "routePlannerRevision": "stage1-frame-full-chain-v7-guide-contact-warning-retract",
                    "stage2ContactPolicy": "phase_guard_evidence_based_contact_warning_v2",
                    "maximumClearanceWaypoints": GOAL1_MAX_CLEARANCE_WAYPOINTS,
                    "maximumIkSeeds": GOAL1_MAX_IK_SEEDS,
                    "jointPlannerId": self._joint_planner_id,
                    "effectiveJointPlannerId": self._effective_joint_planner_id,
                    "jointPlannerAlgorithm": STEP6_JOINT_PLANNER_ALGORITHMS[
                        self._joint_planner_id
                    ],
                    "jointPlanningAttempts": self._joint_planning_attempts,
                    "jointPlanningTimeSec": self._joint_planning_time_sec,
                    "approximateIkEnabled": STEP6_APPROXIMATE_IK_ENABLED,
                    "cartesianPlanningEnabled": STEP6_CARTESIAN_PLANNING_ENABLED,
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
                    **self._guide_clearance_warning_summary(
                        record
                        for record in warning_summary["guideClearanceWarnings"]
                        if record.get("phase") == "approach"
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
                    **self._guide_clearance_warning_summary(
                        record
                        for record in warning_summary["guideClearanceWarnings"]
                        if record.get("phase") == "terminal_contact"
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
                    **self._guide_clearance_warning_summary(
                        record
                        for record in warning_summary["guideClearanceWarnings"]
                        if record.get("phase") == "drilling"
                    ),
                },
            ),
            full_task_outcome={
                # r16 (2026-10-03): stamp the planned route with its input
                # identity, like PreEntry IK evidence, for cross-case traceability.
                **self._goal1_identity_fields(),
                "status": warning_status,
                "selected_candidate_index": int(selected_index),
                "drill_tool_frame_policy": DRILL_TOOL_FRAME_POLICY,
                "tool_orientation_fingerprint": str(
                    selected.get("tool_orientation_fingerprint") or ""
                ),
                "tool_axis_ras": list(selected.get("tool_axis_ras") or ()),
                "axial_frame_roll_deg": float(
                    selected.get("axial_roll_deg", LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG)
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
                "target_conditioning": target_conditioning,
                "template_collision_exclusion_active": bool(
                    self._template_collision_exclusion_active
                ),
                "template_collision_excluded_object_ids": list(
                    self._template_collision_excluded_object_ids
                ),
                "session_anatomy_review_override": dict(self.anatomyReviewState),
                "collision_evidence_scope": (
                    "FunctionalSimulationWithoutUnresolvedStep5CTemplate"
                    if self._template_collision_exclusion_active
                    else "ResearchSimulationWithSessionAnatomyOverride"
                    if self.anatomyReviewState.get("active")
                    else "AuthoritativeCompleteScene"
                ),
                "plan_selection": plan_selection_payload,
                "joint_planner_id": self._effective_joint_planner_id,
                "requested_joint_planner_id": self._joint_planner_id,
                "joint_planner_algorithm": STEP6_JOINT_PLANNER_ALGORITHMS[
                    self._joint_planner_id
                ],
                "joint_planning_attempts": self._joint_planning_attempts,
                "joint_planning_time_sec": self._joint_planning_time_sec,
                "approximate_ik_enabled": STEP6_APPROXIMATE_IK_ENABLED,
                "cartesian_planning_enabled": STEP6_CARTESIAN_PLANNING_ENABLED,
                **warning_summary,
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
            **DENTORobotWorkflowFacade._guide_clearance_warning_summary(
                chain.get("guideClearanceWarnings", ())
            ),
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
                    "sequential_ik_recovery_attempted": bool(
                        getattr(failed_plan, "sequential_ik_recovery_attempted", False)
                    ),
                    "sequential_ik_failure_index": int(
                        getattr(failed_plan, "sequential_ik_failure_index", -1)
                    ),
                    "sequential_ik_failure_message": _bounded_text(
                        getattr(failed_plan, "sequential_ik_failure_message", "")
                    ),
                }
            )
        # A Cartesian failure may supply its own first-invalid pose after the
        # composed index is derived above. Only replace it when the later
        # phase-guard replay has actual evidence, otherwise preserve the
        # solver's retained first-invalid state.
        guard_tcp_ras = chain.get("firstInvalidTcpRasMm")
        guard_joint_positions = chain.get("firstInvalidJointPositionsSi")
        guard_first_body = str(chain.get("guardFirstBody") or "")
        guard_second_body = str(chain.get("guardSecondBody") or "")
        if any((guard_tcp_ras, guard_joint_positions, guard_first_body, guard_second_body)):
            result.update(
                {
                    "first_invalid_joint_positions_si": guard_joint_positions,
                    "first_invalid_ras_mm": guard_tcp_ras,
                    "guard_first_body": guard_first_body,
                    "guard_second_body": guard_second_body,
                    "guard_minimum_world_distance_m": chain.get(
                        "guardMinimumWorldDistanceM"
                    ),
                    "guard_nearest_point_first_base_m": chain.get(
                        "guardNearestPointFirstBaseM"
                    ),
                    "guard_nearest_point_second_base_m": chain.get(
                        "guardNearestPointSecondBaseM"
                    ),
                }
            )
        return result

    def planApproachPhase(
        self,
        *,
        planner_id: str = STEP6_JOINT_PLANNER_ID,
        planning_attempts: int = STEP6_JOINT_PLANNING_ATTEMPTS,
        planning_time_sec: float = GOAL1_DIRECT_PLANNING_TIME_SEC,
        progress=None,
    ) -> RobotActionResult:
        """Plan Approach; warn when the case policy is below the project default.

        S6-LIVE-01 2026-10-05: a case saved with 1 MoveIt attempt (default 5)
        turned a reliable configuration into a failing one. Not blocking.
        """
        scene_status = self.ensureMoveItSceneMatches()
        if scene_status["refuse"]:
            return RobotActionResult(
                False,
                "moveit_scene_mismatch",
                "Planning refused: " + scene_status["message"],
                details={"moveItSceneStatus": scene_status},
            )
        result = self._plan_approach_phase(
            planner_id=planner_id,
            planning_attempts=planning_attempts,
            planning_time_sec=planning_time_sec,
            progress=progress,
        )
        if scene_status["state"] == "resynced":
            result = replace(
                result,
                message="NOTE: MoveIt's planning scene differed from Slicer and was re-synchronized before planning. "
                + str(result.message),
                details={**dict(result.details or {}), "moveItSceneResynchronized": True},
            )
        if int(planning_attempts) < STEP6_JOINT_PLANNING_ATTEMPTS:
            warning = (
                f"WARNING: planning attempts {int(planning_attempts)} is below the project default "
                f"{STEP6_JOINT_PLANNING_ATTEMPTS}; planning is less reliable. Reset it in Planning Parameters. "
            )
            result = replace(
                result,
                message=warning + str(result.message),
                details={**dict(result.details or {}), "planningPolicyBelowDefault": True},
            )
        return result

    @property
    def lastMoveItSceneStatus(self) -> Optional[dict]:
        """Most recent scene-gate outcome, for the GUI badge (display only)."""
        return getattr(self, "_last_moveit_scene_status", None)

    def ensureMoveItSceneMatches(self) -> dict:
        """Compare MoveGroup with Slicer's audit; re-sync once on mismatch.

        States: matched | resynced | mismatch | unreadable | not_checked.
        ``refuse`` is True for mismatch/unreadable (S6-LIVE-01 2026-10-06).
        """
        scene = self.moveItSceneComparison()
        if scene is None:
            status = {"state": "not_checked", "refuse": False, "comparison": None,
                      "message": "MoveIt scene not checked (this bridge cannot read it)."}
            self._last_moveit_scene_status = status
            return status
        resynced = False
        repair_log = []
        republish = getattr(self._bridge, "republish_moveit_obstacles", None)
        sync = getattr(self._logic, "syncStep6MoveItPlanningScene", None)
        for round_index in range(STEP6_SCENE_REPAIR_ROUNDS):
            if scene is None or scene.get("matches") or "expected_count" not in scene:
                break
            # Targeted, paced re-send of only the differing objects; a full burst
            # re-sync is what lost updates in the first place (6 Oct evidence).
            ids = list(scene.get("missing") or ()) + [i for i, _ in scene.get("differing") or ()]
            if callable(republish) and ids:
                ok, message, _sent = republish(ids)
                repair_log.append(f"round {round_index + 1}: {message}")
                if not ok and callable(sync):
                    sync(self._parameter_node())
                    repair_log.append(f"round {round_index + 1}: full re-sync")
            elif callable(sync):
                try:
                    sync(self._parameter_node())
                    repair_log.append(f"round {round_index + 1}: full re-sync")
                except (RuntimeError, ValueError, TypeError) as exc:
                    repair_log.append(f"re-sync failed: {exc}")
                    break
            else:
                break
            resynced = True
            # Publishing is asynchronous: allow MoveGroup a bounded time to apply it.
            deadline = monotonic() + STEP6_SCENE_RESYNC_WAIT_SEC
            while True:
                scene = self.moveItSceneComparison()
                if scene is None or scene.get("matches") or monotonic() >= deadline:
                    break
                sleep(0.25)
        if scene is not None and scene.get("matches"):
            state = "resynced" if resynced else "matched"
            message = str(scene.get("summary"))
        else:
            state = "unreadable" if scene is not None and "expected_count" not in scene else "mismatch"
            message = str((scene or {}).get("detail") or (scene or {}).get("summary"))
        status = {"state": state, "refuse": state in ("mismatch", "unreadable"),
                  "comparison": scene, "message": message, "repair_log": repair_log}
        self._last_moveit_scene_status = status
        return status

    def _frame_check_states(self) -> dict:
        """Task Home plus every stage end of the current diagnostic chain.

        Empty when this bridge cannot compute both FKs (host fakes).
        """
        if not callable(getattr(self._bridge, "compute_moveit_tcp_pose_world_ras_mm", None)):
            return {}
        states = {}
        try:
            home = self._logic.taskHomeRecord(self._parameter_node())
            if home is not None:
                states["task_home"] = dict(zip(home.joint_names, home.joint_positions_si))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        stages = (self._step6_stage_diagnostic_chain or {}).get("stages") or {}
        for phase_id, name in (("P1", "preentry"), ("P2", "entry"), ("P3", "drilling_end")):
            end = (stages.get(phase_id) or {}).get("end")
            if end:
                states[name] = dict(end)
        return states

    def frameConsistency(self, states: Mapping[str, Mapping[str, float]]) -> dict:
        """Slicer KDL TCP pose vs MoveIt-service TCP pose, world RAS mm (S6-LIVE-01 2026-10-06)."""
        from dentobot_workflow.base_diagnosis import compare_frame_poses

        base = self._parameter_node().robotBaseTransform
        pairs = {}
        for name, q in states.items():
            ok_kdl, _m1, kdl = self._bridge.compute_tcp_pose_world_ras_mm(q, base_transform=base)
            ok_moveit, _m2, moveit = self._bridge.compute_moveit_tcp_pose_world_ras_mm(q, base_transform=base)
            pairs[name] = (kdl if ok_kdl else None, moveit if ok_moveit else None)
        comparison = compare_frame_poses(pairs)
        self._last_frame_consistency = comparison
        return comparison

    def moveItSceneComparison(self) -> Optional[dict]:
        """MoveGroup world vs Slicer's audited outgoing objects (S6-LIVE-01 2026-10-06).

        None when this bridge cannot read the MoveIt scene at all (host fakes).
        Otherwise a dict with ``matches``; an unreadable scene counts as no match.
        """
        from dentobot_workflow.base_diagnosis import compare_moveit_scene

        reader = getattr(self._bridge, "read_moveit_world_object_bounds", None)
        if not callable(reader):
            return None
        try:
            audit = self._logic.collisionSceneAuditRecord(self._parameter_node())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            audit = None
        if audit is None:
            return {"matches": False, "summary": "no collision-scene audit to compare",
                    "detail": "Synchronize the Step 6 planning scene before planning."}
        ok, message, objects = reader()
        if not ok:
            ok, message, objects = reader()
        if not ok:
            return {"matches": False, "summary": "MoveIt scene unreadable: " + str(message),
                    "detail": "the MoveIt planning scene could not be read (" + str(message) + ")."}
        comparison = compare_moveit_scene(audit.object_records, objects)
        comparison["detail"] = (
            "MoveIt holds a different collision scene than Slicer: " + comparison["summary"]
            + " Re-sync the Step 6 planning scene."
        )
        self._last_moveit_scene_comparison = comparison
        return comparison

    def _plan_approach_phase(
        self,
        *,
        planner_id: str = STEP6_JOINT_PLANNER_ID,
        planning_attempts: int = STEP6_JOINT_PLANNING_ATTEMPTS,
        planning_time_sec: float = GOAL1_DIRECT_PLANNING_TIME_SEC,
        progress=None,
    ) -> RobotActionResult:
        """Plan strict current→pre-entry plus independently guarded contact."""

        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "A Task Home save or reconciliation is in progress.",
            )
        try:
            if progress:
                progress("Checking confirmed task and runtime")
            self.setJointPlanningPolicy(planner_id, planning_attempts, planning_time_sec)
            parameter_node = self._require_context()
            preferred_plan_selection = self._current_diagnostic_plan_selection(
                parameter_node
            )
            self._diagnostic_plan_selection_override = preferred_plan_selection
            self.stopPreview()
            self._motion_plan = None
            self._preflight_drilling_plan = None
            self._drilling_truncation = None
            self._preflight_task_fingerprint = ""
            self._preflight_orientation_commitment = {}
            self._preflight_complete_approach_evidence = None
            self._diagnostic_candidate_paths = {}
            if self._robot_away_from_home:
                raise ValueError(
                    "The robot is away from Task Home. Use guarded Return Home "
                    "before replanning Approach."
                )
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                raise ValueError("Task confirmation is missing or stale: " + ", ".join(issues))
            if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
            if not self.taskHomeRuntimeValidated(parameter_node):
                raise ValueError(
                    "Task Home is not validated in the current ROS/MoveIt session. "
                    "Return to 6.2 and apply it before planning Approach."
                )
            # Operator 2026-10-02: the 6.3 workspace and its limit review are an
            # optional visual. The prerequisite is that the accepted Base reaches
            # the whole PreEntry->Target stroke kinematically.
            stroke_check = getattr(self._logic, "step6CurrentBaseStrokeReachability", None)
            if callable(stroke_check):
                stroke = stroke_check(parameter_node)
                if not stroke.get("reachable"):
                    raise ValueError(
                        "The accepted Base cannot reach the whole PreEntry-to-Target "
                        f"drilling stroke (first unreachable station: "
                        f"{stroke.get('first_failed_station')}). Use Find Reachable Base "
                        "in 6.1, accept it, and confirm the task again."
                    )
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            guide_fit = self._guide_fit_evidence(parameter_node)
            tool_insertion = self._tool_insertion_evidence(
                snapshot.entry_ras_mm,
                snapshot.target_ras_mm,
            )
            if not tool_insertion.get("planningAllowed", False):
                return RobotActionResult(
                    False,
                    str(tool_insertion["code"]),
                    str(tool_insertion["message"]),
                    details={
                        "toolInsertion": tool_insertion,
                        "guideFit": guide_fit,
                    },
                )
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
                    "Approach planning requires MoveIt's monitored current state to equal "
                    "the immutable Task Home before planning. "
                    + monitored_message
                    + (
                        f" Maximum observed joint error: {monitored_error:.6g}."
                        if monitored_positions
                        else ""
                    )
                    + " Return to 6.2 and apply/validate Task Home."
                )
            if progress:
                progress("Preparing collision and phase guard")
            guard_ok, guard_message = self._prepare_phase_guard(parameter_node, snapshot)
            if not guard_ok:
                raise RuntimeError(guard_message)
            # One guard session spans Goal 1 and Goal 2.  Re-planning Goal 1
            # explicitly starts a fresh sequence/corridor history; individual
            # waypoint commands must never reset that history.
            self._phase_guard_task_fingerprint = snapshot.snapshot_fingerprint
            self._phase_sequence = self._bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE
            self._completed_phase = ""
            pre_entry, entry = self._logic.step6ApproachPoints(parameter_node, snapshot)
            approach_vector = tuple(
                float(entry[index] - pre_entry[index]) for index in range(3)
            )
            approach_length = sum(value * value for value in approach_vector) ** 0.5
            if approach_length <= 1e-9:
                raise RuntimeError("Approach PreEntry and Entry points are coincident.")
            if progress:
                progress("Searching collision-aware PreEntry IK")
            ik_seed_records: list[dict[str, object]] = []
            ik_candidates, _ik_failures = self._goal1_pre_entry_ik_candidates(
                parameter_node,
                pre_entry,
                entry,
                snapshot.target_ras_mm,
                home_positions,
                progress=progress,
                seed_collector=ik_seed_records.append,
            )
            if not ik_candidates:
                position_tolerance_mm = float(
                    _default_bridge.CARTESIAN_START_POSITION_TOLERANCE_MM
                )
                axis_tolerance_deg = float(
                    _default_bridge.CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
                )
                observed_residuals = []
                for index, record in enumerate(ik_seed_records):
                    position = record.get("position_residual_mm")
                    axis = record.get("drilling_axis_residual_deg")
                    if position is None:
                        position = record.get("authoritative_position_residual_mm")
                    if axis is None:
                        axis = record.get(
                            "authoritative_drilling_axis_residual_deg"
                        )
                    try:
                        position = float(position)
                        axis = float(axis)
                    except (TypeError, ValueError):
                        continue
                    if isfinite(position) and isfinite(axis):
                        observed_residuals.append((index, position, axis))
                best_residual = min(
                    observed_residuals,
                    key=lambda values: max(
                        values[1] / position_tolerance_mm,
                        values[2] / axis_tolerance_deg,
                    ),
                    default=None,
                )
                residual_summary = (
                    f"Best observed position/axis residual: {best_residual[1]:.3f} mm / "
                    f"{best_residual[2]:.3f}°; tolerances: {position_tolerance_mm:.3f} mm / "
                    f"{axis_tolerance_deg:.3f}°."
                    if best_residual is not None
                    else "Position/axis residuals are unavailable; tolerances: "
                    f"{position_tolerance_mm:.3f} mm / {axis_tolerance_deg:.3f}°."
                )
                failure_message = (
                    "Approach planning found no collision-aware PreEntry IK endpoint for "
                    "the canonical non-spinning drill TCP. "
                    + residual_summary
                    + " Full per-seed evidence is in Motion Diagnostics."
                )
                diagnostic_records = [
                    {
                        **record,
                        "candidate_index": int(record.get("candidate_index", index)),
                        "axial_roll_deg": LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG,
                        "success": False,
                        "message": _bounded_text(
                            record.get("solver_message")
                            or record.get("failure_classification")
                        ),
                        "completion_fraction": 0.0,
                        "completed_distance_mm": 0.0,
                        "requested_distance_mm": 0.0,
                        "waypoint_count": 0,
                        "failure_classification": str(
                            record.get("failure_classification")
                            or "preentry_ik_unreachable"
                        ),
                        "full_chain_candidate_status": "Blocked",
                        "full_chain_failure_stage": "preentry_ik",
                    }
                    for index, record in enumerate(ik_seed_records)
                ] or [
                    {
                        "candidate_index": 0,
                        "axial_roll_deg": LEGACY_DIAGNOSTIC_TOOL_ROLL_DEG,
                        "success": False,
                        "message": failure_message,
                        "completion_fraction": 0.0,
                        "completed_distance_mm": 0.0,
                        "requested_distance_mm": 0.0,
                        "waypoint_count": 0,
                        "failure_classification": "preentry_ik_unreachable",
                        "full_chain_candidate_status": "Blocked",
                        "full_chain_failure_stage": "preentry_ik",
                    }
                ]
                diagnostic = self._persist_goal1_diagnostic(
                    parameter_node,
                    snapshot,
                    diagnostic_records,
                    best_residual[0] if best_residual is not None else 0,
                    full_task_reason=failure_message,
                )
                self._clear_phase_session()
                details = {}
                if diagnostic is not None and diagnostic.session_fingerprint:
                    details["motionDiagnosticSessionFingerprint"] = (
                        diagnostic.session_fingerprint
                    )
                return RobotActionResult(
                    False,
                    "approach_plan_failed",
                    failure_message,
                    details=details,
                )
            strict_plan = None
            selected_candidate = None
            selected_axis_plan = None
            selected_chain_evaluation = None
            selected_goal1_diagnostic_index = -1
            plan_failures: list[dict[str, object]] = []
            diagnostic_records: list[dict[str, object]] = []
            planned_candidate_routes: list[dict[str, object]] = []
            clearance_candidate_routes: list[dict[str, object]] = []
            candidate_total = min(len(ik_candidates), GOAL1_MAX_PLANNED_IK_CANDIDATES)
            # Read once: the 6.3 run option may be toggled while this plan runs.
            dev_first_complete = bool(self._dev_first_complete_route)
            self._candidate_evaluation = {
                "mode": "dev_first_complete" if dev_first_complete else "all",
                "total": candidate_total,
                "evaluated": candidate_total,
                "notEvaluated": 0,
            }
            for candidate_index, candidate in enumerate(
                ik_candidates[:GOAL1_MAX_PLANNED_IK_CANDIDATES]
            ):
                if progress:
                    progress("Planning and guarding PreEntry routes", candidate_index, min(len(ik_candidates), GOAL1_MAX_PLANNED_IK_CANDIDATES))
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
                candidate_plan = self._plan_home_to_preentry_with_corridor(
                    parameter_node,
                    home_positions,
                    candidate["positions"],
                    pre_entry=pre_entry,
                    entry=snapshot.entry_ras_mm,
                    target=snapshot.target_ras_mm,
                    fixed_rotation_ras=candidate["orientationCommitment"]["rotationRas"],
                    roll_deg=float(candidate["rollDeg"]),
                    planner_context=(
                        "task_home_to_preentry_"
                        + str(candidate.get("routeType") or "direct")
                    ),
                    refresh_planning_scene=(candidate_index == 0),
                )
                if getattr(candidate_plan, "effective_planner_id", ""):
                    self._effective_joint_planner_id = (
                        candidate_plan.effective_planner_id
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
                        target=snapshot.target_ras_mm,
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
                    route = {
                        "candidate": candidate,
                        "strictPlan": candidate_plan,
                        "chain": chain,
                        "diagnosticIndex": len(diagnostic_records) - 1,
                    }
                    planned_candidate_routes.append(route)
                    if dev_first_complete and chain["status"] == "Complete":
                        self._candidate_evaluation.update(
                            evaluated=candidate_index + 1,
                            notEvaluated=candidate_total - candidate_index - 1,
                        )
                        break
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
            ) or (
                preferred_plan_selection is not None
                and str(preferred_plan_selection.get("route_key", {}).get("route_type"))
                == "clearance-detour"
            ):
                # A valid endpoint plus a failed straight joint-space route is
                # not a proof that no route exists.  Reuse only the bounded
                # 6.3 samples already shown to be static-valid and connected
                # from Task Home, then independently replan both legs now.
                clearance_start_plans: dict[int, object] = {}
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
                                planning_attempts=self._joint_planning_attempts,
                                allowed_planning_time_sec=self._joint_planning_time_sec,
                                planner_id=self._joint_planner_id,
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
                            planning_attempts=self._joint_planning_attempts,
                            allowed_planning_time_sec=self._joint_planning_time_sec,
                            planner_id=self._joint_planner_id,
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
                                target=snapshot.target_ras_mm,
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
                            route = {
                                "candidate": candidate,
                                "strictPlan": merged_plan,
                                "chain": chain,
                                "clearance": clearance,
                                "diagnosticIndex": len(diagnostic_records) - 1,
                            }
                            clearance_candidate_routes.append(route)
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
                    selected_clearance = selected_route.get("clearance")
                    selected_goal1_diagnostic_index = int(
                        selected_route["diagnosticIndex"]
                    )
            all_candidate_routes = planned_candidate_routes + clearance_candidate_routes
            if all_candidate_routes and preferred_plan_selection is not None:
                preferred_key = preferred_plan_selection.get("route_key", {})
                preferred_route = next(
                    (
                        route
                        for route in all_candidate_routes
                        if self._goal1_route_key(route) == preferred_key
                        and str(route["chain"].get("status")) == "Complete"
                    ),
                    None,
                )
                if preferred_route is None:
                    raise RuntimeError(
                        "The saved planner route was not regenerated as a complete "
                        "full-chain candidate. Review the current diagnostic before "
                        "using another route."
                    )
                else:
                    selected_route = preferred_route
                    strict_plan = selected_route["strictPlan"]
                    selected_candidate = selected_route["candidate"]
                    selected_chain_evaluation = selected_route["chain"]
                    selected_axis_plan = selected_chain_evaluation["axisPlan"]
                    selected_clearance = selected_route.get("clearance")
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
                    "Approach planning found "
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
            # Preserve the FK-derived orientation of the selected endpoint.
            # Replacing it with a canonical roll recreates an artificial
            # Cartesian bridge even though the TCP position and axis are continuous.
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
                    fixed_rotation_ras=selected_orientation["rotationRas"],
                    position_axis_only=True,
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
                        f"Approach PreEntry diagnostic: {len(strict_waypoints)} "
                        "collision-free Task-Home waypoints are retained as "
                        "display-only evidence. The terminal axis segment toward Entry "
                        f"was rejected at {stage2_failure_fraction * 100.0:.1f}% "
                        f"({stage2_failure_message}); Entry and Drill preview are blocked."
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
                self._motion_plan = None
                self._phase_guard_task_fingerprint = ""
                self._phase_guard_session_id = ""
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
                    False,
                    "approach_full_chain_blocked",
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
                        "collisionAwareIkCandidateCount": len(ik_candidates),
                        "plannedIkCandidateCount": min(
                            len(ik_candidates), GOAL1_MAX_PLANNED_IK_CANDIDATES
                        ),
                        "motionDiagnosticSessionFingerprint": (
                            deferred_diagnostic.session_fingerprint
                        ),
                        "fullTaskStatus": "Blocked",
                        "blockedStage": "stage2_phase_guard",
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
                    fixed_rotation_ras=selected_orientation["rotationRas"],
                    position_axis_only=True,
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
                        + " The collision-free Home→PreEntry route is display-only evidence."
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
                self._motion_plan = None
                self._phase_guard_task_fingerprint = ""
                self._phase_guard_session_id = ""
                self._preflight_drilling_plan = None
                self._preflight_task_fingerprint = ""
                self._preflight_orientation_commitment = {}
                return RobotActionResult(
                    False,
                    "approach_full_chain_blocked",
                    provisional.message,
                    details={
                        "fullTaskStatus": "Blocked",
                        "blockedStage": "stage2_cartesian",
                        "firstInvalidCause": terminal.message,
                        "motionDiagnosticSessionFingerprint": diagnostic.session_fingerprint,
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
                    "Approach terminal plan did not provide an Entry joint state."
                )
            self._persist_goal1_diagnostic(
                parameter_node,
                snapshot,
                diagnostic_records,
                selected_goal1_diagnostic_index,
                stage2_status="Passed",
                full_task_status="PendingStage3Preflight",
            )
            # Retain the Entry→Target preflight result for truthful diagnostics,
            # but do not create Approach preview authority without a complete,
            # independently guard-validated Home→PreEntry→Entry→Target chain.
            drilling_preflight = (
                selected_chain_evaluation.get("drillingPlan")
                if selected_chain_evaluation is not None
                else None
            )
            # Retain the failed Stage-3 result for truthful UI/diagnostic
            # reporting even though partial preflight output is deliberately
            # cleared from the preview-authorizing slot below.
            drilling_preflight_result = drilling_preflight
            drilling_preflight_error = (
                str(selected_chain_evaluation.get("reason") or "")
                if selected_chain_evaluation is not None
                and selected_chain_evaluation.get("status") != "Complete"
                else ""
            )
            guide_warning_summary = self._guide_clearance_warning_summary(
                selected_chain_evaluation.get("guideClearanceWarnings", ())
                if selected_chain_evaluation is not None
                else ()
            )
            complete_guard_evidence = None
            try:
                if drilling_preflight is not None and not drilling_preflight.success:
                    raise RuntimeError(drilling_preflight_error or drilling_preflight.message)
                if drilling_preflight is None:
                    drilling_preflight = self._plan_full_drilling_line(
                        parameter_node,
                        snapshot,
                        terminal.waypoint_joint_vectors_si[-1],
                        start_axial_roll_deg=selected_roll_deg,
                        fixed_rotation_ras=selected_orientation["rotationRas"],
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
                drilling_offset = len(preflight_waypoints) - len(
                    drilling_preflight.waypoint_joint_vectors_si
                )
                if not guard_valid and int(invalid_index) >= drilling_offset:
                    # Operator policy 2b (2026-10-02) also applies to the final
                    # composed chain (Stage 1 + axis + Stage 2 + drilling, r7):
                    # a spindle-housing/template block truncates drilling.
                    blocker = self._bridge.last_task_joint_status()
                    shortened, truncation_or_reason = self._truncate_drilling_for_spindle_collision(
                        parameter_node,
                        snapshot,
                        preflight_waypoints[:drilling_offset],
                        preflight_phases[:drilling_offset],
                        drilling_preflight,
                        drilling_offset,
                        invalid_index,
                        (getattr(blocker, "first_body", ""), getattr(blocker, "second_body", "")),
                        validate_chain=validate_chain,
                        entry=snapshot.entry_ras_mm,
                        target=snapshot.target_ras_mm,
                    )
                    if shortened is not None:
                        drilling_preflight = shortened
                        if selected_chain_evaluation is not None:
                            selected_chain_evaluation = {
                                **selected_chain_evaluation,
                                "drillingTruncation": truncation_or_reason,
                                "drillingPlan": shortened,
                            }
                        preflight_waypoints = (
                            preflight_waypoints[:drilling_offset]
                            + tuple(shortened.waypoint_joint_vectors_si)
                        )
                        preflight_phases = (
                            preflight_phases[:drilling_offset]
                            + ("drilling",) * len(shortened.waypoint_joint_vectors_si)
                        )
                        guard_valid, guard_message, invalid_index = True, shortened.message, -1
                    else:
                        guard_message = f"{guard_message} Truncation not applied: {truncation_or_reason}"
                if not guard_valid:
                    raise RuntimeError(
                        guard_message
                        + f" First invalid composed waypoint: {invalid_index}."
                    )
                guard_identity_reader = getattr(
                    self._bridge,
                    "current_task_guard_identity",
                    _default_bridge.current_task_guard_identity,
                )
                guard_status_reader = getattr(
                    self._bridge,
                    "last_task_joint_status",
                    _default_bridge.last_task_joint_status,
                )
                guard_identity = guard_identity_reader()
                guard_status = guard_status_reader()
                guard_session_id = str(
                    guard_identity.get("guard_session_id") or ""
                    if isinstance(guard_identity, Mapping)
                    else ""
                )
                expected_last_sequence = (
                    int(self._bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE)
                    + len(preflight_waypoints)
                    - 1
                )
                guard_policy_fingerprint = self._strict_guard_policy_fingerprint()
                if not (
                    isinstance(guard_identity, Mapping)
                    and guard_identity.get("task_fingerprint")
                    == snapshot.snapshot_fingerprint
                    and guard_identity.get("collision_scene_policy_fingerprint")
                    == guard_policy_fingerprint
                    and guard_session_id
                    and getattr(guard_status, "task_fingerprint", "")
                    == snapshot.snapshot_fingerprint
                    and getattr(guard_status, "guard_session_id", "")
                    == guard_session_id
                    and getattr(guard_status, "phase", "") == "drilling"
                    and int(getattr(guard_status, "sequence", -1))
                    == expected_last_sequence
                    and bool(getattr(guard_status, "accepted", False))
                    and bool(getattr(guard_status, "validate_only", False))
                ):
                    raise RuntimeError(
                        "The complete independent phase-guard evidence is not current. "
                        "Re-plan Approach before preview."
                    )
                complete_guard_evidence = {
                    "taskFingerprint": snapshot.snapshot_fingerprint,
                    "guardSessionId": guard_session_id,
                    "lastSequence": expected_last_sequence,
                    "policyFingerprint": guard_policy_fingerprint,
                }
                warning_reader = getattr(
                    self._bridge, "last_task_phase_validation_warnings", None
                )
                if callable(warning_reader):
                    guide_warning_summary = self._guide_clearance_warning_summary(
                        warning_reader()
                    )
            except (RuntimeError, ValueError, OSError) as exc:
                drilling_preflight_error = str(exc)
                drilling_preflight = None
                complete_guard_evidence = None
                self._preflight_drilling_plan = None
                self._preflight_task_fingerprint = ""
                self._preflight_orientation_commitment = {}
            if drilling_preflight is not None:
                self._preflight_drilling_plan = drilling_preflight
                self._preflight_task_fingerprint = snapshot.snapshot_fingerprint
                self._preflight_orientation_commitment = selected_orientation
                truncation = (
                    selected_chain_evaluation.get("drillingTruncation")
                    if selected_chain_evaluation is not None
                    else None
                )
                self._drilling_truncation = dict(truncation) if truncation else None
                if self._drilling_truncation:
                    show_remainder = getattr(
                        self._bridge, "show_unreachable_drilling_remainder", None
                    )
                    if callable(show_remainder):
                        start, end = self._drilling_truncation["unreachable_segment_ras_mm"]
                        show_remainder(start, end)
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
                    _dev_fast_mode_stamp(self._candidate_evaluation)
                    + f"Approach ready: {len(strict_waypoints)} free-space, "
                    f"{len(terminal_waypoints)} fixed-axis Stage-2 checkpoint(s) "
                    f"from {source_count} MoveIt samples. "
                    "The independent phase guard keeps all non-tool collision "
                    "rules strict while suppressing only configured burr-to-task "
                    "contact; every suppression will be reported. "
                    "The five-DOF arm determines position and drilling-axis direction; "
                    "axial roll remains unconstrained."
                    + (
                        " through previously validated workspace clearance "
                        f"sample {int(selected_clearance['sampleIndex'])}. "
                        if selected_clearance is not None
                        else ". "
                    )
                    + (
                        (
                            _drilling_truncation_warning(self._drilling_truncation)
                            if self._drilling_truncation
                            else "The complete Entry-to-Target drilling line passed the "
                            "canonical TCP reachability preflight."
                        )
                        if drilling_preflight is not None
                        else (
                            "Full-task status is Blocked at Stage 3; this partial "
                            "route is display-only evidence and cannot be previewed."
                            + (
                                f" Stage 3 reason: {_bounded_text(drilling_preflight_error)}"
                                if drilling_preflight_error
                                else ""
                            )
                        )
                    )
                    + " " + str(tool_insertion["message"])
                    + " " + str(guide_fit["message"])
                    + (
                        " FUNCTIONAL SIMULATION ONLY: the unresolved Step 5C "
                        "final template is visible but excluded from MoveIt "
                        "collision evaluation; this is not physical "
                        "collision-valid evidence."
                        if self._template_collision_exclusion_active
                        else ""
                    )
                    + (
                        " RESEARCH SIMULATION ANATOMY OVERRIDE ACTIVE: the "
                        "reviewed local collision proxy is session-only; source "
                        "anatomy remains unchanged and results are not physical "
                        "collision-valid evidence."
                        if self.anatomyReviewState.get("active")
                        else ""
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
            full_chain_ready = (
                drilling_preflight is not None
                and complete_guard_evidence is not None
            )
            self._motion_plan = plan if full_chain_ready else None
            if full_chain_ready:
                self._phase_guard_task_fingerprint = snapshot.snapshot_fingerprint
                self._phase_guard_session_id = str(
                    complete_guard_evidence["guardSessionId"]
                )
                self._preflight_complete_approach_evidence = {
                    **complete_guard_evidence,
                    "plan": plan,
                }
            else:
                self._phase_guard_task_fingerprint = ""
                self._phase_guard_session_id = ""
                self._preflight_complete_approach_evidence = None
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
                full_chain_ready,
                (
                    "approach_full_chain_plan_ready"
                    if full_chain_ready
                    else "approach_full_chain_blocked"
                ),
                plan.message,
                details={
                    "waypointCount": len(plan.waypoint_joint_vectors_si),
                    "strictWaypointCount": len(strict_waypoints),
                    "axisWaypointCount": len(axis_waypoints),
                    "terminalWaypointCount": len(terminal_waypoints),
                    "terminalContactPolicy": "phase_guard_evidence_based_contact_warning_v2",
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
                        else (
                            drilling_preflight_result.fraction
                            if drilling_preflight_result is not None
                            else None
                        )
                    ),
                    "drillingPreflightError": drilling_preflight_error,
                    "drillingTruncation": self._drilling_truncation,
                    "candidateEvaluation": dict(self._candidate_evaluation),
                    "fullTaskStatus": (
                        "CompletedWithWarnings"
                        if drilling_preflight is not None
                        and guide_warning_summary["guideClearanceWarningCount"]
                        else "Complete"
                        if drilling_preflight is not None
                        else "Blocked"
                    ),
                    "blockedStage": (
                        "stage3_drilling"
                        if drilling_preflight is None
                        else ""
                    ),
                    "firstInvalidCause": drilling_preflight_error,
                    "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                    "toolAxisRas": tuple(selected_orientation["toolAxisRas"]),
                    "toolOrientationFingerprint": selected_orientation[
                        "fingerprint"
                    ],
                    "guideFit": guide_fit,
                    "toolInsertion": tool_insertion,
                    **guide_warning_summary,
                    "templateCollisionExclusionActive": bool(
                        self._template_collision_exclusion_active
                    ),
                    "templateCollisionExcludedObjectIds": tuple(
                        self._template_collision_excluded_object_ids
                    ),
                    "sessionAnatomyReviewOverride": dict(self.anatomyReviewState),
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
        """Prepare the retained Entry→Target preflight for guarded preview."""

        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "A Task Home save or reconciliation is in progress.",
            )
        try:
            parameter_node = self._require_context()
            self.stopPreview()
            if isinstance(self._preflight_complete_approach_evidence, dict):
                self._preflight_complete_approach_evidence.pop("drillingPlan", None)
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                raise ValueError("Task confirmation is missing or stale: " + ", ".join(issues))
            if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                raise ValueError("Connect the simulation-only ROS/MoveIt runtime first.")
            if self._completed_phase != "approach":
                raise ValueError(
                    "Complete the guarded Approach preview before preparing Drill preview."
                )
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            guide_fit = self._guide_fit_evidence(parameter_node)
            preflight_ready = self.drillingPreflightReady
            if not preflight_ready:
                raise ValueError(
                    "The complete Home-to-PreEntry-to-Entry-to-Target preflight "
                    "is not current. Re-plan Approach. Drill preview cannot independently "
                    "replan or promote a partial drilling path."
                )
            if self._phase_guard_task_fingerprint != snapshot.snapshot_fingerprint:
                raise ValueError(
                    "The Approach guard session is missing or belongs to another task. "
                    "Re-plan and preview Approach before Drill preview."
                )
            start_positions = self._bridge.last_accepted_joint_positions_si()
            if not start_positions or any(
                name not in start_positions for name in JOINT_NAMES
            ):
                raise RuntimeError(
                    "The accepted Approach endpoint is unavailable. Re-preview Approach."
                )
            result = self._preflight_drilling_plan
            source_waypoints = tuple(result.waypoint_joint_vectors_si)
            orientation = dict(self._preflight_orientation_commitment)
            if (
                orientation.get("policy") != DRILL_TOOL_FRAME_POLICY
                or not orientation.get("fingerprint")
            ):
                raise RuntimeError(
                    "The Stage-1 drilling-frame commitment is unavailable. "
                    "Re-plan Approach before Drill preview."
                )
            # Entry-to-Target is short and accuracy-dominant. Preserve every
            # fine MoveIt Cartesian sample so the guard never substitutes a
            # sparse joint-space chord for the requested TCP line.
            waypoints = source_waypoints
            waypoint_times = tuple(result.waypoint_times_sec)
            plan = PhasePlan(
                success=True,
                message=(
                    (
                        _drilling_truncation_warning(self._drilling_truncation) + " "
                        if self._drilling_truncation
                        else ""
                    )
                    + f"Drill preview ready: {len(waypoints)} guarded Entry-to-Target "
                    f"checkpoint(s) from {len(source_waypoints)} MoveIt samples. "
                    "The five-DOF arm constrains the drilling axis; axial roll remains unconstrained. "
                    "Solver collision avoidance is disabled for this exploratory "
                    "Cartesian check. The independent guard may suppress only "
                    "configured burr-to-task-object contacts; non-tool collisions, "
                    "bounds, and corridor violations remain rejected. "
                    + str(guide_fit["message"])
                    + (
                        " FUNCTIONAL SIMULATION ONLY: the unresolved Step 5C "
                        "final template is visible but excluded from MoveIt "
                        "collision evaluation; this is not physical "
                        "collision-valid evidence."
                        if self._template_collision_exclusion_active
                        else ""
                    )
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
            evidence = self._preflight_complete_approach_evidence
            if isinstance(evidence, dict):
                self._preflight_complete_approach_evidence = {
                    **evidence,
                    "drillingPlan": plan,
                }
            return RobotActionResult(
                True,
                "drilling_plan_ready",
                plan.message,
                details={
                    "waypointCount": len(waypoints),
                    "sourceWaypointCount": len(source_waypoints),
                    "drillingTruncation": self._drilling_truncation,
                    "cartesianFraction": float(result.fraction),
                    "coordinateFrame": str(result.coordinate_frame),
                    "startPositionErrorMm": result.start_position_error_mm,
                    "startOrientationErrorDeg": result.start_orientation_error_deg,
                    "drillToolFramePolicy": DRILL_TOOL_FRAME_POLICY,
                    "toolAxisRas": tuple(orientation["toolAxisRas"]),
                    "toolOrientationFingerprint": orientation["fingerprint"],
                    "guideFit": guide_fit,
                    "templateCollisionExclusionActive": bool(
                        self._template_collision_exclusion_active
                    ),
                    "templateCollisionExcludedObjectIds": tuple(
                        self._template_collision_excluded_object_ids
                    ),
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
        speed_multiplier: float = 1.0,
        interval_ms: Optional[int] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[RobotActionResult], None]] = None,
    ) -> RobotActionResult:
        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "A Task Home save or reconciliation is in progress.",
            )
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "A guarded phase stopped before endpoint verification. Further preview is blocked while its accepted and rejected evidence is retained.",
            )
        if self._guarded_preview_active:
            return RobotActionResult(
                False,
                "phase_preview_active",
                "A guarded simulation phase preview is already active.",
            )
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
                    "Drill preview has already completed in this guard session. Re-plan Approach to replay the task.",
                )
            return RobotActionResult(
                False,
                "approach_required",
                "Complete the guarded Approach preview before Drill preview.",
            )
        try:
            parameter_node = self._require_context()
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                self._clear_phase_session()
                return RobotActionResult(False, "task_stale", "Task confirmation is stale: " + ", ".join(issues))
            if str(requested_phase) == "drilling":
                evidence = self._preflight_complete_approach_evidence
                orientation = self._preflight_orientation_commitment
                if not (
                    self.drillingPreflightReady
                    and isinstance(evidence, Mapping)
                    and evidence.get("drillingPlan") is plan
                    and evidence.get("taskFingerprint") == plan.task_fingerprint
                    and isinstance(orientation, Mapping)
                    and orientation.get("fingerprint")
                    == plan.tool_orientation_fingerprint
                ):
                    return RobotActionResult(
                        False,
                        "drilling_preflight_required",
                        "Drill preview requires the current drilling plan derived from "
                        "the complete, independently guard-validated Approach preflight.",
                    )
            if str(requested_phase) == "approach":
                snapshot = self._logic.confirmedTaskRecord(parameter_node)
                preflight = self._preflight_drilling_plan
                orientation = self._preflight_orientation_commitment
                evidence = self._preflight_complete_approach_evidence
                identity_reader = getattr(
                    self._bridge,
                    "current_task_guard_identity",
                    _default_bridge.current_task_guard_identity,
                )
                status_reader = getattr(
                    self._bridge,
                    "last_task_joint_status",
                    _default_bridge.last_task_joint_status,
                )
                guard_identity = identity_reader()
                guard_status = status_reader()
                guard_session_id = str(
                    evidence.get("guardSessionId") or ""
                    if isinstance(evidence, Mapping)
                    else ""
                )
                expected_last_sequence = (
                    int(self._bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE)
                    + int(plan.source_waypoint_count)
                    + len(
                        getattr(preflight, "waypoint_joint_vectors_si", ()) or ()
                    )
                    - 1
                )
                full_chain_current = bool(
                    snapshot is not None
                    and snapshot.snapshot_fingerprint == plan.task_fingerprint
                    and self.drillingPreflightReady
                    and self._phase_guard_task_fingerprint
                    == snapshot.snapshot_fingerprint
                    and self._preflight_task_fingerprint
                    == snapshot.snapshot_fingerprint
                    and preflight is not None
                    and bool(getattr(preflight, "success", False))
                    and bool(getattr(preflight, "waypoint_joint_vectors_si", ()))
                    and isinstance(orientation, Mapping)
                    and orientation.get("policy") == DRILL_TOOL_FRAME_POLICY
                    and orientation.get("fingerprint")
                    == plan.tool_orientation_fingerprint
                    and isinstance(evidence, Mapping)
                    and evidence.get("plan") is plan
                    and evidence.get("taskFingerprint")
                    == snapshot.snapshot_fingerprint
                    and int(evidence.get("lastSequence", -1))
                    == expected_last_sequence
                    and guard_session_id
                    and guard_session_id == self._phase_guard_session_id
                    and isinstance(guard_identity, Mapping)
                    and guard_identity.get("task_fingerprint")
                    == snapshot.snapshot_fingerprint
                    and guard_identity.get("guard_session_id")
                    == guard_session_id
                    and guard_identity.get("collision_scene_policy_fingerprint")
                    == evidence.get("policyFingerprint")
                    and evidence.get("policyFingerprint")
                    == self._strict_guard_policy_fingerprint()
                    and getattr(guard_status, "task_fingerprint", "")
                    == snapshot.snapshot_fingerprint
                    and getattr(guard_status, "guard_session_id", "")
                    == guard_session_id
                    and getattr(guard_status, "phase", "") == "drilling"
                    and int(getattr(guard_status, "sequence", -1))
                    == expected_last_sequence
                    and bool(getattr(guard_status, "accepted", False))
                    and bool(getattr(guard_status, "validate_only", False))
                )
                if not full_chain_current:
                    return RobotActionResult(
                        False,
                        "approach_full_chain_required",
                        "Approach preview requires the current complete, independently "
                        "guard-validated Home-to-Target plan. Re-plan Approach.",
                    )
            if self._phase_guard_task_fingerprint != plan.task_fingerprint:
                return RobotActionResult(
                    False,
                    "phase_session_required",
                    "The matching task-guard session is unavailable. Re-plan Approach.",
                )
            if str(requested_phase) == "approach" and (
                self._phase_sequence
                != self._bridge.ROS2_TASK_GUARD_INITIAL_SEQUENCE
                or self._completed_phase
            ):
                return RobotActionResult(
                    False,
                    "phase_session_consumed",
                    "This Approach guard session has already started. Re-plan Approach before replaying it.",
                )
            if str(requested_phase) == "approach":
                home_record = self._logic.taskHomeRecord(parameter_node)
                home_positions = dict(
                    zip(home_record.joint_names, home_record.joint_positions_si)
                )
                monitored_reader = getattr(
                    self._bridge, "monitored_joint_positions_si", None
                )
                monitored_home = (
                    monitored_reader() if callable(monitored_reader) else {}
                )
                home_matches, home_error, _ = self._joint_positions_match(
                    home_positions, monitored_home
                )
                if not home_matches:
                    return RobotActionResult(
                        False,
                        "guarded_motion_history_home_mismatch",
                        "The monitored start state does not match Task Home; guarded "
                        "preview was not started.",
                        details={"maximumJointError": home_error},
                    )
                self._capture_motion_history_home(
                    monitored_home, plan.task_fingerprint
                )
            elif (
                self._motion_history_task_fingerprint != plan.task_fingerprint
                or not self._accepted_motion_history
            ):
                return RobotActionResult(
                    False,
                    "guarded_motion_history_missing",
                    "The accepted Approach motion history is unavailable. Re-plan and "
                    "preview Approach before Drill preview.",
                )
            import qt
        except (RuntimeError, ValueError, ImportError) as exc:
            return RobotActionResult(False, "phase_preview_failed", str(exc))
        self.stopPreview()
        self._preview_index = 0
        self._guarded_preview_active = True
        self._guarded_preview_phase = str(requested_phase)
        self._guarded_preview_task_fingerprint = str(plan.task_fingerprint)
        self._guarded_preview_request = None
        self._preview_exploratory_tool_contact = False
        self._preview_suppressed_tool_contact_samples = 0
        self._preview_guide_clearance_warnings = []
        self._preview_last_display_monotonic = 0.0
        timer = qt.QTimer()
        try:
            speed_multiplier = float(speed_multiplier)
        except (TypeError, ValueError):
            speed_multiplier = 1.0
        speed_multiplier = min(8.0, max(0.25, speed_multiplier))
        legacy_interval = (
            max(20, int(interval_ms)) if interval_ms is not None else None
        )
        timer.setSingleShot(True)

        def schedule_next() -> None:
            if (
                not self._guarded_preview_active
                or self._incomplete_preview_evidence is not None
            ):
                return
            if self._preview_index >= len(plan.waypoint_joint_vectors_si):
                # The final accepted waypoint still needs one event-loop turn
                # to enter the completion branch, where endpoint FK and the
                # finish callback are evaluated.  A single-shot timer avoids
                # leaving the preview permanently active at N/N.
                timer.start(1)
                return
            if legacy_interval is not None:
                delay_ms = legacy_interval
            elif self._preview_index == 0:
                delay_ms = 1
            else:
                times = tuple(plan.waypoint_times_sec or ())
                if len(times) == len(plan.waypoint_joint_vectors_si):
                    delta_sec = max(
                        0.001,
                        float(times[self._preview_index])
                        - float(times[self._preview_index - 1]),
                    )
                    delay_ms = max(1, round(delta_sec * 1000.0 / speed_multiplier))
                else:
                    delay_ms = max(1, round(50.0 / speed_multiplier))
            timer.start(int(delay_ms))

        def advance() -> None:
            if self._preview_waypoint_in_flight:
                return
            # Check the review even on the final tick, before reporting endpoint
            # completion. The ROS scene cannot observe Segment Editor changes.
            review_checker = getattr(self._logic, "step6AnatomyReviewFreshnessIssues", None)
            review_issues = review_checker(parameter_node) if callable(review_checker) else ()
            if review_issues:
                self._latch_incomplete_preview(
                    "Anatomy review changed before the guarded phase endpoint was verified."
                )
                self._stop_preview_timer()
                self._clear_phase_session()
                self._robot_away_from_home = True
                if on_finished:
                    on_finished(
                        RobotActionResult(
                            False,
                            "task_stale",
                            "; ".join(review_issues),
                            details={
                                "incompletePreview": deepcopy(
                                    self._incomplete_preview_evidence
                                )
                            },
                        )
                    )
                return
            if self._preview_index >= len(plan.waypoint_joint_vectors_si):
                completed_phase = plan.requested_phase
                self._stop_preview_timer()
                endpoint = self._verify_preview_endpoint(plan)
                if not endpoint.success:
                    self._latch_incomplete_preview(
                        "The guarded phase endpoint was not verified: "
                        + endpoint.message
                    )
                    self._clear_phase_session()
                    self._robot_away_from_home = True
                    if on_finished:
                        on_finished(
                            RobotActionResult(
                                False,
                                endpoint.code,
                                endpoint.message,
                                details={
                                    **dict(endpoint.details),
                                    "incompletePreview": deepcopy(
                                        self._incomplete_preview_evidence
                                    ),
                                },
                                payload=endpoint.payload,
                            )
                        )
                    return
                self._completed_phase = completed_phase
                self._robot_away_from_home = True
                self._guarded_preview_active = False
                self._guarded_preview_phase = ""
                self._guarded_preview_request = None
                if on_finished:
                    warning_summary = self._guide_clearance_warning_summary(
                        self._preview_guide_clearance_warnings
                    )
                    completed_with_warnings = bool(
                        warning_summary["guideClearanceWarningCount"]
                    )
                    on_finished(
                        RobotActionResult(
                            True,
                            (
                                "phase_preview_complete_with_warnings"
                                if completed_with_warnings
                                else "phase_preview_complete_exploratory_contact"
                                if self._preview_exploratory_tool_contact
                                else "phase_preview_complete"
                            ),
                            "Guarded simulation phase preview completed"
                            + (
                                " with recorded positive guide-clearance warning(s)"
                                if completed_with_warnings
                                else ""
                            )
                            + (
                                f"; configured burr contact was suppressed at "
                                f"{self._preview_suppressed_tool_contact_samples} "
                                "interpolated guard sample(s)"
                                if self._preview_exploratory_tool_contact
                                else ""
                            )
                            + ".",
                            details={
                                "status": (
                                    "CompletedWithWarnings"
                                    if completed_with_warnings
                                    else "Complete"
                                ),
                                "exploratoryToolContactSuppressed": bool(
                                    self._preview_exploratory_tool_contact
                                ),
                                "suppressedToolContactSampleCount": int(
                                    self._preview_suppressed_tool_contact_samples
                                ),
                                **warning_summary,
                            },
                        )
                    )
                return
            current_issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if current_issues:
                self._latch_incomplete_preview(
                    "Task identity changed before the guarded phase endpoint was verified."
                )
                self._stop_preview_timer()
                self._clear_phase_session()
                if on_finished:
                    on_finished(
                        RobotActionResult(
                            False,
                            "task_stale",
                            "Task changed during preview: "
                            + ", ".join(current_issues)
                            + " Re-plan Approach to start a new guarded session.",
                            details={
                                "incompletePreview": deepcopy(
                                    self._incomplete_preview_evidence
                                )
                            },
                        )
                    )
                return
            positions = plan.waypoint_joint_vectors_si[self._preview_index]
            phase = plan.waypoint_phases[self._preview_index]
            request = {
                "taskFingerprint": str(plan.task_fingerprint),
                "guardSessionId": str(self._phase_guard_session_id or ""),
                "phase": str(phase),
                "sequence": int(self._phase_sequence),
                "waypointIndex": int(self._preview_index),
                "acceptedPrefixCount": max(
                    0, len(self._accepted_motion_history) - 1
                ),
                "requestedPositionsSi": dict(positions),
            }
            self._guarded_preview_request = request
            self._preview_waypoint_in_flight = True
            try:
                ok, message = self._bridge.apply_task_phase_joint_positions(
                    positions,
                    task_fingerprint=plan.task_fingerprint,
                    phase=phase,
                    sequence=self._phase_sequence,
                )
                if not ok:
                    failure = {
                        "phase": str(phase),
                        "sequence": int(request["sequence"]),
                        "waypointIndex": int(request["waypointIndex"]),
                        "requestedPositionsSi": dict(positions),
                        **self._preview_request_status(
                            request, accepted=False, message=message
                        ),
                    }
                    if self._incomplete_preview_evidence is None:
                        self._latch_incomplete_preview(
                            "The phase guard rejected a requested waypoint: " + message,
                            request=request,
                            first_rejected=failure,
                        )
                    else:
                        self._latch_incomplete_preview(
                            "The guarded preview was stopped while a waypoint request was pending.",
                            request=request,
                        )
                        self._record_incomplete_preview_request_result(
                            request, accepted=False, message=message
                        )
                    self._stop_preview_timer()
                    self._clear_phase_session()
                    if on_finished:
                        on_finished(
                            RobotActionResult(
                                False,
                                "phase_waypoint_rejected",
                                message
                                + " Re-plan Approach to start a new guarded session.",
                                details={
                                    "incompletePreview": deepcopy(
                                        self._incomplete_preview_evidence
                                    )
                                },
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
                if (
                    status is not None
                    and getattr(status, "task_fingerprint", "")
                    == plan.task_fingerprint
                    and getattr(status, "phase", "") == phase
                    and getattr(status, "sequence", -1) == self._phase_sequence
                    and bool(getattr(status, "accepted", False))
                    and bool(getattr(status, "guide_clearance_warning", False))
                ):
                    self._preview_guide_clearance_warnings.append(
                        {
                            "phase": phase,
                            "sequence": self._phase_sequence,
                            "waypoint_index": self._preview_index,
                            "guide_clearance_warning_sample_count": int(
                                getattr(
                                    status,
                                    "guide_clearance_warning_sample_count",
                                    0,
                                )
                            ),
                            "minimum_guide_clearance_warning_m": getattr(
                                status,
                                "minimum_guide_clearance_warning_m",
                                None,
                            ),
                            "guide_clearance_warning_robot_link": str(
                                getattr(
                                    status,
                                    "guide_clearance_warning_robot_link",
                                    "",
                                )
                            ),
                            "guide_clearance_warning_object_id": str(
                                getattr(
                                    status,
                                    "guide_clearance_warning_object_id",
                                    "",
                                )
                            ),
                            "guide_warning_kind": str(
                                getattr(status, "guide_warning_kind", "")
                            ),
                            "guide_clearance_warning_contact_penetration_m": getattr(
                                status,
                                "guide_clearance_warning_contact_penetration_m",
                                None,
                            ),
                            "guide_clearance_warning_contact_sample_count": int(
                                getattr(
                                    status,
                                    "guide_clearance_warning_contact_sample_count",
                                    0,
                                )
                            ),
                            "guide_clearance_warning_contact_position_base_m": getattr(
                                status,
                                "guide_clearance_warning_contact_position_base_m",
                                None,
                            ),
                            "reason": str(getattr(status, "reason", "")),
                        }
                    )
                self._append_motion_history_waypoint(
                    positions, phase, plan.task_fingerprint
                )
                self._record_incomplete_preview_request_result(
                    request, accepted=True, message=message
                )
                # Keep the re-entrancy latch held until the accepted sequence and
                # MRML display state have both advanced.  EndModify can process
                # widget refresh callbacks, which in turn may spin Qt and fire
                # this timer recursively.  Releasing the latch earlier allowed
                # the same guarded sequence to be published twice.
                self._preview_index += 1
                self._phase_sequence += 1
                self._robot_away_from_home = True
                now = monotonic()
                if (
                    self._preview_index == len(plan.waypoint_joint_vectors_si)
                    or now - self._preview_last_display_monotonic >= 1.0 / 30.0
                ):
                    self._write_display_values(
                        parameter_node,
                        self._display_values_from_si(positions),
                    )
                    self._preview_last_display_monotonic = now
                if on_progress:
                    on_progress(
                        self._preview_index,
                        len(plan.waypoint_joint_vectors_si),
                    )
            finally:
                self._preview_waypoint_in_flight = False
                if self._incomplete_preview_evidence is not None:
                    self._guarded_preview_active = False
                self._guarded_preview_request = None
            if self._incomplete_preview_evidence is not None:
                return
            schedule_next()

        timer.timeout.connect(advance)
        self._preview_timer = timer
        schedule_next()
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
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "A guarded phase stopped before endpoint verification. Further preview is blocked while its accepted and rejected evidence is retained.",
            )
        return RobotActionResult(
            False,
            "guarded_phase_preview_required",
            "Generic motion-plan preview is disabled; create a phase plan and preview it with previewPhase.",
        )

    def stopPreview(self) -> RobotActionResult:
        if self._guarded_preview_active:
            self._latch_incomplete_preview(
                "Manual stop requested before guarded phase endpoint verification.",
                request=self._guarded_preview_request,
            )
            if not self._preview_waypoint_in_flight:
                self._guarded_preview_active = False
        return self._stop_preview_timer()

    def _stop_preview_timer(self) -> RobotActionResult:
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer = None
        self._diagnostic_preview_timer = None
        if not self._preview_waypoint_in_flight:
            self._preview_index = 0
        return RobotActionResult(True, "preview_stopped", "Simulated preview stopped.")

    def stopGuardedPreview(self) -> RobotActionResult:
        """Stop a live guarded preview and retain its unverified evidence."""

        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "incomplete_preview_blocks_motion",
                "This guarded preview is already incomplete; its retained evidence blocks motion.",
            )
        if self._guarded_preview_active:
            accepted_count = max(0, len(self._accepted_motion_history) - 1)
            self._latch_incomplete_preview(
                "Manual stop requested before guarded phase endpoint verification.",
                request=self._guarded_preview_request,
            )
            self._stop_preview_timer()
            if not self._preview_waypoint_in_flight:
                self._guarded_preview_active = False
            self._robot_away_from_home = True
            return RobotActionResult(
                True,
                "preview_stopped_return_required",
                "Preview stopped before endpoint verification. The accepted prefix "
                "and current request evidence are retained; Return Home is blocked.",
                details={"incompletePreview": deepcopy(
                             self._incomplete_preview_evidence
                         ),
                         "acceptedWaypointCount": accepted_count},
            )
        return self._stop_preview_timer()

    def returnToTaskHome(self) -> RobotActionResult:
        """Reverse accepted task motion under the phase guard, then verify Home."""

        if self._manual_task_home_acceptance_in_progress:
            return RobotActionResult(
                False,
                "manual_task_home_review_busy",
                "A Task Home save or reconciliation is in progress.",
            )
        if self._incomplete_preview_evidence is not None:
            return self._incomplete_preview_block(
                "guarded_return_partial_phase",
                "Guarded Return Home is blocked because a preview phase stopped before endpoint verification. The exact saved prefix is retained for review; recovery is not available in this session.",
            )
        stopped = self.stopGuardedPreview()
        if stopped.code == "preview_stopped_return_required":
            return self._incomplete_preview_block(
                "guarded_return_partial_phase",
                "Guarded Return Home is blocked because the active phase stopped before endpoint verification. The exact saved prefix is retained for review.",
            )
        if not self._robot_away_from_home:
            self._clear_phase_session()
            return self.applyTaskHome()
        try:
            parameter_node = self._require_context()
            issues = self._logic.confirmedTaskFreshnessIssues(parameter_node)
            if issues:
                raise RuntimeError(
                    "Task confirmation changed after motion: " + ", ".join(issues)
                )
            snapshot = self._logic.confirmedTaskRecord(parameter_node)
            if self._completed_phase not in {"approach", "drilling"}:
                raise RuntimeError(
                    "No complete guarded approach or drilling phase is available "
                    "for reverse traversal."
                )
            if (
                self._motion_history_task_fingerprint
                != snapshot.snapshot_fingerprint
                or len(self._accepted_motion_history) < 2
            ):
                raise RuntimeError(
                    "The accepted task-motion history is missing or stale."
                )
            accepted = self._bridge.last_accepted_joint_positions_si()
            current_expected = self._accepted_motion_history[-1]["positions"]
            current_matches, current_error, _ = self._joint_positions_match(
                current_expected, accepted
            )
            if not current_matches:
                raise RuntimeError(
                    "The guard's accepted state does not match the retained motion "
                    f"history (maximum joint error {current_error:.6g})."
                )

            warnings = []
            accepted_reverse_count = 0
            while len(self._accepted_motion_history) > 1:
                current_record = self._accepted_motion_history[-1]
                destination = self._accepted_motion_history[-2]
                reverse_phase = (
                    "retraction"
                    if str(current_record.get("phase") or "")
                    in {"terminal_contact", "drilling", "retraction"}
                    else "approach"
                )
                sequence = self._phase_sequence
                ok, message = self._bridge.apply_task_phase_joint_positions(
                    destination["positions"],
                    task_fingerprint=snapshot.snapshot_fingerprint,
                    phase=reverse_phase,
                    sequence=sequence,
                )
                if not ok:
                    raise RuntimeError(
                        f"Reverse waypoint {accepted_reverse_count} was rejected: "
                        + message
                    )
                status_getter = getattr(
                    self._bridge, "last_task_joint_status", None
                )
                status = status_getter() if callable(status_getter) else None
                if status is not None and bool(
                    getattr(status, "guide_clearance_warning", False)
                ):
                    warnings.append(
                        {
                            "phase": reverse_phase,
                            "sequence": sequence,
                            "waypoint_index": accepted_reverse_count,
                            "guide_clearance_warning_sample_count": int(
                                getattr(
                                    status,
                                    "guide_clearance_warning_sample_count",
                                    0,
                                )
                            ),
                            "minimum_guide_clearance_warning_m": getattr(
                                status,
                                "minimum_guide_clearance_warning_m",
                                None,
                            ),
                            "guide_clearance_warning_robot_link": str(
                                getattr(
                                    status,
                                    "guide_clearance_warning_robot_link",
                                    "",
                                )
                            ),
                            "guide_clearance_warning_object_id": str(
                                getattr(
                                    status,
                                    "guide_clearance_warning_object_id",
                                    "",
                                )
                            ),
                            "guide_warning_kind": str(
                                getattr(status, "guide_warning_kind", "")
                            ),
                            "guide_clearance_warning_contact_penetration_m": getattr(
                                status,
                                "guide_clearance_warning_contact_penetration_m",
                                None,
                            ),
                            "guide_clearance_warning_contact_sample_count": int(
                                getattr(
                                    status,
                                    "guide_clearance_warning_contact_sample_count",
                                    0,
                                )
                            ),
                            "guide_clearance_warning_contact_position_base_m": getattr(
                                status,
                                "guide_clearance_warning_contact_position_base_m",
                                None,
                            ),
                            "reason": str(getattr(status, "reason", "")),
                        }
                    )
                self._phase_sequence += 1
                accepted_reverse_count += 1
                self._accepted_motion_history.pop()
                self._write_display_values(
                    parameter_node,
                    self._display_values_from_si(destination["positions"]),
                )

            captured_home = self._accepted_motion_history[0]["positions"]
            home_ok, home_message, monitored_home, home_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    captured_home, timeout_sec=1.5
                )
            )
            if not home_ok:
                raise RuntimeError("Guarded reverse did not reach captured Home: " + home_message)
            warning_summary = self._guide_clearance_warning_summary(warnings)
            self._clear_phase_session()
            result = self.applyTaskHome()
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            self._robot_away_from_home = True
            return RobotActionResult(
                False,
                "task_home_return_failed",
                "Guarded Return Home failed; the robot remains away from Task Home. "
                + str(exc),
            )
        if result.success:
            self._robot_away_from_home = False
            return RobotActionResult(
                True,
                "task_home_returned",
                "Guarded axial retraction and reverse approach completed; the "
                "monitored MoveIt state matches Task Home.",
                details={
                    **dict(result.details),
                    "axialRetractionCompleted": True,
                    "acceptedReverseWaypointCount": accepted_reverse_count,
                    "capturedHomeMaximumJointError": home_error,
                    "capturedHomeMonitoredJointPositionsSi": monitored_home,
                    **warning_summary,
                },
                payload=result.payload,
            )
        self._robot_away_from_home = True
        return RobotActionResult(
            False,
            "task_home_return_failed",
            "Guarded Return Home failed; the robot remains away from Task Home. "
            + result.message,
            details=result.details,
            payload=result.payload,
        )

    def defaultTaskSpaceRoi(self) -> RobotActionResult:
        """Return the current opened-incisor ROI without changing case state."""

        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) != "case":
                return RobotActionResult(
                    False,
                    "case_required",
                    "Open a reviewed case before deriving the task-space ROI.",
                )
            gap_line = getattr(parameter_node, "step6CaseJawGapLine", None)
            if gap_line is None:
                return RobotActionResult(
                    False,
                    "incisor_gap_line_missing",
                    "The current Case Foundation incisor-gap line is unavailable.",
                )
            preparation_issue = self._scene_preparation_issue(parameter_node)
            if preparation_issue:
                return RobotActionResult(
                    False,
                    "case_foundation_stale",
                    _bounded_text(preparation_issue),
                )

            is_line_node = getattr(gap_line, "IsA", None)
            if not callable(is_line_node) or not is_line_node(
                "vtkMRMLMarkupsLineNode"
            ):
                return RobotActionResult(
                    False,
                    "incisor_gap_line_invalid",
                    "The Case Foundation reference is not a Markups line node.",
                )
            expected_role = getattr(
                self._logic, "STEP6_CASE_JAW_GAP_LINE_ROLE", None
            )
            if not expected_role:
                return RobotActionResult(
                    False,
                    "incisor_gap_line_role_unavailable",
                    "The canonical Case Foundation incisor-gap role is unavailable.",
                )
            if gap_line.GetAttribute("DENTOBOT.MarkupsRole") != expected_role:
                return RobotActionResult(
                    False,
                    "incisor_gap_line_wrong_role",
                    "The referenced line is not the Case Foundation incisor-gap line.",
                )
            if gap_line.GetNumberOfDefinedControlPoints() != 2:
                return RobotActionResult(
                    False,
                    "incisor_gap_line_ambiguous",
                    "The Case Foundation incisor-gap line must have "
                    "exactly two defined points.",
                )

            upper_incisor = [0.0, 0.0, 0.0]
            opened_lower_incisor = [0.0, 0.0, 0.0]
            gap_line.GetNthControlPointPositionWorld(0, upper_incisor)
            gap_line.GetNthControlPointPositionWorld(1, opened_lower_incisor)
            roi = default_task_space_roi_from_incisors(
                upper_incisor_world_ras_mm=upper_incisor,
                opened_lower_incisor_world_ras_mm=opened_lower_incisor,
            )
            opening_revision = int(parameter_node.caseFoundationOpeningRevision)
            gap_line_node_id = str(gap_line.GetID() or "").strip()
            if not gap_line_node_id:
                return RobotActionResult(
                    False,
                    "incisor_gap_line_invalid",
                    "The Case Foundation incisor-gap line has no scene identity.",
                )
            return RobotActionResult(
                True,
                "task_space_roi_ready",
                "Default task-space ROI derived from the current opened-incisor line.",
                payload={
                    "centerWorldRasMm": roi.center_world_ras_mm,
                    "dimensionsMm": roi.dimensions_mm,
                    "openingRevision": opening_revision,
                    "gapLineNodeId": gap_line_node_id,
                },
            )
        except Exception as exc:
            return RobotActionResult(
                False,
                "task_space_roi_failed",
                _bounded_text(exc),
            )

    def generateWorkspaceCloud(
        self,
        progress=None,
        *,
        roi: Optional[TaskSpaceRoi] = None,
        roi_source: Optional[Mapping[str, object]] = None,
    ) -> RobotActionResult:
        """Generate ROI-limited samples and validate them through MoveIt."""
        if getattr(self, "_workspace_generation_active", False):
            return RobotActionResult(False, "workspace_busy", "Workspace generation is already running.")
        self._workspace_generation_active = True
        started = monotonic()
        phase_timings_sec: dict[str, float] = {}
        counts = {
            "roiCandidateCount": 0,
            "positionAxisIkAttemptCount": 0,
            "positionAxisIkSuccessCount": 0,
            "positionAxisIkFailureCount": 0,
            "moveItStaticValidityAttemptCount": 0,
            "moveItStaticValidityAcceptedCount": 0,
            "moveItStaticValidityRejectedCount": 0,
            "moveItStaticValidityUnevaluatedCount": 0,
            "moveItFkAttemptCount": 0,
            "homeConnectivityEvaluatedCount": 0,
            "homeConnectedCount": 0,
            "homeConnectivityRejectedCount": 0,
        }
        ik_termination_counts: dict[str, int] = {}
        ik_collision_check_counts: dict[str, int] = {}
        ik_failure_examples: list[dict[str, object]] = []
        runtime_rejections: list[str] = []
        roi_fp = ""
        source_fp = ""
        source_record: dict[str, object] = {}
        axis_status = "Unavailable"
        axis_fp = ""
        task_fp = ""
        workspace_model = None
        workspace_model_updated = False

        def record_phase(name: str, phase_started: float) -> None:
            phase_timings_sec[name] = phase_timings_sec.get(name, 0.0) + max(
                0.0, monotonic() - phase_started
            )

        def mark_provisional(model) -> None:
            setter = getattr(model, "SetAttribute", None)
            if callable(setter):
                try:
                    setter("DENTOBOT.WorkspaceRuntimeValidated", "false")
                    setter("DENTOBOT.WorkspaceState", "Provisional")
                except Exception:
                    pass

        def mark_stale(model) -> None:
            setter = getattr(model, "SetAttribute", None)
            if callable(setter):
                try:
                    setter("DENTOBOT.WorkspaceRuntimeValidated", "false")
                    setter("DENTOBOT.WorkspaceState", "Stale")
                except Exception:
                    pass

        def mark_axis_status(model) -> None:
            setter = getattr(model, "SetAttribute", None)
            if callable(setter) and axis_status != "Unavailable":
                try:
                    setter("DENTOBOT.WorkspaceTaskAxisStatus", axis_status)
                except Exception:
                    pass

        def details(extra=None) -> dict[str, object]:
            elapsed = max(0.0, monotonic() - started)
            timings = dict(phase_timings_sec)
            timings["totalSec"] = elapsed
            return {
                "candidateCounts": dict(counts),
                "phaseTimingsSec": timings,
                "elapsedSec": elapsed,
                "ikTerminationCounts": dict(ik_termination_counts),
                "ikCollisionCheckCounts": dict(ik_collision_check_counts),
                "ikFailureExamples": tuple(ik_failure_examples),
                "sampleFailures": tuple(runtime_rejections),
                "roiFingerprint": roi_fp,
                "roiSourceFingerprint": source_fp,
                "roiSource": dict(source_record),
                "taskAxisStatus": axis_status,
                "taskAxisFingerprint": axis_fp,
                "taskFingerprint": task_fp,
                **dict(extra or {}),
            }

        def fail(code: str, message: str, **extra) -> RobotActionResult:
            self._runtime_validated_workspace_key = ""
            if workspace_model_updated:
                mark_provisional(workspace_model)
            else:
                mark_stale(workspace_model)
            return RobotActionResult(
                False, code, message, details=details(extra)
            )

        try:
            if progress:
                progress("Checking Task Home and synchronized scene")
            parameter_node = self._require_context()
            self._runtime_validated_workspace_key = ""
            model_reader = getattr(self._logic, "robotWorkspaceModelNode", None)
            try:
                workspace_model = (
                    model_reader() if callable(model_reader) else None
                )
                mark_stale(workspace_model)
            except Exception:
                workspace_model = None
            if not self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            ):
                return fail(
                    "runtime_required",
                    "Connect ROS/MoveIt in 6.1 before generating the workspace.",
                )
            if not self._planning_scene_synchronized:
                return fail(
                    "planning_scene_required",
                    "Synchronize and audit the current MoveIt PlanningScene before generating workspace samples.",
                )
            scene_issues = self._logic.collisionSceneAuditFreshnessIssues(
                parameter_node
            )
            if scene_issues:
                return fail("planning_scene_stale", " ".join(scene_issues))
            collision_audit = self._logic.collisionSceneAuditRecord(parameter_node)
            if collision_audit is None or not collision_audit.audit_fingerprint:
                return fail(
                    "planning_scene_required",
                    "The synchronized collision-scene audit is unavailable.",
                )
            collision_fingerprint = str(collision_audit.audit_fingerprint)

            roi_started = monotonic()
            default_result = self.defaultTaskSpaceRoi()
            if not default_result.success:
                record_phase("roiSource", roi_started)
                return fail(
                    str(default_result.code or "workspace_roi_source_unavailable"),
                    str(default_result.message or "The current ROI source is unavailable."),
                )
            if not isinstance(default_result.payload, Mapping):
                record_phase("roiSource", roi_started)
                return fail(
                    "workspace_roi_source_invalid",
                    "The current opened-incisor ROI source is malformed.",
                )
            try:
                default_payload = dict(default_result.payload)
                revision = default_payload["openingRevision"]
                gap_line_id = default_payload["gapLineNodeId"]
                default_roi = TaskSpaceRoi(
                    center_world_ras_mm=default_payload["centerWorldRasMm"],
                    dimensions_mm=default_payload["dimensionsMm"],
                )
                if (
                    isinstance(revision, bool)
                    or not isinstance(revision, int)
                    or revision < 0
                    or not isinstance(gap_line_id, str)
                    or not gap_line_id.strip()
                ):
                    raise ValueError("the Case Foundation ROI source identity is invalid")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                record_phase("roiSource", roi_started)
                return fail("workspace_roi_source_invalid", _bounded_text(exc))
            current_source = {
                "openingRevision": int(revision),
                "gapLineNodeId": gap_line_id.strip(),
            }
            if roi_source is not None:
                if not isinstance(roi_source, Mapping):
                    record_phase("roiSource", roi_started)
                    return fail(
                        "workspace_roi_source_invalid",
                        "Edited ROI source must identify the current opening revision and gap line.",
                    )
                supplied_revision = roi_source.get("openingRevision")
                supplied_line_id = roi_source.get("gapLineNodeId")
                if (
                    isinstance(supplied_revision, bool)
                    or not isinstance(supplied_revision, int)
                    or supplied_revision < 0
                    or not isinstance(supplied_line_id, str)
                    or not supplied_line_id.strip()
                ):
                    record_phase("roiSource", roi_started)
                    return fail(
                        "workspace_roi_source_invalid",
                        "Edited ROI source identity is invalid.",
                    )
                supplied_source = {
                    "openingRevision": int(supplied_revision),
                    "gapLineNodeId": supplied_line_id.strip(),
                }
                if supplied_source != current_source:
                    record_phase("roiSource", roi_started)
                    return fail(
                        "workspace_roi_source_stale",
                        "The edited ROI belongs to a stale Case Foundation opening or gap line.",
                        suppliedRoiSource=supplied_source,
                        currentRoiSource=current_source,
                    )
            elif roi is not None:
                record_phase("roiSource", roi_started)
                return fail(
                    "workspace_roi_source_required",
                    "Edited ROI bounds require the current opening revision and gap-line identity.",
                )
            selected_roi = default_roi if roi is None else roi
            if not isinstance(selected_roi, TaskSpaceRoi):
                record_phase("roiSource", roi_started)
                return fail(
                    "workspace_roi_invalid",
                    "ROI must be a valid TaskSpaceRoi in world RAS millimetres.",
                )
            source_record = current_source
            source_fp = fingerprint(source_record)
            roi_fp = fingerprint(
                {
                    "center_world_ras_mm": selected_roi.center_world_ras_mm,
                    "dimensions_mm": selected_roi.dimensions_mm,
                    "source_fingerprint": source_fp,
                }
            )
            record_phase("roiSource", roi_started)

            trajectory_issues = self._logic.step6PlanningContextFreshnessIssues(
                parameter_node
            )
            if trajectory_issues:
                return fail(
                    "workspace_trajectory_stale",
                    " ".join(trajectory_issues),
                )
            trajectory = self._logic.step6TrajectorySummary(parameter_node)
            if not isinstance(trajectory, Mapping) or not trajectory.get("isValid"):
                return fail(
                    "workspace_trajectory_required",
                    "Select a current valid Entry/Target trajectory before generating workspace samples.",
                )
            trajectory_fp = str(
                self._logic.step6TrajectoryRevision(parameter_node) or ""
            )
            if not trajectory_fp:
                return fail(
                    "workspace_trajectory_required",
                    "The selected Entry/Target trajectory has no current identity.",
                )
            try:
                entry = tuple(float(value) for value in trajectory["entryRas"])
                target = tuple(float(value) for value in trajectory["targetRas"])
                if (
                    len(entry) != 3
                    or len(target) != 3
                    or not all(isfinite(value) for value in entry + target)
                ):
                    raise ValueError("trajectory points must be finite RAS triplets")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                return fail("workspace_trajectory_invalid", _bounded_text(exc))

            axis_status = "ProvisionalSelectedTrajectory"
            axis_entry, axis_target = entry, target
            try:
                snapshot = self._logic.confirmedTaskRecord(parameter_node)
                current_snapshot = bool(
                    snapshot is not None
                    and not self._logic.confirmedTaskFreshnessIssues(parameter_node)
                    and str(snapshot.trajectory_revision or "") == trajectory_fp
                )
                if current_snapshot:
                    snap_entry = tuple(float(value) for value in snapshot.entry_ras_mm)
                    snap_target = tuple(float(value) for value in snapshot.target_ras_mm)
                    if (
                        tuple(round(value, 9) for value in snap_entry)
                        == tuple(round(value, 9) for value in entry)
                        and tuple(round(value, 9) for value in snap_target)
                        == tuple(round(value, 9) for value in target)
                    ):
                        axis_entry, axis_target = snap_entry, snap_target
                        axis_status = "ConfirmedCurrent"
                        task_fp = str(snapshot.snapshot_fingerprint or "")
            except (AttributeError, TypeError, ValueError, OverflowError):
                pass
            axis_fp = fingerprint(
                {
                    "status": axis_status,
                    "entry_ras_mm": axis_entry,
                    "target_ras_mm": axis_target,
                    "trajectory_fingerprint": trajectory_fp,
                    "task_fingerprint": task_fp,
                }
            )
            sample_count = int(parameter_node.robotWorkspaceSampleCount)
            if sample_count < 50 or sample_count > 5000:
                return fail(
                    "workspace_sample_count_invalid",
                    "Workspace sample count must be between 50 and 5000.",
                )
            if not self.taskHomeRuntimeValidated(parameter_node):
                return fail(
                    "task_home_runtime_validation_required",
                    "Save or apply a live-validated Task Home in 6.2 before generating the workspace.",
                )
            home = self._logic.taskHomeRecord(parameter_node)
            if home is None:
                return fail(
                    "task_home_required",
                    "Save a case/base-specific Task Home before generating the workspace.",
                )
            home_positions = canonicalize_planning_joint_positions(
                dict(zip(home.joint_names, home.joint_positions_si))
            )
            monitored_ok, monitored_message, monitored, monitored_error = (
                self._bridge.wait_for_monitored_joint_positions_si(
                    home_positions, timeout_sec=1.0
                )
            )
            if not monitored_ok:
                return fail(
                    "workspace_start_state_mismatch",
                    "Workspace exploration must start from Task Home. "
                    + str(monitored_message),
                    expectedJointPositionsSi=home_positions,
                    monitoredJointPositionsSi=monitored,
                    maximumJointError=monitored_error,
                )
            task_limits = self._logic.getTaskJointLimits(parameter_node)

            def workspace_plan_identity():
                current = self._require_context()
                if current is not parameter_node or not self._planning_scene_synchronized:
                    raise ValueError("Workspace context was replaced or disconnected.")
                if not self._logic.isRos2MotionControlActive(current.robotBaseTransform):
                    raise ValueError("Workspace ROS connection is no longer active.")
                if self._logic.collisionSceneAuditFreshnessIssues(current):
                    raise ValueError("Workspace collision scene is stale.")
                if not self.taskHomeRuntimeValidated(current):
                    raise ValueError("Task Home runtime authority was revoked.")
                current_home = self._logic.taskHomeRecord(current)
                current_audit = self._logic.collisionSceneAuditRecord(current)
                if current_home is None or current_audit is None:
                    raise ValueError("Workspace Home or scene is unavailable.")
                motion_identity = self._motionControlNodeIdentity()
                return fingerprint({
                    "home": current_home.to_dict(),
                    "base": self._logic.robotBaseFingerprint(current),
                    "robot": self._logic.robotProfileFingerprint(),
                    "limits": self._logic.step6TaskLimitsFingerprint(current),
                    "trajectory": self._logic.step6TrajectoryRevision(current),
                    "scene": current_audit.audit_fingerprint,
                    "policy": self._strict_guard_policy_fingerprint(),
                    "robot_node": motion_identity[0],
                    "motion_node": motion_identity[1],
                    "opening": self.defaultTaskSpaceRoi().payload,
                    "target": str(getattr(current, "targetToothSegmentId", "")),
                    "branches": str(getattr(current, "step6TrajectoryRegistryJson", "")),
                    "imported": bool(current.step6PlanningContextImported),
                })

            submitted_workspace_identity = workspace_plan_identity()

            def workspace_plan_is_current():
                try:
                    return workspace_plan_identity() == submitted_workspace_identity
                except Exception:
                    return False

            candidate_started = monotonic()
            candidates = deterministic_task_space_tcp_candidates(
                selected_roi,
                sample_count,
                confirmed_drill_axis_world_ras=tuple(
                    axis_target[index] - axis_entry[index] for index in range(3)
                ),
            )
            counts["roiCandidateCount"] = len(candidates)
            record_phase("candidateGeneration", candidate_started)

            pose_builder = getattr(
                self._bridge,
                "tool_pose_matrices_world_mm",
                _default_bridge.tool_pose_matrices_world_mm,
            )
            goal_setter = getattr(
                self._bridge,
                "set_moveit_tcp_goal_matrix",
                _default_bridge.set_moveit_tcp_goal_matrix,
            )
            solver = getattr(
                self._bridge,
                "solve_moveit_tcp_position_axis_goal",
                _default_bridge.solve_moveit_tcp_position_axis_goal,
            )
            if not all(callable(value) for value in (pose_builder, goal_setter, solver)):
                return fail(
                    "workspace_position_axis_ik_unavailable",
                    "MoveIt position-axis workspace sampling is unavailable in this runtime.",
                )

            ik_solutions = []
            for candidate_index, candidate in enumerate(candidates):
                if progress:
                    progress(
                        "Solving ROI TCP position-axis IK",
                        candidate_index,
                        len(candidates),
                    )
                pose_started = monotonic()
                position = tuple(candidate.position_world_ras_mm)
                axis = tuple(candidate.drill_axis_world_ras_unit)
                poses = pose_builder(
                    position,
                    tuple(position[i] + axis[i] for i in range(3)),
                    1,
                )
                record_phase("fixedAxisPose", pose_started)
                if not poses:
                    return fail(
                        "workspace_pose_build_failed",
                        f"Could not build fixed-axis pose for ROI candidate {candidate_index}.",
                        candidateIndex=candidate_index,
                )
                goal_started = monotonic()
                goal_ok, goal_message, _goal_node = goal_setter(poses[0])
                record_phase("positionAxisGoal", goal_started)
                if not goal_ok:
                    return fail(
                        "workspace_tcp_goal_failed",
                        f"MoveIt rejected ROI candidate {candidate_index}: {goal_message}",
                        candidateIndex=candidate_index,
                    )
                counts["positionAxisIkAttemptCount"] += 1
                ik_started = monotonic()
                try:
                    ik_ok, ik_message, positions_si, diagnostic = solver(
                        seed_joint_positions_si=home_positions,
                        avoid_collisions=True,
                    )
                except Exception as exc:
                    record_phase("positionAxisIK", ik_started)
                    return fail(
                        "workspace_position_axis_ik_failed",
                        _bounded_text(exc),
                        candidateIndex=candidate_index,
                    )
                record_phase("positionAxisIK", ik_started)
                diagnostic = dict(diagnostic) if isinstance(diagnostic, Mapping) else {}
                termination = str(diagnostic.get("termination_reason") or "unknown")
                collision_status = str(
                    diagnostic.get("collision_check_status") or "unknown"
                )
                ik_termination_counts[termination] = (
                    ik_termination_counts.get(termination, 0) + 1
                )
                ik_collision_check_counts[collision_status] = (
                    ik_collision_check_counts.get(collision_status, 0) + 1
                )
                if not ik_ok:
                    counts["positionAxisIkFailureCount"] += 1
                    if len(ik_failure_examples) < 8:
                        ik_failure_examples.append(
                            {
                                "candidateIndex": candidate_index,
                                "requestedTcpWorldRasMm": position,
                                "message": _bounded_text(ik_message),
                                "diagnostic": diagnostic,
                            }
                        )
                    continue
                try:
                    positions_si = canonicalize_planning_joint_positions(positions_si)
                except (KeyError, TypeError, ValueError) as exc:
                    return fail(
                        "workspace_position_axis_ik_invalid",
                        f"MoveIt returned an invalid joint vector for candidate {candidate_index}: {exc}",
                        candidateIndex=candidate_index,
                    )
                counts["positionAxisIkSuccessCount"] += 1
                ik_solutions.append(
                    (candidate_index, candidate, positions_si, ik_message, diagnostic)
                )

            if not ik_solutions:
                return fail(
                    "workspace_no_ik_samples",
                    f"Position-axis IK found no solutions for {counts['roiCandidateCount']} ROI candidates; no static checks or Home paths were run, and no new workspace model was produced.",
                    attemptedCandidateCount=counts["roiCandidateCount"],
                    terminationStatusCounts=dict(ik_termination_counts),
                    collisionCheckStatusCounts=dict(ik_collision_check_counts),
                )

            selected_ik_indices = _bounded_even_indices(
                len(ik_solutions), WORKSPACE_RUNTIME_VALIDATION_MAX_SAMPLES
            )
            selected_ik = tuple(ik_solutions[index] for index in selected_ik_indices)
            counts["moveItStaticValidityUnevaluatedCount"] = (
                len(ik_solutions) - len(selected_ik)
            )
            runtime_accepted: list[WorkspaceAcceptedSample] = []
            sample_evidence: list[dict[str, object]] = []
            for runtime_index, (
                candidate_index,
                candidate,
                positions_si,
                ik_message,
                diagnostic,
            ) in enumerate(selected_ik):
                if progress:
                    progress(
                        "Checking MoveIt static states",
                        runtime_index,
                        len(selected_ik),
                    )
                counts["moveItStaticValidityAttemptCount"] += 1
                static_started = monotonic()
                valid, validity_message, authoritative = (
                    self._bridge.check_moveit_static_joint_state(positions_si)
                )
                record_phase("moveItStaticValidity", static_started)
                if not authoritative:
                    return fail(
                        "workspace_runtime_validation_unavailable",
                        "MoveIt did not return authoritative static-state validity. "
                        + str(validity_message),
                        candidateIndex=candidate_index,
                    )
                if not valid:
                    counts["moveItStaticValidityRejectedCount"] += 1
                    if len(runtime_rejections) < 8:
                        runtime_rejections.append(
                            f"candidate {candidate_index}: {validity_message}"
                        )
                    continue
                counts["moveItStaticValidityAcceptedCount"] += 1
                counts["moveItFkAttemptCount"] += 1
                fk_started = monotonic()
                fk_ok, fk_message, tcp_base_mm = (
                    self._bridge.compute_moveit_static_tcp_pose_base_mm(positions_si)
                )
                record_phase("moveItFk", fk_started)
                if (
                    not fk_ok
                    or tcp_base_mm is None
                    or len(tuple(tcp_base_mm)) != 3
                    or not all(isfinite(float(value)) for value in tcp_base_mm)
                ):
                    return fail(
                        "workspace_moveit_fk_unavailable",
                        "MoveIt did not return authoritative explicit-state TCP FK. "
                        + str(fk_message),
                        candidateIndex=candidate_index,
                    )
                sample = WorkspaceAcceptedSample(
                    tcp_base_mm=tuple(float(value) for value in tcp_base_mm),
                    joint_display=self._display_values_from_si(positions_si),
                    joint_positions_si=tuple(
                        (name, float(positions_si[name])) for name in JOINT_NAMES
                    ),
                )
                runtime_accepted.append(sample)
                sample_evidence.append(
                    {
                        "sample_index": len(runtime_accepted) - 1,
                        "source_candidate_index": candidate_index,
                        "requested_tcp_world_ras_mm": list(
                            candidate.position_world_ras_mm
                        ),
                        "tcp_base_mm": list(sample.tcp_base_mm),
                        "joint_names": list(JOINT_NAMES),
                        "joint_positions_si": [
                            float(positions_si[name]) for name in JOINT_NAMES
                        ],
                        "joint_display": list(sample.joint_display),
                        "position_axis_ik": {
                            "status": "Solved",
                            "message": _bounded_text(ik_message),
                            "termination_reason": str(
                                diagnostic.get("termination_reason") or "unknown"
                            ),
                            "collision_check_status": str(
                                diagnostic.get("collision_check_status") or "unknown"
                            ),
                            "position_residual_mm": diagnostic.get(
                                "position_residual_mm"
                            ),
                            "axis_residual_deg": diagnostic.get(
                                "drilling_axis_residual_deg"
                            ),
                            "iteration_count": diagnostic.get("iteration_count"),
                        },
                        "static_state_validity": {
                            "status": "Valid",
                            "authoritative": True,
                            "message": _bounded_text(validity_message),
                        },
                        "tcp_fk": {
                            "source": "MoveItRobotState",
                            "message": _bounded_text(fk_message),
                        },
                        "home_connectivity": {"status": "NotEvaluated"},
                    }
                )

            if not runtime_accepted:
                return fail(
                    "workspace_no_moveit_valid_samples",
                    "MoveIt rejected every converged ROI workspace candidate against the synchronized PlanningScene.",
                    terminationStatusCounts=dict(ik_termination_counts),
                    collisionCheckStatusCounts=dict(ik_collision_check_counts),
                )
            report = WorkspaceSampleResult(
                requested_count=len(selected_ik),
                accepted_samples=tuple(runtime_accepted),
                self_collision_rejections=0,
                environment_rejections=counts["moveItStaticValidityRejectedCount"],
                task_limits=task_limits,
            )
            builder = getattr(self._logic, "createOrUpdateRobotWorkspace", None)
            if not callable(builder):
                return fail(
                    "workspace_model_builder_unavailable",
                    "The ROI workspace display builder is unavailable.",
                )
            if progress:
                progress("Showing provisional ROI TCP samples")
            display_started = monotonic()
            built = builder(
                parameter_node,
                sample_result=report,
                algorithm="ROI3D+PositionAxisIK",
            )
            if isinstance(built, tuple) and len(built) == 2:
                workspace_model, _ = built
            else:
                workspace_model = built
            if workspace_model is None:
                return fail(
                    "workspace_model_build_failed",
                    "The ROI workspace model was not created.",
                )
            workspace_model_updated = True
            mark_provisional(workspace_model)
            mark_axis_status(workspace_model)
            record_phase("workspaceDisplay", display_started)

            home_indices = self._home_connectivity_sample_indices(
                runtime_accepted, home_positions
            )
            scene_refreshed = False
            for order, sample_index in enumerate(home_indices):
                if progress:
                    progress("Checking Task Home connectivity", order, len(home_indices))
                sample = runtime_accepted[sample_index]
                positions_si = sample.joint_positions_si_dict()
                matches_home, maximum_delta, mismatched = self._joint_positions_match(
                    home_positions, positions_si
                )
                connectivity = sample_evidence[sample_index]["home_connectivity"]
                counts["homeConnectivityEvaluatedCount"] += 1
                connection_started = monotonic()
                if matches_home:
                    connected = True
                    connectivity.update(
                        {
                            "status": "HomeConnected",
                            "method": "IdentityAtTaskHome",
                            "maximum_start_goal_delta": maximum_delta,
                            "waypoint_count": 1,
                            "message": "Sample matches Task Home within monitored-state tolerances.",
                        }
                    )
                else:
                    path = self._bridge.plan_moveit_joint_goal(
                        start_joint_positions_si=home_positions,
                        goal_joint_positions_si=positions_si,
                        refresh_planning_scene=not scene_refreshed,
                        planning_attempts=1,
                        allowed_planning_time_sec=2.0,
                        planner_id=STEP6_JOINT_PLANNER_ID,
                        planner_context="task_home_to_workspace_sample",
                        responsive_wait=True,
                        wait_progress=(lambda phase: progress(phase, order, len(home_indices))) if progress else None,
                        context_is_current=workspace_plan_is_current,
                    )
                    if not workspace_plan_is_current():
                        return fail("workspace_context_changed", "Workspace inputs changed while planning; no result was accepted.")
                    scene_refreshed = True
                    connected = bool(path.success)
                    connectivity.update(
                        {
                            "status": "HomeConnected" if connected else "PlanRejected",
                            "method": "MoveItExplicitTaskHomeStart",
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
                if connected:
                    counts["homeConnectedCount"] += 1
                else:
                    counts["homeConnectivityRejectedCount"] += 1
                record_phase("homeConnectivity", connection_started)
                if order % 3 == 0:
                    try:
                        import slicer

                        slicer.app.processEvents()
                    except Exception:
                        pass
            if not home_indices or counts["homeConnectedCount"] == 0:
                return fail(
                    "workspace_no_home_connected_samples",
                    "Static-valid ROI samples were found, but none of the bounded samples planned successfully from Task Home. The cloud remains provisional display evidence.",
                    homeConnectivityEvaluatedSampleCount=len(home_indices),
                    homeConnectivityRejectedSampleCount=counts[
                        "homeConnectivityRejectedCount"
                    ],
                    acceptedSampleEvidence=tuple(
                        sample_evidence[index] for index in home_indices
                    ),
                )

            if not workspace_plan_is_current():
                return fail("workspace_context_changed", "Workspace inputs changed; the provisional cloud was not promoted.")
            # Visual reach envelope (operator 2026-10-02; display only).
            reach_envelope = {"status": "unavailable"}
            envelope_builder = getattr(self._logic, "updateStep6ReachEnvelope", None)
            if callable(envelope_builder):
                try:
                    reach_envelope = envelope_builder(
                        parameter_node,
                        [sample.tcp_base_mm for sample in runtime_accepted],
                        [
                            runtime_accepted[index].tcp_base_mm
                            for index in home_indices
                            if sample_evidence[index]["home_connectivity"].get("status") == "HomeConnected"
                        ],
                    )
                except Exception as exc:  # display aid must never fail the workspace
                    reach_envelope = {"status": "error", "reason": _bounded_text(exc)}
            proposal_started = monotonic()
            proposal = self._logic.proposeAssistedTaskLimits(parameter_node, report)
            proposal_payload = proposal.to_dict()
            proposal_payload.update(
                {
                    "runtime_validation_status": WORKSPACE_RUNTIME_VALIDATION_STATUS,
                    "runtime_evidence_schema_version": WORKSPACE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
                    "algorithm": "ROI3D+PositionAxisIK",
                    "roi_fingerprint": roi_fp,
                    "roi_source_fingerprint": source_fp,
                    "roi_source": dict(source_record),
                    "roi": {
                        "center_world_ras_mm": list(
                            selected_roi.center_world_ras_mm
                        ),
                        "dimensions_mm": list(selected_roi.dimensions_mm),
                    },
                    "task_axis_status": axis_status,
                    "task_axis_fingerprint": axis_fp,
                    "task_fingerprint": task_fp,
                    "trajectory_fingerprint": trajectory_fp,
                    "tcp_fk_source": "MoveItRobotState",
                    "task_home_fingerprint": fingerprint(home.to_dict()),
                    "collision_audit_fingerprint": collision_fingerprint,
                    "workspace_validation_policy_fingerprint": self._workspace_validation_policy_fingerprint(),
                    "runtime_valid_sample_count": report.accepted_count,
                    "runtime_evaluated_sample_count": len(selected_ik),
                    "locally_accepted_candidate_count": counts[
                        "positionAxisIkSuccessCount"
                    ],
                    "local_requested_candidate_count": len(candidates),
                    "position_axis_ik_attempted_count": counts[
                        "positionAxisIkAttemptCount"
                    ],
                    "position_axis_ik_success_count": counts[
                        "positionAxisIkSuccessCount"
                    ],
                    "position_axis_ik_failure_count": counts[
                        "positionAxisIkFailureCount"
                    ],
                    "position_axis_ik_termination_counts": dict(
                        ik_termination_counts
                    ),
                    "position_axis_ik_collision_check_counts": dict(
                        ik_collision_check_counts
                    ),
                    "moveit_static_validity_rejected_count": counts[
                        "moveItStaticValidityRejectedCount"
                    ],
                    "home_connectivity_status": "BoundedSubsetEvaluated",
                    "home_connectivity_policy": "Nearest+JointExtrema+EvenCoverage",
                    "home_connectivity_evaluated_sample_count": counts[
                        "homeConnectivityEvaluatedCount"
                    ],
                    "home_connected_sample_count": counts["homeConnectedCount"],
                    "home_connectivity_rejected_sample_count": counts[
                        "homeConnectivityRejectedCount"
                    ],
                    "accepted_sample_evidence": sample_evidence,
                    "candidate_counts": dict(counts),
                    "phase_timings_sec": dict(phase_timings_sec),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
            record_phase("proposalPersistence", proposal_started)
            proposal_payload["phase_timings_sec"] = dict(phase_timings_sec)
            proposal_payload["phase_timings_sec"]["totalSec"] = max(
                0.0, monotonic() - started
            )
            parameter_node.step6AssistedLimitProposalJson = canonical_json(
                proposal_payload
            )
            self._runtime_validated_workspace_key = fingerprint(proposal_payload)
            workspace_model.SetAttribute(
                "DENTOBOT.WorkspaceAlgorithm",
                "ROI3D+PositionAxisIK+MoveItStaticStateValidity+BoundedHomeConnectivity",
            )
            for attribute, value in (
                ("DENTOBOT.WorkspaceRuntimeEvaluated", counts["roiCandidateCount"]),
                ("DENTOBOT.WorkspaceAccepted", report.accepted_count),
                (
                    "DENTOBOT.WorkspaceHomeConnectivityEvaluated",
                    counts["homeConnectivityEvaluatedCount"],
                ),
                ("DENTOBOT.WorkspaceHomeConnected", counts["homeConnectedCount"]),
                ("DENTOBOT.WorkspaceRuntimeValidated", "true"),
                ("DENTOBOT.WorkspaceState", "Current"),
                ("DENTOBOT.WorkspaceTaskAxisStatus", axis_status),
            ):
                workspace_model.SetAttribute(attribute, str(value))

            yield_fraction = (
                counts["moveItStaticValidityAcceptedCount"]
                / max(1, counts["moveItStaticValidityAttemptCount"])
            )
            return RobotActionResult(
                True,
                "workspace_ready",
                (
                    f"Generated {counts['roiCandidateCount']} ROI TCP candidates; "
                    f"position-axis IK solved {counts['positionAxisIkSuccessCount']} "
                    f"({counts['positionAxisIkFailureCount']} failed), MoveIt static "
                    f"validity accepted {counts['moveItStaticValidityAcceptedCount']}/"
                    f"{counts['moveItStaticValidityAttemptCount']} evaluated "
                    f"({counts['moveItStaticValidityUnevaluatedCount']} IK solutions "
                    "not evaluated by the bounded MoveIt sample check), and Home "
                    f"connectivity accepted {counts['homeConnectedCount']}/"
                    f"{counts['homeConnectivityEvaluatedCount']}. "
                    f"Task axis: {axis_status}; static-valid yield {yield_fraction:.1%}. "
                    "The ROI bounds sampling only; samples do not prove exact task, route, or guard feasibility."
                    + self._reach_envelope_sentence(reach_envelope)
                ),
                details=details(
                    {
                        "reachEnvelope": reach_envelope,
                        "requestedCount": counts["roiCandidateCount"],
                        "acceptedCount": report.accepted_count,
                        "proposalReviewed": bool(proposal.reviewed),
                        "runtimeValidationStatus": WORKSPACE_RUNTIME_VALIDATION_STATUS,
                        "tcpFkSource": "MoveItRobotState",
                        "moveItStaticValidityRejections": counts[
                            "moveItStaticValidityRejectedCount"
                        ],
                        "homeConnectivityEvaluatedSamples": counts[
                            "homeConnectivityEvaluatedCount"
                        ],
                        "homeConnectedSamples": counts["homeConnectedCount"],
                        "homeConnectivityRejectedSamples": counts[
                            "homeConnectivityRejectedCount"
                        ],
                    }
                ),
                payload=(workspace_model, report, proposal),
            )
        except Exception as exc:
            return fail("workspace_failed", _bounded_text(exc))
        finally:
            self._workspace_generation_active = False
