"""Print the retained case's pre-bind base-lineage comparison without saving."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import extract_scene_mrb, validate_case_bundle  # noqa: E402


PACKAGE = Path(
    os.environ.get(
        "DENTOBOT_BASE_DIAGNOSTIC_PACKAGE",
        "/workspace/data/Slicer_Saved/SampleStudy1/"
        "dentobot-case-13sept.dentocase",
    )
)


def run() -> int:
    inspection = validate_case_bundle(PACKAGE)
    scene_path, _inspection = extract_scene_mrb(
        PACKAGE,
        Path(tempfile.mkdtemp(prefix="dentobot-base-lineage-")) / "incoming",
    )
    if not slicer.util.loadScene(str(scene_path), {"clear": True}):
        raise RuntimeError("Slicer could not load the extracted case MRB")
    slicer.util.selectModule("DENTOWorkflow")
    slicer.app.processEvents()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    if widget is None or widget.logic is None:
        raise RuntimeError("DENTOWorkflow widget did not initialize")
    logic = widget.logic
    parameter = logic.getParameterNode()
    actual = logic.caseBundleWorkflowSummary(parameter)
    expected_step6 = inspection.workflow["step6"]
    expected_base = expected_step6["basePlacement"]
    expected_environment = expected_step6["environment"]
    actual_base = actual["step6"]["basePlacement"]
    actual_environment = actual["step6"]["environment"]
    payload = {
        "expectedBase": expected_base,
        "actualBase": actual_base,
        "parameter": {
            "status": str(parameter.step6BasePlacementStatus),
            "source": str(parameter.step6BasePlacementSource),
            "revision": int(parameter.step6BasePlacementRevision),
            "locked": bool(parameter.robotBaseMountLocked),
            "authority": str(
                parameter.robotBaseTransform.GetAttribute(
                    logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
                )
                or ""
            ),
        },
        "expectedEnvironmentBase": {
            key: expected_environment.get(key)
            for key in (
                "base_matrix",
                "base_fingerprint",
                "base_authority",
                "base_revision",
                "base_status",
                "base_locked",
            )
        },
        "actualEnvironmentBase": {
            key: actual_environment.get(key)
            for key in (
                "base_matrix",
                "base_fingerprint",
                "base_authority",
                "base_revision",
                "base_status",
                "base_locked",
            )
        },
        "revisionDriftPredicate": logic._caseBundleUnlockedBaseRevisionDrift(
            parameter,
            expected_step6,
        ),
    }
    print("DENTOBOT_BASE_LINEAGE_DIAGNOSTIC " + json.dumps(payload, sort_keys=True))
    return 0


try:
    exit_code = run()
except Exception as exc:
    print(
        "DENTOBOT_BASE_LINEAGE_DIAGNOSTIC_FAIL "
        + json.dumps({"error_type": type(exc).__name__, "error": str(exc)}),
        file=sys.stderr,
    )
    exit_code = 1
slicer.util.exit(exit_code)
