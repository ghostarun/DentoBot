"""Host tests for Testing/step6_user_input.py (S6-ADVISOR-GUI-01 real-user input).

No Qt, Slicer or X server is used. Fake widgets, a fake window stack, a fake XTest
backend, a fake libX11/libXtst pair and a fake clock stand in for them. The assertions
cover the Qt and X-level preconditions, the EWMH activation request, the window-chain
hit test, the physical input sequence, delivery confirmation, the demo overlay order,
the ledger evidence, and the absence of any ``click()`` fallback in xtest and demo.
"""

from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step6_user_input as ui  # noqa: E402

ROOT = 99             # the X root window
MAIN_WINDOW = 0x1000  # the Slicer main window's native X window
MAIN_CHILD = 0x1001   # a native descendant of it (for example the VTK render window)
EXTERNAL = 0x4000001  # another application's top-level window (for example T3)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)

    def emit(self):
        for slot in list(self.slots):
            slot()


class FakePoint:
    def __init__(self, x, y):
        self._x, self._y = int(x), int(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class FakeRect:
    def __init__(self, width, height):
        self._w, self._h = width, height

    def center(self):
        return FakePoint(self._w // 2, self._h // 2)

    def left(self):
        return 0

    def topLeft(self):
        return FakePoint(0, 0)


class FakeWindowish:
    """Records geometry, flags and show/hide (demo overlay windows and the main window)."""

    def __init__(self, env, label, text=""):
        self.env, self.label, self.text = env, label, text
        self.flags = None
        self.attributes = {}
        self.shown = False
        self.height = 30
        self.raised = 0
        self.activated = 0

    def setWindowFlags(self, flags):
        self.flags = flags

    def setAttribute(self, attribute, value):
        self.attributes[attribute] = value

    def setFocusPolicy(self, policy):
        self.focus_policy = policy

    def setStyleSheet(self, sheet):
        self.stylesheet = sheet

    def setGeometry(self, *geometry):
        self.geometry = geometry

    def move(self, x, y):
        self.position = (x, y)

    def adjustSize(self):
        pass

    def show(self):
        self.shown = True
        self.env.log.append(("overlay_show", self.label))

    def hide(self):
        if self.shown:
            self.env.log.append(("overlay_hide", self.label))
        self.shown = False

    def deleteLater(self):
        pass

    def raise_(self):
        self.raised += 1

    def activateWindow(self):
        self.activated += 1


class FakeWidget:
    def __init__(self, name, *, parent=None, cls="QPushButton", text="Press me", x=0, y=0,
                 width=100, height=40, visible=True, enabled=True, collapsed=False, native_id=0):
        self.objectName = name
        self.text = text
        self.visible = visible
        self.enabled = enabled
        self.collapsed = collapsed
        self.width = width
        self.height = height
        self._parent = parent
        self._class = cls
        self._origin = (x, y)
        self._native_id = native_id
        self.clicked = FakeSignal()
        self.clicks = 0
        self.raised = 0
        self.activated = 0
        self._inherits = {cls, "QWidget", "QObject"}
        if cls == "ctkCollapsibleButton":
            self._inherits.add("ctkCollapsibleButton")
        self.checkable = False
        self.checked = False
        self._style = None

    def style(self):
        return self._style if self._style is not None else FakeStyle({})

    @property
    def rect(self):
        return FakeRect(self.width, self.height)

    def parent(self):
        return self._parent

    def className(self):
        return self._class

    def inherits(self, name):
        return name in self._inherits

    def winId(self):
        return self._native_id

    def window(self):
        node = self
        while node.parent() is not None:
            node = node.parent()
        return node

    def isAncestorOf(self, other):
        node = other.parent() if other is not None and hasattr(other, "parent") else None
        while node is not None:
            if node is self:
                return True
            node = node.parent()
        return False

    def mapToGlobal(self, point):
        return FakePoint(self._origin[0] + point.x(), self._origin[1] + point.y())

    def click(self):
        self.clicks += 1

    def raise_(self):
        self.raised += 1

    def activateWindow(self):
        self.activated += 1


class FakeScrollArea(FakeWidget):
    def __init__(self, name, **kwargs):
        super().__init__(name, cls="QScrollArea", **kwargs)
        self.ensure_calls = []

    def ensureWidgetVisible(self, widget, *margins):
        self.ensure_calls.append((widget, margins))


_TARGET = object()  # widgetAt() returns the control itself (nothing covers it in Qt)


class FakeEnv:
    """Shared record of everything the fake Qt and the fake backend did, in order."""

    def __init__(self, target, *, dpr=1.0, covered_by=_TARGET):
        self.log = []
        self.target = target
        self.dpr = dpr
        self.covered_by = covered_by
        self.main = FakeWindowish(self, "main")

    def widget_at(self, point):
        return self.target if self.covered_by is _TARGET else self.covered_by


class FakeQApplication:
    def __init__(self, env):
        self.env = env

    def processEvents(self):
        self.env.log.append(("pump",))

    def widgetAt(self, point):
        self.env.log.append(("widgetAt", point.x(), point.y()))
        return self.env.widget_at(point)

    def screenAt(self, point):
        return SimpleNamespace(devicePixelRatio=self.env.dpr)


def make_qt(env):
    flags = SimpleNamespace(
        Tool=0x0B, FramelessWindowHint=0x0800, WindowStaysOnTopHint=0x00040000,
        WindowTransparentForInput=0x00200000, WA_TranslucentBackground=120,
        WA_ShowWithoutActivating=197, NoFocus=0,
    )

    class QFrame(FakeWindowish):
        def __init__(self):
            super().__init__(env, "frame")

    class QLabel(FakeWindowish):
        def __init__(self, text=""):
            super().__init__(env, "caption", text)

    class QPoint(FakePoint):
        pass

    class QStyleOptionButton:
        def initFrom(self, widget):
            self.initialised_from = widget

    style_names = SimpleNamespace(
        SE_CheckBoxIndicator="indicator", SE_CheckBoxContents="contents",
        SE_RadioButtonIndicator="radio-indicator", SE_RadioButtonContents="radio-contents",
        CC_SpinBox="spinbox-control", SC_SpinBoxUp="spinbox-up", SC_SpinBoxDown="spinbox-down",
    )

    class QStyleOptionSpinBox:
        pass

    return SimpleNamespace(
        QApplication=FakeQApplication(env), QPoint=QPoint, QFrame=QFrame, QLabel=QLabel,
        Qt=flags, QStyle=style_names, QStyleOptionButton=QStyleOptionButton,
        QStyleOptionSpinBox=QStyleOptionSpinBox,
    )


class FakeBackend:
    """Stands in for XTestBackend: physical input, a window stack and EWMH activation.

    ``covering`` is the window chain under the pointer until activation takes effect.
    Activation number ``reveal_on_activation`` (1 by default) clears the covering chain;
    None means no window manager ever does.
    """

    def __init__(self, env, *, follows_pointer=True, emit_on_release=True, covering=None,
                 reveal_on_activation=1, names=None):
        self.env = env
        self.position = (0, 0)
        self.events = []
        self.follows_pointer = follows_pointer
        self.emit_on_release = emit_on_release
        self.clear_chain = [MAIN_WINDOW, MAIN_CHILD]
        self.current_chain = list(covering) if covering else list(self.clear_chain)
        self.reveal_on_activation = reveal_on_activation
        self.activations = []
        self.active = 0
        self.names = {EXTERNAL: "T3 Code"} if names is None else dict(names)

    def pointer(self):
        return self.position

    def move(self, x, y):
        self.events.append(("move", int(x), int(y)))
        if self.follows_pointer:
            self.position = (int(x), int(y))

    def button(self, button, pressed):
        self.events.append(("button", int(button), bool(pressed)))
        if not pressed and self.emit_on_release:
            self.env.target.clicked.emit()

    def activate_window(self, window):
        self.activations.append(window)
        if (window == MAIN_WINDOW and self.reveal_on_activation is not None
                and len(self.activations) == self.reveal_on_activation):
            self.current_chain = list(self.clear_chain)
            self.active = window

    def pointer_chain(self):
        return list(self.current_chain)

    def active_window(self):
        return self.active

    def window_name(self, window):
        return self.names.get(window, "")


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(ui, "_NOW", fake.now)
    monkeypatch.setattr(ui, "_SLEEP", fake.sleep)
    return fake


@pytest.fixture
def harness(monkeypatch, clock):
    """Build the fake world: a visible, enabled button inside the Slicer main window."""

    def build(*, dpr=1.0, covered_by=_TARGET, follows_pointer=True, emit_on_release=True,
              covering=None, reveal_on_activation=1, x=300, y=400, width=100, height=40,
              **button_kwargs):
        window = FakeWidget("mainWindow", cls="QMainWindow", x=0, y=0, width=1200, height=800,
                            native_id=MAIN_WINDOW)
        target = FakeWidget("DENTOBOTStep6FindWorkingConfigButton", parent=window,
                            x=x, y=y, width=width, height=height, **button_kwargs)
        env = FakeEnv(target, dpr=dpr, covered_by=covered_by)
        env.main = FakeWindowish(env, "main")
        qt = make_qt(env)
        slicer = SimpleNamespace(util=SimpleNamespace(mainWindow=lambda: env.main))
        backend = FakeBackend(env, follows_pointer=follows_pointer,
                              emit_on_release=emit_on_release, covering=covering,
                              reveal_on_activation=reveal_on_activation)
        monkeypatch.setattr(ui, "_runtime", lambda: (qt, slicer))
        monkeypatch.setattr(ui, "get_backend", lambda: backend)
        return target, env, backend

    return build


def test_qt_click_mode_is_the_legacy_click_and_touches_no_x_input(harness, monkeypatch, tmp_path):
    target, env, backend = harness()
    monkeypatch.setattr(ui, "get_backend", lambda: pytest.fail("legacy mode must not open X input"))
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "Find Working Configuration", mode="qt_click", evidence=ledger)
    assert target.clicks == 1
    assert record["mode"] == "qt_click" and record["delivered"] is None
    assert json.loads(ledger.read_text().splitlines()[0])["label"] == "Find Working Configuration"


def test_xtest_click_activates_the_window_hit_tests_the_control_and_confirms_delivery(harness, tmp_path):
    target, env, backend = harness(x=300, y=400, width=100, height=40)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "Find Working Configuration", mode="xtest", evidence=ledger)
    # centre of (300..400, 400..440) in logical global coordinates is (350, 420)
    assert backend.activations == [MAIN_WINDOW]
    assert backend.events[0] == ("move", 350, 420)
    assert ("button", 1, True) in backend.events and ("button", 1, False) in backend.events
    assert backend.events.index(("button", 1, True)) < backend.events.index(("button", 1, False))
    assert target.clicked.slots == []  # the temporary delivery probe is disconnected
    assert target.clicks == 0  # no QAbstractButton.click() fallback
    assert record["delivered"] is True
    assert record["physical_xy"] == [350, 420] and record["objectName"] == target.objectName
    evidence = record["x_activation"]
    assert evidence["target_window"] == hex(MAIN_WINDOW) and evidence["hit_test"] == "pass"
    assert evidence["attempts"][0]["hit"] is True
    assert evidence["attempts"][0]["chain"][-1] == hex(MAIN_CHILD)  # a descendant of the main window
    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["mode"] == "xtest" and saved["delivered_utc"]
    assert saved["x_activation"]["hit_test"] == "pass"


