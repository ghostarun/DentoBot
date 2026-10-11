"""Disposable offline Slicer projection; never changes the operator's scene."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4


def _clear_future_node_attributes(node, checkpoint_order):
    """Drop saved downstream authority from retained geometry in a prefix."""
    from dentobot_case.contracts import CHECKPOINTS
    from dentobot_case.ownership import NODE_ATTRIBUTE_OWNERS

    orders = {item.id: item.order for item in CHECKPOINTS}
    for attribute, owner in NODE_ATTRIBUTE_OWNERS.items():
        if orders[owner] > checkpoint_order and node.GetAttribute(attribute) is not None:
            node.SetAttribute(attribute,
                "NotVerified" if attribute == "DENTOBOT.VerificationState" else None)



def _restore_selected_docking_parameters(parameter, logic, plan, normalize):
    """Bind retained editor settings to the selected saved assembly, not another branch.

    The audited assembly is authoritative for its construction settings. Future
    checkpoint fields remain cleared by the projection plan. This does not edit
    geometry, mark stale output Current, or manufacture verification evidence.
    """
    assembly = getattr(parameter, "targetDockingAssemblyModel", None)
    if assembly is None:
        return
    if assembly.GetID() not in plan["keepNodeIds"]:
        raise ValueError("Selected docking assembly is outside the retained prefix.")
    summary = logic.getTargetDockingAssemblySummary(assembly)
    saved = json.loads(summary["parametersJson"])
    fields = {
        "targetDockingPatternRadiusMm": ("patternRadiusMm", "pattern_radius_mm"),
        "targetDockingOuterDiameterMm": ("outerDiameterMm", "outer_diameter_mm"),
        "targetDockingBoreDiameterMm": ("boreDiameterMm", "bore_diameter_mm"),
        "targetDockingConnectorDiameterMm": ("connectorDiameterMm", "connector_diameter_mm"),
        "targetDockingConnectorThicknessMm": ("connectorThicknessMm", "connector_thickness_mm"),
        "targetDockingSharedDepthMm": ("sharedDepthMm", "shared_depth_mm"),
        "targetDockingIndividualDepthsEnabled": ("individualDepthsEnabled", "individual_depths_enabled"),
        "targetDockingYawDeg": ("yawDeg", "yaw_deg"),
        "targetDockingCollisionClearanceMm": ("collisionClearanceMm", "collision_clearance_mm"),
        "templateDockingClearanceMm": ("clearanceMm", "clearance_mm"),
        "templateReinforcementRadialMm": ("reinforcementRadialMm", "reinforcement_radial_mm"),
        "templateSamplingSpacingMm": ("processingResolutionMm", "processing_resolution_mm"),
    }
    # Validate the complete saved recipe before mutating any editor value.
    arguments = {argument: saved[key] for key, argument in fields.values()}
    arguments["individual_depths_mm"] = saved["configuredIndividualDepthsMm"]
    normalized = normalize(**arguments)
    if normalized != saved:
        raise ValueError("Selected docking assembly parameters are inconsistent.")
    values = {field: normalized[key] for field, (key, _) in fields.items()}
    values.update({"targetDockingDepth%dMm" % (index + 1): value
                   for index, value in enumerate(normalized["configuredIndividualDepthsMm"])})
    values["targetDockingYawConfirmed"] = summary["orientationState"] == "Confirmed"
    cleared = set(plan["clearParameters"])
    for field, value in values.items():
        if field not in cleared:
            setattr(parameter, field, value)


def _legacy_projection_provenance(workflow):
    """Use the source's validated registry frame for an independent prefix."""
    from DENTOStep6State import REGISTRY_PROVENANCE_FRAME_KEY

    registry = workflow["step6"]["trajectoryRegistry"]
    if not isinstance(registry, dict):
        raise ValueError("Saved trajectory registry is malformed.")
    return REGISTRY_PROVENANCE_FRAME_KEY not in registry


