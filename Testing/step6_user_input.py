"""Real-user input for the headed Step 6 harness (S6-ADVISOR-GUI-01).

A production control is pressed the way a user presses it:

* the control must be visible, enabled, and reachable: it is scrolled into view
  through its QScrollArea ancestors, and it must not sit inside a collapsed
  ctkCollapsibleButton (that fails; nothing is expanded silently);
* a control on a non-current QTabWidget page is reached the way a user reaches it:
  the tab is pressed with a real XTest click (outermost tab first, nested tabs in
  order), with the same window activation and X-level hit test, and the tab change is
  confirmed by ``currentIndex``. Each tab press is its own ledger entry
  (``navigation: "tab"``);
* any other hidden or collapsed reason may use the caller's direct navigation helper
  (for example a shell substep). Its use is logged as its own ledger entry
  (``navigation: "direct"``) with the reason, and visibility is checked again. The
  control is never made clickable any other way, and a control that is still not
  visible fails loudly;
* the control's top-level window (the Slicer main window for its controls) is raised
  and activated in Qt, and at X level with an EWMH ``_NET_ACTIVE_WINDOW`` request
  plus ``XRaiseWindow``;
* the pointer is moved and an X-level hit test must find the control's native window
  under it (XQueryPointer descent from the root). A covered control is never pressed:
  the refusal names the external X window;
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
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ENV_VAR = "DENTOBOT_HEADED_INPUT"
DEFAULT_MODE = "xtest"
MODES = ("xtest", "demo", "qt_click")
DELIVERY_TIMEOUT_SEC = 3.0
X_POLL_TIMEOUT_SEC = 1.5
X_ACTIVATION_ATTEMPTS = 2
DEMO_APPROACH_SEC = 0.9
DEMO_PRE_CLICK_SEC = 1.5
DEMO_POST_CLICK_SEC = 0.8
DEMO_HOLD_SEC = 2.0
DEMO_STEPS = 30
HIGHLIGHT_MARGIN_PX = 6
CAPTION_GAP_PX = 10
PRESS_HOLD_SEC = 0.05
NAVIGATION_STEP_LIMIT = 8  # tab presses plus direct steps allowed before a control is refused

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


def _press_point(widget, qt, label: str):
    """Local point a user presses. A check box or radio button is pressed on its indicator.

    A wide QCheckBox spans its whole row, but Qt only hit-tests its indicator and label text
    (SE_CheckBoxClickRect), so the centre of the row is empty space. The indicator comes from
    the widget's style (SE_CheckBoxIndicator / SE_RadioButtonIndicator); the text area
    (SE_CheckBoxContents / SE_RadioButtonContents) is the fallback. Neither means no press.
    """
    if _inherits(widget, "QCheckBox") or _inherits(widget, "QRadioButton"):
        check = _inherits(widget, "QCheckBox")
        elements = ((qt.QStyle.SE_CheckBoxIndicator, qt.QStyle.SE_CheckBoxContents) if check
                    else (qt.QStyle.SE_RadioButtonIndicator, qt.QStyle.SE_RadioButtonContents))
        option = qt.QStyleOptionButton()
        option.initFrom(widget)
        style = widget.style()
        for element in elements:
            area = style.subElementRect(element, option, widget)
            if area is not None and int(area.width()) > 0 and int(area.height()) > 0:
                return area.center()
        raise UserInputError(f"{label}: the check box has no indicator or label area to press")
    return _value(widget, "rect").center()


def _target(widget, qt, label: str) -> tuple[tuple[int, int], float, tuple[int, int]]:
    """Return (logical global press point, devicePixelRatio, physical X pixel)."""
    point = widget.mapToGlobal(_press_point(widget, qt, label))
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


_CLIENT_MESSAGE = 33
_SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
_SUBSTRUCTURE_REDIRECT_MASK = 1 << 20
_EWMH_SOURCE_PAGER = 2  # EWMH source indication: a pager/taskbar, as for a user's window switch
_CURRENT_TIME = 0
_ANY_PROPERTY_TYPE = 0
XEVENT_SIZE = 192  # sizeof(XEvent) on 64-bit Linux; XClientMessageEvent occupies the first 96 bytes
MAX_WINDOW_DEPTH = 64


class ClientMessageEvent(ctypes.Structure):
    """Xlib's XClientMessageEvent on 64-bit Linux (96 bytes)."""

    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class XTestBackend:
    """ctypes binding to libX11 and libXtst: window stack, EWMH activation, pointer and buttons."""

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
        xlib.XInternAtom.argtypes = [c.c_void_p, c.c_char_p, c.c_int]
        xlib.XInternAtom.restype = c.c_ulong
        xlib.XSendEvent.argtypes = [c.c_void_p, c.c_ulong, c.c_int, c.c_long, c.c_void_p]
        xlib.XSendEvent.restype = c.c_int
        xlib.XRaiseWindow.argtypes = [c.c_void_p, c.c_ulong]
        xlib.XRaiseWindow.restype = c.c_int
        xlib.XGetWindowProperty.argtypes = [
            c.c_void_p, c.c_ulong, c.c_ulong, c.c_long, c.c_long, c.c_int, c.c_ulong,
            c.POINTER(c.c_ulong), c.POINTER(c.c_int), c.POINTER(c.c_ulong),
            c.POINTER(c.c_ulong), c.POINTER(c.c_void_p),
        ]
        xlib.XGetWindowProperty.restype = c.c_int
        xlib.XFetchName.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_void_p)]
        xlib.XFetchName.restype = c.c_int
        xlib.XFree.argtypes = [c.c_void_p]
        xlib.XFree.restype = c.c_int
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
        self._atoms: dict[str, int] = {}

    def _query_pointer(self, window: int) -> tuple[int, int, int]:
        """Return (child of ``window`` containing the pointer or 0, root_x, root_y)."""
        c = ctypes
        root, child = c.c_ulong(), c.c_ulong()
        root_x, root_y, win_x, win_y = (c.c_int() for _ in range(4))
        mask = c.c_uint()
        on_screen = self._x.XQueryPointer(
            self._display, window, c.pointer(root), c.pointer(child),
            c.pointer(root_x), c.pointer(root_y), c.pointer(win_x), c.pointer(win_y),
            c.pointer(mask),
        )
        if not on_screen:
            raise UserInputError("the pointer is not on the X screen")
        return int(child.value), int(root_x.value), int(root_y.value)

    def pointer(self) -> tuple[int, int]:
        _child, x, y = self._query_pointer(self._root)
        return x, y

    def pointer_chain(self) -> list[int]:
        """Windows under the pointer from the top-level down to the deepest (XQueryPointer descent).

        Each step asks a window for the child containing the pointer, so the list is the ancestry
        of the deepest window. A control's native window is hit exactly when its id is in it.
        """
        chain: list[int] = []
        window = self._root
        for _depth in range(MAX_WINDOW_DEPTH):
            child, _x, _y = self._query_pointer(window)
            if not child:
                return chain
            chain.append(child)
            window = child
        raise UserInputError(f"the window stack under the pointer is deeper than {MAX_WINDOW_DEPTH}")

    def atom(self, name: str) -> int:
        if name not in self._atoms:
            self._atoms[name] = int(self._x.XInternAtom(self._display, name.encode("ascii"), 0))
        return self._atoms[name]

    def _property(self, window: int, name: str, req_type: int):
        """Window property: list of ints for format 32, bytes for format 8, None when absent."""
        c = ctypes
        actual_type, actual_format = c.c_ulong(), c.c_int()
        count, remaining = c.c_ulong(), c.c_ulong()
        data = c.c_void_p()
        status = self._x.XGetWindowProperty(
            self._display, window, self.atom(name), 0, 1024, 0, req_type,
            c.pointer(actual_type), c.pointer(actual_format), c.pointer(count),
            c.pointer(remaining), c.pointer(data),
        )
        if status != 0 or not data.value or count.value == 0:
            if data.value:
                self._x.XFree(data.value)
            return None
        try:
            if actual_format.value == 32:
                longs = c.cast(data.value, c.POINTER(c.c_ulong))
                return [int(longs[index]) for index in range(count.value)]
            return c.string_at(data.value, count.value)
        finally:
            self._x.XFree(data.value)

    def active_window(self) -> int:
        """_NET_ACTIVE_WINDOW on the root window (0 when no window manager publishes one)."""
        value = self._property(self._root, "_NET_ACTIVE_WINDOW", _ANY_PROPERTY_TYPE)
        return int(value[0]) if isinstance(value, list) and value else 0

    def window_name(self, window: int) -> str:
        """_NET_WM_NAME (UTF-8) when set, else WM_NAME; empty when neither is available."""
        value = self._property(window, "_NET_WM_NAME", self.atom("UTF8_STRING"))
        if isinstance(value, bytes) and value:
            return value.decode("utf-8", "replace")
        c = ctypes
        name = c.c_void_p()
        if self._x.XFetchName(self._display, window, c.pointer(name)) and name.value:
            try:
                return c.string_at(name.value).decode("utf-8", "replace")
            finally:
                self._x.XFree(name.value)
        return ""

    def activate_window(self, window: int) -> None:
        """EWMH _NET_ACTIVE_WINDOW request to the root window, plus a local XRaiseWindow."""
        message = ClientMessageEvent()
        message.type = _CLIENT_MESSAGE
        message.send_event = 1
        message.display = self._display
        message.window = int(window)
        message.message_type = self.atom("_NET_ACTIVE_WINDOW")
        message.format = 32
        message.data[0] = _EWMH_SOURCE_PAGER
        message.data[1] = _CURRENT_TIME
        message.data[2] = 0  # requestor's currently active window: none known
        event = ctypes.create_string_buffer(XEVENT_SIZE)
        ctypes.memmove(ctypes.addressof(event), ctypes.addressof(message), ctypes.sizeof(message))
        self._x.XSendEvent(self._display, self._root, 0,
                           _SUBSTRUCTURE_REDIRECT_MASK | _SUBSTRUCTURE_NOTIFY_MASK,
                           ctypes.addressof(event))
        self._x.XRaiseWindow(self._display, int(window))
        self._x.XFlush(self._display)

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


