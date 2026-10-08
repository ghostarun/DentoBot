"""Real-user input for the headed Step 6 harness (S6-ADVISOR-GUI-01).

A production control is pressed the way a user presses it:

* the control must be visible, enabled, and reachable: it is scrolled into view
  through its QScrollArea ancestors, and it must not sit inside a collapsed
  ctkCollapsibleButton (that fails; nothing is expanded silently);
* the Slicer main window (and the control's own top-level window) is raised and
  activated;
* the pointer is moved with the X server XTest extension and a real button press
  and release are sent. The press is confirmed by a ``clicked`` slot that runs
  inside the production handler's signal path.

Modes (env ``DENTOBOT_HEADED_INPUT``):

* ``xtest`` (default for new runs): real XTest input, no pacing overlay.
* ``demo``: ``xtest`` plus a pointer glide, a highlight frame and a caption, and
  pauses so a screen recording shows which control was pressed and its result.
* ``qt_click`` (legacy only): ``QAbstractButton.click()`` exactly as before.

``xtest`` and ``demo`` never fall back to ``click()``: every failure raises
``UserInputError`` and the control is not pressed.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

ENV_VAR = "DENTOBOT_HEADED_INPUT"
DEFAULT_MODE = "xtest"
MODES = ("xtest", "demo", "qt_click")
DELIVERY_TIMEOUT_SEC = 3.0
POINTER_SETTLE_TIMEOUT_SEC = 1.0
DEMO_APPROACH_SEC = 0.9
DEMO_PRE_CLICK_SEC = 1.5
DEMO_POST_CLICK_SEC = 0.8
DEMO_HOLD_SEC = 2.0
DEMO_STEPS = 30
HIGHLIGHT_MARGIN_PX = 6
CAPTION_GAP_PX = 10
PRESS_HOLD_SEC = 0.05

# Indirections so host tests can replace time and pumping without Qt or X.
_NOW = time.monotonic
_SLEEP = time.sleep
_BACKEND = None


class UserInputError(RuntimeError):
    """A user-visible precondition failed. The control was not pressed."""


def input_mode_from_env(environ=None) -> str:
    environ = os.environ if environ is None else environ
    raw = str(environ.get(ENV_VAR, "")).strip()
    mode = raw or DEFAULT_MODE
    if mode not in MODES:
        raise UserInputError(f"{ENV_VAR} must be one of {', '.join(MODES)}; got {raw!r}")
    return mode


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _runtime():
    import qt  # Slicer's PythonQt; imported lazily so host tests run without it
    import slicer

    return qt, slicer


def _value(obj, name):
    """Read a Qt property (value) or call a Qt getter method (no arguments)."""
    attribute = getattr(obj, name)
    return attribute() if callable(attribute) else attribute


def _text(obj) -> str:
    return str(_value(obj, "text")) if obj is not None else ""


def _object_name(obj) -> str:
    return str(_value(obj, "objectName")) if obj is not None else ""


def _class_name(obj) -> str:
    try:
        return str(_value(obj, "className"))
    except Exception:
        return type(obj).__name__


def _describe(obj) -> str:
    if obj is None:
        return "no Qt widget at that point (outside the Slicer window?)"
    return f"{_class_name(obj)}/{_object_name(obj) or '<no objectName>'}"


def _inherits(obj, class_name: str) -> bool:
    inherits = getattr(obj, "inherits", None)
    return bool(callable(inherits) and inherits(class_name))


def _ancestors(widget):
    current = _value(widget, "parent")
    while current is not None:
        yield current
        current = _value(current, "parent")


def _collapsed_ancestor(widget):
    for ancestor in _ancestors(widget):
        if _inherits(ancestor, "ctkCollapsibleButton") and bool(_value(ancestor, "collapsed")):
            return ancestor
    return None


def _scroll_areas(widget) -> list:
    return [ancestor for ancestor in _ancestors(widget) if _inherits(ancestor, "QScrollArea")]


def _pump_once() -> None:
    qt, _slicer = _runtime()
    qt.QApplication.processEvents()
    _SLEEP(0.01)


def _pump_until(deadline: float) -> None:
    while _NOW() < deadline:
        _pump_once()


def _wait_for(predicate, timeout: float) -> bool:
    deadline = _NOW() + timeout
    while True:
        if predicate():
            return True
        if _NOW() >= deadline:
            return False
        _pump_once()


def _preflight(widget, label: str) -> list[str]:
    """Fail on any unreachable control, then scroll it into view like a user would."""
    collapsed = _collapsed_ancestor(widget)
    if collapsed is not None:
        raise UserInputError(
            f"{label}: not reachable without expanding {_text(collapsed) or _object_name(collapsed)}"
        )
    if not bool(_value(widget, "visible")):
        raise UserInputError(f"{label}: control is not visible")
    if not bool(_value(widget, "enabled")):
        raise UserInputError(f"{label}: control is disabled")
    scrolled = []
    for area in _scroll_areas(widget):
        area.ensureWidgetVisible(widget)
        scrolled.append(_object_name(area) or _class_name(area))
    if scrolled:
        _pump_once()
    return scrolled


def _raise_and_activate(widget, slicer) -> None:
    main = slicer.util.mainWindow()
    if main is None:
        raise UserInputError("Slicer main window is unavailable")
    main.raise_()
    main.activateWindow()
    top = _value(widget, "window")
    if top is not None and top is not main:
        top.raise_()
        top.activateWindow()
    _pump_once()


def _device_pixel_ratio(qt, point) -> float:
    app = qt.QApplication
    screen = None
    screen_at = getattr(app, "screenAt", None)
    if callable(screen_at):
        screen = screen_at(point)
    if screen is None:
        primary = getattr(app, "primaryScreen", None)
        screen = primary() if callable(primary) else None
    if screen is None:
        raise UserInputError("no screen is available for the logical-to-physical conversion")
    dpr = float(_value(screen, "devicePixelRatio"))
    if not dpr > 0:
        raise UserInputError(f"screen reports an invalid devicePixelRatio: {dpr}")
    return dpr


def _target(widget, qt, label: str) -> tuple[tuple[int, int], float, tuple[int, int]]:
    """Return (logical global centre, devicePixelRatio, physical X pixel)."""
    centre = _value(widget, "rect").center()
    point = widget.mapToGlobal(centre)
    logical = (int(point.x()), int(point.y()))
    dpr = _device_pixel_ratio(qt, point)
    physical = (round(logical[0] * dpr), round(logical[1] * dpr))
    return logical, dpr, physical


def _is_widget_or_descendant(found, widget) -> bool:
    if found is None:
        return False
    if found is widget or found == widget:
        return True
    is_ancestor_of = getattr(widget, "isAncestorOf", None)
    return bool(callable(is_ancestor_of) and is_ancestor_of(found))


def overlay_window_flags(qt) -> int:
    return (int(qt.Qt.Tool) | int(qt.Qt.FramelessWindowHint) | int(qt.Qt.WindowStaysOnTopHint)
            | int(qt.Qt.WindowTransparentForInput))


class _Overlay:
    """Click-through, non-activating highlight frame plus caption (demo mode only)."""

    def __init__(self, qt, widget, caption: str):
        flags = overlay_window_flags(qt)
        self._qt = qt
        origin = widget.mapToGlobal(_value(widget, "rect").topLeft())
        left, top = int(origin.x()), int(origin.y())
        width, height = int(_value(widget, "width")), int(_value(widget, "height"))
        self._frame = qt.QFrame()
        self._frame.setWindowFlags(flags)
        self._frame.setAttribute(qt.Qt.WA_TranslucentBackground, True)
        self._frame.setAttribute(qt.Qt.WA_ShowWithoutActivating, True)
        self._frame.setFocusPolicy(qt.Qt.NoFocus)
        self._frame.setStyleSheet(
            "QFrame { border: 6px solid #e8311a; border-radius: 6px; background: transparent; }"
        )
        margin = HIGHLIGHT_MARGIN_PX
        self._frame.setGeometry(left - margin, top - margin, width + 2 * margin, height + 2 * margin)
        self._caption = qt.QLabel(caption)
        self._caption.setWindowFlags(flags)
        self._caption.setAttribute(qt.Qt.WA_ShowWithoutActivating, True)
        self._caption.setFocusPolicy(qt.Qt.NoFocus)
        self._caption.setStyleSheet(
            "QLabel { background: #111827; color: #ffffff; font-size: 18pt; font-weight: bold;"
            " padding: 8px 14px; border-radius: 6px; }"
        )
        self._caption.adjustSize()
        caption_height = int(_value(self._caption, "height"))
        caption_y = top - margin - CAPTION_GAP_PX - caption_height
        if caption_y < 0:
            caption_y = top + height + margin + CAPTION_GAP_PX
        self._caption.move(max(0, left), max(0, caption_y))

    def show(self) -> None:
        self._frame.show()
        self._caption.show()
        _pump_once()

    def hide(self) -> None:
        for window in (self._frame, self._caption):
            window.hide()
            window.deleteLater()
        _pump_once()


class XTestBackend:
    """ctypes binding to libX11 and libXtst: pointer query, motion, and button events."""

    def __init__(self, xlib, xtst):
        self._x = xlib
        self._t = xtst
        c = ctypes
        xlib.XOpenDisplay.argtypes = [c.c_char_p]
        xlib.XOpenDisplay.restype = c.c_void_p
        xlib.XDefaultRootWindow.argtypes = [c.c_void_p]
        xlib.XDefaultRootWindow.restype = c.c_ulong
        xlib.XQueryPointer.argtypes = [
            c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong), c.POINTER(c.c_ulong),
            c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_int),
            c.POINTER(c.c_uint),
        ]
        xlib.XQueryPointer.restype = c.c_int
        xlib.XFlush.argtypes = [c.c_void_p]
        xlib.XFlush.restype = c.c_int
        xtst.XTestQueryExtension.argtypes = [c.c_void_p] + [c.POINTER(c.c_int)] * 4
        xtst.XTestQueryExtension.restype = c.c_int
        xtst.XTestFakeMotionEvent.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong]
        xtst.XTestFakeMotionEvent.restype = c.c_int
        xtst.XTestFakeButtonEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
        xtst.XTestFakeButtonEvent.restype = c.c_int
        self._display = xlib.XOpenDisplay(None)
        if not self._display:
            raise UserInputError(f"X display is unavailable (DISPLAY={os.environ.get('DISPLAY')!r})")
        events, errors, major, minor = (c.c_int() for _ in range(4))
        if not xtst.XTestQueryExtension(self._display, c.pointer(events), c.pointer(errors),
                                        c.pointer(major), c.pointer(minor)):
            raise UserInputError("the XTest extension is unavailable on the X display")
        self._root = xlib.XDefaultRootWindow(self._display)

    def pointer(self) -> tuple[int, int]:
        c = ctypes
        root, child = c.c_ulong(), c.c_ulong()
        root_x, root_y, win_x, win_y = (c.c_int() for _ in range(4))
        mask = c.c_uint()
        on_screen = self._x.XQueryPointer(
            self._display, self._root, c.pointer(root), c.pointer(child),
            c.pointer(root_x), c.pointer(root_y), c.pointer(win_x), c.pointer(win_y),
            c.pointer(mask),
        )
        if not on_screen:
            raise UserInputError("the pointer is not on the X screen")
        return int(root_x.value), int(root_y.value)

    def move(self, x: int, y: int) -> None:
        self._t.XTestFakeMotionEvent(self._display, -1, int(x), int(y), 0)
        self._x.XFlush(self._display)

    def button(self, button: int, pressed: bool) -> None:
        self._t.XTestFakeButtonEvent(self._display, int(button), 1 if pressed else 0, 0)
        self._x.XFlush(self._display)


def get_backend():
    """Open the X display once per process (the Slicer process owns it)."""
    global _BACKEND
    if _BACKEND is None:
        try:
            xlib = ctypes.CDLL("libX11.so.6")
            xtst = ctypes.CDLL("libXtst.so.6")
        except OSError as exc:
            raise UserInputError(f"XTest libraries are unavailable: {exc}") from exc
        _BACKEND = XTestBackend(xlib, xtst)
    return _BACKEND


def _move_and_verify(backend, target) -> None:
    backend.move(*target)
    reached = _wait_for(lambda: backend.pointer() == tuple(target), POINTER_SETTLE_TIMEOUT_SEC)
    if not reached:
        raise UserInputError(f"pointer did not reach the control at {tuple(target)}; "
                             f"it is at {backend.pointer()}")


def _animate(backend, start, end, seconds: float) -> None:
    began = _NOW()
    for step in range(1, DEMO_STEPS + 1):
        fraction = step / DEMO_STEPS
        backend.move(round(start[0] + (end[0] - start[0]) * fraction),
                     round(start[1] + (end[1] - start[1]) * fraction))
        _pump_until(began + seconds * fraction)


def _append_evidence(evidence, record: dict) -> None:
    if evidence is None:
        return
    path = Path(evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _record(widget, label, mode, **details) -> dict:
    return {
        "label": label,
        "objectName": _object_name(widget),
        "text": _text(widget),
        "widget_class": _class_name(widget),
        "mode": mode,
        "utc": utc_now(),
        **details,
    }


def user_click(widget, label: str, *, mode: str, evidence=None) -> dict:
    """Press ``widget`` the way a user does and return a record of the press.

    Raises ``UserInputError`` (never falls back to ``click()``) in ``xtest`` and
    ``demo`` modes when the control cannot be reached, is covered, or the press
    is not delivered.
    """
    if mode not in MODES:
        raise UserInputError(f"unknown input mode {mode!r}")
    if mode == "qt_click":
        widget.click()
        record = _record(widget, label, mode, physical_xy=None, logical_xy=None,
                         device_pixel_ratio=None, delivered=None)
        _append_evidence(evidence, record)
        return record

    qt, slicer = _runtime()
    scrolled = _preflight(widget, label)
    _raise_and_activate(widget, slicer)
    logical, dpr, physical = _target(widget, qt, label)
    backend = get_backend()
    start = backend.pointer()
    delivered = {"utc": None}

    def on_clicked():
        if delivered["utc"] is None:
            delivered["utc"] = utc_now()

    overlay = None
    connected = False
    try:
        if mode == "demo":
            began = _NOW()
            overlay = _Overlay(qt, widget, f"Clicking: {label}")
            overlay.show()
            _animate(backend, start, physical, DEMO_APPROACH_SEC)
            _pump_until(began + DEMO_PRE_CLICK_SEC)
            overlay.hide()
            overlay = None
        _move_and_verify(backend, physical)
        found = qt.QApplication.widgetAt(qt.QPoint(*logical))
        if not _is_widget_or_descendant(found, widget):
            raise UserInputError(f"{label}: covered by {_describe(found)}")
        clicked_signal = widget.clicked
        clicked_signal.connect(on_clicked)
        connected = True
        backend.button(1, True)
        _pump_until(_NOW() + PRESS_HOLD_SEC)
        backend.button(1, False)
        delivered_ok = _wait_for(lambda: delivered["utc"] is not None, DELIVERY_TIMEOUT_SEC)
        if not delivered_ok:
            raise UserInputError(f"{label}: real click not delivered (no clicked signal within "
                                 f"{DELIVERY_TIMEOUT_SEC:.0f} s)")
        if mode == "demo":
            overlay = _Overlay(qt, widget, f"Clicked: {label}")
            overlay.show()
            _pump_until(_NOW() + DEMO_POST_CLICK_SEC)
            overlay.hide()
            overlay = None
            _pump_until(_NOW() + DEMO_HOLD_SEC)
    finally:
        if connected:
            clicked_signal.disconnect(on_clicked)
        if overlay is not None:
            overlay.hide()

    record = _record(
        widget, label, mode,
        physical_xy=list(physical), logical_xy=list(logical), device_pixel_ratio=dpr,
        pointer_start_xy=list(start), scrolled_areas=scrolled, delivered=True,
        delivered_utc=delivered["utc"],
    )
    _append_evidence(evidence, record)
    return record


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-") or "control"
