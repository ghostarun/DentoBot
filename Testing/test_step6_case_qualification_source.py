"""Host-only source checks for the fresh-process Step 6 case qualifier."""

import ast
import sys
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


RUNNER = Path(__file__).with_name("run_dentobot_step6_case_qualification.py")
CASE_BACKEND = (
    Path(__file__).parents[1]
    / "DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py"
)
HELPERS = CASE_BACKEND.parents[1]
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOStep6State import build_manual_simulation_record, parse_manual_simulation_record  # noqa: E402


def test_case_qualification_source_contract():
    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(RUNNER))
    compile(tree, str(RUNNER), "exec")

    for required in (
        "DENTOBOT_HEADED_CASE_SOURCE",
        "DENTOBOT_HEADED_CASE_SHA256",
        "DENTOBOT_HEADED_EVIDENCE_DIR",
        "DENTOBOT_HEADED_HOST_CHECKOUT_ROOT",
        "DENTOBOT_HEADED_GIT_BRANCH",
        "DENTOBOT_HEADED_GIT_HEAD",
        "DENTOBOT_HEADED_GIT_STATUS_SHA256",
        "feature/step6-workflow-renovation-20260925",
        "sept28_fdi11_step6_five_dof_acceptance.dentocase",
        "EXPECTED_JOINTS = tuple(JOINT_NAMES)",
        "JOINT_LABELS = (\"J1\", \"J2\", \"J3\", \"J4\", \"J5\")",
        "widget._openCaseBundle",
        "validate_case_bundle(case_path)",
        "historical_display_only",
        "source_case_unchanged",
        "step6-case-qualification-",
        "vtkWindowToImageFilter",
    ):
        assert required in source

    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called_attributes.intersection(
        {
            "connect",
            "connectROS2",
            "connectRos2",
            "requestJog",
            "jog",
            "planStep6Task",
            "requestPlan",
            "preview",
            "saveCaseBundle",
            "_saveCaseBundle",
        }
    )


def test_case_bundle_manual_records_save_and_reopen_wiring():
    source = CASE_BACKEND.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CASE_BACKEND))
    compile(tree, str(CASE_BACKEND), "exec")
    backend = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "CaseBackendWidgetMixin"
    )
    method_nodes = {
        node.name: node
        for node in backend.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    namespace = {
        "CaseBundleError": type("CaseBundleError", (RuntimeError,), {}),
        "Mapping": Mapping,
        "_": lambda message: message,
        "parse_manual_simulation_record": parse_manual_simulation_record,
    }
    for name in (
        "_caseManualSimulationRecords",
        "_showCaseManualSimulationRecords",
    ):
        method = method_nodes[name]
        exec(
            compile(
                ast.Module(body=[method], type_ignores=[]),
                str(CASE_BACKEND),
                "exec",
            ),
            namespace,
        )
    collect = namespace["_caseManualSimulationRecords"]
    show_records = namespace["_showCaseManualSimulationRecords"]

    def record(label):
        return build_manual_simulation_record(
            identity={
                name: f"{label}-{name}"
                for name in "prepared_branch_id task_fingerprint base_fingerprint home_fingerprint trajectory_fingerprint robot_profile_fingerprint scene_fingerprint".split()
            },
            events=[
                {"kind": "requested", "monotonic_ns": 0, "tcp_point_ras_mm": [0, 0, 0]}
            ],
        )

    def facade(completed, active):
        return SimpleNamespace(
            manualSimulationCompletedRecords=Mock(return_value=completed),
            manualSimulationRecord=(
                Mock(side_effect=active)
                if isinstance(active, BaseException)
                else Mock(return_value=active)
            ),
        )

    no_record = RuntimeError(
        "Manual simulation recording is unavailable: no event-bearing "
        "complete identity or completed record is available."
    )
    assert collect(SimpleNamespace(_robotWorkflowFacade=facade((), no_record))) == ()

    saved = record("saved")
    assert len(collect(SimpleNamespace(_robotWorkflowFacade=facade((saved,), saved)))) == 1

    for bad_facade in (
        facade(({"malformed": True},), no_record),
        facade((), {"malformed": True}),
    ):
        with pytest.raises(namespace["CaseBundleError"]):
            collect(SimpleNamespace(_robotWorkflowFacade=bad_facade))

    errors = []

    def fail_path_cleanup():
        raise RuntimeError("cleanup failed")

    namespace["clear_manual_simulation_record_paths"] = fail_path_cleanup
    namespace["slicer"] = SimpleNamespace(util=SimpleNamespace(errorDisplay=errors.append))
    panel = Mock(selected="old historical record", displayed=[])
    panel.clearManualSimulationRecords.side_effect = lambda: setattr(panel, "selected", None)
    panel.setManualSimulationRecords.side_effect = lambda records: panel.displayed.extend(records)
    show_records(
        SimpleNamespace(_robotSimulationPanel=panel),
        SimpleNamespace(manual_simulation_records=(saved,)),
    )
    assert panel.selected is None
    assert panel.displayed == []
    assert errors and "could not be cleared" in errors[0]

    create = ast.get_source_segment(source, method_nodes["_createCaseBundle"])
    assert create.index("self._caseManualSimulationRecords()") < create.index(
        "create_case_bundle("
    )
    assert "manual_simulation_records=manualSimulationRecords" in create

    open_case = ast.get_source_segment(source, method_nodes["onOpenCaseBundle"])
    assert open_case.index("if inspection is None:") < open_case.index(
        "self._showCaseManualSimulationRecords(inspection)"
    )
