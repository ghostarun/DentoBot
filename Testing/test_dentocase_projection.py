"""Pure unit checks for fresh saved-case projection plans."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
import os
from io import StringIO
import sys
from pathlib import Path
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))

from DENTOStep6State import REGISTRY_PROVENANCE_FRAME_KEY  # noqa: E402
from dentobot_case.contracts import Artifact, Branch, CaseInventory, CHECKPOINTS  # noqa: E402
from dentobot_case.ownership import DEFAULTS, RESUME_INDICES  # noqa: E402
from dentobot_case.projection import filter_registry, prepare_projection  # noqa: E402
from dentobot_workflow.case_projection import (  # noqa: E402
    _clear_future_node_attributes, _inspect_prefix, _replan_restored_projection,
    _legacy_projection_provenance,
    _check_projector_result, _log_projected_unknown_ownership,
    _new_projector_evidence_dir, _offline_child_workspace,
    _record_projected_ownership_failure,
    _retain_failed_projected_scene, _retain_projector_log,
)


def test_projection_uses_validated_registry_provenance_without_promoting_unknown_evidence():
    legacy = _registry()
    workflow = {"step6": {"trajectoryRegistry": legacy}}
    assert _legacy_projection_provenance(workflow)
    selected = filter_registry(legacy, "target-1", ("trajectory-1",), "branch-1", 100)
    assert selected["prepared_branches"]["branch-1"]["verification_revision"] == "saved-5c"
    # A pre-verification prefix must still discard saved verification authority.
    early = filter_registry(legacy, "target-1", ("trajectory-1",), "branch-1", 90)
    assert early["prepared_branches"]["branch-1"]["verification_revision"] == ""
    current = deepcopy(legacy)
    current[REGISTRY_PROVENANCE_FRAME_KEY] = "OwningJawRASmm"
    assert not _legacy_projection_provenance({"step6": {"trajectoryRegistry": current}})
    with pytest.raises(ValueError, match="registry is malformed"):
        _legacy_projection_provenance({"step6": {"trajectoryRegistry": None}})


def _inventory() -> CaseInventory:
    artifacts = (
        Artifact("source", "source.volume", "shared", role="inputVolume"),
        Artifact(
            "segmentation", "anatomy.segmentation", "shared",
            role="teethSegmentation", dependencies=("source",),
        ),
    )
    projection = {
        "version": "1.0",
        "parameterNodeId": "parameter",
        "nodeIds": ["parameter", "source-node", "future-node", "runtime-node", "history-node", "display-node"],
        "nodeOwners": {
            "parameter": [],
            "source-node": ["source"],
            "future-node": ["segmentation"],
            "runtime-node": ["@runtime"],
            "history-node": ["@history"],
            "display-node": ["@display"],
        },
        "parameterOwners": {
            "current": "source.volume",
            "future": "anatomy.segmentation",
            "runtime": "runtime",
            "history": "history",
            "identity": "identity",
            "navigation": "navigation",
            "registry": "registry",
            "displaySetting": "display",
            "shared": "shared",
        },
        "referenceOwners": {
            "futureReference": "anatomy.segmentation",
            "runtimeReference": "runtime",
            "historyReference": "history",
            "registryReference": "registry",
            "displayReference": "display",
            "sharedReference": "shared",
        },
        "resumeIndices": {"source.volume": 0},
        "defaults": {"future": "", "runtime": "", "history": ""},
    }
    return CaseInventory(
        path="case.dentocase",
        package_id="package",
        case_id="source-case",
        label="Case",
        archive_schema="1.0",
        package_sha256="a" * 64,
        checked_at_utc="2026-10-01T00:00:00Z",
        target_ids=("target-1",),
        artifacts=artifacts,
        ownership_complete=True,
        metadata={"projection": projection},
    )


def _registry() -> dict:
    registry = {
        "schema_version": "3.0",
        "teeth": {
            f"FDI{quadrant}{tooth}": {
                "target_id": "",
                "segment_id": "",
                "trajectory_set": {
                    "slots": [
                        {"slot": slot, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []}
                        for slot in range(1, 4)
                    ]
                },
            }
            for quadrant in range(1, 5)
            for tooth in range(1, 9)
        },
        "prepared_branches": {},
        "selected_branch_id": "",
    }
    tooth = registry["teeth"]["FDI11"]
    tooth["target_id"] = "target-1"
    tooth["segment_id"] = "segment-1"
    slots = tooth["trajectory_set"]["slots"]
    slots[0].update({
        "state": "Current", "target_id": "target-1", "trajectory_id": "trajectory-1",
        "trajectory_node_id": "node-trajectory-1", "trajectory_fingerprint": "fingerprint-1",
        "provenance": "manual", "evidence_state": "Unreviewed", "stale_reason": "",
    })
    slots[1].update({
        "state": "Current", "target_id": "target-1", "trajectory_id": "trajectory-2",
        "trajectory_node_id": "node-trajectory-2", "trajectory_fingerprint": "fingerprint-2",
        "provenance": "manual", "evidence_state": "Unreviewed", "stale_reason": "",
    })
    registry["prepared_branches"] = {
        "branch-1": {
            "branch_id": "branch-1", "target_id": "target-1",
            "trajectory_ids": ["trajectory-1"], "primary_trajectory_id": "trajectory-1",
            "pairing_intent": "Single", "target_docking_node_id": "dock",
            "insertion_direction_node_id": "insertion", "template_id": "template",
            "template_node_id": "node-template", "shell_id": "shell",
            "shell_node_id": "node-shell", "model_node_ids": ["node-template"],
            "revision": "revision", "verification_revision": "saved-5c",
            "planning_pose_fingerprint": "pose", "state": "Current", "stale_reason": "",
        }
    }
    slots[0]["prepared_branch_ids"] = ["branch-1"]
    registry["selected_branch_id"] = "branch-1"
    return registry


def test_prepare_projection_closes_nodes_and_resets_future_state_without_mutating_inventory():
    inventory = _inventory()
    source = deepcopy(inventory.metadata)

    plan = prepare_projection(inventory, "target-1", "source.volume")

    assert plan["keepNodeIds"] == ["display-node", "parameter", "source-node"]
    assert plan["removeNodeIds"] == ["future-node", "history-node", "runtime-node"]
    assert plan["clearParameters"] == ["future", "history", "runtime"]
    assert plan["clearReferenceRoles"] == [
        "displayReference", "futureReference", "historyReference", "runtimeReference",
    ]
    assert plan["defaults"] == {"future": "", "history": "", "runtime": ""}
    assert plan["workflowStageIndex"] == 0
    assert plan["historyPolicy"] == "Fresh"
    assert plan["newCaseId"] != inventory.case_id
    assert inventory.metadata == source


def test_prepare_projection_blocks_incomplete_or_unknown_ownership():
    inventory = _inventory()
    inventory.metadata["projection"]["nodeOwners"]["future-node"] = ["missing-artifact"]
    try:
        prepare_projection(inventory, "target-1", "source.volume")
    except ValueError as exc:
        assert "inventory artifact" in str(exc)
    else:
        raise AssertionError("unknown node ownership must block projection")

    inventory.metadata["projection"]["nodeOwners"]["future-node"] = ["segmentation"]
    del inventory.metadata["projection"]["resumeIndices"]["source.volume"]
    try:
        prepare_projection(inventory, "target-1", "source.volume")
    except ValueError as exc:
        assert "resume index" in str(exc)
    else:
        raise AssertionError("missing resume index must block projection")


def test_verified_prefix_keeps_foundation_geometry_but_resets_step6_authority():
    artifacts = []
    first_by_checkpoint = {}
    for checkpoint in CHECKPOINTS:
        if checkpoint.order > 100:
            break
        for role in checkpoint.artifact_roles:
            artifact_id = f"{checkpoint.id}:{role}"
            dependencies = tuple(first_by_checkpoint[item] for item in checkpoint.requires)
            artifacts.append(Artifact(
                artifact_id, checkpoint.id, checkpoint.scope,
                target_id="target-1" if checkpoint.scope != "shared" else "",
                branch_id="branch-1" if checkpoint.scope == "branch" else "",
                role=role, dependencies=dependencies,
                trajectory_ids=("trajectory-1",) if checkpoint.id == "trajectory.plan" else (),
            ))
            first_by_checkpoint.setdefault(checkpoint.id, artifact_id)
    artifacts.append(Artifact(
        "other-target-template", "template.build", "branch", "target-2", "branch-2",
        role="finalPrintableTemplateModel",
    ))
    parameter_names = (
        "robotBaseMountLocked", "step6BasePlacementStatus", "step6BasePlacementSource",
        "step6BasePlacementRevision", "step6BasePlacementHighWater", "step6EnvironmentJson",
        "step6TaskHomeJson",
    )
    projection = {
        "version": "1.0", "parameterNodeId": "parameter",
        "nodeIds": ["parameter", *[item.id for item in artifacts], "research-config"],
        "nodeOwners": {
            "parameter": [], "research-config": ["@history"],
            **{item.id: [item.id] for item in artifacts},
        },
        "parameterOwners": {
            **{name: ("simulation.home" if name == "step6TaskHomeJson" else "foundation.base")
               for name in parameter_names},
        },
        "referenceOwners": {
            "caseFoundationFixedUpperVolume": "foundation.pose",
            "caseFoundationMovingLowerVolume": "foundation.pose",
        },
        "resumeIndices": dict(RESUME_INDICES),
        "defaults": {name: DEFAULTS[name] for name in parameter_names},
    }
    inventory = CaseInventory(
        path="case.dentocase", package_id="package", case_id="source-case", label="Case",
        archive_schema="3.0", package_sha256="a" * 64,
        checked_at_utc="2026-10-01T00:00:00Z", target_ids=("target-1", "target-2"),
        artifacts=tuple(artifacts),
        branches=(Branch("branch-1", "target-1", ("trajectory-1",), "Single", "Current"),
                  Branch("branch-2", "target-2", ("trajectory-2",), "Single", "Current")),
        ownership_complete=True, metadata={"projection": projection},
    )
    plan = prepare_projection(inventory, "target-1", "template.verify", "branch-1")
    assert "foundation.pose:step6CaseJawTransform" in plan["keepNodeIds"]
    assert "foundation.base:robotBaseTransform" in plan["keepNodeIds"]
    assert "template.build:finalPrintableTemplateModel" in plan["keepNodeIds"]
    assert "research-config" in plan["removeNodeIds"]
    assert "other-target-template" in plan["removeNodeIds"]
    assert set(parameter_names) <= set(plan["clearParameters"])
    assert set(projection["referenceOwners"]) <= set(plan["clearReferenceRoles"])


def test_incomplete_schema3_source_defers_selection_until_restored_scene_audit(monkeypatch, tmp_path):
    source = tmp_path / "source.dentocase"
    source.write_bytes(b"fixture")
    destination = tmp_path / "partial.dentocase"
    inventory = replace(_inventory(), archive_schema="3.0", ownership_complete=False,
                        unknown_ownership=("unmapped saved node",))
    monkeypatch.setattr("dentobot_case.inspection.inspect_package", lambda _path: inventory)
    result, actual_source, actual_destination = _inspect_prefix(
        source, destination, "target-1", "source.volume", "",
    )
    assert result is inventory
    assert actual_source == source and actual_destination == destination

    blocked = replace(inventory, archive_schema="2.0")
    monkeypatch.setattr("dentobot_case.inspection.inspect_package", lambda _path: blocked)
    with pytest.raises(ValueError, match="cannot be re-audited"):
        _inspect_prefix(source, destination, "target-1", "source.volume", "")


def test_complete_schema3_source_defers_stale_saved_plan_until_restored_audit(monkeypatch, tmp_path):
    source = tmp_path / "source.dentocase"
    source.write_bytes(b"fixture")
    inventory = replace(_inventory(), archive_schema="3.0")
    inventory.metadata["projection"]["resumeIndices"].pop("source.volume")
    monkeypatch.setattr("dentobot_case.inspection.inspect_package", lambda _path: inventory)

    result, actual_source, destination = _inspect_prefix(
        source, tmp_path / "partial.dentocase", "target-1", "source.volume", "",
    )
    assert result is inventory
    assert actual_source == source
    assert destination == tmp_path / "partial.dentocase"


@pytest.mark.parametrize("complete_at_save", [True, False])
def test_restored_audit_replans_from_fresh_full_ownership_contract(monkeypatch, complete_at_save):
    @dataclass
    class Inspection:
        workflow: dict

    fresh = _inventory()
    actual_mapping = deepcopy(fresh.metadata["projection"])
    saved_mapping = deepcopy(actual_mapping)
    saved_mapping["parameterOwners"]["future"] = "shared"
    saved_mapping["referenceOwners"]["futureReference"] = "shared"
    saved_mapping["defaults"]["future"] = "stale"
    saved_mapping["resumeIndices"]["source.volume"] = 7
    saved = replace(fresh, ownership_complete=complete_at_save,
                    metadata={"projection": saved_mapping})
    actual_inventory = {"ownershipComplete": True, "unknownOwnership": []}
    observed = []

    def fresh_inventory(_source, inspection, _digest, _source_stat):
        observed.append(inspection.workflow)
        return replace(fresh, metadata={"projection": inspection.workflow["projectionOwnership"]})

    monkeypatch.setattr("dentobot_case.inspection.inventory_from_inspection", fresh_inventory)
    inventory, mapping, plan = _replan_restored_projection(
        "source.dentocase", Inspection({"caseLabel": "Case"}), "digest", None,
        saved, actual_inventory, actual_mapping, "target-1", "source.volume", "",
    )
    assert observed[0]["checkpointInventory"] is actual_inventory
    assert observed[0]["projectionOwnership"] is actual_mapping
    assert inventory.metadata["projection"] is actual_mapping
    assert mapping is actual_mapping
    assert "future" in plan["clearParameters"]
    assert "futureReference" in plan["clearReferenceRoles"]
    assert plan["defaults"]["future"] == ""
    assert plan["workflowStageIndex"] == 0
    assert saved.metadata["projection"] == saved_mapping


def test_restored_audit_rejects_changed_persistent_owner_before_replanning(monkeypatch):
    @dataclass
    class Inspection:
        workflow: dict

    saved = _inventory()
    actual_mapping = deepcopy(saved.metadata["projection"])
    actual_mapping["nodeOwners"]["future-node"] = ["source"]
    monkeypatch.setattr("dentobot_case.inspection.inventory_from_inspection",
                        lambda *_args: pytest.fail("mismatched owner must not be replanned"))
    with pytest.raises(ValueError, match="Restored persistent ownership differs"):
        _replan_restored_projection(
            "source.dentocase", Inspection({}), "digest", None, saved,
            {"ownershipComplete": True, "unknownOwnership": []}, actual_mapping,
            "target-1", "source.volume", "",
        )


def test_failed_child_log_and_traceback_survive_temporary_cleanup(monkeypatch, tmp_path):
    evidence = tmp_path / "durable-evidence"
    monkeypatch.setenv("DENTOCASE_EVIDENCE_DIR", str(evidence))
    monkeypatch.delenv("CRUN", raising=False)
    with tempfile.TemporaryDirectory(dir=tmp_path) as disposable:
        log = Path(disposable) / "process.log"
        full_text = ("diagnostic line\n" * 500 +
                     "DENTOCASE_PROJECTOR_PHASE projection 1.000000\n" +
                     "Traceback (most recent call last):\nValueError: synthetic save failure\n")
        log.write_text(full_text)
        retained, status = _retain_projector_log(
            log, exit_code=1, temporary_dir=disposable,
            output_path=Path(disposable) / "result.dentocase",
            source_sha256="a" * 64,
        )
    assert retained.read_text() == full_text
    assert status["exitCode"] == 1
    assert status["childOutputExists"] is False
    assert status["phases"] == ["DENTOCASE_PROJECTOR_PHASE projection 1.000000"]
    assert json.loads((retained.parent / "status.json").read_text()) == status
    assert status["childTemporaryDirectoryName"] == Path(disposable).name
    assert status["childOutputName"] == "result.dentocase"
    assert str(tmp_path) not in json.dumps(status)
    assert os.stat(retained).st_mode & 0o077 == 0
    assert os.stat(retained.parent / "status.json").st_mode & 0o077 == 0
    with pytest.raises(RuntimeError, match="full child diagnostic") as error:
        _check_projector_result(retained, status)
    assert str(retained) in str(error.value)


def test_successful_child_log_uses_configured_run_evidence(monkeypatch, tmp_path):
    monkeypatch.delenv("DENTOCASE_EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("CRUN", str(tmp_path / "run"))
    with tempfile.TemporaryDirectory(dir=tmp_path) as disposable:
        log = Path(disposable) / "process.log"
        log.write_text("DENTOCASE_PROJECTOR_PHASE fresh_reopen 2.000000\n")
        output = Path(disposable) / "result.dentocase"
        output.write_bytes(b"synthetic package")
        retained, status = _retain_projector_log(
            log, exit_code=0, temporary_dir=disposable,
            output_path=output, source_sha256="a" * 64,
        )
    assert retained.parent.parent == tmp_path / "run/evidence"
    assert status["lastPhase"] == "DENTOCASE_PROJECTOR_PHASE fresh_reopen 2.000000"
    assert status["childOutputExists"] is True
    assert retained.is_file()
    _check_projector_result(retained, status)


def test_post_save_unknown_ownership_log_keeps_exact_bounded_reasons_private():
    stream = StringIO()
    reasons = [f"unmapped persistent parameter reference role: role-{index}" for index in range(130)]
    _log_projected_unknown_ownership({"unknownOwnership": reasons}, stream=stream)
    line = stream.getvalue().strip()
    assert line.startswith("DENTOCASE_PRIVATE_POST_SAVE_OWNERSHIP ")
    assert not line.startswith("DENTOCASE_PROJECTOR_")
    payload = json.loads(line.split(" ", 1)[1])
    assert payload == {"count": 130, "reasons": reasons[:128], "omitted": 2}


def test_post_save_failure_report_preserves_all_reasons_and_plan_without_scene_data(monkeypatch, tmp_path):
    monkeypatch.delenv("DENTOCASE_EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("CRUN", str(tmp_path / "run"))
    reasons = [f"saved node has no concrete owner: node-{index}" for index in range(130)]
    plan = {
        "targetId": "target-1", "branchId": "branch-1", "checkpointId": "template.verify",
        "keepNodeIds": ["node-1"], "removeNodeIds": ["node-2"],
        "clearParameters": ["future"], "clearReferenceRoles": ["futureReference"],
    }
    evidence_dir = _new_projector_evidence_dir()
    path = _record_projected_ownership_failure(
        {"unknownOwnership": reasons}, {"nodeOwners": {"node-1": ["artifact-1"]}},
        plan, "a" * 64, evidence_dir,
    )
    report = json.loads(path.read_text())
    assert path.parent == evidence_dir
    assert report["unknownOwnership"] == reasons
    assert report["capturedNodeOwners"] == {"node-1": ["artifact-1"]}
    assert report["plan"] == plan
    assert os.stat(path).st_mode & 0o077 == 0


def test_failed_child_retains_saved_mrb_with_report_log_and_hash(monkeypatch, tmp_path):
    monkeypatch.delenv("DENTOCASE_EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("CRUN", str(tmp_path / "run"))
    evidence_dir = _new_projector_evidence_dir()
    scene_bytes = b"synthetic projected MRB bytes"
    with tempfile.TemporaryDirectory(dir=tmp_path) as disposable:
        projected = Path(disposable) / "projected.mrb"
        projected.write_bytes(scene_bytes)
        report = _record_projected_ownership_failure(
            {"unknownOwnership": ["unmapped persistent reference: role"]},
            {"nodeOwners": {"node-1": []}},
            {"targetId": "target-1", "branchId": "branch-1", "checkpointId": "template.verify",
             "keepNodeIds": ["node-1"], "removeNodeIds": [],
             "clearParameters": [], "clearReferenceRoles": []},
            "a" * 64, evidence_dir,
        )
        retained_scene = _retain_failed_projected_scene(projected, evidence_dir, save_complete=True)
        log = Path(disposable) / "process.log"
        log.write_text("DENTOCASE_PROJECTOR_PHASE save_scene_complete 1.0\n"
                       "DENTOCASE_PROJECTOR_PHASE post_save_inventory_begin 1.1\n"
                       "ValueError: Projected ownership is incomplete.\n")
        retained_log, status = _retain_projector_log(
            log, exit_code=1, temporary_dir=disposable,
            output_path=Path(disposable) / "result.dentocase",
            source_sha256="a" * 64, evidence_dir=evidence_dir,
        )
    assert retained_scene.read_bytes() == scene_bytes
    assert retained_log.is_file() and report.is_file()
    assert status["projectedMrbName"] == "projected.mrb"
    assert status["projectedMrbSha256"] == hashlib.sha256(scene_bytes).hexdigest()
    assert status["ownershipReportName"] == "post-save-ownership.json"
    assert status["lastPhase"] == "DENTOCASE_PROJECTOR_PHASE post_save_inventory_begin 1.1"
    assert os.stat(evidence_dir).st_mode & 0o077 == 0
    assert os.stat(retained_scene).st_mode & 0o077 == 0


def test_child_workspace_copies_failed_saved_mrb_before_cleanup(monkeypatch, tmp_path):
    monkeypatch.delenv("DENTOCASE_EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("CRUN", str(tmp_path / "run"))
    evidence_dir = _new_projector_evidence_dir()
    state = {"path": None, "complete": False}
    with pytest.raises(ValueError, match="projected ownership"):
        with _offline_child_workspace(tmp_path, evidence_dir, state) as scratch:
            state["path"] = scratch / "projected.mrb"
            state["path"].write_bytes(b"synthetic saved scene")
            state["complete"] = True
            raise ValueError("projected ownership")
    assert not scratch.exists()
    assert (evidence_dir / "projected.mrb").read_bytes() == b"synthetic saved scene"


def test_parent_retains_completed_mrb_after_abnormal_child_exit(monkeypatch, tmp_path):
    monkeypatch.delenv("DENTOCASE_EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("CRUN", str(tmp_path / "run"))
    evidence_dir = _new_projector_evidence_dir()
    with tempfile.TemporaryDirectory(dir=tmp_path) as parent:
        child = Path(parent) / "dentocase-offline-aborted"
        child.mkdir()
        (child / "projected.mrb").write_bytes(b"completed before abnormal exit")
        log = Path(parent) / "process.log"
        log.write_text("DENTOCASE_PROJECTOR_PHASE save_scene_complete 2.0\n")
        retained_log, status = _retain_projector_log(
            log, exit_code=1, temporary_dir=parent,
            output_path=Path(parent) / "result.dentocase",
            source_sha256="a" * 64, evidence_dir=evidence_dir,
        )
    assert retained_log.is_file()
    assert (evidence_dir / "projected.mrb").read_bytes() == b"completed before abnormal exit"
    assert status["projectedMrbSha256"] == hashlib.sha256(
        b"completed before abnormal exit"
    ).hexdigest()


@pytest.mark.parametrize("save_complete,scene_exists", [(False, True), (True, False)])
def test_no_projected_mrb_retained_without_completed_save_and_file(monkeypatch, tmp_path,
                                                                   save_complete, scene_exists):
    monkeypatch.delenv("DENTOCASE_EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("CRUN", str(tmp_path / "run"))
    evidence_dir = _new_projector_evidence_dir()
    with tempfile.TemporaryDirectory(dir=tmp_path) as disposable:
        projected = Path(disposable) / "projected.mrb"
        if scene_exists:
            projected.write_bytes(b"partial output")
            child = Path(disposable) / "dentocase-offline-aborted"
            child.mkdir()
            (child / "projected.mrb").write_bytes(b"partial output")
        assert _retain_failed_projected_scene(
            projected, evidence_dir, save_complete=save_complete,
        ) is None
        log = Path(disposable) / "process.log"
        log.write_text("DENTOCASE_PROJECTOR_PHASE save_scene_begin 1.0\n")
        _retained_log, status = _retain_projector_log(
            log, exit_code=1, temporary_dir=disposable,
            output_path=Path(disposable) / "result.dentocase",
            source_sha256="a" * 64, evidence_dir=evidence_dir,
        )
    assert not (evidence_dir / "projected.mrb").exists()
    assert status["projectedMrbName"] == ""
    assert status["projectedMrbSha256"] == ""
    assert status["ownershipReportName"] == ""


def test_retained_geometry_loses_saved_step6_config_and_base_authority():
    class Node:
        def __init__(self, attributes):
            self.attributes = dict(attributes)

        def GetAttribute(self, name):
            return self.attributes.get(name)

        def SetAttribute(self, name, value):
            if value is None:
                self.attributes.pop(name, None)
            else:
                self.attributes[name] = value

    template = Node({
        "DENTOBOT.VerificationState": "WARNING",
        "DENTOBOT.VerificationJson": "saved-step5c",
        "DENTOBOT.Step6WorkingConfigJson": "saved-home-base-policy",
    })
    base = Node({
        "DENTOBOT.RobotBaseMountLocked": "true",
        "DENTOBOT.RobotBasePlacementAuthority": "ManualSimulationBaseReviewed",
        "DENTOBOT.Step6PlanningContextImported": "true",
    })
    for node in (template, base):
        _clear_future_node_attributes(node, 100)
    assert template.attributes == {
        "DENTOBOT.VerificationState": "WARNING",
        "DENTOBOT.VerificationJson": "saved-step5c",
    }
    assert base.attributes == {}

    _clear_future_node_attributes(template, 90)
    assert template.attributes["DENTOBOT.VerificationState"] == "NotVerified"
    assert "DENTOBOT.VerificationJson" not in template.attributes


def test_filter_registry_keeps_only_selected_pair_and_resets_histories_on_early_cutoff():
    source = _registry()
    before = deepcopy(source)

    built = filter_registry(source, "target-1", ("trajectory-1",), "branch-1", 90)
    assert built["prepared_branches"]["branch-1"]["verification_revision"] == ""
    verified = filter_registry(source, "target-1", ("trajectory-1",), "branch-1", 100)
    assert verified["prepared_branches"]["branch-1"]["verification_revision"] == "saved-5c"

    assert set(built["teeth"]) == set(source["teeth"])
    assert all(not built["teeth"][tooth]["target_id"] for tooth in built["teeth"] if tooth != "FDI11")
    selected_slots = built["teeth"]["FDI11"]["trajectory_set"]["slots"]
    assert selected_slots[0]["trajectory_id"] == "trajectory-1"
    assert selected_slots[0]["prepared_branch_ids"] == ["branch-1"]
    assert selected_slots[1] == {"slot": 2, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []}
    assert set(built["prepared_branches"]) == {"branch-1"}
    assert built["selected_branch_id"] == "branch-1"

    early = filter_registry(source, "target-1", ("trajectory-1",), "branch-1", 40)
    assert all(slot["state"] == "Empty" for slot in early["teeth"]["FDI11"]["trajectory_set"]["slots"])
    assert early["prepared_branches"] == {}
    assert early["selected_branch_id"] == ""
    assert source == before


def test_filter_registry_rejects_unknown_ids_and_unbuilt_branches_are_cleared():
    source = _registry()
    try:
        filter_registry(source, "target-1", ("missing-trajectory",), "branch-1", 90)
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("unknown trajectory identity must block projection")

    before_build = filter_registry(source, "target-1", ("trajectory-1",), "branch-1", 80)
    assert before_build["prepared_branches"] == {}
    assert before_build["selected_branch_id"] == ""