@pytest.mark.parametrize("kwargs, message", [
    ({"visible": False}, "control is not visible"),
    ({"enabled": False}, "control is disabled"),
])
@pytest.mark.parametrize("mode", ["xtest", "demo"])
def test_invisible_or_disabled_controls_fail_without_activating_or_pressing(harness, mode, kwargs, message):
    target, env, backend = harness(**kwargs)
    with pytest.raises(ui.UserInputError, match=message):
        ui.user_click(target, "Start search", mode=mode)
    assert backend.activations == [] and backend.events == []
    assert target.clicks == 0


def test_control_in_a_collapsed_group_says_to_expand_it_and_expands_nothing(harness):
    target, env, backend = harness()
    group = FakeWidget("advancedGroup", cls="ctkCollapsibleButton", text="Advanced settings",
                       parent=target.parent(), collapsed=True)
    target._parent = group
    with pytest.raises(ui.UserInputError, match="not reachable without expanding Advanced settings"):
        ui.user_click(target, "Diagnose", mode="xtest")
    assert backend.events == [] and group.collapsed is True


def test_qt_covered_control_fails_before_the_press(harness):
    other = FakeWidget("dialogCancel", text="Cancel", parent=None)
    target, env, backend = harness(covered_by=other)
    with pytest.raises(ui.UserInputError, match="covered by QPushButton/dialogCancel"):
        ui.user_click(target, "Start search", mode="xtest")
    assert ("button", 1, True) not in backend.events
    assert target.clicks == 0


def test_point_with_no_qt_widget_is_reported_as_covered(harness):
    target, env, backend = harness(covered_by=None)  # widgetAt() finds no Qt widget at the point
    with pytest.raises(ui.UserInputError, match="covered by no Qt widget"):
        ui.user_click(target, "Start search", mode="xtest")
    assert ("button", 1, True) not in backend.events


def test_external_window_covering_the_pointer_fails_without_pressing_and_is_recorded(harness, tmp_path):
    target, env, backend = harness(covering=[EXTERNAL], reveal_on_activation=None)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError,
                       match=r"covered by external X window 0x4000001 T3 Code"):
        ui.user_click(target, "Start search", mode="xtest", evidence=ledger)
    assert backend.activations == [MAIN_WINDOW, MAIN_WINDOW]  # activation retried once
    assert ("button", 1, True) not in backend.events and ("button", 1, False) not in backend.events
    assert target.clicks == 0
    refusal = json.loads(ledger.read_text().splitlines()[0])
    assert refusal["delivered"] is False
    assert "covered by external X window 0x4000001" in refusal["refused"]
    assert refusal["x_activation"]["hit_test"] == "covered"
    assert [attempt["hit"] for attempt in refusal["x_activation"]["attempts"]] == [False, False]


def test_each_activation_attempt_polls_for_up_to_one_and_a_half_seconds(harness, clock):
    target, env, backend = harness(covering=[EXTERNAL], reveal_on_activation=None)
    with pytest.raises(ui.UserInputError, match="covered by external X window"):
        ui.user_click(target, "Start search", mode="xtest")
    assert clock.t >= 2 * ui.X_POLL_TIMEOUT_SEC  # two attempts, each polling the full window
    assert ui.X_POLL_TIMEOUT_SEC == 1.5 and ui.X_ACTIVATION_ATTEMPTS == 2


def test_retry_activation_presses_when_the_second_activation_takes_effect(harness, tmp_path):
    target, env, backend = harness(covering=[EXTERNAL], reveal_on_activation=2)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "Find Working Configuration", mode="xtest", evidence=ledger)
    assert backend.activations == [MAIN_WINDOW, MAIN_WINDOW]
    assert ("button", 1, True) in backend.events and target.clicks == 0
    attempts = record["x_activation"]["attempts"]
    assert [attempt["hit"] for attempt in attempts] == [False, True]
    assert record["x_activation"]["hit_test"] == "pass" and record["delivered"] is True


def test_descendant_of_the_slicer_window_under_the_pointer_is_pressed(harness):
    target, env, backend = harness()  # the default stack is the main window with a native child
    record = ui.user_click(target, "Connect", mode="xtest")
    assert record["delivered"] is True
    assert record["x_activation"]["attempts"][0]["chain"] == [hex(MAIN_WINDOW), hex(MAIN_CHILD)]


def test_demo_refuses_a_covered_control_after_removing_its_overlay(harness):
    target, env, backend = harness(covering=[EXTERNAL], reveal_on_activation=None)
    with pytest.raises(ui.UserInputError, match="covered by external X window"):
        ui.user_click(target, "Start search", mode="demo")
    assert ("button", 1, True) not in backend.events and target.clicks == 0
    assert ("overlay_hide", "frame") in env.log  # the highlight was removed, not left on top


def test_device_pixel_ratio_maps_logical_centre_to_physical_pixels(harness):
    target, env, backend = harness(dpr=2.0, x=300, y=400, width=100, height=40)
    record = ui.user_click(target, "Connect", mode="xtest")
    assert record["logical_xy"] == [350, 420]
    assert record["physical_xy"] == [700, 840]
    assert backend.events[0] == ("move", 700, 840)


def test_pointer_that_does_not_reach_the_target_fails_before_the_press(harness):
    target, env, backend = harness(follows_pointer=False)
    with pytest.raises(ui.UserInputError, match="pointer did not reach the control"):
        ui.user_click(target, "Connect", mode="xtest")
    assert ("button", 1, True) not in backend.events


