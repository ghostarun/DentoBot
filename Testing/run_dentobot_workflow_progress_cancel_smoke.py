"""Focused Slicer check for long-action cancel and commit checkpoints."""

import sys

import qt
import slicer

sys.path.insert(0, "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow/Resources/Python")
from dentobot_workflow.workflow_progress import WorkflowCancelled, WorkflowProgress


def run():
    status = 0
    try:
        progress = WorkflowProgress("Cancel smoke")
        try:
            progress.dialog.cancel()
            try:
                progress.update("next safe checkpoint")
            except WorkflowCancelled:
                print("PROGRESS_CANCEL_PASS", flush=True)
            else:
                raise AssertionError("Cancel did not stop at the next checkpoint")
        finally:
            progress.close()
        commit = WorkflowProgress("Commit smoke")
        try:
            commit.update("Scene commit", can_cancel=False)
            assert not commit.dialog.wasCanceled
            print("PROGRESS_COMMIT_PASS", flush=True)
        finally:
            commit.close()
    except Exception as exc:
        status = 1
        print("PROGRESS_SMOKE_FAIL", type(exc).__name__, str(exc), flush=True)
    slicer.util.exit(status)


qt.QTimer.singleShot(0, run)
