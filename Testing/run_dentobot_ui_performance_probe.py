"""Read-only input case, in-memory Step 5B/4C timing and UI watchdog probe."""

import faulthandler
import cProfile
import io
import json
import os
import sys
import time
import traceback
import pstats

import numpy as np
import qt
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")

CASE = os.environ.get(
    "DENTOBOT_PERF_CASE",
    "/workspace/data/Slicer_Saved/SampleStudy1/FDI21-31-headless-verified-sep22-step6a.dentocase",
)


def run():
    os.environ["DENTOBOT_UI_WATCHDOG_DISABLE"] = "1"  # This probe owns faulthandler's one global timer.
    stack_log = open("/tmp/dentobot-ui-performance-stacks.log", "w")
    faulthandler.dump_traceback_later(30, repeat=True, file=stack_log)
    heartbeats = []
    heartbeat = qt.QTimer()
    heartbeat.setInterval(1000)
    def heartbeat_tick():
        now = time.monotonic()
        heartbeats.append(now)
        print("PERF_HEARTBEAT", now, flush=True)
    heartbeat.connect("timeout()", heartbeat_tick)
    heartbeat.start()
    status = 0
    try:
        slicer.util.selectModule("DENTOWorkflow")
        widget = slicer.util.getModuleWidget("DENTOWorkflow")
        load_only = os.environ.get("DENTOBOT_PERF_LOAD_ONLY") == "1"
        if load_only:
            from dentobot_workflow.workflow_progress import WorkflowProgress
            progress = WorkflowProgress("Opening DENTOBOT case")
        else:
            progress = None
        start = time.monotonic()
        print("PERF_BEGIN load", start, flush=True)
        try:
            if os.environ.get("DENTOBOT_PERF_SCENE_ONLY") == "1":
                from pathlib import Path
                from DENTOCaseBundle import extract_scene_mrb
                scene, _ = extract_scene_mrb(CASE, Path(slicer.app.temporaryPath) / "perf-scene-only")
                assert slicer.util.loadScene(str(scene), {"clear": True})
                assert widget._parameterNode is not None
            else:
                widget._openCaseBundle(CASE, progress=progress)
        finally:
            if progress:
                progress.close()
        print("PERF_END load", time.monotonic() - start, flush=True)
        if os.environ.get("DENTOBOT_PERF_COMPARE_MASKS") == "1":
            segmentation = widget._parameterNode.teethSegmentation
            reference = segmentation.GetNodeReference(
                slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole()
            )
            reference_matrix = vtk.vtkMatrix4x4()
            reference.GetIJKToRASMatrix(reference_matrix)
            reference_extent = reference.GetImageData().GetExtent()
            for review in widget.logic.getSegmentationReviewRecords(segmentation):
                segment_id = str(review.get("segmentId") or "")
                if not segment_id:
                    continue
                internal = segmentation.GetBinaryLabelmapInternalRepresentation(segment_id)
                matrix = vtk.vtkMatrix4x4()
                internal.GetImageToWorldMatrix(matrix)
                extent = internal.GetExtent()
                aligned = all(
                    abs(matrix.GetElement(row, column) - reference_matrix.GetElement(row, column)) < 1e-8
                    for row in range(4) for column in range(4)
                ) and all(reference_extent[index] <= extent[index] and extent[index + 1] <= reference_extent[index + 1]
                          for index in (0, 2, 4))
                if not aligned:
                    print("PERF_MASK_UNALIGNED", segment_id, extent, reference_extent,
                          tuple(matrix.GetElement(i, j) - reference_matrix.GetElement(i, j)
                                for i in range(4) for j in range(4)), flush=True)
                    continue
                internal_array = vtk_to_numpy(internal.GetPointData().GetScalars()).reshape(
                    tuple(reversed(internal.GetDimensions()))
                )
                label = segmentation.GetSegmentation().GetSegment(segment_id).GetLabelValue()
                reference_dtype = vtk_to_numpy(reference.GetImageData().GetPointData().GetScalars()).dtype
                candidate = np.zeros(tuple(reversed(reference.GetImageData().GetDimensions())), dtype=reference_dtype)
                slices = tuple(slice(extent[index] - reference_extent[index], extent[index + 1] - reference_extent[index] + 1)
                               for index in (4, 2, 0))
                candidate[slices] = internal_array == label
                original = slicer.util.arrayFromSegmentBinaryLabelmap(segmentation, segment_id)
                equal = candidate.dtype == original.dtype and np.array_equal(candidate, original)
                print("PERF_MASK_COMPARE", segment_id, label, equal, candidate.shape, original.shape,
                      str(candidate.dtype), str(original.dtype), int(np.count_nonzero(candidate)),
                      int(np.count_nonzero(original)),
                      int(np.count_nonzero(candidate != original)),
                      np.unique(original).tolist(), flush=True)
                assert equal
            print("PERF_MASK_COMPARE_PASS", flush=True)
            print("PERF_PROBE_COMPLETE", flush=True)
            return
        if load_only:
            action_heartbeats = [value for value in heartbeats if value >= start]
            maximum_gap = max((right - left for left, right in zip(action_heartbeats, action_heartbeats[1:])), default=0)
            print("PERF_LOAD_MAX_HEARTBEAT_GAP", maximum_gap, flush=True)
            print("PERF_PROBE_COMPLETE", flush=True)
            return
        if os.environ.get("DENTOBOT_PERF_ENTRY_SETUP") == "1":
            parameter = widget._parameterNode
            segmentation = parameter.teethSegmentation
            segment_id = segmentation.GetSegmentation().GetSegmentIdBySegmentName(
                "upper_right_central_incisor_fdi11"
            )
            assert segment_id
            parameter.targetToothSegmentId = segment_id
            parameter.assistedTrajectoryCount = 1
            assert not widget.logic.dentobotTrajectoriesForTarget(segmentation, segment_id)
            action_started = time.monotonic()
            print("PERF_BEGIN step4a_entry_setup", action_started, flush=True)
            widget.onPlaceAssistedTrajectoryEntries()
            print("PERF_END step4a_entry_setup", time.monotonic() - action_started, flush=True)
            assert widget.logic.isAssistedTrajectoryEntryNode(parameter.assistedTrajectoryEntries)
            action_heartbeats = [value for value in heartbeats if value >= action_started]
            maximum_gap = max((right - left for left, right in zip(action_heartbeats, action_heartbeats[1:])), default=0)
            print("PERF_ACTION_MAX_HEARTBEAT_GAP", maximum_gap, flush=True)
            print("PERF_PROBE_COMPLETE", flush=True)
            return
        if os.environ.get("DENTOBOT_PERF_STEP4A") == "1":
            from dentobot_workflow.workflow_progress import WorkflowProgress
            progress_events = []
            original_update = WorkflowProgress.update
            def record_progress(self, phase, *args, **kwargs):
                progress_events.append(phase)
                return original_update(self, phase, *args, **kwargs)
            WorkflowProgress.update = record_progress
            parameter = widget._parameterNode
            segmentation = parameter.teethSegmentation
            segment_id = parameter.targetToothSegmentId
            old_lines = list(widget.logic.dentobotTrajectoriesForTarget(segmentation, segment_id))
            print("PERF_4A_INPUT", segment_id, len(old_lines), flush=True)
            if not old_lines:
                raise RuntimeError("The selected target has no trajectory Entry to reuse.")
            count = min(2, len(old_lines))
            entries = [widget.logic.getTrajectorySummary(line)["entryRas"] for line in old_lines[:count]]
            for line in old_lines:
                slicer.mrmlScene.RemoveNode(line)
            parameter.targetToothSegmentId = segment_id
            segmentation = parameter.teethSegmentation
            entry_node, _ = widget.logic.createOrResetAssistedTrajectoryEntries(segmentation, segment_id, count)
            for entry in entries:
                entry_node.AddControlPointWorld(vtk.vtkVector3d(*entry))
            parameter.assistedTrajectoryEntries = entry_node
            parameter.assistedTrajectoryCount = count
            widget.logic.validateAssistedTrajectoryEntryAssociation(entry_node, segmentation, segment_id, count)
            slicer.util.infoDisplay = lambda *args, **kwargs: print("PERF_4A_INFO", flush=True)
            slicer.util.errorDisplay = lambda message, *args, **kwargs: print("PERF_4A_ERROR", message, flush=True)
            action_started = time.monotonic()
            print("PERF_BEGIN step4a_gui", action_started, flush=True)
            widget.onGenerateAssistedTrajectories()
            print("PERF_END step4a_gui", time.monotonic() - action_started, flush=True)
            new_lines = widget.logic.dentobotTrajectoriesForTarget(segmentation, segment_id)
            print("PERF_4A_RESULT", len(new_lines), len(progress_events), flush=True)
            assert len(new_lines) == count and len(progress_events) >= 4
            action_heartbeats = [value for value in heartbeats if value >= action_started]
            maximum_gap = max((right - left for left, right in zip(action_heartbeats, action_heartbeats[1:])), default=0)
            print("PERF_ACTION_MAX_HEARTBEAT_GAP", maximum_gap, flush=True)
            assert maximum_gap < 7
            print("PERF_PROBE_COMPLETE", flush=True)
            return
        if os.environ.get("DENTOBOT_PERF_GUI") == "1":
            from dentobot_workflow.workflow_progress import WorkflowProgress
            progress_events = []
            original_update = WorkflowProgress.update
            def record_progress(self, phase, *args, **kwargs):
                progress_events.append((self.title, phase))
                return original_update(self, phase, *args, **kwargs)
            WorkflowProgress.update = record_progress
            if os.environ.get("DENTOBOT_PERF_FULL5B") == "1":
                widget._parameterNode.templateUndercutBlockoutModel = None
                widget._parameterNode.patientContactShellModel = None
            widget._parameterNode.finalPrintableTemplateModel = None
            action_started = time.monotonic()
            for name, action in (
                ("step5b_gui", widget.onBuildOrUpdateCompleteTemplate),
                ("step4c_gui", widget.onGenerateTargetDockingAssembly),
            ):
                start = time.monotonic()
                print("PERF_BEGIN", name, start, flush=True)
                action()
                print("PERF_END", name, time.monotonic() - start, flush=True)
            print("PERF_PROGRESS_COUNTS", json.dumps({
                title: sum(event_title == title for event_title, _ in progress_events)
                for title, _ in progress_events
            }), flush=True)
            assert sum("Step 5B" in title for title, _ in progress_events) >= 15
            assert sum("Step 4C" in title for title, _ in progress_events) >= 15
            action_heartbeats = [value for value in heartbeats if value >= action_started]
            maximum_gap = max((right - left for left, right in zip(action_heartbeats, action_heartbeats[1:])), default=0)
            print("PERF_ACTION_MAX_HEARTBEAT_GAP", maximum_gap, flush=True)
            assert maximum_gap < 7
            print("PERF_PROBE_COMPLETE", flush=True)
            return
        for name, action in (
            ("step5b_preflight", widget._completeTemplateBuildPreflight),
            ("step5b_unified", widget._createOrUpdateFinalPrintableTemplate),
            ("step4c_dock", lambda: widget._regenerateTargetDocking(autoSelectYaw=True)),
        ):
            start = time.monotonic()
            print("PERF_BEGIN", name, start, flush=True)
            profiler = cProfile.Profile()
            try:
                result = profiler.runcall(action)
                print("PERF_END", name, time.monotonic() - start, flush=True)
                if name == "step5b_unified":
                    print("PERF_RESULT", name, json.dumps(result[2]["fusion"]), flush=True)
            except Exception as exc:
                print("PERF_SKIP", name, time.monotonic() - start, type(exc).__name__, str(exc), flush=True)
                traceback.print_exc()
            finally:
                report = io.StringIO()
                pstats.Stats(profiler, stream=report).sort_stats("cumulative").print_stats(12)
                print("PERF_PROFILE", name, report.getvalue(), flush=True)
        print("PERF_PROBE_COMPLETE", flush=True)
    except Exception as exc:
        status = 1
        print("PERF_PROBE_FAIL", type(exc).__name__, str(exc), flush=True)
        traceback.print_exc()
    finally:
        heartbeat.stop()
        faulthandler.cancel_dump_traceback_later()
        stack_log.close()
        slicer.util.exit(status)


qt.QTimer.singleShot(0, run)
