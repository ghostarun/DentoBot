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
    from types import MethodType

    revision_owner = ("issueStep6BasePlacementRevision", "recordStep6BasePlacementRevision",
                      "step6BasePlacementRevisionHighWater")
    exec(compile(ast.fix_missing_locations(ast.Module(body=_base_owner_functions(revision_owner), type_ignores=[])),
                 "<base-lock-revision-owner>", "exec"), namespace)
    for name in revision_owner:  # the high-water owner lives in the Case Foundation mixin
        setattr(logic, name, MethodType(namespace[name], logic))
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


_BASE_OWNER_CLASSES = (
    ("dentobot_workflow/logic_robot.py", "RobotLogicMixin"),
    ("dentobot_workflow/logic_case_foundation.py", "CaseFoundationLogicMixin"),
)


def _base_owner_functions(method_names):
    """Production base-owner methods read by AST from the mixins that DENTOWorkflow composes into the logic class."""

    functions = []
    for relative, class_name in _BASE_OWNER_CLASSES:
        source = (HELPER_DIRECTORY / relative).read_text()
        owner = next(node for node in ast.parse(source).body
                     if isinstance(node, ast.ClassDef) and node.name == class_name)
        functions += [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name in method_names]
    assert {node.name for node in functions} == set(method_names), "missing production method"
    return functions


def _base_owner_namespace():
    from DENTOStep6State import BasePlacementStatus, MANUAL_SIMULATION_BASE_SOURCE, fingerprint, normalize_base_status

    return {
        "BasePlacementStatus": BasePlacementStatus,
        "MANUAL_SIMULATION_BASE_SOURCE": MANUAL_SIMULATION_BASE_SOURCE,
        "normalize_base_status": normalize_base_status,
        "fingerprint": fingerprint,
        "_": lambda text: text,
    }


def _base_identity_host(*method_names):
    """The real base-identity methods (read from the production source by AST) on a small host."""

    functions = _base_owner_functions(method_names)
    namespace = _base_owner_namespace()
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
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
    captured = _base_identity_snapshot(host, node, base)
    host.setRobotBaseMountLocked(node, False)
    base.matrix = _BaseIdentityMatrix(_MOVED_POSE)
    host.setRobotBaseMountLocked(node, True)
    assert node.step6BasePlacementRevision == 39
    assert host.robotBaseFingerprint(node) != captured["base_fingerprint"]


def test_exact_base_identity_restore_reinstates_the_captured_revision_status_and_fingerprint():
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
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
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
    captured = _base_identity_snapshot(host, node, base)
    with pytest.raises(ValueError, match="not locked"):
        host.restoreStep6BaseIdentity(node, {**captured, "locked": False})
    with pytest.raises(ValueError, match="does not match"):
        host.restoreStep6BaseIdentity(node, {**captured, "base_fingerprint": "other"})


_BASE_REVISION_METHODS = (
    "setRobotBaseMountLocked", "robotBaseFingerprint", "robotBasePoseFingerprint", "restoreStep6BaseIdentity",
    "step6BasePlacementRevisionHighWater", "recordStep6BasePlacementRevision", "issueStep6BasePlacementRevision",
    "_baseIdentityCheckpoint", "_baseIdentityDifferences",
)


class _BaseIdentityDisplay:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda value: self.calls.append((name, value))


def _base_identity_host_with_real_notifications(*, reverter=None):
    """Like _base_identity_host, but the production interaction-state method is real and every EndModify delivers
    the parameter notification to ``reverter`` (what an observer that re-derives Base state would do)."""

    functions = _base_owner_functions(_BASE_REVISION_METHODS + ("_applyRobotBaseMountInteractionState",))
    namespace = _base_owner_namespace()
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 "<base-identity-notify>", "exec"), namespace)
    base = _BaseIdentityTransform(np.eye(4).tolist())
    display = _BaseIdentityDisplay()
    base.GetDisplayNode = lambda: display
    host = type("BaseIdentityNotifyHost", (), {})()
    host.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE = "authority"
    host.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY = "circular"
    host.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY = "ManualSimulationBaseReviewed"
    host.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY = "ManualSimulationBaseUnreviewed"
    host.requireCaseFoundationPose = lambda _node: {"planning_pose_fingerprint": "current-pose"}
    host.isRobotBaseTransformNode = lambda value: value is base
    host.isRobotMountPlaneNode = lambda _value: False
    host.robotProfileFingerprint = lambda: "current-profile"
    host.invalidateStep6TaskConfirmation = lambda *_args: None
    host._worldMatrixFromTransform = lambda value: value.matrix
    for name in _BASE_REVISION_METHODS + ("_applyRobotBaseMountInteractionState",):
        setattr(type(host), name, namespace[name])
    node = SimpleNamespace(
        robotBaseTransform=base, robotBaseMountLocked=True, robotMountPlane=None,
        step6BasePlacementStatus="ProvisionalLocked", step6BasePlacementSource="ManualSimulationBase",
        step6BasePlacementRevision=37, notifications=[],
    )

    def end_modify(_old):
        node.notifications.append("parameter-modified")
        if reverter is not None:
            reverter(node, base)

    node.StartModify = lambda: 0
    node.EndModify = end_modify
    base.SetAttribute("authority", "ManualSimulationBaseReviewed")
    return host, node, base, display