def _hex(value) -> str:
    return f"0x{int(value):x}"


def _native_window(top, label: str) -> int:
    """Native X window of the control's top-level Qt window (the Slicer main window for its controls)."""
    if top is None:
        raise UserInputError(f"{label}: the control has no top-level window")
    window = int(_value(top, "winId") or 0)
    if not window:
        raise UserInputError(f"{label}: the control's top-level window has no native X window")
    return window


def _poll_hit_test(backend, target: int, physical) -> dict:
    """Move the pointer to ``physical`` and poll up to X_POLL_TIMEOUT_SEC for an X-level hit.

    A hit means the pointer is at the target and ``target`` is in the window chain under it
    (the deepest window is the target or one of its descendants).
    """
    began = _NOW()
    deadline = began + X_POLL_TIMEOUT_SEC
    target_xy = (int(physical[0]), int(physical[1]))
    backend.move(*target_xy)
    while True:
        _pump_once()
        pointer = tuple(backend.pointer())
        if pointer != target_xy:
            backend.move(*target_xy)
        chain = list(backend.pointer_chain())
        hit = pointer == target_xy and target in chain
        if hit or _NOW() >= deadline:
            return {"hit": bool(hit), "pointer_xy": pointer, "chain": chain,
                    "elapsed_sec": round(_NOW() - began, 3)}


