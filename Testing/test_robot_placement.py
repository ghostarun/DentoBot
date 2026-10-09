"""Pure tests for draft Slicer robot placement geometry."""

from pathlib import Path
import ast
import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIRECTORY = REPOSITORY_ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HELPER_DIRECTORY))

from DENTORobotPlacement import (
    hinge_rotation_matrix,
    joint_positions_si_from_display,
    local_nudge_matrix,
    orthonormal_plane_pose,
    robot_link_mesh_poses_mm,
    solve_hinge_rotation_for_gap,
    solve_anatomy_directed_hinge_rotation_for_gap,
    validate_patient_ras_condylar_landmarks,
    world_transform_to_parent_local,
)
from DENTOStep6State import JOINT_NAMES, build_task_home, canonical_json, parse_task_home


URDF_PATH = REPOSITORY_ROOT / "dentobot_description" / "urdf" / "dentobot.urdf"
DESCRIPTION_ROOT = REPOSITORY_ROOT / "dentobot_description"


def test_selected_zero_and_reversed_joint_four_match_robot_description() -> None:
    zero_positions = joint_positions_si_from_display(0, 0, 0, 0, 0)
    zero_poses = {
        pose.link_name: pose
        for pose in robot_link_mesh_poses_mm(
            URDF_PATH,
            DESCRIPTION_ROOT,
            zero_positions,
        )
    }
    assert len(zero_poses) == 7
    assert np.allclose(
        zero_poses["burr"].matrix_base_from_link_mm[:3, 3],
        # J2=0 is the mechanically extended/home end in the current URDF.
        (-49.564540494, 1.369804798, 117.675185601),
        atol=1e-6,
    )

    moved_positions = dict(zero_positions)
    moved_positions["link-4_Slider-4"] = 0.01
    moved_poses = {
        pose.link_name: pose
        for pose in robot_link_mesh_poses_mm(
            URDF_PATH,
            DESCRIPTION_ROOT,
            moved_positions,
        )
    }
    displacement = (
        moved_poses["link-5"].matrix_base_from_link_mm[:3, 3]
        - zero_poses["link-5"].matrix_base_from_link_mm[:3, 3]
    )
    assert displacement[0] < -9.99
    assert abs(displacement[1]) < 0.23
    assert abs(displacement[2]) < 1e-9


def test_plane_snap_removes_scale_and_local_nudges_follow_snapped_axes() -> None:
    plane = np.eye(4, dtype=float)
    plane[:3, 0] = (0.0, 2.0, 0.0)
    plane[:3, 1] = (-3.0, 0.0, 0.0)
    plane[:3, 2] = (0.0, 0.0, 4.0)
    plane[:3, 3] = (12.0, -8.0, 25.0)
    snapped = orthonormal_plane_pose(plane)
    assert np.allclose(snapped[:3, :3].T @ snapped[:3, :3], np.eye(3), atol=1e-12)
    assert np.linalg.det(snapped[:3, :3]) > 0.999999
    assert np.allclose(snapped[:3, 3], plane[:3, 3])

    nudged = local_nudge_matrix(snapped, translation_local_mm=(2.0, 0.0, 0.0))
    assert np.allclose(nudged[:3, 3], (12.0, -6.0, 25.0), atol=1e-12)
    rotated = local_nudge_matrix(snapped, rotation_local_deg=(0.0, 0.0, 90.0))
    assert np.allclose(rotated[:3, 3], snapped[:3, 3])
    assert np.allclose(rotated[:3, 2], snapped[:3, 2], atol=1e-12)


def test_draft_jaw_opening_is_pure_tmj_hinge_rotation_to_40_mm_gap() -> None:
    left_tmj = np.asarray((-50.0, 0.0, 0.0))
    right_tmj = np.asarray((50.0, 0.0, 0.0))
    upper_incisor = np.asarray((0.0, -90.0, -10.0))
    lower_closed = np.asarray((0.0, -90.0, -12.0))

    angle, matrix, opened_lower, gap = solve_hinge_rotation_for_gap(
        left_tmj,
        right_tmj,
        upper_incisor,
        lower_closed,
        40.0,
    )

    assert abs(angle) > 1.0
    assert abs(gap - 40.0) < 0.1
    assert np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-12)
    assert np.isclose(np.linalg.det(matrix[:3, :3]), 1.0, atol=1e-12)
    for hinge_point in (left_tmj, right_tmj):
        transformed = (matrix @ np.append(hinge_point, 1.0))[:3]
        assert np.allclose(transformed, hinge_point, atol=1e-9)
    assert np.allclose(
        opened_lower,
        (hinge_rotation_matrix(left_tmj, right_tmj, angle)
         @ np.append(lower_closed, 1.0))[:3],
    )


