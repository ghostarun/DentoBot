"""Ordinary-Python tests for the portable DENTOBOT case-bundle contract."""

import ast
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import (  # noqa: E402
    CASE_BUNDLE_SCHEMA_VERSION,
    CASE_BUNDLE_EXTENSION,
    CaseBundleError,
    ROBOT_PROFILE_MEMBER,
    SCENE_MEMBER,
    STUDY_ATTEMPTS_MEMBER,
    STUDY_INDEX_MEMBER,
    audit_mrb_runtime_separation,
    build_robot_profile,
    create_case_bundle,
    extract_scene_mrb,
    is_additive_rrt_profile_upgrade,
    is_five_dof_profile_upgrade,
    lineage_snapshot_matches,
    lineage_snapshot_mismatch_path,
    validate_case_bundle,
)


def _saved_landmark_restore_helper():
    source_path = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_restore_saved_case_foundation_landmarks"
    )
    namespace = {"math": math, "CaseBundleError": CaseBundleError}
    exec(
        compile(ast.Module([helper], type_ignores=[]), str(source_path), "exec"),
        namespace,
    )
    return namespace[helper.name]


def _canonical_case_foundation_landmark_positions_helper():
    source_path = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_foundation.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_canonical_case_foundation_landmark_positions"
    )
    namespace = {"json": json, "math": math}
    exec(
        compile(ast.Module([helper], type_ignores=[]), str(source_path), "exec"),
        namespace,
    )
    return namespace[helper.name]


class FakeLandmarks:
    def __init__(self, points):
        self.points = [list(point) for point in points]
        self.writes = 0

    def GetNumberOfDefinedControlPoints(self):
        return len(self.points)

    def GetNthControlPointPositionWorld(self, index, result):
        result[:] = self.points[index]

    def SetNthControlPointPositionWorld(self, index, *point):
        self.points[index] = list(point)
        self.writes += 1


