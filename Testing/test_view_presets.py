"""Pure contracts for stage recommendations and dental-mask grouping."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOViewPresets import (  # noqa: E402
    ANATOMY_SCOPE_LABELS,
    CBCT_MODE_LABELS,
    RECOMMENDED_VIEW_COMPOSITIONS,
    STAGE_RECOMMENDED_CATEGORIES,
    STAGE_RECOMMENDATION_DESCRIPTIONS,
    ViewComposition,
    anatomy_scopes_for_group,
    dental_jaw_from_fdi,
    detailed_anatomy_group,
    group_segmentation_records,
    group_segmentation_records_detailed,
    recommended_view_categories,
    recommended_view_composition,
    recommended_view_description,
)


def test_every_legacy_stage_has_an_explicit_recommended_view():
    assert set(STAGE_RECOMMENDED_CATEGORIES) == set(range(11))
    assert set(STAGE_RECOMMENDATION_DESCRIPTIONS) == set(range(11))
    assert all(recommended_view_categories(stage) for stage in range(11))
    assert all(recommended_view_description(stage) for stage in range(11))
    assert "case_volume_3d" not in {
        category
        for stage in range(11)
        for category in recommended_view_categories(stage)
    }
    assert set(RECOMMENDED_VIEW_COMPOSITIONS) == set(range(11))
    assert all(
        isinstance(recommended_view_composition(stage), ViewComposition)
        for stage in range(11)
    )
    assert all(
        composition.cbct_mode not in {"intensity_3d", "both"}
        for composition in RECOMMENDED_VIEW_COMPOSITIONS.values()
    )


def test_permanent_fdi_numbers_map_to_upper_and_lower_jaws():
    assert dental_jaw_from_fdi("11") == "upper"
    assert dental_jaw_from_fdi(28) == "upper"
    assert dental_jaw_from_fdi("31") == "lower"
    assert dental_jaw_from_fdi(48) == "lower"
    assert dental_jaw_from_fdi("114") is None
    assert dental_jaw_from_fdi("not-fdi") is None


def test_segmentation_records_form_operator_facing_anatomy_groups():
    grouped = group_segmentation_records(
        [
            {"segmentId": "u11", "category": "Teeth", "fdiNumber": "11"},
            {"segmentId": "l36", "category": "Teeth", "fdiNumber": "36"},
            {
                "segmentId": "p11",
                "category": "Pulp and root canals",
                "fdiNumber": "11",
            },
            {"segmentId": "jaw", "category": "Jaws", "fdiNumber": None},
            {"segmentId": "misc", "category": "Unexpected", "fdiNumber": None},
        ]
    )
    assert grouped["upper_teeth"] == ["u11"]
    assert grouped["lower_teeth"] == ["l36"]
    assert grouped["pulp_root_canals"] == ["p11"]
    assert grouped["jaws"] == ["jaw"]
    assert grouped["other_mask"] == ["misc"]


def test_view_composition_round_trip_and_validation():
    composition = ViewComposition(
        anatomy_scope="upper_jaw_anatomy",
        anatomy_dimension="3d",
        cbct_mode="slices",
        overlay_groups=frozenset({"docks", "robot"}),
        anatomy_opacity=0.35,
    )
    assert ViewComposition.from_dict(composition.to_dict()) == composition
    assert set(ANATOMY_SCOPE_LABELS) >= {
        "target_tooth",
        "upper_jaw_anatomy",
        "lower_jaw_anatomy",
        "full_anatomy",
    }
    assert "intensity_3d" in CBCT_MODE_LABELS
    try:
        ViewComposition(anatomy_scope="not-real")
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown anatomy scope was accepted")


def test_detailed_anatomy_classifier_uses_metadata_not_geometry():
    records = [
        {
            "segmentId": "u11",
            "sourceName": "upper_central_incisor_fdi11",
            "category": "Teeth",
            "fdiNumber": "11",
        },
        {
            "segmentId": "l36p",
            "sourceName": "lower_molar_pulp_fdi136",
            "category": "Pulp and root canals",
            "fdiNumber": "36",
        },
        {
            "segmentId": "maxilla",
            "sourceName": "upper_jawbone",
            "category": "Jaws",
            "fdiNumber": None,
        },
        {
            "segmentId": "mandible",
            "sourceName": "mandible",
            "category": "Jaws",
            "fdiNumber": None,
        },
        {
            "segmentId": "pharynx",
            "sourceName": "pharynx",
            "category": "Sinuses and airway",
            "fdiNumber": None,
        },
    ]
    grouped = group_segmentation_records_detailed(records)
    assert grouped["upper_teeth"] == ["u11"]
    assert grouped["lower_pulp"] == ["l36p"]
    assert grouped["upper_jawbone"] == ["maxilla"]
    assert grouped["lower_jawbone"] == ["mandible"]
    assert grouped["neutral_airway"] == ["pharynx"]
    assert detailed_anatomy_group(records[-1]) == "neutral_airway"
    assert "upper_jaw_anatomy" in anatomy_scopes_for_group("upper_jawbone")
    assert "lower_jaw_anatomy" in anatomy_scopes_for_group("lower_pulp")
    assert "full_anatomy" in anatomy_scopes_for_group("neutral_airway")
    assert "upper_jaw_anatomy" not in anatomy_scopes_for_group(
        "neutral_airway"
    )


def test_elements_inventory_does_not_create_volume_rendering_nodes():
    source = (ROOT / "DENTOWorkflow" / "DENTOWorkflow.py").read_text(
        encoding="utf-8"
    )
    inventory = source.split("def _workflowViewEntries", 1)[1].split(
        "def _step6WorkflowViewEntries", 1
    )[0]
    assert "GetFirstVolumeRenderingDisplayNode" in inventory
    assert "CreateDefaultVolumeRenderingNodes" not in inventory
    assert "Volume rendering — not a mask" in inventory
    assert "and node is self._parameterNode.inputVolume" in inventory
    assert 'else "scene_volume"' in inventory


def test_view_preset_helper_is_part_of_the_installed_slicer_module():
    cmake = (ROOT / "DENTOWorkflow" / "CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    assert "Resources/Python/DENTOViewPresets.py" in cmake


def test_view_preset_helper_is_packaged_with_the_scripted_module():
    cmake = (ROOT / "DENTOWorkflow" / "CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    assert "Resources/Python/DENTOViewPresets.py" in cmake
