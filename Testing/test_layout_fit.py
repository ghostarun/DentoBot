"""Host checks for the narrow-dock fit policy (DENTOLayoutFit).

Pure dock/dialog/reflow arithmetic runs everywhere.  The layout scenarios run
real Qt widgets offscreen through PyQt5 behind a tiny ``qt`` shim and are skipped
when PyQt5 is unavailable.  They prove the generic pass removes the width
overflow of a representative panel; they do not replace a headed Slicer check.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "DENTOWorkflow" / "Resources" / "Python" / "DENTOLayoutFit.py"


def _load_layout_fit(shim):
    previous = sys.modules.get("qt")
    sys.modules["qt"] = shim
    try:
        spec = importlib.util.spec_from_file_location("_dento_layout_fit_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("qt", None)
        else:
            sys.modules["qt"] = previous


def _pyqt_shim():
    pytest.importorskip("PyQt5")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5 import QtCore, QtGui, QtWidgets

    shim = types.ModuleType("qt")
    for source in (QtCore, QtGui, QtWidgets):
        for name in dir(source):
            if not name.startswith("_"):
                setattr(shim, name, getattr(source, name))
    return shim


_APP = None  # keep the QApplication alive for the whole test process


@pytest.fixture(scope="module")
def fit():
    global _APP
    shim = _pyqt_shim()
    module = _load_layout_fit(shim)
    _APP = shim.QApplication.instance() or shim.QApplication([])
    return module, shim


# ---- pure arithmetic -------------------------------------------------------


@pytest.fixture(scope="module")
def pure():
    return _load_layout_fit(None)  # sys.modules["qt"] = None -> ImportError path


@pytest.mark.parametrize(
    "logical_width, expected",
    [(1366, 340), (1920, 461), (2560, 520), (3840 / 1.5, 520), (3840 / 2, 461), (800, 340)],
)
def test_default_dock_width_is_screen_relative_and_clamped(pure, logical_width, expected):
    assert pure.defaultDockWidth(logical_width) == expected


def test_saved_dock_fraction_survives_monitor_changes(pure):
    assert pure.dockWidthFromFraction(0.30, 1920) == 576
    # A width saved on a large screen cannot swallow a small laptop screen.
    assert pure.dockWidthFromFraction(0.45, 1366) <= int(1366 * 0.6)
    assert pure.dockWidthFromFraction(0.9, 3840) == 620
    assert pure.dockWidthFromFraction(0.30, 800) >= pure.DOCK_MIN_WIDTH_PX


@pytest.mark.parametrize("bad", [None, "", "abc", 0, -1, 0.01, 2.0, float("nan")])
def test_unusable_saved_dock_fraction_falls_back_to_default(pure, bad):
    assert pure.dockWidthFromFraction(bad, 1920) == pure.defaultDockWidth(1920)


def test_dock_width_fraction_round_trip(pure):
    fraction = pure.dockWidthToFraction(461, 1920)
    assert pure.dockWidthFromFraction(fraction, 1920) == 461
    assert pure.dockWidthToFraction(100, 0) == 0.0


def test_dialog_is_capped_to_ninety_percent_of_screen(pure):
    assert pure.dialogSizeForScreen(1100, 700, 1366, 768) == (1100, 691)
    assert pure.dialogSizeForScreen(1100, 700, 1000, 600) == (900, 540)
    assert pure.dialogSizeForScreen(300, 200, 1920, 1080) == (300, 200)


def test_reflow_has_hysteresis_against_flapping(pure):
    assert pure.reflowDecision(False, 400, 399) is True
    assert pure.reflowDecision(False, 400, 400) is False
    # Once stacked, widening to exactly the natural width is not enough.
    assert pure.reflowDecision(True, 400, 400) is True
    assert pure.reflowDecision(True, 400, 400 + pure.REFLOW_HYSTERESIS_PX) is False


def test_caption_wrap_breaks_on_words_and_keeps_existing_breaks(pure):
    measure = lambda text: len(text) * 7  # 7 px per character
    text = "Allow spindle-guide contact in step 4C for the selected tooth"
    wrapped = pure.wrapCaption(text, 140, measure)  # 20 characters per line
    assert "\n" in wrapped and wrapped.replace("\n", " ") == text
    assert all(measure(line) <= 140 for line in wrapped.split("\n"))
    assert pure.wrapCaption("short", 140, measure) == "short"
    assert pure.wrapCaption("first line\nsecond line", 400, measure) == "first line\nsecond line"
    # A single word wider than the limit stays whole instead of looping forever.
    assert pure.wrapCaption("supercalifragilisticexpialidocious", 50, measure) == (
        "supercalifragilisticexpialidocious"
    )


def test_kill_switch(pure, monkeypatch):
    monkeypatch.delenv(pure.FIT_ENV, raising=False)
    assert pure.fitEnabled()
    for value in ("0", "false", "No", "OFF"):
        monkeypatch.setenv(pure.FIT_ENV, value)
        assert not pure.fitEnabled()


# ---- offscreen Qt layout scenarios ----------------------------------------

LONG_NOTE = (
    "Accept & Validate stays unavailable until the draft has been applied and "
    "the monitored robot state matches the accepted joints."
)


def _panel(shim, *, extra_min_label=None):
    """A representative narrow-hostile page inside a vertical-only scroll area."""
    scroll = shim.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(shim.Qt.ScrollBarAlwaysOff)
    content = shim.QWidget()
    outer = shim.QVBoxLayout(content)

    note = shim.QLabel(LONG_NOTE)  # not word-wrapped: width = one long line
    outer.addWidget(note)

    row = shim.QHBoxLayout()
    for caption in ("Plan + Apply Home Draft", "Accept & Validate", "Re-review draft"):
        row.addWidget(shim.QPushButton(caption))
    row.addStretch(1)
    outer.addLayout(row)

    form = shim.QFormLayout()
    form.addRow("Linear step (mm)", shim.QLineEdit())
    form.addRow("Rotation step (deg)", shim.QLineEdit())
    outer.addLayout(form)

    combo = shim.QComboBox()
    combo.addItem("6.3 Manual / Workspace / Plan with a very long title")
    outer.addWidget(combo)

    if extra_min_label:
        wide = shim.QLabel("intentional fixed value column")
        wide.setMinimumWidth(extra_min_label)
        outer.addWidget(wide)
    scroll.setWidget(content)
    return scroll, content, row, form


def _settle(shim, scroll, width, height=600):
    scroll.resize(width, height)
    scroll.show()
    for _ in range(3):
        shim.QApplication.instance().processEvents()


def _overflow(scroll, content) -> int:
    return content.width() - scroll.viewport().width()


def test_generic_pass_removes_width_overflow_at_the_minimum_width(fit):
    module, shim = fit
    scroll, content, row, form = _panel(shim)
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    assert _overflow(scroll, content) > 0, "fixture must overflow before the pass"

    controller = module.NarrowFitController(content)
    assert controller.apply() > 0
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)

    assert _overflow(scroll, content) == 0
    assert row.direction() == shim.QBoxLayout.TopToBottom  # stacked buttons
    assert form.rowWrapPolicy() == shim.QFormLayout.WrapLongRows
    assert module.findWidthOffenders(content, module.MIN_FIT_WIDTH_PX - 20) == []
    scroll.close()


def test_rows_return_to_one_line_when_the_dock_is_widened(fit):
    module, shim = fit
    scroll, content, row, _form = _panel(shim)
    controller = module.NarrowFitController(content)
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    controller.apply()
    assert row.direction() == shim.QBoxLayout.TopToBottom
    stretch = next(
        row.itemAt(i).spacerItem() for i in range(row.count()) if row.itemAt(i).spacerItem()
    )
    # While stacked, the row's stretch must not claim vertical or horizontal space.
    assert int(stretch.expandingDirections()) == 0

    _settle(shim, scroll, 900)
    controller.reflow()
    assert row.direction() == shim.QBoxLayout.LeftToRight
    # The stretch is restored, not left neutralised.
    assert int(stretch.expandingDirections()) & int(shim.Qt.Horizontal)
    scroll.close()


def test_resize_event_triggers_reflow(fit):
    module, shim = fit
    scroll, content, row, _form = _panel(shim)
    controller = module.NarrowFitController(content)
    controller.apply()
    controller.installResizeReflow()
    _settle(shim, scroll, 900)
    controller.reflow()
    assert row.direction() == shim.QBoxLayout.LeftToRight

    scroll.resize(module.MIN_FIT_WIDTH_PX, 600)
    from PyQt5.QtTest import QTest

    QTest.qWait(30)
    assert row.direction() == shim.QBoxLayout.TopToBottom
    scroll.close()


def _checkbox_page(shim):
    scroll = shim.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(shim.Qt.ScrollBarAlwaysOff)
    content = shim.QWidget()
    layout = shim.QVBoxLayout(content)
    caption = "Allow the spindle to contact the guide while planning the 4C approach path"
    box = shim.QCheckBox(caption)
    layout.addWidget(box)
    scroll.setWidget(content)
    return scroll, content, box, caption


def test_long_checkbox_captions_wrap_instead_of_overflowing(fit):
    module, shim = fit
    scroll, content, box, caption = _checkbox_page(shim)
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    assert _overflow(scroll, content) > 0, "a long caption must overflow before the pass"

    controller = module.NarrowFitController(content)
    controller.apply()
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    assert _overflow(scroll, content) == 0
    assert "\n" in box.text()
    assert box.text().replace("\n", " ") == caption  # nothing lost, only wrapped

    _settle(shim, scroll, 1400)  # wide dock: back to one line
    controller.reflow()
    assert box.text() == caption
    scroll.close()


def test_caption_changed_by_other_code_is_wrapped_again(fit):
    module, shim = fit
    scroll, content, box, _caption = _checkbox_page(shim)
    controller = module.NarrowFitController(content)
    controller.apply()
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    box.setText("A completely different and equally long caption set by workflow code")
    controller.reflow()
    assert "\n" in box.text()
    assert box.text().replace("\n", " ").startswith("A completely different")
    scroll.close()


def test_reflow_after_the_content_is_destroyed_does_not_raise(fit):
    module, shim = fit
    scroll, content, _row, _form = _panel(shim)
    controller = module.NarrowFitController(content)
    controller.apply()
    import sip

    scroll.close()
    sip.delete(content)
    controller.reflow()  # shutdown order seen in Slicer: must be silent
    assert controller._content is None


def test_opt_out_properties_keep_chrome_untouched(fit):
    module, shim = fit
    scroll, content, row, _form = _panel(shim)
    row.setProperty(module.NO_REFLOW_PROPERTY, True)
    note = content.layout().itemAt(0).widget()
    note.setProperty(module.NO_FIT_PROPERTY, True)
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    module.NarrowFitController(content).apply()
    assert row.direction() == shim.QBoxLayout.LeftToRight  # never stacked
    assert not note.wordWrap()  # label left as the caller built it
    scroll.close()


def test_pass_is_idempotent_and_marks_widgets(fit):
    module, shim = fit
    _scroll, content, _row, _form = _panel(shim)
    controller = module.NarrowFitController(content)
    assert controller.apply() > 0
    assert controller.apply() == 0  # nothing new to process


def test_new_widgets_added_later_are_fitted(fit):
    module, shim = fit
    scroll, content, _row, _form = _panel(shim)
    controller = module.NarrowFitController(content)
    controller.apply()
    late = shim.QLabel(LONG_NOTE)  # e.g. the lazily built robot panel
    content.layout().addWidget(late)
    assert controller.apply() > 0
    assert late.wordWrap()
    scroll.close()


def test_explicit_minimums_are_reported_not_silently_changed(fit):
    module, shim = fit
    scroll, content, _row, _form = _panel(shim, extra_min_label=500)
    controller = module.NarrowFitController(content)
    controller.apply()
    offenders = module.findWidthOffenders(content, module.MIN_FIT_WIDTH_PX)
    assert [item["explicit_min"] for item in offenders] == [500]
    scroll.close()


def test_offender_audit_skips_hidden_widgets(fit):
    module, shim = fit
    scroll, content, _row, _form = _panel(shim, extra_min_label=500)
    hidden = shim.QLabel("hidden but wide")
    hidden.setMinimumWidth(700)
    content.layout().addWidget(hidden)
    module.NarrowFitController(content).apply()
    _settle(shim, scroll, module.MIN_FIT_WIDTH_PX)
    hidden.hide()
    shown = module.findWidthOffenders(content, module.MIN_FIT_WIDTH_PX, visible_within=content)
    assert [item["explicit_min"] for item in shown] == [500]
    assert "parent" in shown[0] and shown[0]["class"] == "QLabel"
    assert shown[0]["leaf"] is True
    scroll.close()


def test_kill_switch_leaves_the_page_untouched(fit, monkeypatch):
    module, shim = fit
    monkeypatch.setenv(module.FIT_ENV, "0")
    scroll, content, row, _form = _panel(shim)
    controller = module.NarrowFitController(content)
    assert controller.apply() == 0
    assert row.direction() == shim.QBoxLayout.LeftToRight
    scroll.close()


# ---- wiring pins (shell/widget need Slicer; pin the source contracts) ------

PYTHON = ROOT / "DENTOWorkflow" / "Resources" / "Python"


def _source(relative: str) -> str:
    return (PYTHON / relative).read_text(encoding="utf-8")


def test_task_dock_uses_screen_relative_bounds_not_fixed_pixels():
    shell = _source("DENTOApplicationShell.py")
    assert "setMinimumWidth(390)" not in shell
    assert "setMaximumWidth(620)" not in shell
    assert "setMinimumWidth(DOCK_MIN_WIDTH_PX)" in shell
    assert "setMaximumWidth(DOCK_USER_MAX_WIDTH_PX)" in shell
    # Width is persisted as a screen fraction and re-applied after the dock is shown.
    assert "TASK_DOCK_WIDTH_FRACTION_SETTING" in shell
    assert "self._apply_task_dock_width()" in shell
    assert "screenChanged(QScreen*)" in shell


def test_fit_pass_is_hooked_for_setup_stage_changes_and_resizes():
    application = _source("dentobot_workflow/widget_application.py")
    bootstrap = _source("dentobot_workflow/widget_bootstrap.py")
    navigation = _source("dentobot_workflow/widget_navigation.py")
    assert "NarrowFitController(contentWidget)" in application
    assert "self._applyNarrowFit(installResizeReflow=True)" in bootstrap
    assert "self._applyNarrowFit()" in navigation
    # The inner scroll area stays vertical-only; the fit pass does not rely on it.
    assert "horizontalScrollBarPolicy = qt.Qt.ScrollBarAlwaysOff" in application


def test_fit_module_avoids_pythonqt_property_assignment_and_window_flags():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "setWindowFlags" not in source
    assert "showPopup" not in source
    # Method-style Qt only, so one implementation runs under PythonQt and PyQt5.
    for forbidden in (".visible =", ".text =", ".enabled =", ".checked ="):
        assert forbidden not in source


def test_layout_fit_module_is_installed_with_the_module():
    cmake = (ROOT / "DENTOWorkflow" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "Resources/Python/DENTOLayoutFit.py" in cmake
