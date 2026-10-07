"""Disposable offline Slicer projection; never changes the operator's scene."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def project_package_offline(source, destination, target, checkpoint, branch=""):
    import slicer
    from dentobot_case.inspection import inspect_package
    from dentobot_case.projection import prepare_projection
    from .workflow_progress import WorkflowProgress

    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or (destination.exists() and os.path.samefile(source, destination)):
        raise ValueError("Partial Save As requires a destination distinct from the source.")
    inventory = inspect_package(source)
    prepare_projection(inventory, target, checkpoint, branch)
    with tempfile.TemporaryDirectory(prefix="dentocase-project-", dir=slicer.app.temporaryPath) as directory:
        directory = Path(directory)
        request = directory / "request.json"
        output = directory / "result.dentocase"
        request.write_text(json.dumps({"source": str(source), "destination": str(output),
                                      "target": target, "checkpoint": checkpoint,
                                      "branch": branch, "sourceSha256": inventory.package_sha256}))
        script = directory / "run.py"
        script.write_text("import sys\nsys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) +
                          ")\nfrom dentobot_workflow.case_projection import run_offline\nrun_offline(" + repr(str(request)) + ")\n")
        progress = WorkflowProgress("Preparing independent partial case")
        try:
            with (directory / "process.log").open("w") as log:
                environment = dict(os.environ)
                # This child cannot participate in the operator's ROS domain.
                environment["ROS_DOMAIN_ID"] = "232"
                process = subprocess.Popen([str(slicer.app.applicationFilePath), "--no-splash",
                    "--no-main-window", "--disable-cli-modules", "--disable-loadable-modules",
                    "--python-script", str(script)], env=environment, stdout=log, stderr=log)
                deadline = time.monotonic() + 180
                try:
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            raise RuntimeError("Offline case projection exceeded 180 seconds.")
                        slicer.app.processEvents()
                        time.sleep(0.03)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
                if process.returncode or not output.is_file():
                    raise RuntimeError("Offline projection failed: " + (directory / "process.log").read_text()[-4000:])
            projected = inspect_package(output)
            if projected.case_id == inventory.case_id or projected.historical_record_count:
                raise ValueError("Independent projection did not reset case identity/history.")
            if hashlib.sha256(source.read_bytes()).hexdigest() != inventory.package_sha256:
                raise ValueError("Source package changed during projection; result was not released.")
            # Same validated bytes, atomically installed at the selected destination.
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staged:
                staged_path = Path(staged.name)
                with output.open("rb") as stream:
                    import shutil
                    shutil.copyfileobj(stream, staged)
                staged.flush()
                os.fsync(staged.fileno())
            try:
                os.replace(staged_path, destination)
            finally:
                staged_path.unlink(missing_ok=True)
            return destination
        finally:
            progress.close()


def run_offline(request_path):
    """Entry called only in the disposable Slicer process."""
    import slicer
    import vtk
    from DENTOCaseBundle import create_case_bundle, extract_scene_mrb
    from dentobot_case.inspection import inspect_package
    from dentobot_case.projection import prepare_projection, filter_registry
    from dentobot_case.contracts import CHECKPOINTS
    from .case_inventory import capture_inventory
    from .parameter_state import DENTOWorkflowParameterNode
    import importlib.util

    try:
        request = json.loads(Path(request_path).read_text())
        inventory = inspect_package(request["source"])
        if inventory.package_sha256 != request["sourceSha256"]:
            raise ValueError("Source changed after selection.")
        plan = prepare_projection(inventory, request["target"], request["checkpoint"], request["branch"])
        with tempfile.TemporaryDirectory(prefix="dentocase-offline-", dir=slicer.app.temporaryPath) as directory:
            scene_path, inspection = extract_scene_mrb(request["source"], directory)
            if not slicer.util.loadScene(str(scene_path), {"clear": True}):
                raise ValueError("Source MRB could not be restored.")
            nodes = {slicer.mrmlScene.GetNthNode(index).GetID(): slicer.mrmlScene.GetNthNode(index)
                     for index in range(slicer.mrmlScene.GetNumberOfNodes())}
            mapping = inventory.metadata["projection"]
            if set(mapping["nodeIds"]) - nodes.keys():
                raise ValueError("Restored scene does not contain every audited node.")
            raw = nodes[mapping["parameterNodeId"]]
            parameter = DENTOWorkflowParameterNode(raw)
            # Load the source logic directly; no module widget or ROS initializer is created.
            module_path = Path(__file__).resolve().parents[3] / "DENTOWorkflow.py"
            spec = importlib.util.spec_from_file_location("DentoCaseOfflineWorkflow", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logic = module.DENTOWorkflowLogic()
            logic.validateLoadedCaseBundleWorkflow(parameter, inspection.workflow)
            actual_inventory, actual_mapping = capture_inventory(parameter, slicer.mrmlScene, inspection.workflow)
            if not actual_inventory["ownershipComplete"]:
                raise ValueError("Restored ownership audit failed: " + "; ".join(actual_inventory["unknownOwnership"]))
            # Re-audit IDs and owners before deleting a single node.
            if actual_mapping["nodeOwners"] != mapping["nodeOwners"]:
                raise ValueError("Restored persistent ownership differs from the saved audit.")
            for name in plan["clearParameters"]:
                value = plan["defaults"][name]
                current = getattr(parameter, name)
                if isinstance(current, bool):
                    value = value.lower() == "true"
                elif isinstance(current, int):
                    value = int(value)
                elif isinstance(current, float):
                    value = float(value)
                setattr(parameter, name, value)
            for role in plan["clearReferenceRoles"]:
                raw.RemoveNodeReferenceIDs(role)
            removed = set(plan["removeNodeIds"])
            # Clear all surviving references to omitted nodes, including auxiliary/display roles.
            for node_id in plan["keepNodeIds"]:
                node = nodes[node_id]
                roles = vtk.vtkStringArray()
                node.GetNodeReferenceRoles(roles)
                for index in range(roles.GetNumberOfValues()):
                    role = roles.GetValue(index)
                    for ref_index in reversed(range(node.GetNumberOfNodeReferences(role))):
                        if node.GetNthNodeReferenceID(role, ref_index) in removed:
                            node.RemoveNthNodeReferenceID(role, ref_index)
            for node_id in removed:
                slicer.mrmlScene.RemoveNode(nodes[node_id])
            branches = [b for b in inventory.branches if b.id == plan["branchId"]]
            trajectory_ids = branches[0].trajectory_ids if branches else tuple(
                trajectory for artifact in inventory.artifacts
                if artifact.target_id == plan["targetId"] and artifact.id in plan["keepNodeIds"]
                for trajectory in artifact.trajectory_ids)
            registry = json.loads(parameter.step6TrajectoryRegistryJson)
            order = next(item.order for item in CHECKPOINTS if item.id == plan["checkpointId"])
            registry = filter_registry(registry, plan["targetId"], trajectory_ids, plan["branchId"], order)
            parameter.step6TrajectoryRegistryJson = json.dumps(registry, sort_keys=True)
            parameter.dentoCaseId = plan["newCaseId"]
            parameter.dentoCaseResumeCheckpoint = plan["checkpointId"]
            parameter.workflowStageIndex = plan["workflowStageIndex"]
            summary = logic.caseBundleWorkflowSummary(parameter)
            summary["caseIdentity"] = {"id": plan["newCaseId"]}
            summary["checkpointInventory"], summary["projectionOwnership"] = capture_inventory(parameter, slicer.mrmlScene, summary)
            if not summary["checkpointInventory"]["ownershipComplete"]:
                raise ValueError("Projected ownership is incomplete.")
            projected_scene = Path(directory) / "projected.mrb"
            if not slicer.util.saveScene(str(projected_scene)):
                raise ValueError("Projected MRB could not be saved.")
            create_case_bundle(request["destination"], projected_scene, case_label=parameter.caseName,
                workflow=summary, robot_profile=inspection.robot_profile,
                application=inspection.manifest.get("application", {}), case_id=plan["newCaseId"])
            # A fresh reopen, before releasing the output, validates reconstructed lineage.
            reopened, result = extract_scene_mrb(request["destination"], Path(directory) / "reopen")
            if not slicer.util.loadScene(str(reopened), {"clear": True}):
                raise ValueError("Projected MRB did not reopen.")
            restored = DENTOWorkflowParameterNode(slicer.mrmlScene.GetNodeByID(raw.GetID()))
            logic.validateLoadedCaseBundleWorkflow(restored, result.workflow)
            if restored.dentoCaseId != plan["newCaseId"]:
                raise ValueError("Projected identity did not survive reopen.")
        slicer.util.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        slicer.util.exit(1)
