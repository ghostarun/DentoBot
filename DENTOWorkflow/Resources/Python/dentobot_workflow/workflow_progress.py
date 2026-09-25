"""Visible, truthful progress for synchronous Slicer workflow actions."""

import logging
import time

import qt
import slicer

from .ui_stall_watchdog import note_ui_phase


class WorkflowCancelled(RuntimeError):
    """Operator cancelled between completed computation checkpoints."""


class WorkflowProgress:
    def __init__(self, title):
        self.title = title
        self.started = time.monotonic()
        self.dialog = qt.QProgressDialog(title, "Cancel", 0, 0, slicer.util.mainWindow())
        self.dialog.setWindowModality(qt.Qt.WindowModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.show()
        self.update("Starting")

    def update(self, phase, done=None, total=None, *, can_cancel=True):
        if self.dialog.wasCanceled:
            raise WorkflowCancelled(f"{self.title} cancelled after the last completed checkpoint.")
        if not can_cancel:
            self.dialog.setCancelButton(None)
        elapsed = int(time.monotonic() - self.started)
        count = f" ({done}/{total})" if done is not None and total else ""
        message = f"{self.title}: {phase}{count} · {elapsed}s elapsed"
        note_ui_phase(f"{self.title}: {phase}", done, total)
        self.dialog.setLabelText(message)
        logging.info("Workflow progress: %s", message)
        print("DENTOBOT_WORKFLOW_PROGRESS", message, flush=True)
        slicer.app.processEvents()
        if can_cancel and self.dialog.wasCanceled:
            raise WorkflowCancelled(f"{self.title} cancelled after the last completed checkpoint.")

    def close(self):
        self.dialog.close()