def test_click_that_is_not_delivered_fails_and_disconnects(harness):
    target, env, backend = harness(emit_on_release=False)
    with pytest.raises(ui.UserInputError, match="real click not delivered"):
        ui.user_click(target, "Connect", mode="xtest")
    assert target.clicked.slots == []
    assert target.clicks == 0


def test_scroll_area_ensure_widget_visible_is_called_before_the_press(harness):
    window = FakeWidget("mainWindow", cls="QMainWindow", width=1200, height=800, native_id=MAIN_WINDOW)
    scroll = FakeScrollArea("workflowScroll", parent=window)
    content = FakeWidget("content", cls="QWidget", parent=scroll)
    target, env, backend = harness()
    target._parent = content
    ui.user_click(target, "Load Robot", mode="xtest")
    assert scroll.ensure_calls and scroll.ensure_calls[0][0] is target
    assert backend.events[0][0] == "move"


def test_demo_mode_shows_a_click_through_highlight_before_the_check_and_keeps_its_caption(harness):
    target, env, backend = harness(x=300, y=400, width=100, height=40)
    record = ui.user_click(target, "Find Working Configuration", mode="demo")
    order = [entry for entry in env.log if entry[0] in ("overlay_show", "overlay_hide", "widgetAt")]
    first_show = order.index(("overlay_show", "frame"))
    hide = order.index(("overlay_hide", "frame"))
    check = order.index(next(entry for entry in order if entry[0] == "widgetAt"))
    assert first_show < hide < check, order
    assert ("overlay_show", "caption") in env.log
    assert record["mode"] == "demo" and record["delivered"] is True
    assert backend.events.count(("button", 1, False)) == 1
    assert target.clicks == 0


def test_overlay_flags_are_click_through_and_non_activating(harness):
    env = FakeEnv(None)
    qt = make_qt(env)
    flags = ui.overlay_window_flags(qt)
    assert flags & int(qt.Qt.WindowTransparentForInput)
    assert flags & int(qt.Qt.FramelessWindowHint)


def test_xtest_failure_never_falls_back_to_click(harness, monkeypatch):
    target, env, backend = harness()

    def unavailable():
        raise ui.UserInputError("X display is unavailable")

    monkeypatch.setattr(ui, "get_backend", unavailable)
    with pytest.raises(ui.UserInputError, match="X display is unavailable"):
        ui.user_click(target, "Connect", mode="xtest")
    with pytest.raises(ui.UserInputError, match="X display is unavailable"):
        ui.user_click(target, "Connect", mode="demo")
    assert target.clicks == 0


def test_unknown_mode_is_rejected():
    with pytest.raises(ui.UserInputError):
        ui.user_click(object(), "x", mode="click")


def test_mode_defaults_to_xtest_and_rejects_unknown_values():
    assert ui.input_mode_from_env({}) == "xtest"
    assert ui.input_mode_from_env({"DENTOBOT_HEADED_INPUT": " demo "}) == "demo"
    assert ui.input_mode_from_env({"DENTOBOT_HEADED_INPUT": "qt_click"}) == "qt_click"
    with pytest.raises(ui.UserInputError, match="DENTOBOT_HEADED_INPUT must be one of"):
        ui.input_mode_from_env({"DENTOBOT_HEADED_INPUT": "click"})


class FakeCFunction:
    def __init__(self, impl):
        self.impl = impl
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.impl(*args)


class FakeLibrary:
    def __init__(self, functions):
        self._functions = functions

    def __getattr__(self, name):
        try:
            return self._functions[name]
        except KeyError:
            raise AttributeError(name) from None


class FakeXServer:
    """Answers the Xlib calls the binding makes from a scripted window stack, and records them.

    ``chain`` is the window stack under the pointer, top-level first. ``names`` answers
    _NET_WM_NAME and ``legacy_names`` answers XFetchName (WM_NAME). With ``window_manager``
    an EWMH _NET_ACTIVE_WINDOW request to the root is honoured and published on the root.
    """

    def __init__(self, *, display=1, chain=(MAIN_WINDOW, MAIN_CHILD), names=None, legacy_names=None,
                 window_manager=True, pointer=(640, 480), desktop=(1920, 1080)):
        self.calls = []
        self.display = display
        self.desktop = tuple(desktop)  # X root size, the union of every monitor
        self.chain = list(chain)
        self.names = dict(names or {})
        self.legacy_names = dict(legacy_names or {})
        self.window_manager = window_manager
        self.pointer = pointer
        self.active = 0
        self._atoms = {}
        self._atom_names = {}
        self._buffers = []

    def record(self, name, *args):
        self.calls.append((name, args))

    def atom(self, name):
        if name not in self._atoms:
            self._atoms[name] = 200 + len(self._atoms)
            self._atom_names[self._atoms[name]] = name
        return self._atoms[name]

    def _open_display(self, name):
        self.record("XOpenDisplay", name)
        return self.display

    def _root_window(self, display):
        self.record("XDefaultRootWindow", display)
        return ROOT

    def _query_pointer(self, display, window, root_return, child_return, root_x, root_y,
                       win_x, win_y, mask):
        self.record("XQueryPointer", window)
        if window == ROOT:
            child = self.chain[0] if self.chain else 0
        elif window in self.chain and self.chain.index(window) + 1 < len(self.chain):
            child = self.chain[self.chain.index(window) + 1]
        else:
            child = 0
        root_return.contents.value = ROOT
        child_return.contents.value = child
        root_x.contents.value, root_y.contents.value = self.pointer
        return 1

    def _flush(self, display):
        self.record("XFlush", display)
        return 1

    def _default_screen(self, display):
        self.record("XDefaultScreen", display)
        return 0

    def _display_width(self, display, screen):
        self.record("XDisplayWidth", display, screen)
        return self.desktop[0]

    def _display_height(self, display, screen):
        self.record("XDisplayHeight", display, screen)
        return self.desktop[1]

    def _intern_atom(self, display, name, only_if_exists):
        self.record("XInternAtom", name.decode("ascii"))
        return self.atom(name.decode("ascii"))

    def _send_event(self, display, window, propagate, mask, event_address):
        message = ui.ClientMessageEvent.from_address(event_address)
        self.record("XSendEvent", window, propagate, mask, message.type, message.window,
                    message.message_type, message.format, tuple(message.data))
        if (self.window_manager and window == ROOT
                and message.message_type == self.atom("_NET_ACTIVE_WINDOW")):
            self.active = int(message.window)
        return 1

    def _raise_window(self, display, window):
        self.record("XRaiseWindow", display, window)
        return 1

    def _get_window_property(self, display, window, atom, offset, length, delete, req_type,
                             actual_type, actual_format, nitems, remaining, prop):
        name = self._atom_names.get(atom, "")
        self.record("XGetWindowProperty", window, name)
        actual_type.contents.value = 0
        actual_format.contents.value = 0
        nitems.contents.value = 0
        remaining.contents.value = 0
        prop.contents.value = 0
        if name == "_NET_ACTIVE_WINDOW" and window == ROOT and self.active:
            data = (ctypes.c_ulong * 1)(self.active)
            self._buffers.append(data)
            prop.contents.value = ctypes.addressof(data)
            nitems.contents.value = 1
            actual_format.contents.value = 32
        elif name == "_NET_WM_NAME" and window in self.names:
            raw = self.names[window].encode("utf-8")
            data = ctypes.create_string_buffer(raw)
            self._buffers.append(data)
            prop.contents.value = ctypes.addressof(data)
            nitems.contents.value = len(raw)
            actual_format.contents.value = 8
        return 0

    def _fetch_name(self, display, window, name_return):
        self.record("XFetchName", window)
        if window in self.legacy_names:
            raw = self.legacy_names[window].encode("utf-8")
            data = ctypes.create_string_buffer(raw)
            self._buffers.append(data)
            name_return.contents.value = ctypes.addressof(data)
            return 1
        return 0

    def _free(self, pointer):
        self.record("XFree")
        return 1

    def _query_extension(self, display, events, errors, major, minor):
        self.record("XTestQueryExtension", display)
        return 1

    def _motion(self, display, screen, x, y, delay):
        self.record("XTestFakeMotionEvent", display, screen, x, y, delay)
        self.pointer = (x, y)
        return 1

    def _button(self, display, button, pressed, delay):
        self.record("XTestFakeButtonEvent", display, button, pressed, delay)
        return 1

    def libraries(self):
        xlib = FakeLibrary({
            "XOpenDisplay": FakeCFunction(self._open_display),
            "XDefaultRootWindow": FakeCFunction(self._root_window),
            "XQueryPointer": FakeCFunction(self._query_pointer),
            "XFlush": FakeCFunction(self._flush),
            "XInternAtom": FakeCFunction(self._intern_atom),
            "XSendEvent": FakeCFunction(self._send_event),
            "XRaiseWindow": FakeCFunction(self._raise_window),
            "XGetWindowProperty": FakeCFunction(self._get_window_property),
            "XFetchName": FakeCFunction(self._fetch_name),
            "XFree": FakeCFunction(self._free),
            "XDefaultScreen": FakeCFunction(self._default_screen),
            "XDisplayWidth": FakeCFunction(self._display_width),
            "XDisplayHeight": FakeCFunction(self._display_height),
        })
        xtst = FakeLibrary({
            "XTestQueryExtension": FakeCFunction(self._query_extension),
            "XTestFakeMotionEvent": FakeCFunction(self._motion),
            "XTestFakeButtonEvent": FakeCFunction(self._button),
        })
        return xlib, xtst


