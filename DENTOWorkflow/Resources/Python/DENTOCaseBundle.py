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
from typing import Mapping
import uuid
import zipfile


CASE_BUNDLE_FORMAT = "DENTOBOTCaseBundle"
CASE_BUNDLE_SCHEMA_VERSION = "1.0"
CASE_BUNDLE_EXTENSION = ".dentocase"
SCENE_MEMBER = "scene/case.mrb"
MANIFEST_MEMBER = "manifest.json"
CHECKSUMS_MEMBER = "integrity/checksums.sha256"
WORKFLOW_MEMBER = "workflow/lineage.json"
ROBOT_PROFILE_MEMBER = "robot/robot-profile.json"
SAVE_REPORT_MEMBER = "records/save-report.json"

MAX_ARCHIVE_MEMBERS = 128
MAX_METADATA_MEMBER_BYTES = 16 * 1024 * 1024
MAX_SCENE_MEMBER_BYTES = 64 * 1024 * 1024 * 1024


class CaseBundleError(RuntimeError):
    """Raised when a case bundle is unsafe, unsupported, or incomplete."""


@dataclass(frozen=True)
class CaseBundleInspection:
    path: Path
    manifest: dict
    workflow: dict
    robot_profile: dict
    save_report: dict

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


def create_case_bundle(
    destination: str | Path,
    scene_mrb: str | Path,
    *,
    case_label: str,
    workflow: Mapping[str, object],
    robot_profile: Mapping[str, object],
    application: Mapping[str, object] | None = None,
    created_at_utc: str | None = None,
) -> CaseBundleInspection:
    """Atomically create and then validate one portable case bundle."""

    destination = Path(destination)
    if destination.suffix.lower() != CASE_BUNDLE_EXTENSION:
        destination = destination.with_name(destination.name + CASE_BUNDLE_EXTENSION)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene_mrb = Path(scene_mrb)
    if not scene_mrb.is_file():
        raise CaseBundleError(f"The scene MRB does not exist: {scene_mrb}")
    runtime_audit = audit_mrb_runtime_separation(scene_mrb)

    workflow_bytes = _canonical_json_bytes(dict(workflow))
    robot_bytes = _canonical_json_bytes(dict(robot_profile))
    save_report = {
        "schemaVersion": "1.0",
        "result": "complete",
        "runtimeAudit": runtime_audit,
        "coordinateValidation": "deferred-to-loaded-MRML",
    }
    save_report_bytes = _canonical_json_bytes(save_report)
    files = {
        SCENE_MEMBER: _file_record_from_path(scene_mrb),
        WORKFLOW_MEMBER: _file_record_from_bytes(workflow_bytes),
        ROBOT_PROFILE_MEMBER: _file_record_from_bytes(robot_bytes),
        SAVE_REPORT_MEMBER: _file_record_from_bytes(save_report_bytes),
    }
    manifest = {
        "format": CASE_BUNDLE_FORMAT,
        "schemaVersion": CASE_BUNDLE_SCHEMA_VERSION,
        "packageId": str(uuid.uuid4()),
        "createdAtUtc": created_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case": {"label": str(case_label or "")},
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
        unexpected = sorted(set(names) - required)
        if unexpected:
            raise CaseBundleError(
                "The case bundle contains unsupported archive members: "
                + ", ".join(unexpected)
            )
        manifest = _json_member(archive, MANIFEST_MEMBER)
        if manifest.get("format") != CASE_BUNDLE_FORMAT:
            raise CaseBundleError("The archive is not a DENTOBOT case bundle.")
        if manifest.get("schemaVersion") != CASE_BUNDLE_SCHEMA_VERSION:
            raise CaseBundleError(
                "Unsupported DENTOBOT case-bundle schema: "
                f"{manifest.get('schemaVersion') or 'missing'}"
            )
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
        if not isinstance(files, dict) or set(files) != {
            SCENE_MEMBER,
            WORKFLOW_MEMBER,
            ROBOT_PROFILE_MEMBER,
            SAVE_REPORT_MEMBER,
        }:
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
        robot_profile = _json_member(archive, ROBOT_PROFILE_MEMBER)
        save_report = _json_member(archive, SAVE_REPORT_MEMBER)
        if save_report.get("runtimeAudit", {}).get("ros2RuntimeNodesSerialized") is not False:
            raise CaseBundleError("The bundle save report did not pass ROS separation.")
        return CaseBundleInspection(
            path=bundle_path,
            manifest=manifest,
            workflow=workflow,
            robot_profile=robot_profile,
            save_report=save_report,
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
