"""Disposable offline Slicer projection; never changes the operator's scene."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def _inspect_prefix(source, destination, target, checkpoint, branch):
    from dentobot_case.inspection import inspect_package
    from dentobot_case.projection import prepare_projection
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or (destination.exists() and os.path.samefile(source, destination)):
        raise ValueError("Partial Save As requires a destination distinct from the source.")
    inventory = inspect_package(source)
    prepare_projection(inventory, target, checkpoint, branch)
    return inventory, source, destination


def _release_projection(output, source, destination, inventory):
    from dentobot_case.inspection import inspect_package
    from DENTOCaseBundle import sha256_file
    import shutil
    projected = inspect_package(output)
    if (projected.integrity != "Valid" or not projected.ownership_complete
            or not projected.case_id or projected.case_id == inventory.case_id
            or projected.package_id == inventory.package_id or projected.historical_record_count):
        raise ValueError("Independent projection did not reset case identity/history.")
    digest = sha256_file(source)
    if digest != inventory.package_sha256:
        raise ValueError("Source package changed during projection; result was not released.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staged:
            staged_path = Path(staged.name)
            with output.open("rb") as stream:
                shutil.copyfileobj(stream, staged)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(staged_path, destination)
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
    return destination


def project_package_offline(source, destination, target, checkpoint, branch=""):
    import slicer
    from concurrent.futures import ThreadPoolExecutor
    from .workflow_progress import WorkflowProgress

    progress = WorkflowProgress("Preparing independent partial case")
    progress.update("Validating saved package and cutoff", can_cancel=False)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dentocase-projection-io")

    def wait_io(future):
        while not future.done():
            slicer.app.processEvents()
            time.sleep(0.03)
        return future.result()

    try:
        inventory, source, destination = wait_io(executor.submit(
            _inspect_prefix, source, destination, target, checkpoint, branch))
        with tempfile.TemporaryDirectory(prefix="dentocase-project-", dir=slicer.app.temporaryPath) as directory:
            directory = Path(directory)
            request = directory / "request.json"
            output = directory / "result.dentocase"
            request.write_text(json.dumps({"source": str(source), "destination": str(output),
                "target": target, "checkpoint": checkpoint, "branch": branch,
                "sourceSha256": inventory.package_sha256}))
            script = directory / "run.py"
            script.write_text("import sys\nsys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) +
                ")\nfrom dentobot_workflow.case_projection import run_offline\nrun_offline(" + repr(str(request)) + ")\n")
            progress.update("Offline projection and fresh reopen", can_cancel=False)
            with (directory / "process.log").open("w") as log:
                environment = dict(os.environ)
                environment["ROS_DOMAIN_ID"] = "232"
                process = subprocess.Popen([str(slicer.app.launcherExecutableFilePath), "--no-splash",
                    "--no-main-window", "--disable-cli-modules", "--python-code",
                    "exec(open(" + repr(str(script)) + ").read())"],
                    env=environment, stdout=log, stderr=log)
                deadline = time.monotonic() + 180
                try:
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Offline case projection exceeded 180 seconds.")
                        slicer.app.processEvents()
                        time.sleep(0.03)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                if process.returncode or not output.is_file():
                    raise RuntimeError("Offline projection failed: " + (directory / "process.log").read_text()[-4000:])
            progress.update("Validating and releasing the independent package", can_cancel=False)
            return wait_io(executor.submit(_release_projection, output, source, destination, inventory))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        progress.close()


def run_offline(request_path):
    """Entry called only in the disposable Slicer process."""
    import slicer
    from DENTOCaseBundle import create_case_bundle, extract_scene_mrb
    from dentobot_case.inspection import inspect_package
    from dentobot_case.projection import prepare_projection, filter_registry
    from dentobot_case.contracts import CHECKPOINTS
    from .case_inventory import capture_inventory
    from .parameter_state import DENTOWorkflowParameterNode
    import importlib.util
    import sys

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
            spec = importlib.util.spec_from_file_location("DENTOWorkflow", module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            logic = module.DENTOWorkflowLogic()
            logic.validateLoadedCaseBundleWorkflow(parameter, inspection.workflow)
            actual_inventory, actual_mapping = capture_inventory(parameter, slicer.mrmlScene, inspection.workflow)
            if not actual_inventory["ownershipComplete"]:
                raise ValueError("Restored ownership audit failed: " + "; ".join(actual_inventory["unknownOwnership"]))
            # Re-audit IDs and owners before deleting a single node.
            if any(actual_mapping["nodeOwners"].get(node_id) != owners
                   for node_id, owners in mapping["nodeOwners"].items()):
                raise ValueError("Restored persistent ownership differs from the saved audit.")
            extra = set(actual_mapping["nodeOwners"]) - set(mapping["nodeOwners"])
            if any(actual_mapping["nodeOwners"][node_id] != ["@display"] for node_id in extra):
                raise ValueError("Restore introduced unaudited persistent geometry or state.")
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
                roles = []
                node.GetNodeReferenceRoles(roles)
                for role in roles:
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
            from dentobot_case.ownership import NODE_ATTRIBUTE_OWNERS
            checkpoint_orders = {item.id: item.order for item in CHECKPOINTS}
            for node_id in plan["keepNodeIds"]:
                for attribute, owner in NODE_ATTRIBUTE_OWNERS.items():
                    if checkpoint_orders[owner] > order and nodes[node_id].GetAttribute(attribute) is not None:
                        nodes[node_id].SetAttribute(attribute,
                            "NotVerified" if attribute == "DENTOBOT.VerificationState" else None)
            parameter.step6TrajectoryRegistryJson = json.dumps(registry, sort_keys=True)
            from dataclasses import asdict
            units = branches if order >= 50 else []
            raw.SetAttribute("DENTOBOT.CasePreparationUnitsJson", json.dumps({
                "version": "1.0", "branches": [asdict(unit) for unit in units],
            }, sort_keys=True))
            # Select the requested saved unit, rather than retaining unrelated
            # global pointers from whichever target was active at save time.
            from dentobot_case.ownership import NODE_FIELDS
            from collections import defaultdict
            candidates = defaultdict(list)
            kept = set(plan["keepNodeIds"])
            for artifact in inventory.artifacts:
                if artifact.id in kept and artifact.role in NODE_FIELDS:
                    candidates[artifact.role].append(artifact.id)
            for field, identifiers in candidates.items():
                current = getattr(parameter, field, None)
                if len(identifiers) == 1:
                    selected_id = identifiers[0]
                elif field == "trajectoryLine" and branches:
                    source_unit = inspection.workflow.get("step6", {}).get(
                        "trajectoryRegistry", {}).get("prepared_branches", {}).get(plan["branchId"], {})
                    primary_identity = source_unit.get("primary_trajectory_id")
                    if not primary_identity and current is not None and current.GetID() in identifiers:
                        selected_id = current.GetID()
                        setattr(parameter, field, nodes[selected_id])
                        continue
                    primary_identity = primary_identity or branches[0].trajectory_ids[0]
                    primary = next((artifact.id for artifact in inventory.artifacts
                        if artifact.id in identifiers and artifact.trajectory_ids
                        and primary_identity in artifact.trajectory_ids), None)
                    if primary is None:
                        raise ValueError("The selected preparation unit has no primary trajectory binding.")
                    selected_id = primary
                elif current is not None and current.GetID() in identifiers:
                    selected_id = current.GetID()
                else:
                    raise ValueError("Ambiguous saved binding for " + field + "; projection was not released.")
                setattr(parameter, field, nodes[selected_id])
            tooth = next((item for item in registry["teeth"].values()
                          if item.get("target_id") == plan["targetId"]), None)
            if tooth is not None:
                parameter.targetToothSegmentId = tooth["segment_id"]
            if parameter.inputVolume is not None:
                parameter.inspectedVolume = parameter.inputVolume
            if parameter.teethSegmentation is not None:
                parameter.inspectedSegmentation = parameter.teethSegmentation
            raw.RemoveNodeReferenceIDs("DENTOBOT.SelectedGuideTrajectory")
            for artifact in inventory.artifacts:
                if artifact.id in kept and artifact.role == "trajectoryLine":
                    raw.AddNodeReferenceID("DENTOBOT.SelectedGuideTrajectory", artifact.id)
            parameter.dentoCaseId = plan["newCaseId"]
            parameter.dentoCaseResumeCheckpoint = plan["checkpointId"]
            parameter.workflowStageIndex = plan["workflowStageIndex"]
            summary = logic.caseBundleWorkflowSummary(parameter)
            summary["caseIdentity"] = {"id": plan["newCaseId"]}
            projected_scene = Path(directory) / "projected.mrb"
            if not slicer.util.saveScene(str(projected_scene)):
                raise ValueError("Projected MRB could not be saved.")
            # As with ordinary saves, include storage nodes created by saving.
            summary["checkpointInventory"], summary["projectionOwnership"] = capture_inventory(parameter, slicer.mrmlScene, summary)
            if not summary["checkpointInventory"]["ownershipComplete"]:
                raise ValueError("Projected ownership is incomplete.")
            create_case_bundle(request["destination"], projected_scene, case_label=parameter.caseName,
                workflow=summary, robot_profile=inspection.robot_profile,
                application=inspection.manifest.get("application", {}), case_id=plan["newCaseId"])
            # A fresh reopen, before releasing the output, validates reconstructed lineage.
            parameter_node_id = raw.GetID()
            reopened, result = extract_scene_mrb(request["destination"], Path(directory) / "reopen")
            if not slicer.util.loadScene(str(reopened), {"clear": True}):
                raise ValueError("Projected MRB did not reopen.")
            restored = DENTOWorkflowParameterNode(slicer.mrmlScene.GetNodeByID(parameter_node_id))
            logic.validateLoadedCaseBundleWorkflow(restored, result.workflow)
            if restored.dentoCaseId != plan["newCaseId"]:
                raise ValueError("Projected identity did not survive reopen.")
            reopened_inventory, _ = capture_inventory(restored, slicer.mrmlScene, result.workflow)
            if (not reopened_inventory["ownershipComplete"]
                    or reopened_inventory["artifacts"] != summary["checkpointInventory"]["artifacts"]
                    or reopened_inventory["branches"] != summary["checkpointInventory"]["branches"]):
                raise ValueError("Projected lineage did not survive fresh reopen.")
        slicer.util.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        slicer.util.exit(1)
