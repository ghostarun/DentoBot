"""Pure tests for the persistent Step 6 state and phase contracts."""

import ast
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOStep6State import (  # noqa: E402
    BasePlacementStatus,
    DENTAL_FDI_TOOTH_IDS,
    JOINT_NAMES,
    LEGACY_JOINT_NAMES,
    MANUAL_SIMULATION_BASE_SOURCE,
    MotionPhase,
    SIMULATION_TARGET_DEPTH_CAP_MM,
    SIMULATION_TOOL_PROVENANCE,
    SPINDLE_PLANNING_POLICY,
    approach_points,
    base_placement_source_issue,
    build_assisted_limit_proposal,
    build_attempt_context,
    build_motion_diagnostic_session,
    build_phase_guard_configuration,
    build_phase_joint_command,
    build_task_home,
    build_task_snapshot,
    build_robot_environment_snapshot,
    canonical_json,
    cap_simulation_target,
    fingerprint,
    empty_trajectory_registry,
    parse_attempt_context,
    parse_robot_environment_snapshot,
    parse_trajectory_registry,
    prepared_branch_ids_for_trajectory,
    parse_task_home,
    parse_task_snapshot,
    parse_motion_diagnostic_session,
    task_snapshot_invalidation_reasons,
    transition_base_status,
    robot_environment_invalidation_scopes,
    select_prepared_branch,
    select_trajectory_record,
    stale_trajectory_record,
    upsert_guide_set,
    upsert_trajectory_record,
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


def registry_with_trajectory(
    registry, tooth: str, ordinal: int, *, fingerprint_value: str | None = None
):
    return upsert_trajectory_record(
        registry,
        tooth_id=tooth,
        target_id=f"target-{tooth}",
        segment_id=f"segment-{tooth}",
        trajectory_id=f"trajectory-{tooth}-{ordinal}",
        trajectory_node_id=f"vtkMRMLMarkupsLineNode{tooth}-{ordinal}",
        trajectory_fingerprint=fingerprint_value or f"geometry-{tooth}-{ordinal}",
        provenance="manual",
    )


def test_reusable_environment_and_attempt_contracts_are_target_independent():
    matrix = tuple(float(value) for value in range(16))
    home = build_task_home(
        joints(),
        base_fingerprint="base-a",
        robot_profile_fingerprint="robot-a",
        runtime_validation_status="Validated",
        collision_audit_fingerprint="live-audit",
        guard_policy_fingerprint="live-guard",
        validated_at_utc="2026-09-09T12:00:00+00:00",
    ).to_dict()
    environment = build_robot_environment_snapshot(
        case_identity="case-a",
        anatomy_fingerprint="anatomy-a",
        jaw_source_fingerprint="jaw-a",
        jaw_landmarks_fingerprint="landmarks-a",
        jaw_configuration_fingerprint="jaw-config-a",
        jaw_transform_matrix=matrix,
        mouth_gap_mm=40.0,
        robot_profile_fingerprint="robot-a",
        tool_identity="dentobot_drill_tcp",
        tool_fingerprint="tool-a",
        base_matrix=matrix,
        base_status="ProvisionalLocked",
        base_locked=True,
        base_fingerprint="base-a",
        task_home_configuration=home,
    )
    restored = parse_robot_environment_snapshot(environment.to_dict())
    assert restored == environment
    assert "runtime_validation_status" not in restored.task_home_configuration
    assert "collision_audit_fingerprint" not in restored.task_home_configuration

    attempt = build_attempt_context(
        environment_fingerprint=environment.environment_fingerprint,
        target_id="target-FDI11",
        tooth_id="FDI11",
        trajectory_id="trajectory-FDI11-1",
        trajectory_fingerprint="trajectory-fingerprint",
        guide_set_id="guide-FDI11",
        guide_set_fingerprint="guide-fingerprint",
    )
    assert parse_attempt_context(attempt.to_dict()) == attempt
    other_target = build_attempt_context(
        environment_fingerprint=environment.environment_fingerprint,
        target_id="target-FDI21",
        tooth_id="FDI21",
        trajectory_id="trajectory-FDI21-1",
        trajectory_fingerprint="other-trajectory-fingerprint",
    )
    assert other_target.environment_fingerprint == attempt.environment_fingerprint
    assert other_target.attempt_fingerprint != attempt.attempt_fingerprint


def test_case_foundation_v2_and_registry_v3_migrate_fail_closed():
    matrix = tuple(float(value) for value in range(16))
    foundation = build_robot_environment_snapshot(
        case_identity="case-a",
        anatomy_fingerprint="anatomy-a",
        source_volume_fingerprint="volume-content-geometry-a",
        source_segmentation_fingerprint="reviewed-segmentation-a",
        jaw_source_fingerprint="jaw-a",
        jaw_landmarks_fingerprint="landmarks-a",
        landmark_positions_ras_mm=tuple(float(value) for value in range(12)),
        landmark_review_fingerprint="surface-review-a",
        hinge_model_schema="PureTMJHingeRotationV2",
        jaw_configuration_fingerprint="jaw-config-a",
        jaw_transform_matrix=matrix,
        mouth_gap_mm=40.0,
        opening_revision=3,
        robot_profile_fingerprint="robot-a",
        base_matrix=matrix,
        base_status="ProvisionalLocked",
        base_locked=True,
        base_fingerprint="base-a",
        base_authority="manual-simulation-base",
        base_revision=2,
    )
    restored = parse_robot_environment_snapshot(foundation.to_dict())
    assert restored.schema_version == "2.0"
    assert restored.planning_pose_fingerprint == foundation.planning_pose_fingerprint
    assert restored.base_setup_fingerprint == foundation.base_setup_fingerprint
    assert restored.foundation_fingerprint == foundation.foundation_fingerprint

    registry = registry_with_trajectory(empty_trajectory_registry(), "FDI11", 1)
    registry = upsert_guide_set(
        registry,
        guide_set_id="branch-a",
        target_id="target-FDI11",
        trajectory_ids=("trajectory-FDI11-1",),
        planning_pose_fingerprint=foundation.planning_pose_fingerprint,
    )
    assert registry["schema_version"] == "3.0"
    assert registry["prepared_branches"]["branch-a"][
        "planning_pose_fingerprint"
    ] == foundation.planning_pose_fingerprint

    legacy = json.loads(canonical_json(registry))
    legacy["schema_version"] = "2.0"
    legacy["prepared_branches"]["branch-a"].pop("planning_pose_fingerprint")
    migrated = parse_trajectory_registry(legacy)
    branch = migrated["prepared_branches"]["branch-a"]
    assert migrated["schema_version"] == "3.0"
    assert branch["planning_pose_fingerprint"] == ""
    assert branch["state"] == "Stale"
    assert "Case Foundation" in branch["stale_reason"]


def test_case_foundation_v2_rejects_malformed_or_nonfinite_state():
    matrix = tuple(float(value) for value in range(16))
    foundation = build_robot_environment_snapshot(
        source_volume_fingerprint="volume-a",
        source_segmentation_fingerprint="segmentation-a",
        landmark_positions_ras_mm=tuple(float(value) for value in range(12)),
        hinge_model_schema="PureTMJHingeRotationV2",
        jaw_transform_matrix=matrix,
        mouth_gap_mm=40.0,
    )
    missing = foundation.to_dict()
    missing.pop("planning_pose_fingerprint")
    with pytest.raises(ValueError, match="missing required fields"):
        parse_robot_environment_snapshot(missing)
    tampered = foundation.to_dict()
    tampered["mouth_gap_mm"] = 41.0
    with pytest.raises(ValueError, match="fingerprint does not match"):
        parse_robot_environment_snapshot(tampered)
    with pytest.raises(ValueError, match="finite"):
        build_robot_environment_snapshot(
            jaw_transform_matrix=(*matrix[:-1], float("nan")),
            mouth_gap_mm=40.0,
        )
    unsupported = foundation.to_dict()
    unsupported["schema_version"] = "9.0"
    with pytest.raises(ValueError, match="unsupported"):
        parse_robot_environment_snapshot(unsupported)


def test_environment_changes_invalidate_only_real_shared_dependencies():
    identity = tuple(float(value) for value in range(16))
    common = dict(
        case_identity="case-a",
        anatomy_fingerprint="anatomy-a",
        jaw_source_fingerprint="jaw-a",
        jaw_landmarks_fingerprint="landmarks-a",
        jaw_configuration_fingerprint="jaw-config-a",
        jaw_transform_matrix=identity,
        mouth_gap_mm=40.0,
        robot_profile_fingerprint="robot-a",
        tool_identity="tool-a",
        tool_fingerprint="tool-fingerprint-a",
        base_matrix=identity,
        base_status="ProvisionalLocked",
        base_locked=True,
        base_fingerprint="base-a",
        task_home_configuration={"joint_positions_si": [0, 1, 2, 3, 4]},
    )
    original = build_robot_environment_snapshot(**common)
    assert robot_environment_invalidation_scopes(original, original) == ()
    for changed in (
        {"jaw_source_fingerprint": "jaw-b"},
        {"jaw_landmarks_fingerprint": "landmarks-b"},
        {"jaw_configuration_fingerprint": "jaw-config-b"},
        {"mouth_gap_mm": 41.0},
    ):
        jaw_changed = build_robot_environment_snapshot(**{**common, **changed})
        assert robot_environment_invalidation_scopes(original, jaw_changed) == (
            "jaw", "base", "home", "attempt"
        )
    robot_changed = build_robot_environment_snapshot(
        **{**common, "robot_profile_fingerprint": "robot-b"}
    )
    assert robot_environment_invalidation_scopes(original, robot_changed) == (
        "base", "home", "attempt"
    )
    base_changed = build_robot_environment_snapshot(
        **{**common, "base_fingerprint": "base-b"}
    )
    assert robot_environment_invalidation_scopes(original, base_changed) == (
        "home", "attempt"
    )
    home_changed = build_robot_environment_snapshot(
        **{**common, "task_home_configuration": {"joint_positions_si": [1] * 5}}
    )
    assert robot_environment_invalidation_scopes(original, home_changed) == (
        "attempt",
    )


def test_32_by_3_registry_has_explicit_slots_and_rejects_a_fourth():
    registry = empty_trajectory_registry()
    assert tuple(registry["teeth"]) == DENTAL_FDI_TOOTH_IDS
    assert all(
        [slot["state"] for slot in tooth["trajectory_set"]["slots"]] == ["Empty"] * 3
        for tooth in registry["teeth"].values()
    )
    for ordinal in range(1, 4):
        registry = registry_with_trajectory(registry, "FDI11", ordinal)
    assert [
        slot["trajectory_id"]
        for slot in registry["teeth"]["FDI11"]["trajectory_set"]["slots"]
    ] == [
        "trajectory-FDI11-1",
        "trajectory-FDI11-2",
        "trajectory-FDI11-3",
    ]
    with pytest.raises(ValueError, match="fourth"):
        registry_with_trajectory(registry, "FDI11", 4)
    assert parse_trajectory_registry(canonical_json(registry)) == registry


def test_registry_stores_branches_once_and_preserves_scoped_staleness():
    registry = empty_trajectory_registry()
    registry = registry_with_trajectory(registry, "FDI11", 1)
    registry = registry_with_trajectory(registry, "FDI11", 2)
    registry = registry_with_trajectory(registry, "FDI11", 3)
    registry = registry_with_trajectory(registry, "FDI21", 1)
    registry = upsert_guide_set(
        registry,
        guide_set_id="guide-FDI11-T1",
        target_id="target-FDI11",
        trajectory_ids=("trajectory-FDI11-1",),
        template_id="template-FDI11-T1",
        template_node_id="template-11-t1",
        shell_id="shell-FDI11-T1",
        shell_node_id="shell-11-t1",
        model_node_ids=("template-11-t1", "shell-11-t1"),
        guide_fingerprint="guide-fingerprint-11-t1",
    )
    registry = upsert_guide_set(
        registry,
        guide_set_id="guide-FDI11-T2",
        target_id="target-FDI11",
        trajectory_ids=("trajectory-FDI11-2",),
        template_id="template-FDI11-T2",
        template_node_id="template-11-t2",
        shell_id="shell-FDI11-T2",
        shell_node_id="shell-11-t2",
        model_node_ids=("template-11-t2", "shell-11-t2"),
        guide_fingerprint="guide-fingerprint-11-t2",
    )
    registry = select_prepared_branch(registry, "guide-FDI11-T1")
    assert registry["selected_branch_id"] == "guide-FDI11-T1"
    registry = stale_trajectory_record(
        registry, "trajectory-FDI11-1", "trajectory geometry changed"
    )
    slots11 = registry["teeth"]["FDI11"]["trajectory_set"]["slots"]
    slots21 = registry["teeth"]["FDI21"]["trajectory_set"]["slots"]
    assert slots11[0]["state"] == "Stale"
    assert slots11[1]["state"] == "Current"
    assert slots11[2]["state"] == "Current"
    assert slots21[0]["state"] == "Current"
    assert slots11[0]["prepared_branch_ids"] == ["guide-FDI11-T1"]
    assert slots11[1]["prepared_branch_ids"] == ["guide-FDI11-T2"]
    assert slots11[2]["prepared_branch_ids"] == []
    assert registry["prepared_branches"]["guide-FDI11-T1"]["state"] == "Stale"
    assert registry["prepared_branches"]["guide-FDI11-T2"]["state"] == "Current"


def test_registry_allows_a_pair_but_rejects_a_three_trajectory_template():
    registry = empty_trajectory_registry()
    for ordinal in (1, 2, 3):
        registry = registry_with_trajectory(registry, "FDI11", ordinal)
    registry = upsert_guide_set(
        registry,
        guide_set_id="guide-FDI11-pair",
        target_id="target-FDI11",
        trajectory_ids=("trajectory-FDI11-1", "trajectory-FDI11-2"),
        pairing_intent="ExplicitPair",
    )
    assert prepared_branch_ids_for_trajectory(
        registry, "trajectory-FDI11-1"
    ) == ("guide-FDI11-pair",)
    assert registry["prepared_branches"]["guide-FDI11-pair"][
        "pairing_intent"
    ] == "ExplicitPair"
    with pytest.raises(ValueError, match="two at most"):
        upsert_guide_set(
            registry,
            guide_set_id="guide-FDI11-triple",
            target_id="target-FDI11",
            trajectory_ids=(
                "trajectory-FDI11-1",
                "trajectory-FDI11-2",
                "trajectory-FDI11-3",
            ),
        )


def test_registry_migrates_legacy_pair_fail_closed():
    registry = empty_trajectory_registry()
    registry = registry_with_trajectory(registry, "FDI11", 1)
    registry = registry_with_trajectory(registry, "FDI11", 2)
    tooth = registry["teeth"]["FDI11"]
    registry["schema_version"] = "1.0"
    legacy_guide = {
        "guide_set_id": "guide-FDI11-pair",
        "target_id": "target-FDI11",
        "trajectory_ids": ["trajectory-FDI11-1", "trajectory-FDI11-2"],
        "template_id": "template-FDI11-pair",
        "template_node_id": "template-11-pair",
        "shell_id": "shell-FDI11",
        "shell_node_id": "shell-11",
        "model_node_ids": ["template-11-pair", "shell-11"],
        "fingerprint": "guide-fingerprint-11-pair",
        "state": "Current",
        "stale_reason": "",
    }
    tooth["guide_set"] = legacy_guide
    for slot in tooth["trajectory_set"]["slots"]:
        slot.pop("guide_set", None)

    migrated = parse_trajectory_registry(registry)

    assert "guide_set" not in migrated["teeth"]["FDI11"]
    slots = migrated["teeth"]["FDI11"]["trajectory_set"]["slots"]
    assert slots[0]["prepared_branch_ids"] == ["guide-FDI11-pair"]
    assert slots[1]["prepared_branch_ids"] == ["guide-FDI11-pair"]
    assert slots[2]["prepared_branch_ids"] == []
    branch = migrated["prepared_branches"]["guide-FDI11-pair"]
    assert branch["pairing_intent"] == "LegacyUnverified"
    assert branch["state"] == "Stale"


def test_registry_rejects_unknown_selected_branch_at_the_trust_boundary():
    registry = registry_with_trajectory(empty_trajectory_registry(), "FDI11", 1)
    registry = registry_with_trajectory(registry, "FDI21", 1)
    registry["selected_branch_id"] = "missing"
    with pytest.raises(ValueError, match="not registered"):
        parse_trajectory_registry(registry)


def test_raw_trajectory_selection_requires_one_unambiguous_current_branch():
    registry = registry_with_trajectory(empty_trajectory_registry(), "FDI11", 1)
    with pytest.raises(ValueError, match="exactly one"):
        select_trajectory_record(registry, "trajectory-FDI11-1")
    registry = upsert_guide_set(
        registry,
        guide_set_id="branch-one",
        target_id="target-FDI11",
        trajectory_ids=("trajectory-FDI11-1",),
    )
    assert select_trajectory_record(registry, "trajectory-FDI11-1")[
        "selected_branch_id"
    ] == "branch-one"


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
    assert len(restored.joint_positions_si) == 5
    assert restored.spindle_planning_policy == SPINDLE_PLANNING_POLICY


def test_legacy_nonzero_spindle_home_migrates_without_changing_arm_pose():
    legacy = build_task_home(
        joints(0.25),
        base_fingerprint="base-a",
        robot_profile_fingerprint="robot-a",
    ).to_dict()
    legacy["joint_names"] = list(LEGACY_JOINT_NAMES)
    legacy["joint_positions_si"] = [
        *legacy["joint_positions_si"],
        2.75,
    ]
    legacy.pop("spindle_planning_policy")
    legacy.pop("spindle_locked_value_rad")
    restored = parse_task_home(legacy)
    assert restored.joint_positions_si == tuple(legacy["joint_positions_si"][:-1])
    assert restored.joint_names == JOINT_NAMES


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
        tool_frame="dentobot_drill_tcp",
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
    assert command.joint_names == JOINT_NAMES
    assert len(command.joint_positions_si) == 5
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


def test_simulation_target_cap_preserves_axis_round_trip_and_rejects_invalid_inputs():
    entry = (1.0, 2.0, 3.0)
    long_target = (4.0, 6.0, 15.0)  # 13 mm, non-axis aligned
    capped = cap_simulation_target(entry, long_target)
    assert capped == pytest.approx(
        tuple(
            entry[index]
            + (SIMULATION_TARGET_DEPTH_CAP_MM / 13.0)
            * (long_target[index] - entry[index])
            for index in range(3)
        )
    )
    assert sum((capped[index] - entry[index]) ** 2 for index in range(3)) ** 0.5 == pytest.approx(
        SIMULATION_TARGET_DEPTH_CAP_MM
    )

    short_target = (1.0, 2.0, -3.0)
    assert cap_simulation_target(entry, short_target) == tuple(
        float(value) for value in short_target
    )
    assert cap_simulation_target(entry, (1.0, 2.0, 5.0)) == (1.0, 2.0, 5.0)
    seven_point_nine_target = (1.0, 2.0, 3.0 + 7.977207292891484)
    clipped = cap_simulation_target(entry, seven_point_nine_target)
    assert sum((clipped[index] - entry[index]) ** 2 for index in range(3)) ** 0.5 == pytest.approx(
        SIMULATION_TARGET_DEPTH_CAP_MM
    )

    home = build_task_home(
        joints(), base_fingerprint="base-a", robot_profile_fingerprint="robot-a"
    )
    snapshot_record = build_task_snapshot(
        target_segment_id="FDI11",
        trajectory_revision="trajectory-a",
        entry_ras_mm=entry,
        target_ras_mm=capped,
        base_fingerprint="base-a",
        home_fingerprint=fingerprint(home.to_dict()),
        limits_fingerprint="limits-a",
        robot_profile_fingerprint="robot-a",
        tool_provenance=SIMULATION_TOOL_PROVENANCE,
    )
    assert parse_task_snapshot(snapshot_record.to_dict()) == snapshot_record
    guard = build_phase_guard_configuration(snapshot_record, target_object_id="FDI11")
    assert guard.target_ras_mm == capped
    assert guard.task_fingerprint == snapshot_record.snapshot_fingerprint
    legacy_record = build_task_snapshot(
        target_segment_id="FDI11",
        trajectory_revision="trajectory-a",
        entry_ras_mm=entry,
        target_ras_mm=seven_point_nine_target,
        base_fingerprint="base-a",
        home_fingerprint=fingerprint(home.to_dict()),
        limits_fingerprint="limits-a",
        robot_profile_fingerprint="robot-a",
        tool_provenance="CAD-derived/provisional/un-calibrated",
    )
    assert parse_task_snapshot(legacy_record.to_dict()).target_ras_mm == tuple(
        float(value) for value in seven_point_nine_target
    )

    invalid = (
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (float("nan"), 1.0, 1.0)),
        ((0.0, 0.0, 0.0), (float("inf"), 1.0, 1.0)),
        ((1.0e308, 0.0, 0.0), (-1.0e308, 0.0, 0.0)),
        ((0.0, 0.0), (1.0, 2.0, 3.0)),
        ((0.0, 0.0, 0.0), (1.0, 2.0, 3.0, 4.0)),
    )
    for bad_entry, bad_target in invalid:
        with pytest.raises(ValueError):
            cap_simulation_target(bad_entry, bad_target)


