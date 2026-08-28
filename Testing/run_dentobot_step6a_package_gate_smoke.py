"""Exercise Step 6A import and placement-only fallback gates on the retained case."""

from __future__ import annotations

from pathlib import Path
import os
import sys
import time

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOROS2Bridge import shutdown_slicer_adapter  # noqa: E402


PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-step6.dentocase"
)


def process_events(seconds: float = 0.4) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run() -> None:
    require(PACKAGE.is_file(), f"operator package is missing: {PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._openCaseBundle(PACKAGE)
    process_events(0.75)
    parameter_node = widget._parameterNode

    require(
        not widget.logic.step6PlanningPackageFreshnessIssues(parameter_node),
        "retained package failed Steps 0–5 freshness before Step 6A import",
    )
    widget.onImportStep6PlanningContext()
    process_events(0.5)
    require(parameter_node.step6PlanningContextImported, "Step 6 import did not activate")
    require(widget._step6SceneKind() == "case", "case is not active after import")
    require(widget.ui.step6CaseJawOpeningGroupBox.enabled, "Step 6A is disabled")
    require(
        widget.ui.createStep6CaseJawLandmarksButton.enabled,
        "Step 6A first landmark action is disabled",
    )
    require(
        not widget.ui.step6MountLockGroupBox.enabled,
        "Step 6.1 was enabled before anatomy preparation",
    )
    require(
        not widget.ui.loadRobotModelButton.enabled,
        "robot loading was enabled before anatomy preparation",
    )
    require(
        not widget.ui.useStep6TargetJawFallbackButton.enabled,
        "fallback was enabled without a recorded primary failure",
    )

    # The retained case must expose enough reviewed metadata to route the four
    # source-specific landmark surfaces, even though this smoke does not invent
    # operator landmarks for the representative anatomy.
    associations = widget.logic.step6CaseJawLandmarkSegmentAssociations(
        parameter_node
    )
    require(len(associations) == 4, "Step 6A did not resolve four landmark surfaces")
    require(associations[0] == associations[1], "TMJ landmarks use different jaws")
    widget.onCreateStep6CaseJawLandmarks()
    process_events(0.25)
    landmarks = parameter_node.step6CaseJawLandmarks
    require(landmarks is not None, "Step 6A did not create its landmark node")
    require(
        landmarks.GetAttribute("DENTOBOT.PendingLandmarkIndex") == "0",
        "first source-specific landmark placement did not start",
    )
    require(
        landmarks.GetAttribute("DENTOBOT.PendingSourceSegmentID")
        == associations[0],
        "first condylar landmark is not tied to the reviewed lower jaw",
    )
    markups_display = landmarks.GetDisplayNode()
    require(
        markups_display.GetSnapMode() == markups_display.SnapModeToVisibleSurface,
        "case landmark placement did not enable visible-surface snap",
    )
    source_display = parameter_node.teethSegmentation.GetDisplayNode()
    jaw_groups = widget.logic.step6CaseJawSegmentIds(
        parameter_node.teethSegmentation
    )
    visible_ids = [
        segment_id
        for segment_id in jaw_groups["upper"] + jaw_groups["lower"]
        if source_display.GetSegmentVisibility3D(segment_id)
    ]
    require(
        visible_ids == [associations[0]],
        "placement did not isolate exactly the intended condylar source surface",
    )
    widget.onClearStep6CaseJawLandmarks()
    process_events(0.2)

    # An import smoke must not invent representative-case landmarks or claim a
    # solver failure. Missing operator surface evidence is specifically not a
    # fallback-eligible condition.
    require(
        not widget.logic.recordStep6CaseJawPreparationFailure(
            parameter_node,
            "All four landmarks must be placed with source-specific surface snapping.",
        ),
        "missing landmark evidence incorrectly authorized fallback",
    )
    widget._updateStep6CaseJawOpeningControls()
    require(
        not widget.ui.useStep6TargetJawFallbackButton.enabled,
        "fallback enabled without a completed guided-landmark attempt",
    )

    print(
        "DENTOBOT_STEP6A_PACKAGE_GATE_PASS",
        parameter_node.targetToothSegmentId,
        widget.logic.step6TargetJaw(parameter_node),
        len(widget.logic.robotModelNodes()),
        flush=True,
    )
    shutdown_slicer_adapter()
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    message = " ".join(str(exc).split())[:500]
    os.write(
        2,
        (
            "DENTOBOT_STEP6A_PACKAGE_GATE_FAILED: "
            f"{type(exc).__name__}: {message}\n"
        ).encode("utf-8", errors="replace"),
    )
    process_events(0.25)
    shutdown_slicer_adapter()
    slicer.util.exit(1)