def test_draft_jaw_opening_rejects_degenerate_hinge() -> None:
    point = np.asarray((1.0, 2.0, 3.0))
    with np.testing.assert_raises_regex(ValueError, "distinct"):
        solve_hinge_rotation_for_gap(
            point,
            point,
            np.asarray((0.0, 0.0, 0.0)),
            np.asarray((0.0, 0.0, -2.0)),
        )


def test_case_jaw_opening_uses_only_gap_increasing_direction() -> None:
    left_tmj = np.asarray((-50.0, 0.0, 0.0))
    right_tmj = np.asarray((50.0, 0.0, 0.0))
    upper = np.asarray((0.0, -90.0, -10.0))
    lower = np.asarray((0.0, -90.0, -12.0))

    angle, matrix, opened, gap = solve_anatomy_directed_hinge_rotation_for_gap(
        left_tmj,
        right_tmj,
        upper,
        lower,
        40.0,
    )

    assert abs(gap - 40.0) <= 0.01
    assert angle != 0.0
    assert opened[2] < lower[2]
    assert np.linalg.norm(opened - upper) > np.linalg.norm(lower - upper)
    for hinge_point in (left_tmj, right_tmj):
        transformed = (matrix @ np.append(hinge_point, 1.0))[:3]
        assert np.allclose(transformed, hinge_point, atol=1e-9)


def test_case_jaw_opening_uses_inferior_branch_for_representative_ras_geometry() -> None:
    left_tmj = np.asarray((-132.735245, -96.085297, 73.430153))
    right_tmj = np.asarray((-47.763081, -95.850441, 76.087006))
    upper = np.asarray((-86.294014, -49.384068, 50.155613))
    lower = np.asarray((-87.795975, -45.079147, 51.003372))

    angle, _matrix, opened, gap = solve_anatomy_directed_hinge_rotation_for_gap(
        left_tmj,
        right_tmj,
        upper,
        lower,
        40.0,
    )

    assert angle < 0.0
    assert opened[2] < lower[2]
    assert abs(gap - 40.0) <= 0.01


def test_patient_ras_condylar_laterality_uses_positive_x_as_patient_right() -> None:
    review = validate_patient_ras_condylar_landmarks(
        np.asarray((-48.0, -32.0, 20.0)),
        np.asarray((51.0, -31.0, 21.0)),
    )
    assert review["leftRasXmm"] < review["rightRasXmm"]
    assert review["separationMm"] > 90.0
    with np.testing.assert_raises_regex(ValueError, "side-swapped"):
        validate_patient_ras_condylar_landmarks(
            np.asarray((48.0, -32.0, 20.0)),
            np.asarray((-51.0, -31.0, 21.0)),
        )


def test_case_jaw_opening_rejects_already_open_and_unreachable_targets() -> None:
    left_tmj = np.asarray((-50.0, 0.0, 0.0))
    right_tmj = np.asarray((50.0, 0.0, 0.0))
    upper = np.asarray((0.0, -90.0, -10.0))
    lower = np.asarray((0.0, -90.0, -50.0))
    with np.testing.assert_raises_regex(ValueError, "already reaches"):
        solve_anatomy_directed_hinge_rotation_for_gap(
            left_tmj,
            right_tmj,
            upper,
            lower,
            40.0,
        )
    with np.testing.assert_raises_regex(ValueError, "unreachable"):
        solve_anatomy_directed_hinge_rotation_for_gap(
            left_tmj,
            right_tmj,
            np.asarray((0.0, -1.0, -10.0)),
            np.asarray((0.0, -1.0, -12.0)),
            40.0,
            maximum_angle_deg=1.0,
        )