_MOVED_POSE_TWO = [[1.0, 0.0, 0.0, 9.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
_IDENTITY_POSE = np.eye(4).tolist()


def _operator_base_edit(host, node, base, matrix):
    """A Base edit through the production owners: unlock (one issue), move, lock (one issue)."""

    host.setRobotBaseMountLocked(node, False)
    base.matrix = _BaseIdentityMatrix(matrix)
    host.setRobotBaseMountLocked(node, True)


def _persisted_attributes(node):
    """What the MRML parameter node keeps for the Base identity: every value stored as text."""

    return {
        "robotBaseMountLocked": str(bool(node.robotBaseMountLocked)),
        "step6BasePlacementStatus": node.step6BasePlacementStatus,
        "step6BasePlacementSource": node.step6BasePlacementSource,
        "step6BasePlacementRevision": str(node.step6BasePlacementRevision),
        "step6BasePlacementHighWater": str(node.step6BasePlacementHighWater),
    }


def _reopened_node(base, attributes):
    return SimpleNamespace(
        robotBaseTransform=base,
        robotBaseMountLocked=attributes["robotBaseMountLocked"] == "True",
        step6BasePlacementStatus=attributes["step6BasePlacementStatus"],
        step6BasePlacementSource=attributes["step6BasePlacementSource"],
        step6BasePlacementRevision=int(attributes["step6BasePlacementRevision"]),
        step6BasePlacementHighWater=int(attributes["step6BasePlacementHighWater"]),
        StartModify=lambda: 0,
        EndModify=lambda _old: None,
    )


def test_trial_then_exact_restore_keeps_the_captured_revision_and_the_next_edit_never_reissues_one():
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
    node.step6BasePlacementHighWater = 37
    captured = _base_identity_snapshot(host, node, base)
    _operator_base_edit(host, node, base, _MOVED_POSE)  # the advisor trial issues 38 and 39
    assert (node.step6BasePlacementRevision, node.step6BasePlacementHighWater) == (39, 39)

    host.setRobotBaseMountLocked(node, False)  # the reinstatement unlocks first: issues 40
    base.matrix = _BaseIdentityMatrix(_IDENTITY_POSE)
    host.restoreStep6BaseIdentity(node, captured)

    assert node.step6BasePlacementRevision == 37
    assert host.robotBaseFingerprint(node) == captured["base_fingerprint"]  # Task Home is fresh again
    assert node.step6BasePlacementHighWater == 40  # the restore never lowers the mark

    _operator_base_edit(host, node, base, _MOVED_POSE_TWO)  # the next real user edit
    assert node.step6BasePlacementRevision == 42  # above every issued number, not 38
    assert node.step6BasePlacementHighWater == 42
    assert host.robotBaseFingerprint(node) != captured["base_fingerprint"]  # Task Home is stale


def test_high_water_mark_survives_save_and_reopen_like_the_revision():
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
    node.step6BasePlacementHighWater = 37
    captured = _base_identity_snapshot(host, node, base)
    _operator_base_edit(host, node, base, _MOVED_POSE)
    host.setRobotBaseMountLocked(node, False)
    base.matrix = _BaseIdentityMatrix(_IDENTITY_POSE)
    host.restoreStep6BaseIdentity(node, captured)
    saved = _persisted_attributes(node)
    assert saved["step6BasePlacementRevision"] == "37" and saved["step6BasePlacementHighWater"] == "40"

    reopened = _reopened_node(base, saved)
    assert host.robotBaseFingerprint(reopened) == captured["base_fingerprint"]
    _operator_base_edit(host, reopened, base, _MOVED_POSE_TWO)
    assert reopened.step6BasePlacementRevision == 42  # the mark came back with the scene, so no reuse after reopen


def test_absent_high_water_mark_in_an_older_case_defaults_to_the_current_revision():
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
    assert not hasattr(node, "step6BasePlacementHighWater")  # a case saved before the field existed
    node.step6BasePlacementRevision = 7
    assert host.step6BasePlacementRevisionHighWater(node) == 7
    _operator_base_edit(host, node, base, _MOVED_POSE)
    assert (node.step6BasePlacementRevision, node.step6BasePlacementHighWater) == (9, 9)


def test_user_edits_without_the_advisor_issue_the_same_consecutive_revisions_as_before():
    host, node, base = _base_identity_host(*_BASE_REVISION_METHODS)
    revisions = []
    for offset in (1.0, 2.0, 3.0):
        matrix = [[1.0, 0.0, 0.0, offset], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        _operator_base_edit(host, node, base, matrix)
        revisions.append(node.step6BasePlacementRevision)
    assert revisions == [39, 41, 43]  # unlock and lock each issue one; nothing skipped or repeated


def test_every_base_revision_write_in_production_goes_through_the_high_water_owner():
    offenders = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self, path):
            self.path, self.stack = path, []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Assign(self, node):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "step6BasePlacementRevision":
                    if not self.stack or self.stack[-1] != "recordStep6BasePlacementRevision":
                        offenders.append(f"{self.path.name}:{node.lineno}")
            self.generic_visit(node)

    sources = [path for path in HELPER_DIRECTORY.rglob("*.py") if "archive" not in path.parts]
    for path in sources:
        _Visitor(path).visit(ast.parse(path.read_text(encoding="utf-8")))
    assert offenders == []


def test_exact_restore_with_the_real_interaction_state_and_notifications_reproduces_the_captured_fingerprint():
    host, node, base, display = _base_identity_host_with_real_notifications()
    captured = _base_identity_snapshot(host, node, base)
    host.setRobotBaseMountLocked(node, False)
    base.matrix = _BaseIdentityMatrix(_MOVED_POSE)
    host.setRobotBaseMountLocked(node, True)
    base.matrix = _BaseIdentityMatrix(np.eye(4).tolist())
    node.robotBaseMountLocked, node.step6BasePlacementStatus = False, "Unlocked"

    host.restoreStep6BaseIdentity(node, captured)

    assert host.robotBaseFingerprint(node) == captured["base_fingerprint"]
    assert base.GetAttribute("DENTOBOT.RobotBaseMountLocked") == "true"  # the real interaction state ran
    assert ("SetEditorVisibility", False) in display.calls


def test_a_later_revert_of_status_and_revision_is_refused_with_the_named_fields_and_the_divergence_point():
    def revert_to_trial_end(node, _base):
        # What a parameter-notified re-derivation would leave behind: the Base is stale and at the trial's revision.
        node.robotBaseMountLocked = False
        node.step6BasePlacementStatus = "Stale"
        node.step6BasePlacementRevision = 42

    host, node, base, _display = _base_identity_host_with_real_notifications()
    captured = _base_identity_snapshot(host, node, base)
    host.setRobotBaseMountLocked(node, False)
    base.matrix = _BaseIdentityMatrix(_MOVED_POSE)
    host.setRobotBaseMountLocked(node, True)
    base.matrix = _BaseIdentityMatrix(np.eye(4).tolist())
    node.robotBaseMountLocked, node.step6BasePlacementStatus = False, "Unlocked"
    node.EndModify = lambda _old: (node.notifications.append("parameter-modified"), revert_to_trial_end(node, base))

    with pytest.raises(ValueError, match="does not match") as raised:
        host.restoreStep6BaseIdentity(node, captured)

    message = str(raised.value)
    assert "status Stale != captured ProvisionalLocked" in message
    assert "sourceRevision 42 != captured 37" in message
    trace = raised.value.base_identity_trace
    assert [step["label"] for step in trace] == [
        "before-restore-writes", "after-lock-block", "after-attribute-writes",
        "after-interaction-state", "at-fingerprint-check"]
    assert trace[1]["status"] == "Stale" and trace[1]["revision"] == 42  # the revert happened inside the lock block


# S6-ADVISOR-GUI-01 live R05: an exact restore is an acceptance-owned Base change. The real reinstate method and the real
# Base observer are extracted by AST; the transform fires ModifiedEvent on attribute writes (as MRML does) but not on the
# matrix write (TransformModifiedEvent only), so the observer's pose cache is the trial pose until an accepted write refreshes it.
class _RobotActionResultStub:
    def __init__(self, success, code, message, details=None, payload=None):
        self.success, self.code, self.message = success, code, message
        self.details, self.payload = dict(details or {}), payload


class _GuardBaseTransform(_BaseIdentityTransform):
    def __init__(self, values):
        super().__init__(values)
        self.observers = []
        self.display = _BaseIdentityDisplay()

    def GetDisplayNode(self):
        return self.display

    def SetAndObserveTransformNodeID(self, _node_id):
        pass

    def SetMatrixTransformToParent(self, matrix):  # MRML fires TransformModifiedEvent here, not ModifiedEvent
        self.matrix = matrix

    def SetAttribute(self, name, value):
        new = None if value is None else str(value)
        old = self.attributes.get(name)
        if new is None:
            self.attributes.pop(name, None)
        else:
            self.attributes[name] = new
        if old != new:
            self.Modified()

    def Modified(self):
        for observer in list(self.observers):
            observer(caller=self, event="ModifiedEvent")


class _DropAcceptanceFlagWrites(ast.NodeTransformer):
    def visit_Assign(self, node):
        if any(isinstance(t, ast.Attribute) and t.attr == "_manual_base_acceptance_in_progress" for t in node.targets):
            return ast.copy_location(ast.Pass(), node)
        return node


def _extract_methods(path, class_name, names, *, drop_flag_writes=False):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    found = []
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            node.decorator_list = []
            if drop_flag_writes:
                node = ast.fix_missing_locations(_DropAcceptanceFlagWrites().visit(node))
            found.append(node)
    assert {node.name for node in found} == set(names), set(names) - {node.name for node in found}
    return found


def _guard_host(*, guarded: bool):
    """The real logic, facade and widget-observer methods on a small host. Closest unit: the facade's unlockBase and
    setBasePose are the owners' essential effects (lock owner; matrix and authority writes), not the full production owners."""
    import logging
    import math
    import time
    from DENTOStep6State import MANUAL_SIMULATION_BASE_SOURCE, fingerprint, normalize_base_status, BasePlacementStatus

    base = _GuardBaseTransform(np.eye(4).tolist())
    base.SetAttribute("authority", "ManualSimulationBaseReviewed")
    node = SimpleNamespace(
        robotBaseTransform=base, robotBaseMountLocked=True, robotMountPlane=None,
        step6BasePlacementStatus="ProvisionalLocked", step6BasePlacementSource=MANUAL_SIMULATION_BASE_SOURCE,
        step6BasePlacementRevision=37, step6BasePlacementHighWater=37, step6ConfirmedTaskJson='{"confirmed": true}',
        StartModify=lambda: 0, EndModify=lambda _old: None,
    )
    logic_names = _BASE_REVISION_METHODS + ("invalidateStep6TaskConfirmation", "_applyRobotBaseMountInteractionState")
    logic_ns = {**_base_owner_namespace(), "logging": logging}
    exec(compile(ast.fix_missing_locations(ast.Module(body=_base_owner_functions(logic_names), type_ignores=[])),
                 "<guard-logic>", "exec"), logic_ns)
    logic = type("GuardLogic", (), {})()
    for name in logic_names:
        setattr(type(logic), name, logic_ns[name])
    logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE = "authority"
    logic.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY = "circular"
    logic.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY = "ManualSimulationBaseReviewed"
    logic.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY = "ManualSimulationBaseUnreviewed"
    logic.isRobotBaseTransformNode = lambda value: value is base
    logic.isRobotMountPlaneNode = lambda _value: False
    logic.requireCaseFoundationPose = lambda _node: {"planning_pose_fingerprint": "current-pose"}
    logic.robotProfileFingerprint = lambda: "current-profile"
    logic.markStep6MotionDiagnosticStale = lambda *_args: None
    logic.robotWorkspaceModelNode = lambda: None
    logic._worldMatrixFromTransform = lambda value: value.matrix
    logic._vtkFromNumpyMatrix = lambda rows: _BaseIdentityMatrix(rows)
    logic.syncStep6MoveItPlanningScene = lambda _node: 34
    logic.collisionSceneAuditRecord = lambda _node: logic.audit_record
    logic.audit_record = SimpleNamespace(status="Acknowledged", audit_fingerprint="audit-1")
    logic.isRos2MotionControlActive = lambda _node: True
    logic.taskHomeRecord = lambda _node: None

    from collections.abc import Mapping
    from typing import Any, Optional
    fac_ns = {**_base_owner_namespace(), "Mapping": Mapping, "Any": Any, "Optional": Optional, "RobotActionResult": _RobotActionResultStub,
              "isfinite": math.isfinite, "monotonic_ns": time.monotonic_ns, "_bounded_text": lambda value: str(value)[:300]}
    facade_methods = _extract_methods(HELPER_DIRECTORY / "DENTORobotWorkflowFacade.py", "DENTORobotWorkflowFacade",
                                      ("reinstateManualBaseIdentity", "_manual_simulation_base_matrix",
                                       "manualBaseAcceptanceInProgress"), drop_flag_writes=not guarded)
    exec(compile(ast.fix_missing_locations(ast.Module(body=facade_methods, type_ignores=[])), "<guard-facade>", "exec"), fac_ns)
    facade = type("GuardFacade", (), {})()
    facade.reinstateManualBaseIdentity = lambda snapshot: fac_ns["reinstateManualBaseIdentity"](facade, snapshot)
    facade._manual_simulation_base_matrix = lambda parameter_node: fac_ns["_manual_simulation_base_matrix"](facade, parameter_node)
    type(facade).manualBaseAcceptanceInProgress = property(fac_ns["manualBaseAcceptanceInProgress"])
    facade._logic = logic
    facade._manual_base_acceptance_uncertain = ""
    facade._incomplete_preview_evidence = None
    facade._guarded_preview_active = False
    facade.previewActive = False
    facade._manual_base_acceptance_in_progress = False
    facade._planning_scene_synchronized = False
    facade._planning_scene_object_count = 0
    facade._runtime_validated_task_home_key = ""
    facade._require_context = lambda: node
    facade._scene_kind = lambda _node: "case"
    facade._clear_phase_session = lambda: None
    facade._task_home_runtime_key = lambda _record: ""
    facade._incomplete_preview_block = lambda code, message: _RobotActionResultStub(False, code, message)
    facade._manual_simulation_finish_acceptance = lambda result, **_kwargs: result
    facade.clearTransientState = lambda: None

    def set_base_pose(matrix_object):  # the facade's pose owner: locked refusal, matrix write, authority reset
        if node.robotBaseMountLocked:
            return _RobotActionResultStub(False, "base_locked", "Unlock the robot base before moving it.")
        base.SetMatrixTransformToParent(matrix_object)
        base.SetAttribute("authority", "ManualSimulationBaseUnreviewed")
        base.SetAttribute("DENTOBOT.PlacementWarning", None)
        return _RobotActionResultStub(True, "base_pose_updated", "")

    facade.setBasePose = set_base_pose
    facade.unlockBase = lambda: (logic.setRobotBaseMountLocked(node, False), _RobotActionResultStub(True, "base_unlocked", ""))[1]

    widget_fn = _extract_methods(HELPER_DIRECTORY / "dentobot_workflow" / "widget_robot_placement.py",
                                 "RobotPlacementWidgetMixin", ("_onRobotPlacementNodeModified",))[0]
    widget_ns = {"_": lambda text: text}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[widget_fn], type_ignores=[])), "<guard-observer>", "exec"), widget_ns)
    widget = type("GuardWidget", (), {})()
    type(widget)._onRobotPlacementNodeModified = widget_ns["_onRobotPlacementNodeModified"]
    widget._updatingRobotPlacementUI = False
    widget.logic = logic
    widget._parameterNode = node
    widget._robotWorkflowFacade = facade
    widget._lastRobotBasePoseFingerprint = logic.robotBasePoseFingerprint(base)
    widget._step6MotionPlan = None
    widget._updateRobotPlacementStatus = lambda *_args, **_kwargs: None
    widget.ui = SimpleNamespace(robotWorkspaceStatusLabel=SimpleNamespace(text="", styleSheet=""))
    base.observers.append(widget._onRobotPlacementNodeModified)
    return SimpleNamespace(base=base, node=node, logic=logic, facade=facade, widget=widget, fingerprint=fingerprint)


