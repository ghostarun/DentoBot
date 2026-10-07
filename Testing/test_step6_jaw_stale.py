"""S6-MULTI-JAW-STALE-01: a mouth-opening change must not invalidate a PreparedBranch.

Known-answer checks of the real logic methods (extracted from source, run against
small MRML fakes): owning-jaw provenance, legacy migration, Step 5C verification
upgrade, opening-only invalidation and the registry contract.
"""

import ast
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PY))

import DENTOStep6State as state  # noqa: E402
from dentobot_workflow import jaw_frame  # noqa: E402

LOGIC = PY / "dentobot_workflow"
METHODS = {
    "logic_case_foundation.py": {"nodeJawOwner", "owningJawWorldMatrix", "owningJawFrameControlPoint",
                                 "_invalidateCaseFoundationPoseDependents"},
    "logic_case_bundle.py": {"_migrateBranchProvenanceToOwningJawFrame", "_upgradeLegacyStep5CVerification",
                             "_registryWorldPoint"},
    "logic_docking.py": {"canonicalTrajectoryGeometry", "legacyWorldTrajectoryGeometry", "targetDockingFrameWorld"},
}


# ---------------------------------------------------------------- MRML fakes
class Matrix:
    def __init__(self, m=None):
        self.m = np.eye(4) if m is None else np.asarray(m, float)

    def GetElement(self, r, c):
        return float(self.m[r, c])


class Transform:
    def __init__(self, m):
        self.m = np.asarray(m, float)

    def GetMatrixTransformToWorld(self, out):
        out.m = self.m.copy()


class Node:
    _ids = 0

    def __init__(self, attrs=None, parent=None, local=()):
        Node._ids += 1
        self.id = f"node{Node._ids}"
        self.attrs = dict(attrs or {})
        self.parent = parent
        self.local = [np.asarray(p, float) for p in local]
        self.refs = {}

    def GetID(self):
        return self.id

    def GetAttribute(self, key):
        return self.attrs.get(key)

    def SetAttribute(self, key, value):
        if value is None:
            self.attrs.pop(key, None)
        else:
            self.attrs[key] = value

    def GetParentTransformNode(self):
        return self.parent

    def GetNodeReference(self, role):
        return self.refs.get(role)

    def GetNumberOfDefinedControlPoints(self):
        return len(self.local)

    def _world(self, index):
        p = self.local[index]
        return (self.parent.m @ np.r_[p, 1.0])[:3] if self.parent is not None else p

    def GetNthControlPointPosition(self, index, out):
        out[:] = list(self.local[index])

    def GetNthControlPointPositionWorld(self, index, out):
        out[:] = list(self._world(index))


def _opening(theta_deg, shift=(0.0, -3.0, -8.0)):
    t = math.radians(theta_deg)
    m = np.eye(4)
    m[1:3, 1:3] = [[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]]
    m[:3, 3] = shift
    return m