def write_mrb(path: Path, mrml: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Case/scene.mrml", mrml)


def test_case_foundation_landmark_positions_recovers_tiny_world_roundoff() -> None:
    canonicalize = _canonical_case_foundation_landmark_positions_helper()
    current = [float(index) for index in range(12)]
    current[0] = 1.2345678901
    saved = list(current)
    saved[0] = 1.2345678904
    environment = {
        "landmark_positions_ras_mm": saved,
        "jaw_landmarks_fingerprint": "jaw-current",
        "planning_pose_fingerprint": "pose-committed",
    }

    result = canonicalize(
        tuple(current), json.dumps(environment), "jaw-current", "pose-committed"
    )

    assert result == tuple(saved)


def test_case_foundation_landmark_positions_fail_closed() -> None:
    canonicalize = _canonical_case_foundation_landmark_positions_helper()
    current = [float(index) for index in range(12)]
    current[0] = 1.2345678904
    saved = list(current)

    def environment_json(
        positions,
        jaw_fingerprint="jaw-current",
        pose_fingerprint="pose-committed",
    ):
        return json.dumps(
            {
                "landmark_positions_ras_mm": positions,
                "jaw_landmarks_fingerprint": jaw_fingerprint,
                "planning_pose_fingerprint": pose_fingerprint,
            }
        )

    drifted = list(saved)
    drifted[0] += 2e-9
    rounded_mismatch = list(saved)
    rounded_mismatch[0] = 1.2345678906
    wrong_length = saved[:-1]
    nonfinite = list(saved)
    nonfinite[0] = float("nan")
    cases = (
        ("material landmark drift", environment_json(drifted)),
        ("rounded-coordinate mismatch", environment_json(rounded_mismatch)),
        ("landmark fingerprint mismatch", environment_json(saved, "jaw-stale")),
        (
            "pose fingerprint mismatch",
            environment_json(saved, pose_fingerprint="pose-stale"),
        ),
        ("malformed JSON", "{"),
        ("wrong coordinate count", environment_json(wrong_length)),
        ("nonfinite saved coordinate", environment_json(nonfinite)),
    )

    for reason, saved_environment_json in cases:
        assert canonicalize(
            tuple(current), saved_environment_json, "jaw-current", "pose-committed"
        ) == tuple(current), reason


def test_case_foundation_landmark_restore_recovers_only_mrml_roundoff() -> None:
    restore = _saved_landmark_restore_helper()
    saved = [54.95761498266071, 1.0, 2.0] + [float(i) for i in range(9)]
    restored_from = list(saved)
    restored_from[0] = 54.95761498266072
    node = FakeLandmarks(
        [restored_from[index:index + 3] for index in range(0, 12, 3)]
    )

    assert restore(node, saved)
    assert node.writes == 4
    assert [value for point in node.points for value in point] == saved


@pytest.mark.parametrize(
    "saved,points",
    [
        ([1.0] * 11, [[1.0, 1.0, 1.0]] * 4),
        ([float("nan")] + [1.0] * 11, [[1.0, 1.0, 1.0]] * 4),
        ([1.0] * 12, [[1.0, 1.0, 1.0]] * 3),
        ([1.0] * 12, [[1.0000011, 1.0, 1.0]] + [[1.0, 1.0, 1.0]] * 3),
        (
            [1.0000000004, 1.0, 1.0] + [1.0] * 9,
            [[1.0000000006, 1.0, 1.0]] + [[1.0, 1.0, 1.0]] * 3,
        ),
    ],
)
def test_case_foundation_landmark_restore_fails_closed(saved, points) -> None:
    restore = _saved_landmark_restore_helper()
    node = FakeLandmarks(points)
    original = [point[:] for point in node.points]

    with pytest.raises(CaseBundleError):
        restore(node, saved)

    assert node.points == original
    assert node.writes == 0


def robot_profile_fixture(tmp_path: Path) -> dict:
    description = tmp_path / "description"
    (description / "urdf").mkdir(parents=True)
    (description / "meshes").mkdir()
    (description / "urdf" / "dentobot.urdf").write_text(
        '<robot name="dentobot"/>', encoding="utf-8"
    )
    (description / "meshes" / "link-1.stl").write_text(
        "solid link\nendsolid link\n", encoding="utf-8"
    )
    return build_robot_profile(description)


def test_case_bundle_round_trip_and_integrity(tmp_path: Path) -> None:
    scene = tmp_path / "source.mrb"
    write_mrb(scene, '<MRML version="Slicer4"><Model id="vtkMRMLModelNode1"/></MRML>')
    profile = robot_profile_fixture(tmp_path)
    destination = tmp_path / "case-one"
    inspection = create_case_bundle(
        destination,
        scene,
        case_label="DeidentifiedCase",
        workflow={
            "schemaVersion": "1.0",
            "coordinateSystem": "SlicerRASmm",
            "nodes": [],
        },
        robot_profile=profile,
        application={"module": "DENTOWorkflow"},
        created_at_utc="2026-08-24T00:00:00+00:00",
    )
    assert inspection.path.suffix == CASE_BUNDLE_EXTENSION
    assert inspection.manifest["schemaVersion"] == CASE_BUNDLE_SCHEMA_VERSION
    assert inspection.manifest["runtime"]["ros2Serialized"] is False
    assert inspection.study_index["attemptCount"] == 0
    assert inspection.study_attempts == ()
    assert inspection.robot_profile["identitySha256"] == profile["identitySha256"]

    extracted, validated = extract_scene_mrb(
        inspection.path, tmp_path / "extracted"
    )
    assert extracted.read_bytes() == scene.read_bytes()
    assert validated.scene_sha256 == inspection.scene_sha256
    with zipfile.ZipFile(inspection.path) as archive:
        assert SCENE_MEMBER in archive.namelist()
        assert ROBOT_PROFILE_MEMBER in archive.namelist()
        assert STUDY_INDEX_MEMBER in archive.namelist()
        assert STUDY_ATTEMPTS_MEMBER in archive.namelist()


def test_schema_one_remains_readable_and_migrates_only_on_later_save(tmp_path: Path) -> None:
    scene = tmp_path / "source.mrb"
    write_mrb(scene, "<MRML/>")
    profile = robot_profile_fixture(tmp_path)
    legacy = create_case_bundle(
        tmp_path / "legacy.dentocase",
        scene,
        case_label="LegacyCase",
        workflow={"schemaVersion": "1.0"},
        robot_profile=profile,
        schema_version="1.0",
        created_at_utc="2026-09-09T00:00:00+00:00",
    )
    assert validate_case_bundle(legacy.path).manifest["schemaVersion"] == "1.0"
    with zipfile.ZipFile(legacy.path) as archive:
        assert STUDY_INDEX_MEMBER not in archive.namelist()
        assert STUDY_ATTEMPTS_MEMBER not in archive.namelist()

    migrated = create_case_bundle(
        tmp_path / "migrated.dentocase",
        scene,
        case_label="LegacyCase",
        workflow={"schemaVersion": "2.0"},
        robot_profile=profile,
        created_at_utc="2026-09-09T00:00:00+00:00",
    )
    assert migrated.manifest["schemaVersion"] == "2.0"
    assert migrated.study_index["attemptCount"] == 0


def test_case_bundle_rejects_serialized_ros_runtime(tmp_path: Path) -> None:
    scene = tmp_path / "unsafe.mrb"
    write_mrb(
        scene,
        '<MRML><ROS2 id="vtkMRMLROS2Node1" class="vtkMRMLROS2Node"/></MRML>',
    )
    with pytest.raises(CaseBundleError, match="live ROS/SlicerROS2"):
        audit_mrb_runtime_separation(scene)


def test_case_bundle_detects_duplicate_or_changed_payload(tmp_path: Path) -> None:
    scene = tmp_path / "source.mrb"
    write_mrb(scene, "<MRML/>")
    bundle = create_case_bundle(
        tmp_path / "case.dentocase",
        scene,
        case_label="",
        workflow={"schemaVersion": "1.0"},
        robot_profile=robot_profile_fixture(tmp_path),
    ).path
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(bundle, "a") as archive:
            archive.writestr(SCENE_MEMBER, b"changed")
    with pytest.raises(CaseBundleError, match="duplicate archive members"):
        validate_case_bundle(bundle)


def test_case_bundle_rejects_unexpected_archive_member(tmp_path: Path) -> None:
    scene = tmp_path / "source.mrb"
    write_mrb(scene, "<MRML/>")
    bundle = create_case_bundle(
        tmp_path / "case.dentocase",
        scene,
        case_label="",
        workflow={"schemaVersion": "1.0"},
        robot_profile=robot_profile_fixture(tmp_path),
    ).path
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("unexpected/payload.bin", b"not part of schema V1")
    with pytest.raises(CaseBundleError, match="unsupported archive members"):
        validate_case_bundle(bundle)


def test_robot_profile_is_portable_and_deterministic(tmp_path: Path) -> None:
    profile = robot_profile_fixture(tmp_path)
    repeated = build_robot_profile(tmp_path / "description")
    assert profile == repeated
    assert profile["components"]
    assert all(not record["path"].startswith("/") for record in profile["components"])
    assert str(tmp_path) not in str(profile)


def test_only_known_additive_rrt_profile_upgrade_is_compatible() -> None:
    def profile(components):
        payload = json.dumps(
            components, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n"
        return {
            "schemaVersion": "1.0",
            "runtimeRestorePolicy": "verify-installed-resources-then-explicitly-connect",
            "identitySha256": hashlib.sha256(payload.encode()).hexdigest(),
            "components": components,
        }

    urdf = {"path": "description/urdf/dentobot.urdf", "sha256": "a" * 64, "sizeBytes": 12}
    old_ompl = {
        "path": "moveit/config/ompl_planning.yaml",
        "sha256": "10f6f69a2f40f047b64430d1f408ecec0350ee29cafc27a9758d07821b16c355",
        "sizeBytes": 748,
    }
    rrt_ompl = {
        **old_ompl,
        "sha256": "da568f2f092e61e9cca2a93d448aa1b4e5b4e143d187248767d240081e106011",
        "sizeBytes": 833,
    }
    new_ompl = {
        **old_ompl,
        "sha256": "9acb46e12a30dcf198d2fe415f10446b8f340fe57b9051de7a9ad91cbab5e7b3",
        "sizeBytes": 930,
    }
    saved = profile([urdf, old_ompl])
    current = profile([urdf, new_ompl])
    assert is_additive_rrt_profile_upgrade(saved, current)
    assert is_additive_rrt_profile_upgrade(profile([urdf, rrt_ompl]), current)
    assert not is_additive_rrt_profile_upgrade(
        saved, profile([{**urdf, "sha256": "b" * 64}, new_ompl])
    )
    assert not is_additive_rrt_profile_upgrade(
        saved, profile([urdf, {**new_ompl, "sha256": "c" * 64}])
    )
    assert not is_additive_rrt_profile_upgrade(saved, {**current, "identitySha256": "forged"})


def test_only_known_five_dof_profile_upgrade_is_compatible() -> None:
    saved_identity = "e73acf9bb6ca29a30707a99ad104235376ef0a579bf0bf71ac117608bb2fe682"
    current_identity = (
        "cac087c6ee96258416e587e43303a0351f331a8b668daf4ff0f3929a030ae52c"
    )

    def profile(identity, components):
        return {
            "schemaVersion": "1.0",
            "runtimeRestorePolicy": "verify-installed-resources-then-explicitly-connect",
            "identitySha256": identity,
            "components": components,
        }

    old_canonical = {
        "path": "description/urdf/dentobot.urdf",
        "sha256": "c70c12e38dc12dd4798f6332426eea82a430dc882836ef31cf0ce293c1e3f3d5",
        "sizeBytes": 100,
    }
    new_canonical = {
        **old_canonical,
        "sha256": "3638f919e5a853b1c72d851f8bf61d4aaff8942aaa767c476face0108daedf8a",
        "sizeBytes": 101,
    }
    old_diagnostic = {
        "path": "description/urdf/dentobot.diagnostic-no-spindle-collision.urdf",
        "sha256": "8345886de7ecbe359df010da37a5099d209edae41dc9fc9857a4dccbe61ace99",
        "sizeBytes": 90,
    }
    new_diagnostic = {
        **old_diagnostic,
        "sha256": "980192c3d4239876ad31948671117acc368816317a814d9433db4c101f0b6995",
        "sizeBytes": 91,
    }
    mesh = {"path": "description/meshes/link.stl", "sha256": "a" * 64, "sizeBytes": 12}
    saved_components = [old_canonical, old_diagnostic, mesh]
    current_components = [new_canonical, new_diagnostic, mesh]
    saved = profile(saved_identity, saved_components)
    current = profile(current_identity, current_components)

    assert is_five_dof_profile_upgrade(saved, current)
    assert not is_five_dof_profile_upgrade(
        saved, profile(current_identity, current_components[:-1])
    )
    assert not is_five_dof_profile_upgrade(
        saved,
        profile(
            current_identity,
            current_components + [{"path": "extra", "sha256": "b" * 64, "sizeBytes": 1}],
        ),
    )
    mutated = [{**item} for item in current_components]
    mutated[2]["sha256"] = "b" * 64
    assert not is_five_dof_profile_upgrade(saved, profile(current_identity, mutated))
    wrong_urdf = [{**item} for item in current_components]
    wrong_urdf[0]["sha256"] = "c" * 64
    assert not is_five_dof_profile_upgrade(saved, profile(current_identity, wrong_urdf))
    assert not is_five_dof_profile_upgrade(
        saved, profile(saved_identity, current_components)
    )


def test_lineage_snapshot_accepts_append_only_schema_v1_extensions() -> None:
    saved = {
        "field": "targetToothBoundsRoi",
        "attributes": {"DENTOBOT.CoordinateSystem": "SlicerRASmm"},
        "controlPointsWorldRasMm": [
            [-72.97225952148438, -66.10609436035156, 61.54914855957031]
        ],
        "locked": True,
    }
    reconstructed = {
        **saved,
        "id": "vtkMRMLMarkupsROINode9",
        "attributes": {
            **saved["attributes"],
            "DENTOBOT.TargetSegmentID": "target-14",
            "DENTOBOT.TargetFdiNumber": "14",
        },
    }

    assert lineage_snapshot_matches(saved, reconstructed)


def test_lineage_snapshot_rejects_missing_or_changed_saved_values() -> None:
    saved = {
        "attributes": {
            "DENTOBOT.CoordinateSystem": "SlicerRASmm",
            "DENTOBOT.TargetSegmentID": "target-14",
        },
        "controlPointsWorldRasMm": [[1.0, 2.0, 3.0]],
    }
    missing = {
        "attributes": {"DENTOBOT.CoordinateSystem": "SlicerRASmm"},
        "controlPointsWorldRasMm": [[1.0, 2.0, 3.0]],
    }
    changed = {
        **saved,
        "controlPointsWorldRasMm": [[1.0, 2.0, 3.001]],
    }

    assert not lineage_snapshot_matches(saved, missing)
    assert (
        lineage_snapshot_mismatch_path(saved, missing)
        == "attributes.DENTOBOT.TargetSegmentID"
    )
    assert not lineage_snapshot_matches(saved, changed)
    assert (
        lineage_snapshot_mismatch_path(saved, changed)
        == "controlPointsWorldRasMm[0][2]"
    )


def test_case_bundle_ui_and_install_contract_are_present() -> None:
    ui = ET.parse(ROOT / "DENTOWorkflow/Resources/UI/DENTOWorkflow.ui")
    assert ui.find(".//widget[@name='saveCaseBundleButton']") is not None
    assert ui.find(".//widget[@name='openCaseBundleButton']") is not None
    assert ui.find(".//widget[@name='step6RegistryTrajectorySelector']") is not None
    trajectory_selector = ui.find(".//widget[@name='trajectorySelector']")
    assert trajectory_selector is not None
    assert trajectory_selector.find("./property[@name='SlicerParameterName']") is None
    workflow_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py"
    ).read_text(encoding="utf-8")
    assert "def _createCaseBundle" in workflow_source
    assert "def _openCaseBundle" in workflow_source
    assert "str(scenePath), {\"clear\": True}" in workflow_source
    assert "_beginCaseBundleRestore" in workflow_source
    assert "_bindAndValidateRestoredCase" in workflow_source
    assert "_validateHydratedCaseBundle" in workflow_source
    assert "prepareDentoCaseSchema2ForSave" in workflow_source
    assert "_resumeLoadedStep6Checkpoint" not in workflow_source
    lifecycle_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_lifecycle.py"
    ).read_text(encoding="utf-8")
    end_close = lifecycle_source[lifecycle_source.index("    def onSceneEndClose"):]
    end_close = end_close[:end_close.index("\n    def ", 5)]
    assert "if self._caseBundleRestoreDepth == 0:" in end_close
    assert "ensure_default_ros2_node_in_scene()" in end_close
    assert workflow_source.count("validateLoadedCaseBundleWorkflow") >= 2
    assert "validateLoadedCaseBundleWorkflow" in workflow_source
    cmake = (ROOT / "DENTOWorkflow/CMakeLists.txt").read_text(encoding="utf-8")
    assert "Resources/Python/DENTOCaseBundle.py" in cmake


