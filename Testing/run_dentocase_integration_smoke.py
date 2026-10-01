"""Offline synthetic DentoCase full/partial persistence and rollback check.

The fixture is saved evidence, including stale geometry; it has no reviewed
planning, ROS, motion or clinical authority.
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import traceback

import numpy as np
import slicer
import vtk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))
from DENTOCaseBundle import create_case_bundle, extract_scene_mrb, CaseBundleError, sha256_file
from dentobot_case.inspection import inspect_package
from dentobot_case.lineage import select_prefix
from dentobot_case.projection import prepare_projection
from dentobot_workflow.case_projection import project_package_offline
from dentobot_workflow.runtime import DENTOWORKFLOW_MODULE_DIRECTORY


def sha(path):
    return sha256_file(path)


def run():
    evidence = Path(os.environ["DENTOCASE_EVIDENCE_DIR"])
    evidence.mkdir(parents=True, exist_ok=True)
    assert DENTOWORKFLOW_MODULE_DIRECTORY == ROOT / "DENTOWorkflow"
    slicer.util.selectModule("DENTOWorkflow")
    slicer.mrmlScene.Clear(0)
    slicer.app.processEvents()
    widget = slicer.util.getModuleWidget("DENTOWorkflow")
    logic, parameter = widget.logic, widget._parameterNode
    parameter.caseName = "DentoCase synthetic integration"
    volume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "Synthetic source")
    slicer.util.updateVolumeFromArray(volume, np.arange(12**3, dtype=np.int16).reshape(12, 12, 12))
    volume.CreateDefaultDisplayNodes()
    volume.SetAttribute("DENTOBOT.CaseScan", "true")
    segmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "Synthetic reviewed masks")
    segmentation.CreateDefaultDisplayNodes()
    segmentation.SetReferenceImageGeometryParameterFromVolumeNode(volume)
    for fdi, offset in (("11", 0), ("21", 4)):
        mask = np.zeros((12, 12, 12), dtype=np.uint8)
        mask[2:5, 2:5, 2+offset:5+offset] = 1
        segment_id = segmentation.GetSegmentation().AddEmptySegment(
            "synthetic-" + fdi, "upper_" + ("right" if fdi == "11" else "left") + "_central_incisor_fdi" + fdi)
        slicer.util.updateSegmentBinaryLabelmapFromArray(mask, segmentation, segment_id, volume)
    segmentation.SetAttribute("DENTOBOT.ReviewState", "Reviewed")
    parameter.inputVolume = volume
    parameter.inspectedVolume = volume
    parameter.teethSegmentation = segmentation
    parameter.inspectedSegmentation = segmentation
    parameter.targetToothSegmentId = "synthetic-11"
    pose = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode", "Synthetic pose")
    parameter.step6CaseJawTransform = pose
    base = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode", "Synthetic Base")
    parameter.robotBaseTransform = base

    def line(fdi, shift=0):
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", "Synthetic trajectory " + fdi)
        node.AddControlPoint(vtk.vtkVector3d(shift, 0, 0))
        node.AddControlPoint(vtk.vtkVector3d(shift, 0, 5))
        node.SetAttribute("DENTOBOT.TrajectoryRole", "EntryToTarget")
        node.SetAttribute("DENTOBOT.TargetSegmentID", "synthetic-" + fdi)
        node.SetAttribute("DENTOBOT.TargetFdiNumber", fdi)
        node.SetAttribute("DENTOBOT.CoordinateSystem", "SlicerRASmm")
        node.SetNodeReferenceID("DENTOBOT.TargetSegmentation", segmentation.GetID())
        return node

    trajectory = line("11")
    paired_trajectory = line("11", 3)
    other_trajectory = line("21", 8)
    parameter.trajectoryLine = trajectory
    registry = logic.syncDentoCaseTrajectoryRegistry(parameter)
    target = trajectory.GetAttribute("DENTOBOT.RegistryTargetID")
    branch_id = logic._stableDentoCaseId("guide", target,
        trajectory.GetAttribute("DENTOBOT.RegistryTrajectoryID"),
        paired_trajectory.GetAttribute("DENTOBOT.RegistryTrajectoryID"))
    primary_id = paired_trajectory.GetID()

    def model(field, role):
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Synthetic " + role)
        sphere = vtk.vtkSphereSource()
        sphere.SetRadius(1)
        sphere.Update()
        node.SetAndObservePolyData(sphere.GetOutput())
        node.CreateDefaultDisplayNodes()
        node.SetAttribute("DENTOBOT.ModelRole", role)
        node.SetAttribute("DENTOBOT.GeometryState", "Stale")
        node.SetAttribute("DENTOBOT.RegistryTargetID", target)
        node.SetAttribute("DENTOBOT.RegistryGuideSetID", branch_id)
        node.SetAndObserveTransformNodeID(pose.GetID())
        setattr(parameter, field, node)
        return node

    draft = model("draftTemplateSupportModel", "TemplateSupportDraft")
    dock = model("targetDockingAssemblyModel", "TargetDockingAssembly")
    visible = model("visibleTemplateSupportModel", "VisibleTemplateSupportSurface")
    shell = model("patientContactShellModel", "PatientContactShell")
    shell.SetNodeReferenceID("DENTOBOT.PatientShellSourceAnatomy", draft.GetID())
    final = model("finalPrintableTemplateModel", "FinalPrintableTemplate")
    final.SetNodeReferenceID("DENTOBOT.FinalGuideSourceTrajectory", trajectory.GetID())
    final.AddNodeReferenceID("DENTOBOT.FinalGuideSourceTrajectory", paired_trajectory.GetID())
    final.SetAttribute("DENTOBOT.PrimaryTrajectoryNodeID", primary_id)
    final.SetNodeReferenceID("DENTOBOT.FinalGuidePatientShell", shell.GetID())
    final.SetNodeReferenceID("DENTOBOT.FinalGuideTargetDockingAssembly", dock.GetID())
    final.SetAttribute("DENTOBOT.PairingIntent", "ExplicitPair")
    late = model("finalizedTemplateShellModel", "FinalizedTemplateShell")
    final.SetNodeReferenceID("DENTOBOT.FinalGuideFinalizedShell", late.GetID())
    late_id, other_id = late.GetID(), other_trajectory.GetID()
    final.SetAttribute("DENTOBOT.VerificationJson", '{"fixture":"saved-5c"}')
    final.SetAttribute("DENTOBOT.VerificationState", "Saved fixture evidence")

    full = evidence / "full.dentocase"
    revision = evidence / "revision.dentocase"
    saved = widget._createCaseBundle(full)
    again = widget._createCaseBundle(revision)
    assert saved.manifest["case"]["id"] == again.manifest["case"]["id"]
    assert saved.manifest["packageId"] != again.manifest["packageId"]
    inventory = inspect_package(full)
    (evidence / "inventory.json").write_text(json.dumps(inventory.to_dict(), indent=2))
    assert inventory.ownership_complete, inventory.unknown_ownership
    selection = select_prefix(inventory, target, "template.build", branch_id)
    assert selection.allowed, selection.reasons
    plan = prepare_projection(inventory, target, "template.build", branch_id)
    assert late_id in plan["removeNodeIds"] and other_id in plan["removeNodeIds"]
    assert final.GetID() in plan["keepNodeIds"]

    # Exercise real PythonQt browser rendering against an explicitly scanned
    # synthetic folder. All live activation remains below, outside this dialog.
    from dentobot_case.catalog import Catalog
    from dentobot_workflow.case_library import show_case_library
    import time
    database = evidence / "catalog.sqlite"
    with Catalog(database) as catalog:
        catalog.scan(evidence)
    def unexpected_action(*_args):
        raise AssertionError("The browser rendering check must not activate a case")
    dialog = show_case_library(slicer.util.mainWindow(), database_path=str(database),
        on_full_load=unexpected_action, on_partial_load=unexpected_action,
        on_partial_save=unexpected_action)
    deadline = time.monotonic() + 10
    while not dialog._case_library_rows and time.monotonic() < deadline:
        slicer.app.processEvents()
        time.sleep(0.03)
    assert dialog._case_library_rows, "The actual Qt browser did not populate"
    assert any(row.get("checkpoint_id") == "template.build" and row.get("partial_enabled")
               for row in dialog._case_library_rows.values())
    dialog.dialog.resize(1200, 850)
    dialog._case_library_tree.expandToDepth(5)
    slicer.app.processEvents()
    assert dialog.dialog.grab().save(str(evidence / "library-synthetic.png"))
    dialog.dialog.close()
    assert dialog._case_library_closed
    before = sha(full)
    live_ids = tuple(slicer.mrmlScene.GetNthNode(i).GetID() for i in range(slicer.mrmlScene.GetNumberOfNodes()))
    active_identity = parameter.dentoCaseId
    partial = evidence / "partial-5b.dentocase"
    project_package_offline(full, partial, target, "template.build", branch_id)
    assert sha(full) == before
    assert parameter.dentoCaseId == active_identity
    assert live_ids == tuple(slicer.mrmlScene.GetNthNode(i).GetID() for i in range(slicer.mrmlScene.GetNumberOfNodes()))
    projected = inspect_package(partial)
    assert projected.case_id != inventory.case_id
    assert not projected.historical_record_count
    widget._openCaseBundle(partial)
    assert widget._parameterNode.dentoCaseId == projected.case_id
    assert widget._parameterNode.finalPrintableTemplateModel is not None
    assert widget._parameterNode.finalizedTemplateShellModel is None
    assert not widget._parameterNode.finalPrintableTemplateModel.GetAttribute("DENTOBOT.VerificationJson")
    assert widget._parameterNode.finalPrintableTemplateModel.GetAttribute("DENTOBOT.VerificationState") == "NotVerified"
    assert slicer.mrmlScene.GetNodeByID(other_id) is None
    assert widget._parameterNode.trajectoryLine.GetID() == primary_id
    assert any(b.pairing_intent == "ExplicitPair" and len(b.trajectory_ids) == 2
               for b in projected.branches)
    assert widget._parameterNode.dentoCaseResumeCheckpoint == "template.build"
    assert widget._parameterNode.workflowStageIndex == 8
    assert not widget._parameterNode.step6PlanningContextImported
    assert not widget._parameterNode.step6ConfirmedTaskJson
    assert not slicer.util.getNodesByClass("vtkMRMLROS2RobotNode")

    # Activation path clears the source destination and restores an unsaved case.
    widget._openLibraryPartialCase(full, target, "template.build", branch_id)
    assert widget._loadedCaseBundlePath == ""
    assert slicer.mrmlScene.GetURL() == ""
    independent_id = widget._parameterNode.dentoCaseId
    widget._createCaseBundle(evidence / "continued-save-as.dentocase")
    assert widget._parameterNode.dentoCaseId == independent_id

    # A pre-build cutoff retains branch preparation intent for continuation.
    prebuild = evidence / "partial-5a.dentocase"
    project_package_offline(full, prebuild, target, "support.surface", branch_id)
    prebuild_inventory = inspect_package(prebuild)
    assert prebuild_inventory.ownership_complete
    assert any(b.id == branch_id for b in prebuild_inventory.branches)

    # Full load preserves identity; a failed incoming lineage restores the prior scene.
    widget._openCaseBundle(full)
    assert widget._parameterNode.dentoCaseId == inventory.case_id
    widget._parameterNode.caseName = "Recovery sentinel"
    sentinel_id = widget._parameterNode.dentoCaseId
    with tempfile.TemporaryDirectory(dir=slicer.app.temporaryPath) as directory:
        scene, source = extract_scene_mrb(full, directory)
        bad_workflow = dict(source.workflow)
        bad_workflow["caseLabel"] = "Invalid incoming label"
        bad = evidence / "invalid-lineage.dentocase"
        create_case_bundle(bad, scene, case_label=source.manifest["case"]["label"],
                           workflow=bad_workflow, robot_profile=source.robot_profile)
    try:
        widget._openCaseBundle(bad)
    except CaseBundleError:
        pass
    else:
        raise AssertionError("Invalid incoming lineage loaded")
    assert widget._parameterNode.caseName == "Recovery sentinel"
    assert widget._parameterNode.dentoCaseId == sentinel_id
    assert widget._caseBundleRestoreDepth == 0
    assert sha(full) == before
    (evidence / "result.json").write_text(json.dumps({"status": "PASS", "fullCaseId": inventory.case_id,
        "partialCaseId": projected.case_id, "sourceSha256": before,
        "evidenceLevel": "synthetic_offline_slicer", "liveAuthority": "Unverified"}, indent=2))
    print("DENTOCASE_INTEGRATION_PASS", flush=True)
    slicer.util.exit(0)


try:
    run()
except Exception:
    failure = traceback.format_exc()
    traceback.print_exc()
    (Path(os.environ["DENTOCASE_EVIDENCE_DIR"]) / "result.json").write_text(json.dumps({
        "status": "FAIL", "firstError": failure,
        "evidenceLevel": "synthetic_offline_slicer", "liveAuthority": "Unverified",
    }, indent=2))
    print("DENTOCASE_INTEGRATION_FAIL", flush=True)
    slicer.util.exit(1)
