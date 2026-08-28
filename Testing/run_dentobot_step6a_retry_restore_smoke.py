"""Exercise restored Step 6A landmark review, retry, and package switching."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOROS2Bridge import shutdown_slicer_adapter  # noqa: E402


CASE_ROOT = Path("/workspace/data/Slicer_Saved/SampleStudy1")
REVIEW_PACKAGE = CASE_ROOT / "dentobot-case-step6x1.dentocase"
ORIGINAL_PACKAGE = CASE_ROOT / "dentobot-case-step6.dentocase"


def process_events(seconds: float = 0.4) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run() -> None:
    require(REVIEW_PACKAGE.is_file(), f"missing package: {REVIEW_PACKAGE}")
    require(ORIGINAL_PACKAGE.is_file(), f"missing package: {ORIGINAL_PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)

    # This operator package currently stores four geometrically valid points,
    # but intentionally lacks current guided-placement evidence. Loading must
    # preserve that honest state instead of silently promoting or deleting it.
    widget._openCaseBundle(REVIEW_PACKAGE)
    process_events(0.75)
    widget._setWorkflowStage(10, ensureVisible=False)
    parameter_node = widget._parameterNode
    require(
        not widget.logic.step6PlanningPackageFreshnessIssues(parameter_node),
        "step6x1 upstream package is stale",
    )
    require(parameter_node.step6PlanningContextImported, "saved import state was lost")
    require(
        parameter_node.step6CaseJawPreparationMode == "ClosedSource",
        "saved closed-jaw review state was not restored",
    )
    require(
        not widget.logic.robotModelNodes(),
        "saved step6x1 package restored transient local robot models",
    )
    landmarks = parameter_node.step6CaseJawLandmarks
    require(
        landmarks is not None and landmarks.GetNumberOfDefinedControlPoints() == 4,
        "saved four-point landmark set was not restored",
    )
    require(
        widget.logic.step6CaseJawSurfaceEvidenceIssues(parameter_node),
        "raw restored points were silently promoted to current surface evidence",
    )
    closed_lower_incisor = [0.0, 0.0, 0.0]
    landmarks.GetNthControlPointPositionWorld(3, closed_lower_incisor)
    widget._updateStep6CaseJawOpeningControls()
    require(
        not widget.ui.applyStep6CaseJawOpeningButton.enabled,
        "unreviewed restored points enabled the open-mouth solver",
    )
    require(
        widget.ui.createStep6CaseJawLandmarksButton.enabled
        and "Review / re-snap" in widget.ui.createStep6CaseJawLandmarksButton.text,
        "restored points did not expose the explicit review action: "
        f"enabled={widget.ui.createStep6CaseJawLandmarksButton.enabled}, "
        f"text={widget.ui.createStep6CaseJawLandmarksButton.text!r}, "
        f"baseLocked={parameter_node.robotBaseMountLocked}, "
        f"mode={parameter_node.step6CaseJawPreparationMode!r}",
    )

    original_confirm = slicer.util.confirmYesNoDisplay
    slicer.util.confirmYesNoDisplay = lambda *args, **kwargs: True
    try:
        widget.onCreateStep6CaseJawLandmarks()
    finally:
        slicer.util.confirmYesNoDisplay = original_confirm
    process_events(0.5)
    require(
        not widget.logic.step6CaseJawSurfaceEvidenceIssues(parameter_node),
        "explicit existing-point review did not establish current evidence",
    )
    require(
        widget.ui.applyStep6CaseJawOpeningButton.enabled,
        "explicit landmark review did not enable the open-mouth solver",
    )
    require(
        "maximum exact-projection residual" in widget.ui.step6CaseJawOpeningStatusLabel.text,
        "review result was not reported to the operator",
    )

    widget.onApplyStep6CaseJawOpening()
    process_events(0.75)
    require(
        parameter_node.step6CaseJawPreparationMode == "ProvisionalOpenProxy",
        "reviewed operator landmarks did not produce the open-jaw proxy",
    )
    transform = parameter_node.step6CaseJawTransform
    require(transform is not None, "open-jaw transform was not created")
    require(
        transform.GetAttribute("DENTOBOT.GeometryState") == "Current",
        "open-jaw transform is stale immediately after creation: "
        f"state={transform.GetAttribute('DENTOBOT.GeometryState')!r}, "
        f"issues={widget.logic.step6CaseJawOpeningFreshnessIssues(parameter_node)!r}",
    )
    require(
        "measured incisor gap 40.00 mm"
        in widget.ui.step6CaseJawOpeningStatusLabel.text,
        "operator status did not report the expected approximately 40 mm gap",
    )
    require(
        float(transform.GetAttribute("DENTOBOT.HingeAngleDeg")) < 0.0,
        "case hinge did not select the inferior signed rotation",
    )
    opened_lower_incisor = [0.0, 0.0, 0.0]
    parameter_node.step6CaseJawGapLine.GetNthControlPointPositionWorld(
        1,
        opened_lower_incisor,
    )
    require(
        opened_lower_incisor[2] < closed_lower_incisor[2],
        "opened lower incisor did not move toward patient-RAS inferior (-Z)",
    )

    # Reset is the explicit retry transition. It returns to closed source while
    # retaining the reviewed four points for adjustment/reapplication.
    widget.onResetStep6CaseJawOpening()
    process_events(0.4)
    require(
        parameter_node.step6CaseJawPreparationMode == "ClosedSource",
        "reset did not return to the closed source anatomy",
    )
    require(parameter_node.step6CaseJawTransform is None, "reset retained jaw transform")
    require(
        landmarks.GetNumberOfDefinedControlPoints() == 4,
        "ordinary reset unexpectedly deleted reviewed landmarks",
    )

    # Switching packages in the same process must not inherit reviewed jaw,
    # base, or imported-planning state from step6x1.
    widget._openCaseBundle(ORIGINAL_PACKAGE)
    process_events(0.75)
    parameter_node = widget._parameterNode
    require(
        not widget.logic.step6PlanningPackageFreshnessIssues(parameter_node),
        "original package failed upstream freshness after package switching",
    )
    require(
        not parameter_node.step6PlanningContextImported,
        "original package saved-false import state was silently promoted",
    )
    widget.onImportStep6PlanningContext()
    process_events(0.4)
    require(parameter_node.step6PlanningContextImported, "original package import failed")
    require(
        widget.ui.createStep6CaseJawLandmarksButton.enabled,
        "original package did not expose Step 6A after explicit import",
    )
    require(not widget.logic.robotModelNodes(), "package switching restored a ROS/MRML robot")

    print("DENTOBOT_STEP6A_RETRY_RESTORE_PASS", flush=True)
    shutdown_slicer_adapter()
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    message = " ".join(str(exc).split())[:700]
    os.write(
        2,
        (
            "DENTOBOT_STEP6A_RETRY_RESTORE_FAILED: "
            f"{type(exc).__name__}: {message}\n"
        ).encode("utf-8", errors="replace"),
    )
    process_events(0.25)
    shutdown_slicer_adapter()
    slicer.util.exit(1)
