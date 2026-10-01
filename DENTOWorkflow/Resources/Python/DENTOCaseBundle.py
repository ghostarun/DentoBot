"""Versioned, integrity-checked DENTOBOT case-bundle utilities.

This module deliberately has no Slicer dependency.  Slicer owns creation and
loading of the embedded MRB; this helper owns only the outer archive contract.
Live ROS objects are never a supported payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Mapping, Sequence
import uuid
import zipfile

from DENTOStep6State import parse_manual_simulation_record


CASE_BUNDLE_FORMAT = "DENTOBOTCaseBundle"
CASE_BUNDLE_SCHEMA_VERSION = "3.0"
SUPPORTED_CASE_BUNDLE_SCHEMA_VERSIONS = ("1.0", "2.0", CASE_BUNDLE_SCHEMA_VERSION)
STUDY_CASE_BUNDLE_SCHEMA_VERSIONS = ("2.0", "3.0")
CASE_BUNDLE_EXTENSION = ".dentocase"
SCENE_MEMBER = "scene/case.mrb"
MANIFEST_MEMBER = "manifest.json"
CHECKSUMS_MEMBER = "integrity/checksums.sha256"
WORKFLOW_MEMBER = "workflow/lineage.json"
ROBOT_PROFILE_MEMBER = "robot/robot-profile.json"
SAVE_REPORT_MEMBER = "records/save-report.json"
STUDY_INDEX_MEMBER = "study/index.json"
STUDY_ATTEMPTS_MEMBER = "study/attempts.ndjson"
MANUAL_SIMULATION_MEMBER = "records/manual-simulation.json"

MAX_ARCHIVE_MEMBERS = 128
MAX_METADATA_MEMBER_BYTES = 16 * 1024 * 1024
MAX_SCENE_MEMBER_BYTES = 64 * 1024 * 1024 * 1024
MAX_MANUAL_SIMULATION_RECORDS = 100
MAX_MANUAL_SIMULATION_EVENTS = 10_000


class CaseBundleError(RuntimeError):
    """Raised when a case bundle is unsafe, unsupported, or incomplete."""


@dataclass(frozen=True)
class CaseBundleInspection:
    path: Path
    manifest: dict
    workflow: dict
    robot_profile: dict
    save_report: dict
    study_index: dict | None = None
    study_attempts: tuple[dict, ...] = ()
    manual_simulation_records: tuple[dict, ...] = ()

    @property
    def scene_sha256(self) -> str:
        return str(self.manifest["files"][SCENE_MEMBER]["sha256"])


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validated_case_uuid(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaseBundleError(f"{field_name} must be a UUID string.")
    try:
        return str(uuid.UUID(value.strip()))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CaseBundleError(f"{field_name} must be a UUID string.") from exc


def _schema3_case_identity(
    workflow: Mapping[str, object], case_id: str | None
) -> tuple[str, dict[str, object]]:
    copied_workflow = dict(workflow)
    raw_identity = copied_workflow.get("caseIdentity")
    if raw_identity is not None and not isinstance(raw_identity, Mapping):
        raise CaseBundleError("workflow.caseIdentity must be an object.")
    copied_identity = dict(raw_identity) if isinstance(raw_identity, Mapping) else {}
    workflow_id = None
    if "id" in copied_identity:
        workflow_id = _validated_case_uuid(
            copied_identity["id"], "workflow.caseIdentity.id"
        )
    supplied_id = (
        _validated_case_uuid(case_id, "case_id") if case_id is not None else None
    )
    if supplied_id and workflow_id and supplied_id != workflow_id:
        raise CaseBundleError("case_id and workflow.caseIdentity.id do not match.")
    stable_id = supplied_id or workflow_id or str(uuid.uuid4())
    copied_identity["id"] = stable_id
    copied_workflow["caseIdentity"] = copied_identity
    return stable_id, copied_workflow


def lineage_snapshot_matches(
    expected: object,
    actual: object,
    tolerance: float = 1e-6,
) -> bool:
    """Compare saved lineage against a reconstructed, possibly newer record.

    Schema-v1 lineage fields are append-only extensions. A package therefore
    defines the values that must still match after MRML restoration, while a
    newer application may reconstruct additional dictionary keys that the
    older package could not have recorded. Lists remain exact and coordinates
    retain the established absolute tolerance.
    """

    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return (
            math.isfinite(float(expected))
            and math.isfinite(float(actual))
            and abs(float(expected) - float(actual)) <= tolerance
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            lineage_snapshot_matches(left, right, tolerance)
            for left, right in zip(expected, actual)
        )
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual
            and lineage_snapshot_matches(expected[key], actual[key], tolerance)
            for key in expected
        )
    return expected == actual


def lineage_snapshot_mismatch_path(
    expected: object,
    actual: object,
    tolerance: float = 1e-6,
) -> str:
    """Return the first saved-lineage field that does not reconstruct."""

    if lineage_snapshot_matches(expected, actual, tolerance):
        return ""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return "<record>"
        for key in expected:
            if key not in actual:
                return str(key)
            nested = lineage_snapshot_mismatch_path(
                expected[key], actual[key], tolerance
            )
            if nested:
                if nested == "<value>":
                    return str(key)
                separator = "" if nested.startswith("[") else "."
                return f"{key}{separator}{nested}"
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return "<list>"
        for index, (left, right) in enumerate(zip(expected, actual)):
            nested = lineage_snapshot_mismatch_path(left, right, tolerance)
            if nested:
                if nested == "<value>":
                    return f"[{index}]"
                separator = "" if nested.startswith("[") else "."
                return f"[{index}]{separator}{nested}"
    return "<value>"


def _safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _json_member(archive: zipfile.ZipFile, name: str) -> dict:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise CaseBundleError(f"Required case-bundle member is missing: {name}") from exc
    if info.file_size > MAX_METADATA_MEMBER_BYTES:
        raise CaseBundleError(f"Case-bundle metadata member is too large: {name}")
    try:
        value = json.loads(archive.read(name).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaseBundleError(f"Case-bundle member is not valid UTF-8 JSON: {name}") from exc
    if not isinstance(value, dict):
        raise CaseBundleError(f"Case-bundle JSON member must contain an object: {name}")
    return value


def _validated_manual_simulation_records(
    records: Sequence[Mapping[str, object]],
) -> tuple[dict, ...]:
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise CaseBundleError("Manual simulation records must be a sequence.")
    if len(records) > MAX_MANUAL_SIMULATION_RECORDS:
        raise CaseBundleError("The manual simulation record count exceeds its limit.")
    total_events = 0
    fingerprints = set()
    validated = []
    for record in records:
        if not isinstance(record, Mapping):
            raise CaseBundleError("Every manual simulation record must be an object.")
        events = record.get("events")
        if isinstance(events, (str, bytes, Mapping)) or not isinstance(
            events, Sequence
        ):
            raise CaseBundleError("Manual simulation events must be a sequence.")
        total_events += len(events)
        if total_events > MAX_MANUAL_SIMULATION_EVENTS:
            raise CaseBundleError("The manual simulation event count exceeds its limit.")
        try:
            parsed = parse_manual_simulation_record(record)
        except (TypeError, ValueError, OverflowError) as exc:
            raise CaseBundleError(f"Invalid manual simulation record: {exc}") from exc
        fingerprint = parsed["record_fingerprint"]
        if fingerprint in fingerprints:
            raise CaseBundleError(
                "Manual simulation records contain a duplicate fingerprint."
            )
        fingerprints.add(fingerprint)
        validated.append(parsed)
    return tuple(validated)


def _checksum_lines(files: Mapping[str, Mapping[str, object]]) -> bytes:
    return "".join(
        f"{record['sha256']}  {name}\n" for name, record in sorted(files.items())
    ).encode("ascii")


def _file_record_from_bytes(payload: bytes) -> dict[str, object]:
    return {"sha256": _sha256_bytes(payload), "sizeBytes": len(payload)}


def _file_record_from_path(path: Path) -> dict[str, object]:
    return {"sha256": sha256_file(path), "sizeBytes": path.stat().st_size}


def _read_mrb_scene_text(path: str | Path) -> str:
    scene_path = Path(path)
    if not zipfile.is_zipfile(scene_path):
        raise CaseBundleError("The embedded Slicer scene must be an MRB archive.")
    with zipfile.ZipFile(scene_path, "r") as archive:
        mrml_members = [name for name in archive.namelist() if name.lower().endswith(".mrml")]
        if len(mrml_members) != 1:
            raise CaseBundleError(
                "The embedded MRB must contain exactly one MRML scene file."
            )
        info = archive.getinfo(mrml_members[0])
        if info.file_size > MAX_METADATA_MEMBER_BYTES:
            raise CaseBundleError("The embedded MRML scene description is too large.")
        try:
            return archive.read(info).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CaseBundleError("The embedded MRML scene is not valid UTF-8.") from exc


def audit_mrb_runtime_separation(path: str | Path) -> dict[str, object]:
    """Reject a scene that would restore process-owned ROS/SlicerROS2 state."""

    scene_text = _read_mrb_scene_text(path)
    forbidden_tokens = (
        "vtkMRMLROS2",
        "<ROS2",
        "DENTOBOTRuntimeROS2Default",
    )
    present = [token for token in forbidden_tokens if token in scene_text]
    active_flag_present = (
        "DENTOBOT.Ros2MotionControlActive:true" in scene_text
        or 'DENTOBOT.Ros2MotionControlActive="true"' in scene_text
        or "DENTOBOT.Ros2MotionControlActive%3Atrue" in scene_text
    )
    if present or active_flag_present:
        details = ", ".join(present + (["ROS-active flag"] if active_flag_present else []))
        raise CaseBundleError(
            "The MRB contains live ROS/SlicerROS2 runtime state and cannot be "
            f"placed in a DENTOBOT case bundle ({details})."
        )
    return {
        "ros2RuntimeNodesSerialized": False,
        "ros2MotionActiveSerialized": False,
        "restorePolicy": "explicit-step6-reconstruction",
    }


def build_robot_profile(
    description_root: str | Path,
    moveit_root: str | Path | None = None,
) -> dict[str, object]:
    """Fingerprint portable robot resources without recording machine paths."""

    roots = [("description", Path(description_root))]
    if moveit_root is not None and Path(moveit_root).is_dir():
        roots.append(("moveit", Path(moveit_root)))
    components = []
    allowed_suffixes = {".urdf", ".xacro", ".srdf", ".yaml", ".yml", ".stl"}
    for prefix, root in roots:
        if not root.is_dir():
            continue
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            if path.suffix.lower() not in allowed_suffixes:
                continue
            components.append(
                {
                    "path": f"{prefix}/{path.relative_to(root).as_posix()}",
                    "sha256": sha256_file(path),
                    "sizeBytes": path.stat().st_size,
                }
            )
    if not any(record["path"].endswith("/dentobot.urdf") for record in components):
        raise CaseBundleError("The DENTOBOT robot profile has no dentobot.urdf.")
    identity_payload = _canonical_json_bytes(components)
    return {
        "schemaVersion": "1.0",
        "identitySha256": _sha256_bytes(identity_payload),
        "components": components,
        "runtimeRestorePolicy": "verify-installed-resources-then-explicitly-connect",
    }


def is_additive_rrt_profile_upgrade(saved: Mapping, current: Mapping) -> bool:
    """Recognize only the checked-in additive RRT/RRT* OMPL choices."""

    path = "moveit/config/ompl_planning.yaml"
    saved_yaml_versions = {
        ("10f6f69a2f40f047b64430d1f408ecec0350ee29cafc27a9758d07821b16c355", 748),
        ("da568f2f092e61e9cca2a93d448aa1b4e5b4e143d187248767d240081e106011", 833),
    }
    current_yaml = (
        "9acb46e12a30dcf198d2fe415f10446b8f340fe57b9051de7a9ad91cbab5e7b3",
        930,
    )
    if (
        saved.get("schemaVersion") != "1.0"
        or current.get("schemaVersion") != "1.0"
        or saved.get("runtimeRestorePolicy") != current.get("runtimeRestorePolicy")
    ):
        return False
    before, after = saved.get("components"), current.get("components")
    if not isinstance(before, list) or not isinstance(after, list):
        return False
    if any(not isinstance(item, dict) for item in before + after):
        return False
    paths = [item.get("path") for item in before]
    if (
        any(not isinstance(path, str) for path in paths)
        or any(not isinstance(item.get("path"), str) for item in after)
        or len(paths) != len(set(paths))
        or paths != [item.get("path") for item in after]
    ):
        return False
    if (
        saved.get("identitySha256") != _sha256_bytes(_canonical_json_bytes(before))
        or current.get("identitySha256") != _sha256_bytes(_canonical_json_bytes(after))
    ):
        return False
    changed = [(left, right) for left, right in zip(before, after) if left != right]
    return (
        len(before) == len(after)
        and len(changed) == 1
        and changed[0][0].get("path") == path
        and changed[0][1].get("path") == path
        and (changed[0][0].get("sha256"), changed[0][0].get("sizeBytes"))
        in saved_yaml_versions
        and (changed[0][1].get("sha256"), changed[0][1].get("sizeBytes"))
        == current_yaml
    )


def is_five_dof_profile_upgrade(saved: Mapping, current: Mapping) -> bool:
    """Recognize only the recorded six-to-five-DOF URDF profile transition."""

    saved_identity = "e73acf9bb6ca29a30707a99ad104235376ef0a579bf0bf71ac117608bb2fe682"
    current_identity = (
        "cac087c6ee96258416e587e43303a0351f331a8b668daf4ff0f3929a030ae52c"
    )
    urdf_hashes = {
        "description/urdf/dentobot.urdf": (
            "c70c12e38dc12dd4798f6332426eea82a430dc882836ef31cf0ce293c1e3f3d5",
            "3638f919e5a853b1c72d851f8bf61d4aaff8942aaa767c476face0108daedf8a",
        ),
        "description/urdf/dentobot.diagnostic-no-spindle-collision.urdf": (
            "8345886de7ecbe359df010da37a5099d209edae41dc9fc9857a4dccbe61ace99",
            "980192c3d4239876ad31948671117acc368816317a814d9433db4c101f0b6995",
        ),
    }
    if (
        saved.get("schemaVersion") != "1.0"
        or current.get("schemaVersion") != "1.0"
        or saved.get("runtimeRestorePolicy")
        != "verify-installed-resources-then-explicitly-connect"
        or current.get("runtimeRestorePolicy")
        != "verify-installed-resources-then-explicitly-connect"
        or saved.get("identitySha256") != saved_identity
        or current.get("identitySha256") != current_identity
    ):
        return False
    before, after = saved.get("components"), current.get("components")
    if (
        not isinstance(before, list)
        or not isinstance(after, list)
        or any(not isinstance(item, dict) for item in before + after)
        or any(set(item) != {"path", "sha256", "sizeBytes"} for item in before + after)
        or any(not isinstance(item.get("path"), str) for item in before + after)
    ):
        return False
    saved_by_path = {item["path"]: item for item in before}
    current_by_path = {item["path"]: item for item in after}
    if (
        len(saved_by_path) != len(before)
        or len(current_by_path) != len(after)
        or saved_by_path.keys() != current_by_path.keys()
    ):
        return False
    if any(
        saved_by_path.get(path, {}).get("sha256") != hashes[0]
        or current_by_path.get(path, {}).get("sha256") != hashes[1]
        for path, hashes in urdf_hashes.items()
    ):
        return False
    return all(
        saved_by_path[path] == current_by_path[path]
        for path in saved_by_path.keys() - urdf_hashes.keys()
    )


def create_case_bundle(
    destination: str | Path,
    scene_mrb: str | Path,
    *,
    case_label: str,
    workflow: Mapping[str, object],
    robot_profile: Mapping[str, object],
    application: Mapping[str, object] | None = None,
    created_at_utc: str | None = None,
    schema_version: str = CASE_BUNDLE_SCHEMA_VERSION,
    case_id: str | None = None,
    manual_simulation_records: Sequence[Mapping[str, object]] = (),
) -> CaseBundleInspection:
    """Create a bundle; manual records are display-only, never scene/ROS authority."""

    destination = Path(destination)
    if destination.suffix.lower() != CASE_BUNDLE_EXTENSION:
        destination = destination.with_name(destination.name + CASE_BUNDLE_EXTENSION)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene_mrb = Path(scene_mrb)
    if not scene_mrb.is_file():
        raise CaseBundleError(f"The scene MRB does not exist: {scene_mrb}")
    runtime_audit = audit_mrb_runtime_separation(scene_mrb)
    if schema_version not in SUPPORTED_CASE_BUNDLE_SCHEMA_VERSIONS:
        raise CaseBundleError(f"Unsupported DENTOBOT case-bundle schema: {schema_version}")
    workflow_payload = dict(workflow)
    stable_case_id = None
    if schema_version == CASE_BUNDLE_SCHEMA_VERSION:
        stable_case_id, workflow_payload = _schema3_case_identity(workflow, case_id)
    elif case_id is not None:
        raise CaseBundleError("case_id is supported only for schema-3 case bundles.")
    manual_records = _validated_manual_simulation_records(manual_simulation_records)
    if manual_records and schema_version not in STUDY_CASE_BUNDLE_SCHEMA_VERSIONS:
        raise CaseBundleError(
            "Manual simulation records require a schema-2 or schema-3 case bundle."
        )
    manual_records_bytes = (
        _canonical_json_bytes(list(manual_records)) if manual_records else None
    )
    if (
        manual_records_bytes is not None
        and len(manual_records_bytes) > MAX_METADATA_MEMBER_BYTES
    ):
        raise CaseBundleError("The manual simulation record member is too large.")

    workflow_bytes = _canonical_json_bytes(workflow_payload)
    robot_bytes = _canonical_json_bytes(dict(robot_profile))
    save_report = {
        "schemaVersion": "1.0",
        "result": "complete",
        "runtimeAudit": runtime_audit,
        "coordinateValidation": "deferred-to-loaded-MRML",
    }
    save_report_bytes = _canonical_json_bytes(save_report)
    study_index = {
        "schemaVersion": "1.0",
        "attemptContextSchemaVersion": "1.0",
        "attemptCount": 0,
        "replays": [],
    }
    study_index_bytes = _canonical_json_bytes(study_index)
    study_attempts_bytes = b""
    files = {
        SCENE_MEMBER: _file_record_from_path(scene_mrb),
        WORKFLOW_MEMBER: _file_record_from_bytes(workflow_bytes),
        ROBOT_PROFILE_MEMBER: _file_record_from_bytes(robot_bytes),
        SAVE_REPORT_MEMBER: _file_record_from_bytes(save_report_bytes),
    }
    if schema_version in STUDY_CASE_BUNDLE_SCHEMA_VERSIONS:
        files.update(
            {
                STUDY_INDEX_MEMBER: _file_record_from_bytes(study_index_bytes),
                STUDY_ATTEMPTS_MEMBER: _file_record_from_bytes(study_attempts_bytes),
            }
        )
    if manual_records_bytes is not None:
        files[MANUAL_SIMULATION_MEMBER] = _file_record_from_bytes(manual_records_bytes)
    manifest = {
        "format": CASE_BUNDLE_FORMAT,
        "schemaVersion": schema_version,
        "packageId": str(uuid.uuid4()),
        "createdAtUtc": created_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case": {
            "label": str(case_label or ""),
            **({"id": stable_case_id} if stable_case_id is not None else {}),
        },
        "coordinateSystem": {
            "world": "SlicerRAS",
            "lengthUnit": "mm",
            "transformConvention": "MRML-transform-to-parent",
        },
        "application": dict(application or {}),
        "scene": {"member": SCENE_MEMBER, "authority": "case-geometry-and-workflow"},
        "runtime": {
            "ros2Serialized": False,
            "restorePolicy": "never-auto-connect",
        },
        "files": files,
    }
    manifest_bytes = _canonical_json_bytes(manifest)
    checksum_bytes = _checksum_lines(files)

    temporary_path = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        with zipfile.ZipFile(temporary_path, "w", allowZip64=True) as archive:
            archive.writestr(MANIFEST_MEMBER, manifest_bytes, zipfile.ZIP_DEFLATED)
            archive.write(scene_mrb, SCENE_MEMBER, compress_type=zipfile.ZIP_STORED)
            archive.writestr(WORKFLOW_MEMBER, workflow_bytes, zipfile.ZIP_DEFLATED)
            archive.writestr(ROBOT_PROFILE_MEMBER, robot_bytes, zipfile.ZIP_DEFLATED)
            archive.writestr(SAVE_REPORT_MEMBER, save_report_bytes, zipfile.ZIP_DEFLATED)
            if schema_version in STUDY_CASE_BUNDLE_SCHEMA_VERSIONS:
                archive.writestr(STUDY_INDEX_MEMBER, study_index_bytes, zipfile.ZIP_DEFLATED)
                archive.writestr(STUDY_ATTEMPTS_MEMBER, study_attempts_bytes, zipfile.ZIP_DEFLATED)
            if manual_records_bytes is not None:
                archive.writestr(
                    MANUAL_SIMULATION_MEMBER,
                    manual_records_bytes,
                    zipfile.ZIP_DEFLATED,
                )
            archive.writestr(CHECKSUMS_MEMBER, checksum_bytes, zipfile.ZIP_DEFLATED)
        inspection = validate_case_bundle(temporary_path)
        os.replace(temporary_path, destination)
        temporary_path = None
        return CaseBundleInspection(
            path=destination,
            manifest=inspection.manifest,
            workflow=inspection.workflow,
            robot_profile=inspection.robot_profile,
            save_report=inspection.save_report,
            study_index=inspection.study_index,
            study_attempts=inspection.study_attempts,
            manual_simulation_records=inspection.manual_simulation_records,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def validate_case_bundle(path: str | Path) -> CaseBundleInspection:
    bundle_path = Path(path)
    if not bundle_path.is_file() or not zipfile.is_zipfile(bundle_path):
        raise CaseBundleError("The selected file is not a DENTOBOT case bundle.")
    with zipfile.ZipFile(bundle_path, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise CaseBundleError("The case bundle contains too many archive members.")
        if len(names) != len(set(names)):
            raise CaseBundleError("The case bundle contains duplicate archive members.")
        for info in infos:
            if not _safe_member_name(info.filename):
                raise CaseBundleError(
                    f"The case bundle contains an unsafe archive path: {info.filename}"
                )
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise CaseBundleError(
                    f"The case bundle contains an unsupported symbolic link: {info.filename}"
                )
            limit = (
                MAX_SCENE_MEMBER_BYTES
                if info.filename == SCENE_MEMBER
                else MAX_METADATA_MEMBER_BYTES
            )
            if info.file_size > limit:
                raise CaseBundleError(
                    f"The case-bundle member exceeds its size limit: {info.filename}"
                )

        required = {
            MANIFEST_MEMBER,
            SCENE_MEMBER,
            CHECKSUMS_MEMBER,
            WORKFLOW_MEMBER,
            ROBOT_PROFILE_MEMBER,
            SAVE_REPORT_MEMBER,
        }
        missing = sorted(required - set(names))
        if missing:
            raise CaseBundleError(
                "The case bundle is incomplete: " + ", ".join(missing)
            )
        manifest = _json_member(archive, MANIFEST_MEMBER)
        if manifest.get("format") != CASE_BUNDLE_FORMAT:
            raise CaseBundleError("The archive is not a DENTOBOT case bundle.")
        schema_version = str(manifest.get("schemaVersion") or "")
        if schema_version not in SUPPORTED_CASE_BUNDLE_SCHEMA_VERSIONS:
            raise CaseBundleError(
                "Unsupported DENTOBOT case-bundle schema: "
                f"{manifest.get('schemaVersion') or 'missing'}"
            )
        if schema_version in STUDY_CASE_BUNDLE_SCHEMA_VERSIONS:
            required.update((STUDY_INDEX_MEMBER, STUDY_ATTEMPTS_MEMBER))
            missing = sorted(required - set(names))
            if missing:
                raise CaseBundleError(
                    "The case bundle is incomplete: " + ", ".join(missing)
                )
        optional = (
            {MANUAL_SIMULATION_MEMBER}
            if schema_version in STUDY_CASE_BUNDLE_SCHEMA_VERSIONS
            else set()
        )
        unexpected = sorted(set(names) - required - optional)
        if unexpected:
            raise CaseBundleError(
                "The case bundle contains unsupported archive members: "
                + ", ".join(unexpected)
            )
        required.update(set(names) & optional)
        coordinate = manifest.get("coordinateSystem")
        if not isinstance(coordinate, dict) or (
            coordinate.get("world") != "SlicerRAS"
            or coordinate.get("lengthUnit") != "mm"
        ):
            raise CaseBundleError(
                "The case bundle does not declare Slicer world-RAS millimetres."
            )
        runtime = manifest.get("runtime")
        if not isinstance(runtime, dict) or runtime.get("ros2Serialized") is not False:
            raise CaseBundleError("The case bundle does not prohibit serialized ROS state.")
        files = manifest.get("files")
        expected_files = required - {MANIFEST_MEMBER, CHECKSUMS_MEMBER}
        if not isinstance(files, dict) or set(files) != expected_files:
            raise CaseBundleError("The case-bundle file inventory is invalid.")
        checksum_text = archive.read(CHECKSUMS_MEMBER).decode("ascii")
        if checksum_text.encode("ascii") != _checksum_lines(files):
            raise CaseBundleError("The checksum inventory does not match the manifest.")
        for name, expected in files.items():
            if not isinstance(expected, dict):
                raise CaseBundleError(f"Invalid file record for {name}.")
            digest = hashlib.sha256()
            size = 0
            with archive.open(name, "r") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
            if digest.hexdigest() != expected.get("sha256") or size != expected.get(
                "sizeBytes"
            ):
                raise CaseBundleError(f"Case-bundle integrity check failed: {name}")
        workflow = _json_member(archive, WORKFLOW_MEMBER)
        if schema_version == CASE_BUNDLE_SCHEMA_VERSION:
            case_record = manifest.get("case")
            if not isinstance(case_record, dict) or "id" not in case_record:
                raise CaseBundleError("Schema-3 manifest.case.id is required.")
            manifest_case_id = _validated_case_uuid(
                case_record["id"], "manifest.case.id"
            )
            case_identity = workflow.get("caseIdentity")
            if not isinstance(case_identity, dict) or "id" not in case_identity:
                raise CaseBundleError("Schema-3 workflow.caseIdentity.id is required.")
            workflow_case_id = _validated_case_uuid(
                case_identity["id"], "workflow.caseIdentity.id"
            )
            if workflow_case_id != manifest_case_id:
                raise CaseBundleError(
                    "Schema-3 manifest and workflow case IDs do not match."
                )
            if "checkpointInventory" in workflow:
                checkpoint_inventory = workflow["checkpointInventory"]
                if not isinstance(checkpoint_inventory, dict):
                    raise CaseBundleError(
                        "Schema-3 workflow.checkpointInventory must be an object."
                    )
                for field_name in ("schemaVersion", "definitionVersion"):
                    value = checkpoint_inventory.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        raise CaseBundleError(
                            "Schema-3 checkpointInventory requires non-empty "
                            f"{field_name}."
                        )
        robot_profile = _json_member(archive, ROBOT_PROFILE_MEMBER)
        save_report = _json_member(archive, SAVE_REPORT_MEMBER)
        if save_report.get("runtimeAudit", {}).get("ros2RuntimeNodesSerialized") is not False:
            raise CaseBundleError("The bundle save report did not pass ROS separation.")
        study_index = None
        study_attempts: tuple[dict, ...] = ()
        manual_simulation_records: tuple[dict, ...] = ()
        if schema_version in STUDY_CASE_BUNDLE_SCHEMA_VERSIONS:
            study_index = _json_member(archive, STUDY_INDEX_MEMBER)
            if (
                study_index.get("schemaVersion") != "1.0"
                or study_index.get("attemptContextSchemaVersion") != "1.0"
                or study_index.get("attemptCount") != 0
                or study_index.get("replays") != []
            ):
                raise CaseBundleError("The schema-2 study index is invalid.")
            attempts_text = archive.read(STUDY_ATTEMPTS_MEMBER).decode("utf-8")
            try:
                study_attempts = tuple(
                    json.loads(line) for line in attempts_text.splitlines() if line.strip()
                )
            except json.JSONDecodeError as exc:
                raise CaseBundleError("The study attempt ledger is invalid NDJSON.") from exc
            if any(not isinstance(record, dict) for record in study_attempts):
                raise CaseBundleError("Every study attempt must be a JSON object.")
            if len(study_attempts) != int(study_index["attemptCount"]):
                raise CaseBundleError("The study attempt count does not match its ledger.")
            if MANUAL_SIMULATION_MEMBER in names:
                try:
                    raw_records = json.loads(
                        archive.read(MANUAL_SIMULATION_MEMBER).decode("utf-8")
                    )
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CaseBundleError(
                        "The manual simulation record member is not valid UTF-8 JSON."
                    ) from exc
                if not isinstance(raw_records, list):
                    raise CaseBundleError(
                        "The manual simulation record member must contain an array."
                    )
                manual_simulation_records = _validated_manual_simulation_records(
                    raw_records
                )
        return CaseBundleInspection(
            path=bundle_path,
            manifest=manifest,
            workflow=workflow,
            robot_profile=robot_profile,
            save_report=save_report,
            study_index=study_index,
            study_attempts=study_attempts,
            manual_simulation_records=manual_simulation_records,
        )


def extract_scene_mrb(
    bundle: str | Path,
    destination_directory: str | Path,
) -> tuple[Path, CaseBundleInspection]:
    inspection = validate_case_bundle(bundle)
    destination = Path(destination_directory)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "case.mrb"
    temporary = destination / ".case.mrb.tmp"
    try:
        with zipfile.ZipFile(inspection.path, "r") as archive, archive.open(
            SCENE_MEMBER, "r"
        ) as source, temporary.open("wb") as target:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                target.write(block)
        if sha256_file(temporary) != inspection.scene_sha256:
            raise CaseBundleError("Extracted MRB checksum does not match the manifest.")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    audit_mrb_runtime_separation(output)
    return output, inspection
