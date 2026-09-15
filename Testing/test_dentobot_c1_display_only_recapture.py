"""Pure checks for the retained Campaign-1 review recapture driver."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import run_dentobot_c1_display_only_recapture as driver
from run_dentobot_c1_display_only_recapture import (
    ReviewCaptureBlocked,
    _derive_tcp_world_from_displayed_spindle,
    _ensure_case_foundation_display_volumes,
    _prepare_target_surface_for_review,
    _require_single_jaw_preparation,
    _read_world_matrix,
    _set_review_parameter_joint_state,
    _set_properties_label_visibility_if_supported,
    JOINT_ORDER,
    compare_bounds,
    compare_robot_description_identity,
    compare_transform,
    deferred_transition_report,
    load_review_state,
    native_geometry_records,
    review_capture_readiness,
)


# Testing/ -> DentoBot/ -> src/ -> ros2_ws/ -> dentobot/
ROOT = Path(__file__).resolve().parents[4]
RETAINED = ROOT / (
    "data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/"
    "c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected"
)


def _retained_json(name: str) -> dict:
    return json.loads((RETAINED / name).read_text(encoding="utf-8"))


def test_optional_slicer_label_api_is_compatibility_guarded() -> None:
    class WithMethod:
        def __init__(self) -> None:
            self.value = None

        def SetPropertiesLabelVisibility(self, value) -> None:
            self.value = value

    supported = WithMethod()
    unsupported = object()
    assert _set_properties_label_visibility_if_supported(supported) is True
    assert supported.value is True
    assert _set_properties_label_visibility_if_supported(unsupported) is False


def test_model_world_matrix_uses_parent_transform_when_model_api_is_missing() -> None:
    class FakeMatrix:
        def __init__(self) -> None:
            self.value = None

        def Identity(self) -> None:
            self.value = "identity"

    class ParentTransform:
        def GetMatrixTransformToWorld(self, matrix) -> bool:
            matrix.value = "parent-world"
            return True

    class Model:
        def __init__(self, parent) -> None:
            self.parent = parent

        def GetParentTransformNode(self):
            return self.parent

        def GetName(self) -> str:
            return "fake-model"

    matrix = FakeMatrix()
    _read_world_matrix(Model(ParentTransform()), matrix)
    assert matrix.value == "parent-world"


def test_model_world_matrix_without_parent_is_identity() -> None:
    class FakeMatrix:
        def __init__(self) -> None:
            self.value = None

        def Identity(self) -> None:
            self.value = "identity"

    class Model:
        def GetParentTransformNode(self):
            return None

        def GetName(self) -> str:
            return "fake-model"

    matrix = FakeMatrix()
    _read_world_matrix(Model(), matrix)
    assert matrix.value == "identity"


def test_saved_endpoint_and_transition_are_distinct_and_attributed() -> None:
    state = load_review_state(
        _retained_json("rejected_state.json"),
        _retained_json("state_identity.json"),
    )
    endpoint = state["endpoint"]
    transition = state["transition"]
    assert endpoint["kind"] == "static_endpoint"
    assert transition["kind"] == "transition_sample"
    assert endpoint["joints_si"] != transition["joints_si"]
    assert transition["sample_index"] == 1
    assert transition["total_sample_count"] == 134
    assert transition["starting_joints_si"]
    assert transition["requested_joints_si"] == endpoint["joints_si"]
    assert transition["native_fk_world_ras_mm"] == {}
    assert "not Target static validity" in transition["static_result_label"]


def test_transition_native_fk_is_consumed_only_when_saved() -> None:
    rejected = _retained_json("rejected_state.json")
    identity = _retained_json("state_identity.json")
    native_fk = copy.deepcopy(identity["display_evidence"]["goal_robot_fk"]["native_fk_world_ras_mm"])
    rejected["states"]["first_guard_rejected"]["transition"][
        "evaluated_or_rejected_sample"
    ]["native_fk_world_ras_mm"] = native_fk
    state = load_review_state(rejected, identity)
    assert state["transition"]["native_fk_world_ras_mm"] == native_fk
    assert state["transition"]["native_state_source"] == "saved native evaluated-sample FK matrices"


def test_endpoint_only_defers_transition_without_downgrading_state() -> None:
    transition = load_review_state(
        _retained_json("rejected_state.json"),
        _retained_json("state_identity.json"),
    )["transition"]
    deferred = deferred_transition_report(transition)
    assert deferred["status"] == "NOT_RUN"
    assert deferred["runtime_entered"] is False
    assert deferred["native_fk_available"] is False
    assert deferred["state"]["sample_index"] == 1
    assert deferred["state"]["total_sample_count"] == 134
    assert "Endpoint-only" in deferred["reason"]


def test_transform_and_bounds_comparisons_fail_closed() -> None:
    identity = [
        [1.0, 0.0, 0.0, 10.0],
        [0.0, 1.0, 0.0, 20.0],
        [0.0, 0.0, 1.0, 30.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    assert compare_transform(identity, copy.deepcopy(identity))["match"] is True
    shifted = copy.deepcopy(identity)
    shifted[0][3] += 0.26
    assert compare_transform(identity, shifted)["match"] is False
    assert compare_transform(identity, None)["match"] is None
    assert compare_bounds([0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5])["match"] is True
    assert compare_bounds([0, 1, 2, 3, 4, 5], None)["match"] is None


def test_native_geometry_records_are_indexed_by_role() -> None:
    records = native_geometry_records(_retained_json("state_identity.json"))
    assert records["selected-target-tooth"]["prepared_world_fingerprint"]
    assert records["verified-final-template"]["prepared_bounds_world_ras_mm"]


def test_target_jaw_preparation_requires_exactly_one_native_application() -> None:
    accepted = {
        "jaw_transform_application_count": 1,
        "jaw_transform_fingerprint": "retained-jaw-transform",
    }
    assert _require_single_jaw_preparation(accepted)[
        "applied_jaw_transform_application_count"
    ] == 1
    for count in (0, 2):
        rejected = dict(accepted)
        rejected["jaw_transform_application_count"] = count
        with pytest.raises(ReviewCaptureBlocked, match="exactly one"):
            _require_single_jaw_preparation(rejected)


def test_target_review_preparation_calls_frozen_jaw_once(monkeypatch) -> None:
    class PolyData:
        def GetNumberOfPoints(self):
            return 1

        def GetNumberOfPolys(self):
            return 1

    class Logic:
        def __init__(self):
            self.calls = 0

        def _step6CaseJawPolydataWorld(self, parameter, source):
            del parameter, source
            self.calls += 1
            return PolyData()

    logic = Logic()
    monkeypatch.setattr(driver, "_triangle_filter_polydata", lambda polydata: polydata)
    monkeypatch.setattr(driver, "_validate_saved_jaw_preparation_identity", lambda parameter, record: {})
    prepared, contract = _prepare_target_surface_for_review(
        logic,
        object(),
        object(),
        {
            "jaw_transform_application_count": 1,
            "jaw_transform_fingerprint": "retained-jaw-transform",
        },
    )
    assert prepared is not None
    assert logic.calls == 1
    assert contract["applied_jaw_transform_application_count"] == 1


def test_missing_case_foundation_display_volumes_use_existing_restore_helper() -> None:
    class Parameter:
        caseFoundationFixedUpperVolume = None
        caseFoundationMovingLowerVolume = None

    class Logic:
        def __init__(self):
            self.calls = 0

        def rebuildCaseFoundationDisplayVolumes(self, parameter):
            del parameter
            self.calls += 1
            return object(), object()

    logic = Logic()
    repair = _ensure_case_foundation_display_volumes(logic, Parameter())
    assert repair["restored"] is True
    assert logic.calls == 1


def test_existing_case_foundation_display_volumes_are_not_rebuilt() -> None:
    class Parameter:
        caseFoundationFixedUpperVolume = object()
        caseFoundationMovingLowerVolume = object()

    class Logic:
        def rebuildCaseFoundationDisplayVolumes(self, parameter):
            raise AssertionError("existing display volumes must be preserved")

    repair = _ensure_case_foundation_display_volumes(Logic(), Parameter())
    assert repair["restored"] is False


def test_review_parameter_joint_state_matches_existing_rehydration_units() -> None:
    class Parameter:
        def __init__(self):
            self.values = {}
            self.modify_calls = 0

        def StartModify(self):
            self.modify_calls += 1
            return "token"

        def EndModify(self, token):
            assert token == "token"

        def __setattr__(self, name, value):
            if name == "values":
                object.__setattr__(self, name, value)
                return
            if name == "modify_calls":
                object.__setattr__(self, name, value)
                return
            self.values[name] = value

    parameter = Parameter()
    joints = {
        "link-1_Revolute-1": 0.1,
        "link-2_Slider-2": 0.02,
        "link-3_Revolute-3": -0.3,
        "link-4_Slider-4": 0.04,
        "link-5_Revolute-5": 0.5,
    }
    values = _set_review_parameter_joint_state(parameter, joints)
    assert values["robotJoint1Deg"] == pytest.approx(0.1 * 180.0 / 3.141592653589793)
    assert values["robotJoint2Mm"] == pytest.approx(20.0)
    assert values["robotJoint3Deg"] == pytest.approx(-0.3 * 180.0 / 3.141592653589793)
    assert values["robotJoint4Mm"] == pytest.approx(40.0)
    assert values["robotJoint5Deg"] == pytest.approx(0.5 * 180.0 / 3.141592653589793)
    assert values["robotJoint6Deg"] == 0.0
    assert parameter.modify_calls == 1
    assert parameter.values == values


def test_review_parameter_joint_state_rejects_missing_endpoint_joint() -> None:
    with pytest.raises(ReviewCaptureBlocked, match="missing finite values"):
        _set_review_parameter_joint_state(
            object(),
            {name: 0.0 for name in JOINT_ORDER[:-1]},
        )


def test_meshless_tcp_derivation_passes_from_spindle_visual_origin() -> None:
    identity = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    spindle_mesh_from_link = copy.deepcopy(identity)
    spindle_mesh_from_link[0][3] = 2.0
    spindle_link_world = copy.deepcopy(identity)
    spindle_link_world[0][3] = 50.0
    observed_spindle_mesh = driver._matmul(spindle_link_world, spindle_mesh_from_link)
    tcp_from_base = copy.deepcopy(identity)
    tcp_from_base[0][3] = 10.0
    result = _derive_tcp_world_from_displayed_spindle(
        observed_spindle_mesh_world=observed_spindle_mesh,
        base_from_spindle_link_mm=identity,
        base_from_spindle_mesh_mm=spindle_mesh_from_link,
        base_from_tcp_mm=tcp_from_base,
    )
    expected_tcp = copy.deepcopy(identity)
    expected_tcp[0][3] = 60.0
    assert result["available"] is True
    assert result["visual_origin_accounted"] is True
    assert compare_transform(expected_tcp, result["observed_tcp_world_ras_mm"])["match"] is True


@pytest.mark.parametrize(
    "perturbation",
    [
        "spindle_mesh",
        "tcp_offset",
    ],
)
def test_meshless_tcp_derivation_rejects_perturbed_mesh_or_fixed_offset(perturbation: str) -> None:
    identity = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    mesh_from_link = copy.deepcopy(identity)
    mesh_from_link[0][3] = 2.0
    observed_link = copy.deepcopy(identity)
    observed_link[0][3] = 50.0
    observed_mesh = driver._matmul(observed_link, mesh_from_link)
    tcp_from_base = copy.deepcopy(identity)
    tcp_from_base[0][3] = 10.0
    expected_tcp = copy.deepcopy(identity)
    expected_tcp[0][3] = 60.0
    if perturbation == "spindle_mesh":
        observed_mesh[1][3] += 1.0
    else:
        tcp_from_base[0][3] += 1.0
    result = _derive_tcp_world_from_displayed_spindle(
        observed_spindle_mesh_world=observed_mesh,
        base_from_spindle_link_mm=identity,
        base_from_spindle_mesh_mm=mesh_from_link,
        base_from_tcp_mm=tcp_from_base,
    )
    assert compare_transform(expected_tcp, result["observed_tcp_world_ras_mm"])["match"] is False


def test_robot_description_identity_fails_closed() -> None:
    assert compare_robot_description_identity("abc", "abc")["match"] is True
    assert compare_robot_description_identity("abc", "def")["match"] is False
    missing = compare_robot_description_identity("abc", None)
    assert missing["available"] is False
    assert missing["match"] is False


def test_capture_readiness_requires_saved_transition_fk() -> None:
    common = {
        "geometry": {"match": True},
        "display_robot": {
            "mesh_transforms_match": True,
            "native_exposed_fk_match": True,
            "saved_pose_persistence_match": True,
            "native_evaluated_sample_fk_match": False,
        },
    }
    readiness = review_capture_readiness(
        state_kind="transition_sample",
        state={},
        **common,
    )
    assert readiness["ready"] is False
    assert readiness["checks"]["native_evaluated_sample_fk"] is False


def test_capture_readiness_separates_pre_save_from_reopen_gate() -> None:
    display_robot = {
        "mesh_transforms_match": True,
        "native_exposed_fk_match": True,
    }
    pre_save = review_capture_readiness(
        state_kind="static_endpoint",
        state={},
        geometry={"match": True},
        display_robot=display_robot,
        saved_pose_required=False,
    )
    post_reopen = review_capture_readiness(
        state_kind="static_endpoint",
        state={},
        geometry={"match": True},
        display_robot=display_robot,
    )
    assert pre_save["ready"] is True
    assert post_reopen["ready"] is False


@pytest.mark.parametrize("kind", ["static_endpoint", "transition_sample"])
def test_capture_readiness_accepts_only_complete_parity(kind: str) -> None:
    readiness = review_capture_readiness(
        state_kind=kind,
        state={},
        geometry={"match": True},
        display_robot={
            "mesh_transforms_match": True,
            "native_exposed_fk_match": True,
            "saved_pose_persistence_match": True,
            "native_evaluated_sample_fk_match": True,
        },
    )
    assert readiness["ready"] is True
