from types import SimpleNamespace

import pytest

import Testing.step6_expected_error_dialog as dialog_probe
from Testing.step6_expected_error_dialog import make_expected_error_dialog_callback


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self, callback):
        self.callbacks.remove(callback)

    def emit(self):
        for callback in tuple(self.callbacks):
            callback()


class _Timer:
    def __init__(self):
        self.timeout = _Signal()
        self.active = False
        self.interval_ms = None

    def start(self, interval_ms):
        self.interval_ms = interval_ms
        self.active = True

    def stop(self):
        self.active = False

    def tick(self):
        if self.active:
            self.timeout.emit()


class _Dialog:
    def __init__(self, text, on_dismiss, *, callable_text=False):
        self.visible = True
        self.reject_count = 0
        self.close_count = 0
        self.accept_count = 0
        self.on_dismiss = on_dismiss
        if callable_text:
            self.text = lambda: text
        else:
            self.text = text

    def isVisible(self):
        return self.visible

    def reject(self):
        self.reject_count += 1
        self.visible = False
        self.on_dismiss()

    def close(self):
        self.close_count += 1
        self.visible = False
        self.on_dismiss()

    def accept(self):
        self.accept_count += 1
        raise AssertionError("the callback must never approve a modal")


class _Button:
    def __init__(self, on_click):
        self.on_click = on_click
        self.click_count = 0

    def click(self):
        self.click_count += 1
        self.on_click()


def _timer_factory():
    timers = []

    def create():
        timer = _Timer()
        timers.append(timer)
        return timer

    return SimpleNamespace(QTimer=create), timers


def _finish(timer):
    assert timer.active is False
    assert timer.timeout.callbacks == []


def test_expected_modal_is_captured_before_reject_after_one_button_click():
    qt, timers = _timer_factory()
    current = {"dialog": None}
    dialog = _Dialog(
        "Base commit acknowledgement lost",
        lambda: current.update(dialog=None),
        callable_text=True,
    )
    captures = []

    def capture(stage):
        assert current["dialog"] is dialog
        assert dialog.visible
        captures.append(stage)
        return "screenshot://base-error"

    button = _Button(lambda: (current.update(dialog=dialog), timers[0].tick()))
    callback = make_expected_error_dialog_callback(
        qt, lambda: current["dialog"], capture
    )

    result = callback(button, "Base commit acknowledgement lost", "base-unknown")

    assert button.click_count == 1
    assert captures == ["base-unknown"]
    assert result == {
        "button_clicked": True,
        "dialog_captured": True,
        "dialog_dismissed": True,
        "dialog_text": "Base commit acknowledgement lost",
        "capture": "screenshot://base-error",
        "capture_reference": "screenshot://base-error",
    }
    assert dialog.reject_count == 1 and dialog.close_count == 0
    assert dialog.accept_count == 0
    _finish(timers[0])


def test_six_second_backend_delay_is_within_explicit_180_second_budget(monkeypatch):
    qt, timers = _timer_factory()
    current = {"dialog": None}
    clock = {"now": 0.0}
    monkeypatch.setattr(dialog_probe.time, "monotonic", lambda: clock["now"])
    dialog = _Dialog("Base commit acknowledgement lost", lambda: current.update(dialog=None))
    captures = []

    def click():
        # Model a slow backend after the click; the former 5 s budget timed out here.
        clock["now"] = 6.0
        current["dialog"] = dialog
        timers[0].tick()

    callback = make_expected_error_dialog_callback(
        qt,
        lambda: current["dialog"],
        lambda stage: captures.append(stage) or "screenshot://delayed-base-error",
        timeout_sec=180.0,
    )
    button = _Button(click)

    result = callback(button, "Base commit acknowledgement lost", "base-unknown")

    assert button.click_count == 1
    assert captures == ["base-unknown"]
    assert result["dialog_captured"] is True
    assert result["dialog_dismissed"] is True
    assert result["capture_reference"] == "screenshot://delayed-base-error"
    assert dialog.reject_count == 1 and dialog.accept_count == 0
    _finish(timers[0])


def test_missing_modal_fails_and_cleans_timer():
    qt, timers = _timer_factory()
    button = _Button(lambda: None)
    callback = make_expected_error_dialog_callback(qt, lambda: None, lambda _stage: "shot")

    with pytest.raises(RuntimeError, match="without an observed active modal"):
        callback(button, "expected error", "missing")

    assert button.click_count == 1
    _finish(timers[0])


def test_timeout_then_late_modal_is_captured_rejected_and_still_fails(monkeypatch):
    qt, timers = _timer_factory()
    current = {"dialog": None}
    clock = {"now": 0.0}
    monkeypatch.setattr(dialog_probe.time, "monotonic", lambda: clock["now"])
    captures = []
    dialog = _Dialog("expected error", lambda: current.update(dialog=None))

    def click():
        clock["now"] = 2.0
        timers[0].tick()  # timeout while no modal is active
        current["dialog"] = dialog
        timers[0].tick()  # late modal is rejected but cannot become a pass

    button = _Button(click)
    callback = make_expected_error_dialog_callback(
        qt,
        lambda: current["dialog"],
        lambda stage: captures.append(stage) or "screenshot://late",
        timeout_sec=1.0,
    )

    with pytest.raises(TimeoutError, match="before the dialog timeout"):
        callback(button, "expected error", "late")

    assert button.click_count == 1
    assert captures == ["late-late-modal"]
    assert dialog.reject_count == 1 and dialog.accept_count == 0
    _finish(timers[0])


def test_unexpected_modal_is_captured_then_rejected_and_raises():
    qt, timers = _timer_factory()
    current = {"dialog": None}
    dialog = _Dialog("Confirm unrelated operation?", lambda: current.update(dialog=None))
    captures = []

    def click():
        current["dialog"] = dialog
        timers[0].tick()

    callback = make_expected_error_dialog_callback(
        qt,
        lambda: current["dialog"],
        lambda stage: captures.append(stage) or "screenshot://unexpected",
    )
    button = _Button(click)

    with pytest.raises(RuntimeError, match="Unexpected modal text"):
        callback(button, "expected error", "action")

    assert button.click_count == 1
    assert captures == ["action-unexpected-modal"]
    assert dialog.reject_count == 1 and dialog.accept_count == 0
    _finish(timers[0])


def test_capture_failure_rejects_modal_and_fails_closed():
    qt, timers = _timer_factory()
    current = {"dialog": None}
    dialog = _Dialog("expected error", lambda: current.update(dialog=None))

    def click():
        current["dialog"] = dialog
        timers[0].tick()

    callback = make_expected_error_dialog_callback(
        qt,
        lambda: current["dialog"],
        lambda _stage: {},
    )
    button = _Button(click)

    with pytest.raises(RuntimeError, match="Expected modal capture failed"):
        callback(button, "expected error", "capture-failure")

    assert button.click_count == 1
    assert dialog.reject_count == 1 and dialog.accept_count == 0
    _finish(timers[0])


def test_original_button_exception_is_preserved_and_timer_is_cleaned():
    qt, timers = _timer_factory()
    failure = LookupError("original button exception")
    button = _Button(lambda: (_ for _ in ()).throw(failure))
    callback = make_expected_error_dialog_callback(qt, lambda: None, lambda _stage: "shot")

    with pytest.raises(LookupError, match="original button exception") as caught:
        callback(button, "expected error", "button-error")

    assert caught.value is failure
    assert button.click_count == 1
    _finish(timers[0])