def _guard_snapshot(host):
    """The advisor's captured Base identity at search start (locked, ProvisionalLocked, revision 37, pose P0)."""
    base, node = host.base, host.node
    return {
        "matrix": [base.matrix.GetElement(r, c) for r in range(4) for c in range(4)],
        "locked": True, "status": "ProvisionalLocked", "source": node.step6BasePlacementSource,
        "revision": 37, "authority": "ManualSimulationBaseReviewed",
        "case_foundation_fingerprint": "current-pose", "robot_profile_fingerprint": "current-profile",
        "placement_warning": "", "base_fingerprint": host.logic.robotBaseFingerprint(node),
        "collision_audit_json": "{}", "collision_audit_fingerprint": "audit-1",
        "task_home_key": "", "runtime_task_home_key": "",
    }


def _trial_then_failed_candidate(host):
    """The advisor trial as it runs live: unlock (38), accept under the acceptance flag (pose 39), then the candidate fails
    and the restore starts from the unlocked trial-end state (the live trace reads revision 40 at this point)."""
    host.facade.unlockBase()
    host.facade._manual_base_acceptance_in_progress = True
    try:
        host.facade.setBasePose(host.logic._vtkFromNumpyMatrix(_MOVED_POSE))
        host.logic.setRobotBaseMountLocked(host.node, True)
    finally:
        host.facade._manual_base_acceptance_in_progress = False
    assert host.node.step6BasePlacementRevision == 39 and host.widget._lastRobotBasePoseFingerprint == host.logic.robotBasePoseFingerprint(host.base)


