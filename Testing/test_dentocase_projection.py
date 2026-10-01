"""Pure unit checks for fresh saved-case projection plans."""

from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))

from dentobot_case.contracts import Artifact, CaseInventory  # noqa: E402
from dentobot_case.projection import filter_registry, prepare_projection  # noqa: E402


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