def _x_activate_and_confirm(backend, widget, slicer, target: int, physical, label: str,
                            evidence: dict) -> None:
    """Activate the control's top-level window at X level and require an X-level hit test.

    Two attempts. Each sends the EWMH activation and XRaiseWindow (the second repeats the Qt
    raise first) and then polls up to 1.5 s for the pointer to hit the target. Never presses.
    A covered control raises UserInputError that names the external window under the pointer.
    """
    evidence["attempts"] = []
    last = None
    for attempt in range(1, X_ACTIVATION_ATTEMPTS + 1):
        if attempt > 1:
            _raise_and_activate(widget, slicer)
        backend.activate_window(target)
        _pump_once()
        last = _poll_hit_test(backend, target, physical)
        evidence["attempts"].append({
            "attempt": attempt,
            "hit": last["hit"],
            "pointer_xy": list(last["pointer_xy"]),
            "chain": [_hex(window) for window in last["chain"]],
            "elapsed_sec": last["elapsed_sec"],
            "active_window_after": _hex(backend.active_window()),
        })
        if last["hit"]:
            evidence["hit_test"] = "pass"
            return
    evidence["hit_test"] = "covered"
    target_xy = (int(physical[0]), int(physical[1]))
    if tuple(last["pointer_xy"]) != target_xy:
        raise UserInputError(
            f"{label}: pointer did not reach the control at {target_xy}; "
            f"it is at {tuple(last['pointer_xy'])}"
        )
    chain = last["chain"]
    external = chain[0] if chain else 0
    name = backend.window_name(external) if external else ""
    raise UserInputError(f"{label}: covered by external X window {_hex(external)} {name or '<no name>'}")


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


