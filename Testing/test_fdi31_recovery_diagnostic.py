"""Pure checks for the bounded FDI31 recovery diagnostic helpers."""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "fdi31_recovery_diagnostic",
    Path(__file__).with_name("run_dentobot_fdi31_recovery_diagnostic.py"),
)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)


def test_phase_guard_does_not_admit_later_campaign_phases():
    assert _MODULE.phase_guard("p1_scene_audit") == "p1_scene_audit"
    assert _MODULE.phase_guard("p2_state_contact") == "p2_state_contact"
    with pytest.raises(ValueError):
        _MODULE.phase_guard("p3_endpoint")
    with pytest.raises(ValueError):
        _MODULE.phase_guard("p4_insertion")


def test_missing_state_stays_null_and_carries_reason():
    slot = _MODULE.state_slot(
        "last_guard_accepted",
        unknown_reason="no preceding accepted sample was saved",
    )
    assert slot["available"] is False
    assert slot["joints_si"] is None
    assert slot["unknown_reason"] == "no preceding accepted sample was saved"


def test_contact_record_does_not_invent_nearest_points_or_depth():
    record = _MODULE.contact_record(
        state_id="rejected",
        native_status={
            "accepted": False,
            "first_body": "dentobot_target_tooth_2.25.127809691704402484963988182477922906518",
            "second_body": "pneumatic_spindle-Copy",
            "checked_samples": 1,
            "minimum_world_distance_m": None,
            "guide_clearance_warning": False,
            "exploratory_tool_contact_suppressed": False,
        },
    )
    assert record["contact_class"] == "FORBIDDEN_COLLISION"
    assert record["native_pair"] == [
        "dentobot_target_tooth_2.25.127809691704402484963988182477922906518",
        "pneumatic_spindle-Copy",
    ]
    assert record["native_nearest_points_base_m"] is None
    assert record["native_depth"] is None
    assert record["native_clearance_m"] is None


def test_atomic_json_write_replaces_partial_destination(tmp_path):
    destination = tmp_path / "state.json"
    destination.write_text('{"old": true}\n', encoding="utf-8")
    _MODULE.atomic_json_write(destination, {"new": True, "missing": None})
    assert destination.read_text(encoding="utf-8").endswith("\n")
    assert '"new": true' in destination.read_text(encoding="utf-8")
    assert '"missing": null' in destination.read_text(encoding="utf-8")


def test_jsonable_walks_dataclass_without_deepcopying_mrml_objects():
    class FakeMrmlNode:
        def GetID(self):
            return "vtkMRMLLinearTransformNode5"

        def GetName(self):
            return "base"

        def GetClassName(self):
            return "vtkMRMLLinearTransformNode"

    @dataclasses.dataclass
    class Status:
        node: object

    assert _MODULE._jsonable(Status(FakeMrmlNode())) == {
        "node": {
            "id": "vtkMRMLLinearTransformNode5",
            "name": "base",
            "class": "vtkMRMLLinearTransformNode",
        }
    }


def test_transition_evidence_does_not_relabel_first_sample_as_target_static():
    target = {"j1": 0.2, "j2": 0.01}
    record = _MODULE.phase_transition_record(
        transition_id="home-to-target",
        start_positions_si={"j1": 0.0, "j2": 0.0},
        requested_positions_si=target,
        phase="drilling",
        sequence=1,
        validate_only=True,
        native_status={
            "accepted": False,
            "validate_only": True,
            "reason": "corridor violation",
            "requested_positions": [0.2, 0.01],
            "accepted_positions": [0.0, 0.0],
            "checked_samples": 1,
            "corridor_ok": False,
        },
        joint_order=("j1", "j2"),
    )
    assert record["starting_state"]["joints_si"] == {"j1": 0.0, "j2": 0.0}
    assert record["requested_state"]["joints_si"] == target
    assert record["result"]["attribution"].startswith("transition only")
    assert record["evaluated_or_rejected_sample"]["sample_index"] == 1
    assert record["evaluated_or_rejected_sample"]["joints_si"] is None
    assert record["evaluated_or_rejected_sample"]["interpolation_fraction"] is None


