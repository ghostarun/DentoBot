from __future__ import annotations

import sys
from pathlib import Path

import pytest


PYTHON_ROOT = Path(__file__).resolve().parents[1] / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PYTHON_ROOT))

from dentobot_case.contracts import Artifact, Branch, CaseInventory, Checkpoint  # noqa: E402
from dentobot_case.lineage import available_cutoffs, select_prefix, validate_checkpoints  # noqa: E402


def cp(identifier: str, order: int, scope: str, requires: tuple[str, ...] = (), label: str = "") -> Checkpoint:
    return Checkpoint(identifier, label, order, scope, requires)


def art(
    identifier: str,
    checkpoint_id: str,
    scope: str,
    *,
    target: str = "",
    branch: str = "",
    dependencies: tuple[str, ...] = (),
    trajectory_ids: tuple[str, ...] = (),
    state: str = "Current",
) -> Artifact:
    return Artifact(
        identifier,
        checkpoint_id,
        scope,
        target_id=target,
        branch_id=branch,
        dependencies=dependencies,
        trajectory_ids=trajectory_ids,
        state=state,
    )


def inv(
    artifacts: tuple[Artifact, ...],
    *,
    targets: tuple[str, ...] = ("tooth-a",),
    branches: tuple[Branch, ...] = (),
    owned: bool = True,
    unknown: tuple[str, ...] = (),
    case_id: str = "source-case",
    definition_version: str = "1.0",
) -> CaseInventory:
    return CaseInventory(
        path="synthetic.dentocase",
        package_id="package-1",
        case_id=case_id,
        label="synthetic",
        archive_schema="2.0",
        package_sha256="0" * 64,
        checked_at_utc="2026-10-01T00:00:00Z",
        target_ids=targets,
        artifacts=artifacts,
        branches=branches,
        ownership_complete=owned,
        unknown_ownership=unknown,
        definition_version=definition_version,
    )


def test_stable_ids_and_explicit_order_survive_renamed_and_inserted_labels():
    checkpoints = (
        cp("foundation.source", 10, "shared", label="renamed to something unrelated"),
        cp("inserted.audit", 15, "shared", ("foundation.source",), label="not a workflow step"),
        cp("trajectory.plan", 20, "target", ("inserted.audit",), label="label says order 999"),
    )
    inventory = inv((
        art("source", "foundation.source", "shared"),
        art("audit", "inserted.audit", "shared", dependencies=("source",)),
        art("route", "trajectory.plan", "target", target="tooth-a", dependencies=("audit",)),
    ))

    selected = select_prefix(inventory, "tooth-a", "trajectory.plan", checkpoints=checkpoints)

    assert selected.allowed
    assert selected.included_ids == ("audit", "route", "source")
    assert selected.latest_complete_checkpoint == "trajectory.plan"


def test_checkpoint_validation_rejects_cycles_unknown_edges_and_bad_order():
    with pytest.raises(ValueError, match="cycle"):
        validate_checkpoints((
            cp("a", 10, "shared", ("b",)),
            cp("b", 20, "shared", ("a",)),
        ))
    with pytest.raises(ValueError, match="unknown prerequisite"):
        validate_checkpoints((cp("a", 10, "shared", ("missing",)),))
    with pytest.raises(ValueError, match="order must precede"):
        validate_checkpoints((cp("first", 20, "shared"), cp("second", 10, "target", ("first",))))


def test_shared_prerequisite_closure_and_target_isolation():
    checkpoints = (cp("foundation", 10, "shared"), cp("route", 20, "target", ("foundation",)))
    inventory = inv((
        art("foundation-artifact", "foundation", "shared"),
        art("route-a", "route", "target", target="tooth-a", dependencies=("foundation-artifact",)),
        art("route-b", "route", "target", target="tooth-b", dependencies=("foundation-artifact",)),
    ), targets=("tooth-a", "tooth-b"))

    selected = select_prefix(inventory, "tooth-a", "route", checkpoints=checkpoints)

    assert selected.allowed
    assert selected.included_ids == ("foundation-artifact", "route-a")
    assert selected.excluded_ids == ("route-b",)