def _contains(page, widget) -> bool:
    """True when ``page`` is ``widget`` or one of its ancestors."""
    if page is None:
        return False
    return page == widget or bool(page.isAncestorOf(widget))


def _page_index(tab_widget, widget):
    """Index of the QTabWidget page that contains ``widget``, or None."""
    for index in range(int(_value(tab_widget, "count"))):
        if _contains(tab_widget.widget(index), widget):
            return index
    return None


def _tab_pages_outermost_first(widget) -> list:
    """(QTabWidget, page index) for each tab page that contains ``widget``, outermost first."""
    pages = []
    for ancestor in _ancestors(widget):
        if not _inherits(ancestor, "QTabWidget"):
            continue
        index = _page_index(ancestor, widget)
        if index is not None:
            pages.append((ancestor, index))
    return list(reversed(pages))


def _first_hidden_tab_page(widget):
    """The outermost (QTabWidget, index) whose page holds ``widget`` but is not current."""
    for tab_widget, index in _tab_pages_outermost_first(widget):
        if int(_value(tab_widget, "currentIndex")) != index:
            return tab_widget, index
    return None


def _navigate_tab(tab_widget, index: int, *, owner_label: str, mode: str, evidence, qt, slicer) -> dict:
    """Open tab ``index`` of ``tab_widget`` with a real XTest click, the way a user would.

    Same preconditions as a control press: the tab bar must be visible, the tab enabled,
    the window activated and hit at X level, and the tab bar not covered in Qt. The tab
    change is confirmed by ``currentIndex``. Writes one ledger entry, refusals included.
    Never calls ``click()`` or sets ``currentIndex`` directly.
    """
    tab_bar = tab_widget.tabBar()
    tab_text = str(tab_widget.tabText(index))
    label = f"Open tab '{tab_text}' ({_object_name(tab_widget) or _class_name(tab_widget)})"
    reason = f"{owner_label} is on this tab page, which is not the current tab"
    x_activation: dict = {}
    scrolled: list[str] = []
    delivered = {"utc": None}
    overlay = None
    connected = False
    signal = None

    def on_tab_clicked(clicked_index):
        if int(clicked_index) == index and delivered["utc"] is None:
            delivered["utc"] = utc_now()

    def base_record() -> dict:
        return {
            "navigation": "tab", "label": label, "reason": reason, "mode": mode,
            "objectName": _object_name(tab_widget), "widget_class": _class_name(tab_widget),
            "tab_bar_objectName": _object_name(tab_bar), "tab_index": int(index),
            "tab_text": tab_text, "utc": utc_now(),
        }

    try:
        if not bool(_value(tab_bar, "visible")):
            raise UserInputError(f"{label}: tab bar is not visible")
        if not bool(tab_bar.isTabEnabled(index)):
            raise UserInputError(f"{label}: tab is disabled")
        for area in _scroll_areas(tab_bar):
            area.ensureWidgetVisible(tab_bar)
            scrolled.append(_object_name(area) or _class_name(area))
        if scrolled:
            _pump_once()
        _raise_and_activate(tab_widget, slicer)
        point = tab_bar.mapToGlobal(tab_bar.tabRect(index).center())
        logical = (int(point.x()), int(point.y()))
        dpr = _device_pixel_ratio(qt, point)
        physical = (round(logical[0] * dpr), round(logical[1] * dpr))
        backend = get_backend()
        start = backend.pointer()
        target = _native_window(_value(tab_widget, "window"), label)
        x_activation["target_window"] = _hex(target)
        if mode == "demo":
            began = _NOW()
            overlay = _Overlay(qt, tab_bar, f"Clicking: {label}")
            overlay.show()
            _animate(backend, start, physical, DEMO_APPROACH_SEC)
            _pump_until(began + DEMO_PRE_CLICK_SEC)
            overlay.hide()
            overlay = None
        _x_activate_and_confirm(backend, tab_widget, slicer, target, physical, label, x_activation)
        found = qt.QApplication.widgetAt(qt.QPoint(*logical))
        if not _is_widget_or_descendant(found, tab_bar):
            raise UserInputError(f"{label}: covered by {_describe(found)}")
        before = int(_value(tab_widget, "currentIndex"))
        signal = tab_widget.tabBarClicked
        signal.connect(on_tab_clicked)
        connected = True
        backend.button(1, True)
        _pump_until(_NOW() + PRESS_HOLD_SEC)
        backend.button(1, False)
        if not _wait_for(lambda: int(_value(tab_widget, "currentIndex")) == index, DELIVERY_TIMEOUT_SEC):
            current = int(_value(tab_widget, "currentIndex"))
            raise UserInputError(f"{label}: tab press not delivered (current tab stayed {current})")
        after = int(_value(tab_widget, "currentIndex"))
        if mode == "demo":
            overlay = _Overlay(qt, tab_bar, f"Opened: {label}")
            overlay.show()
            _pump_until(_NOW() + DEMO_POST_CLICK_SEC)
            overlay.hide()
            overlay = None
            _pump_until(_NOW() + DEMO_HOLD_SEC)
    except UserInputError as refusal:
        _append_evidence(evidence, {**base_record(), "delivered": False, "refused": str(refusal),
                                    "x_activation": x_activation, "scrolled_areas": scrolled})
        raise
    finally:
        if connected:
            signal.disconnect(on_tab_clicked)
        if overlay is not None:
            overlay.hide()

    record = {
        **base_record(), "delivered": True, "delivered_utc": delivered["utc"],
        "currentIndex_before": before, "currentIndex_after": after,
        "physical_xy": list(physical), "logical_xy": list(logical), "device_pixel_ratio": dpr,
        "pointer_start_xy": list(start), "scrolled_areas": scrolled, "x_activation": x_activation,
    }
    _append_evidence(evidence, record)
    return record