def test_draft_jaw_opening_hinge_survives_workspace_parent_translation() -> None:
    """World hinge rotation must be expressed in workspace-local parent space."""

    parent_to_world = np.eye(4, dtype=float)
    parent_to_world[:3, 3] = (0.0, -50.0, -1305.0)

    def to_world(native: np.ndarray) -> np.ndarray:
        return (parent_to_world @ np.append(native, 1.0))[:3]

    left_native = np.asarray((-45.0, -105.0, 1500.0))
    right_native = np.asarray((45.0, -105.0, 1500.0))
    upper_native = np.asarray((0.0, -178.0, 1472.0))
    lower_native = np.asarray((0.0, -175.0, 1468.0))
    left_world = to_world(left_native)
    right_world = to_world(right_native)
    upper_world = to_world(upper_native)
    lower_world = to_world(lower_native)

    angle, world_matrix, opened_lower, gap = solve_hinge_rotation_for_gap(
        left_world,
        right_world,
        upper_world,
        lower_world,
        40.0,
    )
    jaw_local = world_transform_to_parent_local(world_matrix, parent_to_world)

    closed_world = to_world(lower_native)
    opened_via_chain = (
        parent_to_world @ jaw_local @ np.append(lower_native, 1.0)
    )[:3]
    assert abs(gap - 40.0) < 0.1
    assert np.allclose(opened_via_chain, opened_lower, atol=1e-3)
    assert np.allclose(
        opened_via_chain,
        (world_matrix @ np.append(closed_world, 1.0))[:3],
        atol=1e-3,
    )
    for hinge_world in (left_world, right_world):
        hinge_local = np.linalg.inv(parent_to_world) @ np.append(hinge_world, 1.0)
        hinge_after = (parent_to_world @ jaw_local @ hinge_local)[:3]
        assert np.allclose(hinge_after, hinge_world, atol=1e-3)


def _profile_migration_logic():
    source = (
        HELPER_DIRECTORY / "dentobot_workflow" / "logic_robot.py"
    ).read_text()
    mixin = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "RobotLogicMixin"
    )
    methods = [
        node for node in mixin.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_robotProfileComponentSha256",
            "_migrateLegacyJ2ZeroRobotProfile",
        }
    ]
    helper_calls = []

    def five_dof_upgrade(saved, current):
        helper_calls.append((saved, current))
        return (
            saved.get("fiveDofProfile") is True
            and current.get("upgradesFiveDofProfile") == saved.get("name")
        )

    namespace = {
        "JOINT_NAMES": JOINT_NAMES,
        "LEGACY_J2_RETRACTED_ZERO_URDF_SHA256": "legacy-j2",
        "J2_EXTENDED_J5_CONTINUOUS_URDF_SHA256": "current-j2",
        "J2_TRAVEL_M": 0.08,
        "J2_TRAVEL_MM": 80.0,
        "build_task_home": build_task_home,
        "canonical_json": canonical_json,
        "is_additive_rrt_profile_upgrade": lambda *_args: False,
        "is_five_dof_profile_upgrade": five_dof_upgrade,
        "_": lambda message: message,
        "math": math,
    }
    extracted = ast.Module(
        body=[ast.ClassDef(
            name="ExtractedRobotLogic",
            bases=[],
            keywords=[],
            body=methods,
            decorator_list=[],
        )],
        type_ignores=[],
    )
    exec(
        compile(ast.fix_missing_locations(extracted), "<profile-migration>", "exec"),
        namespace,
    )
    return namespace["ExtractedRobotLogic"], helper_calls


class _MigrationParameterNode(SimpleNamespace):
    def StartModify(self):
        return 0

    def EndModify(self, _was_modifying):
        pass


class _MigrationHost:
    def __init__(self, logic_type, current_profile):
        self.logic = logic_type()
        self.current_profile = current_profile
        self.invalidations = []

    def caseBundleRobotProfile(self):
        return self.current_profile

    def taskHomeRecord(self, parameter_node):
        payload = str(parameter_node.step6TaskHomeJson or "").strip()
        return parse_task_home(payload) if payload else None

    def isRobotBaseTransformNode(self, node):
        return node is not None

    def _robotProfileComponentSha256(self, profile, component_path):
        return self.logic._robotProfileComponentSha256(profile, component_path)

    def invalidateStep6TaskConfirmation(self, parameter_node, reason):
        self.invalidations.append(reason)
        parameter_node.step6ConfirmedTaskJson = ""

    def migrate(self, parameter_node, saved_profile):
        return type(self.logic)._migrateLegacyJ2ZeroRobotProfile(
            self, parameter_node, saved_profile
        )


