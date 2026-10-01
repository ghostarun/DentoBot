"""Build a conservative, serializable ownership view of the current MRML scene.

This module deliberately has no Slicer, Qt, VTK, or ROS imports at module load.
Only persisted nodes with an exact workflow role or an approved ownership link
are attributable to a partial-case checkpoint.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import json
from typing import Any

from dentobot_case.contracts import (
    Artifact,
    Branch,
    CHECKPOINT_DEFINITION_VERSION,
    CHECKPOINTS,
    INVENTORY_SCHEMA_VERSION,
)
from dentobot_case.ownership import DEFAULTS, NODE_FIELDS, PARAMETER_OWNERS, RESUME_INDICES


_CHECKPOINTS = {item.id: item for item in CHECKPOINTS}
_ORDER = {item.id: item.order for item in CHECKPOINTS}
_CHECKPOINT_FOR_FIELD = {
    field: owner for field, owner in PARAMETER_OWNERS.items()
    if owner in _CHECKPOINTS
}
_CHECKPOINT_FOR_FIELD.update({
    "inputVolume": "source.volume", "inspectedVolume": "source.volume",
    "roundTripVolume": "source.volume",
    "inspectedSegmentation": "anatomy.segmentation",
    "teethSegmentation": "anatomy.segmentation",
})
_CHECKPOINT_FOR_FIELD.update({
    "inputVolume": "source.volume", "inspectedVolume": "source.volume",
    "roundTripVolume": "source.volume",
    "inspectedSegmentation": "anatomy.segmentation",
    "teethSegmentation": "anatomy.segmentation",
})
_REGISTRY_SCHEMA = "3.0"
_UNIT_ATTRIBUTE = "DENTOBOT.CasePreparationUnitsJson"
_DISPLAY_CLASSES = {
    "vtkMRMLViewNode", "vtkMRMLCameraNode", "vtkMRMLSliceNode",
    "vtkMRMLSliceCompositeNode", "vtkMRMLLayoutNode",
    "vtkMRMLInteractionNode", "vtkMRMLSelectionNode",
    "vtkMRMLSubjectHierarchyNode", "vtkMRMLColorTableNode",
    "vtkMRMLProceduralColorNode", "vtkMRMLUnitNode",
}
_ROLE_ATTRIBUTES = (
    "DENTOBOT.ModelRole", "DENTOBOT.MarkupsRole", "DENTOBOT.TransformRole",
    "DENTOBOT.SegmentationRole", "DENTOBOT.DynamicModelerRole",
    "DENTOBOT.TrajectoryRole", "DENTOBOT.BoundsRole",
)

# The value maps are keyed by the exact persisted attribute and value.  The
# field is the canonical parameter-wrapper field when one exists; auxiliary
# nodes retain their exact semantic role.
_SEMANTIC_ROLES = {
    ("DENTOBOT.CaseScan", "true"): ("source.volume", "inputVolume"),
    ("DENTOBOT.TrajectoryRole", "EntryToTarget"): ("trajectory.plan", "trajectoryLine"),
    ("DENTOBOT.MarkupsRole", "AssistedTrajectoryEntries"): ("trajectory.plan", "assistedTrajectoryEntries"),
    ("DENTOBOT.BoundsRole", "TargetToothAABB"): ("trajectory.plan", "targetToothBoundsRoi"),
    ("DENTOBOT.MarkupsRole", "TargetDockingReferencePlane"): ("dock.assembly", "targetDockingReferencePlane"),
    ("DENTOBOT.ModelRole", "TemplateSupportDraft"): ("support.selection", "draftTemplateSupportModel"),
    ("DENTOBOT.ModelRole", "TargetDockingAssembly"): ("dock.assembly", "targetDockingAssemblyModel"),
    ("DENTOBOT.ModelRole", "PatientContactShell"): ("template.build", "patientContactShellModel"),
    ("DENTOBOT.ModelRole", "FinalPrintableTemplate"): ("template.build", "finalPrintableTemplateModel"),
    ("DENTOBOT.ModelRole", "TemplateDockingAssembly"): ("template.build", "templateDockingAssemblyModel"),
    ("DENTOBOT.ModelRole", "TemplateDockingClearance"): ("template.build", "templateDockingClearanceModel"),
    ("DENTOBOT.ModelRole", "TemplateDockingReinforcement"): ("template.build", "templateDockingReinforcementModel"),
    ("DENTOBOT.ModelRole", "TemplateDockingChannels"): ("template.build", "templateDockingChannelsModel"),
    ("DENTOBOT.ModelRole", "ResearchTemplateShell"): ("template.build", "researchTemplateShellModel"),
    ("DENTOBOT.ModelRole", "ResearchTemplateSleeve"): ("template.build", "researchTemplateSleeveModel"),
    ("DENTOBOT.ModelRole", "TemplateUndercutSurface"): ("template.build", "templateUndercutSurfaceModel"),
    ("DENTOBOT.ModelRole", "TemplateUndercutBlockout"): ("template.build", "templateUndercutBlockoutModel"),
    ("DENTOBOT.ModelRole", "RobotForeheadProxy"): ("foundation.base", "robotForeheadProxyModel"),
    ("DENTOBOT.ModelRole", "Step6OpenedLowerJaw"): ("foundation.pose", "step6OpenedLowerJawModel"),
    ("DENTOBOT.ModelRole", "Step6OpenedTargetGeometry"): ("trajectory.plan", "step6OpenedTargetGeometryModel"),
    ("DENTOBOT.ModelRole", "Step6OpenedTrajectory"): ("trajectory.plan", "step6OpenedTrajectoryLine"),
    ("DENTOBOT.ModelRole", "RobotLink"): ("@runtime", ""),
    ("DENTOBOT.ModelRole", "RobotWorkspaceCloud"): ("@runtime", ""),
    ("DENTOBOT.MarkupsRole", "RobotMountPlane"): ("foundation.base", "robotMountPlane"),
    ("DENTOBOT.MarkupsRole", "Step6CaseJawLandmarks"): ("foundation.pose", "step6CaseJawLandmarks"),
    ("DENTOBOT.MarkupsRole", "Step6CaseJawGapLine"): ("foundation.pose", "step6CaseJawGapLine"),
    ("DENTOBOT.MarkupsRole", "TemplateSupportBoundary"): ("support.surface", "templateSupportBoundaryCurve"),
    ("DENTOBOT.MarkupsRole", "TemplateSupportBoundaryPlane"): ("support.surface", "templateSupportBoundaryPlane"),
    ("DENTOBOT.MarkupsRole", "TemplateInsertionDirection"): ("support.surface", "templateInsertionDirection"),
    ("DENTOBOT.MarkupsRole", "TemplateShellTrimROI"): ("template.build", "templateShellRoi"),
    ("DENTOBOT.MarkupsRole", "TemplateFinalizationPlane"): ("template.verify", "templateTrimPlane"),
    ("DENTOBOT.MarkupsRole", "TemplateFinalizationCurve"): ("template.verify", "templateTrimCurve"),
    ("DENTOBOT.TransformRole", "RobotBase"): ("foundation.base", "robotBaseTransform"),
    ("DENTOBOT.TransformRole", "RobotLinkPose"): ("@runtime", ""),
    ("DENTOBOT.TransformRole", "Step6CaseJawTransform"): ("foundation.pose", "step6CaseJawTransform"),
    ("DENTOBOT.SegmentationRole", "Step6FixedUpperAnatomy"): ("foundation.pose", "step6FixedUpperAnatomy"),
    ("DENTOBOT.SegmentationRole", "Step6MovingLowerAnatomy"): ("foundation.pose", "step6MovingLowerAnatomy"),
    ("DENTOBOT.SegmentationRole", "Step6TargetJawFallbackAnatomy"): ("foundation.pose", "step6TargetJawFallbackAnatomy"),
    ("DENTOBOT.ModelRole", "VisibleTemplateSupportSurface"): ("support.surface", "visibleTemplateSupportModel"),
    ("DENTOBOT.ModelRole", "FinalizedTemplateShell"): ("template.verify", "finalizedTemplateShellModel"),
}

_BRANCH_REFERENCE_ROLES = {
    "DENTOBOT.FinalGuidePatientShell", "DENTOBOT.FinalGuideSourceTrajectory",
    "DENTOBOT.FinalGuideTargetDockingAssembly", "DENTOBOT.FinalGuideDockingAssembly",
    "DENTOBOT.FinalGuideDockingClearance", "DENTOBOT.FinalGuideReinforcement",
    "DENTOBOT.FinalGuideChannels", "DENTOBOT.PatientShellSourceAnatomy",
    "DENTOBOT.PatientShellBoundaryBridge", "DENTOBOT.PatientShellFittingSurface",
    "DENTOBOT.PatientShellHollowCandidate", "DENTOBOT.PatientShellHollowDynamicModeler",
    "DENTOBOT.PatientShellMarginDynamicModeler",
}
_AUXILIARY_OWNER_ROLES = {
    ("DENTOBOT.MarkupsRole", "TargetDockingMeasurement"): ("DENTOBOT.OwnerAssemblyNodeID", "dock.assembly"),
    ("DENTOBOT.ModelRole", "TemplateFittingSurface"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.build"),
    ("DENTOBOT.ModelRole", "TemplateHollowCandidate"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.build"),
    ("DENTOBOT.ModelRole", "TemplateSupportBoundaryBridge"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.build"),
    ("DENTOBOT.DynamicModelerRole", "PatientContactFitMargin"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.build"),
    ("DENTOBOT.DynamicModelerRole", "PatientContactHollow"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.build"),
    ("DENTOBOT.DynamicModelerRole", "TemplateFinalizationCut"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.verify"),
    ("DENTOBOT.ModelRole", "TemplateFinalizationCutAuxiliary"): ("DENTOBOT.AuxiliaryOwnerNodeID", "template.verify"),
}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _attr(node: object, name: str) -> str:
    getter = getattr(node, "GetAttribute", None)
    try:
        return _text(getter(name)) if getter else ""
    except (RuntimeError, TypeError):
        return ""


def _values(method: object) -> list[str] | None:
    """Read a returned iterable or a native C++ vector output argument."""
    if not callable(method):
        return None
    try:
        result = method()
    except TypeError:
        output: list[str] = []
        try:
            method(output)
            return [_text(value) for value in output]
        except (TypeError, RuntimeError):
            return None
    if result is not None:
        try:
            return [_text(value) for value in result]
        except TypeError:
            return None
    return None


def _node_references(node: object) -> dict[str, list[str]]:
    roles = _values(getattr(node, "GetNodeReferenceRoles", None)) or []
    result: dict[str, list[str]] = {}
    for role in roles:
        if not role:
            continue
        count_getter = getattr(node, "GetNumberOfNodeReferences", None)
        id_getter = getattr(node, "GetNthNodeReferenceID", None)
        ids: list[str] = []
        if callable(count_getter) and callable(id_getter):
            try:
                ids = [_text(id_getter(role, index)) for index in range(count_getter(role))]
            except (RuntimeError, TypeError):
                ids = []
        if not ids:
            getter = getattr(node, "GetNodeReferenceID", None)
            if callable(getter):
                try:
                    value = _text(getter(role))
                    ids = [value] if value else []
                except (RuntimeError, TypeError):
                    pass
        result[role] = list(dict.fromkeys(value for value in ids if value))
    return result


def _saved_nodes(scene: object) -> list[object]:
    count = int(scene.GetNumberOfNodes())
    result = []
    for index in range(count):
        node = scene.GetNthNode(index)
        if node is None:
            continue
        try:
            if node.GetSaveWithScene():
                result.append(node)
        except (AttributeError, RuntimeError, TypeError):
            continue
    return result


def _is_a(node: object, class_name: str) -> bool:
    checker = getattr(node, "IsA", None)
    if callable(checker):
        try:
            return bool(checker(class_name))
        except (RuntimeError, TypeError):
            return False
    return getattr(node, "GetClassName", lambda: "")() == class_name


def _class_name(node: object) -> str:
    getter = getattr(node, "GetClassName", None)
    try:
        return _text(getter()) if getter else ""
    except (RuntimeError, TypeError):
        return ""


def _linked_nodes(node: object) -> list[str]:
    ids: list[str] = []
    for getter_name, id_name in (("GetDisplayNode", "GetDisplayNodeID"),
                                 ("GetStorageNode", "GetStorageNodeID")):
        getter = getattr(node, getter_name, None)
        linked = None
        if callable(getter):
            try:
                linked = getter()
            except (RuntimeError, TypeError):
                pass
        if linked is not None:
            try:
                value = _text(linked.GetID())
                if value:
                    ids.append(value)
            except (AttributeError, RuntimeError, TypeError):
                pass
        id_getter = getattr(node, id_name, None)
        if callable(id_getter):
            try:
                value = _text(id_getter())
                if value:
                    ids.append(value)
            except (RuntimeError, TypeError):
                pass
    for role in ("display", "storage"):
        refs = _node_references(node).get(role, ())
        ids.extend(refs)
    return list(dict.fromkeys(ids))


def _scene_identity(node: object) -> str:
    try:
        return _text(node.GetID())
    except (AttributeError, RuntimeError, TypeError):
        return ""


def _registry_data(workflow_summary: object, unknown: list[str]) -> dict[str, Any]:
    targets: dict[str, dict[str, str]] = {}
    trajectories: dict[str, dict[str, str]] = {}
    node_trajectories: dict[str, str] = {}
    branches: dict[str, Branch] = {}
    branch_primary: dict[str, str] = {}
    branch_models: dict[str, list[str]] = defaultdict(list)
    selected = ""
    step6 = workflow_summary.get("step6") if isinstance(workflow_summary, dict) else None
    registry = step6.get("trajectoryRegistry") if isinstance(step6, dict) else None
    if registry is not None:
        if not isinstance(registry, dict) or registry.get("schema_version") != _REGISTRY_SCHEMA:
            unknown.append("trajectory registry is malformed or has an unsupported schema")
        else:
            teeth = registry.get("teeth")
            branch_records = registry.get("prepared_branches")
            if not isinstance(teeth, dict) or not isinstance(branch_records, dict):
                unknown.append("trajectory registry teeth or prepared branches are malformed")
            else:
                for fdi_key, tooth in teeth.items():
                    if not isinstance(tooth, dict):
                        unknown.append(f"trajectory registry tooth is malformed: {fdi_key}")
                        continue
                    target_id = _text(tooth.get("target_id"))
                    segment_id = _text(tooth.get("segment_id"))
                    if target_id:
                        if target_id in targets and targets[target_id] != {
                            "fdi": _text(fdi_key[3:] if fdi_key.startswith("FDI") else ""),
                            "segmentId": segment_id,
                        }:
                            unknown.append(f"registry target identity conflicts: {target_id}")
                        else:
                            targets[target_id] = {
                                "fdi": _text(fdi_key[3:] if fdi_key.startswith("FDI") else ""),
                                "segmentId": segment_id,
                            }
                    trajectory_set = tooth.get("trajectory_set")
                    slots = trajectory_set.get("slots") if isinstance(trajectory_set, dict) else None
                    if not isinstance(slots, list):
                        unknown.append(f"trajectory registry slots are malformed: {fdi_key}")
                        continue
                    for slot in slots:
                        if not isinstance(slot, dict):
                            unknown.append(f"trajectory registry slot is malformed: {fdi_key}")
                            continue
                        trajectory_id = _text(slot.get("trajectory_id"))
                        if not trajectory_id:
                            continue
                        owner_target = _text(slot.get("target_id")) or target_id
                        state = _text(slot.get("state")) or "Unknown"
                        node_id = _text(slot.get("trajectory_node_id"))
                        if not owner_target or (target_id and owner_target != target_id):
                            unknown.append(f"trajectory target association conflicts: {trajectory_id}")
                        if trajectory_id in trajectories:
                            unknown.append(f"duplicate registry trajectory identity: {trajectory_id}")
                        trajectories[trajectory_id] = {"target_id": owner_target, "state": state, "node_id": node_id}
                        if node_id:
                            if node_id in node_trajectories and node_trajectories[node_id] != trajectory_id:
                                unknown.append(f"node maps to multiple trajectories: {node_id}")
                            node_trajectories[node_id] = trajectory_id

                for branch_id, record in branch_records.items():
                    if not isinstance(record, dict) or not isinstance(branch_id, str) or not branch_id:
                        unknown.append("prepared branch registry contains an invalid identity")
                        continue
                    target_id = _text(record.get("target_id"))
                    trajectory_ids = record.get("trajectory_ids")
                    intent = _text(record.get("pairing_intent"))
                    state = _text(record.get("state")) or "Unknown"
                    if (not target_id or not isinstance(trajectory_ids, list)
                            or any(not isinstance(item, str) or not item.strip() for item in trajectory_ids)):
                        unknown.append(f"prepared branch is malformed: {branch_id}")
                        continue
                    members = tuple(_text(item) for item in trajectory_ids)
                    branches[branch_id] = Branch(branch_id, target_id, members, intent, state)
                    primary = _text(record.get("primary_trajectory_id"))
                    if primary:
                        branch_primary[branch_id] = primary
                    model_ids = record.get("model_node_ids", [])
                    if not isinstance(model_ids, list) or any(not isinstance(item, str) for item in model_ids):
                        unknown.append(f"prepared branch model node list is malformed: {branch_id}")
                    else:
                        branch_models[branch_id].extend(item for item in model_ids if item)
                    if target_id not in targets:
                        unknown.append(f"prepared branch has unknown target: {branch_id}")
                    for trajectory_id in members:
                        owner = trajectories.get(trajectory_id)
                        if owner is None or owner["target_id"] != target_id:
                            unknown.append(f"prepared branch trajectory ownership conflicts: {branch_id}/{trajectory_id}")
                    if intent not in {"Single", "ExplicitPair", "LegacyUnverified"}:
                        unknown.append(f"prepared branch pairing intent is unknown: {branch_id}")
                    if not members or len(members) != len(set(members)):
                        unknown.append(f"prepared branch trajectory membership is invalid: {branch_id}")
                selected = _text(registry.get("selected_branch_id"))
                if selected and selected not in branches:
                    unknown.append(f"selected registry branch is unknown: {selected}")

    reviewed = workflow_summary.get("reviewedTargets", []) if isinstance(workflow_summary, dict) else []
    if reviewed is not None:
        if not isinstance(reviewed, list):
            unknown.append("reviewed target summary is malformed")
        else:
            for record in reviewed:
                if not isinstance(record, dict):
                    unknown.append("reviewed target entry is malformed")
                    continue
                target_id = _text(record.get("targetId"))
                fdi = _text(record.get("fdi"))
                segment_id = _text(record.get("segmentId"))
                if not target_id or not fdi or not segment_id:
                    unknown.append("reviewed target entry is missing its semantic identity")
                    continue
                association = {"fdi": fdi, "segmentId": segment_id}
                if target_id in targets and targets[target_id] != association:
                    unknown.append(f"reviewed and registry target associations conflict: {target_id}")
                else:
                    targets[target_id] = association

    by_segment: dict[str, set[str]] = defaultdict(set)
    by_fdi: dict[str, set[str]] = defaultdict(set)
    for target_id, association in targets.items():
        if association["segmentId"]:
            by_segment[association["segmentId"]].add(target_id)
        if association["fdi"]:
            by_fdi[association["fdi"]].add(target_id)

    return {
        "targets": targets, "by_segment": by_segment, "by_fdi": by_fdi,
        "trajectories": trajectories, "node_trajectories": node_trajectories,
        "branches": branches, "branch_primary": branch_primary,
        "branch_models": branch_models, "selected": selected,
    }


def _preparation_units(raw: object, data: dict[str, Any], unknown: list[str]) -> None:
    payload = _attr(raw, _UNIT_ATTRIBUTE)
    if not payload:
        return
    try:
        value = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        unknown.append("case preparation units JSON is malformed")
        return
    if not isinstance(value, dict) or set(value) != {"version", "branches"} or value.get("version") != "1.0" or not isinstance(value.get("branches"), list):
        unknown.append("case preparation units have an unsupported version or shape")
        return
    supplied: dict[str, Branch] = {}
    for record in value["branches"]:
        if not isinstance(record, dict) or set(record) != {"id", "target_id", "trajectory_ids", "pairing_intent", "state"}:
            unknown.append("case preparation unit branch has an unsupported shape")
            continue
        branch_id = _text(record.get("id"))
        target_id = _text(record.get("target_id"))
        member_values = record.get("trajectory_ids")
        intent = _text(record.get("pairing_intent"))
        state = _text(record.get("state"))
        if (not branch_id or not target_id or not isinstance(member_values, list)
                or any(not isinstance(item, str) or not item.strip() for item in member_values) or not state):
            unknown.append("case preparation unit branch has invalid identity or state")
            continue
        members = tuple(_text(item) for item in member_values)
        branch = Branch(branch_id, target_id, members, intent, state)
        if branch_id in supplied:
            unknown.append(f"duplicate case preparation unit branch: {branch_id}")
            continue
        supplied[branch_id] = branch
        if target_id not in data["targets"]:
            unknown.append(f"case preparation unit has unknown target: {branch_id}")
        if (not members or len(members) != len(set(members))
                or any(data["trajectories"].get(item, {}).get("target_id") != target_id for item in members)):
            unknown.append(f"case preparation unit trajectory membership conflicts: {branch_id}")
        if intent not in {"Single", "ExplicitPair", "LegacyUnverified"}:
            unknown.append(f"case preparation unit pairing intent is unknown: {branch_id}")
        if (intent == "Single" and len(members) != 1) or (intent == "ExplicitPair" and len(members) != 2):
            unknown.append(f"case preparation unit pairing shape conflicts: {branch_id}")

    for branch_id, branch in supplied.items():
        registered = data["branches"].get(branch_id)
        if registered is not None:
            if (registered.target_id, registered.trajectory_ids, registered.pairing_intent) != (
                    branch.target_id, branch.trajectory_ids, branch.pairing_intent):
                unknown.append(f"registry and preparation unit identities conflict: {branch_id}")
            # The registry is current saved evidence for state; never promote it from the unit record.
            continue
        data["branches"][branch_id] = branch


def _all_registry_branches(data: dict[str, Any], unknown: list[str]) -> None:
    covered = {trajectory_id for branch in data["branches"].values() for trajectory_id in branch.trajectory_ids}
    for trajectory_id, item in sorted(data["trajectories"].items()):
        if trajectory_id in covered:
            continue
        branch_id = "trajectory:" + trajectory_id
        if branch_id in data["branches"]:
            unknown.append(f"synthetic trajectory branch identity collides: {branch_id}")
            continue
        data["branches"][branch_id] = Branch(
            branch_id, item["target_id"], (trajectory_id,), "Single", item["state"]
        )


def _semantic_candidates(node: object, unknown: list[str]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for attribute in _ROLE_ATTRIBUTES:
        value = _attr(node, attribute)
        if not value:
            continue
        candidate = _SEMANTIC_ROLES.get((attribute, value))
        if candidate is None:
            if (attribute, value) in _AUXILIARY_OWNER_ROLES:
                continue
            # Robot roles are runtime evidence, not reusable saved geometry.
            if (attribute, value) in {
                ("DENTOBOT.ModelRole", "RobotLink"),
                ("DENTOBOT.ModelRole", "RobotWorkspaceCloud"),
                ("DENTOBOT.TransformRole", "RobotLinkPose"),
            }:
                continue
            unknown.append(f"unmapped persistent semantic role {attribute}={value} on {_scene_identity(node) or '<no-id>'}")
            continue
        checkpoint_id, role = candidate
        if checkpoint_id == "@runtime":
            continue
        else:
            candidates.append((checkpoint_id, role))
    if _attr(node, "DENTOBOT.CaseScan").casefold() == "true" and not _is_a(node, "vtkMRMLScalarVolumeNode"):
        unknown.append(f"CaseScan marker is on a non-volume node: {_scene_identity(node) or '<no-id>'}")
    if _is_a(node, "vtkMRMLScalarVolumeNode") and _attr(node, "DENTOBOT.CaseScan").casefold() == "true":
        candidates.append(("source.volume", "inputVolume"))
    return candidates


def _special_node_owner(node: object) -> str:
    class_name = _class_name(node)
    if class_name in _DISPLAY_CLASSES or class_name == "vtkMRMLCrosshairNode":
        return "@display"
    if class_name == "vtkMRMLScriptedModuleNode":
        module_name = _text(getattr(node, "GetModuleName", lambda: "")())
        singleton_tag = _text(getattr(node, "GetSingletonTag", lambda: "")())
        if singleton_tag in {"DataProbe", "Units"} and module_name in {"", singleton_tag}:
            return "@display"
        return ""
    if _is_a(node, "vtkMRMLDisplayNode"):
        return "@display"
    role_values = {_attr(node, name) for name in _ROLE_ATTRIBUTES}
    if role_values & {"RobotLink", "RobotLinkPose", "RobotWorkspaceCloud"}:
        return "@runtime"
    if class_name.startswith("vtkMRMLROS"):
        return "@runtime"
    return ""


def _read_parameter_names(raw: object) -> list[str] | None:
    return _values(getattr(raw, "GetParameterNames", None))


def _target_claims(node: object, data: dict[str, Any], unknown: list[str]) -> set[str]:
    claims: set[str] = set()
    explicit = _attr(node, "DENTOBOT.RegistryTargetID")
    if explicit:
        if explicit not in data["targets"]:
            unknown.append(f"node has unregistered target claim {explicit}: {_scene_identity(node)}")
        else:
            claims.add(explicit)
    segment = _attr(node, "DENTOBOT.LineageTargetSegmentID")
    if segment:
        matches = data["by_segment"].get(segment, set())
        if len(matches) == 1:
            claims.update(matches)
        else:
            unknown.append(f"lineage segment does not resolve uniquely to a reviewed registry target on {_scene_identity(node)}")
    fdi = _attr(node, "DENTOBOT.LineageTargetFdiNumber")
    if fdi:
        matches = data["by_fdi"].get(fdi, set())
        if len(matches) == 1:
            claims.update(matches)
        else:
            unknown.append(f"lineage FDI does not resolve uniquely to a reviewed registry target on {_scene_identity(node)}")
    trajectory_id = _attr(node, "DENTOBOT.RegistryTrajectoryID")
    if not trajectory_id:
        trajectory_id = data["node_trajectories"].get(_scene_identity(node), "")
    if trajectory_id:
        trajectory = data["trajectories"].get(trajectory_id)
        if trajectory is None:
            unknown.append(f"node has unregistered trajectory claim {trajectory_id}: {_scene_identity(node)}")
        elif trajectory["target_id"]:
            claims.add(trajectory["target_id"])
    return claims


def _branch_claims(node: object, data: dict[str, Any], unknown: list[str]) -> set[str]:
    claims: set[str] = set()
    explicit = _attr(node, "DENTOBOT.RegistryGuideSetID")
    if explicit:
        if explicit not in data["branches"]:
            unknown.append(f"node has unregistered branch claim {explicit}: {_scene_identity(node)}")
        else:
            claims.add(explicit)
    node_id = _scene_identity(node)
    for branch_id, model_ids in data["branch_models"].items():
        if node_id and node_id in model_ids:
            claims.add(branch_id)
    if len(claims) > 1:
        unknown.append(f"node has conflicting registered branch claims: {node_id}")
    return claims


def _canonical_role(candidates: list[tuple[str, str]]) -> tuple[str, str] | None:
    unique = set(candidates)
    if not unique:
        return None
    if len({checkpoint for checkpoint, _role in unique}) != 1:
        return None
    checkpoint = next(iter(unique))[0]
    roles = {role for _checkpoint, role in unique if role}
    # Same-node wrapper aliases that describe one shared input have one fixed authority.
    if checkpoint == "source.volume" and roles <= {"inputVolume", "inspectedVolume"}:
        return checkpoint, "inputVolume"
    if checkpoint == "anatomy.segmentation" and roles <= {"teethSegmentation", "inspectedSegmentation"}:
        return checkpoint, "teethSegmentation"
    if len(roles) == 1:
        return checkpoint, next(iter(roles))
    return (checkpoint, next(iter(roles))) if len(roles) == 1 else None


def _configuration_artifacts(parameter_wrapper: object, data: dict[str, Any], unknown: list[str]) -> list[Artifact]:
    result: list[Artifact] = []
    for field, checkpoint, role in (
        ("step6TaskHomeJson", "simulation.home", "step6TaskHomeJson"),
        ("step6AssistedLimitProposalJson", "simulation.workspace", "step6AssistedLimitProposalJson"),
    ):
        payload = _text(getattr(parameter_wrapper, field, ""))
        if not payload:
            continue
        try:
            value = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            unknown.append(f"nonempty {field} payload is malformed")
            continue
        if not isinstance(value, dict):
            unknown.append(f"nonempty {field} payload is not an object")
            continue
        if field == "step6TaskHomeJson":
            state = _text(value.get("runtime_validation_status")) or "Unreviewed"
        else:
            reviewed = value.get("reviewed", False)
            if type(reviewed) is not bool:
                unknown.append("nonempty step6AssistedLimitProposalJson has an invalid reviewed flag")
                continue
            state = "Reviewed" if reviewed else "Unreviewed"
        if not data["targets"]:
            unknown.append(f"nonempty {field} has no explicit reviewed inventory target")
            continue
        for target_id in sorted(data["targets"]):
            result.append(Artifact(
                f"parameter:{field}:{target_id}", checkpoint, "target", target_id,
                state=state, role=role,
                reason="Saved case/base configuration; live freshness unverified",
            ))
    return result


def capture_inventory(parameter_wrapper: object, scene: object, workflow_summary: object) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the exact inventory and projection payloads for saved scene state."""
    unknown: list[str] = []
    raw = getattr(parameter_wrapper, "parameterNode", None)
    if raw is None:
        unknown.append("workflow parameter wrapper has no raw parameterNode")
    nodes = _saved_nodes(scene)
    by_id = {node_id: node for node in nodes if (node_id := _scene_identity(node))}
    if len(by_id) != len(nodes):
        unknown.append("saved scene has a node without a stable MRML ID")
    for node_id, node in by_id.items():
        if _values(getattr(node, "GetNodeReferenceRoles", None)) is None:
            unknown.append(f"saved node reference roles could not be audited: {node_id}")
    parameter_id = _scene_identity(raw) if raw is not None else ""
    if not parameter_id or parameter_id not in by_id:
        unknown.append("raw workflow parameter node is not present among saved scene nodes")

    data = _registry_data(workflow_summary, unknown)
    if raw is not None:
        _preparation_units(raw, data, unknown)
    _all_registry_branches(data, unknown)

    raw_names = _read_parameter_names(raw) if raw is not None else None
    parameter_owners: dict[str, str] = {}
    defaults: dict[str, str] = {}
    if raw_names is None:
        unknown.append("raw parameter node did not expose persistent parameter names")
    else:
        for name in sorted(set(raw_names)):
            if not name:
                continue
            if name in NODE_FIELDS:
                getter = getattr(raw, "GetParameter", None)
                try:
                    value = getter(name) if callable(getter) else None
                except (RuntimeError, TypeError):
                    value = None
                if value is None:
                    unknown.append(f"node field parameter did not expose its blank serializer sentinel: {name}")
                elif not isinstance(value, str) or value != "":
                    unknown.append(f"node field parameter has unexpected scalar payload: {name}")
                continue
            owner = PARAMETER_OWNERS.get(name)
            if owner is None:
                unknown.append(f"unmapped persistent parameter: {name}")
                continue
            parameter_owners[name] = owner
            if name in DEFAULTS:
                defaults[name] = DEFAULTS[name]

    reference_owners: dict[str, str] = {}
    field_nodes: dict[str, list[str]] = defaultdict(list)
    if raw is not None:
        for role, ref_ids in _node_references(raw).items():
            owner = PARAMETER_OWNERS.get(role)
            if role == "DENTOBOT.SelectedGuideTrajectory":
                owner = "trajectory.plan"
            if owner is None:
                unknown.append(f"unmapped persistent parameter reference role: {role}")
                continue
            reference_owners[role] = owner
            if role in NODE_FIELDS:
                field_nodes[role].extend(ref_ids)
            for node_id in ref_ids:
                if node_id not in by_id:
                    unknown.append(f"parameter reference points to a node not saved with scene: {role}/{node_id}")
                elif role == "DENTOBOT.SelectedGuideTrajectory":
                    field_nodes[role].append(node_id)

    candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for field, node_ids in field_nodes.items():
        checkpoint = _CHECKPOINT_FOR_FIELD.get(field)
        if checkpoint:
            for node_id in node_ids:
                candidates[node_id].append((checkpoint, field))
        elif field == "DENTOBOT.SelectedGuideTrajectory":
            for node_id in node_ids:
                candidates[node_id].append(("trajectory.plan", "trajectoryLine"))
    for node_id, node in by_id.items():
        candidates[node_id].extend(_semantic_candidates(node, unknown))

    target_claims: dict[str, set[str]] = {}
    branch_claims: dict[str, set[str]] = {}
    for node_id, node in by_id.items():
        target_claims[node_id] = _target_claims(node, data, unknown)
        branch_claims[node_id] = _branch_claims(node, data, unknown)
        trajectory_id = _attr(node, "DENTOBOT.RegistryTrajectoryID") or data["node_trajectories"].get(node_id, "")
        if trajectory_id and trajectory_id in data["trajectories"]:
            target_claims[node_id].add(data["trajectories"][trajectory_id]["target_id"])
    for node_id, node in by_id.items():
        owner_id = _attr(node, "DENTOBOT.AuxiliaryOwnerNodeID") or _attr(node, "DENTOBOT.OwnerAssemblyNodeID")
        if owner_id:
            if owner_id not in by_id:
                unknown.append(f"saved auxiliary owner is missing: {node_id}->{owner_id}")
                continue
            target_claims[node_id].update(target_claims[owner_id])
            branch_claims[node_id].update(branch_claims[owner_id])

    # Exact owned references propagate a known branch backwards to referenced
    # branch geometry; they never invent checkpoint roles or branch ownership
    # for shared anatomy or target-scope trajectories.
    for _ in range(max(1, len(by_id))):
        changed = False
        for parent_id, parent in by_id.items():
            parent_branches = branch_claims[parent_id]
            if len(parent_branches) != 1:
                continue
            branch_id = next(iter(parent_branches))
            branch = data["branches"].get(branch_id)
            if branch is None:
                continue
            for role, child_ids in _node_references(parent).items():
                if role not in _BRANCH_REFERENCE_ROLES:
                    continue
                for child_id in child_ids:
                    if child_id not in by_id:
                        unknown.append(f"branch geometry reference points outside the saved scene: {role}/{child_id}")
                        continue
                    child_candidate = _canonical_role(candidates[child_id])
                    child_scope = _CHECKPOINTS[child_candidate[0]].scope if child_candidate and child_candidate[0] in _CHECKPOINTS else ""
                    if child_scope == "shared":
                        continue
                    if child_scope == "target":
                        target_claims[child_id].add(branch.target_id)
                        continue
                    if child_scope == "branch" and branch_id not in branch_claims[child_id]:
                        branch_claims[child_id].add(branch_id)
                        target_claims[child_id].add(branch.target_id)
                        changed = True
        if not changed:
            break

    # Resolve the globally selected registry unit only for actual global
    # parameter-wrapper references, never for historical scene candidates.
    selected_branch = data["branches"].get(data["selected"])
    for node_id in by_id:
        global_ref = any(node_id in values for values in field_nodes.values())
        if not global_ref or selected_branch is None:
            continue
        candidate = _canonical_role(candidates[node_id])
        if candidate is None or candidate[0] not in _CHECKPOINTS:
            continue
        checkpoint_scope = _CHECKPOINTS[candidate[0]].scope
        if checkpoint_scope == "shared":
            continue
        target_claims[node_id].add(selected_branch.target_id)
        if checkpoint_scope == "branch":
            branch_claims[node_id].add(selected_branch.id)
        if candidate == ("trajectory.plan", "trajectoryLine"):
            primary = data["branch_primary"].get(selected_branch.id)
            if not primary and len(selected_branch.trajectory_ids) == 1:
                primary = selected_branch.trajectory_ids[0]
            if primary and primary in data["trajectories"]:
                node_trajectory = data["node_trajectories"].get(node_id)
                if not node_trajectory or node_trajectory == primary:
                    # The selected line is global workflow state; the registry
                    # primary ID is its only accepted fallback association.
                    data["node_trajectories"][node_id] = primary

    # An exact auxiliary owner may itself be a global wrapper reference; inherit
    # its resolved unit only after the selected registry fallback is applied.
    for node_id, node in by_id.items():
        owner_id = _attr(node, "DENTOBOT.AuxiliaryOwnerNodeID") or _attr(node, "DENTOBOT.OwnerAssemblyNodeID")
        if owner_id in by_id:
            target_claims[node_id].update(target_claims[owner_id])
            branch_claims[node_id].update(branch_claims[owner_id])

    artifact_by_node: dict[str, Artifact] = {}
    artifact_ids: dict[str, str] = {}
    node_roles: dict[str, str] = {}
    for node_id, node in by_id.items():
        if node_id == parameter_id:
            continue
        candidate = _canonical_role(candidates[node_id])
        if candidates[node_id] and candidate is None:
            unknown.append(f"conflicting checkpoint roles on saved node: {node_id}")
            continue
        if candidate is None:
            continue
        checkpoint_id, role = candidate
        if checkpoint_id == "@runtime":
            continue
        checkpoint = _CHECKPOINTS.get(checkpoint_id)
        if checkpoint is None:
            unknown.append(f"unknown checkpoint for saved node: {node_id}")
            continue
        scope = checkpoint.scope
        targets = set(target_claims[node_id])
        branches = set(branch_claims[node_id])
        trajectory_id = _attr(node, "DENTOBOT.RegistryTrajectoryID") or data["node_trajectories"].get(node_id, "")
        if len(targets) > 1:
            unknown.append(f"saved node has conflicting target ownership: {node_id}")
            continue
        if len(branches) > 1:
            unknown.append(f"saved node has conflicting branch ownership: {node_id}")
            continue
        target_id = next(iter(targets), "")
        branch_id = next(iter(branches), "")
        if scope == "shared":
            if target_id or branch_id:
                unknown.append(f"shared checkpoint node has target or branch claims: {node_id}")
                continue
        elif scope == "target":
            if not target_id:
                unknown.append(f"target checkpoint node has no reviewed registry owner: {node_id}")
                continue
            if branch_id:
                # Registered membership does not make a trajectory branch-scoped.
                if checkpoint_id == "trajectory.plan":
                    branch_id = ""
                else:
                    unknown.append(f"target checkpoint node has a branch claim: {node_id}")
                    continue
        else:
            branch = data["branches"].get(branch_id)
            if not branch_id or branch is None:
                unknown.append(f"branch checkpoint node has no registered branch owner: {node_id}")
                continue
            if not target_id:
                target_id = branch.target_id
            if target_id != branch.target_id:
                unknown.append(f"branch checkpoint target conflicts with its registry branch: {node_id}")
                continue
        if target_id and target_id not in data["targets"]:
            unknown.append(f"saved node has an unregistered target owner: {node_id}")
            continue
        trajectory_ids = (trajectory_id,) if trajectory_id else ()
        if trajectory_id:
            trajectory = data["trajectories"].get(trajectory_id)
            if trajectory is None or trajectory["target_id"] != target_id:
                unknown.append(f"saved node trajectory does not match its target: {node_id}")
                continue
        artifact_id = node_id
        state = _attr(node, "DENTOBOT.GeometryState") or _attr(node, "DENTOBOT.PlanningStatus") or "Unknown"
        artifact = Artifact(
            artifact_id, checkpoint_id, scope, target_id, branch_id, state,
            role, (), trajectory_ids, "",
        )
        assembly_owner = _attr(node, "DENTOBOT.OwnerAssemblyNodeID")
        if assembly_owner:
            owner_target = target_claims.get(assembly_owner, set())
            owner_branch = branch_claims.get(assembly_owner, set())
            if len(owner_target) == 1:
                target_claims[node_id].update(owner_target)
            if len(owner_branch) == 1:
                branch_claims[node_id].update(owner_branch)
        artifact_by_node[node_id] = artifact
        artifact_ids[node_id] = artifact_id
        node_roles[node_id] = role

    # Same field and same unit with multiple candidate nodes is ambiguous.
    candidate_keys: dict[tuple[str, str, str, str, tuple[str, ...]], list[str]] = defaultdict(list)
    for node_id, artifact in artifact_by_node.items():
        candidate_keys[(artifact.checkpoint_id, artifact.role, artifact.target_id,
                        artifact.branch_id, artifact.trajectory_ids)].append(node_id)
    for (checkpoint_id, role, target_id, branch_id, _trajectory_ids), node_ids in candidate_keys.items():
        if len(node_ids) > 1:
            unknown.append(
                f"duplicate candidate binding for {checkpoint_id}/{role}/{target_id}/{branch_id}: "
                + ", ".join(sorted(node_ids))
            )

    # Transform and explicit auxiliary-owner edges retain only same-or-earlier
    # checkpoint dependencies with compatible unit ownership.
    artifacts: list[Artifact] = []
    for node_id, artifact in artifact_by_node.items():
        node = by_id[node_id]
        dependency_ids: list[str] = []
        transform_getter = getattr(node, "GetTransformNodeID", None)
        parent_ids: list[str] = []
        if callable(transform_getter):
            try:
                parent = _text(transform_getter())
                if parent:
                    parent_ids.append(parent)
            except (RuntimeError, TypeError):
                pass
        auxiliary = _attr(node, "DENTOBOT.AuxiliaryOwnerNodeID")
        if auxiliary:
            parent_ids.append(auxiliary)
        assembly_owner = _attr(node, "DENTOBOT.OwnerAssemblyNodeID")
        if assembly_owner:
            parent_ids.append(assembly_owner)
        for parent_id in dict.fromkeys(parent_ids):
            parent_artifact = artifact_by_node.get(parent_id)
            if parent_artifact is None:
                unknown.append(f"owned node dependency has no checkpoint artifact: {node_id}->{parent_id}")
                continue
            compatible = (
                parent_artifact.scope == "shared"
                or (parent_artifact.target_id == artifact.target_id
                    and (parent_artifact.scope == "target" or parent_artifact.branch_id == artifact.branch_id))
            )
            if (_ORDER[parent_artifact.checkpoint_id] > _ORDER[artifact.checkpoint_id]
                    or not compatible):
                unknown.append(f"node dependency is later or outside its unit: {node_id}->{parent_id}")
                continue
            dependency_ids.append(artifact_ids[parent_id])
        artifacts.append(Artifact(
            artifact.id, artifact.checkpoint_id, artifact.scope,
            artifact.target_id, artifact.branch_id, artifact.state, artifact.role,
            tuple(sorted(set(dependency_ids))), artifact.trajectory_ids, artifact.reason,
        ))

    artifact_by_node = {node_id: next(item for item in artifacts if item.id == artifact.id)
                        for node_id, artifact in artifact_by_node.items()}

    for node_id, node in by_id.items():
        for role_attribute in _ROLE_ATTRIBUTES:
            value = _attr(node, role_attribute)
            contract = _AUXILIARY_OWNER_ROLES.get((role_attribute, value))
            if contract is None:
                continue
            owner_attribute, required_checkpoint = contract
            owner_id = _attr(node, owner_attribute)
            owner_artifact = artifact_by_node.get(owner_id)
            if owner_artifact is None or owner_artifact.checkpoint_id != required_checkpoint:
                unknown.append(
                    f"auxiliary role has no {required_checkpoint} owner: {node_id}->{owner_id or '<missing>'}"
                )

    # Propagate checkpoint artifact owners to linked display/storage and explicit
    # auxiliary nodes. Unresolved links remain ownerless blockers.
    node_owners: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    if parameter_id in node_owners:
        node_owners[parameter_id] = []
    for node_id, artifact_id in artifact_ids.items():
        node_owners[node_id] = [artifact_id]
    parent_links: dict[str, set[str]] = defaultdict(set)
    for parent_id, parent in by_id.items():
        for child_id in _linked_nodes(parent):
            if child_id in by_id:
                parent_links[child_id].add(parent_id)
        # AuxiliaryOwnerNodeID is an exact persisted ownership edge.
        child_id = _attr(parent, "DENTOBOT.AuxiliaryOwnerNodeID")
        if child_id and child_id in by_id:
            parent_links[parent_id].add(child_id)
        child_id = _attr(parent, "DENTOBOT.OwnerAssemblyNodeID")
        if child_id and child_id in by_id:
            parent_links[parent_id].add(child_id)
    special = {node_id: _special_node_owner(node) for node_id, node in by_id.items()}
    for _ in range(max(1, len(by_id))):
        changed = False
        for child_id, parents in parent_links.items():
            if node_owners[child_id]:
                continue
            inherited = {owner for parent_id in parents for owner in node_owners.get(parent_id, ())}
            if inherited:
                node_owners[child_id] = sorted(inherited)
                changed = True
                continue
            if len(parents) == 1:
                parent_id = next(iter(parents))
                if special.get(parent_id):
                    node_owners[child_id] = [special[parent_id]]
                    changed = True
        if not changed:
            break
    for node_id, owner in special.items():
        if owner and not node_owners[node_id]:
            node_owners[node_id] = [owner]
    for node_id, owners in node_owners.items():
        if node_id == parameter_id:
            continue
        if not owners:
            unknown.append(f"saved node has no concrete checkpoint or display/runtime owner: {node_id} ({_class_name(by_id[node_id])})")
        elif len(owners) > 1 and not all(owner.startswith("artifact:") for owner in owners):
            unknown.append(f"saved node inherits conflicting ownership: {node_id}")

    # Translate MRML transform parents into artifact dependencies after display
    # and storage inheritance; they cannot be silently omitted from ownership.
    artifacts.extend(_configuration_artifacts(parameter_wrapper, data, unknown))
    artifacts.sort(key=lambda item: item.id)
    inventory_artifacts = []
    for artifact in artifacts:
        inventory_artifacts.append({
            "id": artifact.id, "checkpoint_id": artifact.checkpoint_id,
            "scope": artifact.scope, "target_id": artifact.target_id,
            "branch_id": artifact.branch_id, "state": artifact.state,
            "role": artifact.role, "dependencies": list(artifact.dependencies),
            "trajectory_ids": list(artifact.trajectory_ids), "reason": artifact.reason,
        })
    inventory_branches = [
        {"id": branch.id, "target_id": branch.target_id,
         "trajectory_ids": list(branch.trajectory_ids),
         "pairing_intent": branch.pairing_intent, "state": branch.state}
        for branch in sorted(data["branches"].values(), key=lambda item: item.id)
    ]
    unknown = sorted(set(unknown))
    inventory = {
        "schemaVersion": INVENTORY_SCHEMA_VERSION,
        "definitionVersion": CHECKPOINT_DEFINITION_VERSION,
        "targetIds": sorted(data["targets"]),
        "artifacts": inventory_artifacts,
        "branches": inventory_branches,
        "ownershipComplete": not unknown,
        "unknownOwnership": unknown,
    }
    projection = {
        "version": "1.0",
        "parameterNodeId": parameter_id,
        "nodeIds": sorted(by_id),
        "nodeOwners": {node_id: node_owners[node_id] for node_id in sorted(by_id)},
        "parameterOwners": dict(sorted(parameter_owners.items())),
        "referenceOwners": dict(sorted(reference_owners.items())),
        "resumeIndices": dict(RESUME_INDICES),
        "defaults": dict(sorted(defaults.items())),
    }
    return inventory, projection
