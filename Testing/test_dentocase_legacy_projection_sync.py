"""Host regression for the legacy Step 5C registry path used by projection."""

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow/Resources/Python"
sys.path.insert(0, str(PY))

import DENTOStep6State as state  # noqa: E402
from dentobot_case.contracts import Artifact, Branch  # noqa: E402
from dentobot_case.projection import filter_registry  # noqa: E402
from dentobot_workflow import jaw_frame  # noqa: E402
from dentobot_workflow.case_inventory import _step5c_verification_artifacts  # noqa: E402
from dentobot_workflow.case_projection import (  # noqa: E402
    _clear_future_node_attributes, _legacy_projection_provenance,
)


class Node:
    def __init__(self, node_id, attrs):
        self.node_id = node_id
        self.attrs = dict(attrs)

    def GetID(self):
        return self.node_id

    def GetAttribute(self, key):
        return self.attrs.get(key)

    def SetAttribute(self, key, value):
        self.attrs[key] = value

    def GetNodeReference(self, _role):
        return None


def _production_logic(trajectory, template, parameter):
    sources = {
        "logic_case_bundle.py": {"syncDentoCaseTrajectoryRegistry"},
        "logic_case_validation.py": {"caseBundleWorkflowSummary", "_caseBundleWorkflowSummary"},
    }
    body = []
    for name, wanted in sources.items():
        tree = ast.parse((PY / "dentobot_workflow" / name).read_text())
        body.extend(method for cls in tree.body if isinstance(cls, ast.ClassDef)
                    for method in cls.body if isinstance(method, ast.FunctionDef)
                    and method.name in wanted)
    namespace = {
        "json": json, "fingerprint": state.fingerprint,
        "parse_trajectory_registry": state.parse_trajectory_registry,
        "empty_trajectory_registry": state.empty_trajectory_registry,
        "upsert_trajectory_record": state.upsert_trajectory_record,
        "stale_trajectory_record": state.stale_trajectory_record,
        "upsert_guide_set": state.upsert_guide_set,
        "select_prepared_branch": state.select_prepared_branch,
        "canonical_json": state.canonical_json,
        "REGISTRY_PROVENANCE_FRAME_KEY": state.REGISTRY_PROVENANCE_FRAME_KEY,
        "DENTAL_FDI_TOOTH_IDS": state.DENTAL_FDI_TOOTH_IDS,
        "DENTOCASE_STATE_SCHEMA_VERSION": state.DENTOCASE_STATE_SCHEMA_VERSION,
        "jaw_frame": jaw_frame, "_": lambda text: text,
        "slicer": SimpleNamespace(util=SimpleNamespace(getNodesByClass=lambda kind: (
            [trajectory] if kind == "vtkMRMLMarkupsLineNode" else [template]
        ))),
    }
    module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(
        name="ProductionPaths", bases=[], keywords=[], body=body, decorator_list=[],
    )], type_ignores=[]))
    exec(compile(module, "case-summary-sync-path", "exec"), namespace)

    class Logic(namespace["ProductionPaths"]):
        REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE = "DENTOBOT.RegistryTrajectorySlot"
        REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE = "DENTOBOT.RegistryTrajectoryFingerprint"
        REGISTRY_TARGET_ID_ATTRIBUTE = "DENTOBOT.RegistryTargetID"
        REGISTRY_TRAJECTORY_ID_ATTRIBUTE = "DENTOBOT.RegistryTrajectoryID"
        REGISTRY_GUIDE_SET_ID_ATTRIBUTE = "DENTOBOT.RegistryGuideSetID"
        REGISTRY_TEMPLATE_ID_ATTRIBUTE = "DENTOBOT.RegistryTemplateID"
        REGISTRY_SHELL_ID_ATTRIBUTE = "DENTOBOT.RegistryShellID"
        REGISTRY_BRANCH_REVISION_ATTRIBUTE = "DENTOBOT.PreparedBranchRevision"
        TEMPLATE_FINAL_GUIDE_SOURCE_TRAJECTORY_REFERENCE_ROLE = "source"
        TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE = "shell"
        TEMPLATE_FINAL_GUIDE_TARGET_DOCKING_REFERENCE_ROLE = "dock"
        TEMPLATE_FINAL_GUIDE_RESEARCH_SHELL_REFERENCE_ROLE = "research-shell"
        TEMPLATE_FINAL_GUIDE_RESEARCH_SLEEVE_REFERENCE_ROLE = "research-sleeve"
        TEMPLATE_FINAL_GUIDE_FINALIZED_SHELL_REFERENCE_ROLE = "finalized"
        TEMPLATE_FINAL_GUIDE_DOCKING_REFERENCE_ROLE = "docking"
        TEMPLATE_FINAL_GUIDE_CLEARANCE_REFERENCE_ROLE = "clearance"
        TEMPLATE_FINAL_GUIDE_REINFORCEMENT_REFERENCE_ROLE = "reinforcement"
        TEMPLATE_FINAL_GUIDE_CHANNELS_REFERENCE_ROLE = "channels"

        def isDentobotTrajectoryNode(self, node):
            return node is trajectory

        def getTrajectoryTargetAssociation(self, _node):
            return {"targetRecord": {"fdiNumber": "34", "segmentId": "seg-34"},
                    "segmentationNode": None}

        def ensureDentoCaseTrajectoryIdentity(self, node, _segmentation, _target):
            return node.GetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE), 1

        def _trajectoryRegistryGeometryFingerprint(self, _node, *, legacyWorld=False):
            return "world-fingerprint" if legacyWorld else "jaw-fingerprint"

        def isFinalPrintableTemplateModelNode(self, node):
            return node is template

        def _nodeReferences(self, _node, role):
            return [trajectory] if role == "source" else []

        def isPatientContactShellModelNode(self, _node):
            return False

        def _stableDentoCaseId(self, kind, *_values):
            return {"guide": "guide-fdi34", "template": "template-fdi34",
                    "shell": "shell-fdi34"}[kind]

        def _migrateBranchProvenanceToOwningJawFrame(self, *_args):
            return []

        def _upgradeLegacyStep5CVerification(self, *_args, **_kwargs):
            return False

        def evaluateCaseFoundationEligibility(self, _node):
            return {"pose": {"eligible": True}, "base": {"eligible": False}}

        def robotBaseFingerprint(self, _node):
            return ""

        def isStep6CaseJawTransformNode(self, _node):
            return False

        def step6PlanningContextFreshnessIssues(self, _node):
            return []

    return Logic()