def _five_dof_profiles():
    saved = {
        "name": "five-dof-v1",
        "fiveDofProfile": True,
        "identitySha256": "saved-profile",
        "components": [],
    }
    current = {
        "identitySha256": "current-profile",
        "upgradesFiveDofProfile": "five-dof-v1",
        "components": [],
    }
    return saved, current


def test_five_dof_profile_upgrade_preserves_home_and_invalidates_dependent_state() -> None:
    logic_type, helper_calls = _profile_migration_logic()
    saved_profile, current_profile = _five_dof_profiles()
    positions = (0.12, 0.025, -0.34, 0.041, 1.2)
    original_home = build_task_home(
        dict(zip(JOINT_NAMES, positions)),
        base_fingerprint="base-pose-v3",
        robot_profile_fingerprint="saved-profile",
        revision=7,
        runtime_validation_status="Validated",
        collision_audit_fingerprint="old-audit",
        guard_policy_fingerprint="old-guard",
        validated_at_utc="2026-09-20T00:00:00Z",
        minimum_clearance_mm=2.0,
        world_object_count=4,
    )

    class Base:
        def __init__(self):
            self.attributes = {"DENTOBOT.RobotProfileFingerprint": "saved-profile"}

        def GetAttribute(self, name):
            return self.attributes.get(name, "")

    base = Base()
    parameter = _MigrationParameterNode(
        step6TaskHomeJson=canonical_json(original_home.to_dict()),
        step6PlanningContextImported=True,
        robotBaseTransform=base,
        robotJoint1Deg=6.0,
        robotJoint2Mm=21.0,
        robotJoint3Deg=-18.0,
        robotJoint4Mm=33.0,
        robotJoint5Deg=54.0,
        step6AssistedLimitProposalJson="old-proposal",
        step6CollisionSceneAuditJson="old-audit",
        step6ConfirmedTaskJson="old-confirmation",
    )
    host = _MigrationHost(logic_type, current_profile)

    result = host.migrate(parameter, saved_profile)

    migrated_home = parse_task_home(parameter.step6TaskHomeJson)
    assert result["compatible"] and result["migrated"]
    assert helper_calls == [(saved_profile, current_profile)]
    assert migrated_home.joint_names == JOINT_NAMES
    assert migrated_home.joint_positions_si == positions
    assert migrated_home.robot_profile_fingerprint == "current-profile"
    assert migrated_home.base_fingerprint == "base-pose-v3"
    assert migrated_home.revision == 8
    assert migrated_home.runtime_validation_status == "Unreviewed"
    assert migrated_home.collision_audit_fingerprint == ""
    assert migrated_home.guard_policy_fingerprint == ""
    assert len(migrated_home.joint_positions_si) == 5
    assert parameter.step6AssistedLimitProposalJson == ""
    assert parameter.step6CollisionSceneAuditJson == ""
    assert parameter.step6ConfirmedTaskJson == ""
    assert host.invalidations
    assert parameter.robotBaseTransform is base
    assert base.GetAttribute("DENTOBOT.RobotProfileFingerprint") == "saved-profile"
    assert (
        parameter.robotJoint1Deg,
        parameter.robotJoint2Mm,
        parameter.robotJoint3Deg,
        parameter.robotJoint4Mm,
        parameter.robotJoint5Deg,
    ) == (6.0, 21.0, -18.0, 33.0, 54.0)
    assert not hasattr(parameter, "robotJoint6Deg")


