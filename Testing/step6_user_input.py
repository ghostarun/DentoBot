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
* ``uinput``: the same preconditions and X-level checks as ``xtest``, but the pointer is
  moved and the button pressed through a kernel absolute pointer (uinput). Use it where the
  compositor ignores XTest motion (GNOME Wayland with rootless Xwayland). Every move is
  verified with XQueryPointer and corrected at most ``POINTER_CORRECTIONS`` times, then
  refused. See the uinput section below.
* ``qt_click`` (legacy only): ``QAbstractButton.click()`` exactly as before.

``xtest``, ``demo`` and ``uinput`` never fall back to ``click()`` or to another pointer
path: every failure raises ``UserInputError`` and the control is not pressed.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import re
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ENV_VAR = "DENTOBOT_HEADED_INPUT"
DEFAULT_MODE = "xtest"
MODES = ("xtest", "demo", "qt_click", "uinput")
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
        xlib.XDefaultScreen.argtypes = [c.c_void_p]
        xlib.XDefaultScreen.restype = c.c_int
        xlib.XDisplayWidth.argtypes = [c.c_void_p, c.c_int]
        xlib.XDisplayWidth.restype = c.c_int
        xlib.XDisplayHeight.argtypes = [c.c_void_p, c.c_int]
        xlib.XDisplayHeight.restype = c.c_int
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

    def desktop_size(self) -> tuple[int, int]:
        """Size of the X root window, which spans every monitor, in X pixels."""
        screen = int(self._x.XDefaultScreen(self._display))
        return (int(self._x.XDisplayWidth(self._display, screen)),
                int(self._x.XDisplayHeight(self._display, screen)))

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


# --- uinput: a kernel absolute pointer for compositors that ignore XTest motion ---------------
#
# On GNOME Wayland (rootless Xwayland) the compositor does not apply XTest pointer motion, so
# the XTest path cannot place the pointer. ``uinput`` mode creates a virtual absolute pointer in
# the kernel (ABS_X/ABS_Y over the X root, BTN_LEFT, INPUT_PROP_POINTER), which the compositor
# treats like a physical pointer. Every move is verified at X level with XQueryPointer. A miss
# gets at most POINTER_CORRECTIONS corrective moves, then UserInputError. Nothing falls back to
# XTest, XWarpPointer or click().
#
# The device is created in this process when /dev/uinput opens here. When it cannot (the
# DentoBot container has no uinput device), DENTOBOT_UINPUT_RELAY_DIR names a run-root directory
# served by a host helper (Testing/step6_uinput_helper.py) that owns the device. The helper only
# executes the absolute values the harness computes, and the harness verifies the result itself.

UINPUT_PATH = "/dev/uinput"
UINPUT_RELAY_ENV = "DENTOBOT_UINPUT_RELAY_DIR"
UINPUT_ABS_MAX = 65535
UINPUT_DEVICE_NAME = "dentobot-step6-absolute-pointer"
UINPUT_SETTLE_SEC = 1.0         # after UI_DEV_CREATE, so the compositor enumerates the device
POINTER_TOLERANCE_PX = 2        # X root pixels between the target and the verified position
POINTER_CORRECTIONS = 3         # corrective moves after the first move, then refusal
POINTER_SETTLE_SEC = 0.5        # how long the X pointer may take to reach one move
POINTER_SETTLE_STEP_SEC = 0.02
RELAY_POLL_SEC = 0.005
RELAY_READY_TIMEOUT_SEC = 15.0
RELAY_RESPONSE_TIMEOUT_SEC = 3.0

EV_SYN, EV_KEY, EV_ABS = 0x00, 0x01, 0x03
SYN_REPORT = 0x00
ABS_X, ABS_Y = 0x00, 0x01
BTN_LEFT = 0x110
INPUT_PROP_POINTER = 0x00
BUS_VIRTUAL = 0x06
_UINPUT_VENDOR = 0x1209  # pid.codes test vendor; the device name identifies this device
_UINPUT_PRODUCT = 0x0001
_IOC_NONE, _IOC_WRITE = 0, 1
_EVENT_FORMAT = "@llHHi"        # struct input_event on LP64 Linux: timeval, type, code, value
_SETUP_FORMAT = "=HHHH80sI"     # struct uinput_setup: input_id, name[80], ff_effects_max
_ABS_SETUP_FORMAT = "=Hxx6i"    # struct uinput_abs_setup: code, then input_absinfo (six __s32)


