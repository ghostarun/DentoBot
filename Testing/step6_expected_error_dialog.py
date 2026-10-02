"""Capture and dismiss the real modal raised by a headed GUI action."""

from __future__ import annotations

import math
import time


def _value(obj, name, default=None):
    value = getattr(obj, name, default)
    return value() if callable(value) else value


def _dialog_text(dialog):
    parts = []
    for name in ("text", "informativeText", "detailedText"):
        value = _value(dialog, name, "")
        if value:
            parts.append(str(value))
    if not parts:
        title = _value(dialog, "windowTitle", "")
        if title:
            parts.append(str(title))
    return "\n".join(parts)


def _has_capture(reference):
    if reference is None:
        return False
    try:
        return bool(reference)
    except (TypeError, ValueError):
        return True


def _dismiss(dialog, active_modal_widget):
    reject = getattr(dialog, "reject", None)
    close = getattr(dialog, "close", None)
    error = None
    for dismiss in (reject, close):
        if not callable(dismiss):
            continue
        try:
            dismiss()
            break
        except Exception as exc:
            error = exc
    else:
        raise RuntimeError("The modal has no safe reject/close operation.") from error

    if callable(close) and _value(dialog, "isVisible", True):
        close()
    current = active_modal_widget()
    if current is dialog or _value(dialog, "isVisible", False):
        raise RuntimeError("The modal remained open after reject/close.")


def make_expected_error_dialog_callback(
    qt, active_modal_widget, capture_callback, timeout_sec=5.0
):
    """Return a callback that verifies, captures, then rejects the real modal.

    ``active_modal_widget`` is the Qt active-modal getter. ``capture_callback``
    receives the supplied capture stage and must return a non-empty reference.
    """
    try:
        timeout_sec = float(timeout_sec)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("timeout_sec must be a finite positive number") from exc
    if not math.isfinite(timeout_sec) or timeout_sec <= 0:
        raise ValueError("timeout_sec must be a finite positive number")

    def active():
        return active_modal_widget() if callable(active_modal_widget) else active_modal_widget

    def callback(button, expected_text, capture_stage):
        expected_text = str(expected_text or "")
        if not expected_text:
            raise ValueError("expected_text must be non-empty")

        existing = active()
        if existing is not None:
            capture_error = None
            try:
                reference = capture_callback(str(capture_stage) + "-unexpected-existing-modal")
                if not _has_capture(reference):
                    capture_error = RuntimeError("Screenshot capture returned no reference.")
            except Exception as exc:
                capture_error = exc
            finally:
                _dismiss(existing, active)
            if capture_error is not None:
                raise RuntimeError("Unexpected existing modal capture failed: " + str(capture_error))
            raise RuntimeError("An unexpected modal was already active before the button click.")

        state = {"result": None, "failure": None, "handled": False}
        deadline = time.monotonic() + timeout_sec
        timer = qt.QTimer()
        signal = timer.timeout

        def poll():
            if state["handled"]:
                return
            try:
                dialog = active()
                expired = time.monotonic() >= deadline
                if dialog is None:
                    if state["failure"] is None and expired:
                        state["failure"] = TimeoutError(
                            "No active modal appeared before the dialog timeout."
                        )
                    return

                if state["failure"] is None and expired:
                    state["failure"] = TimeoutError(
                        "The active modal appeared after the dialog timeout."
                    )
                if state["failure"] is not None:
                    state["handled"] = True
                    try:
                        reference = capture_callback(str(capture_stage) + "-late-modal")
                        if not _has_capture(reference):
                            raise RuntimeError("Screenshot capture returned no reference.")
                    except Exception:
                        pass
                    try:
                        _dismiss(dialog, active)
                    except Exception:
                        pass
                    return

                text = _dialog_text(dialog)
                if expected_text not in text:
                    state["handled"] = True
                    try:
                        reference = capture_callback(str(capture_stage) + "-unexpected-modal")
                        if not _has_capture(reference):
                            raise RuntimeError("Screenshot capture returned no reference.")
                    except Exception as exc:
                        state["failure"] = RuntimeError(
                            "Unexpected modal capture failed: " + str(exc)
                        )
                    try:
                        _dismiss(dialog, active)
                    except Exception as exc:
                        state["failure"] = RuntimeError(
                            "Unexpected modal could not be safely dismissed: " + str(exc)
                        )
                    if state["failure"] is None:
                        state["failure"] = RuntimeError(
                            "Unexpected modal text: " + (text or "<empty>")
                        )
                    return

                state["handled"] = True
                try:
                    reference = capture_callback(capture_stage)
                    if not _has_capture(reference):
                        raise RuntimeError("Screenshot capture returned no reference.")
                except Exception as exc:
                    state["failure"] = RuntimeError("Expected modal capture failed: " + str(exc))
                    try:
                        _dismiss(dialog, active)
                    except Exception as dismiss_exc:
                        state["failure"] = RuntimeError(
                            str(state["failure"]) + "; modal dismissal failed: " + str(dismiss_exc)
                        )
                    return

                try:
                    _dismiss(dialog, active)
                except Exception as exc:
                    state["failure"] = RuntimeError(
                        "Expected modal could not be safely dismissed: " + str(exc)
                    )
                    return
                state["result"] = {
                    "button_clicked": True,
                    "dialog_captured": True,
                    "dialog_dismissed": True,
                    "dialog_text": text,
                    "capture": reference,
                    "capture_reference": reference,
                }
            except Exception as exc:
                state["failure"] = exc

        connected = False
        click_error = None
        click_traceback = None
        cleanup_errors = []
        try:
            signal.connect(poll)
            connected = True
            timer.start(25)
            button.click()
        except BaseException as exc:
            click_error = exc
            click_traceback = exc.__traceback__
        finally:
            try:
                timer.stop()
            except Exception as exc:
                cleanup_errors.append(exc)
            if connected:
                try:
                    signal.disconnect(poll)
                except Exception as exc:
                    cleanup_errors.append(exc)

        if click_error is not None:
            raise click_error.with_traceback(click_traceback)
        if cleanup_errors:
            raise RuntimeError("Dialog timer cleanup failed: " + "; ".join(map(str, cleanup_errors)))
        if state["failure"] is not None:
            raise state["failure"]
        if state["result"] is None:
            raise RuntimeError("The button click returned without an observed active modal.")
        return state["result"]

    return callback