def _load(parameter_node, models=()):
    body = []
    for name, wanted in METHODS.items():
        tree = ast.parse((LOGIC / name).read_text(encoding="utf-8"))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            body.extend(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted)
    assert {f.name for f in body} == set().union(*METHODS.values())
    namespace = {
        "json": json, "np": np, "jaw_frame": jaw_frame, "datetime": datetime, "timezone": timezone,
        "logging": SimpleNamespace(info=lambda *a, **k: None), "_": lambda text: text,
        "vtk": SimpleNamespace(vtkMatrix4x4=Matrix),
        "slicer": SimpleNamespace(util=SimpleNamespace(getNodesByClass=lambda cls: list(models))),
    }
    module = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(
        name="Logic", bases=[], keywords=[], body=body, decorator_list=[])], type_ignores=[]))
    exec(compile(module, "jaw-stale-logic", "exec"), namespace)
    Logic = namespace["Logic"]

    class Harness(Logic):
        LINEAGE_TARGET_SEGMENT_ATTRIBUTE = "DENTOBOT.LineageTargetSegmentID"
        TARGET_DOCKING_REFERENCE_PLANE_REFERENCE_ROLE = "plane"
        _staticmethods = ()

        def __init__(self):
            self.calls = []

        def getParameterNode(self):
            return parameter_node

        def _targetJawOwner(self, node, segment_id):
            return {"lower": "MovingLower", "upper": "FixedUpper"}.get(segment_id, "")

        def getTrajectorySummary(self, node):
            a, b = [0.0] * 3, [0.0] * 3
            node.GetNthControlPointPositionWorld(0, a)
            node.GetNthControlPointPositionWorld(1, b)
            return {"entryRas": a, "targetRas": b}

        def isTargetDockingAssemblyModelNode(self, node):
            return node.GetAttribute("role") == "dock"

        def isFinalPrintableTemplateModelNode(self, node):
            return node.GetAttribute("role") == "final"

        def getTemplateInsertionDirectionSummary(self, node):
            raise ValueError("no insertion in this fixture")

        def evaluateCaseFoundationEligibility(self, node):
            return {"pose": {"eligible": True}, "planning_pose_fingerprint": "pose-B",
                    "branch_foundation_fingerprint": "branch-F"}

        def syncDentoCaseTrajectoryRegistry(self, node):
            self.calls.append("sync")

        def invalidateStep6TaskConfirmation(self, node, reason, makeBaseStale=False):
            self.calls.append(("task", makeBaseStale))

        def deleteRobotWorkspaceModel(self):
            self.calls.append("workspace")

        def _staleVirtualForeheadPrior(self, node, reason):
            self.calls.append("forehead")

    # staticmethods keep their decorator when extracted; nothing else to bind.
    return Harness()


def _lower_trajectory(jaw):
    return Node({"DENTOBOT.JawOwner": "MovingLower"}, parent=jaw, local=[(10, 20, 40), (10, 20, 30)])


def _dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------- tests
def test_lower_trajectory_provenance_is_opening_invariant_and_upper_is_world():
    jaw = Transform(_opening(10.0))
    node = SimpleNamespace(step6CaseJawTransform=jaw)
    logic = _load(node)
    lower = _lower_trajectory(jaw)
    upper = Node({"DENTOBOT.JawOwner": "FixedUpper"}, local=[(1, 2, 3), (4, 5, 6)])
    before = logic.canonicalTrajectoryGeometry([lower, upper])
    legacy_before = logic.legacyWorldTrajectoryGeometry([lower])
    jaw.m = _opening(17.5)
    assert logic.canonicalTrajectoryGeometry([lower, upper]) == before          # no false staleness
    assert logic.legacyWorldTrajectoryGeometry([lower]) != legacy_before        # the old world rule moved
    assert before[0]["entryRas"] == [10.0, 20.0, 40.0]                          # closed-mouth (jaw-local)
    assert before[1]["entryRas"] == [1.0, 2.0, 3.0]                             # upper: world RAS


def test_unparented_lower_node_is_mapped_through_the_jaw_matrix():
    jaw = Transform(_opening(12.0))
    logic = _load(SimpleNamespace(step6CaseJawTransform=jaw))
    hardened = Node({"DENTOBOT.JawOwner": "MovingLower"}, local=[tuple(jaw.m @ np.r_[10, 20, 40, 1.0])[:3]])
    point = logic.owningJawFrameControlPoint(SimpleNamespace(step6CaseJawTransform=jaw), hardened, 0)
    assert np.allclose(point, [10, 20, 40])