def _replan_restored_projection(source, inspection, digest, source_stat,
                                saved_inventory, actual_inventory, actual_mapping,
                                target, checkpoint, branch):
    """Use the complete restored ownership contract for every destructive step."""
    from dentobot_case.inspection import inventory_from_inspection
    from dentobot_case.projection import prepare_projection

    if not actual_inventory["ownershipComplete"]:
        raise ValueError("Restored ownership audit failed: " + "; ".join(actual_inventory["unknownOwnership"]))
    saved_mapping = saved_inventory.metadata["projection"]
    if actual_mapping["parameterNodeId"] != saved_mapping["parameterNodeId"]:
        raise ValueError("Restored parameter node differs from the saved audit.")
    if saved_inventory.ownership_complete and any(
            actual_mapping["nodeOwners"].get(node_id) != owners
            for node_id, owners in saved_mapping["nodeOwners"].items()):
        raise ValueError("Restored persistent ownership differs from the saved audit.")
    extra = set(actual_mapping["nodeOwners"]) - set(saved_mapping["nodeOwners"])
    if any(actual_mapping["nodeOwners"][node_id] != ["@display"] for node_id in extra):
        raise ValueError("Restore introduced unaudited persistent geometry or state.")

    audited_workflow = dict(inspection.workflow)
    audited_workflow["checkpointInventory"] = actual_inventory
    audited_workflow["projectionOwnership"] = actual_mapping
    inventory = inventory_from_inspection(
        source, replace(inspection, workflow=audited_workflow), digest, source_stat,
    )
    plan = prepare_projection(inventory, target, checkpoint, branch)
    return inventory, actual_mapping, plan


def _projector_evidence_root():
    configured = os.environ.get("DENTOCASE_EVIDENCE_DIR")
    run_root = os.environ.get("CRUN") or os.environ.get("DENTOBOT_RUN_DIR")
    if configured:
        return Path(configured)
    if run_root:
        return Path(run_root) / "evidence"
    now = datetime.now(timezone.utc)
    archive_root = Path("/workspace/data/dentobot-runs")
    if not archive_root.is_dir():
        archive_root = Path("/home/tarun/dentobot/data/dentobot-runs")
    if not archive_root.is_dir():
        raise RuntimeError("Configure DENTOCASE_EVIDENCE_DIR or CRUN within the dated run archive.")
    return archive_root / now.strftime("%Y-%m-%d") / (
        "DCP-PROJECTION-" + now.strftime("%Y%m%dT%H%M%SZ")
    ) / "evidence"


def _new_projector_evidence_dir():
    evidence_dir = _projector_evidence_root() / ("projector-" + uuid4().hex)
    evidence_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(evidence_dir, 0o700)
    return evidence_dir


def retain_failed_partial_load(package_path, error):
    """Preserve a completed child package when parent hydration rejects it."""
    evidence_dir = _new_projector_evidence_dir()
    retained = evidence_dir / "parent-rejected.dentocase"
    staging = evidence_dir / "parent-rejected.dentocase.tmp"
    digest = hashlib.sha256()
    try:
        with staging.open("xb") as target, Path(package_path).open("rb") as source:
            os.chmod(staging, 0o600)
            for block in iter(lambda: source.read(1024 * 1024), b""):
                target.write(block)
                digest.update(block)
            target.flush()
            os.fsync(target.fileno())
        os.replace(staging, retained)
    finally:
        staging.unlink(missing_ok=True)
    status = evidence_dir / "parent-load-failure.json"
    cause = error.__cause__
    status.write_text(json.dumps({
        "schemaVersion": "1.0",
        "packageName": retained.name,
        "packageSha256": digest.hexdigest(),
        "exceptionType": type(error).__name__,
        "causeType": type(cause).__name__ if cause is not None else "",
    }, indent=2, sort_keys=True) + "\n")
    os.chmod(status, 0o600)
    return retained


