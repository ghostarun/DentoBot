"""Visible, truthful progress for synchronous Slicer workflow actions."""

import logging
import time

import qt
import slicer

from .ui_stall_watchdog import begin_ui_action, end_ui_action, note_ui_phase


class WorkflowCancelled(RuntimeError):
    """Operator cancelled between completed computation checkpoints."""


class WorkflowProgress:
    def __init__(self, title):
        self.title = title
        self.started = time.monotonic()
        self.dialog = None
        self._closed = False
        self._cancelled = False
        self.action_token = begin_ui_action(title)
        try:
            self.dialog = qt.QProgressDialog(title, "Cancel", 0, 0, slicer.util.mainWindow())
            self.dialog.setWindowModality(qt.Qt.WindowModal)
            self.dialog.setMinimumDuration(0)
            self.dialog.show()
            self.update("Starting")
        except Exception:
            self.close("error")
            raise

    def update(self, phase, done=None, total=None, *, can_cancel=True):
        if self._closed:
            return
        try:
            if self.dialog.wasCanceled:
                self._cancelled = True
                raise WorkflowCancelled(
                    f"{self.title} cancelled after the last completed checkpoint."
                )
            if not can_cancel:
                self.dialog.setCancelButton(None)
            elapsed = int(time.monotonic() - self.started)
            count = f" ({done}/{total})" if done is not None and total else ""
            message = f"{self.title}: {phase}{count} · {elapsed}s elapsed"
            note_ui_phase(f"{self.title}: {phase}", done, total, token=self.action_token)
            self.dialog.setLabelText(message)
            logging.info("Workflow progress: %s", message)
            print("DENTOBOT_WORKFLOW_PROGRESS", message, flush=True)
            slicer.app.processEvents()
            if can_cancel and self.dialog.wasCanceled:
                self._cancelled = True
                raise WorkflowCancelled(
                    f"{self.title} cancelled after the last completed checkpoint."
                )
        except WorkflowCancelled:
            self.close("cancelled")
            raise
        except Exception:
            self.close("error")
            raise

    def close(self, outcome="closed"):
        if self._closed:
            return
        self._closed = True
        if self._cancelled and outcome == "closed":
            outcome = "cancelled"
        try:
            if self.dialog is not None:
                self.dialog.close()
        finally:
            end_ui_action(self.action_token, outcome)
