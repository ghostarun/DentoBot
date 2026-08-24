"""Pure view-preset classification used by both DENTOBOT presentations.

This module deliberately contains no Slicer, MRML, Qt, or rendering calls.
It classifies existing segmentation records and defines the stage-level
display categories; the workflow widget remains responsible for applying
those choices to MRML display nodes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


STAGE_RECOMMENDED_CATEGORIES: dict[int, frozenset[str]] = {
    0: frozenset({"case_volume"}),
    1: frozenset({"case_volume"}),
    2: frozenset(
        {
            "case_volume",
            "upper_teeth",
            "lower_teeth",
            "pulp_root_canals",
            "neural_canals",
            "jaws",
            "sinuses_airway",
            "restorations_implants",
            "other_mask",
        }
    ),
    3: frozenset(
        {
            "case_volume",
            "upper_teeth",
            "lower_teeth",
            "pulp_root_canals",
            "neural_canals",
            "jaws",
            "sinuses_airway",
            "restorations_implants",
            "other_mask",
        }
    ),
    4: frozenset({"target_mask", "bounds", "trajectory", "assisted"}),
    5: frozenset({"target_mask", "support_mask", "draft_support"}),
    6: frozenset(
        {
            "target_mask",
            "support_mask",
            "draft_support",
            "trajectory",
            "target_docking",
            "target_docking_measurement",
        }
    ),
    7: frozenset(
        {
            "target_mask",
            "support_mask",
            "support_boundary",
            "support_plane",
            "visible_support",
        }
    ),
    8: frozenset({"patient_shell", "trajectory", "target_docking"}),
    9: frozenset({"patient_shell", "target_docking"}),
    10: frozenset(
        {
            "case_volume",
            "target_mask",
            "bounds",
            "trajectory",
            "target_docking",
            "final",
            "robot_mount",
            "robot_mrml",
        }
    ),
}


STAGE_RECOMMENDATION_DESCRIPTIONS: dict[int, str] = {
    0: "Case volume in slice views, when available",
    1: "CBCT volume in slice views",
    2: "CBCT slices with all grouped segmentation masks",
    3: "CBCT slices with all grouped segmentation masks for review",
    4: "Target tooth, target bounds, and trajectory context",
    5: "Target tooth, selected support teeth, and support draft",
    6: "Support package, selected trajectory, rails, and docks",
    7: "Support masks, boundary, plane, and visible-surface preview",
    8: "Current shell/guide result, or the final template when available",
    9: "Final printable template, or current shell and docks",
    10: "Active case or phantom with robot and locked mount context",
}


SEGMENT_CATEGORY_TO_VIEW_GROUP = {
    "Pulp and root canals": "pulp_root_canals",
    "Neural and mandibular canals": "neural_canals",
    "Jaws": "jaws",
    "Sinuses and airway": "sinuses_airway",
    "Restorations and implants": "restorations_implants",
    "Other anatomy": "other_mask",
}


def recommended_view_categories(stage_index: int) -> set[str]:
    """Return a copy so callers may safely add state-dependent categories."""

    return set(STAGE_RECOMMENDED_CATEGORIES.get(int(stage_index), frozenset()))


def recommended_view_description(stage_index: int) -> str:
    """Return a concise operator-facing explanation for one internal stage."""

    return STAGE_RECOMMENDATION_DESCRIPTIONS.get(
        int(stage_index),
        "Current workflow context",
    )


def dental_jaw_from_fdi(fdi_number: object) -> str | None:
    """Classify a permanent-tooth FDI number as upper or lower jaw."""

    value = str(fdi_number or "").strip()
    if len(value) != 2 or value[0] not in "1234" or value[1] not in "12345678":
        return None
    return "upper" if value[0] in "12" else "lower"


def group_segmentation_records(
    records: Iterable[Mapping[str, object]],
) -> dict[str, list[str]]:
    """Group existing segment IDs into operator-facing anatomy collections."""

    grouped: dict[str, list[str]] = {
        "upper_teeth": [],
        "lower_teeth": [],
        "pulp_root_canals": [],
        "neural_canals": [],
        "jaws": [],
        "sinuses_airway": [],
        "restorations_implants": [],
        "other_mask": [],
    }
    for record in records:
        segment_id = str(record.get("segmentId") or "").strip()
        if not segment_id:
            continue
        category = str(record.get("category") or "")
        if category == "Teeth":
            jaw = dental_jaw_from_fdi(record.get("fdiNumber"))
            key = f"{jaw}_teeth" if jaw else "other_mask"
        else:
            key = SEGMENT_CATEGORY_TO_VIEW_GROUP.get(category, "other_mask")
        if segment_id not in grouped[key]:
            grouped[key].append(segment_id)
    return grouped