def _unreachable_message(label: str, collapsed, direct_action) -> str:
    if collapsed is not None:
        message = f"{label}: not reachable without expanding {_text(collapsed) or _object_name(collapsed)}"
    else:
        message = f"{label}: control is not visible"
    if direct_action is not None:
        message += f" after direct navigation ({direct_action})"
    return message


def _ensure_reachable(widget, label: str, *, mode: str, evidence, qt, slicer, direct_navigation) -> list:
    """Bring ``widget`` into a user's view by ordinary navigation, or refuse.

    A disabled control is refused before any navigation. A control on a non-current tab
    page is reached by real tab presses (outermost first). Otherwise the caller's
    ``direct_navigation(widget, reason)`` may be used once: it returns None when it has no
    navigation for this control, or ``{"reason", "action"}`` after it has navigated, and
    that use is logged as its own entry. Visibility is checked again each time. Returns
    the navigation records written for this control.
    """
    navigations: list[dict] = []
    direct_action = None
    for _step in range(NAVIGATION_STEP_LIMIT + 1):
        collapsed = _collapsed_ancestor(widget)
        if collapsed is None and not bool(_value(widget, "enabled")):
            raise UserInputError(f"{label}: control is disabled")
        if collapsed is None and bool(_value(widget, "visible")):
            return navigations
        if collapsed is None:
            pending = _first_hidden_tab_page(widget)
            if pending is not None and bool(_value(pending[0], "visible")):
                tab_widget, index = pending
                navigations.append(_navigate_tab(tab_widget, index, owner_label=label, mode=mode,
                                                 evidence=evidence, qt=qt, slicer=slicer))
                continue
        hidden_reason = ("collapsed group" if collapsed is not None
                         else "hidden by a non-current page or group")
        if direct_navigation is None or direct_action is not None:
            raise UserInputError(_unreachable_message(label, collapsed, direct_action))
        result = direct_navigation(widget, hidden_reason)
        if result is None:
            raise UserInputError(_unreachable_message(label, collapsed, None))
        direct_action = str(result["action"])
        entry = {
            "navigation": "direct", "label": label, "reason": str(result["reason"]),
            "hidden_reason": hidden_reason, "action": direct_action, "mode": mode,
            "objectName": _object_name(widget), "text": _text(widget),
            "widget_class": _class_name(widget), "delivered": None, "utc": utc_now(),
        }
        _append_evidence(evidence, entry)
        navigations.append(entry)
    raise UserInputError(
        f"{label}: navigation did not make the control reachable in {NAVIGATION_STEP_LIMIT} steps"
    )