class UnexpectedModalError(RuntimeError):
    """A production action raised a modal the headed run did not expect."""

    def __init__(self, text, capture_reference=None):
        self.dialog_text = text
        self.capture_reference = capture_reference
        super().__init__("Unexpected modal during headed action: " + (text or "<empty>"))


def _is_progress_dialog(qt, dialog):
    """Production progress dialogs are modal but are not failures."""
    progress_class = getattr(qt, "QProgressDialog", None)
    if isinstance(progress_class, type):
        try:
            if isinstance(dialog, progress_class):
                return True
        except TypeError:
            pass
    return callable(getattr(dialog, "wasCanceled", None))


def make_modal_watchdog_click(qt, active_modal_widget, capture_callback):
    """Return ``click(button, capture_stage)`` that never blocks on a modal.

    Any modal opened while the click runs is captured, dismissed (reject/close,
    never accepted) and reported by raising ``UnexpectedModalError`` after the
    click returns. A click that opens no modal returns ``None``; modal progress dialogs are
    ignored, never captured or dismissed. A modal already
    open before the click is captured, dismissed and also raises.
    """

    def active():
        return active_modal_widget() if callable(active_modal_widget) else active_modal_widget

    def capture(stage):
        try:
            reference = capture_callback(stage)
            return reference if _has_capture(reference) else None
        except Exception:
            return None

    def click(button, capture_stage):
        existing = active()
        if existing is not None and not _is_progress_dialog(qt, existing):
            text = _dialog_text(existing)
            reference = capture(str(capture_stage) + "-pre-existing-modal")
            _dismiss(existing, active)
            raise UnexpectedModalError(text, reference)

        state = {"text": None, "reference": None, "failure": None}
        timer = qt.QTimer()
        signal = timer.timeout

        def poll():
            if state["text"] is not None or state["failure"] is not None:
                return
            try:
                dialog = active()
                if dialog is None or _is_progress_dialog(qt, dialog):
                    return
                state["text"] = _dialog_text(dialog) or "<empty>"
                state["reference"] = capture(str(capture_stage) + "-unexpected-modal")
                _dismiss(dialog, active)
            except Exception as exc:
                state["failure"] = exc

        connected = False
        click_error = None
        try:
            signal.connect(poll)
            connected = True
            timer.start(25)
            button.click()
        except BaseException as exc:
            click_error = exc
        finally:
            timer.stop()
            if connected:
                signal.disconnect(poll)
        if click_error is not None:
            raise click_error
        if state["failure"] is not None:
            raise RuntimeError("Unexpected modal could not be handled: " + str(state["failure"]))
        if state["text"] is not None:
            raise UnexpectedModalError(state["text"], state["reference"])
        return None

    return click
