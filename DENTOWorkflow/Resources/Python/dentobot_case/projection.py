"""Pure plans for projecting a saved case into a fresh workflow prefix."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import CHECKPOINTS, CaseInventory
from .lineage import select_prefix


_SPECIAL_NODE_OWNERS = {"@display", "@runtime", "@history"}
_PARAMETER_SPECIAL_OWNERS = {
    "shared", "runtime", "history", "identity", "navigation", "registry", "display"
}
_REFERENCE_SPECIAL_OWNERS = {"shared", "runtime", "history", "registry", "display"}
_TEETH = tuple(f"FDI{quadrant}{tooth}" for quadrant in range(1, 5) for tooth in range(1, 9))
_SLOTS_PER_TOOTH = 3
_REGISTRY_SCHEMA = "3.0"


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{name} must be {'a string' if allow_empty else 'a nonempty string'}")
    return value


def _owner(value: object, name: str, *, special: set[str], checkpoints: set[str]) -> str:
    owner = _text(value, name)
    if owner not in special and owner not in checkpoints:
        raise ValueError(f"unknown checkpoint or ownership role for {name}: {owner}")
    return owner


def _projection_metadata(inventory: CaseInventory) -> dict[str, Any]:
    metadata = inventory.metadata
    if not isinstance(metadata, dict) or not isinstance(metadata.get("projection"), dict):
        raise ValueError("projection ownership metadata is missing")
    projection = metadata["projection"]
    required = {
        "version", "parameterNodeId", "nodeIds", "nodeOwners", "parameterOwners",
        "referenceOwners", "resumeIndices", "defaults",
    }
    if set(projection) != required:
        raise ValueError("projection metadata has missing or unknown fields")
    if projection["version"] != "1.0":
        raise ValueError(f"unsupported projection metadata version: {projection['version']!r}")

    parameter_node_id = _text(projection["parameterNodeId"], "parameterNodeId")
    node_ids = projection["nodeIds"]
    if (not isinstance(node_ids, list) or any(not isinstance(item, str) or not item.strip() for item in node_ids)
            or len(node_ids) != len(set(node_ids))):
        raise ValueError("nodeIds must be a unique list of nonempty strings")
    if parameter_node_id not in node_ids:
        raise ValueError("parameterNodeId is missing from the audited nodeIds")

    checkpoints = {item.id: item.order for item in CHECKPOINTS}
    artifact_ids = {item.id for item in inventory.artifacts}
    node_owners = projection["nodeOwners"]
    if not isinstance(node_owners, dict) or set(node_owners) != set(node_ids):
        raise ValueError("node ownership must cover every audited node")
    for node_id, owners in node_owners.items():
        if not isinstance(owners, list) or any(not isinstance(item, str) or not item.strip() for item in owners):
            raise ValueError(f"node ownership must be a list of nonempty strings: {node_id}")
        if len(owners) != len(set(owners)):
            raise ValueError(f"node ownership contains duplicates: {node_id}")
        if node_id == parameter_node_id and not owners:
            continue
        if not owners:
            raise ValueError(f"node has no owner: {node_id}")
        if any(owner in _SPECIAL_NODE_OWNERS for owner in owners):
            if len(owners) != 1 or owners[0] not in _SPECIAL_NODE_OWNERS:
                raise ValueError(f"special node ownership must be exclusive: {node_id}")
        elif any(owner not in artifact_ids for owner in owners):
            unknown = next(owner for owner in owners if owner not in artifact_ids)
            raise ValueError(f"node owner does not name an inventory artifact: {unknown}")

    def validate_owner_map(name: str, special: set[str]) -> dict[str, str]:
        owners = projection[name]
        if not isinstance(owners, dict):
            raise ValueError(f"{name} must be an object")
        result: dict[str, str] = {}
        for key, value in owners.items():
            field = _text(key, f"{name} key")
            result[field] = _owner(value, f"{name}[{field}]", special=special, checkpoints=set(checkpoints))
        return result

    parameter_owners = validate_owner_map("parameterOwners", _PARAMETER_SPECIAL_OWNERS)
    reference_owners = validate_owner_map("referenceOwners", _REFERENCE_SPECIAL_OWNERS)

    resume_indices = projection["resumeIndices"]
    if not isinstance(resume_indices, dict):
        raise ValueError("resumeIndices must be an object")
    for checkpoint_id, index in resume_indices.items():
        if checkpoint_id not in checkpoints:
            raise ValueError(f"resumeIndices names an unknown checkpoint: {checkpoint_id}")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError(f"resume index must be a nonnegative integer: {checkpoint_id}")

    defaults = projection["defaults"]
    if not isinstance(defaults, dict):
        raise ValueError("defaults must be an object")
    for name, value in defaults.items():
        if name not in parameter_owners or not isinstance(value, str):
            raise ValueError(f"invalid parameter default: {name}")

    return {
        "parameterNodeId": parameter_node_id,
        "nodeIds": node_ids,
        "nodeOwners": node_owners,
        "parameterOwners": parameter_owners,
        "referenceOwners": reference_owners,
        "resumeIndices": resume_indices,
        "defaults": defaults,
        "checkpointOrders": checkpoints,
    }


def prepare_projection(
    inventory: CaseInventory,
    target_id: str,
    checkpoint_id: str,
    branch_id: str = "",
) -> dict[str, object]:
    """Build a non-mutating, auditable plan for a fresh saved-evidence prefix."""
    if not isinstance(inventory, CaseInventory):
        raise ValueError("inventory must be a CaseInventory")
    _text(target_id, "target_id")
    _text(checkpoint_id, "checkpoint_id")
    _text(branch_id, "branch_id", allow_empty=True)

    selection = select_prefix(inventory, target_id, checkpoint_id, branch_id)
    if not selection.allowed:
        raise ValueError("; ".join(selection.reasons) or "case prefix is blocked")

    projection = _projection_metadata(inventory)
    checkpoint_order = projection["checkpointOrders"].get(checkpoint_id)
    if checkpoint_order is None:
        raise ValueError(f"unknown checkpoint: {checkpoint_id}")
    resume_indices = projection["resumeIndices"]
    if checkpoint_id not in resume_indices:
        raise ValueError(f"missing resume index for checkpoint: {checkpoint_id}")

    included = set(selection.included_ids)
    keep = {projection["parameterNodeId"]}
    for node_id in projection["nodeIds"]:
        owners = projection["nodeOwners"][node_id]
        if owners == ["@display"] or any(owner in included for owner in owners):
            keep.add(node_id)
    remove = set(projection["nodeIds"]) - keep

    def must_clear(owner: str) -> bool:
        return owner in {"runtime", "history"} or (
            owner in projection["checkpointOrders"]
            and projection["checkpointOrders"][owner] > checkpoint_order
        )

    clear_parameters = sorted(
        name for name, owner in projection["parameterOwners"].items() if must_clear(owner)
    )
    clear_references = sorted(
        role for role, owner in projection["referenceOwners"].items()
        if must_clear(owner) or owner == "display"
    )
    missing_defaults = sorted(set(clear_parameters) - set(projection["defaults"]))
    if missing_defaults:
        raise ValueError("missing defaults for cleared parameters: " + ", ".join(missing_defaults))

    return {
        "newCaseId": selection.new_case_id,
        "keepNodeIds": sorted(keep),
        "removeNodeIds": sorted(remove),
        "clearParameters": clear_parameters,
        "clearReferenceRoles": clear_references,
        "defaults": {name: projection["defaults"][name] for name in clear_parameters},
        "workflowStageIndex": resume_indices[checkpoint_id],
        "targetId": target_id,
        "branchId": selection.branch_id,
        "checkpointId": checkpoint_id,
        "historyPolicy": "Fresh",
    }


def _empty_tooth() -> dict[str, object]:
    return {
        "target_id": "",
        "segment_id": "",
        "trajectory_set": {
            "slots": [
                {"slot": index, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []}
                for index in range(1, _SLOTS_PER_TOOTH + 1)
            ]
        },
    }


def _empty_slot(index: int) -> dict[str, object]:
    return {"slot": index, "state": "Empty", "trajectory_id": "", "prepared_branch_ids": []}


def _validate_registry(registry: object) -> tuple[dict[str, Any], dict[str, tuple[str, dict[str, Any]]]]:
    if not isinstance(registry, dict) or registry.get("schema_version") != _REGISTRY_SCHEMA:
        raise ValueError("unsupported trajectory-registry schema")
    teeth = registry.get("teeth")
    if not isinstance(teeth, dict) or set(teeth) != set(_TEETH):
        raise ValueError("trajectory registry must contain all 32 permanent teeth")
    if not isinstance(registry.get("selected_branch_id"), str):
        raise ValueError("selected branch identity must be a string")
    branches = registry.get("prepared_branches")
    if not isinstance(branches, dict):
        raise ValueError("prepared-branch registry is invalid")

    trajectory_owners: dict[str, tuple[str, dict[str, Any]]] = {}
    target_owners: dict[str, str] = {}
    slot_branch_ids: set[str] = set()
    for tooth_id in _TEETH:
        tooth = teeth[tooth_id]
        if not isinstance(tooth, dict):
            raise ValueError(f"invalid tooth record: {tooth_id}")
        target_id = tooth.get("target_id")
        segment_id = tooth.get("segment_id")
        trajectory_set = tooth.get("trajectory_set")
        if not isinstance(target_id, str) or not isinstance(segment_id, str):
            raise ValueError(f"invalid tooth identity: {tooth_id}")
        if target_id:
            if target_id in target_owners:
                raise ValueError(f"duplicate target identity: {target_id}")
            target_owners[target_id] = tooth_id
        if not isinstance(trajectory_set, dict):
            raise ValueError(f"invalid trajectory set: {tooth_id}")
        slots = trajectory_set.get("slots")
        if (not isinstance(slots, list)
                or [slot.get("slot") if isinstance(slot, dict) else None for slot in slots] != [1, 2, 3]
                or any(isinstance(slot.get("slot"), bool) or not isinstance(slot.get("slot"), int) for slot in slots)):
            raise ValueError(f"{tooth_id} must contain three ordered trajectory slots")
        for slot in slots:
            state = slot.get("state")
            trajectory_id = slot.get("trajectory_id")
            slot_branches = slot.get("prepared_branch_ids")
            if (not isinstance(state, str) or state not in {"Empty", "Current", "Stale"}
                    or not isinstance(trajectory_id, str)
                    or not isinstance(slot_branches, list)
                    or any(not isinstance(item, str) or not item.strip() for item in slot_branches)
                    or len(slot_branches) != len(set(slot_branches))):
                raise ValueError(f"invalid trajectory slot: {tooth_id}")
            slot_branch_ids.update(slot_branches)
            if state == "Empty":
                if trajectory_id or slot_branches:
                    raise ValueError("an empty trajectory slot cannot have an identity or prepared branch")
                continue
            if not trajectory_id.strip() or trajectory_id in trajectory_owners:
                raise ValueError("trajectory identities must be nonempty and unique")
            if slot.get("target_id") != target_id or not target_id:
                raise ValueError("trajectory target identity does not match its tooth")
            trajectory_owners[trajectory_id] = (tooth_id, slot)

    for branch_id, branch in branches.items():
        if (not isinstance(branch_id, str) or not branch_id or not isinstance(branch, dict)
                or branch.get("branch_id") != branch_id):
            raise ValueError("prepared branch identity is invalid")
        target_id = branch.get("target_id")
        trajectory_ids = branch.get("trajectory_ids")
        primary_id = branch.get("primary_trajectory_id")
        pairing_intent = branch.get("pairing_intent")
        state = branch.get("state")
        if (not isinstance(target_id, str) or target_id not in target_owners
                or not isinstance(trajectory_ids, list) or not 1 <= len(trajectory_ids) <= 2
                or any(not isinstance(item, str) or not item.strip() for item in trajectory_ids)
                or len(trajectory_ids) != len(set(trajectory_ids))
                or not isinstance(primary_id, str) or primary_id not in trajectory_ids
                or not isinstance(pairing_intent, str)
                or pairing_intent not in {"Single", "ExplicitPair", "LegacyUnverified"}
                or not isinstance(state, str) or state not in {"Current", "Stale"}):
            raise ValueError("prepared branch contents are invalid")
        if ((pairing_intent == "Single" and len(trajectory_ids) != 1)
                or (pairing_intent == "ExplicitPair" and len(trajectory_ids) != 2)
                or not isinstance(branch.get("planning_pose_fingerprint", ""), str)):
            raise ValueError("prepared branch contract is invalid")
        owners = {trajectory_owners.get(item, ("", {}))[0] for item in trajectory_ids}
        if len(owners) != 1 or "" in owners or target_owners[target_id] not in owners:
            raise ValueError("prepared branch belongs to a different tooth target")
        if any(branch_id not in trajectory_owners[item][1]["prepared_branch_ids"] for item in trajectory_ids):
            raise ValueError("prepared branch is not referenced by every owning trajectory")
    if slot_branch_ids != set(branches):
        raise ValueError("trajectory slots and prepared branches disagree")
    for trajectory_id, (_, slot) in trajectory_owners.items():
        if any(trajectory_id not in branches[branch_id]["trajectory_ids"] for branch_id in slot["prepared_branch_ids"]):
            raise ValueError("trajectory references a branch that does not own it")
    selected = registry["selected_branch_id"]
    if selected and selected not in branches:
        raise ValueError("selected prepared branch is not registered")
    return registry, trajectory_owners


def filter_registry(
    registry: dict[str, object],
    target_id: str,
    trajectory_ids: tuple[str, ...],
    branch_id: str,
    cutoff_order: int,
) -> dict[str, object]:
    """Return a fresh-schema registry containing only the selected target prefix."""
    _text(target_id, "target_id")
    _text(branch_id, "branch_id", allow_empty=True)
    if not isinstance(trajectory_ids, tuple) or any(not isinstance(item, str) or not item for item in trajectory_ids):
        raise ValueError("trajectory_ids must be a tuple of nonempty strings")
    if len(trajectory_ids) != len(set(trajectory_ids)):
        raise ValueError("trajectory_ids must be unique")
    if isinstance(cutoff_order, bool) or not isinstance(cutoff_order, int):
        raise ValueError("cutoff_order must be an integer")
    checkpoint_orders = {item.id: item.order for item in CHECKPOINTS}
    if cutoff_order not in checkpoint_orders.values():
        raise ValueError(f"unknown checkpoint order: {cutoff_order}")

    source, trajectory_owners = _validate_registry(registry)
    selected_tooth = next((
        tooth_id for tooth_id, record in source["teeth"].items()
        if record["target_id"] == target_id
    ), None)
    if selected_tooth is None:
        raise ValueError(f"target is not in trajectory registry: {target_id}")
    for trajectory_id in trajectory_ids:
        owner = trajectory_owners.get(trajectory_id)
        if owner is None or owner[0] != selected_tooth:
            raise ValueError(f"trajectory does not belong to selected target: {trajectory_id}")

    plan_order = checkpoint_orders["trajectory.plan"]
    build_order = checkpoint_orders["template.build"]
    keep_trajectories = cutoff_order >= plan_order
    keep_branch = cutoff_order >= build_order and bool(branch_id)
    if keep_branch and branch_id not in source["prepared_branches"]:
        raise ValueError(f"prepared branch is not registered: {branch_id}")
    if keep_branch:
        branch = source["prepared_branches"][branch_id]
        if branch["target_id"] != target_id or not set(branch["trajectory_ids"]) <= set(trajectory_ids):
            raise ValueError(f"prepared branch is outside the selected trajectory prefix: {branch_id}")

    result = deepcopy(source)
    for tooth_id in _TEETH:
        if tooth_id != selected_tooth:
            result["teeth"][tooth_id] = _empty_tooth()
            continue
        tooth = result["teeth"][tooth_id]
        slots = tooth["trajectory_set"]["slots"]
        kept_slots = []
        for index, slot in enumerate(slots, 1):
            trajectory_id = slot["trajectory_id"]
            if keep_trajectories and trajectory_id in trajectory_ids:
                kept = slot
                kept["prepared_branch_ids"] = (
                    [branch_id]
                    if keep_branch and trajectory_id in result["prepared_branches"][branch_id]["trajectory_ids"]
                    else []
                )
                kept_slots.append(kept)
            else:
                kept_slots.append(_empty_slot(index))
        tooth["trajectory_set"]["slots"] = kept_slots

    result["prepared_branches"] = (
        {branch_id: result["prepared_branches"][branch_id]} if keep_branch else {}
    )
    result["selected_branch_id"] = branch_id if keep_branch else ""
    verification_order = next(item.order for item in CHECKPOINTS if item.id == "template.verify")
    if cutoff_order < verification_order:
        for retained in result["prepared_branches"].values():
            retained["verification_revision"] = ""
    return result