def _branch(jaw, *, stamped_opening):
    """A legacy branch recorded in world RAS at ``stamped_opening`` (pre-2026-10-07)."""
    trajectory = _lower_trajectory(jaw)
    saved = jaw.m.copy()
    jaw.m = stamped_opening
    legacy_logic = _load(SimpleNamespace(step6CaseJawTransform=jaw))
    world_json = _dumps(legacy_logic.legacyWorldTrajectoryGeometry([trajectory]))
    frame_local = {"originRas": [10.0, 20.0, 30.0], "zAxisRas": [0.0, 0.0, 1.0],
                   "matrixColumnMajorRas": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 20, 30, 1]}
    frame_world = jaw_frame.to_world(frame_local, stamped_opening)
    jaw.m = saved
    dock = Node({"role": "dock", "DENTOBOT.TargetSegmentId": "lower", "DENTOBOT.TrajectoryGeometryJson": world_json,
                 "DENTOBOT.FrameJson": _dumps(frame_world)}, parent=jaw)
    final = Node({"role": "final", "DENTOBOT.TrajectoryGeometryJson": world_json,
                  "DENTOBOT.PlanningPoseFingerprint": "pose-B"})
    return trajectory, dock, final, frame_local


def test_legacy_records_at_the_current_opening_migrate_and_then_follow_the_jaw():
    jaw = Transform(_opening(10.0))
    node = SimpleNamespace(step6CaseJawTransform=jaw)
    logic = _load(node)
    trajectory, dock, final, frame_local = _branch(jaw, stamped_opening=jaw.m.copy())
    migrated = logic._migrateBranchProvenanceToOwningJawFrame(node, final, [trajectory], [final, dock], None)
    jaw_json = _dumps(logic.canonicalTrajectoryGeometry([trajectory]))
    assert final.attrs["DENTOBOT.TrajectoryGeometryJson"] == jaw_json
    assert dock.attrs["DENTOBOT.TrajectoryGeometryJson"] == jaw_json
    assert dock.attrs[jaw_frame.PROVENANCE_FRAME_ATTRIBUTE] == jaw_frame.OWNING_JAW_FRAME
    assert final.attrs[jaw_frame.BRANCH_FOUNDATION_ATTRIBUTE] == "branch-F"
    assert len(migrated) == 4
    assert logic._migrateBranchProvenanceToOwningJawFrame(node, final, [trajectory], [final, dock], None) == []
    # The opening changes: provenance still matches, the dock frame follows the jaw for construction.
    jaw.m = _opening(19.0)
    assert _dumps(logic.canonicalTrajectoryGeometry([trajectory])) == jaw_json
    frame = logic.targetDockingFrameWorld(dock)
    assert np.allclose(frame["originRas"], (jaw.m @ np.r_[frame_local["originRas"], 1.0])[:3])


def test_legacy_records_from_another_opening_are_not_migrated():
    jaw = Transform(_opening(10.0))
    node = SimpleNamespace(step6CaseJawTransform=jaw)
    logic = _load(node)
    trajectory, dock, final, _local = _branch(jaw, stamped_opening=_opening(4.0))
    before = dict(dock.attrs)
    logic._migrateBranchProvenanceToOwningJawFrame(node, final, [trajectory], [final, dock], None)
    assert dock.attrs == before  # stays stale, exactly as before the change
    assert final.attrs["DENTOBOT.TrajectoryGeometryJson"] != _dumps(logic.canonicalTrajectoryGeometry([trajectory]))


def _verification(**extra):
    return {"overall": "PASS", "preparedBranchRevision": "legacy-rev", "planningPoseFingerprint": "pose-B", **extra}


