"""Pure view-preset classification used by both DENTOBOT presentations.

This module deliberately contains no Slicer, MRML, Qt, or rendering calls.
It classifies existing segmentation records and defines the stage-level
display categories; the workflow widget remains responsible for applying
those choices to MRML display nodes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace


ANATOMY_SCOPE_LABELS: dict[str, str] = {
    "none": "None",
    "target_tooth": "Target tooth",
    "target_support": "Target + support teeth",
    "upper_teeth": "Upper teeth",
    "lower_teeth": "Lower teeth",
    "all_teeth": "All teeth",
    "upper_jaw_anatomy": "Upper jaw anatomy",
    "lower_jaw_anatomy": "Lower jaw anatomy",
    "full_anatomy": "Full segmented anatomy",
    "jawbones": "Jawbones",
    "pulp_root_canals": "Pulp / root canals",
    "neural_canals": "Neural canals",
    "sinuses_airway": "Sinuses / airway",
    "restorations_implants": "Restorations / implants",
}

ANATOMY_DIMENSION_LABELS: dict[str, str] = {
    "2d": "2D",
    "3d": "3D",
    "both": "Both",
}

CBCT_MODE_LABELS: dict[str, str] = {
    "off": "Off",
    "slices": "2D slices",
    "intensity_3d": "3D intensity rendering — not a mask",
    "both": "2D + 3D intensity rendering",
}

OVERLAY_GROUP_LABELS: dict[str, str] = {
    "target_bounds": "Target bounds",
    "trajectories": "Trajectories / assisted points",
    "support_draft": "Support draft",
    "support_tools": "Support-surface tools",
    "docks": "Rails / docks and measurements",
    "shell_components": "Shell / guide components",
    "final_template": "Final template",
    "jaw_opening": "Opened-jaw planning geometry",
    "phantom": "Draft skull phantom",
    "robot": "Robot, goal and mount",
}

OVERLAY_CATEGORY_MAP: dict[str, frozenset[str]] = {
    "target_bounds": frozenset({"bounds"}),
    "trajectories": frozenset({"trajectory", "assisted"}),
    "support_draft": frozenset({"draft_support"}),
    "support_tools": frozenset(
        {"support_boundary", "support_plane", "visible_support", "insertion", "undercut", "blockout"}
    ),
    "docks": frozenset({"target_docking", "target_docking_measurement"}),
    "shell_components": frozenset({"patient_shell", "final_aux"}),
    "final_template": frozenset({"final"}),
    "jaw_opening": frozenset({"case_jaw_opening"}),
    "phantom": frozenset({"phantom", "phantom_landmarks"}),
    "robot": frozenset(
        {"robot_mrml", "robot_ros", "robot_goal", "robot_mount", "forehead_proxy"}
    ),
}


@dataclass(frozen=True)
class ViewComposition:
    """Pure, serializable display intent shared by both GUI presentations."""

    anatomy_scope: str = "none"
    anatomy_dimension: str = "both"
    cbct_mode: str = "off"
    overlay_groups: frozenset[str] = frozenset()
    anatomy_opacity: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "overlay_groups", frozenset(self.overlay_groups))
        if self.anatomy_scope not in ANATOMY_SCOPE_LABELS:
            raise ValueError(f"Unknown anatomy scope: {self.anatomy_scope}")
        if self.anatomy_dimension not in ANATOMY_DIMENSION_LABELS:
            raise ValueError(f"Unknown anatomy dimension: {self.anatomy_dimension}")
        if self.cbct_mode not in CBCT_MODE_LABELS:
            raise ValueError(f"Unknown CBCT mode: {self.cbct_mode}")
        unknown = self.overlay_groups - set(OVERLAY_GROUP_LABELS)
        if unknown:
            raise ValueError(f"Unknown overlay group(s): {sorted(unknown)}")
        opacity = float(self.anatomy_opacity)
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("Anatomy opacity must be between 0 and 1")
        object.__setattr__(self, "anatomy_opacity", opacity)

    def updated(self, **changes) -> "ViewComposition":
        return replace(self, **changes)

    def to_dict(self) -> dict[str, object]:
        return {
            "anatomy_scope": self.anatomy_scope,
            "anatomy_dimension": self.anatomy_dimension,
            "cbct_mode": self.cbct_mode,
            "overlay_groups": sorted(self.overlay_groups),
            "anatomy_opacity": self.anatomy_opacity,
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, object]) -> "ViewComposition":
        return cls(
            anatomy_scope=str(values.get("anatomy_scope", "none")),
            anatomy_dimension=str(values.get("anatomy_dimension", "both")),
            cbct_mode=str(values.get("cbct_mode", "off")),
            overlay_groups=frozenset(values.get("overlay_groups", ())),
            anatomy_opacity=float(values.get("anatomy_opacity", 1.0)),
        )


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


RECOMMENDED_VIEW_COMPOSITIONS: dict[int, ViewComposition] = {
    0: ViewComposition(cbct_mode="slices"),
    1: ViewComposition(cbct_mode="slices"),
    2: ViewComposition(
        anatomy_scope="full_anatomy",
        anatomy_dimension="both",
        cbct_mode="slices",
    ),
    3: ViewComposition(
        anatomy_scope="full_anatomy",
        anatomy_dimension="both",
        cbct_mode="slices",
    ),
    4: ViewComposition(
        anatomy_scope="target_tooth",
        anatomy_dimension="both",
        cbct_mode="slices",
        overlay_groups=frozenset({"target_bounds", "trajectories"}),
    ),
    5: ViewComposition(
        anatomy_scope="target_support",
        anatomy_dimension="3d",
        overlay_groups=frozenset({"support_draft"}),
        anatomy_opacity=0.35,
    ),
    6: ViewComposition(
        anatomy_scope="target_support",
        anatomy_dimension="3d",
        overlay_groups=frozenset(
            {"trajectories", "support_draft", "docks"}
        ),
        anatomy_opacity=0.35,
    ),
    7: ViewComposition(
        anatomy_scope="target_support",
        anatomy_dimension="3d",
        overlay_groups=frozenset({"support_tools"}),
        anatomy_opacity=0.35,
    ),
    8: ViewComposition(
        anatomy_scope="full_anatomy",
        anatomy_dimension="3d",
        overlay_groups=frozenset(
            {"trajectories", "docks", "shell_components"}
        ),
        anatomy_opacity=0.35,
    ),
    9: ViewComposition(
        anatomy_scope="full_anatomy",
        anatomy_dimension="3d",
        overlay_groups=frozenset({"docks", "final_template"}),
        anatomy_opacity=0.35,
    ),
    10: ViewComposition(
        anatomy_scope="full_anatomy",
        anatomy_dimension="3d",
        cbct_mode="slices",
        overlay_groups=frozenset(
            {"target_bounds", "trajectories", "docks", "final_template", "jaw_opening", "robot"}
        ),
        anatomy_opacity=0.35,
    ),
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


def recommended_view_composition(stage_index: int) -> ViewComposition:
    """Return one immutable stage composition; callers may derive a local copy."""

    return RECOMMENDED_VIEW_COMPOSITIONS.get(int(stage_index), ViewComposition())


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


DETAILED_ANATOMY_GROUP_CATEGORY: dict[str, str] = {
    "upper_teeth": "upper_teeth",
    "lower_teeth": "lower_teeth",
    "upper_pulp": "pulp_root_canals",
    "lower_pulp": "pulp_root_canals",
    "upper_jawbone": "jaws",
    "lower_jawbone": "jaws",
    "upper_sinus": "sinuses_airway",
    "lower_neural": "neural_canals",
    "neutral_airway": "sinuses_airway",
    "upper_restoration": "restorations_implants",
    "lower_restoration": "restorations_implants",
    "neutral_restoration": "restorations_implants",
    "other_mask": "other_mask",
}

DETAILED_ANATOMY_GROUP_LABELS: dict[str, str] = {
    "upper_teeth": "Teeth — upper jaw",
    "lower_teeth": "Teeth — lower jaw",
    "upper_pulp": "Pulp / root canals — upper jaw",
    "lower_pulp": "Pulp / root canals — lower jaw",
    "upper_jawbone": "Maxilla / upper jawbone",
    "lower_jawbone": "Mandible / lower jawbone",
    "upper_sinus": "Maxillary sinuses",
    "lower_neural": "Mandibular / inferior-alveolar canals",
    "neutral_airway": "Airway / pharynx / unassigned sinus",
    "upper_restoration": "Restorations / implants — upper jaw",
    "lower_restoration": "Restorations / implants — lower jaw",
    "neutral_restoration": "Unassigned restorations / implants",
    "other_mask": "Other / adjacent anatomy",
}


def _record_jaw(record: Mapping[str, object]) -> str | None:
    jaw = dental_jaw_from_fdi(record.get("fdiNumber"))
    if jaw:
        return jaw
    source_name = str(record.get("sourceName") or "").strip().lower()
    category = str(record.get("category") or "")
    if any(token in source_name for token in ("maxilla", "upper_jawbone", "maxillary_sinus")):
        return "upper"
    if any(
        token in source_name
        for token in (
            "mandible",
            "lower_jawbone",
            "mandibular_canal",
            "inferior_alveolar",
        )
    ):
        return "lower"
    if category == "Neural and mandibular canals":
        return "lower"
    return None


def detailed_anatomy_group(record: Mapping[str, object]) -> str:
    """Classify one reviewed segment using labels/metadata, never geometry."""

    category = str(record.get("category") or "")
    jaw = _record_jaw(record)
    if category == "Teeth" and jaw:
        return f"{jaw}_teeth"
    if category == "Pulp and root canals" and jaw:
        return f"{jaw}_pulp"
    if category == "Jaws" and jaw:
        return f"{jaw}_jawbone"
    if category == "Neural and mandibular canals":
        return "lower_neural"
    if category == "Sinuses and airway":
        return "upper_sinus" if jaw == "upper" else "neutral_airway"
    if category == "Restorations and implants":
        return f"{jaw}_restoration" if jaw else "neutral_restoration"
    return "other_mask"


def group_segmentation_records_detailed(
    records: Iterable[Mapping[str, object]],
) -> dict[str, list[str]]:
    """Return jaw-aware anatomy groups while retaining stable segment IDs."""

    grouped = {key: [] for key in DETAILED_ANATOMY_GROUP_CATEGORY}
    for record in records:
        segment_id = str(record.get("segmentId") or "").strip()
        if not segment_id:
            continue
        key = detailed_anatomy_group(record)
        if segment_id not in grouped[key]:
            grouped[key].append(segment_id)
    return grouped


def anatomy_scopes_for_group(group_key: str) -> frozenset[str]:
    """Return routine scopes containing one detailed anatomy group."""

    scopes = {"full_anatomy"}
    if group_key == "upper_teeth":
        scopes.update({"upper_teeth", "all_teeth", "upper_jaw_anatomy"})
    elif group_key == "lower_teeth":
        scopes.update({"lower_teeth", "all_teeth", "lower_jaw_anatomy"})
    elif group_key.startswith("upper_"):
        scopes.add("upper_jaw_anatomy")
    elif group_key.startswith("lower_"):
        scopes.add("lower_jaw_anatomy")
    if group_key.endswith("_jawbone"):
        scopes.add("jawbones")
    if group_key.endswith("_pulp"):
        scopes.add("pulp_root_canals")
    if group_key == "lower_neural":
        scopes.add("neural_canals")
    if group_key in {"upper_sinus", "neutral_airway"}:
        scopes.add("sinuses_airway")
    if group_key.endswith("_restoration"):
        scopes.add("restorations_implants")
    return frozenset(scopes)
