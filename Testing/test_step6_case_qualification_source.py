"""Host-only source checks for the fresh-process Step 6 case qualifier."""

import ast
from pathlib import Path


RUNNER = Path(__file__).with_name("run_dentobot_step6_case_qualification.py")


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