def test_step5c_verification_is_upgraded_only_when_it_matched_under_the_legacy_rules():
    logic = _load(SimpleNamespace(step6CaseJawTransform=None))
    upgrade = logic._upgradeLegacyStep5CVerification
    final = Node({"DENTOBOT.VerificationJson": _dumps(_verification())})
    assert upgrade(final, legacyRevision="legacy-rev", branchRevision="new-rev",
                   planningPoseFingerprint="pose-B", branchFoundationFingerprint="branch-F")
    record = json.loads(final.attrs["DENTOBOT.VerificationJson"])
    assert record["preparedBranchRevision"] == "new-rev" and record["branchFoundationFingerprint"] == "branch-F"
    assert record["provenanceUpgrade"]["legacyPreparedBranchRevision"] == "legacy-rev"
    assert record["overall"] == "PASS"
    assert not upgrade(final, legacyRevision="legacy-rev", branchRevision="x",
                       planningPoseFingerprint="pose-B", branchFoundationFingerprint="branch-F")  # idempotent
    for bad in ({"legacyRevision": "other"}, {"planningPoseFingerprint": "pose-A"},
                {"branchFoundationFingerprint": ""}):
        stale = Node({"DENTOBOT.VerificationJson": _dumps(_verification())})
        kwargs = {"legacyRevision": "legacy-rev", "branchRevision": "new-rev",
                  "planningPoseFingerprint": "pose-B", "branchFoundationFingerprint": "branch-F", **bad}
        assert not upgrade(stale, **kwargs)
        assert json.loads(stale.attrs["DENTOBOT.VerificationJson"]) == _verification()


def test_opening_only_invalidation_keeps_step5c_but_still_invalidates_step6():
    final = Node({"role": "final", "DENTOBOT.VerificationState": "PASS",
                  "DENTOBOT.VerificationJson": _dumps(_verification())})
    logic = _load(SimpleNamespace(step6CaseJawTransform=None), models=[final])
    logic._invalidateCaseFoundationPoseDependents(None, "opening", openingOnly=True)
    assert final.attrs["DENTOBOT.VerificationState"] == "PASS"
    assert ("task", True) in logic.calls and "workspace" in logic.calls
    logic._invalidateCaseFoundationPoseDependents(None, "source changed")
    assert final.attrs["DENTOBOT.VerificationState"] == "NotVerified"
    assert "DENTOBOT.VerificationJson" not in final.attrs


def test_registry_marks_owning_jaw_provenance_and_keeps_legacy_registries_recognisable():
    empty = state.empty_trajectory_registry()
    assert empty[state.REGISTRY_PROVENANCE_FRAME_KEY] == state.REGISTRY_PROVENANCE_FRAME
    legacy = state.empty_trajectory_registry()
    legacy.pop(state.REGISTRY_PROVENANCE_FRAME_KEY)
    assert state.REGISTRY_PROVENANCE_FRAME_KEY not in state.parse_trajectory_registry(legacy)
    migrated_v1 = state.parse_trajectory_registry({"schema_version": "1.0", "teeth": empty["teeth"]})
    assert state.REGISTRY_PROVENANCE_FRAME_KEY not in migrated_v1


def test_eligibility_binds_to_the_opening_independent_foundation_identity():
    source = (LOGIC / "logic_case_bundle.py").read_text(encoding="utf-8")
    eligibility = source[source.index("def evaluatePreparedBranchEligibility"):]
    eligibility = eligibility[:eligibility.index("\n    def ", 10)]
    assert 'foundation["branch_foundation_fingerprint"]' in eligibility
    assert 'verification.get("branchFoundationFingerprint")' in eligibility
    assert 'foundation["planning_pose_fingerprint"]' not in eligibility
    assert 'verification.get("planningPoseFingerprint")' not in eligibility