def test_scene_acknowledgement_requires_exact_pose_policy_and_request_correlation():
    expected = [
        {
            "outgoing_collision_object_id": "target",
            "outgoing_pose_base_link_m_xyzw": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            "outgoing_bounds_base_link_mm": [0.0, 10.0, 0.0, 10.0, 0.0, 10.0],
        }
    ]
    observed = [
        {
            "id": "target",
            "pose_base_link_m_xyzw": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            "bounds_base_link_m": [0.0, 0.01, 0.0, 0.01, 0.0, 0.01],
            "shape_count": 1,
        }
    ]
    trusted = _MODULE.collision_scene_acknowledgement_evidence(
        expected,
        observed,
        expected_policy_fingerprint="policy",
        observed_policy_fingerprint="policy",
        readback_correlated=True,
        reported_status="Acknowledged",
    )
    assert trusted["trusted"]
    untrusted = _MODULE.collision_scene_acknowledgement_evidence(
        expected,
        observed,
        expected_policy_fingerprint="policy",
        observed_policy_fingerprint="",
        readback_correlated=False,
        reported_status="Acknowledged",
    )
    assert not untrusted["trusted"]
    assert any("policy" in item for item in untrusted["mismatches"])
    assert any("correlated" in item for item in untrusted["mismatches"])


def test_display_fk_comparison_rejects_marker_only_or_misaligned_geometry():
    identity = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    displayed = {"tcp": identity, "spindle": identity}
    native = {"tcp": identity, "spindle": identity}
    assert _MODULE.compare_display_fk_transforms(displayed, native)["match"]
    shifted = [list(row) for row in identity]
    shifted[0][3] = 1.0
    mismatch = _MODULE.compare_display_fk_transforms(
        {"tcp": identity, "spindle": shifted}, native
    )
    assert mismatch["comparisons"]["spindle"]["match"] is False
    missing = _MODULE.compare_display_fk_transforms({"spindle": identity}, native)
    assert missing["comparisons"]["tcp"]["available"] is False
    assert missing["marker_only_rejected"]


def test_display_robot_uses_live_goal_handle_and_known_link_names():
    class FakeBridge:
        ROS2_ROBOT_NAME = "dentobot"

        @staticmethod
        def find_ros2_robot_by_name(name):
            assert name == "dentobot"
            return "live-robot"

    assert _MODULE._refresh_goal_robot(FakeBridge(), "stale-robot") == "live-robot"
    assert _MODULE._goal_display_node_kind("pneumatic-spindle-copy_model_0_goal") == "spindle"
    assert _MODULE._goal_display_node_kind("burr_model_0_goal") == "burr"
    assert _MODULE._goal_display_node_kind("burr_goal_transform") == "burr"
    assert _MODULE._goal_display_node_kind("dentobot_drill_tcp") == "tcp"


def test_phase_aware_static_interface_is_read_only_and_implemented_in_existing_topics():
    proposal = _MODULE.phase_aware_static_interface_proposal()
    assert proposal["required"]
    assert proposal["available_in_current_sources"]
    assert proposal["status"] == "implemented_in_existing_task_guard_contract"
    assert proposal["guard_policy_change"] is False
    assert proposal["request_addition"]["validation_kind"] == "static_state"
    assert proposal["response_addition"]["interpolation"]["sample_count"] == 1
    assert proposal["transition_telemetry_addition"]["response"]["evaluated_positions"]


def test_transition_telemetry_uses_native_sample_when_present():
    record = _MODULE.phase_transition_record(
        transition_id="home-to-target",
        start_positions_si={"j1": 0.0, "j2": 0.0},
        requested_positions_si={"j1": 0.2, "j2": 0.01},
        phase="drilling",
        sequence=3,
        validate_only=True,
        native_status={
            "accepted": False,
            "request_id": "transition-1",
            "validation_kind": "transition",
            "requested_positions": [0.2, 0.01],
            "starting_positions": [0.0, 0.0],
            "evaluated_positions": [0.01, 0.001],
            "evaluated_sample_index": 1,
            "interpolation_fraction": 0.25,
            "first_rejection_interpolation_fraction": 0.25,
            "total_sample_count": 4,
            "checked_samples": 1,
        },
        joint_order=("j1", "j2"),
    )
    assert record["request_id"] == "transition-1"
    assert record["evaluated_or_rejected_sample"]["joints_si"] == [0.01, 0.001]
    assert record["evaluated_or_rejected_sample"]["sample_index"] == 1
    assert record["evaluated_or_rejected_sample"]["interpolation_fraction"] == 0.25
    assert record["interpolation"]["total_sample_count"] == 4