def _ioc(direction: int, nr: int, size: int) -> int:
    """Linux _IOC(direction, 'U', nr, size) for the uinput ioctls."""
    return (direction << 30) | (size << 16) | (ord("U") << 8) | nr


UI_DEV_CREATE = _ioc(_IOC_NONE, 1, 0)                                # 0x5501
UI_DEV_DESTROY = _ioc(_IOC_NONE, 2, 0)                               # 0x5502
UI_DEV_SETUP = _ioc(_IOC_WRITE, 3, struct.calcsize(_SETUP_FORMAT))   # 0x405c5503
UI_ABS_SETUP = _ioc(_IOC_WRITE, 4, struct.calcsize(_ABS_SETUP_FORMAT))  # 0x401c5504
UI_SET_EVBIT = _ioc(_IOC_WRITE, 100, 4)                              # 0x40045564
UI_SET_KEYBIT = _ioc(_IOC_WRITE, 101, 4)                             # 0x40045565
UI_SET_ABSBIT = _ioc(_IOC_WRITE, 103, 4)                             # 0x40045567
UI_SET_PROPBIT = _ioc(_IOC_WRITE, 110, 4)                            # 0x4004556e


def encode_event(event_type: int, code: int, value: int) -> bytes:
    """One ``struct input_event``. The kernel stamps the time, so the timeval is zero."""
    return struct.pack(_EVENT_FORMAT, 0, 0, int(event_type), int(code), int(value))


def decode_events(payload: bytes) -> list[tuple[int, int, int]]:
    """(type, code, value) of every ``struct input_event`` in ``payload``."""
    size = struct.calcsize(_EVENT_FORMAT)
    if len(payload) % size:
        raise ValueError(f"{len(payload)} bytes is not a whole number of input events")
    return [struct.unpack_from(_EVENT_FORMAT, payload, offset)[2:] for offset in range(0, len(payload), size)]


def encode_abs_move(x: int, y: int) -> bytes:
    return (encode_event(EV_ABS, ABS_X, x) + encode_event(EV_ABS, ABS_Y, y)
            + encode_event(EV_SYN, SYN_REPORT, 0))


def encode_button(pressed: bool) -> bytes:
    return encode_event(EV_KEY, BTN_LEFT, 1 if pressed else 0) + encode_event(EV_SYN, SYN_REPORT, 0)


def absolute_value(pixel: int, extent: int) -> int:
    """Absolute pointer value of root pixel ``pixel`` on an axis of ``extent`` pixels.

    The X root spans every monitor, so one range covers the whole logical desktop, including a
    monitor placed at a non-zero origin. Pixel 0 maps to 0 and pixel extent-1 to UINPUT_ABS_MAX.
    """
    pixel = int(pixel)
    if extent < 1 or not 0 <= pixel < extent:
        raise UserInputError(f"pixel {pixel} is outside the desktop (extent {extent})")
    if extent == 1:
        return 0
    return round(pixel * UINPUT_ABS_MAX / (extent - 1))


def absolute_step(error_px: int, extent: int) -> int:
    """Absolute units that move the pointer by ``error_px`` root pixels on an axis of ``extent``."""
    if extent <= 1:
        return 0
    return round(int(error_px) * UINPUT_ABS_MAX / (extent - 1))


def _clamp_absolute(value: int) -> int:
    return min(max(int(value), 0), UINPUT_ABS_MAX)


def _within(observed, target, tolerance: int = POINTER_TOLERANCE_PX) -> bool:
    return abs(observed[0] - target[0]) <= tolerance and abs(observed[1] - target[1]) <= tolerance


def _fcntl_ioctl(fd, request, arg):
    import fcntl  # Linux only; imported here so the module still loads on other hosts

    return fcntl.ioctl(fd, request, arg)


