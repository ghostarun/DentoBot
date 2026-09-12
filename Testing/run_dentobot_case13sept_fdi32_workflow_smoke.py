"""Focused offline saved-case workflow check for FDI32 trajectory generation.

This runner deliberately keeps the package read-only: the case is loaded into
MRML, local robot meshes are reconstructed without ROS, and the generated
trajectory exists only in the verification process.  Screenshots and a small
JSON result are written under ``data/dentobot-runs/case13sept-fdi32``.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import zipfile

import numpy as np
import qt
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


PACKAGE = Path(
    os.environ.get(
        "DENTOBOT_CASE_SOURCE",
        "/workspace/data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase",
    )
)
ORIGINAL_PACKAGE = PACKAGE
OUTPUT = Path(
    os.environ.get(
        "DENTOBOT_CASE_OUTPUT",
        "/workspace/data/dentobot-runs/case13sept-fdi32",
    )
)


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + float(seconds)
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _diagnostic_integrity_repair(source: Path) -> tuple[Path, dict[str, object]]:
    """Create an opt-in copy for the known revision-only package defect.

    The supplied package is never changed.  This is diagnostic evidence only;
    production loading remains fail-closed for the original mismatch.
    """

    requested = os.environ.get("DENTOBOT_CASE_REPAIR_BASE_REVISION", "").strip()
    if not requested:
        return source, {"applied": False}
    require(requested == "0", "only the known base-revision repair (0) is supported")
    repaired = OUTPUT / "diagnostic-integrity-repaired-case.dentocase"
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(source, "r") as outer:
        members = {info.filename: outer.read(info.filename) for info in outer.infolist()}
    original_mrb = members.get("scene/case.mrb")
    require(original_mrb is not None, "diagnostic repair could not find scene/case.mrb")
    repaired_mrb = io.BytesIO()
    changed = 0
    with zipfile.ZipFile(io.BytesIO(original_mrb), "r") as inner, zipfile.ZipFile(
        repaired_mrb, "w", allowZip64=True
    ) as rebuilt:
        for info in inner.infolist():
            payload = inner.read(info.filename)
            if info.filename.lower().endswith(".mrml"):
                old = b"step6BasePlacementRevision 1"
                new = b"step6BasePlacementRevision 0"
                changed += payload.count(old)
                payload = payload.replace(old, new)
            rebuilt.writestr(info, payload)
    require(changed == 1, f"diagnostic repair expected one stale revision, found {changed}")
    members["scene/case.mrb"] = repaired_mrb.getvalue()

    manifest = json.loads(members["manifest.json"].decode("utf-8"))
    scene_record = manifest["files"]["scene/case.mrb"]
    scene_record["sha256"] = hashlib.sha256(members["scene/case.mrb"]).hexdigest()
    scene_record["sizeBytes"] = len(members["scene/case.mrb"])
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    members["manifest.json"] = manifest_bytes
    checksum_lines = "".join(
        f"{record['sha256']}  {name}\n"
        for name, record in sorted(manifest["files"].items())
    ).encode("ascii")
    members["integrity/checksums.sha256"] = checksum_lines
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temporary = repaired.with_suffix(repaired.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload, compress_type=zipfile.ZIP_STORED if name == "scene/case.mrb" else zipfile.ZIP_DEFLATED)
    temporary.replace(repaired)
    return repaired, {
        "applied": True,
        "reason": "MRML step6BasePlacementRevision 1 disagreed with saved lineage/environment revision 0",
        "original": str(source),
        "repaired": str(repaired),
        "revision": 0,
    }


def segment_ids(segmentation_node) -> list[str]:
    segmentation = segmentation_node.GetSegmentation()
    ids = vtk.vtkStringArray()
    segmentation.GetSegmentIDs(ids)
    return [ids.GetValue(index) for index in range(ids.GetNumberOfValues())]


def enabled(widget) -> bool:
    try:
        return bool(widget.isEnabled())
    except Exception:
        return bool(getattr(widget, "enabled", False))


def current_text(widget) -> str:
    value = getattr(widget, "text", "")
    return str(value() if callable(value) else value)


def _save_widget_png(host, path: Path) -> bool:
    if host is None:
        return False
    try:
        host.show()
    except Exception:
        pass
    process_events(0.15)
    try:
        pixmap = host.grab()
    except Exception:
        return False
    if pixmap.isNull():
        return False
    return bool(pixmap.save(str(path)))


def capture(widget, stem: str) -> list[str]:
    """Capture module UI and the actual VTK 3D render window."""

    OUTPUT.mkdir(parents=True, exist_ok=True)
    ui_path = OUTPUT / f"{stem}-ui.png"
    viewport_path = OUTPUT / f"{stem}-viewport.png"
    # Capture the full application so the selected stage, controls, and 3D
    # viewport are visible together; the module's scroll-content widget can be
    # clipped when Slicer runs under Xvfb.
    ui_host = slicer.util.mainWindow()
    if not _save_widget_png(ui_host, ui_path):
        require(
            _save_widget_png(getattr(widget, "_uiWidget", None), ui_path),
            f"could not capture module UI: {ui_path}",
        )

    layout_manager = slicer.app.layoutManager()
    three_d = layout_manager.threeDWidget(0).threeDView()
    three_d.show()
    three_d.forceRender()
    slicer.util.forceRenderAllViews()
    process_events(0.25)
    viewport = three_d.grab()
    if viewport.isNull() or not viewport.save(str(viewport_path)):
        # Off-screen Qt surfaces can return a null QPixmap even when VTK has
        # rendered correctly.  Capture the render window directly so the
        # evidence remains the real 3D viewport.
        capture_filter = vtk.vtkWindowToImageFilter()
        capture_filter.SetInput(three_d.renderWindow())
        capture_filter.ReadFrontBufferOff()
        capture_filter.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(viewport_path))
        writer.SetInputConnection(capture_filter.GetOutputPort())
        writer.Write()
    require(viewport_path.is_file(), f"could not capture 3D viewport: {viewport_path}")
    return [str(ui_path), str(viewport_path)]


def visibility_summary(node) -> dict:
    display = node.GetDisplayNode() if node else None
    ids = segment_ids(node) if node else []
    return {
        "name": node.GetName() if node else "",
        "segment_count": len(ids),
        "aggregate": bool(display and display.GetVisibility()),
        "visibility_2d": bool(display and display.GetVisibility2D()),
        "visibility_3d": bool(display and display.GetVisibility3D()),
        "all_segments_3d": bool(
            display
            and ids
            and all(display.GetSegmentVisibility3D(segment_id) for segment_id in ids)
        ),
    }


def _visual_diagnostic(widget, parameter, fixed, moving, logic, target_id: str) -> dict:
    """Capture display/camera state when a visual smoke image is empty."""

    def display_state(node) -> dict:
        display = node.GetDisplayNode() if node else None
        ids = segment_ids(node) if node else []
        return {
            "name": node.GetName() if node else "",
            "visibility": bool(display and display.GetVisibility()),
            "visibility_2d": bool(display and display.GetVisibility2D()),
            "visibility_3d": bool(display and display.GetVisibility3D()),
            "generic_segments": {
                segment_id: bool(display.GetSegmentVisibility(segment_id))
                for segment_id in ids
            } if display else {},
            "segments_3d": {
                segment_id: bool(display.GetSegmentVisibility3D(segment_id))
                for segment_id in ids
            } if display else {},
        }

    target_bounds = {}
    for label, node in (("source", parameter.teethSegmentation), ("moving", moving)):
        try:
            target_bounds[label] = list(logic.getSegmentationSegmentBoundsWorld(node, target_id))
        except Exception as exc:
            target_bounds[label] = f"{type(exc).__name__}: {exc}"
    renderer_actors = None
    camera = {}
    try:
        three_d = slicer.app.layoutManager().threeDWidget(0).threeDView()
        renderer = three_d.renderWindow().GetRenderers().GetFirstRenderer()
        renderer_actors = int(renderer.GetActors().GetNumberOfItems()) if renderer else None
        camera_node = three_d.cameraNode()
        vtk_camera = camera_node.GetCamera()
        renderer_camera = renderer.GetActiveCamera() if renderer else None
        camera = {
            "position": [float(value) for value in vtk_camera.GetPosition()],
            "focal_point": [float(value) for value in vtk_camera.GetFocalPoint()],
            "clipping_range": [float(value) for value in vtk_camera.GetClippingRange()],
            "renderer_clipping_range": [
                float(value) for value in renderer_camera.GetClippingRange()
            ] if renderer_camera else None,
        }
    except Exception as exc:
        camera = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "scene_kind": widget._step6SceneKind(),
        "pose_issues": list(logic.step6CaseJawOpeningFreshnessIssues(parameter)),
        "workflow_visible_keys": sorted(str(key) for key in widget._workflowViewVisibleKeys),
        "fixed": display_state(fixed),
        "moving": display_state(moving),
        "source": display_state(parameter.teethSegmentation),
        "target_bounds": target_bounds,
        "renderer_actor_count": renderer_actors,
        "camera": camera,
    }


def _camera_clipping_range() -> list[float]:
    three_d = slicer.app.layoutManager().threeDWidget(0).threeDView()
    return [float(value) for value in three_d.cameraNode().GetCamera().GetClippingRange()]


def _map_point(matrix, point) -> list[float]:
    mapped = matrix.MultiplyPoint((*[float(value) for value in point], 1.0))
    scale = float(mapped[3])
    require(math.isfinite(scale) and abs(scale) > 1e-12, "point transform is invalid")
    result = [float(value) / scale for value in mapped[:3]]
    require(all(math.isfinite(value) for value in result), "point transform is invalid")
    return result


def _crown_center_entry(logic, segmentation_node, segment_id: str) -> tuple[list[float], dict]:
    """Choose a surface point near the superior crown cap, without guessing a voxel."""

    surface = logic._getClosedSurfaceCopy(segmentation_node, segment_id)
    points_data = surface.GetPoints().GetData() if surface.GetPoints() else None
    require(points_data is not None, "FDI32 has no closed-surface points")
    points = np.asarray(vtk_to_numpy(points_data), dtype=float)
    require(points.ndim == 2 and points.shape[1] == 3 and len(points) >= 8, "FDI32 surface is unusable")
    require(np.all(np.isfinite(points)), "FDI32 surface contains non-finite points")

    centered = points - np.mean(points, axis=0)
    covariance = centered.T @ centered
    _eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = np.asarray(eigenvectors[:, int(np.argmax(_eigenvalues))], dtype=float)
    axis_length = float(np.linalg.norm(axis))
    require(math.isfinite(axis_length) and axis_length > 1e-8, "FDI32 surface axis is degenerate")
    axis /= axis_length
    # The saved case uses Slicer RAS with the crown superior (+S) for the
    # lower incisors.  Orient the principal tooth axis consistently before
    # selecting a small cap around its centre.
    if axis[2] < 0.0:
        axis *= -1.0
    projections = centered @ axis
    threshold = float(np.quantile(projections, 0.84))
    cap = points[projections >= threshold]
    require(len(cap) >= 3, "FDI32 crown cap contains too few surface points")
    cap_center = np.mean(cap, axis=0)
    entry = points[int(np.argmin(np.linalg.norm(points - cap_center, axis=1)))]
    bounds = tuple(float(value) for value in surface.GetBounds())
    require(len(bounds) == 6 and all(math.isfinite(value) for value in bounds), "FDI32 bounds are invalid")
    return [float(value) for value in entry], {
        "bounds_ras_mm": list(bounds),
        "principal_axis_ras": [float(value) for value in axis],
        "cap_threshold": threshold,
        "cap_point_count": int(len(cap)),
        "entry_ras_mm": [float(value) for value in entry],
    }


def _trajectory_record(logic, trajectory, segmentation_node, target_id: str) -> dict:
    summary = logic.getTrajectorySummary(trajectory)
    association = logic.getTrajectoryTargetAssociation(trajectory)
    require(summary["isValid"] and summary["definedPointCount"] == 2, "generated FDI32 trajectory is incomplete")
    require(association is not None, "generated FDI32 trajectory has no target association")
    require(association["segmentationNode"] is segmentation_node, "generated trajectory uses another segmentation")
    require(association["targetRecord"]["segmentId"] == target_id, "generated trajectory uses another target")
    return {
        "id": trajectory.GetID(),
        "name": trajectory.GetName(),
        "summary": summary,
        "target_fdi": association["targetRecord"].get("fdiNumber") or "",
        "creation_method": trajectory.GetAttribute("DENTOBOT.TrajectoryCreationMethod") or "",
        "assisted_analysis_present": bool(trajectory.GetAttribute("DENTOBOT.AssistedAnalysisJson")),
    }


def run() -> None:
    source_package = ORIGINAL_PACKAGE
    require(source_package.is_file(), f"missing saved case: {source_package}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    package_path, repair = _diagnostic_integrity_repair(source_package)
    package_sha256 = hashlib.sha256(package_path.read_bytes()).hexdigest()

    slicer.util.selectModule("DENTOWorkflow")
    process_events(1.0)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    require(widget is not None and widget.logic is not None, "DENTOWorkflow widget did not initialize")
    main_window = slicer.util.mainWindow()
    try:
        main_window.resize(1600, 1000)
        main_window.show()
    except Exception:
        pass
    logic = widget.logic
    inspection = widget._openCaseBundle(str(package_path))
    del inspection
    process_events(1.5)
    parameter = widget._parameterNode
    require(parameter is not None, "case package did not restore a parameter node")
    segmentation = parameter.teethSegmentation
    require(parameter.inputVolume is not None and segmentation is not None, "case source anatomy did not restore")

    foundation = logic.evaluateCaseFoundationEligibility(parameter)
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    records = logic.getTargetToothRecords(segmentation)
    fdi_numbers = [str(record.get("fdiNumber") or "") for record in records]
    ros_nodes = list(slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"))
    ros_transforms = [
        node
        for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
        if str(node.GetAttribute("DENTOBOT.Ros2MotionControlActive") or "").lower() == "true"
    ]
    require(foundation["pose"]["eligible"], f"saved Case Foundation pose is not eligible: {foundation['pose']}")
    require(not ros_nodes and not ros_transforms, "case load restored live ROS state")
    require(not registry.get("prepared_branches"), "saved verification case unexpectedly contains PreparedBranches")
    base_before = parameter.robotBaseTransform
    base_before_locked = bool(parameter.robotBaseMountLocked)
    base_before_status = str(parameter.step6BasePlacementStatus or "")
    print(
        "CASE13_LOADED "
        + json.dumps(
            {
                "package_sha256": package_sha256,
                "source_package": str(source_package),
                "loaded_package": str(package_path),
                "diagnostic_repair": repair,
                "source_volume": parameter.inputVolume.GetName(),
                "source_segmentation": segmentation.GetName(),
                "source_volume_fingerprint": foundation["source_volume_fingerprint"],
                "source_segmentation_fingerprint": foundation["source_segmentation_fingerprint"],
                "planning_pose_fingerprint": foundation["planning_pose_fingerprint"],
                "pose": foundation["pose"],
                "base": foundation["base"],
                "base_status": base_before_status,
                "base_locked": base_before_locked,
                "prepared_branch_count": len(registry.get("prepared_branches", {})),
                "target_fdi_numbers": fdi_numbers,
                "ros_nodes": len(ros_nodes),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    require(logic.isRobotBaseTransformNode(base_before), "saved Manual Simulation Base is missing")
    require(not base_before_locked, "verification package changed: expected the persisted base to remain unlocked")

    evidence: list[str] = []
    widget._setWorkflowStage(3, ensureVisible=True)
    widget._applyWorkflowViewPreset("recommended", updateStatus=False)
    process_events(0.6)
    fixed = parameter.step6FixedUpperAnatomy
    moving = parameter.step6MovingLowerAnatomy
    require(fixed is not None and moving is not None, "Case Foundation derived upper/lower displays are missing")
    require(not logic.step6CaseJawOpeningFreshnessIssues(parameter), "saved Case Foundation is stale")
    fixed_summary = visibility_summary(fixed)
    moving_summary = visibility_summary(moving)
    require(fixed_summary["visibility_3d"] and fixed_summary["all_segments_3d"], "fixed-upper Case Foundation display is not fully visible")
    require(moving_summary["visibility_3d"] and moving_summary["all_segments_3d"], "moving-lower Case Foundation display is not fully visible")
    source_display = segmentation.GetDisplayNode()
    require(source_display is not None, "source segmentation display is missing")
    beige = parameter.step6OpenedLowerJawModel
    beige_visible = bool(beige and beige.GetDisplayNode() and beige.GetDisplayNode().GetVisibility3D())
    require(not beige_visible, "beige opened-lower fallback is visible beside the colored moving-lower proxy")
    widget.onFrameWorkflowView()
    evidence.extend(capture(widget, "stage3-case-foundation"))
    print("STAGE3_FOUNDATION_PASS " + json.dumps({"fixed": fixed_summary, "moving": moving_summary, "beige_visible": beige_visible}, sort_keys=True), flush=True)

    step6_index = len(widget._workflowStageEntries()) - 1
    widget._setWorkflowStage(step6_index, ensureVisible=True)
    widget._applyStep6RecommendedView()
    process_events(0.6)
    load_result = widget._robotWorkflowFacade.loadRobot()
    require(load_result.success, f"offline local robot reconstruction failed: {load_result.message}")
    widget._updateRobotPlacement()
    widget._applyStep6RecommendedView()
    widget.onFrameStep6ResearchWorkspace()
    process_events(0.6)
    robot_models = logic.robotModelNodes()
    base_after_load = parameter.robotBaseTransform
    require(base_after_load is not None and logic.isRobotBaseTransformNode(base_after_load), "offline robot load lost the Manual Simulation Base")
    matrix = vtk.vtkMatrix4x4()
    base_after_load.GetMatrixTransformToWorld(matrix)
    matrix_values = [float(matrix.GetElement(row, column)) for row in range(4) for column in range(4)]
    require(all(math.isfinite(value) for value in matrix_values), "Manual Simulation Base matrix is non-finite")
    require(bool(parameter.robotBaseMountLocked) == base_before_locked, "offline robot reconstruction changed base lock state")
    require(str(parameter.step6BasePlacementStatus or "") == base_before_status, "offline robot reconstruction changed base review status")
    require(not logic.isRos2MotionControlActive(base_after_load), "offline robot reconstruction activated ROS motion control")
    evidence.extend(capture(widget, "step6-offline-base"))
    print(
        "STEP6_OFFLINE_BASE_PASS "
        + json.dumps(
            {
                "robot_link_count": len(robot_models),
                "base_status": str(parameter.step6BasePlacementStatus or ""),
                "base_locked": bool(parameter.robotBaseMountLocked),
                "base_matrix_to_world": matrix_values,
                "message": str(load_result.message),
            },
            sort_keys=True,
        ),
        flush=True,
    )

    widget._setWorkflowStage(4, ensureVisible=True)
    widget._applyWorkflowViewPreset("recommended", updateStatus=False)
    widget._updatePlanning()
    widget._updateTrajectoryPlacementModeControls()
    widget._updateAssistedTrajectoryControls()
    process_events(0.6)
    require(enabled(widget.ui.targetToothComboBox), "Step 4A target selection is disabled before base locking")
    require(not bool(parameter.robotBaseMountLocked), "Step 4A pre-target check did not retain the unlocked base state")
    evidence.extend(capture(widget, "step4a-target-selection-unlocked-base"))

    target_record = next(
        (record for record in records if str(record.get("fdiNumber") or "") == "32"),
        None,
    )
    require(target_record is not None, f"FDI32 is not available in the reviewed segmentation; available={fdi_numbers}")
    target_id = target_record["segmentId"]
    target_index = widget.ui.targetToothComboBox.findData(target_id)
    require(target_index >= 0, "FDI32 is missing from the Step 4A target selector")
    widget.ui.targetToothComboBox.currentIndex = target_index
    process_events(0.8)
    require(parameter.targetToothSegmentId == target_id, "Step 4A target selector did not activate FDI32")
    require(enabled(widget.ui.targetToothComboBox), "Step 4A target selector became disabled after FDI32 selection")
    target_bounds = widget._planningTargetBoundsWorld()
    widget._frameRasBoundsInViews(target_bounds)
    print("STEP4A_CLIP_IMMEDIATE " + json.dumps(_camera_clipping_range()), flush=True)
    process_events(0.4)

    assisted_mode_index = widget.ui.trajectoryPlacementModeComboBox.findData("Assisted")
    require(assisted_mode_index >= 0, "Step 4A Assisted placement mode is unavailable")
    widget.ui.trajectoryPlacementModeComboBox.currentIndex = assisted_mode_index
    count_index = widget.ui.assistedTrajectoryCountComboBox.findData(1)
    require(count_index >= 0, "Step 4A one-trajectory assisted option is unavailable")
    widget.ui.assistedTrajectoryCountComboBox.currentIndex = count_index
    process_events(0.5)
    widget._updateAssistedTrajectoryControls()
    require(enabled(widget.ui.trajectoryPlacementModeComboBox), "Step 4A placement-mode selector is disabled with a current pose")
    require(enabled(widget.ui.assistedTrajectoryCountComboBox), "assisted trajectory count is disabled before entry placement")
    require(enabled(widget.ui.placeAssistedTrajectoryEntriesButton), "assisted entry placement is disabled before entry placement")
    widget._applyWorkflowViewPreset("recommended", updateStatus=False)
    widget._frameRasBoundsInViews(target_bounds)
    process_events(0.4)
    step4a_fixed_summary = visibility_summary(fixed)
    step4a_moving_summary = visibility_summary(moving)
    require(
        step4a_fixed_summary["aggregate"]
        and step4a_fixed_summary["visibility_3d"]
        and step4a_fixed_summary["all_segments_3d"],
        "fixed-upper Case Foundation display is not visible in Step 4A",
    )
    require(
        step4a_moving_summary["aggregate"]
        and step4a_moving_summary["visibility_3d"]
        and step4a_moving_summary["all_segments_3d"],
        "moving-lower Case Foundation display is not visible in Step 4A",
    )
    evidence.extend(capture(widget, "step4a-fdi32-assisted-ready"))
    print(
        "STEP4A_VISUAL_DIAGNOSTIC_READY "
        + json.dumps(
            _visual_diagnostic(widget, parameter, fixed, moving, logic, target_id),
            sort_keys=True,
        ),
        flush=True,
    )

    widget.onPlaceAssistedTrajectoryEntries()
    process_events(0.6)
    entry_node = parameter.assistedTrajectoryEntries
    require(logic.isAssistedTrajectoryEntryNode(entry_node), "Step 4A did not create the FDI32 assisted-entry node")
    source_entry_point, entry_details = _crown_center_entry(logic, segmentation, target_id)
    entry_point = list(source_entry_point)
    if logic._targetJawOwner(parameter, target_id) == "MovingLower":
        entry_point = _map_point(
            logic._step6CaseJawMatrixWorld(parameter),
            source_entry_point,
        )
        entry_details["source_entry_ras_mm"] = list(source_entry_point)
        entry_details["entry_ras_mm"] = list(entry_point)
    entry_node.AddControlPointWorld(vtk.vtkVector3d(*entry_point))
    process_events(0.5)
    logic.stopTrajectoryPlacement()
    widget._updateAssistedTrajectoryControls()
    entry_summary = logic.getAssistedTrajectoryEntrySummary(entry_node)
    require(entry_summary["isComplete"], "automated FDI32 crown-center entry was not accepted")
    widget._applyWorkflowViewPreset("recommended", updateStatus=False)
    widget._frameRasBoundsInViews(target_bounds)
    process_events(0.4)
    evidence.extend(capture(widget, "step4a-fdi32-crown-center-entry"))
    print(
        "STEP4A_VISUAL_DIAGNOSTIC_ENTRY "
        + json.dumps(
            _visual_diagnostic(widget, parameter, fixed, moving, logic, target_id),
            sort_keys=True,
        ),
        flush=True,
    )
    print(
        "STEP4A_FDI32_ENTRY_PASS "
        + json.dumps(
            {
                "entry": entry_details,
                "fixed": step4a_fixed_summary,
                "moving": step4a_moving_summary,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    trajectories, analysis = logic.generateAssistedTrajectories(
        entry_node,
        segmentation,
        target_id,
        1,
        parameter.targetToothBoundsRoi,
    )
    require(len(trajectories) == 1, f"expected one assisted FDI32 trajectory, got {len(trajectories)}")
    trajectory = trajectories[0]
    parameter.trajectoryLine = trajectory
    widget._bindPlanningTrajectoryNode(trajectory)
    widget._updatePlanning()
    widget._updateTemplateModeling()
    widget._updateTemplateGuide()
    process_events(0.8)
    trajectory_details = _trajectory_record(logic, trajectory, segmentation, target_id)
    require(trajectory_details["target_fdi"] == "32", "generated trajectory is not associated with FDI32")
    require(trajectory_details["assisted_analysis_present"], "generated trajectory lacks assisted-generation provenance")
    require(
        all(
            logic.isRasPointWithinBounds(point, target_bounds)
            for point in (
                trajectory_details["summary"]["entryRas"],
                trajectory_details["summary"]["targetRas"],
            )
        ),
        "generated FDI32 trajectory is outside the opened target bounds",
    )
    widget._applyWorkflowViewPreset("recommended", updateStatus=False)
    widget._frameRasBoundsInViews(target_bounds)
    process_events(0.4)
    evidence.extend(capture(widget, "step4a-fdi32-assisted-generated"))
    print(
        "STEP4A_VISUAL_DIAGNOSTIC_GENERATED "
        + json.dumps(
            _visual_diagnostic(widget, parameter, fixed, moving, logic, target_id),
            sort_keys=True,
        ),
        flush=True,
    )
    print("DENTOBOT_CASE13_FDI32_ASSISTED_PASS " + json.dumps({"trajectory": trajectory_details, "analysis": analysis}, sort_keys=True), flush=True)

    manual_index = widget.ui.trajectoryPlacementModeComboBox.findData("Manual")
    require(manual_index >= 0, "Step 4A Manual placement mode is unavailable")
    widget.ui.trajectoryPlacementModeComboBox.currentIndex = manual_index
    process_events(0.4)
    require(enabled(widget.ui.targetToothComboBox), "target selection became disabled after assisted generation")
    require(enabled(widget.ui.trajectoryPlacementModeComboBox), "manual/assisted selector became disabled after assisted generation")
    evidence.extend(capture(widget, "step4a-fdi32-manual-mode"))

    rest_stages = []
    for stage_index in range(5, 10):
        widget._setWorkflowStage(stage_index, ensureVisible=True)
        widget._applyWorkflowViewPreset("recommended", updateStatus=False)
        process_events(0.35)
        stage_entries = widget._workflowStageEntries()
        section = stage_entries[stage_index][1]
        require(bool(section.visible), f"workflow stage {stage_index} did not become visible")
        widget.onFrameWorkflowView()
        evidence.extend(capture(widget, f"stage{stage_index}"))
        rest_stages.append(
            {
                "index": stage_index,
                "label": str(stage_entries[stage_index][0]),
                "section_visible": bool(section.visible),
                "planning_pose_eligible": bool(logic.evaluateCaseFoundationEligibility(parameter)["pose"]["eligible"]),
            }
        )
    widget._setWorkflowStage(step6_index, ensureVisible=True)
    widget._applyStep6RecommendedView()
    process_events(0.35)
    final_branch_gate = logic.evaluatePreparedBranchEligibility(parameter)
    require(not final_branch_gate.get("branch"), "foundation-only case unexpectedly acquired a PreparedBranch")
    require(not logic.isRos2MotionControlActive(parameter.robotBaseTransform), "verification enabled ROS after trajectory generation")

    result = {
        "package": str(package_path),
        "source_package": str(source_package),
        "diagnostic_repair": repair,
        "package_sha256": package_sha256,
        "source_volume": parameter.inputVolume.GetName(),
        "source_segmentation": segmentation.GetName(),
        "foundation": foundation,
        "base_status": str(parameter.step6BasePlacementStatus or ""),
        "base_locked": bool(parameter.robotBaseMountLocked),
        "robot_link_count": len(robot_models),
        "target_fdi": "32",
        "step4a_case_foundation_visibility": {
            "fixed": step4a_fixed_summary,
            "moving": step4a_moving_summary,
        },
        "entry": entry_details,
        "trajectory": trajectory_details,
        "analysis": analysis,
        "rest_stages": rest_stages,
        "prepared_branch_count": len(logic.syncDentoCaseTrajectoryRegistry(parameter).get("prepared_branches", {})),
        "ros_active": bool(logic.isRos2MotionControlActive(parameter.robotBaseTransform)),
        "screenshots": evidence,
    }
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    logic.stopTrajectoryPlacement()
    print("DENTOBOT_CASE13_FDI32_WORKFLOW_PASS " + json.dumps({"screenshots": evidence, "result": str(OUTPUT / 'result.json')}, sort_keys=True), flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception as exc:
    failure = {
        "package": str(PACKAGE),
        "source_package": str(ORIGINAL_PACKAGE),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "failure.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
    print("DENTOBOT_CASE13_FDI32_WORKFLOW_FAIL " + json.dumps(failure, sort_keys=True), file=sys.stderr, flush=True)
    try:
        slicer.util.exit(1)
    except Exception:
        raise