def test_five_dof_profile_upgrade_without_step6_state_does_not_fabricate_state() -> None:
    logic_type, helper_calls = _profile_migration_logic()
    saved_profile, current_profile = _five_dof_profiles()
    parameter = _MigrationParameterNode(
        step6TaskHomeJson="",
        step6PlanningContextImported=False,
        robotBaseTransform=None,
        step6AssistedLimitProposalJson="",
        step6CollisionSceneAuditJson="",
        step6ConfirmedTaskJson="",
    )
    host = _MigrationHost(logic_type, current_profile)

    result = host.migrate(parameter, saved_profile)

    assert result["compatible"] and not result["migrated"]
    assert helper_calls == [(saved_profile, current_profile)]
    assert parameter.step6TaskHomeJson == ""
    assert parameter.step6AssistedLimitProposalJson == ""
    assert parameter.step6CollisionSceneAuditJson == ""
    assert not host.invalidations


@pytest.mark.parametrize("corruption", ("profile", "extra-j6"))
def test_five_dof_profile_upgrade_rejects_incompatible_saved_home(corruption) -> None:
    logic_type, _helper_calls = _profile_migration_logic()
    saved_profile, current_profile = _five_dof_profiles()
    home = build_task_home(
        dict(zip(JOINT_NAMES, (0.0, 0.01, 0.0, 0.02, 0.0))),
        base_fingerprint="base-pose-v3",
        robot_profile_fingerprint="saved-profile",
        revision=3,
    ).to_dict()
    if corruption == "profile":
        home["robot_profile_fingerprint"] = "different-profile"
    else:
        home["joint_names"] = [*JOINT_NAMES, "link-6_Revolute-6"]
        home["joint_positions_si"] = [*home["joint_positions_si"], 0.0]
    saved_home_json = canonical_json(home)
    parameter = _MigrationParameterNode(
        step6TaskHomeJson=saved_home_json,
        step6PlanningContextImported=True,
        robotBaseTransform=None,
        step6AssistedLimitProposalJson="proposal",
        step6CollisionSceneAuditJson="audit",
        step6ConfirmedTaskJson="confirmed",
    )
    host = _MigrationHost(logic_type, current_profile)

    with pytest.raises(ValueError):
        host.migrate(parameter, saved_profile)

    assert parameter.step6TaskHomeJson == saved_home_json
    assert parameter.step6AssistedLimitProposalJson == "proposal"
    assert parameter.step6CollisionSceneAuditJson == "audit"
    assert parameter.step6ConfirmedTaskJson == "confirmed"
    assert not host.invalidations


def test_unrecognized_profile_transition_remains_incompatible_and_unchanged() -> None:
    logic_type, helper_calls = _profile_migration_logic()
    _saved_profile, current_profile = _five_dof_profiles()
    saved_profile = {
        "identitySha256": "unknown-profile",
        "components": [],
    }
    parameter = _MigrationParameterNode(
        step6TaskHomeJson="",
        step6PlanningContextImported=True,
        robotBaseTransform=object(),
        step6AssistedLimitProposalJson="proposal",
        step6CollisionSceneAuditJson="audit",
        step6ConfirmedTaskJson="confirmed",
    )
    host = _MigrationHost(logic_type, current_profile)

    result = host.migrate(parameter, saved_profile)

    assert not result["compatible"]
    assert helper_calls == [(saved_profile, current_profile)]
    assert parameter.step6AssistedLimitProposalJson == "proposal"
    assert parameter.step6CollisionSceneAuditJson == "audit"
    assert parameter.step6ConfirmedTaskJson == "confirmed"
    assert not host.invalidations