class UinputDevice:
    """A uinput virtual absolute pointer, created with raw ioctls (no third-party module).

    The owner calls ``close`` (which destroys the kernel device); ``close`` is also registered
    at exit. ``ioctl``, ``open_fn``, ``write_fn`` and ``close_fn`` are injection points for host
    tests. Opening /dev/uinput needs membership of the ``input`` group on the DentoBot hosts.
    """

    def __init__(self, *, path=UINPUT_PATH, ioctl=None, open_fn=None, write_fn=None, close_fn=None):
        self._path = path
        self._ioctl = ioctl or _fcntl_ioctl
        self._open = open_fn or os.open
        self._write = write_fn or os.write
        self._close = close_fn or os.close
        self._fd = None

    def create(self) -> None:
        if self._fd is not None:
            raise UserInputError("the uinput pointer already exists")
        try:
            fd = self._open(self._path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            raise UserInputError(
                f"cannot open {self._path}: {exc} (the user must be in group input)"
            ) from exc
        try:
            for event_type in (EV_SYN, EV_KEY, EV_ABS):
                self._ioctl(fd, UI_SET_EVBIT, event_type)
            self._ioctl(fd, UI_SET_KEYBIT, BTN_LEFT)
            for code in (ABS_X, ABS_Y):
                self._ioctl(fd, UI_SET_ABSBIT, code)
            self._ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_POINTER)
            for code in (ABS_X, ABS_Y):
                # code, then absinfo: value, minimum, maximum, fuzz, flat, resolution
                self._ioctl(fd, UI_ABS_SETUP, struct.pack(_ABS_SETUP_FORMAT, code, 0, 0, UINPUT_ABS_MAX, 0, 0, 0))
            name = UINPUT_DEVICE_NAME.encode("ascii")
            setup = struct.pack(_SETUP_FORMAT, BUS_VIRTUAL, _UINPUT_VENDOR, _UINPUT_PRODUCT, 1, name, 0)
            self._ioctl(fd, UI_DEV_SETUP, setup)
            self._ioctl(fd, UI_DEV_CREATE, 0)
        except OSError as exc:
            self._close(fd)
            raise UserInputError(f"cannot create the uinput pointer on {self._path}: {exc}") from exc
        self._fd = fd

    def _emit(self, payload: bytes) -> None:
        if self._fd is None:
            raise UserInputError("the uinput pointer is not created")
        try:
            self._write(self._fd, payload)
        except OSError as exc:
            raise UserInputError(f"uinput write failed: {exc}") from exc

    def abs_move(self, x: int, y: int) -> None:
        for value in (x, y):
            if type(value) is not int or not 0 <= value <= UINPUT_ABS_MAX:
                raise UserInputError(f"absolute value {value!r} is outside 0..{UINPUT_ABS_MAX}")
        self._emit(encode_abs_move(x, y))

    def button(self, pressed: bool) -> None:
        self._emit(encode_button(bool(pressed)))

    def close(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            self._ioctl(fd, UI_DEV_DESTROY, 0)
        except OSError as exc:
            raise UserInputError(f"cannot destroy the uinput pointer: {exc}") from exc
        finally:
            self._close(fd)


def write_atomic_json(path, payload) -> None:
    """Write JSON in one step (temporary name, then rename) so a reader never sees a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, path)


class RelayTransport:
    """Pointer requests to the host helper that owns the uinput device, exchanged in ``root``.

    The harness writes ``requests/<name>.json`` and waits for ``responses/<name>.json``. The helper
    writes ``ready.json`` once the device exists, or ``failed.json`` if it could not create it.
    Names sort by time, so a restarted harness continues on the same relay.
    """

    def __init__(self, root, *, ready_timeout_sec=None, response_timeout_sec=None):
        self._root = Path(root)
        self._count = 0
        self._response_timeout = (RELAY_RESPONSE_TIMEOUT_SEC if response_timeout_sec is None
                                  else float(response_timeout_sec))
        ready = self._wait_for_ready(RELAY_READY_TIMEOUT_SEC if ready_timeout_sec is None
                                     else float(ready_timeout_sec))
        if ready.get("abs_max") != UINPUT_ABS_MAX:
            raise UserInputError(f"uinput helper reports abs_max {ready.get('abs_max')!r}; "
                                 f"expected {UINPUT_ABS_MAX}")

    def _wait_for_ready(self, timeout: float) -> dict:
        deadline = _NOW() + timeout
        while True:
            failed = self._root / "failed.json"
            if failed.is_file():
                raise UserInputError("uinput helper could not create the pointer: "
                                     + str(_read_json(failed).get("error")))
            ready = self._root / "ready.json"
            if ready.is_file():
                return _read_json(ready)
            if _NOW() >= deadline:
                raise UserInputError(f"uinput helper is not ready after {timeout:.0f} s ({ready} is missing)")
            _SLEEP(RELAY_POLL_SEC)

    def _send(self, op: str, **fields) -> None:
        self._count += 1
        name = f"{time.time_ns():020d}-{os.getpid():07d}-{self._count:06d}.json"
        write_atomic_json(self._root / "requests" / name, {"op": op, "name": name, "utc": utc_now(), **fields})
        response_path = self._root / "responses" / name
        deadline = _NOW() + self._response_timeout
        while not response_path.is_file():
            if _NOW() >= deadline:
                raise UserInputError(f"uinput helper did not answer {op} {name} within "
                                     f"{self._response_timeout:.0f} s")
            _SLEEP(RELAY_POLL_SEC)
        response = _read_json(response_path)
        if not response.get("ok"):
            raise UserInputError(f"uinput helper refused {op}: {response.get('error')}")

    def abs_move(self, x: int, y: int) -> None:
        self._send("abs_move", x=int(x), y=int(y))

    def button(self, pressed: bool) -> None:
        self._send("button", button=1, pressed=bool(pressed))


def _read_json(path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UserInputError(f"cannot read the uinput relay file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise UserInputError(f"the uinput relay file {path} is not a JSON object")
    return payload


class UinputPointer:
    """Moves and clicks a uinput pointer and verifies every move at X level.

    ``transport`` provides ``abs_move(x, y)`` and ``button(pressed)``: a UinputDevice in this
    process, or a RelayTransport. ``observe()`` returns the X root pointer (x, y) from
    XQueryPointer. ``desktop`` is the X root size, which covers every monitor.
    """

    def __init__(self, transport, observe, desktop):
        width, height = int(desktop[0]), int(desktop[1])
        if width < 1 or height < 1:
            raise UserInputError(f"the X root reports an empty desktop {width}x{height}")
        self._transport = transport
        self._observe = observe
        self._width, self._height = width, height
        self.verified = None   # (x, y) of the last move that landed within tolerance
        self.last_move = None  # evidence of the last move, for the ledger

    def move(self, x, y) -> dict:
        x, y = int(x), int(y)
        if not (0 <= x < self._width and 0 <= y < self._height):
            raise UserInputError(f"target ({x}, {y}) is outside the desktop {self._width}x{self._height}")
        self.verified = None
        ax, ay = absolute_value(x, self._width), absolute_value(y, self._height)
        attempts = []
        for correction in range(POINTER_CORRECTIONS + 1):
            self._transport.abs_move(ax, ay)
            observed = self._settle((x, y))
            attempts.append({"abs_xy": [ax, ay], "observed_xy": list(observed)})
            if _within(observed, (x, y)):
                self.verified = (x, y)
                self.last_move = {"target_xy": [x, y], "attempts": attempts, "landed": True}
                return self.last_move
            if correction < POINTER_CORRECTIONS:
                ax = _clamp_absolute(ax + absolute_step(x - observed[0], self._width))
                ay = _clamp_absolute(ay + absolute_step(y - observed[1], self._height))
        self.last_move = {"target_xy": [x, y], "attempts": attempts, "landed": False}
        raise UserInputError(
            f"pointer did not reach ({x}, {y}) after {POINTER_CORRECTIONS} corrective uinput moves; "
            f"it is at {tuple(attempts[-1]['observed_xy'])} (tolerance {POINTER_TOLERANCE_PX} px)"
        )

    def _settle(self, target):
        began = _NOW()
        observed = tuple(self._observe())
        while not _within(observed, target) and _NOW() - began < POINTER_SETTLE_SEC:
            _SLEEP(POINTER_SETTLE_STEP_SEC)
            observed = tuple(self._observe())
        return observed

    def button(self, button, pressed) -> None:
        if type(button) is not int or button != 1:
            raise UserInputError(f"uinput mode presses only the left button (1); got {button!r}")
        if pressed:
            if self.verified is None:
                raise UserInputError("no verified pointer position before the press; no press sent")
            observed = tuple(self._observe())
            if not _within(observed, self.verified):
                raise UserInputError(f"pointer is at {observed}, not at the verified {self.verified}; "
                                     "no press sent")
        self._transport.button(bool(pressed))


class UinputBackend:
    """XTestBackend for window and pointer queries; motion and buttons go through a UinputPointer."""

    def __init__(self, xbackend, pointer: UinputPointer):
        self._x = xbackend
        self._pointer = pointer

    def pointer(self) -> tuple[int, int]:
        return self._x.pointer()

    def pointer_chain(self) -> list[int]:
        return self._x.pointer_chain()

    def active_window(self) -> int:
        return self._x.active_window()

    def window_name(self, window: int) -> str:
        return self._x.window_name(window)

    def activate_window(self, window: int) -> None:
        self._x.activate_window(window)

    @property
    def last_move(self):
        return self._pointer.last_move

    def move(self, x: int, y: int) -> None:
        self._pointer.move(x, y)

    def button(self, button: int, pressed: bool) -> None:
        self._pointer.button(button, pressed)


_UINPUT_BACKEND = None


def _close_at_exit(device: UinputDevice) -> None:
    try:
        device.close()
    except Exception as exc:  # the process is exiting: report the failure, do not raise
        print(f"uinput pointer close failed: {exc}", file=sys.stderr)


def get_uinput_backend() -> UinputBackend:
    """The uinput backend for this process, built once: relay to the host helper, or a local device."""
    global _UINPUT_BACKEND
    if _UINPUT_BACKEND is None:
        xbackend = get_backend()
        desktop = xbackend.desktop_size()
        relay_dir = os.environ.get(UINPUT_RELAY_ENV, "").strip()
        if relay_dir:
            transport = RelayTransport(relay_dir)
        else:
            device = UinputDevice()
            device.create()
            atexit.register(_close_at_exit, device)
            _SLEEP(UINPUT_SETTLE_SEC)
            transport = device
        pointer = UinputPointer(transport, observe=xbackend.pointer, desktop=desktop)
        _UINPUT_BACKEND = UinputBackend(xbackend, pointer)
    return _UINPUT_BACKEND


def pointer_backend(mode: str):
    """The backend that moves the pointer and presses buttons for ``mode``."""
    if mode == "uinput":
        return get_uinput_backend()
    return get_backend()


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
            result = {"hit": bool(hit), "pointer_xy": pointer, "chain": chain,
                      "elapsed_sec": round(_NOW() - began, 3)}
            move = getattr(backend, "last_move", None)  # uinput only: the verified move's record
            if move is not None:
                result["move"] = move
            return result


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
        record = {
            "attempt": attempt,
            "hit": last["hit"],
            "pointer_xy": list(last["pointer_xy"]),
            "chain": [_hex(window) for window in last["chain"]],
            "elapsed_sec": last["elapsed_sec"],
            "active_window_after": _hex(backend.active_window()),
        }
        if "move" in last:
            record["uinput_move"] = last["move"]
        evidence["attempts"].append(record)
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
        backend = pointer_backend(mode)
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
        backend = pointer_backend(mode)
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


# --- combo rows: choose an item in a QComboBox popup by real presses ----------------------------
#
# The 6.0 "Active registry slot" combo is a tree-backed list: its model holds one top-level root
# ('Scene') and the selectable items are that root's children. A list row therefore has to be
# indexed under the combo's root index. Indexing it at the top level gives an invalid index, an
# empty visual rect, and a press at the popup corner, which selects row 0 (2026-10-09 B2 run).

POPUP_OPEN_TIMEOUT_SEC = 3.0
POPUP_ROW_TIMEOUT_SEC = 3.0
POPUP_STABLE_SEC = 0.3
POPUP_STEP_SEC = 0.05
SELECT_HOLD_SEC = 0.25
SELECT_DELIVERY_TIMEOUT_SEC = 3.0


def combo_row_index(combo, row: int):
    """Model index of list row ``row`` of a QComboBox, under the combo's root index."""
    index = combo.model().index(int(row), 0, combo.rootModelIndex())
    if not index.isValid():
        raise UserInputError(f"combo row {row} has no valid index under the combo's root")
    return index


def _popup_row_sample(combo, row: int, qt) -> dict:
    """Geometry of list row ``row`` in the open popup: its rect, the popup box and the press point."""
    view = combo.view()
    container = view.window()
    rect = view.visualRect(combo_row_index(combo, row))
    origin = container.mapToGlobal(qt.QPoint(0, 0))
    box = [int(origin.x()), int(origin.y()), int(container.width), int(container.height)]
    sample = {"rect": [int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())], "box": box,
              "valid": bool(rect.isValid()) and int(rect.width()) > 0 and int(rect.height()) > 0,
              "inside": False, "global_xy": None}
    if not sample["valid"]:
        return sample
    point = view.viewport().mapToGlobal(rect.center())
    x, y = int(point.x()), int(point.y())
    sample["global_xy"] = [x, y]
    sample["inside"] = box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]
    return sample