def test_xtest_binding_issues_the_expected_xlib_and_xtest_sequence():
    server = FakeXServer()
    backend = ui.XTestBackend(*server.libraries())
    assert backend.pointer() == (640, 480)
    backend.move(350, 420)
    backend.button(1, True)
    backend.button(1, False)
    names = [name for name, _args in server.calls]
    assert names[0] == "XOpenDisplay" and names.count("XOpenDisplay") == 1
    assert names[1] == "XTestQueryExtension"
    motion = server.calls.index(("XTestFakeMotionEvent", (1, -1, 350, 420, 0)))
    press = server.calls.index(("XTestFakeButtonEvent", (1, 1, True, 0)))
    release = server.calls.index(("XTestFakeButtonEvent", (1, 1, False, 0)))
    assert motion < press < release


def test_pointer_chain_descends_from_the_root_to_the_deepest_window():
    server = FakeXServer(chain=[0x1000, 0x1001, 0x1002])
    backend = ui.XTestBackend(*server.libraries())
    assert backend.pointer_chain() == [0x1000, 0x1001, 0x1002]
    queries = [args[0] for name, args in server.calls if name == "XQueryPointer"]
    assert queries == [ROOT, 0x1000, 0x1001, 0x1002]


def test_activation_is_an_ewmh_client_message_to_the_root_then_xraisewindow():
    server = FakeXServer(chain=[MAIN_WINDOW])
    backend = ui.XTestBackend(*server.libraries())
    backend.activate_window(MAIN_WINDOW)
    sends = [args for name, args in server.calls if name == "XSendEvent"]
    assert len(sends) == 1
    window, propagate, mask, msg_type, msg_window, msg_atom, fmt, data = sends[0]
    assert window == ROOT and propagate == 0
    assert mask == (1 << 20) | (1 << 19)  # SubstructureRedirectMask | SubstructureNotifyMask
    assert msg_type == 33 and msg_window == MAIN_WINDOW and fmt == 32
    assert msg_atom == server.atom("_NET_ACTIVE_WINDOW")
    assert data[0] == 2  # EWMH source indication: pager/taskbar (a user action)
    assert data[1] == 0  # timestamp: CurrentTime
    names = [name for name, _args in server.calls]
    assert names.index("XInternAtom") < names.index("XSendEvent") < names.index("XRaiseWindow")
    assert names[-1] == "XFlush"
    assert ("XRaiseWindow", (1, MAIN_WINDOW)) in server.calls


def test_active_window_is_read_back_from_the_root_after_activation():
    server = FakeXServer(chain=[MAIN_WINDOW])
    backend = ui.XTestBackend(*server.libraries())
    assert backend.active_window() == 0
    backend.activate_window(MAIN_WINDOW)
    assert backend.active_window() == MAIN_WINDOW


def test_window_name_prefers_net_wm_name_and_falls_back_to_wm_name():
    server = FakeXServer(chain=[EXTERNAL], names={EXTERNAL: "T3 Code"},
                         legacy_names={EXTERNAL: "legacy name"})
    backend = ui.XTestBackend(*server.libraries())
    assert backend.window_name(EXTERNAL) == "T3 Code"
    assert not any(name == "XFetchName" for name, _args in server.calls)
    legacy = FakeXServer(chain=[EXTERNAL], legacy_names={EXTERNAL: "legacy name"})
    assert ui.XTestBackend(*legacy.libraries()).window_name(EXTERNAL) == "legacy name"
    assert ui.XTestBackend(*FakeXServer().libraries()).window_name(0x9999) == ""


def test_xtest_binding_refuses_when_no_display_is_open():
    server = FakeXServer(display=0)
    with pytest.raises(ui.UserInputError, match="X display is unavailable"):
        ui.XTestBackend(*server.libraries())


def test_backend_loads_libx11_and_libxtst_once_and_caches(monkeypatch):
    server = FakeXServer()
    xlib, xtst = server.libraries()
    loaded = []

    def fake_cdll(name):
        loaded.append(name)
        return xlib if "X11" in name else xtst

    monkeypatch.setattr(ui, "_BACKEND", None)
    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)
    first = ui.get_backend()
    second = ui.get_backend()
    assert first is second
    assert loaded == ["libX11.so.6", "libXtst.so.6"]
    assert [name for name, _args in server.calls].count("XOpenDisplay") == 1


def test_client_message_layout_matches_xlib_on_64_bit_linux():
    if ctypes.sizeof(ctypes.c_long) != 8:
        pytest.skip("the layout check assumes LP64")
    assert ctypes.sizeof(ui.ClientMessageEvent) == 96
    assert ui.ClientMessageEvent.message_type.offset == 40
    assert ui.ClientMessageEvent.format.offset == 48
    assert ui.ClientMessageEvent.data.offset == 56
    assert ui.XEVENT_SIZE >= ctypes.sizeof(ui.ClientMessageEvent)


def test_real_xlib_exports_every_symbol_the_binding_uses_without_opening_a_display():
    try:
        xlib = ctypes.CDLL("libX11.so.6")
        xtst = ctypes.CDLL("libXtst.so.6")
    except OSError:
        pytest.skip("libX11 or libXtst is not installed on this host")
    for name in ("XOpenDisplay", "XDefaultRootWindow", "XQueryPointer", "XFlush", "XInternAtom",
                 "XSendEvent", "XRaiseWindow", "XGetWindowProperty", "XFetchName", "XFree",
                 "XDefaultScreen", "XDisplayWidth", "XDisplayHeight"):
        assert hasattr(xlib, name), name
    for name in ("XTestQueryExtension", "XTestFakeMotionEvent", "XTestFakeButtonEvent"):
        assert hasattr(xtst, name), name


def test_slug_is_a_safe_screenshot_label():
    assert ui.slug("Find Working Configuration") == "find-working-configuration"
    assert ui.slug("  Keep searching!! ") == "keep-searching"
    assert ui.slug("") == "control"


# --- Tab navigation before real-input presses (S6-ADVISOR-GUI-01 harness) -------------------

class ArgSignal(FakeSignal):
    """A Qt signal that passes its arguments to the connected slots (tabBarClicked(int))."""

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


def effective_visible(node) -> bool:
    """Qt isVisible(): own flag, and no ancestor hides it (a non-current QTabWidget page does)."""
    current = node
    while current is not None:
        if not getattr(current, "own_visible", True):
            return False
        parent = current.parent()
        if isinstance(parent, FakeTabWidget):
            index = parent.page_index_of(current)
            if index is not None and index != parent.currentIndex:
                return False
        current = parent
    return True


class TabWorldWidget(FakeWidget):
    """A FakeWidget whose ``visible`` is Qt-like: it also follows the ancestors and tab pages."""

    @property
    def visible(self):
        return effective_visible(self)

    @visible.setter
    def visible(self, value):
        self.own_visible = bool(value)


class FakePage(TabWorldWidget):
    def __init__(self, name, *, parent, x, y, width, height):
        super().__init__(name, parent=parent, cls="QWidget", x=x, y=y, width=width, height=height)