def test_case_registry_audit_preserves_legacy_and_requires_matching_migration():
    path = LOGIC / "logic_case_validation.py"
    tree = ast.parse(path.read_text())
    method = next(n for cls in tree.body if isinstance(cls, ast.ClassDef)
                  for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_caseBundleRegistryForAudit")
    namespace = {"REGISTRY_PROVENANCE_FRAME_KEY": state.REGISTRY_PROVENANCE_FRAME_KEY,
                 "canonical_json": state.canonical_json,
                 "parse_trajectory_registry": state.parse_trajectory_registry,
                 "CaseBundleError": ValueError}
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    audit = namespace["_caseBundleRegistryForAudit"]
    legacy = state.empty_trajectory_registry()
    legacy.pop(state.REGISTRY_PROVENANCE_FRAME_KEY)
    migrated = state.empty_trajectory_registry()
    logic = SimpleNamespace()
    assert audit(logic, legacy, postHydration=False) == (legacy, True)
    with pytest.raises(ValueError, match="No validated registry migration"):
        audit(logic, legacy, postHydration=True)
    logic._caseBundleRegistryMigrationAudit = (state.canonical_json(legacy), state.canonical_json(migrated))
    assert audit(logic, legacy, postHydration=True) == (migrated, False)
    changed = dict(legacy, selected_branch_id="different")
    with pytest.raises(ValueError, match="No validated registry migration"):
        audit(logic, changed, postHydration=True)
    assert audit(logic, migrated, postHydration=True) == (migrated, False)
    # The migration proof is frozen, not a reference to a mutable live registry.
    returned, _ = audit(logic, legacy, postHydration=True)
    returned["selected_branch_id"] = "changed-after-hydration"
    assert audit(logic, legacy, postHydration=True) == (migrated, False)


@pytest.mark.parametrize("legacy", [True, False])
def test_case_summary_does_not_migrate_legacy_registry_during_integrity_audit(legacy):
    path = LOGIC / "logic_case_validation.py"
    tree = ast.parse(path.read_text())
    method = next(n for cls in tree.body if isinstance(cls, ast.ClassDef)
                  for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_caseBundleWorkflowSummary")
    namespace = {"json": json, "DENTOCASE_STATE_SCHEMA_VERSION": "3.0"}
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)

    class Parameter:
        teethSegmentation = None
        dentoCaseSchemaVersion = "3.0"
        step6TrajectoryRegistryJson = ""

        def __getattr__(self, name):
            return "" if name.endswith("Json") else 0

    parameter = Parameter()
    fields = next(n.value for n in method.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "fields" for t in n.targets))
    for field in ast.literal_eval(fields):
        setattr(parameter, field, None)
    registry = state.empty_trajectory_registry()
    if legacy:
        registry.pop(state.REGISTRY_PROVENANCE_FRAME_KEY)
    calls = []

    def sync(node, *, legacyProvenance=False):
        calls.append(("sync", legacyProvenance))
        node.step6TrajectoryRegistryJson = state.canonical_json(registry)
        return registry

    def freshness(node):
        calls.append(("freshness",))
        # Reproduce the production readiness helper's current-provenance sync.
        node.step6TrajectoryRegistryJson = state.canonical_json(state.empty_trajectory_registry())
        return ["not ready"]

    logic = SimpleNamespace(
        evaluateCaseFoundationEligibility=lambda node: {
            "pose": {"eligible": False}, "base": {"eligible": False}},
        syncDentoCaseTrajectoryRegistry=sync,
        robotBaseFingerprint=lambda node: "",
        isStep6CaseJawTransformNode=lambda node: False,
        step6PlanningContextFreshnessIssues=freshness,
    )
    summary = namespace["_caseBundleWorkflowSummary"](
        logic, parameter, legacyProvenance=legacy)["step6"]
    assert summary["trajectoryRegistry"] == registry
    assert calls == ([("sync", True)] if legacy
                     else [("sync", False), ("freshness",)])
    assert summary["freshnessIssuesAtSave"] == (None if legacy else ["not ready"])


