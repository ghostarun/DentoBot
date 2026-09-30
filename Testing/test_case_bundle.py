"""Ordinary-Python tests for the portable DENTOBOT case-bundle contract."""

from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile

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
    lineage_snapshot_matches,
    lineage_snapshot_mismatch_path,
    validate_case_bundle,
)


def write_mrb(path: Path, mrml: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Case/scene.mrml", mrml)


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
    assert open_case.index(
        "self.setParameterNode(self.logic.getParameterNode())"
    ) < open_case.index("self._endCaseBundleRestore(restoreGeneration)") < open_case.index(
        "self.logic.hydrateDentoCaseStateAfterLoad("
    )
    assert "self._updateFromParameterNodeOnce()" in open_case
    assert open_case.index("self.logic.hydrateDentoCaseStateAfterLoad(") < open_case.index(
        "self._validateHydratedCaseBundle(inspection.workflow)"
    )
    assert open_case.index("self._validateHydratedCaseBundle(inspection.workflow)") < open_case.index(
        "self._revalidateImportedStep6ContextAfterLoad()"
    )

    template_build_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_template_build.py"
    ).read_text(encoding="utf-8")
    controls_start = template_build_source.index(
        "    def _updateFinalPrintableTemplateControls"
    )
    controls_end = template_build_source.index("\n    def ", controls_start + 5)
    controls = template_build_source[controls_start:controls_end]
    assert "restoringCaseBundle = bool(self._caseBundleRestoreDepth)" in controls
    assert "if staleReason and not restoringCaseBundle:" in controls


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
