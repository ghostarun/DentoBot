"""Pure tests for the persistent Step 6 state and phase contracts."""

from dataclasses import replace
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOStep6State import (  # noqa: E402
    BasePlacementStatus,
    JOINT_NAMES,
    MANUAL_SIMULATION_BASE_SOURCE,
    MotionPhase,
    SPINDLE_JOINT_NAME,
    SPINDLE_LOCKED_VALUE_RAD,
    SPINDLE_PLANNING_POLICY,
    approach_points,
    base_placement_source_issue,
    build_assisted_limit_proposal,
    build_motion_diagnostic_session,
    build_phase_guard_configuration,
    build_phase_joint_command,
    build_task_home,
    build_task_snapshot,
    fingerprint,
    parse_task_home,
    parse_motion_diagnostic_session,
    task_snapshot_invalidation_reasons,
    transition_base_status,
)


def joints(value=0.0):
    return {name: float(value + index) for index, name in enumerate(JOINT_NAMES)}


def snapshot():
    home = build_task_home(
        joints(), base_fingerprint="base-a", robot_profile_fingerprint="robot-a"
    )
    return build_task_snapshot(
        target_segment_id="FDI14",
        trajectory_revision="trajectory-a",
        entry_ras_mm=(1.0, 2.0, 3.0),
        target_ras_mm=(1.0, 2.0, -7.0),
        base_fingerprint="base-a",
        home_fingerprint=fingerprint(home.to_dict()),
        limits_fingerprint="limits-a",
        robot_profile_fingerprint="robot-a",
    )


def test_base_state_transitions_fail_closed_and_reserve_registered_lock():
    assert transition_base_status("Unlocked", "provisional_lock") == (
        BasePlacementStatus.PROVISIONAL_LOCKED
    )
    assert transition_base_status("ProvisionalLocked", "invalidate") == (
        BasePlacementStatus.STALE
    )
    assert transition_base_status("Stale", "unlock") == BasePlacementStatus.UNLOCKED
    with pytest.raises(ValueError, match="future verified registration"):
        transition_base_status("Unlocked", "registered_lock")


def test_provisional_base_requires_explicit_manual_simulation_source():
    assert not base_placement_source_issue(
        "ProvisionalLocked",
        MANUAL_SIMULATION_BASE_SOURCE,
        True,
    )
    assert "predates" in base_placement_source_issue(
        "ProvisionalLocked",
        "manual-mount-plane",
        True,
    )
    assert "explicitly reviewed" in base_placement_source_issue(
        "Unlocked",
        "operator-unlocked",
        True,
    )
    assert not base_placement_source_issue(
        "Stale",
        "quarantined-circular-mount-plane",
        False,
    )


def test_task_home_round_trip_is_versioned_and_case_base_specific():
    record = build_task_home(
        joints(0.25),
        base_fingerprint="base-a",
        robot_profile_fingerprint="robot-a",
        revision=3,
    )
    restored = parse_task_home(record.to_dict())
    assert restored == record
    assert restored.revision == 3
    assert restored.joint_names == JOINT_NAMES
    assert restored.joint_positions_si[-1] == SPINDLE_LOCKED_VALUE_RAD
    assert restored.spindle_planning_policy == SPINDLE_PLANNING_POLICY


def test_legacy_nonzero_spindle_home_migrates_without_changing_arm_pose():
    legacy = build_task_home(
        joints(0.25),
        base_fingerprint="base-a",
        robot_profile_fingerprint="robot-a",
    ).to_dict()
    legacy.pop("spindle_planning_policy")
    legacy.pop("spindle_locked_value_rad")
    legacy["joint_positions_si"][-1] = 2.75
    restored = parse_task_home(legacy)
    assert restored.joint_positions_si[:-1] == tuple(legacy["joint_positions_si"][:-1])
    assert restored.joint_positions_si[-1] == 0.0
    assert restored.joint_names[-1] == SPINDLE_JOINT_NAME


def test_workspace_limit_suggestion_retains_observed_range_and_needs_review():
    proposal = build_assisted_limit_proposal(
        ((0, 10, 20, 30, 40, 50), (10, 20, 30, 40, 50, 60)),
        (-100, 0, -100, 0, -100, -360),
        (360, 80, 360, 75, 360, 360),
    )
    assert proposal.accepted_sample_count == 2
    assert not proposal.reviewed
    assert proposal.minimum_display[0] < 0
    assert proposal.maximum_display[0] > 10
    assert proposal.minimum_display[1] >= 0