def test_step6_jaw_opening_readiness_is_excluded_from_lineage_equivalence() -> None:
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_bundle.py"
    ).read_text(encoding="utf-8")
    validate_start = source.index("    def validateLoadedCaseBundleWorkflow")
    validate = source[validate_start:]
    assert 'expectedJawOpening.pop("current", None)' in validate
    assert 'expectedJawOpening.pop("placementReady", None)' in validate
    assert 'currentJawOpening.pop("current", None)' in validate
    assert 'currentJawOpening.pop("placementReady", None)' in validate


def test_case_bundle_validates_before_gui_hydration() -> None:
    source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py"
    ).read_text(encoding="utf-8")
    bind_start = source.index("    def _bindAndValidateRestoredCase")
    bind_end = source.index("\n    def ", bind_start + 5)
    bind = source[bind_start:bind_end]
    assert bind.count("validateLoadedCaseBundleWorkflow") == 2
    assert "self.setParameterNode(" not in bind
    assert "slicer.app.processEvents()" not in bind

    open_start = source.index("    def _openCaseBundle")
    open_end = source.index("\n    def onOpenCaseBundle", open_start)
    open_case = source[open_start:open_end]
    bind_validation = open_case.index(
        "self._bindAndValidateRestoredCase(inspection.workflow"
    )
    hydrated_validation = open_case.index(
        "self._validateHydratedCaseBundle(inspection.workflow)"
    )
    profile_migration = open_case.index(
        "self.logic._migrateLegacyJ2ZeroRobotProfile("
    )
    revalidation = open_case.index(
        "self._revalidateImportedStep6ContextAfterLoad()"
    )
    assert bind_validation < hydrated_validation < profile_migration < revalidation
    assert (
        "self.logic._migrateLegacyJ2ZeroRobotProfile(\n"
        "                                self.logic.getParameterNode(),"
    ) in open_case
    assert open_case.index(
        "self.setParameterNode(self.logic.getParameterNode())"
    ) < open_case.index("self._endCaseBundleRestore(restoreGeneration)") < open_case.index(
        "self.logic.hydrateDentoCaseStateAfterLoad("
    )
    assert "self._updateFromParameterNodeOnce()" in open_case
    assert open_case.index("self.logic.hydrateDentoCaseStateAfterLoad(") < open_case.index(
        "self._validateHydratedCaseBundle(inspection.workflow)"
    )
    validation = open_case.index(
        "self._validateHydratedCaseBundle(inspection.workflow)"
    )
    saved_environment_parse = open_case.index(
        "parse_robot_environment_snapshot(environment)", validation
    )
    saved_environment_reset = open_case.index(
        "self._parameterNode.step6EnvironmentJson = canonical_json(", validation
    )
    landmark_restore = open_case.index(
        "_restore_saved_case_foundation_landmarks(", validation
    )
    revalidate = open_case.index("self._revalidateImportedStep6ContextAfterLoad()")
    assert (
        validation
        < saved_environment_parse
        < saved_environment_reset
        < landmark_restore
        < revalidate
    )


def test_post_hydration_audit_allows_only_derived_environment_refresh() -> None:
    logic_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_bundle.py"
    ).read_text(encoding="utf-8")
    validate_start = logic_source.index("    def validateLoadedCaseBundleWorkflow")
    validate = logic_source[validate_start:]
    assert "allowDerivedEnvironmentMismatch: bool = False" in validate
    assert 'expectedComparableStep6.pop("environment", None)' in validate
    assert 'actualComparableStep6.pop("environment", None)' in validate

    backend_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py"
    ).read_text(encoding="utf-8")
    hydrated_start = backend_source.index("    def _validateHydratedCaseBundle")
    hydrated_end = backend_source.index("\n    @staticmethod", hydrated_start)
    hydrated = backend_source[hydrated_start:hydrated_end]
    assert "allowDerivedEnvironmentMismatch=True" in hydrated