def _migration_node_audit_fixture():
    import copy
    path = LOGIC / "logic_case_validation.py"
    tree = ast.parse(path.read_text())
    methods = [n for cls in tree.body if isinstance(cls, ast.ClassDef)
               for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in {"_caseBundleRegistryForAudit", "_caseBundleNodeRecordForAudit"}]
    namespace = {"copy": copy, "REGISTRY_PROVENANCE_FRAME_KEY": state.REGISTRY_PROVENANCE_FRAME_KEY,
                 "canonical_json": state.canonical_json,
                 "parse_trajectory_registry": state.parse_trajectory_registry,
                 "CaseBundleError": ValueError}
    module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    legacy = state.empty_trajectory_registry()
    legacy.pop(state.REGISTRY_PROVENANCE_FRAME_KEY)
    tooth = legacy["teeth"]["FDI11"]
    tooth["target_id"] = "target-11"
    tooth["segment_id"] = "segment-11"
    tooth["trajectory_set"]["slots"][0].update(
        trajectory_id="trajectory-11", target_id="target-11", state="Current",
        trajectory_node_id="line-11", trajectory_fingerprint="old-world-fingerprint")
    migrated = copy.deepcopy(legacy)
    migrated[state.REGISTRY_PROVENANCE_FRAME_KEY] = state.REGISTRY_PROVENANCE_FRAME
    migrated["teeth"]["FDI11"]["trajectory_set"]["slots"][0]["trajectory_fingerprint"] = "new-jaw-fingerprint"
    logic = SimpleNamespace(
        REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE="fingerprint",
        REGISTRY_TRAJECTORY_ID_ATTRIBUTE="trajectory_id",
        REGISTRY_TARGET_ID_ATTRIBUTE="target_id",
        REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE="slot",
        _caseBundleRegistryMigrationAudit=(state.canonical_json(legacy), state.canonical_json(migrated)),
    )
    logic._caseBundleRegistryForAudit = lambda *a, **kw: namespace["_caseBundleRegistryForAudit"](logic, *a, **kw)
    record = {"field": "trajectoryLine", "id": "line-11",
              "controlPointsWorldRasMm": [[1, 2, 3], [4, 5, 6]],
              "attributes": {"fingerprint": "old-world-fingerprint", "trajectory_id": "trajectory-11",
                             "target_id": "target-11", "slot": "1", "unrelated": "unchanged"}}
    audit = lambda value, **kw: namespace["_caseBundleNodeRecordForAudit"](logic, value, legacy, **kw)
    return logic, record, audit


def test_node_audit_translates_only_frozen_validated_trajectory_fingerprint():
    import copy
    logic, record, audit = _migration_node_audit_fixture()
    original = copy.deepcopy(record)
    assert audit(record, postHydration=False) is record
    expected = copy.deepcopy(record)
    expected["attributes"]["fingerprint"] = "new-jaw-fingerprint"
    assert audit(record, postHydration=True) == expected
    assert record == original
    logic._caseBundleRegistryMigrationAudit = None
    with pytest.raises(ValueError, match="No validated registry migration"):
        audit(record, postHydration=True)


@pytest.mark.parametrize("field,value", [("fingerprint", "tampered"), ("trajectory_id", "other"),
                                         ("target_id", "other"), ("slot", "2"), ("id", "other")])
def test_node_audit_rejects_changed_legacy_lineage(field, value):
    _logic, record, audit = _migration_node_audit_fixture()
    if field == "id":
        record[field] = value
    else:
        record["attributes"][field] = value
    with pytest.raises(ValueError, match="Trajectory lineage does not match"):
        audit(record, postHydration=True)