class FakeTabRect:
    def __init__(self, x, y, width, height):
        self._x, self._y, self._w, self._h = x, y, width, height

    def center(self):
        return FakePoint(self._x + self._w // 2, self._y + self._h // 2)


class FakeTabBar(TabWorldWidget):
    def __init__(self, name, *, parent, x, y, width, tabs):
        super().__init__(name, parent=parent, cls="QTabBar", x=x, y=y, width=width, height=30)
        self.tabs = tabs  # list of dicts: text, rect (x, y, w, h relative to the bar), enabled

    def tabRect(self, index):
        x, y, w, h = self.tabs[index]["rect"]
        return FakeTabRect(x, y, w, h)

    def isTabEnabled(self, index):
        return bool(self.tabs[index].get("enabled", True))

    def index_at(self, global_xy):
        ox, oy = self._origin
        for index, tab in enumerate(self.tabs):
            x, y, w, h = tab["rect"]
            if x <= global_xy[0] - ox < x + w and y <= global_xy[1] - oy < y + h:
                return index
        return None


class FakeTabWidget(TabWorldWidget):
    def __init__(self, name, *, parent, x, y, width, height, tabs, current=0):
        super().__init__(name, parent=parent, cls="QTabWidget", x=x, y=y, width=width, height=height)
        self.currentIndex = current
        self._tab_texts = [tab["text"] for tab in tabs]
        self.pages: list[FakeWidget] = []
        self.tabBarClicked = ArgSignal()
        self.currentChanged = ArgSignal()
        self._bar = FakeTabBar(f"{name}.tabBar", parent=self, x=x, y=y, width=width, tabs=tabs)

    @property
    def count(self):
        return len(self.pages)

    def widget(self, index):
        return self.pages[index]

    def tabBar(self):
        return self._bar

    def tabText(self, index):
        return self._tab_texts[index]

    def page_index_of(self, node):
        for index, page in enumerate(self.pages):
            if page is node:
                return index
        return None

    def click(self):  # a QAbstractButton-style fallback must never reach a tab widget
        raise AssertionError("tab widgets are never clicked through click()")


class TabEnv(FakeEnv):
    """Hit testing over the visible widgets: the topmost visible widget under the point wins."""

    def __init__(self, *, dpr=1.0):
        super().__init__(target=None, dpr=dpr)
        self.widgets: list[FakeWidget] = []

    def widget_at(self, point):
        """The topmost visible widget under the point: a higher ``z`` (a window stacked above),
        then the deepest (a child is stacked above its parent), then the later registration."""
        hit, hit_key = None, None
        for widget in self.widgets:
            if not effective_visible(widget):
                continue
            ox, oy = widget._origin
            if not (ox <= point.x() < ox + widget.width and oy <= point.y() < oy + widget.height):
                continue
            depth, node = 0, widget.parent()
            while node is not None:
                depth, node = depth + 1, node.parent()
            key = (getattr(widget, "z", 0), depth)
            if hit_key is None or key >= hit_key:
                hit, hit_key = widget, key
        return hit


class TabBackend(FakeBackend):
    """Release on a tab bar selects the tab under the pointer (what Qt does); release on a
    button emits its clicked signal. Presses are recorded but do nothing on their own."""

    def __init__(self, env, *, tab_responds=True, **kwargs):
        super().__init__(env, **kwargs)
        self.tab_responds = tab_responds

    def button(self, button, pressed):
        self.events.append(("button", int(button), bool(pressed)))
        if pressed:
            return
        hit = self.env.widget_at(FakePoint(*self.position))
        if isinstance(hit, FakeTabBar):
            index = hit.index_at(self.position)
            if index is not None and self.tab_responds:
                tab_widget = hit.parent()
                tab_widget.currentIndex = index
                tab_widget.tabBarClicked.emit(index)
        elif hit is not None:
            hit.clicked.emit()


@pytest.fixture
def tab_world(monkeypatch, clock):
    """Main window > QTabWidget (Placement, Scene); the target button sits on the Scene page."""

    def build(*, current=0, tab_enabled=True, control_enabled=True, control_visible=True,
              tabs_visible=True, tab_responds=True, cover_tab_bar=False, dpr=1.0, follows_pointer=True):
        env = TabEnv(dpr=dpr)
        env.main = FakeWindowish(env, "main")
        window = FakeWidget("mainWindow", cls="QMainWindow", x=0, y=0, width=1200, height=800,
                            native_id=MAIN_WINDOW)
        env.widgets.append(window)
        tabs = FakeTabWidget(
            "DENTOBOTStep61TabWidget", parent=window, x=0, y=0, width=800, height=600, current=current,
            tabs=[{"text": "Placement", "rect": (0, 0, 200, 30)},
                  {"text": "Scene", "rect": (200, 0, 200, 30), "enabled": tab_enabled}],
        )
        tabs.own_visible = tabs_visible
        env.widgets += [tabs, tabs.tabBar()]
        placement = FakePage("DENTOBOTStep61PlacementPage", parent=tabs, x=0, y=30, width=800, height=570)
        scene = FakePage("DENTOBOTStep61ScenePage", parent=tabs, x=0, y=30, width=800, height=570)
        tabs.pages = [placement, scene]
        env.widgets += [placement, scene]
        if cover_tab_bar:
            cover = FakeWidget("coverWidget", parent=window, x=0, y=0, width=800, height=30)
            cover.z = 1  # another window stacked above the tab bar
            env.widgets.append(cover)
        target = TabWorldWidget("DENTOBOTSyncCollisionSceneButton", parent=scene, x=300, y=400,
                            width=100, height=40, text="Audit + Sync Collision Surfaces",
                            visible=control_visible, enabled=control_enabled)
        env.widgets.append(target)
        qt = make_qt(env)
        slicer = SimpleNamespace(util=SimpleNamespace(mainWindow=lambda: env.main))
        backend = TabBackend(env, tab_responds=tab_responds, follows_pointer=follows_pointer)
        monkeypatch.setattr(ui, "_runtime", lambda: (qt, slicer))
        monkeypatch.setattr(ui, "get_backend", lambda: backend)
        return SimpleNamespace(target=target, tabs=tabs, scene=scene, placement=placement, env=env,
                               backend=backend, window=window)

    return build


def _entries(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_control_on_a_non_current_tab_page_is_reached_by_a_real_tab_press_first(tab_world, tmp_path):
    world = tab_world(current=0)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(world.target, "Sync Collision Scene", mode="xtest", evidence=ledger)
    assert world.tabs.currentIndex == 1  # the Scene page is now current, from a real press
    presses = [event for event in world.backend.events if event[0] == "button"]
    # tab press and release come before the control press and release
    assert presses == [("button", 1, True), ("button", 1, False), ("button", 1, True), ("button", 1, False)]
    moves = [event[1:] for event in world.backend.events if event[0] == "move"]
    assert moves[0] == (300, 15)  # centre of the Scene tab (x 200..400, y 0..30)
    assert moves[-1] == (350, 420)  # then the centre of the control
    assert world.target.clicks == 0
    entries = _entries(ledger)
    assert [entry.get("navigation") for entry in entries] == ["tab", None]
    tab_entry = entries[0]
    assert tab_entry["delivered"] is True and tab_entry["tab_index"] == 1
    assert tab_entry["tab_text"] == "Scene" and tab_entry["currentIndex_before"] == 0
    assert tab_entry["currentIndex_after"] == 1 and tab_entry["x_activation"]["hit_test"] == "pass"
    assert tab_entry["delivered_utc"] and tab_entry["physical_xy"] == [300, 15]
    assert entries[1]["delivered"] is True and entries[1]["objectName"] == "DENTOBOTSyncCollisionSceneButton"
    assert entries[1]["navigated_before_press"] == [
        {"navigation": "tab", "label": tab_entry["label"], "tab_index": 1, "action": None}
    ]
    assert record["navigated_before_press"][0]["navigation"] == "tab"


def test_nested_tab_pages_are_opened_outermost_first_each_as_a_real_press(tab_world, tmp_path, monkeypatch):
    world = tab_world(current=0)
    # Put a second QTabWidget inside the Scene page: Overview (current) and Collision (target).
    inner_tabs = FakeTabWidget(
        "DENTOBOTStep61InnerTabWidget", parent=world.scene, x=0, y=60, width=800, height=400, current=0,
        tabs=[{"text": "Overview", "rect": (0, 0, 200, 30)}, {"text": "Collision", "rect": (200, 0, 200, 30)}],
    )
    inner_tabs.own_visible = True
    world.env.widgets += [inner_tabs, inner_tabs.tabBar()]
    overview = FakePage("Overview", parent=inner_tabs, x=0, y=90, width=800, height=370)
    collision = FakePage("Collision", parent=inner_tabs, x=0, y=90, width=800, height=370)
    inner_tabs.pages = [overview, collision]
    world.env.widgets += [overview, collision]
    world.target._parent = collision
    world.env.widgets.remove(world.target)
    world.env.widgets.append(world.target)  # the button stays topmost
    world.target._origin = (300, 300)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    ui.user_click(world.target, "Sync Collision Scene", mode="xtest", evidence=ledger)
    assert world.tabs.currentIndex == 1 and inner_tabs.currentIndex == 1
    moves = [event[1:] for event in world.backend.events if event[0] == "move"]
    assert moves[0] == (300, 15) and moves[1] == (300, 75) and moves[-1] == (350, 320)
    entries = _entries(ledger)
    assert [entry.get("navigation") for entry in entries] == ["tab", "tab", None]
    assert entries[0]["objectName"] == "DENTOBOTStep61TabWidget" and entries[0]["tab_text"] == "Scene"
    assert entries[1]["objectName"] == "DENTOBOTStep61InnerTabWidget" and entries[1]["tab_text"] == "Collision"
    assert [item["tab_index"] for item in entries[2]["navigated_before_press"]] == [1, 1]


def test_tab_press_that_is_not_delivered_is_refused_and_the_control_is_not_pressed(tab_world, tmp_path):
    world = tab_world(tab_responds=False)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match=r"Open tab 'Scene'.*tab press not delivered \(current tab stayed 0\)"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest", evidence=ledger)
    assert ("button", 1, True) in world.backend.events and world.target.clicks == 0
    assert [event for event in world.backend.events if event[0] == "button" and event[2]] == [("button", 1, True)]
    entries = _entries(ledger)
    assert entries[0]["navigation"] == "tab" and entries[0]["delivered"] is False
    assert "not delivered" in entries[0]["refused"]
    assert entries[-1]["delivered"] is False and entries[-1]["navigated_before_press"] == []


def test_covered_tab_bar_is_refused_without_pressing_the_tab_or_the_control(tab_world, tmp_path):
    world = tab_world(cover_tab_bar=True)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match=r"covered by QPushButton/coverWidget"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest", evidence=ledger)
    assert [event for event in world.backend.events if event[0] == "button"] == []
    assert world.tabs.currentIndex == 0
    assert _entries(ledger)[0]["navigation"] == "tab" and _entries(ledger)[0]["delivered"] is False


def test_disabled_tab_is_refused_before_any_press(tab_world, tmp_path):
    world = tab_world(tab_enabled=False)
    with pytest.raises(ui.UserInputError, match=r"Open tab 'Scene'.*tab is disabled"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest")
    assert world.backend.events == [] and world.tabs.currentIndex == 0


def test_disabled_control_on_a_hidden_page_is_refused_without_navigating(tab_world):
    world = tab_world(control_enabled=False)
    with pytest.raises(ui.UserInputError, match="control is disabled"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest")
    assert world.backend.events == [] and world.tabs.currentIndex == 0


def test_hidden_tab_widget_is_not_navigated_and_refuses_without_a_direct_helper(tab_world):
    world = tab_world(tabs_visible=False)
    with pytest.raises(ui.UserInputError, match="control is not visible"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest")
    assert world.backend.events == [] and world.tabs.currentIndex == 0


def test_direct_navigation_is_logged_with_its_reason_and_the_control_is_pressed_after_recheck(tab_world, tmp_path):
    world = tab_world()
    group = TabWorldWidget("DENTOBOTCollisionSceneGroupBox", parent=world.window, x=0, y=0, width=800, height=600)
    group.own_visible = False  # hidden by the shell: not the current substep page
    world.target._parent = group
    world.env.widgets.append(group)
    calls = []

    def direct(widget, reason):
        calls.append((widget.objectName, reason))
        group.own_visible = True
        return {"reason": "the collision group is on shell substep 1", "action": "_configureRobotSimulationShellSubstep(1)"}

    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    ui.user_click(world.target, "Sync Collision Scene", mode="xtest", evidence=ledger, direct_navigation=direct)
    assert calls == [("DENTOBOTSyncCollisionSceneButton", "hidden by a non-current page or group")]
    entries = _entries(ledger)
    assert entries[0]["navigation"] == "direct" and entries[0]["delivered"] is None
    assert entries[0]["reason"] == "the collision group is on shell substep 1"
    assert entries[0]["action"] == "_configureRobotSimulationShellSubstep(1)"
    assert entries[0]["hidden_reason"] == "hidden by a non-current page or group"
    assert entries[1]["delivered"] is True and entries[1]["navigated_before_press"][0]["navigation"] == "direct"


def test_direct_navigation_returning_none_refuses_loudly_and_presses_nothing(tab_world, tmp_path):
    world = tab_world()
    group = TabWorldWidget("hiddenGroup", parent=world.window, x=0, y=0, width=800, height=600)
    group.own_visible = False
    world.target._parent = group
    world.env.widgets.append(group)
    calls = []
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match="control is not visible"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest", evidence=ledger,
                      direct_navigation=lambda widget, reason: calls.append(reason) or None)
    assert calls == ["hidden by a non-current page or group"]
    assert world.backend.events == []
    entries = _entries(ledger)
    assert len(entries) == 1 and entries[0]["delivered"] is False and "not visible" in entries[0]["refused"]


def test_direct_navigation_that_does_not_reveal_the_control_is_tried_once_then_refused(tab_world):
    world = tab_world()
    group = TabWorldWidget("hiddenGroup", parent=world.window, x=0, y=0, width=800, height=600)
    group.own_visible = False
    world.target._parent = group
    world.env.widgets.append(group)
    calls = []

    def direct(widget, reason):
        calls.append(reason)
        return {"reason": "claimed", "action": "_configureRobotSimulationShellSubstep(9)"}

    with pytest.raises(ui.UserInputError,
                       match=r"control is not visible after direct navigation \(_configureRobotSimulationShellSubstep\(9\)\)"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest", direct_navigation=direct)
    assert len(calls) == 1 and world.backend.events == []


def test_collapsed_group_is_expanded_only_through_the_direct_helper_and_logged(tab_world, tmp_path):
    world = tab_world()
    group = FakeWidget("advancedGroup", cls="ctkCollapsibleButton", text="Advanced settings",
                       parent=world.window, collapsed=True)
    world.target._parent = group
    calls = []

    def direct(widget, reason):
        calls.append(reason)
        group.collapsed = False
        return {"reason": "the advanced group is collapsed", "action": "expand Advanced settings"}

    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    ui.user_click(world.target, "Diagnose", mode="xtest", evidence=ledger, direct_navigation=direct)
    assert calls == ["collapsed group"]
    entries = _entries(ledger)
    assert entries[0]["navigation"] == "direct" and entries[0]["hidden_reason"] == "collapsed group"
    assert entries[1]["delivered"] is True


def test_collapsed_group_without_a_helper_still_refuses_and_expands_nothing(tab_world, tmp_path):
    world = tab_world()
    group = FakeWidget("advancedGroup", cls="ctkCollapsibleButton", text="Advanced settings",
                       parent=world.window, collapsed=True)
    world.target._parent = group
    with pytest.raises(ui.UserInputError, match="not reachable without expanding Advanced settings"):
        ui.user_click(world.target, "Diagnose", mode="xtest", direct_navigation=None)
    assert world.backend.events == [] and group.collapsed is True


def test_direct_navigation_is_not_consulted_for_disabled_controls(tab_world):
    world = tab_world(control_enabled=False)
    group = TabWorldWidget("hiddenGroup", parent=world.window, x=0, y=0, width=800, height=600)
    group.own_visible = False
    world.target._parent = group
    world.env.widgets.append(group)
    calls = []
    with pytest.raises(ui.UserInputError, match="control is disabled"):
        ui.user_click(world.target, "Sync Collision Scene", mode="xtest",
                      direct_navigation=lambda widget, reason: calls.append(reason))
    assert calls == [] and world.backend.events == []


def test_demo_mode_shows_and_hides_its_overlays_around_a_tab_press(tab_world, tmp_path):
    world = tab_world()
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    ui.user_click(world.target, "Sync Collision Scene", mode="demo", evidence=ledger)
    shows = [entry for entry in world.env.log if entry[0] == "overlay_show"]
    hides = [entry for entry in world.env.log if entry[0] == "overlay_hide"]
    assert shows and len(shows) == len(hides)
    entries = _entries(ledger)
    assert [entry.get("navigation") for entry in entries] == ["tab", None]
    assert entries[0]["mode"] == "demo" and entries[0]["delivered"] is True


def test_tab_navigation_source_has_no_direct_index_assignment_or_click_fallback():
    import inspect

    source = inspect.getsource(ui._navigate_tab) + inspect.getsource(ui._ensure_reachable)
    assert ".click(" not in source
    assert "currentIndex =" not in source and "setCurrentIndex" not in source


class FakeArea:
    """A style sub-element rectangle in widget-local coordinates."""

    def __init__(self, x, y, width, height):
        self._x, self._y, self._w, self._h = x, y, width, height

    def width(self):
        return self._w

    def height(self):
        return self._h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def center(self):
        return FakePoint(self._x + self._w // 2, self._y + self._h // 2)


class FakeStyle:
    """Answers Qt sub-element/sub-control geometry from tables; absent means an empty rect."""

    def __init__(self, areas, *, subcontrols=None, events=None):
        self._areas = areas
        self._subcontrols = {} if subcontrols is None else subcontrols
        self.events = events

    def subElementRect(self, element, option, widget):
        spec = self._areas.get(element)
        return FakeArea(*spec) if spec else FakeArea(0, 0, 0, 0)

    def subControlRect(self, control, option, subcontrol, widget):
        if self.events is not None:
            self.events.append("geometry")
        spec = self._subcontrols.get(subcontrol)
        return FakeArea(*spec) if spec else FakeArea(0, 0, 0, 0)


class BoolBackend(FakeBackend):
    """Release emits clicked(bool) like QCheckBox; ``toggle`` flips the checked state first, as Qt does."""

    def __init__(self, env, *, toggle=True, **kwargs):
        super().__init__(env, **kwargs)
        self.toggle = toggle

    def button(self, button, pressed):
        self.events.append(("button", int(button), bool(pressed)))
        if not pressed and self.emit_on_release:
            if self.toggle:
                self.env.target.checked = not self.env.target.checked
            self.env.target.clicked.emit(bool(self.env.target.checked))


class RaisingSignal(ArgSignal):
    """A production slot that raises: PythonQt reports it through the interpreter's excepthook."""

    def emit(self, *args):
        super().emit(*args)
        sys.excepthook(RuntimeError, RuntimeError("production handler failed"), None)


def _check_box(harness, monkeypatch, *, areas, checked=False, toggle=True, **kwargs):
    target, env, _backend = harness(cls="QCheckBox", x=300, y=400, width=1000, height=30, **kwargs)
    target.clicked = ArgSignal()
    target.checkable = True
    target.checked = checked
    target._style = FakeStyle(areas)
    backend = BoolBackend(env, toggle=toggle)
    monkeypatch.setattr(ui, "get_backend", lambda: backend)
    return target, backend


def test_check_box_is_pressed_on_its_style_indicator_not_on_the_empty_centre_of_its_row(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={"indicator": (4, 8, 14, 14)})
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "I consent to Task Home revalidation", mode="xtest", evidence=ledger)
    assert record["delivered"] is True
    assert record["physical_xy"] == [311, 415]  # indicator centre: 300 + 4 + 7, row y 400 + 8 + 7
    assert ("move", 311, 415) in backend.events
    assert ("move", 500, 415) not in backend.events  # not the centre of the 1000 px row
    assert record["checkable"] is True and record["checked_before"] is False and record["checked_after"] is True


def test_check_box_without_an_indicator_is_pressed_on_its_text_area(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={"contents": (20, 0, 200, 30)})
    record = ui.user_click(target, "I consent to Task Home revalidation", mode="xtest")
    assert record["physical_xy"] == [420, 415]  # text area centre: 300 + 20 + 100, y 400 + 15


def test_check_box_with_no_indicator_or_text_area_is_refused_without_pressing(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={})
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match="no indicator or label area to press"):
        ui.user_click(target, "I consent to Task Home revalidation", mode="xtest", evidence=ledger)
    assert backend.events == []
    assert json.loads(ledger.read_text().splitlines()[-1])["delivered"] is False


def test_checkable_control_whose_state_does_not_change_is_refused_and_recorded_undelivered(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={"indicator": (4, 8, 14, 14)}, toggle=False)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match=r"clicked, but the checked state stayed False"):
        ui.user_click(target, "I consent to Task Home revalidation", mode="xtest", evidence=ledger)
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row["delivered"] is False and row["checked_before"] is False and row["checked_after"] is False


def test_slot_that_raises_during_the_press_makes_the_press_fail_and_is_recorded(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={"indicator": (4, 8, 14, 14)})
    hook_before = sys.excepthook
    target.clicked = RaisingSignal()  # the probe runs, then the production slot raises
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match=r"not delivered; a slot raised during the press \(RuntimeError: production handler failed\)"):
        ui.user_click(target, "I consent to Task Home revalidation", mode="xtest", evidence=ledger)
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row["delivered"] is False
    assert row["signal_errors"] == ["RuntimeError: production handler failed"]
    assert target.checked is True  # the state did toggle; the press is still not recorded as delivered
    assert sys.excepthook is hook_before  # the capture hook is restored after the press


def test_probe_failure_in_the_clicked_slot_is_not_recorded_as_delivered(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={"indicator": (4, 8, 14, 14)})
    real = ui.utc_now
    calls = {"n": 0}

    def flaky():  # the first call is the probe's; it fails once
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("probe write failed")
        return real()

    monkeypatch.setattr(ui, "utc_now", flaky)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match=r"not delivered; the clicked probe failed \(RuntimeError: probe write failed\)"):
        ui.user_click(target, "I consent to Task Home revalidation", mode="xtest", evidence=ledger)
    row = json.loads(ledger.read_text().splitlines()[-1])
    assert row["delivered"] is False and row["signal_errors"] == ["RuntimeError: probe write failed"]


def test_checkable_control_that_toggles_is_delivered_with_its_before_and_after_state(harness, monkeypatch, tmp_path):
    target, backend = _check_box(harness, monkeypatch, areas={"indicator": (4, 8, 14, 14)})
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "I consent to Task Home revalidation", mode="xtest", evidence=ledger)
    assert record["delivered"] is True and record["signal_errors"] == []
    assert json.loads(ledger.read_text().splitlines()[-1])["checked_after"] is True