# A QComboBox popup shows at most maxVisibleItems rows (Qt default 10). The 11th row of the stage combo
# ("6 · Robot Placement") is below the visible list, so the list has to be scrolled with real wheel notches.
POPUP_WHEEL_UP = 4
POPUP_WHEEL_DOWN = 5
POPUP_WHEEL_MAX_NOTCHES = 30


def _scroll_popup_to_row(combo, row: int, *, backend, qt, dpr: float, step, label: str, mode: str,
                         popup_window: int) -> int:
    """Scroll the open popup list with real wheel notches until row ``row`` lies inside the popup.

    The pointer is moved over the popup list first, and each notch is only sent while the popup window is in the
    pointer chain. Returns the number of notches. Refuses loudly when the row never comes into the popup.
    """
    view = combo.view()
    viewport = view.viewport()
    notches = 0
    began = _NOW()
    moved = False
    while True:
        sample = _popup_row_sample(combo, row, qt)
        if sample["inside"]:
            if notches:
                step("popup_scroll", notches=notches, rect=sample["rect"], box=sample["box"])
            return notches
        if not sample["valid"]:
            if _NOW() - began >= POPUP_ROW_TIMEOUT_SEC:
                return notches  # no geometry: the caller's stable-geometry wait refuses it with its own message
            _pump_until(_NOW() + POPUP_STEP_SEC)  # the row's geometry may still be settling
            continue
        if notches >= POPUP_WHEEL_MAX_NOTCHES:
            raise UserInputError(f"{label}: row {row} did not come into the popup after {notches} wheel "
                                 f"notches (last {sample}); no row press sent")
        if mode == "uinput":
            raise UserInputError(f"{label}: row {row} is outside the visible popup list and the wheel is not sent "
                                 "in uinput mode (it presses the left button only); use xtest mode")
        if not moved:
            centre = viewport.mapToGlobal(_value(viewport, "rect").center())
            backend.move(round(int(centre.x()) * dpr), round(int(centre.y()) * dpr))
            _pump_until(_NOW() + 0.1)
            moved = True
        chain = list(backend.pointer_chain())
        if popup_window not in chain:
            raise UserInputError(f"{label}: the pointer over the popup list is not in the popup window "
                                 f"{_hex(popup_window)} (chain {[_hex(w) for w in chain]}); no wheel sent")
        rect = view.visualRect(combo_row_index(combo, row))
        below = int(rect.y()) > 0  # a row that is not inside lies either above the list top or below it
        backend.button(POPUP_WHEEL_DOWN if below else POPUP_WHEEL_UP, True)
        backend.button(POPUP_WHEEL_DOWN if below else POPUP_WHEEL_UP, False)
        notches += 1
        _pump_until(_NOW() + POPUP_STEP_SEC)


