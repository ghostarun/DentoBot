"""Shared provenance rules for opt-in manual-jog outcome scenarios."""

import json


def fixture_identity(
    *,
    branch_id,
    task_core,
    home_revision,
    home_joint_positions_si,
    scene_source_object_ids,
    scene_base_fingerprint,
    fingerprint_fn,
):
    return fingerprint_fn(
        {
            "branch_id": branch_id,
            "task_core": task_core,
            "home_revision": int(home_revision),
            "home_joint_positions_si": home_joint_positions_si,
            "scene_source_object_ids": scene_source_object_ids,
            "scene_base_fingerprint": scene_base_fingerprint,
        }
    )


def rejection_plan(
    raw_plan, *, case_sha256, fixture_identity_value, finite_vector
):
    if not raw_plan.strip():
        return None, "No exact pre-reviewed rejection vector was supplied."
    try:
        plan = json.loads(raw_plan)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Rejection plan is not valid JSON: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != "1.0":
        raise ValueError("Rejection plan schema_version must be '1.0'.")
    if plan.get("case_sha256") != case_sha256:
        raise ValueError("Rejection plan belongs to a different saved case.")
    if plan.get("fixture_identity") != fixture_identity_value:
        raise ValueError("Rejection plan belongs to a different fixture identity.")
    start = finite_vector(plan.get("starting_positions_si"))
    target = finite_vector(plan.get("requested_positions_si"))
    return {
        "starting_positions_si": start,
        "requested_positions_si": target,
        "case_sha256": case_sha256,
        "fixture_identity": fixture_identity_value,
        "review_reference": str(plan.get("review_reference") or ""),
    }, ""