def test_without_the_acceptance_guard_the_restore_is_treated_as_an_operator_edit_and_stales_the_base():
    host = _guard_host(guarded=False)
    snapshot = _guard_snapshot(host)
    _trial_then_failed_candidate(host)

    result = host.facade.reinstateManualBaseIdentity(snapshot)

    assert not result.success and result.code == "base_identity_reinstate_failed"
    assert "Differs: status Stale != captured ProvisionalLocked" in result.message
    assert host.node.step6BasePlacementStatus == "Stale" and host.node.robotBaseMountLocked is False
    assert host.node.step6BasePlacementRevision == 42  # the live R05 value: the observer's bumps above the high-water mark


def test_the_acceptance_owned_restore_keeps_revision_status_and_the_captured_fingerprint():
    host = _guard_host(guarded=True)
    snapshot = _guard_snapshot(host)
    _trial_then_failed_candidate(host)

    result = host.facade.reinstateManualBaseIdentity(snapshot)

    assert result.success and result.code == "base_identity_reinstated", result.message
    assert host.node.step6BasePlacementRevision == 37
    assert host.node.step6BasePlacementStatus == "ProvisionalLocked" and host.node.robotBaseMountLocked is True
    assert host.logic.robotBaseFingerprint(host.node) == snapshot["base_fingerprint"]
    assert host.widget._lastRobotBasePoseFingerprint == host.logic.robotBasePoseFingerprint(host.base)  # cache at the restored pose
    assert host.facade._manual_base_acceptance_in_progress is False  # the flag is released on every exit


def test_a_user_pose_edit_after_the_acceptance_owned_restore_still_stales_and_bumps_past_the_high_water_mark():
    host = _guard_host(guarded=True)
    snapshot = _guard_snapshot(host)
    _trial_then_failed_candidate(host)
    assert host.facade.reinstateManualBaseIdentity(snapshot).success
    high_water_before = host.logic.step6BasePlacementRevisionHighWater(host.node)

    host.base.matrix = _BaseIdentityMatrix(_MOVED_POSE_TWO)  # a real user drag: the transform changes and fires ModifiedEvent
    host.base.Modified()

    assert host.node.step6BasePlacementStatus == "Stale" and host.node.robotBaseMountLocked is False
    # The observer's own re-entrant SetAttribute writes issue more than one revision for one user edit (observed +3 in
    # this host); that is existing observer behaviour and is not changed here. No number is reissued.
    assert host.node.step6BasePlacementRevision > high_water_before
    assert host.node.step6BasePlacementRevision == host.logic.step6BasePlacementRevisionHighWater(host.node)  # highest issued