def _navigation_summary(navigations) -> list[dict]:
    """Compact view of the navigation entries written before a control press."""
    return [{"navigation": item["navigation"], "label": item.get("label"),
             "tab_index": item.get("tab_index"), "action": item.get("action")}
            for item in navigations]


def user_click(widget, label: str, *, mode: str, evidence=None, direct_navigation=None) -> dict:
    """Press ``widget`` the way a user does and return a record of the press.

    ``xtest`` and ``demo`` raise ``UserInputError`` and never call ``click()`` when the control
    is unreachable, its window is not activated and hit at X level, Qt reports another widget
    on top, or the press is not delivered. A press is delivered only when the clicked signal
    reached this probe and no slot raised during the press. For a checkable control (check box,
    radio button) the checked state must also change. Each refusal is also written to the ledger
    with ``delivered: false``.

    Before the press, a hidden control on a non-current tab page is reached by real tab presses
    (see ``_ensure_reachable``). ``direct_navigation(widget, reason)`` is the caller's optional
    helper for other hidden reasons; its use is logged with ``navigation: "direct"``.
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
    x_activation: dict = {}
    overlay = None
    connected = False
    clicked_signal = None
    probe = {"utc": None, "errors": []}
    hook = {"previous": None, "errors": []}
    navigations: list[dict] = []
    checkable = bool(_value(widget, "checkable"))
    checked = {"before": None, "after": None}

    def on_clicked(*_args):  # a QCheckBox's clicked signal passes its checked state
        try:
            if probe["utc"] is None:
                probe["utc"] = utc_now()
        except Exception as exc:  # the probe never reports a delivery it did not record
            probe["errors"].append(f"{type(exc).__name__}: {exc}")

    def capture_exception(exc_type, exc, traceback):  # an exception raised by any slot during the press
        hook["errors"].append(f"{getattr(exc_type, '__name__', exc_type)}: {exc}")
        if hook["previous"] is not None:
            hook["previous"](exc_type, exc, traceback)

    def signal_errors() -> list:
        return list(probe["errors"]) + list(hook["errors"])

    try:
        navigations = _ensure_reachable(widget, label, mode=mode, evidence=evidence, qt=qt,
                                        slicer=slicer, direct_navigation=direct_navigation)
        scrolled = _preflight(widget, label)
        _raise_and_activate(widget, slicer)
        logical, dpr, physical = _target(widget, qt, label)
        backend = get_backend()
        start = backend.pointer()
        target = _native_window(_value(widget, "window"), label)
        x_activation["target_window"] = _hex(target)
        if checkable:
            checked["before"] = bool(_value(widget, "checked"))
        if mode == "demo":
            began = _NOW()
            overlay = _Overlay(qt, widget, f"Clicking: {label}")
            overlay.show()
            _animate(backend, start, physical, DEMO_APPROACH_SEC)
            _pump_until(began + DEMO_PRE_CLICK_SEC)
            overlay.hide()
            overlay = None
        _x_activate_and_confirm(backend, widget, slicer, target, physical, label, x_activation)
        found = qt.QApplication.widgetAt(qt.QPoint(*logical))
        if not _is_widget_or_descendant(found, widget):
            raise UserInputError(f"{label}: covered by {_describe(found)}")
        clicked_signal = widget.clicked
        clicked_signal.connect(on_clicked)
        connected = True
        hook["previous"] = sys.excepthook
        sys.excepthook = capture_exception
        backend.button(1, True)
        _pump_until(_NOW() + PRESS_HOLD_SEC)
        backend.button(1, False)
        if not _wait_for(lambda: probe["utc"] is not None or bool(probe["errors"]), DELIVERY_TIMEOUT_SEC):
            raise UserInputError(f"{label}: real click not delivered (no clicked signal within "
                                 f"{DELIVERY_TIMEOUT_SEC:.0f} s)")
        if probe["errors"]:
            raise UserInputError(f"{label}: not delivered; the clicked probe failed ({probe['errors'][0]})")
        if hook["errors"]:
            raise UserInputError(f"{label}: not delivered; a slot raised during the press ({hook['errors'][0]})")
        if checkable:
            checked["after"] = bool(_value(widget, "checked"))
            if checked["after"] == checked["before"]:
                raise UserInputError(f"{label}: clicked, but the checked state stayed {checked['before']}")
        if mode == "demo":
            overlay = _Overlay(qt, widget, f"Clicked: {label}")
            overlay.show()
            _pump_until(_NOW() + DEMO_POST_CLICK_SEC)
            overlay.hide()
            overlay = None
            _pump_until(_NOW() + DEMO_HOLD_SEC)
    except UserInputError as refusal:
        _append_evidence(evidence, _record(widget, label, mode, delivered=False,
                                           refused=str(refusal), x_activation=x_activation,
                                           signal_errors=signal_errors(), checkable=checkable,
                                           checked_before=checked["before"], checked_after=checked["after"],
                                           navigated_before_press=_navigation_summary(navigations)))
        raise
    finally:
        if hook["previous"] is not None:
            sys.excepthook = hook["previous"]
            hook["previous"] = None
        if connected:
            clicked_signal.disconnect(on_clicked)
        if overlay is not None:
            overlay.hide()

    record = _record(
        widget, label, mode,
        physical_xy=list(physical), logical_xy=list(logical), device_pixel_ratio=dpr,
        pointer_start_xy=list(start), scrolled_areas=scrolled, delivered=True,
        delivered_utc=probe["utc"], x_activation=x_activation, signal_errors=signal_errors(),
        checkable=checkable, checked_before=checked["before"], checked_after=checked["after"],
        navigated_before_press=_navigation_summary(navigations),
    )
    _append_evidence(evidence, record)
    return record


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-") or "control"
