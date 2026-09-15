"""Pure contracts for canonical dental identity and pulp association."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from dentobot_workflow.dental_semantics import (  # noqa: E402
    apply_pulp_association,
    associate_pulp_components,
    build_segment_record,
    normalize_source_label,
    occupied_components,
    pulp_record_is_planning_ready,
    rank_pulp_component,
    semantic_document,
    semantic_fingerprint,
)


def _record(
    segment_id: str,
    source_name: str,
    *,
    structure_type_hint: str | None = None,
    fdi_hint: str | None = None,
) -> dict:
    return build_segment_record(
        segment_id=segment_id,
        label_id=1 if segment_id.startswith("t") else 2,
        source_name=source_name,
        voxel_count=10,
        volume_mm3=10.0,
        structure_type_hint=structure_type_hint,
        fdi_hint=fdi_hint,
    )


def _candidate(
    tooth_id: str,
    fdi: str,
    *,
    inside: float = 1.0,
    nearest: float = 1.0,
    distance: float = 1.0,
    source_hint: str | None = None,
) -> dict:
    return {
        "toothSegmentId": tooth_id,
        "toothFdiNumber": fdi,
        "insideFraction": inside,
        "nearestToothFraction": nearest,
        "robustSurfaceDistanceMm": distance,
        "sourceFdiHint": source_hint,
    }


def _association(
    pulp_id: str,
    target_id: str,
    candidates: list[dict],
    *,
    components: list[tuple[int, int, int]] | None = None,
) -> dict:
    component_points = components or [(0, 0, 0)]
    component_ids = occupied_components(component_points)
    return associate_pulp_components(
        [
            {
                "componentId": f"{pulp_id}#component-{index}",
                "sourceSegmentId": pulp_id,
                "candidates": candidates,
            }
            for index, _component in enumerate(component_ids, 1)
        ],
        target_id,
    )


def test_a_raw_fdi_tooth_and_pulp_hint_form_a_high_confidence_pair():
    tooth = _record("t11", "upper_right_central_incisor_fdi11")
    pulp = _record("p11", "upper_right_central_incisor_pulp_fdi111")
    association = _association(
        "p11",
        "t11",
        [_candidate("t11", "11", source_hint=pulp["sourceFdiHint"])],
    )

    assert association["validationState"] == "VALID"
    assert association["associationConfidence"] == "HIGH"
    result = apply_pulp_association([tooth, pulp], association)
    paired = next(record for record in result if record["segmentId"] == "p11")
    assert paired["canonicalName"] == "Pulp_FDI11"
    assert paired["parentToothSegmentIds"] == ["t11"]
    assert pulp_record_is_planning_ready(paired, "t11")


def test_b_generic_pulp_name_uses_geometry_selected_parent():
    tooth = _record("t11", "tooth_primary", structure_type_hint="TOOTH", fdi_hint="11")
    pulp = _record("p11", "internal_structure_alpha", structure_type_hint="PULP")
    association = _association("p11", "t11", [_candidate("t11", "11")])

    result = apply_pulp_association([tooth, pulp], association)
    paired = next(record for record in result if record["segmentId"] == "p11")
    assert paired["canonicalName"] == "Pulp_FDI11"
    assert paired["associationMethod"] == "spatial"


def test_c_geometry_disagreement_is_preserved_and_not_overridden_by_hint():
    tooth11 = _record("t11", "tooth_11", structure_type_hint="TOOTH", fdi_hint="11")
    tooth21 = _record("t21", "tooth_21", structure_type_hint="TOOTH", fdi_hint="21")
    pulp = _record("p11", "pulp_fdi111")
    association = _association(
        "p11",
        "t21",
        [
            _candidate("t21", "21", inside=0.98, nearest=0.98, source_hint="11"),
            _candidate("t11", "11", inside=0.65, nearest=0.78, distance=5.0, source_hint="11"),
        ],
    )

    assert association["validationState"] == "VALID"
    assert association["associationConfidence"] == "MEDIUM"
    decision = association["components"][0]
    assert decision["toothFdiNumber"] == "21"
    assert decision["hintDisagreement"]
    result = apply_pulp_association([tooth11, tooth21, pulp], association)
    paired = next(record for record in result if record["segmentId"] == "p11")
    assert paired["canonicalName"] == "Pulp_FDI21"
    assert paired["associationEvidence"]["hintDisagreement"]


def test_d_missing_pulp_components_is_blocked_without_fabrication():
    association = associate_pulp_components([], "t11")

    assert association["validationState"] == "MISSING"
    assert association["parentToothSegmentIds"] == []


def test_e_close_adjacent_candidates_are_ambiguous():
    decision = rank_pulp_component(
        "p11#component-1",
        [
            _candidate("t11", "11"),
            _candidate("t21", "21"),
        ],
    )

    assert decision["validationState"] == "AMBIGUOUS"
    assert decision["toothSegmentId"] is None


def test_f_fragmented_same_source_is_allowed_but_cross_tooth_or_duplicate_source_is_not():
    same_source = _association(
        "p11",
        "t11",
        [_candidate("t11", "11")],
        components=[(0, 0, 0), (0, 0, 1), (3, 3, 3)],
    )
    assert same_source["validationState"] == "VALID"
    assert len(same_source["components"]) == 2

    cross_tooth = associate_pulp_components(
        [
            {
                "componentId": "p11#component-1",
                "sourceSegmentId": "p11",
                "candidates": [_candidate("t11", "11")],
            },
            {
                "componentId": "p11#component-2",
                "sourceSegmentId": "p11",
                "candidates": [_candidate("t21", "21")],
            },
        ],
        "t11",
    )
    assert cross_tooth["validationState"] == "AMBIGUOUS"

    duplicate_source = associate_pulp_components(
        [
            {
                "componentId": "p11#component-1",
                "sourceSegmentId": "p11-a",
                "candidates": [_candidate("t11", "11")],
            },
            {
                "componentId": "p11#component-2",
                "sourceSegmentId": "p11-b",
                "candidates": [_candidate("t11", "11")],
            },
        ],
        "t11",
    )
    assert duplicate_source["validationState"] == "INVALID"
    with pytest.raises(ValueError, match="Only a valid pulp association"):
        apply_pulp_association(
            [_record("p11-a", "pulp_a", structure_type_hint="PULP"), _record("p11-b", "pulp_b", structure_type_hint="PULP")],
            duplicate_source,
        )


def test_g_canonical_registry_round_trips_and_fingerprint_ignores_raw_renames():
    tooth = _record("t31", "lower_left_central_incisor_fdi31")
    pulp = _record("p31", "lower_left_central_incisor_pulp_fdi131")
    association = _association(
        "p31",
        "t31",
        [_candidate("t31", "31", source_hint=pulp["sourceFdiHint"])],
    )
    records = apply_pulp_association([tooth, pulp], association)
    document = semantic_document(records)
    restored = json.loads(json.dumps(document))
    assert restored["schemaVersion"] == "1.0"
    restored_pulp = next(item for item in restored["segments"] if item["segmentId"] == "p31")
    assert restored_pulp["parentToothSegmentIds"] == ["t31"]
    assert restored_pulp["canonicalName"] == "Pulp_FDI31"

    renamed = deepcopy(records)
    renamed[0]["sourceName"] = "backend-renamed-tooth"
    renamed[1]["sourceName"] = "backend-renamed-pulp"
    assert semantic_fingerprint(records) == semantic_fingerprint(renamed)


def test_h_explicit_adapter_facts_survive_changed_names_and_unadaptable_names_block():
    adapted = normalize_source_label(
        "structure_alpha",
        structure_type_hint="TOOTH",
        fdi_hint="31",
    )
    assert adapted["canonicalName"] == "Tooth_FDI31"
    assert adapted["validationState"] == "VALID"

    unadaptable = normalize_source_label("structure_alpha", structure_type_hint="OTHER")
    assert unadaptable["canonicalName"] is None
    assert unadaptable["validationState"] == "UNRESOLVED"
    assert not pulp_record_is_planning_ready(unadaptable, "t31")
