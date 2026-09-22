"""Focused Slicer verification for S6-REUSABLE-CASE-SETUP."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time

import slicer
import vtk


ROOT = Path("/workspace/ros2_ws/src/DentoBot")
HELPERS = ROOT / "DENTOWorkflow/Resources/Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOWorkflow import DENTOWorkflowTest  # noqa: E402
from DENTOCaseBundle import validate_case_bundle  # noqa: E402
from DENTOGuideGeometry import normalize_target_docking_parameters  # noqa: E402


CASE_SOURCE = Path(os.environ.get("DENTOBOT_REUSABLE_CASE_SOURCE", ""))
OUTPUT = Path(os.environ.get("DENTOBOT_REUSABLE_CASE_OUTPUT", "/workspace/data/dentobot-runs/multitarget-step5c"))
CASE_SAVE = Path(os.environ.get("DENTOBOT_REUSABLE_CASE_SAVE", ""))


def process_events(seconds: float = 0.25) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.01)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def enabled(widget) -> bool:
    try:
        return bool(widget.isEnabled())
    except Exception:
        return bool(widget.enabled)


def click(widget, label: str, wait: float = 0.5) -> None:
    require(enabled(widget), f"{label} is disabled")
    widget.click()
    process_events(wait)


def capture(stem: str) -> list[str]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    main_path = OUTPUT / f"{stem}-ui.png"
    viewport_path = OUTPUT / f"{stem}-viewport.png"
    main_window = slicer.util.mainWindow()
    main_window.show()
    process_events(0.2)
    pixmap = main_window.grab()
    require(not pixmap.isNull() and pixmap.save(str(main_path)), "UI capture failed")
    three_d = slicer.app.layoutManager().threeDWidget(0).threeDView()
    three_d.forceRender()
    slicer.util.forceRenderAllViews()
    capture_filter = vtk.vtkWindowToImageFilter()
    capture_filter.SetInput(three_d.renderWindow())
    capture_filter.ReadFrontBufferOff()
    capture_filter.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(viewport_path))
    writer.SetInputConnection(capture_filter.GetOutputPort())
    writer.Write()
    require(viewport_path.is_file(), "3D viewport capture failed")
    return [str(main_path), str(viewport_path)]


def target_combo_index(widget, fdi: str) -> int:
    needle = f"FDI {fdi}"
    for index in range(widget.ui.targetToothComboBox.count):
        if needle in str(widget.ui.targetToothComboBox.itemText(index)):
            return index
    raise RuntimeError(f"target {needle} is absent from Step 4A")


def branch_for_fdi(logic, parameter, fdi: str) -> tuple[str, dict]:
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    tooth = registry["teeth"].get(f"FDI{fdi}") or {}
    branch_ids = [branch_id for slot in tooth.get("trajectory_set", {}).get("slots", ()) for branch_id in slot.get("prepared_branch_ids", ())]
    require(branch_ids, f"FDI{fdi} has no PreparedBranch")
    branch_id = next(
        (
            value
            for value in branch_ids
            if logic.evaluatePreparedBranchForVerification(parameter, value, registry=registry)["eligible"]
        ),
        branch_ids[0],
    )
    return branch_id, registry["prepared_branches"][branch_id]


def active_docking_parameters(parameter) -> dict:
    return normalize_target_docking_parameters(
        pattern_radius_mm=parameter.targetDockingPatternRadiusMm,
        outer_diameter_mm=parameter.targetDockingOuterDiameterMm,
        bore_diameter_mm=parameter.targetDockingBoreDiameterMm,
        connector_diameter_mm=parameter.targetDockingConnectorDiameterMm,
        connector_thickness_mm=parameter.targetDockingConnectorThicknessMm,
        shared_depth_mm=parameter.targetDockingSharedDepthMm,
        individual_depths_mm=(parameter.targetDockingDepth1Mm, parameter.targetDockingDepth2Mm, parameter.targetDockingDepth3Mm, parameter.targetDockingDepth4Mm),
        individual_depths_enabled=parameter.targetDockingIndividualDepthsEnabled,
        yaw_deg=parameter.targetDockingYawDeg,
        collision_clearance_mm=parameter.targetDockingCollisionClearanceMm,
        clearance_mm=parameter.templateDockingClearanceMm,
        reinforcement_radial_mm=parameter.templateReinforcementRadialMm,
        processing_resolution_mm=parameter.templateSamplingSpacingMm,
    )


def select_step5c_branch(widget, fdi: str) -> dict:
    widget._setWorkflowStage(9, ensureVisible=True)
    widget._updateTemplateFinalization()
    process_events(0.2)
    selector = widget.ui.finalVerificationModelSelector
    needle = f"FDI{fdi}"
    index = next((i for i in range(selector.count) if needle in str(selector.itemText(i))), -1)
    require(index > 0, f"Step 5C has no {needle} target guide")
    selector.setCurrentIndex(index)
    process_events(0.5)
    parameter = widget._parameterNode
    logic = widget.logic
    branch_id, branch = branch_for_fdi(logic, parameter, fdi)
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    require(str(registry["selected_branch_id"]) == branch_id, f"{needle} did not become selected")
    dock = slicer.mrmlScene.GetNodeByID(branch["target_docking_node_id"])
    stored = json.loads(logic.getTargetDockingAssemblySummary(dock)["parametersJson"])
    require(active_docking_parameters(parameter) == stored, f"{needle} docking scalars were not restored")
    click(widget.ui.verifyFinalTemplateButton, f"Verify {needle}", 0.8)
    eligibility = logic.evaluatePreparedBranchEligibility(parameter, branch_id)
    require(eligibility["eligible"], f"{needle} verification failed: {eligibility['message']}")
    return {"fdi": fdi, "branch_id": branch_id, "yaw_deg": stored["yawDeg"], "reason": eligibility["reason"]}


def run_saved_multitarget() -> None:
    require(CASE_SOURCE.is_file(), f"missing saved case: {CASE_SOURCE}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    slicer.util.selectModule("DENTOWorkflow")
    process_events(0.8)
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    require(widget is not None and widget.logic is not None, "DENTOWorkflow did not initialize")
    slicer.util.mainWindow().resize(1836, 900)
    widget._openCaseBundle(str(CASE_SOURCE))
    process_events(1.0)
    parameter = widget._parameterNode
    logic = widget.logic
    require(parameter is not None, "case did not restore a parameter node")
    errors = []
    original_error = slicer.util.errorDisplay
    original_confirm = slicer.util.confirmYesNoDisplay
    slicer.util.errorDisplay = lambda message, **_kwargs: errors.append(str(message))
    slicer.util.confirmYesNoDisplay = lambda *_args, **_kwargs: True
    evidence = []
    try:
        widget._setWorkflowStage(4, ensureVisible=True)
        widget.ui.targetToothComboBox.setCurrentIndex(target_combo_index(widget, "21"))
        process_events(0.8)
        target = logic.validateTargetTooth(parameter.teethSegmentation, parameter.targetToothSegmentId)
        require(str(target["fdiNumber"]) == "21", "Step 4A did not select FDI21")

        widget._setWorkflowStage(5, ensureVisible=True)
        widget._updateTemplateModeling()
        process_events(0.3)
        click(widget.ui.createDraftTemplateSupportModelButton, "Step 4B Update Draft Support", 1.0)
        widget._setWorkflowStage(6, ensureVisible=True)
        click(widget.ui.generateTargetDockingAssemblyButton, "Step 4C Auto-Place Draft", 1.0)
        click(widget.ui.confirmTargetDockingYawButton, "Step 4C Confirm Orientation", 0.5)
        widget._setWorkflowStage(7, ensureVisible=True)
        click(widget.ui.createTemplateSupportPlaneButton, "Step 5A Create Support Plane", 0.6)
        click(widget.ui.generateTemplateSupportBoundaryFromPlaneButton, "Step 5A Generate Boundary", 1.0)
        widget._setWorkflowStage(8, ensureVisible=True)
        click(widget.ui.generateFinalPrintableTemplateButton, "Step 5B Build Unified Template", 4.0)

        switches = [select_step5c_branch(widget, fdi) for fdi in ("31", "21", "31")]
        evidence.extend(capture("step5c-third-alternate-fdi31"))
        final_fdi21 = select_step5c_branch(widget, "21")
        evidence.extend(capture("step5c-final-fdi21-verified"))
        widget._setWorkflowStage(10, ensureVisible=True)
        widget._updateStep6PlanningUi()
        click(widget.ui.importStep6PlanningContextButton, "Step 6A Activate PreparedBranch", 1.0)
        require(parameter.step6PlanningContextImported, "Step 6A did not import FDI21")
        active = logic.evaluatePreparedBranchEligibility(parameter)
        require(active["eligible"], f"Step 6A branch is not eligible: {active['message']}")
        evidence.extend(capture("step6a-fdi21-preparedbranch-active"))
        require(not errors, f"GUI reported errors: {errors}")
        saved_case = None
        if str(CASE_SAVE):
            require(not CASE_SAVE.exists(), f"refusing to overwrite saved case: {CASE_SAVE}")
            CASE_SAVE.parent.mkdir(parents=True, exist_ok=True)
            inspection = widget._createCaseBundle(CASE_SAVE)
            validate_case_bundle(inspection.path)
            saved_case = {
                "path": str(inspection.path),
                "sha256": hashlib.sha256(inspection.path.read_bytes()).hexdigest(),
            }
        result = {
            "status": "PASS",
            "case": str(CASE_SOURCE),
            "case_sha256": hashlib.sha256(CASE_SOURCE.read_bytes()).hexdigest(),
            "switches": switches,
            "final_fdi21": final_fdi21,
            "step6_selected_branch_id": active["branch_id"],
            "step6_imported": bool(parameter.step6PlanningContextImported),
            "saved_case": saved_case,
            "evidence": evidence,
        }
        (OUTPUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print("DENTOBOT_MULTITARGET_STEP5C_PASS " + json.dumps(result, sort_keys=True), flush=True)
    finally:
        slicer.util.errorDisplay = original_error
        slicer.util.confirmYesNoDisplay = original_confirm


def run_synthetic() -> None:
    slicer.util.selectModule("DENTOWorkflow")
    test = DENTOWorkflowTest()
    test.setUp()
    test.test_DENTOWorkflowCaseFoundation()
    test.setUp()
    test._focusedPreparedBranchSmoke = True
    test.test_DENTOWorkflowVisibleTemplateSupportSurface()
    print("DENTOBOT_REUSABLE_CASE_PASS", flush=True)


try:
    run_saved_multitarget() if str(CASE_SOURCE) else run_synthetic()
    slicer.util.exit(0)
except Exception as exc:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    failure = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
    (OUTPUT / "result.json").write_text(json.dumps(failure, indent=2) + "\n")
    print(f"DENTOBOT_REUSABLE_CASE_FAILED: {failure['error']}", file=sys.stderr, flush=True)
    slicer.util.exit(1)