def test_base_lock_publishes_complete_review_evidence_before_parameter_notification():
    from DENTOStep6State import (
        BasePlacementStatus, MANUAL_SIMULATION_BASE_SOURCE, normalize_base_status,
    )

    source = (HELPER_DIRECTORY / "dentobot_workflow/logic_robot.py").read_text()
    robot_class = next(node for node in ast.parse(source).body
                       if isinstance(node, ast.ClassDef) and node.name == "RobotLogicMixin")
    method = next(node for node in robot_class.body
                  if isinstance(node, ast.FunctionDef) and node.name == "setRobotBaseMountLocked")
    namespace = {
        "BasePlacementStatus": BasePlacementStatus,
        "MANUAL_SIMULATION_BASE_SOURCE": MANUAL_SIMULATION_BASE_SOURCE,
        "normalize_base_status": normalize_base_status,
        "_": lambda text: text,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 "<base-lock>", "exec"), namespace)
    attributes = {"authority": "ManualSimulationBaseUnreviewed"}
    base = SimpleNamespace(
        GetAttribute=attributes.get,
        SetAttribute=lambda key, value: attributes.__setitem__(key, value),
    )
    notifications = []
    invalidations = []
    node = SimpleNamespace(
        robotBaseTransform=base,
        robotBaseMountLocked=False,
        step6BasePlacementStatus="Stale",
        step6BasePlacementSource="old-source",
        step6BasePlacementRevision=7,
        StartModify=lambda: 0,
        EndModify=lambda _old: notifications.append((
            node.robotBaseMountLocked, node.step6BasePlacementStatus,
            node.step6BasePlacementSource, dict(attributes), list(invalidations),
        )),
    )
    logic = SimpleNamespace(
        requireCaseFoundationPose=lambda _node: {"planning_pose_fingerprint": "current-pose"},
        isRobotBaseTransformNode=lambda value: value is base,
        ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE="authority",
        ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY="circular",
        ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY="ManualSimulationBaseReviewed",
        ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY="ManualSimulationBaseUnreviewed",
        robotProfileFingerprint=lambda: "current-profile",
        invalidateStep6TaskConfirmation=lambda *_args: invalidations.append("invalidated"),
        _applyRobotBaseMountInteractionState=lambda *_args: None,
    )
    lock = namespace["setRobotBaseMountLocked"]
    lock(logic, node, True)
    assert notifications == [(True, "ProvisionalLocked", MANUAL_SIMULATION_BASE_SOURCE, {
        "authority": "ManualSimulationBaseReviewed",
        "DENTOBOT.CaseFoundationFingerprint": "current-pose",
        "DENTOBOT.RobotProfileFingerprint": "current-profile",
    }, ["invalidated"])]
    assert node.step6BasePlacementRevision == 8
    lock(logic, node, True)
    assert node.step6BasePlacementRevision == 8
    assert invalidations == ["invalidated"]
    lock(logic, node, False)
    assert notifications[-1][0:3] == (False, "Unlocked", "operator-unlocked")
    assert notifications[-1][3]["authority"] == "ManualSimulationBaseUnreviewed"
    assert node.step6BasePlacementRevision == 9


class _BaseIdentityMatrix:
    def __init__(self, values):
        self.values = [[float(values[row][column]) for column in range(4)] for row in range(4)]

    def GetElement(self, row, column):
        return self.values[row][column]


class _BaseIdentityTransform:
    def __init__(self, values):
        self.matrix = _BaseIdentityMatrix(values)
        self.attributes = {}

    def GetAttribute(self, name):
        return self.attributes.get(name)

    def SetAttribute(self, name, value):
        if value is None:
            self.attributes.pop(name, None)
        else:
            self.attributes[name] = str(value)


def _base_identity_host(*method_names):
    """The real RobotLogicMixin base-identity methods (read from logic_robot.py by AST) on a small host."""

    from DENTOStep6State import BasePlacementStatus, MANUAL_SIMULATION_BASE_SOURCE, fingerprint, normalize_base_status

    source = (HELPER_DIRECTORY / "dentobot_workflow/logic_robot.py").read_text()
    robot_class = next(node for node in ast.parse(source).body
                       if isinstance(node, ast.ClassDef) and node.name == "RobotLogicMixin")
    functions = [node for node in robot_class.body if isinstance(node, ast.FunctionDef) and node.name in method_names]
    assert {node.name for node in functions} == set(method_names), "missing production method"
    namespace = {
        "BasePlacementStatus": BasePlacementStatus,
        "MANUAL_SIMULATION_BASE_SOURCE": MANUAL_SIMULATION_BASE_SOURCE,
        "normalize_base_status": normalize_base_status,
        "fingerprint": fingerprint,
        "_": lambda text: text,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 "<base-identity>", "exec"), namespace)
    base = _BaseIdentityTransform(np.eye(4).tolist())
    base.matrix = _BaseIdentityMatrix(np.eye(4).tolist())
    host = type("BaseIdentityHost", (), {})()
    host.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE = "authority"
    host.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY = "circular"
    host.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY = "ManualSimulationBaseReviewed"
    host.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY = "ManualSimulationBaseUnreviewed"
    host.requireCaseFoundationPose = lambda _node: {"planning_pose_fingerprint": "current-pose"}
    host.isRobotBaseTransformNode = lambda value: value is base
    host.robotProfileFingerprint = lambda: "current-profile"
    host.invalidateStep6TaskConfirmation = lambda *_args: None
    host._applyRobotBaseMountInteractionState = lambda *_args: None
    host._worldMatrixFromTransform = lambda value: value.matrix
    for name in method_names:
        setattr(type(host), name, namespace[name])
    node = SimpleNamespace(
        robotBaseTransform=base, robotBaseMountLocked=True, step6BasePlacementStatus="ProvisionalLocked",
        step6BasePlacementSource="ManualSimulationBase", step6BasePlacementRevision=37,
        StartModify=lambda: 0, EndModify=lambda _old: None,
    )
    base.SetAttribute("authority", "ManualSimulationBaseReviewed")
    return host, node, base


