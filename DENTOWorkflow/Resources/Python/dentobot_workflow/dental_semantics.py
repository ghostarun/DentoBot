"""Pure dental-structure normalization and pulp-association decisions.

The module deliberately accepts plain records and precomputed geometry
evidence.  Slicer/VTK code stays at the MRML boundary; raw backend names are
provenance and never decide a pulp parent without spatial evidence.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence


SEMANTIC_SCHEMA_VERSION = "1.0"

SEMANTIC_STATUS_CURRENT = "current"
SEMANTIC_STATUS_NEEDS_ASSOCIATION = "needs-association"
SEMANTIC_STATUS_NEEDS_REVIEW = "needs-review"

STRUCTURE_TYPES = (
    "TOOTH",
    "PULP",
    "CANAL",
    "JAW",
    "AIRWAY",
    "RESTORATION",
    "OTHER",
)

VALIDATION_STATES = (
    "VALID",
    "AMBIGUOUS",
    "MISSING",
    "INVALID",
    "MANUALLY_CONFIRMED",
    "UNRESOLVED",
)

ASSOCIATION_CONFIDENCES = ("HIGH", "MEDIUM")

# These are deliberately explicit and versioned by the semantic schema.  They
# are gates over already-computed geometry evidence, not a substitute for a
# surface/voxel measurement implementation.
DEFAULT_ASSOCIATION_POLICY = {
    "minInsideFraction": 0.50,
    "minNearestToothFraction": 0.75,
    "maxRobustSurfaceDistanceMm": 10.0,
    "minScoreMargin": 0.10,
    "highScoreMargin": 0.20,
}

_CANONICAL_RECORD_KEYS = (
    "segmentId",
    "sourceLabelId",
    "structureType",
    "canonicalName",
    "fdiNumber",
    "parentToothSegmentIds",
    "associationMethod",
    "associationConfidence",
    "validationState",
    "associationEvidence",
)

_CATEGORY_BY_STRUCTURE = {
    "TOOTH": "Teeth",
    "PULP": "Pulp and root canals",
    "CANAL": "Neural and mandibular canals",
    "JAW": "Jaws",
    "AIRWAY": "Sinuses and airway",
    "RESTORATION": "Restorations and implants",
    "OTHER": "Other anatomy",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _valid_fdi(value: object) -> str | None:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[1-4][1-8]", text) else None


def _finite_fraction(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite fraction")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{field} must be a finite fraction")
    return result


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be finite and non-negative")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{field} must be finite and non-negative")
    return result


def _structure_from_source_name(source_name: str) -> str:
    name = source_name.lower()
    if "pulp" in name:
        return "PULP"
    if "canal" in name:
        return "CANAL"
    if "jawbone" in name or name in {"mandible", "maxilla"}:
        return "JAW"
    if any(token in name for token in ("sinus", "pharynx", "airway")):
        return "AIRWAY"
    if any(token in name for token in ("bridge", "crown", "implant", "restoration")):
        return "RESTORATION"
    return "TOOTH" if re.search(r"_fdi[1-4][1-8]$", name) else "OTHER"


def normalize_source_label(
    source_name: str,
    *,
    structure_type_hint: str | None = None,
    fdi_hint: str | None = None,
) -> dict[str, str | None]:
    """Normalize backend facts without making them a planning decision.

    ``structure_type_hint`` and ``fdi_hint`` are explicit adapter inputs for a
    backend whose terminology changes.  If absent, the current report naming
    grammar is used only to populate review/provenance fields.
    """

    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError("A source segment name is required.")
    source_name = source_name.strip()
    normalized = source_name.lower()
    fdi_match = re.search(r"_fdi(\d+)$", normalized)
    source_fdi_code = fdi_match.group(1) if fdi_match else None
    base_name = normalized[: fdi_match.start()] if fdi_match else normalized
    structure_type = (
        str(structure_type_hint or "").strip().upper()
        or _structure_from_source_name(source_name)
    )
    if structure_type not in STRUCTURE_TYPES:
        raise ValueError(f"Unsupported dental structure type: {structure_type}")

    source_fdi_hint = _valid_fdi(fdi_hint)
    if source_fdi_hint is None and source_fdi_code:
        if len(source_fdi_code) == 2:
            source_fdi_hint = _valid_fdi(source_fdi_code)
        elif (
            structure_type == "PULP"
            and len(source_fdi_code) == 3
            and source_fdi_code.startswith("1")
        ):
            source_fdi_hint = _valid_fdi(source_fdi_code[1:])

    canonical_fdi = source_fdi_hint if structure_type == "TOOTH" else None
    canonical_name = (
        f"Tooth_FDI{canonical_fdi}" if canonical_fdi else None
    )
    state = "VALID" if canonical_fdi else "UNRESOLVED"
    if structure_type == "PULP":
        state = "UNRESOLVED"
    return {
        "sourceName": source_name,
        "sourceFdiCode": source_fdi_code,
        "sourceFdiHint": source_fdi_hint,
        "structureType": structure_type,
        "canonicalName": canonical_name,
        "fdiNumber": canonical_fdi,
        "validationState": state,
        "category": _CATEGORY_BY_STRUCTURE[structure_type],
        "baseName": base_name,
    }


def build_segment_record(
    *,
    segment_id: str,
    label_id: int,
    source_name: str,
    voxel_count: int,
    volume_mm3: float,
    structure_type_hint: str | None = None,
    fdi_hint: str | None = None,
) -> dict[str, Any]:
    """Build one canonical MRML-ready record from validated raw metrics."""

    segment_id = str(segment_id or "").strip()
    if not segment_id:
        raise ValueError("A segment ID is required.")
    label_id = int(label_id)
    if label_id <= 0:
        raise ValueError("A source label ID must be positive.")
    voxel_count = int(voxel_count)
    if voxel_count <= 0:
        raise ValueError("A segment voxel count must be positive.")
    volume_mm3 = float(volume_mm3)
    if not math.isfinite(volume_mm3) or volume_mm3 <= 0.0:
        raise ValueError("A segment volume must be finite and positive.")

    descriptor = normalize_source_label(
        source_name,
        structure_type_hint=structure_type_hint,
        fdi_hint=fdi_hint,
    )
    return {
        "segmentId": segment_id,
        "sourceLabelId": label_id,
        "sourceName": descriptor["sourceName"],
        "sourceFdiCode": descriptor["sourceFdiCode"],
        "sourceFdiHint": descriptor["sourceFdiHint"],
        "structureType": descriptor["structureType"],
        "canonicalName": descriptor["canonicalName"],
        "fdiNumber": descriptor["fdiNumber"],
        "parentToothSegmentIds": [],
        "associationMethod": None,
        "associationConfidence": None,
        "validationState": descriptor["validationState"],
        "associationEvidence": {
            "source": "validated-report-label",
            "sourceFdiCode": descriptor["sourceFdiCode"],
        },
        "labelId": label_id,
        "voxelCount": voxel_count,
        "volumeMm3": volume_mm3,
    }


def presentation_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project canonical data into the existing review-tree presentation."""

    source_name = str(record.get("sourceName") or "").strip()
    if not source_name:
        raise ValueError("A canonical record has no source name.")
    normalized = source_name.lower()
    fdi_match = re.search(r"_fdi(\d+)$", normalized)
    base_name = normalized[: fdi_match.start()] if fdi_match else normalized
    canonical_fdi = str(record.get("fdiNumber") or "")
    source_hint = str(record.get("sourceFdiHint") or "")
    # The hint is display/search context only until a pulp association writes
    # the canonical FDI and a VALID/MANUALLY_CONFIRMED state.
    display_fdi = canonical_fdi or (
        source_hint if record.get("structureType") == "PULP" else ""
    )
    anatomy_name = " ".join(
        word.capitalize() for word in base_name.split("_") if word
    )
    display_name = (
        f"FDI {display_fdi} — {anatomy_name}"
        if display_fdi
        else anatomy_name
    )
    category = _CATEGORY_BY_STRUCTURE.get(
        str(record.get("structureType") or "OTHER"),
        "Other anatomy",
    )
    search_text = " ".join(
        value.lower()
        for value in (
            source_name,
            display_name,
            category,
            str(record.get("sourceFdiCode") or ""),
            canonical_fdi,
            source_hint,
        )
        if value
    )
    return {
        "sourceName": source_name,
        "displayName": display_name,
        "category": category,
        "fdiNumber": canonical_fdi or (source_hint or None),
        "canonicalFdiNumber": canonical_fdi or None,
        "sourceFdiCode": record.get("sourceFdiCode"),
        "searchText": search_text,
    }


