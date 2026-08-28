"""Ordinary-Python tests for the portable DENTOBOT case-bundle contract."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import (  # noqa: E402
    CASE_BUNDLE_EXTENSION,
    CaseBundleError,
    ROBOT_PROFILE_MEMBER,
    SCENE_MEMBER,
    audit_mrb_runtime_separation,
    build_robot_profile,
    create_case_bundle,
    extract_scene_mrb,
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
    assert inspection.manifest["runtime"]["ros2Serialized"] is False
    assert inspection.robot_profile["identitySha256"] == profile["identitySha256"]

    extracted, validated = extract_scene_mrb(
        inspection.path, tmp_path / "extracted"
    )
    assert extracted.read_bytes() == scene.read_bytes()
    assert validated.scene_sha256 == inspection.scene_sha256
    with zipfile.ZipFile(inspection.path) as archive:
        assert SCENE_MEMBER in archive.namelist()
        assert ROBOT_PROFILE_MEMBER in archive.namelist()


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
    workflow_source = (
        ROOT
        / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py"
    ).read_text(encoding="utf-8")
    assert "def _createCaseBundle" in workflow_source
    assert "def _openCaseBundle" in workflow_source
    assert "str(scenePath), {\"clear\": True}" in workflow_source
    assert "_beginCaseBundleRestore" in workflow_source
    assert "_bindAndValidateRestoredCase" in workflow_source
    assert workflow_source.count("validateLoadedCaseBundleWorkflow") >= 2
    assert "validateLoadedCaseBundleWorkflow" in workflow_source
    cmake = (ROOT / "DENTOWorkflow/CMakeLists.txt").read_text(encoding="utf-8")
    assert "Resources/Python/DENTOCaseBundle.py" in cmake
