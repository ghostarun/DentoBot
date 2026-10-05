"""Narrow-dock fit policy shared by the legacy module panel and the shell.

Contract: every workflow page reflows from ``MIN_FIT_WIDTH_PX`` upward and never
needs a horizontal scrollbar; only the page body scrolls, vertically.

Qt only lets a widget shrink below its size hint when it has an explicit
positive minimum width (or an Ignored policy), so the generic pass caps
hint-driven minimums with a small floor instead of changing size policies.
Wide horizontal rows flip to a vertical stack while their natural width does
not fit.  Widgets whose *explicit* minimum is wider than the available width
(intentional per-panel sizes) are not touched; ``findWidthOffenders`` lists
them so they can be fixed per panel.

Qt calls are method-style only (no PythonQt property assignment) so the same
code runs under Slicer's PythonQt and the PyQt5 host tests.
"""

from __future__ import annotations

import os

try:  # Slicer provides ``qt``; pure host tests import only the helpers.
    import qt
except ImportError:  # pragma: no cover - exercised by host tests
    qt = None


MIN_FIT_WIDTH_PX = 340
DOCK_MIN_WIDTH_PX = 340
DOCK_DEFAULT_MAX_WIDTH_PX = 520
DOCK_USER_MAX_WIDTH_PX = 620
DOCK_SCREEN_FRACTION = 0.24
NARROW_BREAKPOINT_PX = 430
REFLOW_HYSTERESIS_PX = 8
WIDGET_MIN_FLOOR_PX = 48
LABEL_MIN_FLOOR_PX = 40
FIT_ENV = "DENTOBOT_NARROW_FIT"
_FIT_MARK = "dentobotFitApplied"
NO_FIT_PROPERTY = "dentobotNoFit"  # widget: leave wrapping/minimum alone
NO_REFLOW_PROPERTY = "dentobotNoReflow"  # layout: never stack this row
_FULL_TEXT_KEY = "dentobotFullCaption"
_WRAPPED_TEXT_KEY = "dentobotWrappedCaption"
CAPTION_WRAP_MIN_CHARS = 24
CAPTION_RIGHT_MARGIN_PX = 12
CAPTION_INDICATOR_PX = 24
CAPTION_MIN_WIDTH_PX = 120


def fitEnabled() -> bool:
    """Kill switch for live sessions: ``DENTOBOT_NARROW_FIT=0`` disables the pass."""
    return os.environ.get(FIT_ENV, "1").strip().lower() not in {"0", "false", "no", "off"}


def defaultDockWidth(logical_screen_width: float) -> int:
    """Default task-dock width: 24 % of the logical screen width, clamped."""
    width = round(float(logical_screen_width) * DOCK_SCREEN_FRACTION)
    return int(max(DOCK_MIN_WIDTH_PX, min(DOCK_DEFAULT_MAX_WIDTH_PX, width)))


def dockWidthToFraction(width_px: float, logical_screen_width: float) -> float:
    if logical_screen_width <= 0:
        return 0.0
    return max(0.0, min(1.0, float(width_px) / float(logical_screen_width)))


def dockWidthFromFraction(fraction, logical_screen_width: float) -> int:
    """Restore a saved dock width (stored as a screen fraction) for this screen.

    An unusable saved value falls back to the default.  The result never leaves
    ``[DOCK_MIN_WIDTH_PX, DOCK_USER_MAX_WIDTH_PX]`` and never exceeds 60 % of
    the screen, so a width saved on a large monitor cannot swallow a laptop.
    """
    try:
        value = float(fraction)
    except (TypeError, ValueError):
        return defaultDockWidth(logical_screen_width)
    if not 0.05 <= value <= 0.9:
        return defaultDockWidth(logical_screen_width)
    width = round(value * float(logical_screen_width))
    ceiling = min(DOCK_USER_MAX_WIDTH_PX, int(float(logical_screen_width) * 0.6))
    return int(max(DOCK_MIN_WIDTH_PX, min(max(DOCK_MIN_WIDTH_PX, ceiling), width)))