def paired_inventory(*, include_second: bool = True) -> tuple[CaseInventory, tuple[Checkpoint, ...]]:
    checkpoints = (
        cp("foundation", 10, "shared"),
        cp("trajectory.plan", 20, "target", ("foundation",)),
        cp("support.selection", 30, "branch", ("trajectory.plan",)),
    )
    trajectory_artifacts = [
        art("foundation-artifact", "foundation", "shared"),
        art("trajectory-a", "trajectory.plan", "target", target="tooth-a", trajectory_ids=("traj-a",)),
    ]
    if include_second:
        trajectory_artifacts.append(
            art("trajectory-b", "trajectory.plan", "target", target="tooth-a", trajectory_ids=("traj-b",))
        )
    trajectory_artifacts.append(
        art("support", "support.selection", "branch", target="tooth-a", branch="paired", dependencies=("trajectory-a",))
    )
    branch = Branch("paired", "tooth-a", ("traj-a", "traj-b"), "ExplicitPair", "Ready")
    return inv(tuple(trajectory_artifacts), branches=(branch,)), checkpoints


def test_explicit_pair_keeps_both_members_and_rejects_a_missing_member():
    inventory, checkpoints = paired_inventory()
    selected = select_prefix(inventory, "tooth-a", "support.selection", checkpoints=checkpoints)
    assert selected.allowed
    assert selected.branch_id == "paired"
    assert {"trajectory-a", "trajectory-b"}.issubset(selected.included_ids)

    incomplete, _ = paired_inventory(include_second=False)
    rejected = select_prefix(incomplete, "tooth-a", "support.selection", checkpoints=checkpoints)
    assert not rejected.allowed
    assert any("explicit pair missing trajectory.plan members: traj-b" in reason for reason in rejected.reasons)
    assert rejected.new_case_id == ""

    plan_rejected = select_prefix(
        incomplete, "tooth-a", "trajectory.plan", "paired", checkpoints=checkpoints
    )
    assert not plan_rejected.allowed
    assert any("explicit pair missing trajectory.plan members: traj-b" in reason for reason in plan_rejected.reasons)


def test_legacy_pair_and_wrong_or_unknown_branch_are_rejected():
    inventory, checkpoints = paired_inventory()
    legacy = Branch("paired", "tooth-a", ("traj-a", "traj-b"), "LegacyUnverified", "Ready")
    rejected = select_prefix(
        inv(inventory.artifacts, branches=(legacy,)),
        "tooth-a",
        "support.selection",
        checkpoints=checkpoints,
    )
    assert not rejected.allowed
    assert any("unsafe branch: paired" in reason for reason in rejected.reasons)

    assert not select_prefix(inventory, "tooth-a", "support.selection", "missing", checkpoints=checkpoints).allowed
    assert not select_prefix(inventory, "tooth-b", "support.selection", "paired", checkpoints=checkpoints).allowed


def test_missing_checkpoint_prerequisite_reports_latest_complete_cutoff():
    checkpoints = (
        cp("foundation", 10, "shared"),
        cp("route", 20, "target", ("foundation",)),
        cp("diagnostic", 30, "target", ("route",)),
    )
    inventory = inv((
        art("foundation-artifact", "foundation", "shared"),
        art("diagnostic-artifact", "diagnostic", "target", target="tooth-a"),
    ))

    selected = select_prefix(inventory, "tooth-a", "diagnostic", checkpoints=checkpoints)

    assert not selected.allowed
    assert selected.latest_complete_checkpoint == "foundation"
    assert any("missing checkpoint prerequisite: route" in reason for reason in selected.reasons)