def _without_source_provenance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_source_provenance(item)
            for key, item in value.items()
            if key not in {"sourceName", "sourceFdiCode", "sourceFdiHint"}
        }
    if isinstance(value, list):
        return [_without_source_provenance(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_without_source_provenance(item) for item in value)
    return deepcopy(value)


def _fingerprint_record(record: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        key: deepcopy(record.get(key))
        for key in _CANONICAL_RECORD_KEYS
        if key != "associationEvidence"
    }
    evidence = record.get("associationEvidence")
    if isinstance(evidence, Mapping):
        result["associationEvidence"] = _without_source_provenance(evidence)
    else:
        result["associationEvidence"] = {}
    return result


def semantic_fingerprint(records: Sequence[Mapping[str, Any]]) -> str:
    """Fingerprint canonical identity/relations, excluding raw display names."""

    stable = sorted(
        (_fingerprint_record(record) for record in records),
        key=lambda record: str(record.get("segmentId") or ""),
    )
    return hashlib.sha256(_canonical_json(stable).encode("utf-8")).hexdigest()


def semantic_status(records: Sequence[Mapping[str, Any]]) -> str:
    states = {str(record.get("validationState") or "UNRESOLVED") for record in records}
    if states & {"INVALID", "AMBIGUOUS", "MISSING"}:
        return SEMANTIC_STATUS_NEEDS_REVIEW
    if "UNRESOLVED" in states:
        return SEMANTIC_STATUS_NEEDS_ASSOCIATION
    return SEMANTIC_STATUS_CURRENT


def semantic_document(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    canonical_records = [
        {
            key: deepcopy(record.get(key))
            for key in _CANONICAL_RECORD_KEYS
        }
        for record in sorted(
            records,
            key=lambda record: str(record.get("segmentId") or ""),
        )
    ]
    return {
        "schemaVersion": SEMANTIC_SCHEMA_VERSION,
        "status": semantic_status(records),
        "fingerprint": semantic_fingerprint(records),
        "segments": canonical_records,
    }


def occupied_components(points: Sequence[Sequence[int]]) -> list[list[tuple[int, int, int]]]:
    """Return deterministic 6-connected components from occupied IJK points."""

    remaining = set()
    for point in points:
        if len(point) != 3:
            raise ValueError("An occupied voxel coordinate must have three values.")
        try:
            normalized = tuple(int(value) for value in point)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("An occupied voxel coordinate must be integral.") from exc
        if tuple(float(value) for value in point) != tuple(float(value) for value in normalized):
            raise ValueError("An occupied voxel coordinate must be integral.")
        remaining.add(normalized)

    components = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        stack = [seed]
        component = [seed]
        while stack:
            x, y, z = stack.pop()
            for neighbor in (
                (x - 1, y, z),
                (x + 1, y, z),
                (x, y - 1, z),
                (x, y + 1, z),
                (x, y, z - 1),
                (x, y, z + 1),
            ):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
                    component.append(neighbor)
        components.append(sorted(component))
    components.sort(key=lambda component: component[0])
    return components


def _association_score(candidate: Mapping[str, Any]) -> float:
    inside = _finite_fraction(candidate.get("insideFraction"), "insideFraction")
    nearest = _finite_fraction(
        candidate.get("nearestToothFraction"),
        "nearestToothFraction",
    )
    robust_distance = _finite_nonnegative(
        candidate.get("robustSurfaceDistanceMm"),
        "robustSurfaceDistanceMm",
    )
    # Distance only breaks ties; enclosure and nearest-tooth consistency carry
    # the decision so centroid proximity cannot become the sole rule.
    return round(
        0.55 * inside
        + 0.35 * nearest
        + 0.10 * (1.0 / (1.0 + robust_distance)),
        9,
    )


def rank_pulp_component(
    component_id: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Rank one component against all tooth surfaces and fail closed."""

    component_id = str(component_id or "").strip()
    if not component_id:
        raise ValueError("A pulp component ID is required.")
    if not candidates:
        return {
            "componentId": component_id,
            "validationState": "MISSING",
            "associationConfidence": None,
            "reason": "no tooth candidates",
            "candidates": [],
        }
    settings = {**DEFAULT_ASSOCIATION_POLICY, **dict(policy or {})}
    try:
        thresholds = {
            "minInsideFraction": _finite_fraction(
                settings["minInsideFraction"], "minInsideFraction"
            ),
            "minNearestToothFraction": _finite_fraction(
                settings["minNearestToothFraction"],
                "minNearestToothFraction",
            ),
            "maxRobustSurfaceDistanceMm": _finite_nonnegative(
                settings["maxRobustSurfaceDistanceMm"],
                "maxRobustSurfaceDistanceMm",
            ),
            "minScoreMargin": _finite_fraction(
                settings["minScoreMargin"], "minScoreMargin"
            ),
            "highScoreMargin": _finite_fraction(
                settings["highScoreMargin"], "highScoreMargin"
            ),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "componentId": component_id,
            "validationState": "INVALID",
            "associationConfidence": None,
            "reason": f"invalid association policy: {exc}",
            "candidates": [],
        }
    if thresholds["highScoreMargin"] < thresholds["minScoreMargin"]:
        return {
            "componentId": component_id,
            "validationState": "INVALID",
            "associationConfidence": None,
            "reason": "high score margin is below minimum score margin",
            "candidates": [],
        }

    normalized = []
    seen_tooth_ids = set()
    try:
        for candidate in candidates:
            tooth_id = str(candidate.get("toothSegmentId") or "").strip()
            tooth_fdi = _valid_fdi(candidate.get("toothFdiNumber"))
            if not tooth_id or not tooth_fdi or tooth_id in seen_tooth_ids:
                raise ValueError("candidate tooth identity is missing or duplicated")
            seen_tooth_ids.add(tooth_id)
            inside = _finite_fraction(candidate.get("insideFraction"), "insideFraction")
            nearest = _finite_fraction(
                candidate.get("nearestToothFraction"),
                "nearestToothFraction",
            )
            robust_distance = _finite_nonnegative(
                candidate.get("robustSurfaceDistanceMm"),
                "robustSurfaceDistanceMm",
            )
            item = deepcopy(dict(candidate))
            item.update(
                {
                    "componentId": component_id,
                    "toothSegmentId": tooth_id,
                    "toothFdiNumber": tooth_fdi,
                    "insideFraction": inside,
                    "nearestToothFraction": nearest,
                    "robustSurfaceDistanceMm": robust_distance,
                    "score": _association_score(candidate),
                }
            )
            item["passesSpatialGate"] = bool(
                inside >= thresholds["minInsideFraction"]
                and nearest >= thresholds["minNearestToothFraction"]
                and robust_distance <= thresholds["maxRobustSurfaceDistanceMm"]
            )
            normalized.append(item)
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "componentId": component_id,
            "validationState": "INVALID",
            "associationConfidence": None,
            "reason": str(exc),
            "candidates": [],
        }

    normalized.sort(
        key=lambda item: (-float(item["score"]), str(item["toothSegmentId"]))
    )
    top = normalized[0]
    runner_up = normalized[1] if len(normalized) > 1 else None
    margin = (
        float(top["score"]) - float(runner_up["score"])
        if runner_up
        else 1.0
    )
    raw_hint = _valid_fdi(top.get("sourceFdiHint"))
    hint_disagreement = bool(raw_hint and raw_hint != top["toothFdiNumber"])
    if not top["passesSpatialGate"]:
        state = "INVALID"
        confidence = None
        reason = "best tooth candidate failed spatial evidence gates"
    elif runner_up and runner_up["passesSpatialGate"] and margin < thresholds["minScoreMargin"]:
        state = "AMBIGUOUS"
        confidence = None
        reason = "top two tooth candidates do not have a safe score margin"
    else:
        state = "VALID"
        confidence = "MEDIUM" if hint_disagreement else (
            "HIGH" if margin >= thresholds["highScoreMargin"] else "MEDIUM"
        )
        reason = "spatial association accepted"
    return {
        "componentId": component_id,
        "validationState": state,
        "associationConfidence": confidence,
        "associationMethod": (
            "spatial-disagrees-source-hint"
            if hint_disagreement
            else "spatial+source-hint"
            if raw_hint
            else "spatial"
        ),
        "toothSegmentId": top["toothSegmentId"] if state == "VALID" else None,
        "toothFdiNumber": top["toothFdiNumber"] if state == "VALID" else None,
        "sourceFdiHint": raw_hint,
        "hintDisagreement": hint_disagreement,
        "scoreMargin": round(margin, 9),
        "selected": deepcopy(top),
        "runnerUp": deepcopy(runner_up) if runner_up else None,
        "candidates": normalized,
        "reason": reason,
    }


def associate_pulp_components(
    components: Sequence[Mapping[str, Any]],
    target_tooth_segment_id: str,
    *,
    policy: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate component decisions and reject cross-tooth grouping."""

    target_id = str(target_tooth_segment_id or "").strip()
    if not target_id:
        raise ValueError("A target tooth segment ID is required.")
    if not components:
        return {
            "validationState": "MISSING",
            "associationConfidence": None,
            "parentToothSegmentIds": [],
            "components": [],
            "reason": "no non-empty pulp components",
        }
    decisions = []
    for component in components:
        component_id = str(component.get("componentId") or "").strip()
        source_segment_id = str(component.get("sourceSegmentId") or "").strip()
        if not component_id or not source_segment_id:
            return {
                "validationState": "INVALID",
                "associationConfidence": None,
                "parentToothSegmentIds": [],
                "components": decisions,
                "reason": "pulp component identity is incomplete",
            }
        decision = rank_pulp_component(
            component_id,
            component.get("candidates") or [],
            policy=policy,
        )
        decision["sourceSegmentId"] = source_segment_id
        decisions.append(decision)
    failed = [item for item in decisions if item["validationState"] != "VALID"]
    if failed:
        state = "AMBIGUOUS" if any(
            item["validationState"] == "AMBIGUOUS" for item in failed
        ) else failed[0]["validationState"]
        return {
            "validationState": state,
            "associationConfidence": None,
            "parentToothSegmentIds": [],
            "components": decisions,
            "reason": failed[0].get("reason") or "pulp component association failed",
        }
    parent_ids = sorted({str(item["toothSegmentId"]) for item in decisions})
    if parent_ids != [target_id]:
        return {
            "validationState": "AMBIGUOUS",
            "associationConfidence": None,
            "parentToothSegmentIds": parent_ids,
            "components": decisions,
            "reason": "pulp components disagree about the target tooth",
        }
    source_ids = sorted({str(item["sourceSegmentId"]) for item in decisions})
    if len(source_ids) > 1:
        return {
            "validationState": "INVALID",
            "associationConfidence": None,
            "parentToothSegmentIds": parent_ids,
            "components": decisions,
            "reason": "multiple source pulp segments claim one canonical parent",
        }
    confidence = (
        "HIGH"
        if all(item["associationConfidence"] == "HIGH" for item in decisions)
        else "MEDIUM"
    )
    return {
        "validationState": "VALID",
        "associationConfidence": confidence,
        "parentToothSegmentIds": parent_ids,
        "components": decisions,
        "sourceSegmentIds": source_ids,
        "associationMethod": (
            "spatial-disagrees-source-hint"
            if any(item.get("hintDisagreement") for item in decisions)
            else "spatial+source-hint"
            if all(item.get("associationMethod") == "spatial+source-hint" for item in decisions)
            else "spatial"
        ),
        "reason": "all pulp components associate with the selected tooth",
    }


def apply_pulp_association(
    records: Sequence[Mapping[str, Any]],
    association: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Apply one accepted association without changing mask geometry."""

    if association.get("validationState") != "VALID":
        raise ValueError("Only a valid pulp association can be persisted.")
    components = association.get("components") or []
    source_ids = sorted(
        {
            str(component.get("sourceSegmentId") or "").strip()
            for component in components
            if str(component.get("sourceSegmentId") or "").strip()
        }
    )
    target_ids = [
        str(value).strip()
        for value in association.get("parentToothSegmentIds") or []
        if str(value).strip()
    ]
    if len(source_ids) != 1 or len(target_ids) != 1:
        raise ValueError("A persisted pulp association must have one source and one parent.")
    target_fdi = next(
        (
            str(component.get("toothFdiNumber") or "")
            for component in components
            for child in [component.get("selected") or {}]
            if str(child.get("toothSegmentId") or "") == target_ids[0]
        ),
    )
    target_fdi = _valid_fdi(target_fdi)
    if not target_fdi:
        raise ValueError("A persisted pulp association has no valid parent FDI.")
    result = [deepcopy(dict(record)) for record in records]
    changed = False
    evidence = {
        "componentIds": [str(item.get("componentId") or "") for item in components],
        "sourceSegmentIds": source_ids,
        "parentToothSegmentIds": target_ids,
        "componentDecisions": deepcopy(list(components)),
        "hintDisagreement": any(
            bool(item.get("hintDisagreement"))
            for item in components
        ),
    }
    for record in result:
        if str(record.get("segmentId") or "") != source_ids[0]:
            continue
        if str(record.get("structureType") or "") != "PULP":
            raise ValueError("Only PULP records can receive a pulp association.")
        record.update(
            {
                "canonicalName": f"Pulp_FDI{target_fdi}",
                "fdiNumber": target_fdi,
                "parentToothSegmentIds": target_ids,
                "associationMethod": association.get("associationMethod") or "spatial",
                "associationConfidence": association.get("associationConfidence"),
                "validationState": "VALID",
                "associationEvidence": evidence,
            }
        )
        changed = True
    if not changed:
        raise ValueError("The accepted pulp source segment is not in the registry.")
    return result


def pulp_record_is_planning_ready(record: Mapping[str, Any], target_id: str) -> bool:
    """Return whether one persisted pulp record may feed endpoint planning."""

    return bool(
        str(record.get("structureType") or "") == "PULP"
        and (
            (
                str(record.get("validationState") or "") == "VALID"
                and str(record.get("associationConfidence") or "") == "HIGH"
            )
            or (
                str(record.get("validationState") or "") == "MANUALLY_CONFIRMED"
                and str(record.get("associationConfidence") or "")
                in ASSOCIATION_CONFIDENCES
            )
        )
        and [str(value) for value in record.get("parentToothSegmentIds") or []]
        == [str(target_id or "").strip()]
    )