def _retain_failed_projected_scene(scene_path, evidence_dir, *, save_complete):
    """Keep a private MRB only after saveScene reported completion."""
    scene_path = Path(scene_path) if scene_path is not None else None
    if not save_complete or scene_path is None or not scene_path.is_file():
        return None
    retained = Path(evidence_dir) / "projected.mrb"
    staging = Path(evidence_dir) / "projected.mrb.tmp"
    try:
        with staging.open("xb") as target:
            os.chmod(staging, 0o600)
            with scene_path.open("rb") as source:
                shutil.copyfileobj(source, target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(staging, retained)
    finally:
        staging.unlink(missing_ok=True)
    return retained


@contextmanager
def _offline_child_workspace(temporary_root, evidence_dir, save_state):
    """Copy a completed failed projection while its scratch MRB still exists."""
    with tempfile.TemporaryDirectory(prefix="dentocase-offline-", dir=temporary_root) as directory:
        try:
            yield Path(directory)
        except Exception:
            try:
                retained = _retain_failed_projected_scene(
                    save_state["path"], evidence_dir, save_complete=save_state["complete"],
                )
                if retained is not None:
                    print("DENTOCASE_PRIVATE_PROJECTED_MRB", retained, flush=True)
            except Exception as copy_error:
                print("Projected MRB retention failed:", copy_error, flush=True)
            raise


def _retain_projector_log(log_path, *, exit_code, temporary_dir, output_path,
                          source_sha256, failure="", evidence_dir=None):
    """Keep the full child diagnostic before its disposable directory closes."""
    evidence_dir = Path(evidence_dir) if evidence_dir is not None else _new_projector_evidence_dir()
    retained_log = evidence_dir / "process.log"
    with retained_log.open("wb") as target:
        os.chmod(retained_log, 0o600)
        with Path(log_path).open("rb") as source:
            shutil.copyfileobj(source, target)
    with retained_log.open(errors="replace") as source:
        phases = [line.rstrip("\n") for line in source if line.startswith("DENTOCASE_PROJECTOR_")]
    saved_scene = evidence_dir / "projected.mrb"
    save_complete = any(
        line.startswith("DENTOCASE_PROJECTOR_PHASE save_scene_complete ") for line in phases
    )
    scene_retention_error = ""
    if save_complete and not saved_scene.is_file() and (exit_code or failure):
        candidates = list(Path(temporary_dir).glob("dentocase-offline-*/projected.mrb"))
        if len(candidates) == 1:
            try:
                _retain_failed_projected_scene(candidates[0], evidence_dir, save_complete=True)
            except Exception as exc:
                scene_retention_error = type(exc).__name__
    scene_retained = saved_scene.is_file() and save_complete
    scene_sha256 = ""
    if scene_retained:
        digest = hashlib.sha256()
        with saved_scene.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        scene_sha256 = digest.hexdigest()
    ownership_report = evidence_dir / "post-save-ownership.json"
    metadata = {
        "schemaVersion": "1.0",
        "exitCode": exit_code,
        "failure": failure,
        "childTemporaryDirectoryName": Path(temporary_dir).name,
        "childOutputName": Path(output_path).name,
        "childOutputExists": Path(output_path).is_file(),
        "sourceSha256": source_sha256,
        "phases": phases,
        "lastPhase": phases[-1] if phases else "",
        "logName": retained_log.name,
        "projectedMrbName": saved_scene.name if scene_retained else "",
        "projectedMrbSha256": scene_sha256,
        "projectedMrbRetentionError": scene_retention_error,
        "ownershipReportName": ownership_report.name if ownership_report.is_file() else "",
    }
    metadata_path = evidence_dir / "status.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    os.chmod(metadata_path, 0o600)
    return retained_log, metadata


def _check_projector_result(retained_log, status):
    if status["failure"] or status["exitCode"] or not status["childOutputExists"]:
        raise RuntimeError("Offline projection failed; full child diagnostic: " + str(retained_log))


def _log_projected_unknown_ownership(inventory, *, stream=None):
    """Expose bounded exact audit reasons only in the private child log."""
    reasons = inventory["unknownOwnership"]
    limit = 128
    print("DENTOCASE_PRIVATE_POST_SAVE_OWNERSHIP " + json.dumps({
        "count": len(reasons),
        "reasons": reasons[:limit],
        "omitted": max(0, len(reasons) - limit),
    }, ensure_ascii=False), file=stream, flush=True)


def _record_projected_ownership_failure(inventory, projection, plan, source_sha256, evidence_dir):
    """Preserve the full failed audit without copying clinical scene geometry."""
    path = Path(evidence_dir) / "post-save-ownership.json"
    report = {
        "schemaVersion": "1.0",
        "sourceSha256": source_sha256,
        "unknownOwnership": inventory["unknownOwnership"],
        "capturedNodeOwners": projection["nodeOwners"],
        "plan": {
            "targetId": plan["targetId"],
            "branchId": plan["branchId"],
            "checkpointId": plan["checkpointId"],
            "keepNodeIds": plan["keepNodeIds"],
            "removeNodeIds": plan["removeNodeIds"],
            "clearParameters": plan["clearParameters"],
            "clearReferenceRoles": plan["clearReferenceRoles"],
        },
    }
    with path.open("x") as output:
        os.chmod(path, 0o600)
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    return path


def _inspect_prefix(source, destination, target, checkpoint, branch):
    from dentobot_case.inspection import inspect_package
    from dentobot_case.projection import prepare_projection
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or (destination.exists() and os.path.samefile(source, destination)):
        raise ValueError("Partial Save As requires a destination distinct from the source.")
    inventory = inspect_package(source)
    if inventory.ownership_complete and inventory.archive_schema != "3.0":
        prepare_projection(inventory, target, checkpoint, branch)
    elif (inventory.archive_schema != "3.0" or not isinstance(inventory.metadata.get("projection"), dict)):
        raise ValueError("Saved ownership cannot be re-audited for this package schema.")
    # An incomplete schema-3 save can only be projected after the disposable
    # Slicer process restores and re-audits its exact saved scene. No selection
    # or deletion uses the old incomplete map.
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

    started = time.monotonic()
    def phase(name):
        print("DENTOCASE_PROJECTION_PHASE", name, f"{time.monotonic() - started:.6f}", flush=True)
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
        phase("source_verification")
        with tempfile.TemporaryDirectory(prefix="dentocase-project-", dir=slicer.app.temporaryPath) as directory:
            directory = Path(directory)
            evidence_dir = _new_projector_evidence_dir()
            request = directory / "request.json"
            output = directory / "result.dentocase"
            request.write_text(json.dumps({"source": str(source), "destination": str(output),
                "target": target, "checkpoint": checkpoint, "branch": branch,
                "sourceSha256": inventory.package_sha256,
                "diagnosticDir": str(evidence_dir),
                "workspaceRoot": str(directory)}))
            script = directory / "run.py"
            script.write_text("import sys\nsys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1])) +
                ")\nfrom dentobot_workflow.case_projection import run_offline\nrun_offline(" + repr(str(request)) + ")\n")
            progress.update("Offline projection and fresh reopen", can_cancel=False)
            child_log = directory / "process.log"
            with child_log.open("w") as log:
                environment = dict(os.environ)
                environment["ROS_DOMAIN_ID"] = "232"
                print("DENTOCASE_PROJECTOR_LAUNCH", f"{time.monotonic():.6f}", flush=True)
                process = None
                failure = ""
                try:
                    process = subprocess.Popen([str(slicer.app.launcherExecutableFilePath), "--no-splash",
                        "--no-main-window", "--disable-cli-modules", "--python-code",
                        "exec(open(" + repr(str(script)) + ").read())"],
                        env=environment, stdout=log, stderr=log)
                    deadline = time.monotonic() + 180
                    while process.poll() is None:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Offline case projection exceeded 180 seconds.")
                        slicer.app.processEvents()
                        time.sleep(0.03)
                except Exception as exc:
                    failure = type(exc).__name__
                    print("Projector parent error:", exc, file=log, flush=True)
                finally:
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                log.flush()
            retained_log, child_status = _retain_projector_log(
                child_log, exit_code=process.returncode if process is not None else None,
                temporary_dir=directory, output_path=output,
                source_sha256=inventory.package_sha256, failure=failure,
                evidence_dir=evidence_dir,
            )
            _check_projector_result(retained_log, child_status)
            for line in child_log.read_text(errors="replace").splitlines():
                if line.startswith("DENTOCASE_PROJECTOR_"):
                    print(line, flush=True)
            phase("projector_complete")
            progress.update("Validating and releasing the independent package", can_cancel=False)
            result = wait_io(executor.submit(_release_projection, output, source, destination, inventory))
            phase("release_complete")
            return result
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        progress.close()


def run_offline(request_path):
    """Entry called only in the disposable Slicer process."""
    import slicer
    from DENTOCaseBundle import create_case_bundle, extract_scene_mrb, sha256_file
    from dentobot_case.inspection import inventory_from_inspection
    from dentobot_case.projection import prepare_projection, filter_registry
    from dentobot_case.contracts import CHECKPOINTS
    from .case_inventory import capture_inventory
    from .parameter_state import DENTOWorkflowParameterNode
    import importlib.util
    import sys

    started = time.monotonic()
    save_state = {"path": None, "complete": False}
    print("DENTOCASE_PROJECTOR_READY", f"{started:.6f}", flush=True)
    def phase(name):
        print("DENTOCASE_PROJECTOR_PHASE", name, f"{time.monotonic() - started:.6f}", flush=True)
    try:
        request = json.loads(Path(request_path).read_text())
        diagnostic_dir = Path(request["diagnosticDir"])
        with _offline_child_workspace(request["workspaceRoot"], diagnostic_dir, save_state) as directory:
            source = Path(request["source"])
            signature = source.stat()
            scene_path, inspection = extract_scene_mrb(source, directory)
            digest = sha256_file(source)
            after = source.stat()
            if (signature.st_dev, signature.st_ino, signature.st_size, signature.st_mtime_ns, signature.st_ctime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("Source changed during projection preparation.")
            if digest != request["sourceSha256"]:
                raise ValueError("Source changed after selection.")
            inventory = inventory_from_inspection(source, inspection, digest, after)
            if inventory.ownership_complete and inventory.archive_schema != "3.0":
                prepare_projection(inventory, request["target"], request["checkpoint"], request["branch"])
            phase("source_preparation")
            if not slicer.util.loadScene(str(scene_path), {"clear": True}):
                raise ValueError("Source MRB could not be restored.")
            phase("source_restore")
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
            inventory, mapping, plan = _replan_restored_projection(
                source, inspection, digest, after, inventory, actual_inventory, actual_mapping,
                request["target"], request["checkpoint"], request["branch"],
            )
            phase("restored_audit_complete")
            from dentobot_case.ownership import LEGACY_PARAMETER_OWNERS
            for name in plan["clearParameters"]:
                if name in LEGACY_PARAMETER_OWNERS:
                    raw.UnsetParameter(name)
                    continue
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
            for node_id in plan["keepNodeIds"]:
                _clear_future_node_attributes(nodes[node_id], order)
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
            from DENTOGuideGeometry import normalize_target_docking_parameters
            _restore_selected_docking_parameters(
                parameter, logic, plan, normalize_target_docking_parameters)
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
            # Schema-3 always carries a Case Foundation snapshot. Build it only
            # after the selected prefix has cleared Step 6 authority, so it is
            # derived from the projected scene instead of the source payload.
            logic.buildDentoCaseRobotEnvironment(parameter)
            # Validation above audited the saved registry under its recorded
            # provenance. Keep that provenance while constructing a prefix:
            # an ordinary sync would migrate a legacy branch after pruning,
            # changing its revision while leaving the saved Step 5C evidence.
            summary = logic.caseBundleWorkflowSummary(
                parameter, legacyProvenance=_legacy_projection_provenance(inspection.workflow),
            )
            summary["caseIdentity"] = {"id": plan["newCaseId"]}
            phase("projection")
            projected_scene = Path(directory) / "projected.mrb"
            save_state["path"] = projected_scene
            phase("save_scene_begin")
            if not slicer.util.saveScene(str(projected_scene)):
                raise ValueError("Projected MRB could not be saved.")
            save_state["complete"] = True
            phase("save_scene_complete")
            # As with ordinary saves, include storage nodes created by saving.
            phase("post_save_inventory_begin")
            summary["checkpointInventory"], summary["projectionOwnership"] = capture_inventory(parameter, slicer.mrmlScene, summary)
            if not summary["checkpointInventory"]["ownershipComplete"]:
                _log_projected_unknown_ownership(summary["checkpointInventory"])
                report_path = _record_projected_ownership_failure(
                    summary["checkpointInventory"], summary["projectionOwnership"],
                    plan, inventory.package_sha256, diagnostic_dir,
                )
                print("DENTOCASE_PRIVATE_POST_SAVE_REPORT", report_path, flush=True)
                raise ValueError("Projected ownership is incomplete.")
            phase("post_save_inventory_complete")
            phase("bundle_create_begin")
            create_case_bundle(request["destination"], projected_scene, case_label=parameter.caseName,
                workflow=summary, robot_profile=inspection.robot_profile,
                application=inspection.manifest.get("application", {}), case_id=plan["newCaseId"])
            phase("bundle_create_complete")
            phase("projected_save")
            # A fresh reopen, before releasing the output, validates reconstructed lineage.
            phase("fresh_reopen_begin")
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
            phase("fresh_reopen")
        slicer.util.exit(0)
    except Exception as exc:
        import traceback
        traceback.print_exception(type(exc), exc, exc.__traceback__)
        slicer.util.exit(1)
