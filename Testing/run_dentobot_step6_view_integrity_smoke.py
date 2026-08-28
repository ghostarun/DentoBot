"""Stress the real Step 6 Views tree against restored/opened case anatomy."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

import qt
import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOROS2Bridge import shutdown_slicer_adapter  # noqa: E402


PACKAGE = Path(
    "/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-step6x1.dentocase"
)


def process_events(seconds: float = 0.2) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def segment_ids(segmentation_node) -> list[str]:
    ids = []
    segmentation = segmentation_node.GetSegmentation()
    for index in range(segmentation.GetNumberOfSegments()):
        ids.append(segmentation.GetNthSegmentID(index))
    return ids


def find_tree_item(tree, wanted_key: str):
    stack = [
        tree.topLevelItem(index)
        for index in range(tree.topLevelItemCount)
    ]
    while stack:
        item = stack.pop()
        if str(item.data(0, qt.Qt.UserRole) or "") == wanted_key:
            return item
        stack.extend(item.child(index) for index in range(item.childCount()))
    return None


def tree_keys(tree) -> list[str]:
    keys = []
    stack = [
        tree.topLevelItem(index)
        for index in range(tree.topLevelItemCount)
    ]
    while stack:
        item = stack.pop()
        key = str(item.data(0, qt.Qt.UserRole) or "")
        if key:
            keys.append(key)
        stack.extend(item.child(index) for index in range(item.childCount()))
    return keys


def set_tree_entry(widget, key: str, visible: bool) -> None:
    widget._updateWorkflowViewControls()
    process_events(0.05)
    item = find_tree_item(widget._workflowAdvancedTree, key)
    require(
        item is not None,
        f"missing advanced Views item: {key}; present={tree_keys(widget._workflowAdvancedTree)[:20]}",
    )
    item.setCheckState(0, qt.Qt.Checked if visible else qt.Qt.Unchecked)
    process_events(0.12)


def run() -> None:
    require(PACKAGE.is_file(), f"missing package: {PACKAGE}")
    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._applyDENTOBOTGuiMode("legacy", persist=False)
    widget._setWorkflowStage(10, ensureVisible=False)
    widget._openCaseBundle(PACKAGE)
    process_events(0.8)
    widget._setWorkflowStage(10, ensureVisible=False)
    process_events(0.2)

    parameter_node = widget._parameterNode
    require(
        parameter_node.step6CaseJawPreparationMode == "ClosedSource",
        "step6x1 did not restore its closed source anatomy",
    )
    landmarks = parameter_node.step6CaseJawLandmarks
    require(
        landmarks is not None and landmarks.GetNumberOfDefinedControlPoints() == 4,
        "step6x1 did not restore its four operator landmarks",
    )
    original_confirm = slicer.util.confirmYesNoDisplay
    slicer.util.confirmYesNoDisplay = lambda *args, **kwargs: True
    try:
        widget.onCreateStep6CaseJawLandmarks()
    finally:
        slicer.util.confirmYesNoDisplay = original_confirm
    process_events(0.4)
    require(
        not widget.logic.step6CaseJawSurfaceEvidenceIssues(parameter_node),
        "restored landmark review failed",
    )
    widget.onApplyStep6CaseJawOpening()
    process_events(0.7)
    require(
        not widget.logic.step6CaseJawOpeningFreshnessIssues(parameter_node),
        "opened case anatomy is stale",
    )

    derived_nodes = [
        parameter_node.step6FixedUpperAnatomy,
        parameter_node.step6MovingLowerAnatomy,
    ]
    require(all(derived_nodes), "opened upper/lower case anatomy is missing")
    derived_displays = [node.GetDisplayNode() for node in derived_nodes]
    require(all(derived_displays), "opened case anatomy display is missing")
    derived_ids = [segment_ids(node) for node in derived_nodes]
    require(
        all(len(ids) > 1 for ids in derived_ids),
        "opened anatomy does not contain jaw plus teeth",
    )

    widget.onOpenViewControlsPalette()
    widget._applyStep6RecommendedView()
    process_events(0.4)

    # The clean Step 6 view must show both derived jaw/tooth groups, not only
    # pulp/root-canal masks from the source node.
    for display, ids in zip(derived_displays, derived_ids):
        require(display.GetVisibility3D(), "derived jaw display is hidden")
        require(
            all(display.GetSegmentVisibility3D(segment_id) for segment_id in ids),
            "recommended Step 6 view hid derived jaw/tooth segments",
        )
    source = parameter_node.teethSegmentation
    source_display = source.GetDisplayNode()
    require(source_display is not None, "source segmentation display is missing")
    source_ids = segment_ids(source)
    source_internal_was_visible = any(
        source_display.GetSegmentVisibility3D(segment_id)
        for segment_id in source_ids
    )

    # Use the real QTreeWidget itemChanged signal path repeatedly. Reacquiring
    # each item after every event-loop turn catches unsafe synchronous rebuilds.
    derived_keys = (
        "node:step6FixedUpperAnatomy",
        "node:step6MovingLowerAnatomy",
    )
    for _cycle in range(12):
        for key, display, ids in zip(derived_keys, derived_displays, derived_ids):
            set_tree_entry(widget, key, False)
            require(not display.GetVisibility(), "tree could not hide derived anatomy")
            set_tree_entry(widget, key, True)
            require(display.GetVisibility(), "tree could not show derived anatomy")
            require(
                all(display.GetSegmentVisibility3D(segment_id) for segment_id in ids),
                "showing derived anatomy did not restore every jaw/tooth segment",
            )

    # An explicit source-mask choice is allowed as custom presentation and can
    # be reversed without losing the fallback object or crashing the tree.
    source_group_key = next(
        (
            key
            for key, entry in widget._workflowViewEntriesByKey.items()
            if entry.get("segmentationNode") is source
            and entry.get("anatomyGroup") in {"upper_pulp", "lower_pulp"}
        ),
        "",
    )
    require(source_group_key, "source pulp/root-canal group is missing")
    set_tree_entry(widget, source_group_key, True)
    set_tree_entry(widget, source_group_key, False)

    widget._applyStep6RecommendedView()
    process_events(0.3)
    for display, ids in zip(derived_displays, derived_ids):
        require(
            all(display.GetSegmentVisibility3D(segment_id) for segment_id in ids),
            "recommended view did not recover derived anatomy after custom edits",
        )
    require(
        not any(source_display.GetSegmentVisibility3D(segment_id) for segment_id in source_ids),
        "recommended view did not clear source internal anatomy after custom edits",
    )
    require(
        not source_internal_was_visible,
        "initial recommended opened-case view retained source internal anatomy",
    )
    widget.onFrameWorkflowView()
    process_events(0.2)

    print(
        "DENTOBOT_STEP6_VIEW_INTEGRITY_PASS",
        sum(len(ids) for ids in derived_ids),
        len(source_ids),
        flush=True,
    )
    shutdown_slicer_adapter()
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    message = " ".join(str(exc).split())[:700]
    os.write(
        2,
        (
            "DENTOBOT_STEP6_VIEW_INTEGRITY_FAILED: "
            f"{type(exc).__name__}: {message}\n"
        ).encode("utf-8", errors="replace"),
    )
    process_events(0.25)
    shutdown_slicer_adapter()
    slicer.util.exit(1)
