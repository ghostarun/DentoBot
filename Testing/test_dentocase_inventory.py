"""Offline checks for the frozen MRML ownership adapter."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
sys.path.insert(0, str(PYTHON))

from dentobot_case.contracts import Artifact, Branch, CaseInventory, CHECKPOINTS  # noqa: E402
from dentobot_case.lineage import select_prefix  # noqa: E402
from dentobot_case.ownership import DEFAULTS, NODE_FIELDS, PARAMETER_OWNERS, RESUME_INDICES  # noqa: E402
from dentobot_workflow.case_inventory import capture_inventory  # noqa: E402


class Node:
    def __init__(self, node_id, class_name="vtkMRMLNode", attrs=None, refs=None,
                 saved=True, linked=None):
        self.node_id = node_id
        self.class_name = class_name
        self.attrs = dict(attrs or {})
        self.refs = {role: list(ids) for role, ids in (refs or {}).items()}
        self.saved = saved
        self.linked = dict(linked or {})

    def GetID(self):
        return self.node_id

    def GetClassName(self):
        return self.class_name

    def IsA(self, name):
        return self.class_name == name or (name == "vtkMRMLDisplayNode" and self.class_name.endswith("DisplayNode"))

    def GetSaveWithScene(self):
        return self.saved

    def GetAttribute(self, name):
        return self.attrs.get(name)

    def SetAttribute(self, name, value):
        if value is None:
            self.attrs.pop(name, None)
        else:
            self.attrs[name] = value

    def GetNodeReferenceRoles(self, roles):
        roles.extend(self.refs)

    def GetNumberOfNodeReferences(self, role):
        return len(self.refs.get(role, ()))

    def GetNthNodeReferenceID(self, role, index):
        return self.refs[role][index]

    def GetTransformNodeID(self):
        return self.linked.get("transform", "")

    def GetDisplayNodeID(self):
        return self.linked.get("display", "")

    def GetStorageNodeID(self):
        return self.linked.get("storage", "")

    def GetModuleName(self):
        return self.attrs.get("module_name", "")

    def GetSingletonTag(self):
        return self.attrs.get("singleton_tag", "")


class ParameterNode(Node):
    def __init__(self, *args, parameter_names=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.parameter_names = list(parameter_names)
        self.parameter_values = {}

    def GetParameterNames(self):
        return self.parameter_names

    def GetParameter(self, name):
        return self.parameter_values.get(name, "")


class Wrapper:
    def __init__(self, raw, **values):
        self.parameterNode = raw
        self.__dict__.update(values)


class Scene:
    def __init__(self, nodes):
        self.nodes = list(nodes)

    def GetNumberOfNodes(self):
        return len(self.nodes)

    def GetNthNode(self, index):
        return self.nodes[index]


def _registry():
    teeth = {
        f"FDI{quadrant}{tooth}": {
            "target_id": "", "segment_id": "",
            "trajectory_set": {"slots": [
                {"slot": slot, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []}
                for slot in range(1, 4)
            ]},
        }
        for quadrant in range(1, 5) for tooth in range(1, 9)
    }
    tooth = teeth["FDI31"]
    tooth.update(target_id="target-31", segment_id="segment-31")
    tooth["trajectory_set"]["slots"][0].update(
        state="Current", target_id="target-31", trajectory_id="trajectory-1",
        trajectory_node_id="trajectory-node", prepared_branch_ids=["branch-1"],
    )
    return {
        "schema_version": "3.0", "teeth": teeth,
        "selected_branch_id": "branch-1",
        "prepared_branches": {
            "branch-1": {
                "branch_id": "branch-1", "target_id": "target-31",
                "trajectory_ids": ["trajectory-1"], "primary_trajectory_id": "trajectory-1",
                "pairing_intent": "Single", "state": "Current",
                "model_node_ids": ["support-node", "dock-node", "boundary-node", "shell-node", "final-node"],
            },
        },
    }


def _fixture(*, units=None, extra_nodes=(), unknown_reference=False):
    unit_payload = json.dumps({"version": "1.0", "branches": units or []}) if units is not None else ""
    raw_refs = {
        "inputVolume": ["volume-node"], "inspectedVolume": ["volume-node"],
        "teethSegmentation": ["seg-node"], "inspectedSegmentation": ["seg-node"],
        "step6CaseJawTransform": ["jaw-node"], "robotBaseTransform": ["base-node"],
        "trajectoryLine": ["trajectory-node"], "draftTemplateSupportModel": ["support-node"],
        "targetDockingAssemblyModel": ["dock-node"],
        "templateSupportBoundaryCurve": ["boundary-node"],
        "patientContactShellModel": ["shell-node"],
        "finalizedTemplateShellModel": ["final-node"],
    }
    if unknown_reference:
        raw_refs["unmappedReference"] = ["volume-node"]
    raw = ParameterNode(
        "parameter-node", "vtkMRMLScriptedModuleNode",
        attrs={"DENTOBOT.CasePreparationUnitsJson": unit_payload}, refs=raw_refs,
        parameter_names=("caseName", "dentoCaseId", "step6TrajectoryRegistryJson", "templateShellThicknessMm",
                         "step6TaskHomeJson", "step6AssistedLimitProposalJson",
                         "finalizedTemplateShellModel", "templateTrimPlane"),
    )
    nodes = [
        raw,
        Node("volume-node", "vtkMRMLScalarVolumeNode", {"DENTOBOT.CaseScan": "true"},
             linked={"display": "volume-display", "storage": "volume-storage"}),
        Node("seg-node", "vtkMRMLSegmentationNode"),
        Node("jaw-node", "vtkMRMLLinearTransformNode"),
        Node("base-node", "vtkMRMLLinearTransformNode"),
        Node("trajectory-node", "vtkMRMLMarkupsLineNode", {
            "DENTOBOT.TrajectoryRole": "EntryToTarget",
            "DENTOBOT.RegistryTargetID": "target-31",
            "DENTOBOT.RegistryTrajectoryID": "trajectory-1",
        }),
        Node("support-node", "vtkMRMLModelNode", {
            "DENTOBOT.ModelRole": "TemplateSupportDraft",
            "DENTOBOT.RegistryTargetID": "target-31",
            "DENTOBOT.RegistryGuideSetID": "branch-1",
        }),
        Node("dock-node", "vtkMRMLModelNode", {
            "DENTOBOT.ModelRole": "TargetDockingAssembly",
            "DENTOBOT.RegistryTargetID": "target-31",
            "DENTOBOT.RegistryGuideSetID": "branch-1",
        }),
        Node("boundary-node", "vtkMRMLMarkupsClosedCurveNode", {
            "DENTOBOT.MarkupsRole": "TemplateSupportBoundary",
            "DENTOBOT.RegistryTargetID": "target-31",
            "DENTOBOT.RegistryGuideSetID": "branch-1",
        }),
        Node("shell-node", "vtkMRMLModelNode", {
            "DENTOBOT.ModelRole": "PatientContactShell",
            "DENTOBOT.RegistryTargetID": "target-31",
            "DENTOBOT.RegistryGuideSetID": "branch-1",
        }),
        Node("final-node", "vtkMRMLModelNode", {
            "DENTOBOT.ModelRole": "FinalizedTemplateShell",
            "DENTOBOT.RegistryTargetID": "target-31",
            "DENTOBOT.RegistryGuideSetID": "branch-1",
        }),
        Node("fitting-node", "vtkMRMLModelNode", {
            "DENTOBOT.ModelRole": "TemplateFittingSurface",
            "DENTOBOT.AuxiliaryOwnerNodeID": "shell-node",
        }),
        Node("measurement-node", "vtkMRMLMarkupsLineNode", {
            "DENTOBOT.MarkupsRole": "TargetDockingMeasurement",
            "DENTOBOT.OwnerAssemblyNodeID": "dock-node",
        }),
        Node("finalization-cut-node", "vtkMRMLDynamicModelerNode", {
            "DENTOBOT.DynamicModelerRole": "TemplateFinalizationCut",
            "DENTOBOT.AuxiliaryOwnerNodeID": "final-node",
        }),
        Node("dataprobe-node", "vtkMRMLScriptedModuleNode", {
            "singleton_tag": "DataProbe",
        }),
        Node("units-node", "vtkMRMLScriptedModuleNode", {
            "module_name": None, "singleton_tag": "Units",
        }),
        Node("volume-display", "vtkMRMLScalarVolumeDisplayNode"),
        Node("volume-storage", "vtkMRMLVolumeArchetypeStorageNode"),
        Node("unsaved-node", "vtkMRMLModelNode", saved=False),
        *extra_nodes,
    ]
    summary = {
        "reviewedTargets": [{"targetId": "target-31", "fdi": "31", "segmentId": "segment-31"}],
        "step6": {"trajectoryRegistry": _registry()},
    }
    wrapper = Wrapper(
        raw,
        step6TaskHomeJson=json.dumps({"revision": 1, "runtime_validation_status": "Unreviewed"}),
        step6AssistedLimitProposalJson=json.dumps({"revision": 1, "reviewed": False}),
    )
    return wrapper, Scene(nodes), summary


def _add_reviewed_target(summary, fdi, target_id, segment_id):
    slots = [
        {"slot": slot, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []}
        for slot in range(1, 4)
    ]
    summary["step6"]["trajectoryRegistry"]["teeth"][f"FDI{fdi}"] = {
        "target_id": target_id, "segment_id": segment_id,
        "trajectory_set": {"slots": slots},
    }
    summary["reviewedTargets"].append({
        "targetId": target_id, "fdi": str(fdi), "segmentId": segment_id,
    })


def _add_step5c_template(
    wrapper, scene, summary, *, branch_id="branch-1", target_id="target-31",
    node_id="step5b-template-node", revision="revision-1",
    planning_pose="pose-1", foundation="foundation-1", state="WARNING",
    include_foundation=True, remove_legacy_template=False,
):
    registry = summary["step6"]["trajectoryRegistry"]
    branch = registry["prepared_branches"][branch_id]
    if remove_legacy_template and "final-node" in branch["model_node_ids"]:
        branch["model_node_ids"].remove("final-node")
    branch["model_node_ids"].append(node_id)
    verification = {
        "schemaVersion": "1.0", "overall": state,
        "verifiedUtc": "2026-10-10T00:00:00+00:00",
        "finalModelUpdatedUtc": "2026-10-09T00:00:00+00:00",
        "preparedBranchId": branch_id, "preparedBranchRevision": revision,
        "planningPoseFingerprint": planning_pose,
        "checks": [{"result": "WARNING", "name": "Host fixture", "details": "Saved verification fixture."}],
    }
    if include_foundation:
        verification["branchFoundationFingerprint"] = foundation
    verification_json = json.dumps(verification, sort_keys=True, separators=(",", ":"))
    verification_revision = hashlib.sha256(verification_json.encode("utf-8")).hexdigest()
    branch.update({
        "template_node_id": node_id,
        "revision": revision, "verification_revision": verification_revision,
        "planning_pose_fingerprint": planning_pose,
    })
    if include_foundation:
        branch["branch_foundation_fingerprint"] = foundation
    else:
        branch.pop("branch_foundation_fingerprint", None)
    attributes = {
        "DENTOBOT.ModelRole": "FinalPrintableTemplate",
        "DENTOBOT.RegistryTargetID": target_id,
        "DENTOBOT.RegistryGuideSetID": branch_id,
        "DENTOBOT.PreparedBranchRevision": revision,
        "DENTOBOT.PlanningPoseFingerprint": planning_pose,
        "DENTOBOT.GeometryState": "Current",
        "DENTOBOT.VerificationState": state,
        "DENTOBOT.VerificationJson": verification_json,
    }
    if include_foundation:
        attributes["DENTOBOT.BranchFoundationFingerprint"] = foundation
    template = Node(node_id, "vtkMRMLModelNode", attributes)
    if remove_legacy_template:
        scene.nodes.remove(next(node for node in scene.nodes if node.GetID() == "final-node"))
        scene.nodes.remove(next(node for node in scene.nodes if node.GetID() == "finalization-cut-node"))
        wrapper.parameterNode.refs.pop("finalizedTemplateShellModel")
    scene.nodes.append(template)
    return template, verification


def _case_inventory_from_capture(payload):
    return CaseInventory(
        path="fixture.dentocase", package_id="package", case_id="case",
        label="fixture", archive_schema="3.0", package_sha256="sha256",
        checked_at_utc="2026-10-10T00:00:00+00:00",
        target_ids=tuple(payload["targetIds"]),
        artifacts=tuple(Artifact(
            **{**record, "dependencies": tuple(record["dependencies"]),
               "trajectory_ids": tuple(record["trajectory_ids"])}
        ) for record in payload["artifacts"]),
        branches=tuple(Branch(
            **{**record, "trajectory_ids": tuple(record["trajectory_ids"])}
        ) for record in payload["branches"]),
        ownership_complete=payload["ownershipComplete"],
        unknown_ownership=tuple(payload["unknownOwnership"]),
        definition_version=payload["definitionVersion"],
    )


def test_frozen_maps_match_parameter_wrapper_ast():
    source = (PYTHON / "dentobot_workflow/parameter_state.py").read_text()
    tree = ast.parse(source)
    wrapper = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DENTOWorkflowParameterNode")
    fields = {item.target.id: item for item in wrapper.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)}
    node_fields = {
        name for name, item in fields.items()
        if isinstance(item.annotation, ast.Name) and item.annotation.id.startswith("vtkMRML")
    }
    defaults = {name for name, item in fields.items() if item.value is not None}
    assert set(PARAMETER_OWNERS) == set(fields)
    assert set(NODE_FIELDS) == node_fields
    assert set(DEFAULTS) == defaults
    assert set(RESUME_INDICES) == {checkpoint.id for checkpoint in CHECKPOINTS}


def test_capture_emits_exact_payloads_and_inherits_linked_storage_ownership():
    wrapper, scene, summary = _fixture()
    inventory, projection = capture_inventory(wrapper, scene, summary)

    assert set(inventory) == {
        "schemaVersion", "definitionVersion", "targetIds", "artifacts", "branches",
        "ownershipComplete", "unknownOwnership",
    }
    assert set(projection) == {
        "version", "parameterNodeId", "nodeIds", "nodeOwners", "parameterOwners",
        "referenceOwners", "resumeIndices", "defaults",
    }
    assert inventory["ownershipComplete"] is True
    assert inventory["targetIds"] == ["target-31"]
    assert [item["id"] for item in inventory["branches"]] == ["branch-1"]
    assert inventory["branches"][0]["state"] == "Current"
    assert projection["nodeOwners"]["parameter-node"] == []
    assert projection["nodeOwners"]["volume-display"] == ["volume-node"]
    assert projection["nodeOwners"]["volume-storage"] == ["volume-node"]
    assert projection["nodeOwners"]["fitting-node"] == ["shell-node"]
    assert projection["nodeOwners"]["measurement-node"] == ["dock-node"]
    assert projection["nodeOwners"]["finalization-cut-node"] == ["final-node"]
    assert projection["nodeOwners"]["dataprobe-node"] == ["@display"]
    assert projection["nodeOwners"]["units-node"] == ["@display"]
    reference_roles = {
        "inputVolume", "inspectedVolume", "teethSegmentation", "inspectedSegmentation",
        "step6CaseJawTransform", "robotBaseTransform", "trajectoryLine",
        "draftTemplateSupportModel", "targetDockingAssemblyModel",
        "templateSupportBoundaryCurve", "patientContactShellModel", "finalizedTemplateShellModel",
    }
    assert projection["referenceOwners"] == {
        role: PARAMETER_OWNERS[role] for role in sorted(reference_roles)
    }
    assert "finalizedTemplateShellModel" not in projection["parameterOwners"]
    assert "templateTrimPlane" not in projection["parameterOwners"]
    assert "unsaved-node" not in projection["nodeIds"]
    artifacts = {item["id"]: item for item in inventory["artifacts"]}
    assert artifacts["volume-node"]["role"] == "inputVolume"
    assert artifacts["seg-node"]["role"] == "teethSegmentation"
    assert artifacts["jaw-node"]["checkpoint_id"] == "foundation.pose"
    assert artifacts["base-node"]["checkpoint_id"] == "foundation.base"
    assert artifacts["trajectory-node"]["trajectory_ids"] == ["trajectory-1"]
    assert artifacts["trajectory-node"]["branch_id"] == ""
    assert artifacts["support-node"]["checkpoint_id"] == "support.selection"
    assert artifacts["shell-node"]["branch_id"] == "branch-1"
    assert artifacts["parameter:step6TaskHomeJson:target-31"]["state"] == "Unreviewed"
    assert artifacts["parameter:step6AssistedLimitProposalJson:target-31"]["state"] == "Unreviewed"
    assert "fitting-node" not in artifacts
    assert "measurement-node" not in artifacts
    assert "finalization-cut-node" not in artifacts


def test_selected_registry_unit_is_only_fallback_for_global_wrapper_bindings():
    wrapper, scene, summary = _fixture()
    trajectory = next(node for node in scene.nodes if node.GetID() == "trajectory-node")
    trajectory.attrs.pop("DENTOBOT.RegistryTargetID")
    trajectory.attrs.pop("DENTOBOT.RegistryTrajectoryID")
    slot = summary["step6"]["trajectoryRegistry"]["teeth"]["FDI31"]["trajectory_set"]["slots"][0]
    slot.pop("trajectory_node_id")
    support = next(node for node in scene.nodes if node.GetID() == "support-node")
    support.attrs.pop("DENTOBOT.RegistryTargetID")
    support.attrs.pop("DENTOBOT.RegistryGuideSetID")
    summary["step6"]["trajectoryRegistry"]["prepared_branches"]["branch-1"]["model_node_ids"].remove("support-node")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    artifacts = {item["id"]: item for item in inventory["artifacts"]}
    assert artifacts["trajectory-node"]["target_id"] == "target-31"
    assert artifacts["trajectory-node"]["trajectory_ids"] == ["trajectory-1"]
    assert artifacts["support-node"]["branch_id"] == "branch-1"
    assert inventory["ownershipComplete"] is True


def test_exact_saved_target_semantics_resolve_the_unique_registered_branch():
    wrapper, scene, summary = _fixture()
    support = next(node for node in scene.nodes if node.GetID() == "support-node")
    support.attrs.pop("DENTOBOT.RegistryTargetID")
    support.attrs.pop("DENTOBOT.RegistryGuideSetID")
    support.attrs.update({
        "DENTOBOT.TargetSegmentID": "segment-31",
        "DENTOBOT.TargetFdiNumber": "31",
    })
    wrapper.parameterNode.refs.pop("draftTemplateSupportModel")
    summary["step6"]["trajectoryRegistry"]["prepared_branches"]["branch-1"]["model_node_ids"].remove("support-node")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    artifact = next(item for item in inventory["artifacts"] if item["id"] == "support-node")
    assert inventory["ownershipComplete"] is True
    assert artifact["target_id"] == "target-31"
    assert artifact["branch_id"] == "branch-1"


def test_inconsistent_exact_target_semantics_fail_closed():
    wrapper, scene, summary = _fixture()
    support = next(node for node in scene.nodes if node.GetID() == "support-node")
    support.attrs.pop("DENTOBOT.RegistryTargetID")
    support.attrs.pop("DENTOBOT.RegistryGuideSetID")
    support.attrs.update({
        "DENTOBOT.TargetSegmentID": "segment-31",
        "DENTOBOT.TargetFdiNumber": "99",
    })
    wrapper.parameterNode.refs.pop("draftTemplateSupportModel")
    summary["step6"]["trajectoryRegistry"]["prepared_branches"]["branch-1"]["model_node_ids"].remove("support-node")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("semantic target identity does not resolve uniquely and consistently" in reason
               for reason in inventory["unknownOwnership"])
    assert any("support-node" in reason for reason in inventory["unknownOwnership"])


def test_incomplete_exact_target_semantics_fail_closed():
    wrapper, scene, summary = _fixture()
    support = next(node for node in scene.nodes if node.GetID() == "support-node")
    support.attrs.pop("DENTOBOT.RegistryTargetID")
    support.attrs.pop("DENTOBOT.RegistryGuideSetID")
    support.SetAttribute("DENTOBOT.TargetSegmentID", "segment-31")
    wrapper.parameterNode.refs.pop("draftTemplateSupportModel")
    summary["step6"]["trajectoryRegistry"]["prepared_branches"]["branch-1"]["model_node_ids"].remove("support-node")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("semantic target identity is incomplete on support-node" in reason
               for reason in inventory["unknownOwnership"])


def test_conflicting_target_claims_do_not_gain_a_branch_owner():
    wrapper, scene, summary = _fixture()
    _add_reviewed_target(summary, "32", "target-32", "segment-32")
    support = next(node for node in scene.nodes if node.GetID() == "support-node")
    support.attrs.pop("DENTOBOT.RegistryGuideSetID")
    support.attrs.update({
        "DENTOBOT.TargetSegmentID": "segment-32",
        "DENTOBOT.TargetFdiNumber": "32",
    })
    wrapper.parameterNode.refs.pop("draftTemplateSupportModel")
    summary["step6"]["trajectoryRegistry"]["prepared_branches"]["branch-1"]["model_node_ids"].remove("support-node")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("saved node has conflicting target ownership: support-node" in reason
               for reason in inventory["unknownOwnership"])


def test_multiple_registered_branches_for_exact_target_are_ambiguous():
    wrapper, scene, summary = _fixture()
    support = next(node for node in scene.nodes if node.GetID() == "support-node")
    support.attrs.pop("DENTOBOT.RegistryTargetID")
    support.attrs.pop("DENTOBOT.RegistryGuideSetID")
    support.attrs.update({
        "DENTOBOT.TargetSegmentID": "segment-31",
        "DENTOBOT.TargetFdiNumber": "31",
    })
    wrapper.parameterNode.refs.pop("draftTemplateSupportModel")
    registry = summary["step6"]["trajectoryRegistry"]
    registry["prepared_branches"]["branch-1"]["model_node_ids"].remove("support-node")
    registry["prepared_branches"]["branch-2"] = {
        "branch_id": "branch-2", "target_id": "target-31",
        "trajectory_ids": ["trajectory-1"], "primary_trajectory_id": "trajectory-1",
        "pairing_intent": "Single", "state": "Current", "model_node_ids": [],
    }
    registry["teeth"]["FDI31"]["trajectory_set"]["slots"][0]["prepared_branch_ids"].append("branch-2")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("multiple registered branches for branch checkpoint node: support-node" in reason
               for reason in inventory["unknownOwnership"])
    assert any("branch checkpoint node has no registered branch owner: support-node" in reason
               for reason in inventory["unknownOwnership"])


def test_valid_registered_template_verification_creates_virtual_step5c_artifact():
    wrapper, scene, summary = _fixture()
    _template, _verification = _add_step5c_template(
        wrapper, scene, summary, remove_legacy_template=True
    )

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    artifact = next(item for item in inventory["artifacts"] if item["id"] == "verification:branch-1")
    assert inventory["ownershipComplete"] is True
    assert artifact["checkpoint_id"] == "template.verify"
    assert artifact["scope"] == "branch"
    assert artifact["target_id"] == "target-31"
    assert artifact["branch_id"] == "branch-1"
    assert artifact["state"] == "WARNING"
    assert artifact["role"] == "step5cVerification"
    assert artifact["dependencies"] == ["step5b-template-node"]


def test_legacy_verification_without_branch_foundation_fingerprint_is_valid_when_all_omit_it():
    wrapper, scene, summary = _fixture()
    _add_step5c_template(
        wrapper, scene, summary, include_foundation=False,
        remove_legacy_template=True,
    )

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    artifact = next(item for item in inventory["artifacts"] if item["id"] == "verification:branch-1")
    assert inventory["ownershipComplete"] is True
    assert artifact["checkpoint_id"] == "template.verify"
    assert artifact["state"] == "WARNING"


def test_optional_branch_foundation_fingerprint_must_be_consistent_when_present():
    wrapper, scene, summary = _fixture()
    template, verification = _add_step5c_template(
        wrapper, scene, summary, include_foundation=False,
        remove_legacy_template=True,
    )
    verification["branchFoundationFingerprint"] = "foundation-1"
    template.SetAttribute(
        "DENTOBOT.VerificationJson",
        json.dumps(verification, sort_keys=True, separators=(",", ":")),
    )

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert not any(item["id"] == "verification:branch-1" for item in inventory["artifacts"])
    assert any("persisted Step 5C verification does not match its prepared branch" in reason
               for reason in inventory["unknownOwnership"])


def test_virtual_step5c_artifact_enables_only_the_verified_prefix():
    wrapper, scene, summary = _fixture()
    _add_step5c_template(wrapper, scene, summary, remove_legacy_template=True)
    inventory_payload, _projection = capture_inventory(wrapper, scene, summary)
    inventory = _case_inventory_from_capture(inventory_payload)

    without_verification = CaseInventory(
        **{**inventory.__dict__, "artifacts": tuple(
            artifact for artifact in inventory.artifacts
            if artifact.checkpoint_id != "template.verify"
        )}
    )
    blocked = select_prefix(without_verification, "target-31", "template.verify", "branch-1")
    allowed = select_prefix(inventory, "target-31", "template.verify", "branch-1")
    assert blocked.allowed is False
    assert any("missing checkpoint artifact: template.verify" in reason for reason in blocked.reasons)
    assert allowed.allowed is True
    assert "verification:branch-1" in allowed.included_ids


def test_mismatched_persisted_template_verification_fails_closed():
    wrapper, scene, summary = _fixture()
    template, verification = _add_step5c_template(
        wrapper, scene, summary, remove_legacy_template=True
    )
    verification["preparedBranchRevision"] = "another-revision"
    template.SetAttribute(
        "DENTOBOT.VerificationJson",
        json.dumps(verification, sort_keys=True, separators=(",", ":")),
    )

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert not any(item["id"] == "verification:branch-1" for item in inventory["artifacts"])
    assert any("persisted Step 5C verification does not match its prepared branch" in reason
               for reason in inventory["unknownOwnership"])


def test_template_node_registered_to_multiple_branches_is_ambiguous():
    wrapper, scene, summary = _fixture()
    _add_step5c_template(wrapper, scene, summary, remove_legacy_template=True)
    registry = summary["step6"]["trajectoryRegistry"]
    registry["prepared_branches"]["branch-2"] = {
        "branch_id": "branch-2", "target_id": "target-31",
        "trajectory_ids": ["trajectory-1"], "primary_trajectory_id": "trajectory-1",
        "pairing_intent": "Single", "state": "Current",
        "template_node_id": "step5b-template-node", "revision": "revision-2",
        "verification_revision": "", "planning_pose_fingerprint": "pose-2",
        "branch_foundation_fingerprint": "foundation-2", "model_node_ids": [],
    }
    registry["teeth"]["FDI31"]["trajectory_set"]["slots"][0]["prepared_branch_ids"].append("branch-2")

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert not any(item["id"] == "verification:branch-1" for item in inventory["artifacts"])
    assert any("registered template node has ambiguous branch ownership: step5b-template-node" in reason
               for reason in inventory["unknownOwnership"])


def test_each_registered_target_branch_gets_its_own_verified_artifact():
    wrapper, scene, summary = _fixture()
    _add_step5c_template(wrapper, scene, summary, remove_legacy_template=True)
    registry = summary["step6"]["trajectoryRegistry"]
    for fdi in range(32, 36):
        target_id = f"target-{fdi}"
        segment_id = f"segment-{fdi}"
        branch_id = f"branch-{fdi}"
        trajectory_id = f"trajectory-{fdi}"
        _add_reviewed_target(summary, str(fdi), target_id, segment_id)
        slot = registry["teeth"][f"FDI{fdi}"]["trajectory_set"]["slots"][0]
        slot.update({
            "state": "Current", "target_id": target_id,
            "trajectory_id": trajectory_id, "prepared_branch_ids": [branch_id],
        })
        registry["prepared_branches"][branch_id] = {
            "branch_id": branch_id, "target_id": target_id,
            "trajectory_ids": [trajectory_id], "primary_trajectory_id": trajectory_id,
            "pairing_intent": "Single", "state": "Current", "model_node_ids": [],
        }
        _add_step5c_template(
            wrapper, scene, summary,
            branch_id=branch_id, target_id=target_id,
            node_id=f"step5b-template-{fdi}", revision=f"revision-{fdi}",
            planning_pose=f"pose-{fdi}", foundation=f"foundation-{fdi}",
        )

    inventory, _projection = capture_inventory(wrapper, scene, summary)
    virtual = {
        item["id"]: (item["target_id"], item["branch_id"], item["dependencies"])
        for item in inventory["artifacts"] if item["role"] == "step5cVerification"
    }
    assert inventory["ownershipComplete"] is True
    assert virtual == {
        "verification:branch-1": ("target-31", "branch-1", ["step5b-template-node"]),
        **{
            f"verification:branch-{fdi}": (
                f"target-{fdi}", f"branch-{fdi}", [f"step5b-template-{fdi}"]
            )
            for fdi in range(32, 36)
        },
    }


def test_registry_state_wins_for_matching_preparation_unit_and_unknown_branch_is_blocked():
    unit = {
        "id": "branch-1", "target_id": "target-31", "trajectory_ids": ["trajectory-1"],
        "pairing_intent": "Single", "state": "Stale",
    }
    wrapper, scene, summary = _fixture(units=[unit])
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is True
    assert inventory["branches"][0]["state"] == "Current"

    unit["trajectory_ids"] = ["missing-trajectory"]
    wrapper, scene, summary = _fixture(units=[unit])
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("trajectory membership conflicts" in reason for reason in inventory["unknownOwnership"])


def test_unknown_persistent_node_and_reference_block_partial_ownership_without_guessing():
    wrapper, scene, summary = _fixture(extra_nodes=[
        Node("legacy-geometry", "vtkMRMLModelNode"),
        Node("unknown-scripted-singleton", "vtkMRMLScriptedModuleNode", {
            "module_name": "OtherModule", "singleton_tag": "OtherModule",
        }),
    ])
    inventory, projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert projection["nodeOwners"]["legacy-geometry"] == []
    assert any("legacy-geometry" in reason for reason in inventory["unknownOwnership"])
    assert projection["nodeOwners"]["unknown-scripted-singleton"] == []
    assert any("unknown-scripted-singleton" in reason for reason in inventory["unknownOwnership"])

    wrapper, scene, summary = _fixture(unknown_reference=True)
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("unmapped persistent parameter reference role" in reason for reason in inventory["unknownOwnership"])


def test_conflicting_explicit_branch_claims_and_malformed_units_fail_closed():
    wrapper, scene, summary = _fixture()
    ambiguous = next(node for node in scene.nodes if node.GetID() == "support-node")
    registry = summary["step6"]["trajectoryRegistry"]
    second = dict(registry["prepared_branches"]["branch-1"])
    second["branch_id"] = "branch-2"
    second["model_node_ids"] = ["support-node"]
    registry["prepared_branches"]["branch-2"] = second
    registry["teeth"]["FDI31"]["trajectory_set"]["slots"][0]["prepared_branch_ids"].append("branch-2")
    ambiguous.SetAttribute("DENTOBOT.RegistryGuideSetID", "branch-2")
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("conflicting registered branch claims" in reason for reason in inventory["unknownOwnership"])

    wrapper, scene, summary = _fixture()
    wrapper.parameterNode.attrs["DENTOBOT.CasePreparationUnitsJson"] = '{bad'
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("preparation units JSON is malformed" in reason for reason in inventory["unknownOwnership"])

    wrapper, scene, summary = _fixture()
    wrapper.step6TaskHomeJson = "{bad"
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("step6TaskHomeJson payload is malformed" in reason for reason in inventory["unknownOwnership"])

    wrapper, scene, summary = _fixture()
    wrapper.parameterNode.parameter_values["finalizedTemplateShellModel"] = "unexpected-node-id"
    inventory, _projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"] is False
    assert any("node field parameter has unexpected scalar payload" in reason
               for reason in inventory["unknownOwnership"])


def test_adapter_module_has_no_top_level_host_imports():
    source = (PYTHON / "dentobot_workflow/case_inventory.py").read_text()
    tree = ast.parse(source)
    imports = [alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names]
    imports.extend(node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom))
    assert not any(name.split(".")[0] in {"slicer", "qt", "vtk", "rclpy", "rospy"} for name in imports)


def test_unreadable_reference_roles_block_ownership():
    class UnreadableReferences(Node):
        def GetNodeReferenceRoles(self, roles):
            raise RuntimeError("native enumeration unavailable")
    wrapper, scene, summary = _fixture(extra_nodes=[
        UnreadableReferences("unreadable-display", "vtkMRMLScalarVolumeDisplayNode")])
    inventory, _ = capture_inventory(wrapper, scene, summary)
    assert not inventory["ownershipComplete"]
    assert any("reference roles could not be audited: unreadable-display" in reason
               for reason in inventory["unknownOwnership"])


def test_nonselected_case_scan_is_history_only_when_unreferenced():
    historical = Node("historical-scan", "vtkMRMLScalarVolumeNode", {"DENTOBOT.CaseScan": "true"},
                      linked={"storage": "historical-storage"})
    storage = Node("historical-storage", "vtkMRMLVolumeArchetypeStorageNode")
    wrapper, scene, summary = _fixture(extra_nodes=[historical, storage])
    inventory, projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"]
    assert projection["nodeOwners"]["historical-scan"] == ["@history"]
    assert projection["nodeOwners"]["historical-storage"] == ["@history"]

    # A saved reference to the other scan can carry a real dependency;
    # that case remains ambiguous until an owner is recorded.
    next(node for node in scene.nodes if node.GetID() == "seg-node").refs["source"] = ["historical-scan"]
    inventory, _ = capture_inventory(wrapper, scene, summary)
    assert not inventory["ownershipComplete"]
    assert any("nonselected CaseScan is referenced" in reason for reason in inventory["unknownOwnership"])


def test_transient_foundation_references_and_exact_legacy_fields_clear_without_unknowns():
    wrapper, scene, summary = _fixture(extra_nodes=[
        Node("portal", "vtkMRMLMarkupsFiducialNode", {
            "DENTOBOT.MarkupsRole": "Step6MouthPortalVertices",
        }, linked={"storage": "portal-storage"}),
        Node("portal-storage", "vtkMRMLMarkupsJsonStorageNode"),
        Node("research-config", "vtkMRMLScriptedModuleNode", {
            "DENTOBOT.Research": "Step6WorkingConfigurations; simulation research only",
        }),
    ])
    wrapper.parameterNode.refs.update({
        "caseFoundationFixedUpperVolume": ["unsaved-upper"],
        "caseFoundationMovingLowerVolume": ["unsaved-lower"],
    })
    wrapper.parameterNode.parameter_names.extend(["draftJawTargetGapMm", "robotJoint6Deg"])
    wrapper.parameterNode.parameter_values["draftJawTargetGapMm"] = "40.0"
    inventory, projection = capture_inventory(wrapper, scene, summary)
    assert inventory["ownershipComplete"]
    assert projection["nodeOwners"]["portal"] == ["@runtime"]
    assert projection["nodeOwners"]["portal-storage"] == ["@runtime"]
    assert projection["nodeOwners"]["research-config"] == ["@history"]
    assert set(projection["referenceOwners"]) >= {
        "caseFoundationFixedUpperVolume", "caseFoundationMovingLowerVolume",
    }
    assert projection["parameterOwners"]["draftJawTargetGapMm"] == "history"
    assert projection["parameterOwners"]["robotJoint6Deg"] == "runtime"

    wrapper.parameterNode.refs["unreviewed_missing_role"] = ["unsaved-node"]
    inventory, _ = capture_inventory(wrapper, scene, summary)
    assert not inventory["ownershipComplete"]
    assert any("unmapped persistent parameter reference role" in reason for reason in inventory["unknownOwnership"])
