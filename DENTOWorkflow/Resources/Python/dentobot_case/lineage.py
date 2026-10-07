"""Pure cutoff selection for saved DentoCase evidence."""

from __future__ import annotations

from .contracts import (
    CHECKPOINT_DEFINITION_VERSION,
    CHECKPOINTS,
    Artifact,
    Branch,
    CaseInventory,
    Checkpoint,
    PrefixSelection,
    new_case_id,
)


_SCOPES = {"shared", "target", "branch"}
_PAIRING_INTENTS = {"Single", "ExplicitPair", "LegacyUnverified"}


def validate_checkpoints(checkpoints: tuple[Checkpoint, ...] = CHECKPOINTS) -> None:
    """Raise ValueError when checkpoint IDs, ordering or prerequisite edges are invalid."""
    by_id: dict[str, Checkpoint] = {}
    orders: set[int] = set()
    for checkpoint in checkpoints:
        if not isinstance(checkpoint.id, str) or not checkpoint.id.strip():
            raise ValueError("checkpoint IDs must be nonempty")
        if checkpoint.id in by_id:
            raise ValueError(f"duplicate checkpoint ID: {checkpoint.id}")
        if isinstance(checkpoint.order, bool) or not isinstance(checkpoint.order, int):
            raise ValueError(f"checkpoint order must be an integer: {checkpoint.id}")
        if checkpoint.order in orders:
            raise ValueError(f"duplicate checkpoint order: {checkpoint.order}")
        if checkpoint.scope not in _SCOPES:
            raise ValueError(f"unknown checkpoint scope: {checkpoint.scope}")
        by_id[checkpoint.id] = checkpoint
        orders.add(checkpoint.order)

    for checkpoint in checkpoints:
        for prerequisite_id in checkpoint.requires:
            if prerequisite_id not in by_id:
                raise ValueError(
                    f"unknown prerequisite checkpoint: {prerequisite_id}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(checkpoint_id: str) -> None:
        if checkpoint_id in visiting:
            raise ValueError(f"checkpoint prerequisite cycle: {checkpoint_id}")
        if checkpoint_id in visited:
            return
        visiting.add(checkpoint_id)
        for prerequisite_id in by_id[checkpoint_id].requires:
            visit(prerequisite_id)
        visiting.remove(checkpoint_id)
        visited.add(checkpoint_id)

    for checkpoint_id in by_id:
        visit(checkpoint_id)

    for checkpoint in checkpoints:
        for prerequisite_id in checkpoint.requires:
            if by_id[prerequisite_id].order >= checkpoint.order:
                raise ValueError(
                    f"prerequisite order must precede checkpoint: {prerequisite_id} -> {checkpoint.id}"
                )


def _inventory_errors(
    inventory: CaseInventory,
    by_checkpoint: dict[str, Checkpoint],
) -> list[str]:
    errors: list[str] = []
    if inventory.definition_version != CHECKPOINT_DEFINITION_VERSION:
        errors.append(
            "checkpoint definition version mismatch: "
            f"{inventory.definition_version}"
        )
    if not inventory.ownership_complete:
        errors.append("artifact ownership is incomplete")
    if inventory.unknown_ownership:
        errors.append(
            "unknown artifact ownership: "
            + ", ".join(sorted(set(inventory.unknown_ownership)))
        )
    if len(inventory.target_ids) != len(set(inventory.target_ids)):
        errors.append("duplicate target IDs")
    if any(not isinstance(target_id, str) or not target_id.strip() for target_id in inventory.target_ids):
        errors.append("target IDs must be nonempty")

    branch_by_id: dict[str, Branch] = {}
    for branch in inventory.branches:
        if not isinstance(branch.id, str) or not branch.id.strip():
            errors.append("branch IDs must be nonempty")
            continue
        if branch.id in branch_by_id:
            errors.append(f"duplicate branch ID: {branch.id}")
        branch_by_id[branch.id] = branch
        if branch.target_id not in inventory.target_ids:
            errors.append(f"branch has unknown target: {branch.id}")
        if branch.pairing_intent not in _PAIRING_INTENTS:
            errors.append(f"unknown branch pairing intent: {branch.id}")
        members = branch.trajectory_ids
        if not members:
            errors.append(f"branch has no trajectory IDs: {branch.id}")
        if any(not isinstance(item, str) or not item.strip() for item in members):
            errors.append(f"branch has empty trajectory ID: {branch.id}")
        if len(members) != len(set(members)):
            errors.append(f"branch has duplicate trajectory IDs: {branch.id}")
        if branch.pairing_intent == "Single" and len(members) != 1:
            errors.append(f"single branch must contain one trajectory: {branch.id}")
        if branch.pairing_intent == "ExplicitPair" and len(members) != 2:
            errors.append(f"explicit pair must contain two trajectories: {branch.id}")

    artifact_by_id: dict[str, Artifact] = {}
    for artifact in inventory.artifacts:
        if not isinstance(artifact.id, str) or not artifact.id.strip():
            errors.append("artifact IDs must be nonempty")
        elif artifact.id in artifact_by_id:
            errors.append(f"duplicate artifact ID: {artifact.id}")
        else:
            artifact_by_id[artifact.id] = artifact

        checkpoint = by_checkpoint.get(artifact.checkpoint_id)
        if checkpoint is None:
            errors.append(f"unknown artifact checkpoint: {artifact.checkpoint_id}")
            continue
        if artifact.scope not in _SCOPES or artifact.scope != checkpoint.scope:
            errors.append(f"artifact checkpoint scope mismatch: {artifact.id}")
        if artifact.scope == "shared":
            if artifact.target_id or artifact.branch_id:
                errors.append(f"shared artifact has target or branch ownership: {artifact.id}")
        elif artifact.scope == "target":
            if artifact.target_id not in inventory.target_ids or artifact.branch_id:
                errors.append(f"target artifact has invalid ownership: {artifact.id}")
        elif artifact.scope == "branch":
            branch = branch_by_id.get(artifact.branch_id)
            if (
                artifact.target_id not in inventory.target_ids
                or branch is None
                or branch.target_id != artifact.target_id
            ):
                errors.append(f"branch artifact has invalid ownership: {artifact.id}")

        dependencies = tuple(artifact.dependencies)
        if any(not isinstance(dep, str) or not dep.strip() for dep in dependencies):
            errors.append(f"artifact has empty dependency ID: {artifact.id}")
        if len(dependencies) != len(set(dependencies)):
            errors.append(f"artifact has duplicate dependency ID: {artifact.id}")

    return sorted(set(errors))


def _checkpoint_ancestors(checkpoint_id: str, by_checkpoint: dict[str, Checkpoint]) -> set[str]:
    found: set[str] = set()
    pending = list(by_checkpoint[checkpoint_id].requires)
    while pending:
        prerequisite_id = pending.pop()
        if prerequisite_id in found:
            continue
        found.add(prerequisite_id)
        pending.extend(by_checkpoint[prerequisite_id].requires)
    return found


def _branch_is_safe(branch: Branch) -> bool:
    return branch.pairing_intent != "LegacyUnverified" and branch.state.casefold() not in {
        "rejected", "unsafe", "legacyunverified"
    }


def _evaluate(
    inventory: CaseInventory,
    target_id: str,
    checkpoint_id: str,
    branch_id: str,
    checkpoints: tuple[Checkpoint, ...],
    by_checkpoint: dict[str, Checkpoint],
) -> tuple[bool, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    cutoff = by_checkpoint[checkpoint_id]
    artifact_by_id = {artifact.id: artifact for artifact in inventory.artifacts}
    all_ids = tuple(sorted({artifact.id for artifact in inventory.artifacts if artifact.id}))
    excluded: dict[str, str] = {}
    errors = _inventory_errors(inventory, by_checkpoint)
    if target_id not in inventory.target_ids:
        errors.append(f"target is not in inventory: {target_id}")

    explicit_branch = branch_id
    matching_branches = [branch for branch in inventory.branches if branch.target_id == target_id]
    required_checkpoints = {checkpoint_id} | _checkpoint_ancestors(checkpoint_id, by_checkpoint)
    has_branch_artifact = any(
        artifact.target_id == target_id
        and by_checkpoint.get(artifact.checkpoint_id) is not None
        and by_checkpoint[artifact.checkpoint_id].order <= cutoff.order
        and artifact.scope == "branch"
        for artifact in inventory.artifacts
    )
    branch_required = any(
        by_checkpoint[item].scope == "branch" for item in required_checkpoints
    )
    selected_branch: Branch | None = None
    if explicit_branch:
        selected_branch = next(
            (branch for branch in inventory.branches if branch.id == explicit_branch), None
        )
        if selected_branch is None:
            errors.append(f"unknown branch: {explicit_branch}")
        elif selected_branch.target_id != target_id:
            errors.append(f"branch belongs to another target: {explicit_branch}")
    elif branch_required or has_branch_artifact:
        if len(matching_branches) == 1:
            selected_branch = matching_branches[0]
        elif len(matching_branches) > 1:
            errors.append(f"ambiguous branch for target: {target_id}")
        else:
            errors.append(f"branch required but unavailable for target: {target_id}")

    if selected_branch is not None and not _branch_is_safe(selected_branch):
        errors.append(f"unsafe branch: {selected_branch.id}")

    def eligibility(artifact: Artifact) -> tuple[bool, str]:
        artifact_checkpoint = by_checkpoint.get(artifact.checkpoint_id)
        if artifact_checkpoint is None:
            return False, "unknown checkpoint"
        if artifact_checkpoint.order > cutoff.order:
            return False, "after cutoff"
        if artifact.scope == "shared":
            return True, ""
        if artifact.target_id != target_id:
            return False, "different target"
        if artifact.scope == "target":
            if selected_branch is not None and artifact.trajectory_ids:
                if not set(artifact.trajectory_ids).intersection(selected_branch.trajectory_ids):
                    return False, "trajectory does not belong to selected branch"
            return True, ""
        if selected_branch is None:
            return False, "branch not selected"
        if artifact.branch_id != selected_branch.id:
            return False, "different branch"
        return True, ""

    included: set[str] = set()
    if not errors:
        for artifact in inventory.artifacts:
            if not artifact.id:
                continue
            allowed, reason = eligibility(artifact)
            if allowed:
                included.add(artifact.id)
            else:
                excluded[artifact.id] = reason

        # Check every reachable edge before filtering invalid dependencies so a
        # cycle cannot disappear merely because one edge crosses the cutoff.
        colors: dict[str, int] = {}

        def visit_artifact(artifact_id: str) -> None:
            color = colors.get(artifact_id, 0)
            if color == 1:
                errors.append(f"artifact dependency cycle: {artifact_id}")
                return
            if color == 2:
                return
            colors[artifact_id] = 1
            for dependency_id in artifact_by_id[artifact_id].dependencies:
                if dependency_id in artifact_by_id:
                    visit_artifact(dependency_id)
            colors[artifact_id] = 2

        for artifact_id in sorted(included):
            visit_artifact(artifact_id)

        pending = list(sorted(included))
        while pending:
            artifact = artifact_by_id[pending.pop()]
            for dependency_id in artifact.dependencies:
                if dependency_id == artifact.id:
                    errors.append(f"self dependency: {dependency_id}")
                    continue
                dependency = artifact_by_id.get(dependency_id)
                if dependency is None:
                    errors.append(f"missing dependency: {dependency_id}")
                    continue
                artifact_checkpoint = by_checkpoint[artifact.checkpoint_id]
                dependency_checkpoint = by_checkpoint[dependency.checkpoint_id]
                if dependency_checkpoint.order > artifact_checkpoint.order:
                    errors.append(
                        f"dependency {dependency_id} is after its dependent checkpoint"
                    )
                    continue
                allowed, reason = eligibility(dependency)
                if not allowed:
                    errors.append(f"dependency {dependency_id} is {reason}")
                    continue
                if dependency_id not in included:
                    included.add(dependency_id)
                    excluded.pop(dependency_id, None)
                    pending.append(dependency_id)

        if (
            selected_branch is not None
            and selected_branch.pairing_intent == "ExplicitPair"
            and (
                ("trajectory.plan" in by_checkpoint
                 and cutoff.order >= by_checkpoint["trajectory.plan"].order)
                or any(
                    artifact_by_id[item].checkpoint_id == "trajectory.plan"
                    for item in included
                )
            )
        ):
            if "trajectory.plan" not in by_checkpoint:
                errors.append("missing checkpoint definition: trajectory.plan")
            else:
                represented: set[str] = set()
                for artifact_id in included:
                    artifact = artifact_by_id[artifact_id]
                    if artifact.checkpoint_id == "trajectory.plan" and artifact.scope == "target":
                        represented.add(artifact.id)
                        represented.update(artifact.trajectory_ids)
                missing_members = sorted(set(selected_branch.trajectory_ids) - represented)
                if missing_members:
                    errors.append(
                        "explicit pair missing trajectory.plan members: "
                        + ", ".join(missing_members)
                    )

        included_checkpoints = {checkpoint_id}
        included_checkpoints.update(
            artifact_by_id[item].checkpoint_id for item in included
        )
        needed_checkpoints: set[str] = set()
        pending_checkpoints = list(included_checkpoints)
        while pending_checkpoints:
            current_id = pending_checkpoints.pop()
            if current_id in needed_checkpoints:
                continue
            needed_checkpoints.add(current_id)
            pending_checkpoints.extend(by_checkpoint[current_id].requires)

        retained_checkpoints = {artifact_by_id[item].checkpoint_id for item in included}
        for required_id in sorted(needed_checkpoints, key=lambda item: by_checkpoint[item].order):
            if required_id not in retained_checkpoints:
                if required_id == checkpoint_id:
                    errors.append(f"missing checkpoint artifact: {required_id}")
                else:
                    errors.append(f"missing checkpoint prerequisite: {required_id}")

    # On any failure, do not expose a partial prefix as a usable selection.
    if errors:
        included.clear()
        for artifact_id in all_ids:
            excluded.setdefault(artifact_id, "selection rejected")
    reasons = tuple(sorted(set(errors + [f"{artifact_id}: {reason}" for artifact_id, reason in excluded.items()])))
    actual_branch_id = selected_branch.id if selected_branch is not None else ""
    return (
        not errors,
        actual_branch_id,
        tuple(sorted(included)),
        tuple(sorted(excluded)),
        reasons,
    )


def _fresh_case_id(source_case_id: str) -> str:
    case_id = new_case_id()
    while case_id == source_case_id:
        case_id = new_case_id()
    return case_id


def _select(
    inventory: CaseInventory,
    target_id: str,
    checkpoint_id: str,
    branch_id: str = "",
    *,
    checkpoints: tuple[Checkpoint, ...] = CHECKPOINTS,
) -> PrefixSelection:
    try:
        validate_checkpoints(checkpoints)
    except (AttributeError, TypeError, ValueError) as exc:
        return PrefixSelection(
            target_id=target_id,
            branch_id=branch_id,
            checkpoint_id=checkpoint_id,
            allowed=False,
            excluded_ids=tuple(sorted({artifact.id for artifact in inventory.artifacts if artifact.id})),
            reasons=(f"invalid checkpoint definitions: {exc}",),
        )

    by_checkpoint = {checkpoint.id: checkpoint for checkpoint in checkpoints}
    if checkpoint_id not in by_checkpoint:
        return PrefixSelection(
            target_id=target_id,
            branch_id=branch_id,
            checkpoint_id=checkpoint_id,
            allowed=False,
            excluded_ids=tuple(sorted({artifact.id for artifact in inventory.artifacts if artifact.id})),
            reasons=(f"unknown checkpoint: {checkpoint_id}",),
        )

    ordered = sorted(checkpoints, key=lambda item: item.order)
    valid: list[str] = []
    for checkpoint in ordered:
        if checkpoint.order > by_checkpoint[checkpoint_id].order:
            break
        allowed, _, _, _, _ = _evaluate(
            inventory,
            target_id,
            checkpoint.id,
            branch_id,
            checkpoints,
            by_checkpoint,
        )
        if allowed:
            valid.append(checkpoint.id)

    allowed, actual_branch_id, included, excluded, reasons = _evaluate(
        inventory,
        target_id,
        checkpoint_id,
        branch_id,
        checkpoints,
        by_checkpoint,
    )
    return PrefixSelection(
        target_id=target_id,
        branch_id=actual_branch_id,
        checkpoint_id=checkpoint_id,
        allowed=allowed,
        included_ids=included,
        excluded_ids=excluded,
        reasons=reasons,
        latest_complete_checkpoint=valid[-1] if valid else None,
        new_case_id=_fresh_case_id(inventory.case_id) if allowed else "",
        history_policy="Fresh",
    )


def select_prefix(
    inventory: CaseInventory,
    target_id: str,
    checkpoint_id: str,
    branch_id: str = "",
    *,
    checkpoints: tuple[Checkpoint, ...] = CHECKPOINTS,
) -> PrefixSelection:
    """Preview a fresh saved-evidence prefix through one stable checkpoint ID."""
    return _select(inventory, target_id, checkpoint_id, branch_id, checkpoints=checkpoints)


def available_cutoffs(
    inventory: CaseInventory,
    target_id: str,
    branch_id: str = "",
    *,
    checkpoints: tuple[Checkpoint, ...] = CHECKPOINTS,
) -> tuple[PrefixSelection, ...]:
    """Return allowed checkpoint prefixes in explicit checkpoint order."""
    try:
        validate_checkpoints(checkpoints)
    except (AttributeError, TypeError, ValueError):
        return ()
    return tuple(
        selection
        for checkpoint in sorted(checkpoints, key=lambda item: item.order)
        if (selection := _select(
            inventory, target_id, checkpoint.id, branch_id, checkpoints=checkpoints
        )).allowed
    )