def _restore_sync_methods():
    path = LOGIC / "logic_case_bundle.py"
    tree = ast.parse(path.read_text())
    methods = [n for cls in tree.body if isinstance(cls, ast.ClassDef)
               for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in {"syncDentoCaseTrajectoryRegistry", "hydrateDentoCaseStateAfterLoad"}]
    environment = SimpleNamespace(to_dict=lambda: {})
    namespace = {"json": json, "canonical_json": state.canonical_json,
                 "parse_trajectory_registry": state.parse_trajectory_registry,
                 "empty_trajectory_registry": state.empty_trajectory_registry,
                 "REGISTRY_PROVENANCE_FRAME_KEY": state.REGISTRY_PROVENANCE_FRAME_KEY,
                 "parse_robot_environment_snapshot": lambda payload: environment,
                 "LEGACY_DENTOCASE_STATE_SCHEMA_VERSIONS": {"1.0", "2.0"},
                 "DENTOCASE_STATE_SCHEMA_VERSION": "3.0", "CaseBundleError": ValueError,
                 "logging": SimpleNamespace(info=lambda *a: None, warning=lambda *a: None),
                 "_": lambda text: text,
                 "slicer": SimpleNamespace(util=SimpleNamespace(getNodesByClass=lambda cls: []))}
    module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    class Parameter:
        step6EnvironmentJson = "{}"
        def __getattr__(self, name):
            return None
    parameter = Parameter()
    legacy = state.empty_trajectory_registry()
    legacy.pop(state.REGISTRY_PROVENANCE_FRAME_KEY)
    parameter.step6TrajectoryRegistryJson = state.canonical_json(legacy)
    logic = SimpleNamespace(_caseBundleRestoreDepth=1,
                            buildDentoCaseRobotEnvironment=lambda node: environment,
                            isStep6CaseJawTransformNode=lambda node: False,
                            isRobotBaseTransformNode=lambda node: False)
    sync = namespace["syncDentoCaseTrajectoryRegistry"]
    logic.syncDentoCaseTrajectoryRegistry = lambda node, **kw: sync(logic, node, **kw)
    return namespace, parameter, legacy, logic


def test_queued_readiness_sync_cannot_migrate_before_hydration_proof():
    namespace, parameter, legacy, logic = _restore_sync_methods()
    # Default GUI/readiness calls inside the barrier preserve the saved bytes.
    assert logic.syncDentoCaseTrajectoryRegistry(parameter) == legacy
    assert parameter.step6TrajectoryRegistryJson == state.canonical_json(legacy)
    namespace["hydrateDentoCaseStateAfterLoad"](logic, parameter, "3.0")
    before, after = logic._caseBundleRegistryMigrationAudit
    assert before == state.canonical_json(legacy)
    assert state.REGISTRY_PROVENANCE_FRAME_KEY in state.parse_trajectory_registry(after)
    assert logic._caseBundleRegistryMigrationAllowed is False
    # Once hydrated, ordinary callbacks keep the current provenance.
    assert state.REGISTRY_PROVENANCE_FRAME_KEY in logic.syncDentoCaseTrajectoryRegistry(parameter)


def test_normal_sync_outside_restore_still_migrates_legacy_registry():
    _namespace, parameter, _legacy, logic = _restore_sync_methods()
    logic._caseBundleRestoreDepth = 0
    assert state.REGISTRY_PROVENANCE_FRAME_KEY in logic.syncDentoCaseTrajectoryRegistry(parameter)


def test_restore_barrier_mirrors_nested_depth_and_ignores_obsolete_end():
    path = LOGIC / "widget_case_backend.py"
    tree = ast.parse(path.read_text())
    methods = [n for cls in tree.body if isinstance(cls, ast.ClassDef)
               for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in {"_beginCaseBundleRestore", "_endCaseBundleRestore"}]
    namespace = {"logging": SimpleNamespace(warning=lambda *a: None)}
    module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
    exec(compile(module, str(path), "exec"), namespace)
    widget = SimpleNamespace(_caseBundleRestoreDepth=0, _caseBundleRestoreGeneration=0,
                             _restoreStageExclusiveInteractionLocks=lambda: None,
                             logic=SimpleNamespace(), _parameterNode=None)
    begin = lambda: namespace["_beginCaseBundleRestore"](widget)
    end = lambda generation: namespace["_endCaseBundleRestore"](widget, generation)
    one, two = begin(), begin()
    assert widget.logic._caseBundleRestoreDepth == 2
    end(one)
    assert widget.logic._caseBundleRestoreDepth == 2
    end(two)
    assert widget.logic._caseBundleRestoreDepth == 1
    end(two)
    assert widget.logic._caseBundleRestoreDepth == 0
