"""Read-only inspection of saved DentoCase bundles."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
import importlib
import sys
import uuid
from typing import Any

from .contracts import (
    Artifact,
    Branch,
    CaseInventory,
    CHECKPOINTS,
    CHECKPOINT_DEFINITION_VERSION,
    INVENTORY_SCHEMA_VERSION,
    LIVE_FRESHNESS,
)


_OWNER_DIR = Path(__file__).resolve().parents[1]
_OWNER_MODULE = "DENTOCaseBundle"
_LINEAGE_FDI = "DENTOBOT.LineageTargetFdiNumber"
_LINEAGE_SEGMENT = "DENTOBOT.LineageTargetSegmentID"
_REGISTRY_TARGET = "DENTOBOT.RegistryTargetID"
_REGISTRY_TRAJECTORY = "DENTOBOT.RegistryTrajectoryID"
_REGISTRY_BRANCH = "DENTOBOT.RegistryGuideSetID"


def _load_case_bundle_owner():
    module = sys.modules.get(_OWNER_MODULE)
    if module is not None:
        return module
    owner_dir = str(_OWNER_DIR)
    sys.path.insert(0, owner_dir)
    try:
        return importlib.import_module(_OWNER_MODULE)
    finally:
        if sys.path and sys.path[0] == owner_dir:
            sys.path.pop(0)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")
    result = value.strip()
    if not result and not allow_empty:
        raise ValueError(f"{name} must be a non-empty string.")
    return result


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings.")
    return tuple(_text(item, name) for item in value)


def _unique(values: tuple[str, ...], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must contain unique IDs.")


def _uuid_text(value: object, name: str) -> str:
    raw = _text(value, name)
    try:
        return str(uuid.UUID(raw))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUID.") from exc


def _saved_home_summary(workflow: dict[str, Any]) -> object:
    step6 = workflow.get("step6")
    home = step6.get("taskHome") if isinstance(step6, dict) else None
    if not isinstance(home, dict):
        return "Unknown"
    revision = home.get("revision")
    if type(revision) is not int or revision < 1:
        revision = "Unknown"
    status = home.get("runtime_validation_status")
    if status not in {"Validated", "Unreviewed"}:
        status = "Unknown"
    return {
        "revision": revision,
        "savedRuntimeValidationStatus": status,
        "freshness": "Unverified",
    }


def _explicit_inventory(raw: object) -> tuple[
    tuple[str, ...], tuple[Artifact, ...], tuple[Branch, ...], bool, tuple[str, ...]
]:
    if not isinstance(raw, dict):
        raise ValueError("checkpointInventory must be an object.")
    required = {
        "schemaVersion",
        "definitionVersion",
        "targetIds",
        "artifacts",
        "branches",
        "ownershipComplete",
        "unknownOwnership",
    }
    if required - raw.keys() or raw.keys() - required:
        raise ValueError("checkpointInventory fields are incomplete or unsupported.")
    if raw["schemaVersion"] != INVENTORY_SCHEMA_VERSION:
        raise ValueError("Unsupported checkpoint inventory schema version.")
    if raw["definitionVersion"] != CHECKPOINT_DEFINITION_VERSION:
        raise ValueError("Unsupported checkpoint definition version.")
    if type(raw["ownershipComplete"]) is not bool:
        raise ValueError("checkpointInventory.ownershipComplete must be a boolean.")

    target_ids = _string_list(raw["targetIds"], "checkpointInventory.targetIds")
    _unique(target_ids, "checkpointInventory.targetIds")
    if not isinstance(raw["artifacts"], list):
        raise ValueError("checkpointInventory.artifacts must be a list.")
    if not isinstance(raw["branches"], list):
        raise ValueError("checkpointInventory.branches must be a list.")
    unknown = list(_string_list(
        raw["unknownOwnership"], "checkpointInventory.unknownOwnership"
    ))
    _unique(tuple(unknown), "checkpointInventory.unknownOwnership")

    artifact_fields = {item.name for item in fields(Artifact)}
    required_artifact_fields = {"id", "checkpoint_id", "scope"}
    artifacts: list[Artifact] = []
    artifact_ids: list[str] = []
    checkpoint_by_id = {item.id: item for item in CHECKPOINTS}
    known_checkpoint_issue = False
    for index, item in enumerate(raw["artifacts"]):
        if not isinstance(item, dict) or required_artifact_fields - item.keys() or item.keys() - artifact_fields:
            raise ValueError(f"checkpointInventory.artifacts[{index}] has invalid fields.")
        record = dict(item)
        for name in ("id", "checkpoint_id", "scope"):
            record[name] = _text(record[name], f"artifact.{name}")
        for name in ("target_id", "branch_id", "state", "role", "reason"):
            if name in record:
                record[name] = _text(record[name], f"artifact.{name}", allow_empty=True)
        for name in ("dependencies", "trajectory_ids"):
            if name in record:
                record[name] = _string_list(record[name], f"artifact.{name}")
                _unique(record[name], f"artifact.{name}")
        if record["scope"] not in {"shared", "target", "branch"}:
            raise ValueError(f"checkpointInventory.artifacts[{index}].scope is invalid.")
        artifact_ids.append(record["id"])
        checkpoint = checkpoint_by_id.get(record["checkpoint_id"])
        if checkpoint is None:
            known_checkpoint_issue = True
            note = f"Unknown checkpoint ID: {record['checkpoint_id']}"
            if note not in unknown:
                unknown.append(note)
            record.setdefault("reason", note)
        elif record["scope"] != checkpoint.scope:
            known_checkpoint_issue = True
            note = f"Artifact {record['id']} scope conflicts with checkpoint {checkpoint.id}."
            if note not in unknown:
                unknown.append(note)
            record.setdefault("reason", note)
        target_id = record.get("target_id", "")
        branch_id = record.get("branch_id", "")
        if record["scope"] == "shared" and (target_id or branch_id):
            known_checkpoint_issue = True
            note = f"Shared artifact {record['id']} declares an owner."
            if note not in unknown:
                unknown.append(note)
            record.setdefault("reason", note)
        elif record["scope"] == "target" and target_id not in target_ids:
            known_checkpoint_issue = True
            note = f"Target owner is missing or unknown for artifact {record['id']}."
            if note not in unknown:
                unknown.append(note)
            record.setdefault("reason", note)
        elif record["scope"] == "branch" and not record.get("branch_id"):
            known_checkpoint_issue = True
            note = f"Branch owner is missing for artifact {record['id']}."
            if note not in unknown:
                unknown.append(note)
            record.setdefault("reason", note)
        artifacts.append(Artifact(**record))
    _unique(tuple(artifact_ids), "checkpointInventory.artifacts")

    branch_fields = {item.name for item in fields(Branch)}
    branches: list[Branch] = []
    branch_ids: list[str] = []
    for index, item in enumerate(raw["branches"]):
        required_branch_fields = {"id", "target_id", "trajectory_ids"}
        if not isinstance(item, dict) or required_branch_fields - item.keys() or item.keys() - branch_fields:
            raise ValueError(f"checkpointInventory.branches[{index}] has invalid fields.")
        record = dict(item)
        record["id"] = _text(record["id"], "branch.id")
        record["target_id"] = _text(record["target_id"], "branch.target_id", allow_empty=True)
        for name in ("pairing_intent", "state"):
            if name in record:
                record[name] = _text(record[name], f"branch.{name}", allow_empty=True)
        record["trajectory_ids"] = _string_list(
            record["trajectory_ids"], "branch.trajectory_ids"
        )
        _unique(record["trajectory_ids"], "branch.trajectory_ids")
        branch_ids.append(record["id"])
        if record["target_id"] not in target_ids:
            known_checkpoint_issue = True
            note = f"Target owner is missing or unknown for branch {record['id']}."
            if note not in unknown:
                unknown.append(note)
        branches.append(Branch(**record))
    _unique(tuple(branch_ids), "checkpointInventory.branches")
    branch_id_set = set(branch_ids)
    for artifact in artifacts:
        if artifact.scope == "branch" and artifact.branch_id not in branch_id_set:
            known_checkpoint_issue = True
            note = f"Branch owner is missing or unknown for artifact {artifact.id}."
            if note not in unknown:
                unknown.append(note)
            updated = artifact.reason or note
            artifacts[artifacts.index(artifact)] = replace(artifact, reason=updated)

    declared_complete = raw["ownershipComplete"]
    if not declared_complete and not unknown:
        unknown.append("Inventory declares checkpoint ownership incomplete.")
    ownership_complete = declared_complete and not unknown and not known_checkpoint_issue
    return target_ids, tuple(artifacts), tuple(branches), ownership_complete, tuple(unknown)


def _legacy_inventory(workflow: dict[str, Any]) -> tuple[
    tuple[str, ...], tuple[Artifact, ...], tuple[Branch, ...], tuple[str, ...]
]:
    unknown = ["Legacy package has no complete checkpoint ownership inventory"]
    step6 = workflow.get("step6")
    registry = step6.get("trajectoryRegistry") if isinstance(step6, dict) else None
    if not isinstance(registry, dict):
        registry = {}
        unknown.append("Saved trajectory registry is missing or invalid.")
    teeth = registry.get("teeth")
    if not isinstance(teeth, dict):
        teeth = {}
        unknown.append("Saved tooth registry is missing or invalid.")

    target_ids: set[str] = set()
    tooth_by_target: dict[str, tuple[str, dict[str, Any]]] = {}
    trajectory_target: dict[str, str] = {}
    conflicted_trajectory_ids: set[str] = set()
    trajectory_owner_branches: dict[str, set[str]] = {}
    for tooth_key, tooth in teeth.items():
        if not isinstance(tooth_key, str) or not isinstance(tooth, dict):
            unknown.append("A saved tooth registry entry is malformed.")
            continue
        target_id = tooth.get("target_id")
        segment_id = tooth.get("segment_id")
        target_id = target_id.strip() if isinstance(target_id, str) else ""
        segment_id = segment_id.strip() if isinstance(segment_id, str) else ""
        if target_id:
            target_ids.add(target_id)
            if target_id in tooth_by_target:
                unknown.append("Saved tooth registry has duplicate target IDs.")
            else:
                tooth_by_target[target_id] = (tooth_key, tooth)
        trajectory_set = tooth.get("trajectory_set")
        slots = trajectory_set.get("slots") if isinstance(trajectory_set, dict) else None
        if not isinstance(slots, list):
            if segment_id or target_id:
                unknown.append(f"Saved trajectory slots are missing for registry tooth {tooth_key}.")
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                unknown.append(f"A trajectory slot is malformed for registry tooth {tooth_key}.")
                continue
            trajectory_id = slot.get("trajectory_id")
            trajectory_id = trajectory_id.strip() if isinstance(trajectory_id, str) else ""
            slot_target = slot.get("target_id")
            slot_target = slot_target.strip() if isinstance(slot_target, str) else ""
            if not trajectory_id:
                continue
            owner_id = slot_target or target_id
            if owner_id:
                target_ids.add(owner_id)
                prior_owner = trajectory_target.get(trajectory_id)
                if prior_owner is not None and prior_owner != owner_id:
                    conflicted_trajectory_ids.add(trajectory_id)
                    trajectory_target.pop(trajectory_id, None)
                elif trajectory_id not in conflicted_trajectory_ids:
                    trajectory_target[trajectory_id] = owner_id
            else:
                unknown.append(f"Populated trajectory {trajectory_id} has no registry target ID.")

    raw_branches = registry.get("prepared_branches")
    if not isinstance(raw_branches, dict):
        raw_branches = {}
        unknown.append("Saved prepared-branch registry is missing or invalid.")
    branches: list[Branch] = []
    branch_by_id: dict[str, Branch] = {}
    branch_node_owners: dict[str, set[str]] = {}
    for branch_key, record in raw_branches.items():
        if not isinstance(branch_key, str) or not isinstance(record, dict):
            unknown.append("A saved prepared branch is malformed.")
            continue
        branch_id = record.get("branch_id")
        branch_id = branch_id.strip() if isinstance(branch_id, str) else ""
        if not branch_id:
            branch_id = branch_key.strip()
        if branch_id != branch_key:
            unknown.append("A prepared branch ID does not match its registry key.")
            continue
        trajectory_ids_raw = record.get("trajectory_ids", [])
        trajectory_ids = tuple(
            value.strip() for value in trajectory_ids_raw
            if isinstance(value, str) and value.strip()
        ) if isinstance(trajectory_ids_raw, list) else ()
        target_id = record.get("target_id")
        target_id = target_id.strip() if isinstance(target_id, str) else ""
        if not target_id:
            owners = {trajectory_target[value] for value in trajectory_ids if value in trajectory_target}
            if len(owners) == 1:
                target_id = next(iter(owners))
        if target_id and target_id not in target_ids:
            unknown.append(f"Prepared branch {branch_id} has an unknown target owner.")
        if not target_id:
            unknown.append(f"Prepared branch {branch_id} has no explicit target owner.")
        pairing = record.get("pairing_intent")
        if pairing not in {"Single", "ExplicitPair", "LegacyUnverified"}:
            pairing = "Unknown"
        state = record.get("state")
        if state not in {"Current", "Stale"}:
            state = "Unknown"
        branch = Branch(
            id=branch_id,
            target_id=target_id,
            trajectory_ids=trajectory_ids,
            pairing_intent=pairing,
            state=state,
        )
        branches.append(branch)
        branch_by_id[branch_id] = branch
        for field_name in (
            "target_docking_node_id",
            "insertion_direction_node_id",
            "template_node_id",
            "shell_node_id",
        ):
            node_id = record.get(field_name)
            if isinstance(node_id, str) and node_id.strip():
                branch_node_owners.setdefault(node_id.strip(), set()).add(branch_id)
        model_node_ids = record.get("model_node_ids", [])
        if isinstance(model_node_ids, list):
            for node_id in model_node_ids:
                if isinstance(node_id, str) and node_id.strip():
                    branch_node_owners.setdefault(node_id.strip(), set()).add(branch_id)
        else:
            unknown.append(f"Prepared branch {branch_id} has invalid model node references.")
        for trajectory_id in trajectory_ids:
            trajectory_owner_branches.setdefault(trajectory_id, set()).add(branch_id)

    checkpoint_by_role = {
        role: checkpoint
        for checkpoint in CHECKPOINTS
        for role in checkpoint.artifact_roles
    }
    raw_nodes = workflow.get("nodes")
    if not isinstance(raw_nodes, list):
        raw_nodes = []
        unknown.append("Legacy package has no valid workflow node inventory.")
    artifacts: list[Artifact] = []
    seen_artifact_ids: set[str] = set()
    for node in raw_nodes:
        if not isinstance(node, dict):
            unknown.append("A legacy workflow node record is malformed.")
            continue
        field_name = node.get("field")
        checkpoint = checkpoint_by_role.get(field_name) if isinstance(field_name, str) else None
        if checkpoint is None:
            continue
        node_id = node.get("id")
        node_id = node_id.strip() if isinstance(node_id, str) else ""
        if not node_id:
            unknown.append(f"Checkpoint field {field_name} has no persistent node ID.")
            continue
        if node_id in seen_artifact_ids:
            unknown.append(f"Checkpoint field {field_name} has a duplicate node ID.")
            continue
        seen_artifact_ids.add(node_id)
        attributes = node.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        target_candidates: set[str] = set()
        trajectory_id = attributes.get(_REGISTRY_TRAJECTORY)
        if isinstance(trajectory_id, str) and trajectory_id.strip():
            trajectory_id = trajectory_id.strip()
            target = (
                None if trajectory_id in conflicted_trajectory_ids
                else trajectory_target.get(trajectory_id)
            )
            if target:
                target_candidates.add(target)
            elif trajectory_id in conflicted_trajectory_ids:
                unknown.append(
                    f"Checkpoint field {field_name} has conflicting trajectory owners."
                )
            else:
                unknown.append(f"Checkpoint field {field_name} has an unregistered trajectory ID.")
        else:
            trajectory_id = ""
        registry_target = attributes.get(_REGISTRY_TARGET)
        if isinstance(registry_target, str) and registry_target.strip():
            registry_target = registry_target.strip()
            if registry_target in target_ids:
                target_candidates.add(registry_target)
            else:
                unknown.append(f"Checkpoint field {field_name} has an unregistered target ID.")
        for target_id in _lineage_targets(attributes, teeth, target_ids):
            target_candidates.add(target_id)
        if len(target_candidates) > 1:
            target_id = ""
            unknown.append(f"Checkpoint field {field_name} has conflicting registry owners.")
        else:
            target_id = next(iter(target_candidates), "")

        branch_candidates: set[str] = set()
        registry_branch = attributes.get(_REGISTRY_BRANCH)
        if isinstance(registry_branch, str) and registry_branch.strip():
            branch_candidates.add(registry_branch.strip())
        branch_candidates.update(branch_node_owners.get(node_id, set()))
        if trajectory_id and trajectory_id not in conflicted_trajectory_ids:
            branch_candidates.update(trajectory_owner_branches.get(trajectory_id, set()))
        branch_candidates.intersection_update(branch_by_id)
        if len(branch_candidates) > 1:
            branch_id = ""
            unknown.append(f"Checkpoint field {field_name} has ambiguous branch ownership.")
        else:
            branch_id = next(iter(branch_candidates), "")
        if branch_id and not target_id:
            target_id = branch_by_id[branch_id].target_id

        if checkpoint.scope == "target" and not target_id:
            unknown.append(f"Checkpoint field {field_name} has unknown target ownership.")
        if checkpoint.scope == "branch" and not branch_id:
            unknown.append(f"Checkpoint field {field_name} has unknown branch ownership.")
        state = attributes.get("DENTOBOT.VerificationState")
        if not isinstance(state, str) or not state.strip():
            state = attributes.get("DENTOBOT.GeometryState")
        if not isinstance(state, str) or not state.strip():
            state = "Unknown"
        artifacts.append(
            Artifact(
                id=node_id,
                checkpoint_id=checkpoint.id,
                scope=checkpoint.scope,
                target_id=target_id if checkpoint.scope != "shared" else "",
                branch_id=branch_id if checkpoint.scope == "branch" else "",
                state=state.strip(),
                role=field_name,
                trajectory_ids=(trajectory_id,) if trajectory_id else (
                    branch_by_id[branch_id].trajectory_ids if branch_id else ()
                ),
                reason=(
                    "Legacy ownership is incomplete."
                    if checkpoint.scope != "shared" and not (target_id if checkpoint.scope == "target" else branch_id)
                    else ""
                ),
            )
        )

    return (
        tuple(sorted(target_ids)),
        tuple(artifacts),
        tuple(sorted(branches, key=lambda item: item.id)),
        tuple(dict.fromkeys(unknown)),
    )


def _lineage_targets(
    attributes: dict[str, Any], teeth: dict[str, Any], target_ids: set[str]
) -> set[str]:
    fdi = attributes.get(_LINEAGE_FDI)
    segment_id = attributes.get(_LINEAGE_SEGMENT)
    fdi = fdi.strip().upper() if isinstance(fdi, str) else ""
    segment_id = segment_id.strip() if isinstance(segment_id, str) else ""
    if not fdi and not segment_id:
        return set()
    matches: set[str] = set()
    for tooth_key, tooth in teeth.items():
        if not isinstance(tooth_key, str) or not isinstance(tooth, dict):
            continue
        if fdi:
            key = tooth_key.upper()
            normalized = fdi[3:] if fdi.startswith("FDI") else fdi
            if key != fdi and key.removeprefix("FDI") != normalized:
                continue
        saved_segment = tooth.get("segment_id")
        if segment_id and saved_segment != segment_id:
            continue
        target_id = tooth.get("target_id")
        if isinstance(target_id, str) and target_id.strip() in target_ids:
            matches.add(target_id.strip())
    return matches


def _target_tooth_associations(workflow: dict[str, Any]) -> list[dict[str, str | bool]]:
    """Expose only populated, explicitly keyed saved registry tooth mappings."""

    step6 = workflow.get("step6")
    registry = step6.get("trajectoryRegistry") if isinstance(step6, dict) else None
    teeth = registry.get("teeth") if isinstance(registry, dict) else None
    if not isinstance(teeth, dict):
        return []
    target_fdis: dict[str, set[str]] = {}
    fallback_fdis: set[str] = set()
    for tooth_key, tooth in teeth.items():
        if not isinstance(tooth_key, str) or not isinstance(tooth, dict):
            continue
        fdi = tooth_key.upper().removeprefix("FDI")
        if len(fdi) != 2 or fdi[0] not in "1234" or fdi[1] not in "12345678":
            continue
        target_id = tooth.get("target_id")
        segment_id = tooth.get("segment_id")
        target_id = target_id.strip() if isinstance(target_id, str) else ""
        segment_id = segment_id.strip() if isinstance(segment_id, str) else ""
        if not target_id and not segment_id:
            continue
        if target_id:
            target_fdis.setdefault(target_id, set()).add(f"FDI{fdi}")
        else:
            fallback_fdis.add(f"FDI{fdi}")
    associations: list[dict[str, str | bool]] = [
        {
            "targetId": target_id,
            "fdi": next(iter(fdis)) if len(fdis) == 1 else "Unknown",
            "fallbackId": False,
        }
        for target_id, fdis in target_fdis.items()
    ]
    associations.extend(
        {"targetId": fdi, "fdi": fdi, "fallbackId": True}
        for fdi in fallback_fdis
    )
    return sorted(associations, key=lambda item: (item["fdi"], item["targetId"]))


def inspect_package(path: str | Path) -> CaseInventory:
    """Validate and summarize one package without loading its MRB geometry."""

    owner = _load_case_bundle_owner()
    try:
        package_path = Path(path).expanduser().resolve(strict=True)
        before = package_path.stat()
        if not package_path.is_file():
            raise ValueError("DentoCase path must be a regular file.")
        inspected = owner.validate_case_bundle(package_path)
        package_sha256 = owner.sha256_file(package_path)
        after = package_path.stat()
    except owner.CaseBundleError as exc:
        raise ValueError(str(exc) or "DentoCase archive validation failed.") from exc
    except OSError as exc:
        raise ValueError("DentoCase file could not be read.") from exc

    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ValueError("DentoCase file changed during inspection.")

    manifest = inspected.manifest
    workflow = inspected.workflow
    if not isinstance(manifest, dict) or not isinstance(workflow, dict):
        raise ValueError("DentoCase manifest and workflow must be objects.")
    package_id = _text(manifest.get("packageId"), "manifest.packageId")
    case_record = manifest.get("case")
    if case_record is not None and not isinstance(case_record, dict):
        raise ValueError("manifest.case must be an object.")
    manifest_case_id = None
    if isinstance(case_record, dict) and "id" in case_record:
        manifest_case_id = _uuid_text(case_record["id"], "manifest.case.id")
    case_identity = workflow.get("caseIdentity")
    if case_identity is not None:
        if not isinstance(case_identity, dict):
            raise ValueError("workflow.caseIdentity must be an object.")
        if "id" in case_identity:
            workflow_case_id = _uuid_text(
                case_identity["id"], "workflow.caseIdentity.id"
            )
            if manifest_case_id is None or workflow_case_id != manifest_case_id:
                raise ValueError("Manifest and workflow case IDs do not match.")
    legacy_identity = manifest_case_id is None
    case_id = (
        f"legacy:{package_id}:{package_sha256}"
        if legacy_identity
        else manifest_case_id
    )

    raw_label = case_record.get("label") if isinstance(case_record, dict) else None
    if not isinstance(raw_label, str) or not raw_label.strip():
        raw_label = workflow.get("caseLabel")
    label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else "Unknown"
    archive_schema = manifest.get("schemaVersion")
    archive_schema = archive_schema if isinstance(archive_schema, str) else "Unknown"
    raw_inventory = workflow.get("checkpointInventory")
    inventory_schema = None
    definition_version = CHECKPOINT_DEFINITION_VERSION
    if raw_inventory is None:
        target_ids, artifacts, branches, unknown_ownership = _legacy_inventory(workflow)
        ownership_complete = False
    else:
        if not isinstance(raw_inventory, dict):
            raise ValueError("checkpointInventory must be an object.")
        inventory_schema = _text(
            raw_inventory.get("schemaVersion"), "checkpointInventory.schemaVersion"
        )
        unsupported = []
        if inventory_schema != INVENTORY_SCHEMA_VERSION:
            unsupported.append(
                f"Unsupported checkpoint inventory schema version: {inventory_schema}."
            )
            raw_definition_version = raw_inventory.get("definitionVersion")
            definition_version = (
                raw_definition_version.strip()
                if isinstance(raw_definition_version, str)
                and raw_definition_version.strip()
                else "Unknown"
            )
        else:
            definition_version = _text(
                raw_inventory.get("definitionVersion"),
                "checkpointInventory.definitionVersion",
            )
            if definition_version != CHECKPOINT_DEFINITION_VERSION:
                unsupported.append(
                    f"Unsupported checkpoint definition version: {definition_version}."
                )
        if unsupported:
            target_ids, artifacts, branches, legacy_unknown = _legacy_inventory(workflow)
            unknown_ownership = tuple((*legacy_unknown, *unsupported))
            ownership_complete = False
        else:
            target_ids, artifacts, branches, ownership_complete, unknown_ownership = (
                _explicit_inventory(raw_inventory)
            )
    metadata = {
        "savedHome": _saved_home_summary(workflow),
        "historicalRecordCount": len(inspected.manual_simulation_records),
        "studyAttemptCount": len(inspected.study_attempts),
        "projectionValidity": "Unverified",
        "targetToothAssociations": _target_tooth_associations(workflow) + [
            dict(item) for item in workflow.get("reviewedTargets", [])
            if isinstance(item, dict) and isinstance(item.get("targetId"), str)
            and isinstance(item.get("fdi"), str)
        ],
    }
    if isinstance(workflow.get("projectionOwnership"), dict):
        metadata["projection"] = workflow["projectionOwnership"]
    if inventory_schema is not None:
        metadata["checkpointInventorySchemaVersion"] = inventory_schema
    return CaseInventory(
        path=str(package_path),
        package_id=package_id,
        case_id=case_id,
        label=label,
        archive_schema=archive_schema,
        package_sha256=package_sha256,
        checked_at_utc=_now_utc(),
        target_ids=target_ids,
        artifacts=artifacts,
        branches=branches,
        ownership_complete=ownership_complete,
        unknown_ownership=unknown_ownership,
        definition_version=definition_version,
        live_freshness=LIVE_FRESHNESS,
        legacy_identity=legacy_identity,
        historical_record_count=len(inspected.manual_simulation_records),
        stat_size=after.st_size,
        stat_mtime_ns=after.st_mtime_ns,
        metadata=metadata,
    )