def dialogSizeForScreen(
    preferred_w: int, preferred_h: int, available_w: int, available_h: int
) -> tuple[int, int]:
    """Size a dialog to its preferred size but at most 90 % of the screen."""
    return (
        int(max(1, min(preferred_w, available_w * 0.9))),
        int(max(1, min(preferred_h, available_h * 0.9))),
    )


def wrapCaption(text: str, max_width_px: float, measure) -> str:
    """Break ``text`` into lines no wider than ``max_width_px`` (word wrap).

    ``measure`` returns a string's pixel width.  Existing line breaks are kept;
    a single word wider than the limit stays whole.  Checkbox/radio captions
    render ``\\n`` as a real line break, so this wraps them without any
    layout surgery.
    """
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = word if not line else f"{line} {word}"
            if line and measure(candidate) > max_width_px:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return "\n".join(lines)


def reflowDecision(
    stacked: bool, natural_width: int, available_width: int
) -> bool:
    """Return the new stacked state for a row (hysteresis against flapping)."""
    if stacked:
        return not (available_width >= natural_width + REFLOW_HYSTERESIS_PX)
    return natural_width > available_width


# ---------------------------------------------------------------------------
# Qt helpers (method-style calls only)
# ---------------------------------------------------------------------------


def logicalScreenWidth(widget=None) -> int:
    """Logical (device-independent) available width of the widget's screen."""
    screen = None
    try:
        screen = widget.screen() if widget is not None else None
    except (AttributeError, RuntimeError):
        screen = None
    if screen is None:
        screen = qt.QApplication.primaryScreen()
        screen = _val(screen) if screen is not None else None
    if screen is None:
        return 1920
    geometry = _val(screen.availableGeometry)
    return int(_val(geometry.width)) or 1920


def resizeDockWidth(main_window, dock, width_px: int) -> None:
    """Set a docked widget's width (resizeDocks is the only reliable way)."""
    main_window.resizeDocks([dock], [int(width_px)], qt.Qt.Horizontal)


def _widgets(root) -> list:
    try:
        return list(root.findChildren("QWidget"))
    except TypeError:  # PyQt5 takes a type, PythonQt a class name
        return list(root.findChildren(qt.QWidget))


def _layouts(root) -> list:
    try:
        return list(root.findChildren("QLayout"))
    except TypeError:
        return list(root.findChildren(qt.QLayout))


def _val(attribute):
    """PythonQt exposes some Qt members as properties, PyQt5 as methods."""
    return attribute() if callable(attribute) else attribute


qtValue = _val  # public alias for callers outside this module


def _className(widget) -> str:
    return type(widget).__name__


def _layoutItems(layout) -> list:
    return [layout.itemAt(i) for i in range(int(_val(layout.count)))]


def _explicitMinWidth(widget) -> int:
    return int(_val(widget.minimumWidth))


def _hintWidth(widget) -> int:
    return int(_val(_val(widget.sizeHint).width))


def _minHintWidth(widget) -> int:
    return int(_val(_val(widget.minimumSizeHint).width))


def _isFixedWidth(widget) -> bool:
    minimum = _explicitMinWidth(widget)
    return minimum > 0 and minimum == int(_val(widget.maximumWidth))


def _capMinimum(widget, floor: int) -> bool:
    """Let a hint-driven minimum shrink to ``floor``; leave explicit minimums."""
    if _explicitMinWidth(widget) > 0 or _isFixedWidth(widget):
        return False
    if _minHintWidth(widget) <= floor:
        return False
    widget.setMinimumWidth(floor)
    return True


