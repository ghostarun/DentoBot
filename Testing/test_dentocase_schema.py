"""Focused compatibility tests for DentoCase archive schema versions."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import uuid
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import (  # noqa: E402
    CASE_BUNDLE_SCHEMA_VERSION,
    CHECKSUMS_MEMBER,
    MANIFEST_MEMBER,
    WORKFLOW_MEMBER,
    CaseBundleError,
    build_robot_profile,
    create_case_bundle,
    validate_case_bundle,
)
from DENTOStep6State import JOINT_NAMES, build_manual_simulation_record  # noqa: E402


def _write_mrb(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Case/scene.mrml", "<MRML/>")


def _robot_profile(tmp_path: Path) -> dict:
    description = tmp_path / "description"
    (description / "urdf").mkdir(parents=True, exist_ok=True)
    (description / "meshes").mkdir(parents=True, exist_ok=True)
    (description / "urdf" / "dentobot.urdf").write_text(
        '<robot name="dentobot"/>', encoding="utf-8"
    )
    (description / "meshes" / "link.stl").write_text(
        "solid link\nendsolid link\n", encoding="utf-8"
    )
    return build_robot_profile(description)


def _record(label: str) -> dict:
    identity = {
        name: f"{label}-{name}"
        for name in (
            "prepared_branch_id",
            "task_fingerprint",
            "base_fingerprint",
            "home_fingerprint",
            "trajectory_fingerprint",
            "robot_profile_fingerprint",
            "scene_fingerprint",
        )
    }
    return build_manual_simulation_record(
        identity=identity,
        events=[
            {
                "kind": "requested",
                "monotonic_ns": 0,
                "requested_joints": {name: 0.0 for name in JOINT_NAMES},
            }
        ],
    )


def _create(
    tmp_path: Path,
    name: str,
    *,
    workflow: dict | None = None,
    schema_version: str = CASE_BUNDLE_SCHEMA_VERSION,
    case_id: str | None = None,
    manual_simulation_records: tuple[dict, ...] = (),
):
    scene = tmp_path / f"{name}.mrb"
    _write_mrb(scene)
    return create_case_bundle(
        tmp_path / f"{name}.dentocase",
        scene,
        case_label=name,
        workflow=workflow or {"schemaVersion": "1.0", "nodes": []},
        robot_profile=_robot_profile(tmp_path),
        schema_version=schema_version,
        case_id=case_id,
        manual_simulation_records=manual_simulation_records,
    ).path


def _rewrite_archive(package: Path, transform) -> None:
    temporary = package.with_name(package.name + ".rewrite")
    with zipfile.ZipFile(package, "r") as source:
        members = [(info, source.read(info.filename)) for info in source.infolist()]
    contents = {info.filename: payload for info, payload in members}
    transform(contents)
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as output:
        for info, _ in members:
            output.writestr(info, contents[info.filename])
    temporary.replace(package)


def _rewrite_json_member(package: Path, member: str, transform) -> None:
    def apply(contents: dict[str, bytes]) -> None:
        value = json.loads(contents[member])
        transform(value)
        contents[member] = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        if member == WORKFLOW_MEMBER:
            manifest = json.loads(contents[MANIFEST_MEMBER])
            manifest["files"][WORKFLOW_MEMBER] = {
                "sha256": hashlib.sha256(contents[WORKFLOW_MEMBER]).hexdigest(),
                "sizeBytes": len(contents[WORKFLOW_MEMBER]),
            }
            contents[MANIFEST_MEMBER] = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            files = manifest["files"]
            contents[CHECKSUMS_MEMBER] = "".join(
                f"{record['sha256']}  {name}\n"
                for name, record in sorted(files.items())
            ).encode("ascii")

    _rewrite_archive(package, apply)


def test_schema2_manual_simulation_records_remain_readable(tmp_path: Path) -> None:
    package = _create(
        tmp_path,
        "schema-two-history",
        schema_version="2.0",
        manual_simulation_records=(_record("historical"),),
    )

    inspection = validate_case_bundle(package)

    assert inspection.manifest["schemaVersion"] == "2.0"
    assert inspection.study_index is not None
    assert inspection.study_attempts == ()
    assert len(inspection.manual_simulation_records) == 1
    assert "id" not in inspection.manifest["case"]


def test_schema3_case_identity_is_stable_across_package_revisions(
    tmp_path: Path,
) -> None:
    case_id = str(uuid.uuid4())
    first = _create(tmp_path, "schema-three-first", case_id=case_id)
    second = _create(
        tmp_path,
        "schema-three-second",
        workflow={"schemaVersion": "1.0", "nodes": [], "saveRevision": 2},
        case_id=case_id,
    )

    first_inspection = validate_case_bundle(first)
    second_inspection = validate_case_bundle(second)

    assert CASE_BUNDLE_SCHEMA_VERSION == "3.0"
    assert first_inspection.manifest["case"]["id"] == case_id
    assert second_inspection.manifest["case"]["id"] == case_id
    assert first_inspection.workflow["caseIdentity"]["id"] == case_id
    assert second_inspection.workflow["caseIdentity"]["id"] == case_id
    assert first_inspection.manifest["packageId"] != second_inspection.manifest["packageId"]


def test_schema3_adds_identity_without_mutating_callers_workflow(tmp_path: Path) -> None:
    case_id = str(uuid.uuid4())
    workflow = {
        "schemaVersion": "1.0",
        "nodes": [],
        "existing": {"value": "preserve"},
    }
    original = copy.deepcopy(workflow)

    package = _create(
        tmp_path,
        "schema-three-copy-workflow",
        workflow=workflow,
        case_id=case_id,
    )
    inspection = validate_case_bundle(package)

    assert workflow == original
    assert inspection.workflow["existing"] == original["existing"]
    assert inspection.workflow["caseIdentity"] == {"id": case_id}


def test_schema3_generates_identity_for_standalone_writer(tmp_path: Path) -> None:
    package = _create(tmp_path, "schema-three-generated")

    inspection = validate_case_bundle(package)
    case_id = inspection.manifest["case"]["id"]

    assert str(uuid.UUID(case_id)) == case_id
    assert inspection.workflow["caseIdentity"]["id"] == case_id


@pytest.mark.parametrize(
    ("case_id", "workflow", "message"),
    [
        ("bad-id", {"schemaVersion": "1.0"}, "case_id must be a UUID"),
        (
            None,
            {"schemaVersion": "1.0", "caseIdentity": {"id": "bad-id"}},
            "workflow.caseIdentity.id must be a UUID",
        ),
        (
            str(uuid.uuid4()),
            {"schemaVersion": "1.0", "caseIdentity": {"id": str(uuid.uuid4())}},
            "do not match",
        ),
    ],
)
def test_schema3_writer_rejects_invalid_or_conflicting_identity(
    tmp_path: Path, case_id: str | None, workflow: dict, message: str
) -> None:
    with pytest.raises(CaseBundleError, match=message):
        _create(
            tmp_path,
            f"invalid-{uuid.uuid4().hex}",
            workflow=workflow,
            case_id=case_id,
        )


def test_schema3_validator_rejects_invalid_manifest_uuid(tmp_path: Path) -> None:
    package = _create(tmp_path, "schema-three-invalid-manifest")
    _rewrite_json_member(
        package, MANIFEST_MEMBER, lambda manifest: manifest["case"].update(id="bad-id")
    )

    with pytest.raises(CaseBundleError, match="manifest.case.id must be a UUID"):
        validate_case_bundle(package)


def test_schema3_validator_rejects_workflow_manifest_identity_mismatch(
    tmp_path: Path,
) -> None:
    package = _create(tmp_path, "schema-three-mismatch")
    other_id = str(uuid.uuid4())
    _rewrite_json_member(
        package,
        WORKFLOW_MEMBER,
        lambda workflow: workflow["caseIdentity"].update(id=other_id),
    )

    with pytest.raises(CaseBundleError, match="case IDs do not match"):
        validate_case_bundle(package)


def test_schema3_checkpoint_inventory_requires_version_strings_only(
    tmp_path: Path,
) -> None:
    workflow = {
        "schemaVersion": "1.0",
        "checkpointInventory": {
            "schemaVersion": "future-schema",
            "definitionVersion": "future-definitions",
            "futurePayload": {"opaque": True},
        },
    }
    package = _create(tmp_path, "opaque-inventory", workflow=workflow)
    inspection = validate_case_bundle(package)

    assert inspection.workflow["checkpointInventory"] == workflow["checkpointInventory"]
    for invalid in (
        None,
        {"schemaVersion": "1.0"},
        {"schemaVersion": "1.0", "definitionVersion": " "},
        [],
    ):
        with pytest.raises(CaseBundleError, match="checkpointInventory"):
            _create(
                tmp_path,
                f"malformed-inventory-{uuid.uuid4().hex}",
                workflow={"checkpointInventory": invalid},
            )


def test_schema_one_and_two_legacy_bundles_remain_readable(tmp_path: Path) -> None:
    schema_one = _create(tmp_path, "legacy-schema-one", schema_version="1.0")
    schema_two = _create(tmp_path, "legacy-schema-two", schema_version="2.0")

    first = validate_case_bundle(schema_one)
    second = validate_case_bundle(schema_two)

    assert first.manifest["schemaVersion"] == "1.0"
    assert second.manifest["schemaVersion"] == "2.0"
    assert first.study_index is None and first.study_attempts == ()
    assert second.study_index is not None and second.study_attempts == ()
    assert "id" not in first.manifest["case"]
    assert "id" not in second.manifest["case"]