# --- uinput mode in user_click (S6-ADVISOR-GUI-01 harness) ----------------------------------

def test_uinput_mode_presses_through_the_uinput_backend_and_confirms_delivery(harness, monkeypatch, tmp_path):
    target, env, backend = harness()
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: backend)
    monkeypatch.setattr(ui, "get_backend", lambda: pytest.fail("uinput mode must not use the XTest pointer path"))
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "Find Working Configuration", mode="uinput", evidence=ledger)
    assert record["mode"] == "uinput" and record["delivered"] is True
    assert backend.events[0] == ("move", 350, 420)
    assert ("button", 1, True) in backend.events and ("button", 1, False) in backend.events
    assert backend.events.index(("button", 1, True)) < backend.events.index(("button", 1, False))
    assert target.clicks == 0 and target.clicked.slots == []
    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["mode"] == "uinput" and saved["delivered_utc"]


def test_uinput_refusal_is_loud_and_presses_nothing(harness, monkeypatch, tmp_path):
    target, env, backend = harness()

    class RefusingPointer(type(backend)):
        def move(self, x, y):
            self.events.append(("move", int(x), int(y)))
            raise ui.UserInputError(f"pointer did not reach ({x}, {y}) after 3 corrective uinput moves; "
                                    "it is at (5, 5) (tolerance 2 px)")

    refusing = RefusingPointer(env)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: refusing)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    with pytest.raises(ui.UserInputError, match="did not reach"):
        ui.user_click(target, "Find Working Configuration", mode="uinput", evidence=ledger)
    assert target.clicks == 0
    assert refusing.events == [("move", 350, 420)]  # no button was sent
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["delivered"] is False and entry["mode"] == "uinput"
    assert "did not reach" in entry["refused"]