def test_task_dependency_changes_invalidate_confirmation_but_display_does_not():
    confirmed = snapshot()
    assert task_snapshot_invalidation_reasons(
        confirmed,
        target_segment_id="FDI14",
        trajectory_revision="trajectory-a",
        base_fingerprint="base-a",
        home_fingerprint=confirmed.home_fingerprint,
        limits_fingerprint="limits-a",
        robot_profile_fingerprint="robot-a",
        tool_frame="dentobot_drill_tip_provisional",
    ) == ()
    reasons = task_snapshot_invalidation_reasons(
        confirmed,
        target_segment_id="FDI13",
        trajectory_revision="trajectory-b",
        base_fingerprint="base-b",
        home_fingerprint="home-b",
        limits_fingerprint="limits-b",
        robot_profile_fingerprint="robot-b",
        tool_frame="calibrated-tip",
    )
    assert reasons == (
        "target tooth",
        "trajectory",
        "base pose",
        "Task Home",
        "assisted limits",
        "robot resources",
        "tool profile",
    )
    # Camera and opacity are intentionally absent from the dependency contract.
    assert replace(confirmed, corridor_radius_mm=confirmed.corridor_radius_mm)


def test_phase_schema_binds_commands_to_one_immutable_task():
    confirmed = snapshot()
    config = build_phase_guard_configuration(
        confirmed, target_object_id="dentobot_target_FDI14"
    )
    command = build_phase_joint_command(
        task_fingerprint=confirmed.snapshot_fingerprint,
        phase=MotionPhase.DRILLING,
        sequence=7,
        joint_positions_si=joints(),
    )
    assert config.allowed_contact_pair == ("burr", "dentobot_target_FDI14")
    assert command.phase is MotionPhase.DRILLING
    assert command.task_fingerprint == config.task_fingerprint
    assert command.to_dict()["phase"] == "drilling"
    assert command.joint_positions_si[-1] == SPINDLE_LOCKED_VALUE_RAD
    with pytest.raises(ValueError, match="task fingerprint"):
        build_phase_joint_command(
            task_fingerprint="",
            phase="approach",
            sequence=0,
            joint_positions_si=joints(),
        )


def test_approach_uses_five_mm_pre_entry_standoff_without_changing_entry():
    pre_entry, entry = approach_points((0, 0, 0), (0, 0, -10), 5.0)
    assert pre_entry == pytest.approx((0, 0, 5))
    assert entry == (0.0, 0.0, 0.0)


def test_approach_uses_two_mm_research_default_for_new_cases():
    pre_entry, entry = approach_points((0, 0, 0), (0, 0, -10))
    assert pre_entry == pytest.approx((0, 0, 2))
    assert entry == (0.0, 0.0, 0.0)


def _motion_candidate():
    return {
        "candidate_index": 0,
        "axial_roll_deg": 0.0,
        "success": True,
        "completion_fraction": 1.0,
        "completed_distance_mm": 2.0,
        "requested_distance_mm": 2.0,
        "waypoint_count": 3,
        "failure_classification": "none",
    }


def _motion_diagnostic(*, schema_version, stage_name):
    return build_motion_diagnostic_session(
        state="Current",
        task_fingerprint="task-a",
        base_fingerprint="base-a",
        trajectory_fingerprint="trajectory-a",
        robot_profile_fingerprint="robot-a",
        collision_audit_fingerprint="collision-a",
        planning_parameters_fingerprint="planner-a",
        candidate_records=(_motion_candidate(),),
        selected_candidate_index=0,
        failure_classification="none",
        schema_version=schema_version,
        stage_outcomes=(
            {"stage": "stage1_free_space", "status": "Passed"},
            {"stage": stage_name, "status": "Passed"},
            {"stage": "stage3_drilling", "status": "Passed"},
        ),
        full_task_outcome={"status": "Complete"},
    )


def test_motion_diagnostic_v21_names_fixed_axis_terminal_stage():
    record = _motion_diagnostic(
        schema_version="2.1",
        stage_name="stage2_fixed_axis_terminal",
    )
    assert parse_motion_diagnostic_session(record.to_dict()) == record


def test_motion_diagnostic_v20_remains_readable_after_stage2_policy_upgrade():
    record = _motion_diagnostic(
        schema_version="2.0",
        stage_name="stage2_strict_axis",
    )
    assert parse_motion_diagnostic_session(record.to_dict()) == record