def test_stale_present_artifact_is_retained_without_status_promotion():
    checkpoints = (cp("foundation", 10, "shared"),)
    stale = art("stale-foundation", "foundation", "shared", state="Stale")
    inventory = inv((stale,))

    selected = select_prefix(inventory, "tooth-a", "foundation", checkpoints=checkpoints)

    assert selected.allowed
    assert selected.included_ids == ("stale-foundation",)
    assert inventory.artifacts[0].state == "Stale"


def test_unknown_ownership_and_definition_version_block_selection():
    checkpoints = (cp("foundation", 10, "shared"),)
    artifacts = (art("foundation-artifact", "foundation", "shared"),)
    for inventory in (
        inv(artifacts, owned=False),
        inv(artifacts, unknown=("unmapped payload",)),
        inv(artifacts, definition_version="0.9"),
    ):
        selected = select_prefix(inventory, "tooth-a", "foundation", checkpoints=checkpoints)
        assert not selected.allowed
        assert selected.included_ids == ()
        assert selected.new_case_id == ""


def test_dependency_closure_rejects_missing_ids_cycles_and_later_edges():
    checkpoints = (
        cp("foundation", 10, "shared"),
        cp("route", 20, "target", ("foundation",)),
        cp("diagnostic", 30, "target", ("route",)),
    )
    missing = inv((
        art("foundation-artifact", "foundation", "shared"),
        art("route-artifact", "route", "target", target="tooth-a", dependencies=("absent-id",)),
    ))
    selected = select_prefix(missing, "tooth-a", "route", checkpoints=checkpoints)
    assert not selected.allowed
    assert any("missing dependency: absent-id" in reason for reason in selected.reasons)

    cyclic = inv((
        art("foundation-artifact", "foundation", "shared", dependencies=("route-artifact",)),
        art("route-artifact", "route", "target", target="tooth-a", dependencies=("foundation-artifact",)),
    ))
    selected = select_prefix(cyclic, "tooth-a", "route", checkpoints=checkpoints)
    assert not selected.allowed
    assert any("artifact dependency cycle" in reason for reason in selected.reasons)

    later = inv((
        art("foundation-artifact", "foundation", "shared"),
        art("route-artifact", "route", "target", target="tooth-a", dependencies=("diagnostic-artifact",)),
        art("diagnostic-artifact", "diagnostic", "target", target="tooth-a"),
    ))
    selected = select_prefix(later, "tooth-a", "route", checkpoints=checkpoints)
    assert not selected.allowed
    assert any("dependency diagnostic-artifact is after its dependent checkpoint" in reason for reason in selected.reasons)

    same_checkpoint = inv((
        art("geometry", "foundation", "shared"),
        art("transform", "foundation", "shared", dependencies=("geometry",)),
    ))
    selected = select_prefix(same_checkpoint, "tooth-a", "foundation", checkpoints=(checkpoints[0],))
    assert selected.allowed
    assert selected.included_ids == ("geometry", "transform")

    self_dependent = inv((art("foundation-artifact", "foundation", "shared", dependencies=("foundation-artifact",)),))
    selected = select_prefix(self_dependent, "tooth-a", "foundation", checkpoints=(checkpoints[0],))
    assert not selected.allowed
    assert any("self dependency: foundation-artifact" in reason for reason in selected.reasons)


def test_available_cutoffs_only_returns_complete_prefixes_and_fresh_history():
    checkpoints = (
        cp("foundation", 10, "shared", label="renamed source"),
        cp("route", 20, "target", ("foundation",), label="renamed route"),
        cp("support", 30, "branch", ("route",), label="renamed branch"),
    )
    inventory = inv((
        art("foundation-artifact", "foundation", "shared"),
        art("route-artifact", "route", "target", target="tooth-a"),
    ))
    source_before = inventory.to_dict()

    options = available_cutoffs(inventory, "tooth-a", checkpoints=checkpoints)

    assert tuple(option.checkpoint_id for option in options) == ("foundation", "route")
    assert all(option.allowed and option.history_policy == "Fresh" for option in options)
    assert all(option.new_case_id and option.new_case_id != inventory.case_id for option in options)
    assert inventory.to_dict() == source_before