def test_uinput_move_evidence_is_kept_on_each_hit_test_attempt(harness, monkeypatch, tmp_path):
    target, env, backend = harness()

    class LoggingPointer(type(backend)):
        last_move = None

        def move(self, x, y):
            super().move(x, y)
            self.last_move = {"target_xy": [int(x), int(y)], "landed": True,
                              "attempts": [{"abs_xy": [1, 2], "observed_xy": [int(x), int(y)]}]}

    logging_backend = LoggingPointer(env)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: logging_backend)
    record = ui.user_click(target, "Find Working Configuration", mode="uinput", evidence=tmp_path / "ledger.jsonl")
    first = record["x_activation"]["attempts"][0]
    assert first["uinput_move"]["landed"] is True and first["uinput_move"]["target_xy"] == [350, 420]


def test_xtest_mode_never_touches_the_uinput_backend(harness, monkeypatch, tmp_path):
    target, env, backend = harness()
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: pytest.fail("xtest must not open uinput"))
    record = ui.user_click(target, "Find Working Configuration", mode="xtest")
    assert record["delivered"] is True
    assert "uinput_move" not in record["x_activation"]["attempts"][0]


def test_uinput_mode_reaches_a_hidden_tab_page_with_the_same_real_tab_press(tab_world, monkeypatch, tmp_path):
    world = tab_world(current=0)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: world.backend)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(world.target, "Sync Collision Scene", mode="uinput", evidence=ledger)
    assert world.tabs.currentIndex == 1 and record["delivered"] is True
    entries = _entries(ledger)
    assert [entry.get("navigation") for entry in entries] == ["tab", None]
    assert all(entry["mode"] == "uinput" for entry in entries)
    assert world.target.clicks == 0


