"""Offline, display-only recapture of the retained FDI21 first-invalid pose."""

import hashlib
import json
import os
from pathlib import Path
import sys
import time

import qt
import slicer
import vtk

ROOT = Path("/workspace/ros2_ws/src/DentoBot")
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))
from DENTOCaseBundle import validate_case_bundle  # noqa: E402

SOURCE = Path(os.environ["DENTOBOT_CASE_SOURCE"])
CHECKPOINT = Path(os.environ["DENTOBOT_CHECKPOINT"])
OUTPUT = Path(os.environ["DENTOBOT_EVIDENCE_DIR"])
EXPECTED_SHA = os.environ["DENTOBOT_CASE_SHA256"]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def events():
    slicer.app.processEvents()
    time.sleep(0.2)
    slicer.app.processEvents()


def run():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    require(hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED_SHA,
            "source case checksum changed")
    validate_case_bundle(SOURCE)
    checkpoint = json.loads(CHECKPOINT.read_text())
    require(checkpoint["identity"]["branch_id"] == "guide-fe8080de25e7eb57622d",
            "retained FDI21 branch changed")
    attempt = checkpoint["attempts"][0]
    require(attempt["planner_id"] == "RRTConnectkConfigDefault"
            and attempt["status"] == "Fail", "retained trial changed")
    session = attempt["session"]
    selected = session["selected_candidate_index"]
    record = next((item for item in session["candidate_records"]
                   if item.get("candidate_index") == selected), None)
    require(record and record.get("first_invalid_joint_positions_si"),
            "selected first-invalid joints unavailable")
    pair = [record.get("guard_first_body"), record.get("guard_second_body")]
    require(pair[0] and pair[1] == "pneumatic_spindle-Copy"
            and "target_tooth" in pair[0], "retained collision pair changed")

    slicer.util.selectModule("DENTOWorkflow")
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    widget._openCaseBundle(str(SOURCE))
    events()
    parameter = widget._parameterNode
    logic = widget.logic
    require(logic.robotBaseFingerprint(parameter) == checkpoint["identity"]["base"],
            "saved base differs from retained diagnostic")
    require(str(parameter.targetToothSegmentId or ""), "saved target segment missing")
    require(not widget._robotWorkflowFacade.capabilities().connected,
            "offline recapture unexpectedly connected ROS")

    joints = record["first_invalid_joint_positions_si"]
    base, robot_models = logic.createOrUpdateRobotPlacement(parameter.robotBaseTransform, joints)
    require(base is parameter.robotBaseTransform and logic.updateRobotJointPoses(joints) == 7,
            "offline FK did not reconstruct seven robot links")
    spindle = next((node for node in robot_models
                    if node.GetAttribute("DENTOBOT.RobotLinkName") == "pneumatic_spindle-Copy"), None)
    require(spindle is not None, "local spindle model unavailable")
    target_source = logic._segmentationSegmentsSurfaceWorld(
        parameter.teethSegmentation, {parameter.targetToothSegmentId})
    require(target_source is not None and target_source.GetNumberOfPoints(),
            "saved target surface unavailable")
    target_poly = logic._step6CaseJawPolydataWorld(parameter, target_source)
    require(target_poly is not None and target_poly.GetNumberOfPoints(),
            "opened-jaw target reconstruction unavailable")
    target = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "[Review] FDI21 target tooth")
    target.SetAndObservePolyData(target_poly)
    target.CreateDefaultDisplayNodes()
    target.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyCollisionReview")
    target.GetDisplayNode().SetColor(0.95, 0.18, 0.12)
    target.GetDisplayNode().SetOpacity(0.55)
    target.GetDisplayNode().SetEdgeVisibility(True)
    spindle.GetDisplayNode().SetColor(0.1, 0.75, 0.95)
    spindle.GetDisplayNode().SetOpacity(0.65)
    spindle.GetDisplayNode().SetEdgeVisibility(True)
    visible = {target.GetID(), spindle.GetID()}
    for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
        display = node.GetDisplayNode()
        if display is not None:
            display.SetVisibility(node.GetID() in visible)

    layout = slicer.app.layoutManager()
    layout.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
    events()
    view = layout.threeDWidget(0).threeDView()
    view.mrmlViewNode().SetAxisLabelsVisible(False)
    target_bounds = [0.0] * 6
    spindle_bounds = [0.0] * 6
    target.GetRASBounds(target_bounds)
    spindle.GetRASBounds(spindle_bounds)
    require(all(target_bounds[2*i] <= spindle_bounds[2*i+1]
                and spindle_bounds[2*i] <= target_bounds[2*i+1]
                for i in range(3)),
            "native/display mismatch: reconstructed tooth and spindle bounds do not overlap; "
            f"tooth={target_bounds}, spindle={spindle_bounds}")
    bounds = [value for axis in range(3)
              for value in (min(target_bounds[2*axis], spindle_bounds[2*axis]),
                            max(target_bounds[2*axis+1], spindle_bounds[2*axis+1]))]
    center = [(bounds[2*i] + bounds[2*i+1]) / 2 for i in range(3)]
    span = max(bounds[1]-bounds[0], bounds[3]-bounds[2], bounds[5]-bounds[4], 5.0)
    camera = view.cameraNode().GetCamera()
    images = []
    for name, direction, up in (
        ("inferior", (0, 0, -1), (0, 1, 0)),
        ("apical", (0, 0, 1), (0, 1, 0)),
        ("oblique", (0, 0.75, -0.66), (0, 0.66, 0.75)),
    ):
        camera.SetFocalPoint(*center)
        camera.SetPosition(*(center[i] + 1.7*span*direction[i] for i in range(3)))
        camera.SetViewUp(*up)
        camera.SetParallelProjection(True)
        camera.SetParallelScale(0.65*span)
        view.renderWindow().GetRenderers().GetFirstRenderer().ResetCameraClippingRange()
        view.forceRender()
        events()
        image = OUTPUT / f"FDI21-first-invalid-{name}.png"
        require(view.grab().save(str(image)) and image.stat().st_size > 1024,
                f"empty screenshot: {image}")
        images.append(str(image))
    manifest = {
        "scope": "offline display-only reconstruction; not native collision-depth proof",
        "source_sha256": EXPECTED_SHA,
        "checkpoint_sha256": hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest(),
        "base_fingerprint": checkpoint["identity"]["base"],
        "selected_candidate_index": selected,
        "collision_pair": pair,
        "first_invalid_joint_positions_si": joints,
        "native_guard_message": record.get("full_chain_guard_message", ""),
        "target_bounds_world_ras_mm": target_bounds,
        "spindle_bounds_world_ras_mm": spindle_bounds,
        "images": images,
        "ros_connected": False,
        "planner_run": False,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("DENTOBOT_FDI21_COLLISION_RECAPTURE_PASS " + str(OUTPUT / "manifest.json"), flush=True)


try:
    run()
    slicer.util.exit(0)
except Exception as exc:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "failure.json").write_text(json.dumps({"error": str(exc)}, indent=2) + "\n")
    print("DENTOBOT_FDI21_COLLISION_RECAPTURE_FAIL " + str(exc), file=sys.stderr, flush=True)
    slicer.util.exit(1)