def test_legacy_warning_survives_production_summary_sync_only_at_verified_prefix():
    trajectory = Node("vtkMRMLMarkupsLineNode19", {
        "DENTOBOT.TargetFdiNumber": "34", "DENTOBOT.RegistryTrajectoryID": "trajectory-fdi34",
        "DENTOBOT.RegistryTargetID": "target-fdi34", "DENTOBOT.RegistryTrajectorySlot": "1",
    })
    template = Node("vtkMRMLModelNode47", {
        "DENTOBOT.ModelRole": "FinalPrintableTemplate", "DENTOBOT.GeometryState": "Current",
        "DENTOBOT.UpdatedUtc": "2026-10-05T21:55:55.688013+00:00",
        "DENTOBOT.PlanningPoseFingerprint": "pose-fdi34",
        "DENTOBOT.PairingIntent": "Single",
        "DENTOBOT.VerificationState": "WARNING",
    })

    class Parameter:
        dentoCaseSchemaVersion = "3.0"
        teethSegmentation = None
        step6PlanningContextImported = False

        def __init__(self):
            registry = state.empty_trajectory_registry()
            registry.pop(state.REGISTRY_PROVENANCE_FRAME_KEY)
            self.step6TrajectoryRegistryJson = state.canonical_json(registry)

        def __getattr__(self, name):
            return "" if name.endswith("Json") else 0

    parameter = Parameter()
    summary_tree = ast.parse((PY / "dentobot_workflow/logic_case_validation.py").read_text())
    summary_method = next(method for cls in summary_tree.body if isinstance(cls, ast.ClassDef)
                          for method in cls.body if isinstance(method, ast.FunctionDef)
                          and method.name == "_caseBundleWorkflowSummary")
    fields = next(statement.value for statement in summary_method.body
                  if isinstance(statement, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "fields"
                          for target in statement.targets))
    for field in ast.literal_eval(fields):
        setattr(parameter, field, None)
    logic = _production_logic(trajectory, template, parameter)
    first = logic.syncDentoCaseTrajectoryRegistry(parameter, legacyProvenance=True)
    revision = first["prepared_branches"]["guide-fdi34"]["revision"]
    payload = {"schemaVersion": "1.0", "overall": "WARNING", "preparedBranchId": "guide-fdi34",
               "preparedBranchRevision": revision, "planningPoseFingerprint": "pose-fdi34",
               "finalModelUpdatedUtc": template.GetAttribute("DENTOBOT.UpdatedUtc")}
    template.SetAttribute("DENTOBOT.VerificationJson", state.canonical_json(payload))
    summary = logic.caseBundleWorkflowSummary(parameter, legacyProvenance=True)
    registry = summary["step6"]["trajectoryRegistry"]
    branch = registry["prepared_branches"]["guide-fdi34"]
    assert _legacy_projection_provenance(summary)
    assert branch["revision"] == revision
    assert branch["state"] == "Current"
    assert branch["verification_revision"] == state.fingerprint(payload)
    def audited_verification(record):
        unknown = []
        artifacts = _step5c_verification_artifacts(
            {template.GetID(): template},
            {"registered_branches": {"guide-fdi34"},
             "branch_evidence": {"guide-fdi34": {
                 "template_node_id": template.GetID(), "verification_revision": record["verification_revision"],
                 "revision": record["revision"], "planning_pose_fingerprint": "pose-fdi34",
                 "branch_foundation_fingerprint": "", "branch_foundation_present": False,
             }},
             "branches": {"guide-fdi34": Branch("guide-fdi34", "target-fdi34",
                                              ("trajectory-fdi34",), "Single", record["state"])}},
            {template.GetID(): Artifact(template.GetID(), "template.build", "branch",
                                        "target-fdi34", "guide-fdi34")}, unknown,
        )
        return artifacts, unknown

    artifacts, unknown = audited_verification(branch)
    assert not unknown and [artifact.id for artifact in artifacts] == ["verification:guide-fdi34"]
    verified = filter_registry(registry, "target-fdi34", ("trajectory-fdi34",), "guide-fdi34", 100)
    assert verified["prepared_branches"]["guide-fdi34"]["verification_revision"] == state.fingerprint(payload)
    earlier = filter_registry(registry, "target-fdi34", ("trajectory-fdi34",), "guide-fdi34", 90)
    assert earlier["prepared_branches"]["guide-fdi34"]["verification_revision"] == ""
    _clear_future_node_attributes(template, 90)
    assert template.GetAttribute("DENTOBOT.VerificationState") == "NotVerified"
    assert template.GetAttribute("DENTOBOT.VerificationJson") is None

    # An unrelated revision cannot acquire verification by choosing legacy mode.
    payload["preparedBranchRevision"] = "unrelated-revision"
    template.SetAttribute("DENTOBOT.VerificationState", "WARNING")
    template.SetAttribute("DENTOBOT.VerificationJson", state.canonical_json(payload))
    stale = logic.caseBundleWorkflowSummary(parameter, legacyProvenance=True)
    stale_branch = stale["step6"]["trajectoryRegistry"]["prepared_branches"]["guide-fdi34"]
    assert stale_branch["verification_revision"] == ""
    artifacts, unknown = audited_verification(stale_branch)
    assert not artifacts
    assert unknown == [f"registry has no Step 5C verification revision for template: {template.GetID()}"]