class SpinArrowBackend(FakeBackend):
    """Apply a spinbox step only when a real left-button release hits a style arrow point."""

    def __init__(self, env, spinbox, *, up_point, down_point, step_on_click=True, **kwargs):
        super().__init__(env, **kwargs)
        self.spinbox = spinbox
        self.up_point = up_point
        self.down_point = down_point
        self.step_on_click = step_on_click

    def button(self, button, pressed):
        super().button(button, pressed)
        if button != 1 or pressed or not self.step_on_click:
            return
        value = float(self.spinbox.value)
        step = float(self.spinbox.singleStep)
        if self.position == self.up_point:
            self.spinbox.value = min(float(self.spinbox.maximum), value + step)
        elif self.position == self.down_point:
            self.spinbox.value = max(float(self.spinbox.minimum), value - step)


def _spinbox_arrow_world(harness, monkeypatch, *, dpr=1.0, value=40.0, visible=True, enabled=True,
                         step_on_click=True):
    target, env, _unused = harness(cls="QDoubleSpinBox", x=300, y=400, width=100, height=40,
                                   dpr=dpr, visible=visible, enabled=enabled)
    target._inherits.add("QAbstractSpinBox")
    target.value = float(value)
    target.singleStep = 1.0
    target.minimum = 20.0
    target.maximum = 60.0
    target.decimals = 1
    target.wrapping = False
    target.initStyleOption = lambda option: None
    up_rect, down_rect = (80, 4, 15, 12), (80, 22, 15, 12)
    events = []
    target._style = FakeStyle({}, subcontrols={"spinbox-up": up_rect, "spinbox-down": down_rect}, events=events)

    def physical_for(rect):
        point = target.mapToGlobal(FakeArea(*rect).center())
        return (round(point.x() * dpr), round(point.y() * dpr))

    backend = SpinArrowBackend(env, target, up_point=physical_for(up_rect), down_point=physical_for(down_rect),
                               step_on_click=step_on_click)
    monkeypatch.setattr(ui, "get_backend", lambda: backend)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: backend)
    return target, env, backend, events


@pytest.mark.parametrize("up, expected, arrow_point", [
    (True, 41.0, (580, 615)),
    (False, 39.0, (580, 642)),
])
def test_spinbox_arrow_click_scrolls_before_style_geometry_and_logs_verified_real_press(
        harness, monkeypatch, tmp_path, up, expected, arrow_point):
    target, env, backend, events = _spinbox_arrow_world(harness, monkeypatch, dpr=1.5)
    scroll = FakeScrollArea("settingsScroll", parent=target.parent())
    target._parent = scroll
    original_ensure = scroll.ensureWidgetVisible

    def ensure_visible(widget, *margins):
        events.append("scroll")
        original_ensure(widget, *margins)

    scroll.ensureWidgetVisible = ensure_visible
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.spinbox_arrow_click(target, up, f"Opening target gap {'up' if up else 'down'}",
                                    mode="xtest", evidence=ledger)

    assert scroll.ensure_calls == [(target, ())]
    assert events.index("scroll") < events.index("geometry")
    assert backend.events[0] == ("move", *arrow_point)  # centre of Qt's selected sub-control at DPR 1.5
    assert ("button", 1, True) in backend.events and ("button", 1, False) in backend.events
    assert target.value == expected and target.clicks == 0
    assert record["attempted"] is True and record["press_sent"] is True and record["delivered"] is True
    assert record["arrow"] == ("up" if up else "down")
    assert record["value_before"] == 40.0 and record["value_after"] == expected
    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["action"] == "spinbox arrow click" and saved["delivered_utc"]
    assert saved["x_activation"]["hit_test"] == "pass"


@pytest.mark.parametrize("kwargs, message", [
    ({"visible": False}, "control is not visible"),
    ({"enabled": False}, "control is disabled"),
])
def test_spinbox_arrow_preflight_refusal_is_logged_without_geometry_or_input(
        harness, monkeypatch, tmp_path, kwargs, message):
    target, env, backend, events = _spinbox_arrow_world(harness, monkeypatch, **kwargs)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"

    with pytest.raises(ui.UserInputError, match=message):
        ui.spinbox_arrow_click(target, True, "Opening target gap up", mode="xtest", evidence=ledger)

    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["attempted"] is True and saved["delivered"] is False
    assert saved["press_attempted"] is False and saved["press_sent"] is False and saved["refused"]
    assert events == [] and backend.events == [] and target.value == 40.0


def test_spinbox_arrow_refuses_missing_style_geometry_before_loading_pointer_backend(
        harness, monkeypatch, tmp_path):
    target, env, backend, events = _spinbox_arrow_world(harness, monkeypatch)
    target._style._subcontrols = {}
    monkeypatch.setattr(ui, "get_backend", lambda: pytest.fail("missing arrow geometry must refuse before input"))
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"

    with pytest.raises(ui.UserInputError, match="has no usable style geometry"):
        ui.spinbox_arrow_click(target, False, "Opening target gap down", mode="xtest", evidence=ledger)

    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["delivered"] is False and saved["press_attempted"] is False
    assert "style geometry" in saved["refused"] and target.value == 40.0
    assert events == ["geometry"] and backend.events == []


def test_spinbox_arrow_no_value_change_is_recorded_as_refused_without_a_second_press(
        harness, monkeypatch, tmp_path):
    target, env, backend, _events = _spinbox_arrow_world(harness, monkeypatch, step_on_click=False)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"

    with pytest.raises(ui.UserInputError, match="did not produce the expected value step"):
        ui.spinbox_arrow_click(target, False, "Opening target gap down", mode="xtest", evidence=ledger)

    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["attempted"] is True and saved["press_attempted"] is True and saved["press_sent"] is True
    assert saved["delivered"] is False and saved["value_before"] == 40.0 and saved["value_after"] == 40.0
    assert backend.events.count(("button", 1, True)) == 1 and backend.events.count(("button", 1, False)) == 1


def test_spinbox_arrow_uinput_uses_only_uinput_and_logs_a_pointer_refusal(
        harness, monkeypatch, tmp_path):
    target, env, backend, _events = _spinbox_arrow_world(harness, monkeypatch)
    monkeypatch.setattr(ui, "get_backend", lambda: pytest.fail("uinput mode must not use XTest pointer path"))
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: backend)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.spinbox_arrow_click(target, True, "Opening target gap up", mode="uinput", evidence=ledger)
    assert record["mode"] == "uinput" and record["delivered"] is True and target.value == 41.0

    class RefusingUinput(SpinArrowBackend):
        def move(self, x, y):
            self.events.append(("move", int(x), int(y)))
            raise ui.UserInputError("uinput pointer could not reach the arrow")

    refusing = RefusingUinput(env, target, up_point=backend.up_point, down_point=backend.down_point)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: refusing)
    with pytest.raises(ui.UserInputError, match="could not reach the arrow"):
        ui.spinbox_arrow_click(target, False, "Opening target gap down", mode="uinput", evidence=ledger)

    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert rows[0]["delivered"] is True
    assert rows[1]["delivered"] is False and "could not reach" in rows[1]["refused"]
    assert not any(event[0] == "button" for event in refusing.events)