def test_confirmed_task_freshness_rejects_legacy_tool_policy():
    legacy = snapshot()
    source_path = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "confirmedTaskFreshnessIssues"
    )
    namespace = {
        "_": lambda value: value,
        "json": json,
        "SIMULATION_TARGET_DEPTH_CAP_MM": SIMULATION_TARGET_DEPTH_CAP_MM,
        "SIMULATION_TOOL_PROVENANCE": SIMULATION_TOOL_PROVENANCE,
        "task_snapshot_invalidation_reasons": task_snapshot_invalidation_reasons,
    }
    exec(compile(ast.Module([method], type_ignores=[]), str(source_path), "exec"), namespace)

    class Probe:
        @staticmethod
        def step6AnatomyReviewFreshnessIssues(_parameter):
            return ()

        @staticmethod
        def step6BasePlacementFreshnessIssues(_parameter):
            return ()

        @staticmethod
        def confirmedTaskRecord(_parameter):
            return legacy

    parameter_node = SimpleNamespace(
        targetToothSegmentId="FDI14",
        step6ToolFrame="dentobot_drill_tcp",
    )
    issues = namespace["confirmedTaskFreshnessIssues"](Probe(), parameter_node)
    assert issues == (
        "Confirmed Step 6 task uses an older simulation Target policy; "
        "reconfirm the Step 6 task for the 6 mm cap.",
    )


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