def _base_identity_snapshot(host, node, base):
    """The facade's manualBaseIdentitySnapshot fields, as the advisor captures them before a search."""

    return {
        "matrix": [base.matrix.GetElement(r, c) for r in range(4) for c in range(4)],
        "locked": bool(node.robotBaseMountLocked), "status": node.step6BasePlacementStatus,
        "source": node.step6BasePlacementSource, "revision": node.step6BasePlacementRevision,
        "authority": base.GetAttribute("authority"), "case_foundation_fingerprint": "current-pose",
        "robot_profile_fingerprint": "current-profile", "placement_warning": "",
        "base_fingerprint": host.robotBaseFingerprint(node),
    }


_MOVED_POSE = [[1.0, 0.0, 0.0, 5.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def test_user_base_edit_through_the_lock_owners_still_bumps_the_revision_and_changes_the_identity():
    host, node, base = _base_identity_host("setRobotBaseMountLocked", "robotBaseFingerprint",
                                           "robotBasePoseFingerprint")
    captured = _base_identity_snapshot(host, node, base)
    host.setRobotBaseMountLocked(node, False)
    base.matrix = _BaseIdentityMatrix(_MOVED_POSE)
    host.setRobotBaseMountLocked(node, True)
    assert node.step6BasePlacementRevision == 39
    assert host.robotBaseFingerprint(node) != captured["base_fingerprint"]


def test_exact_base_identity_restore_reinstates_the_captured_revision_status_and_fingerprint():
    host, node, base = _base_identity_host("setRobotBaseMountLocked", "robotBaseFingerprint",
                                           "robotBasePoseFingerprint", "restoreStep6BaseIdentity")
    captured = _base_identity_snapshot(host, node, base)
    host.setRobotBaseMountLocked(node, False)  # the advisor trial: unlock, pose change, lock
    base.matrix = _BaseIdentityMatrix(_MOVED_POSE)
    host.setRobotBaseMountLocked(node, True)
    assert node.step6BasePlacementRevision == 39
    base.matrix = _BaseIdentityMatrix(np.eye(4).tolist())  # the owner put the captured pose back while unlocked
    node.robotBaseMountLocked, node.step6BasePlacementStatus = False, "Unlocked"

    host.restoreStep6BaseIdentity(node, captured)

    assert node.step6BasePlacementRevision == 37
    assert host.robotBaseFingerprint(node) == captured["base_fingerprint"]
    assert (node.robotBaseMountLocked, node.step6BasePlacementStatus, node.step6BasePlacementSource) == (
        True, "ProvisionalLocked", "ManualSimulationBase")
    assert base.GetAttribute("authority") == "ManualSimulationBaseReviewed"


def test_exact_base_identity_restore_refuses_an_unlocked_snapshot_or_a_fingerprint_mismatch():
    host, node, base = _base_identity_host("setRobotBaseMountLocked", "robotBaseFingerprint",
                                           "robotBasePoseFingerprint", "restoreStep6BaseIdentity")
    captured = _base_identity_snapshot(host, node, base)
    with pytest.raises(ValueError, match="not locked"):
        host.restoreStep6BaseIdentity(node, {**captured, "locked": False})
    with pytest.raises(ValueError, match="does not match"):
        host.restoreStep6BaseIdentity(node, {**captured, "base_fingerprint": "other"})