def select_combo_item(combo, row: int, expected_text: str, *, mode: str, evidence=None) -> dict:
    """Select list row ``row`` of ``combo`` by real presses on its popup, and verify the result.

    The combo is opened by a real press. The row is pressed only when the popup is visible, the row
    has a valid rect that is stable for POPUP_STABLE_SEC and lies inside the popup window (a row below the
    visible list is first brought into the popup with real wheel notches over the list, xtest mode only), the
    pointer chain at the row contains the popup's X window, and Qt reports the popup list under
    the row. The press is held for SELECT_HOLD_SEC and released. The combo must then show ``row``
    with ``expected_text``, or UserInputError is raised. No programmatic selection is made.
    """
    if mode not in ("xtest", "demo", "uinput"):
        raise UserInputError(f"combo selection needs real pointer input; mode {mode!r} is not allowed")
    qt, slicer = _runtime()
    label = f"Select '{expected_text}' in {_object_name(combo) or _class_name(combo)}"
    record = {"navigation": None, "action": "combo row selection", "label": label, "row": int(row),
              "expected_text": expected_text, "mode": mode, "steps": []}

    def step(name, **data):
        record["steps"].append({"step": name, "utc": utc_now(), **data})

    x_activation: dict = {}
    try:
        if not 0 <= int(row) < int(combo.count):
            raise UserInputError(f"{label}: row {row} is outside the combo (count {int(combo.count)})")
        model_text = str(combo.model().data(combo_row_index(combo, row)) or "")
        if str(combo.itemText(int(row))) != expected_text or model_text != expected_text:
            raise UserInputError(f"{label}: row {row} reads {str(combo.itemText(int(row)))!r}, "
                                 f"model {model_text!r}; expected {expected_text!r}")
        before = int(combo.currentIndex)
        _preflight(combo, label)
        _raise_and_activate(combo, slicer)
        logical, dpr, physical = _target(combo, qt, label)
        backend = pointer_backend(mode)
        start = backend.pointer()
        target = _native_window(_value(combo, "window"), label)
        x_activation["target_window"] = _hex(target)
        _x_activate_and_confirm(backend, combo, slicer, target, physical, label, x_activation)
        found = qt.QApplication.widgetAt(qt.QPoint(*logical))
        if not _is_widget_or_descendant(found, combo):
            raise UserInputError(f"{label}: covered by {_describe(found)}")
        backend.button(1, True)
        _pump_until(_NOW() + PRESS_HOLD_SEC)
        backend.button(1, False)
        opened = _wait_for(lambda: bool(combo.view().isVisible()), POPUP_OPEN_TIMEOUT_SEC)
        step("open_press", popup_visible=bool(opened), physical_xy=list(physical))
        if not opened:
            raise UserInputError(f"{label}: the popup did not open after a real press; no row press sent")
        popup_window = int(combo.view().window().winId())
        if not _popup_row_sample(combo, row, qt)["inside"]:
            _scroll_popup_to_row(combo, row, backend=backend, qt=qt, dpr=dpr, step=step, label=label,
                                 mode=mode, popup_window=popup_window)
        began = _NOW()
        last, stable_since, sample = None, None, None
        while True:
            _pump_once()
            sample = _popup_row_sample(combo, row, qt)
            key = (tuple(sample["rect"]), tuple(sample["box"])) if sample["inside"] else None
            if key is not None and key == last:
                stable_since = stable_since if stable_since is not None else _NOW()
                if _NOW() - stable_since >= POPUP_STABLE_SEC:
                    break
            else:
                last, stable_since = key, None
            if _NOW() - began >= POPUP_ROW_TIMEOUT_SEC:
                raise UserInputError(f"{label}: row {row} has no stable valid geometry inside the popup "
                                     f"after {POPUP_ROW_TIMEOUT_SEC:.0f} s (last {sample}); no row press sent")
            _SLEEP(POPUP_STEP_SEC)
        step("row_stable", rect=sample["rect"], box=sample["box"], global_xy=sample["global_xy"],
             stable_after_s=round(_NOW() - began, 3))
        point = sample["global_xy"]
        backend.move(round(point[0] * dpr), round(point[1] * dpr))
        _pump_until(_NOW() + 0.1)
        chain = list(backend.pointer_chain())
        row_widget = qt.QApplication.widgetAt(qt.QPoint(*point))
        step("row_hit", pointer_xy=list(backend.pointer()), chain=[_hex(w) for w in chain],
             popup_window=_hex(popup_window), widget_at_row=_describe(row_widget))
        if popup_window not in chain:
            raise UserInputError(f"{label}: the pointer at row {row} is not over the popup window "
                                 f"{_hex(popup_window)} (chain {[_hex(w) for w in chain]}); no press sent")
        if not _is_widget_or_descendant(row_widget, combo.view()):
            raise UserInputError(f"{label}: Qt reports {_describe(row_widget)} at row {row}, not the popup "
                                 "list; no press sent")
        backend.button(1, True)
        _pump_until(_NOW() + SELECT_HOLD_SEC)
        backend.button(1, False)
        selected = _wait_for(lambda: int(combo.currentIndex) == int(row)
                             and str(combo.currentText) == expected_text, SELECT_DELIVERY_TIMEOUT_SEC)
        after = int(combo.currentIndex)
        step("release", currentIndex_before=before, currentIndex_after=after,
             currentText=str(combo.currentText), popup_visible=bool(combo.view().isVisible()),
             selected=bool(selected))
        if not selected:
            raise UserInputError(f"{label}: the press did not select row {row} (currentIndex {after}, "
                                 f"text {str(combo.currentText)!r}); no other selection is made")
    except UserInputError as refusal:
        _append_evidence(evidence, {**record, "delivered": False, "refused": str(refusal),
                                    "x_activation": x_activation})
        raise
    record.update(delivered=True, currentIndex_before=before, currentIndex_after=after,
                  x_activation=x_activation, physical_xy=list(physical), logical_xy=list(logical),
                  device_pixel_ratio=dpr, pointer_start_xy=list(start), utc=utc_now())
    _append_evidence(evidence, record)
    return record


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-") or "control"
