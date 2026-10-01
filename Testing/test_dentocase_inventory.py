"""Offline checks for the frozen MRML ownership adapter."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
sys.path.insert(0, str(PYTHON))

from dentobot_case.contracts import CHECKPOINTS  # noqa: E402
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