def _fitWidget(widget) -> bool:
    if widget.property(NO_FIT_PROPERTY):
        return False
    if widget.inherits("QLabel"):
        text = _val(widget.text)
        if not str(text or "").strip():
            return False
        widget.setWordWrap(True)
        return _capMinimum(widget, LABEL_MIN_FLOOR_PX)
    if widget.inherits("QAbstractButton") and not (
        widget.inherits("QCheckBox") or widget.inherits("QRadioButton")
    ):
        # Long captions are clipped, not wrapped, below the floor; the full text
        # stays reachable through the tooltip.
        text = _val(widget.text)
        tip = _val(widget.toolTip)
        if text and not tip:
            widget.setToolTip(str(text))
        return _capMinimum(widget, WIDGET_MIN_FLOOR_PX)
    if widget.inherits("QComboBox"):
        widget.setSizeAdjustPolicy(qt.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(8)
        return _capMinimum(widget, WIDGET_MIN_FLOOR_PX)
    if widget.inherits("QAbstractSpinBox") or widget.inherits("QLineEdit"):
        return _capMinimum(widget, WIDGET_MIN_FLOOR_PX)
    if widget.inherits("qMRMLNodeComboBox"):
        return _capMinimum(widget, WIDGET_MIN_FLOOR_PX)
    return False


def _wrapsCaption(widget) -> bool:
    """Long checkbox/radio captions wrap; everything else is handled elsewhere."""
    if widget.property(NO_FIT_PROPERTY):
        return False
    if not (widget.inherits("QCheckBox") or widget.inherits("QRadioButton")):
        return False
    return len(str(_val(widget.text))) >= CAPTION_WRAP_MIN_CHARS


def _fitLayout(layout) -> bool:
    if layout.inherits("QFormLayout"):
        layout.setRowWrapPolicy(qt.QFormLayout.WrapLongRows)
        layout.setFieldGrowthPolicy(qt.QFormLayout.AllNonFixedFieldsGrow)
        return True
    return False


class _ReflowRow:
    """One horizontal row that stacks vertically while it does not fit."""

    def __init__(self, layout, natural_width: int, spacers: list) -> None:
        self.layout = layout
        self.natural_width = natural_width
        self.spacers = spacers  # [(item, w, h, hPolicy, vPolicy)]
        self.stacked = False

    def setStacked(self, stacked: bool) -> None:
        if stacked == self.stacked:
            return
        self.stacked = stacked
        self.layout.setDirection(
            qt.QBoxLayout.TopToBottom if stacked else qt.QBoxLayout.LeftToRight
        )
        for item, w, h, hp, vp in self.spacers:
            if stacked:
                item.changeSize(0, 0, qt.QSizePolicy.Minimum, qt.QSizePolicy.Minimum)
            else:
                item.changeSize(w, h, hp, vp)
        self.layout.invalidate()


def _registerRow(layout):
    """Return a _ReflowRow for a horizontal row worth flipping, else None."""
    if not layout.inherits("QHBoxLayout") or layout.property(NO_REFLOW_PROPERTY):
        return None
    widgets, spacers = [], []
    for item in _layoutItems(layout):
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            widgets.append(widget)
        elif item.spacerItem() is not None:
            spacer = item.spacerItem()
            if not hasattr(spacer, "changeSize"):
                return None  # cannot neutralise the spacer when stacked
            size = _val(spacer.sizeHint)
            policy = _val(spacer.sizePolicy)
            spacers.append(
                (
                    spacer,
                    int(_val(size.width)),
                    int(_val(size.height)),
                    _val(policy.horizontalPolicy),
                    _val(policy.verticalPolicy),
                )
            )
        else:
            return None  # nested layouts keep their own structure
    if len(widgets) < 2:
        return None
    spacing = max(0, int(_val(layout.spacing)))
    natural = sum(_hintWidth(w) for w in widgets) + spacing * (len(widgets) - 1)
    return _ReflowRow(layout, natural, spacers)


class NarrowFitController:
    """Applies the fit pass to a content widget and reflows rows on resize."""

    def __init__(self, content_widget) -> None:
        self._content = content_widget
        self._rows: list[_ReflowRow] = []
        self._captions: list = []
        self._filter = None
        self._busy = False

    def apply(self) -> int:
        """Idempotently fit every not-yet-processed descendant; returns count."""
        if not fitEnabled() or self._content is None:
            return 0
        changed = 0
        for widget in _widgets(self._content):
            if widget.property(_FIT_MARK):
                continue
            widget.setProperty(_FIT_MARK, True)
            if _fitWidget(widget):
                changed += 1
            if _wrapsCaption(widget):
                self._captions.append(widget)
                changed += 1
        for layout in _layouts(self._content):
            if layout.property(_FIT_MARK):
                continue
            layout.setProperty(_FIT_MARK, True)
            if _fitLayout(layout):
                changed += 1
            row = _registerRow(layout)
            if row is not None:
                self._rows.append(row)
        self.reflow()
        return changed

    def available_width(self) -> int:
        """Width the page may use: the scroll viewport, never the content itself.

        Overflowing content has already grown to its own minimum width, so its
        width cannot be the budget.
        """
        parent = self._content.parentWidget()
        source = parent if parent is not None else self._content
        return int(_val(source.width))

    def reflow(self) -> None:
        if self._busy or self._content is None:
            return
        self._busy = True
        try:
            available = self.available_width()
            for row in self._rows:
                row.setStacked(reflowDecision(row.stacked, row.natural_width, available))
            self._rewrapCaptions(available)
        except (ValueError, RuntimeError):
            # Qt deleted the content widget (shutdown or shell deactivation).
            self._content = None
            self._rows = []
            self._captions = []
        finally:
            self._busy = False

    def _rewrapCaptions(self, available: int) -> None:
        for widget in self._captions:
            current = str(_val(widget.text))
            full = widget.property(_FULL_TEXT_KEY)
            if full is None or current != widget.property(_WRAPPED_TEXT_KEY):
                full = current  # first sight, or other code set a new caption
                widget.setProperty(_FULL_TEXT_KEY, full)
            left = int(_val(widget.mapTo(self._content, qt.QPoint(0, 0)).x))
            limit = max(
                CAPTION_MIN_WIDTH_PX,
                available - left - CAPTION_RIGHT_MARGIN_PX - CAPTION_INDICATOR_PX,
            )
            metrics = qt.QFontMetrics(_val(widget.font))
            measure = (
                metrics.horizontalAdvance
                if hasattr(metrics, "horizontalAdvance")
                else metrics.width
            )
            wrapped = wrapCaption(str(full), limit, measure)
            if wrapped != current:
                widget.setText(wrapped)
            widget.setProperty(_WRAPPED_TEXT_KEY, wrapped)

    def installResizeReflow(self) -> None:
        if self._filter is not None or self._content is None or not fitEnabled():
            return
        self._filter = _ResizeFilter(self._content, self)


class _ResizeFilter(qt.QObject if qt is not None else object):
    def __init__(self, widget, controller: NarrowFitController) -> None:
        super().__init__(widget)
        self._controller = controller
        widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == qt.QEvent.Resize:
            qt.QTimer.singleShot(0, self._controller.reflow)
        return False


def findWidthOffenders(root, available_width: int, visible_within=None) -> list[dict]:
    """List widgets whose own minimum width exceeds ``available_width``.

    Diagnostic only: this is the Phase-0 audit that selects per-panel fixes
    (explicit minimums, long captions, grids) after the generic pass.
    ``visible_within`` limits the list to widgets shown inside that ancestor
    (the active page), skipping stages and sections that are hidden.  ``leaf``
    is True when no offending descendant explains the width, i.e. the widget
    itself is the root cause rather than a container inheriting it.
    """
    found = []
    for widget in _widgets(root):
        if visible_within is not None and not widget.isVisibleTo(visible_within):
            continue
        explicit = _explicitMinWidth(widget)
        hint = _minHintWidth(widget)
        effective = explicit if explicit > 0 else hint
        if effective > available_width:
            found.append((widget, explicit, hint, effective))
    offenders = []
    for widget, explicit, hint, effective in found:
        parent = widget.parentWidget()
        offenders.append(
            {
                "object": str(_val(widget.objectName)),
                "class": _className(widget),
                "parent": str(_val(parent.objectName)) if parent is not None else "",
                "explicit_min": explicit,
                "hint_min": hint,
                "needs": effective,
                "leaf": not any(
                    other is not widget and widget.isAncestorOf(other)
                    for other, *_rest in found
                ),
                "text": str(_val(widget.text))[:60] if widget.inherits("QAbstractButton") else "",
            }
        )
    offenders.sort(key=lambda row: (not row["leaf"], -row["needs"]))
    return offenders
