"""Verify failed post-load validation restores the prior live MRML case."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time

import slicer


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOCaseBundle import (  # noqa: E402
    CaseBundleError,
    create_case_bundle,
    extract_scene_mrb,
)


def process_events(seconds: float = 0.5) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def run() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    process_events()
    slicer.mrmlScene.Clear(0)
    process_events()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._parameterNode.caseName = "TransactionCase"
    sentinel = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLTextNode", "DENTOBOT transaction sentinel"
    )
    sentinel.SetText("state captured in incoming MRB")

    temporary_root = Path(slicer.app.temporaryPath) / "dentobot-transaction-smoke"
    temporary_root.mkdir(parents=True, exist_ok=True)
    valid_bundle = temporary_root / "valid.dentocase"
    invalid_bundle = temporary_root / "invalid-lineage.dentocase"
    inspection = widget._createCaseBundle(valid_bundle)
    with tempfile.TemporaryDirectory(
        prefix="dentobot-transaction-extract-",
        dir=slicer.app.temporaryPath,
    ) as extracted_directory:
        scene_mrb, _ = extract_scene_mrb(valid_bundle, extracted_directory)
        invalid_workflow = dict(inspection.workflow)
        invalid_workflow["caseLabel"] = "ManifestMismatch"
        create_case_bundle(
            invalid_bundle,
            scene_mrb,
            case_label="TransactionCase",
            workflow=invalid_workflow,
            robot_profile=inspection.robot_profile,
            application=inspection.manifest.get("application", {}),
        )

    sentinel.SetText("live state that must survive failed restore")
    location_before_restore = (
        slicer.mrmlScene.GetURL() or "",
        slicer.mrmlScene.GetRootDirectory() or "",
    )
    try:
        widget._openCaseBundle(invalid_bundle)
    except CaseBundleError as exc:
        if "case label" not in str(exc):
            raise
    else:
        raise RuntimeError("invalid lineage package unexpectedly loaded")
    process_events()
    restored = slicer.mrmlScene.GetFirstNodeByName("DENTOBOT transaction sentinel")
    if restored is None or restored.GetText() != "live state that must survive failed restore":
        raise RuntimeError("transaction recovery did not restore the prior MRML scene")
    if widget._parameterNode is None or widget._parameterNode.caseName != "TransactionCase":
        raise RuntimeError("transaction recovery did not restore workflow parameters")
    location_after_restore = (
        slicer.mrmlScene.GetURL() or "",
        slicer.mrmlScene.GetRootDirectory() or "",
    )
    if location_after_restore != location_before_restore:
        raise RuntimeError("transaction recovery did not restore the prior scene location")
    if slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        raise RuntimeError("transaction recovery restored a ROS robot")
    if widget._caseBundleRestoreDepth != 0:
        raise RuntimeError("transaction recovery left the restore barrier active")

    valid_bundle.unlink(missing_ok=True)
    invalid_bundle.unlink(missing_ok=True)
    temporary_root.rmdir()
    print("DENTOBOT_CASE_BUNDLE_TRANSACTION_PASS", flush=True)
    slicer.mrmlScene.Clear(0)
    process_events()
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    print(
        f"DENTOBOT_CASE_BUNDLE_TRANSACTION_FAILED: {exc}",
        file=sys.stderr,
        flush=True,
    )
    slicer.util.exit(1)
