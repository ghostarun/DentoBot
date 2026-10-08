"""Host tests for Testing/step6_user_input.py (S6-ADVISOR-GUI-01 real-user input).

No Qt, Slicer or X server is used: fake widgets, a fake XTest backend, and a fake
clock stand in for them. The assertions cover the preconditions, the physical
input sequence, delivery confirmation, the demo overlay order, and the absence of
any ``click()`` fallback in the ``xtest`` and ``demo`` modes.
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

    def topLeft(self):
        return FakePoint(0, 0)


class FakeWindowish:
    """Records geometry, flags and show/hide (used for the demo overlay and the main window)."""

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
                 width=100, height=40, visible=True, enabled=True, collapsed=False):
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
        self.clicked = FakeSignal()
        self.clicks = 0
        self.raised = 0
        self.activated = 0
        self._inherits = {cls, "QWidget", "QObject"}
        if cls == "ctkCollapsibleButton":
            self._inherits.add("ctkCollapsibleButton")
        self.env = None

    @property
    def rect(self):
        return FakeRect(self.width, self.height)

    def parent(self):
        return self._parent

    def className(self):
        return self._class

    def inherits(self, name):
        return name in self._inherits

    def window(self):
        node = self
        while node.parent() is not None:
            node = node.parent()
        return node

    def isAncestorOf(self, other):
        node = other.parent() if other is not None else None
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


_TARGET = object()  # widgetAt() returns the control itself (nothing covers it)


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

    return SimpleNamespace(
        QApplication=FakeQApplication(env), QPoint=QPoint, QFrame=QFrame, QLabel=QLabel,
        Qt=flags,
    )


class FakeBackend:
    """Stands in for XTestBackend: it records the physical input sequence."""

    def __init__(self, env, *, follows_pointer=True, emit_on_release=True):
        self.env = env
        self.position = (0, 0)
        self.events = []
        self.follows_pointer = follows_pointer
        self.emit_on_release = emit_on_release

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


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(ui, "_NOW", fake.now)
    monkeypatch.setattr(ui, "_SLEEP", fake.sleep)
    return fake


@pytest.fixture
def harness(monkeypatch, clock):
    """Build the fake world: a visible, enabled button inside a window, behind a scroll area."""

    def build(*, dpr=1.0, covered_by=_TARGET, follows_pointer=True, emit_on_release=True,
              x=300, y=400, width=100, height=40, **button_kwargs):
        window = FakeWidget("mainWindow", cls="QMainWindow", x=0, y=0, width=1200, height=800)
        target = FakeWidget("DENTOBOTStep6FindWorkingConfigButton", parent=window,
                            x=x, y=y, width=width, height=height, **button_kwargs)
        env = FakeEnv(target, dpr=dpr, covered_by=covered_by)
        env.main = FakeWindowish(env, "main")
        qt = make_qt(env)
        slicer = SimpleNamespace(util=SimpleNamespace(mainWindow=lambda: env.main))
        backend = FakeBackend(env, follows_pointer=follows_pointer,
                              emit_on_release=emit_on_release)
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


def test_xtest_click_uses_real_motion_press_release_and_confirms_delivery(harness, tmp_path):
    target, env, backend = harness(x=300, y=400, width=100, height=40)
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    record = ui.user_click(target, "Find Working Configuration", mode="xtest", evidence=ledger)
    # centre of (300..400, 400..440) in logical global coordinates is (350, 420)
    assert backend.events[0] == ("move", 350, 420)
    assert ("button", 1, True) in backend.events and ("button", 1, False) in backend.events
    assert backend.events.index(("button", 1, True)) < backend.events.index(("button", 1, False))
    assert target.clicked.slots == []  # the temporary delivery probe is disconnected
    assert target.clicks == 0  # no QAbstractButton.click() fallback
    assert record["delivered"] is True
    assert record["physical_xy"] == [350, 420] and record["objectName"] == target.objectName
    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["mode"] == "xtest" and saved["delivered_utc"]


@pytest.mark.parametrize("kwargs, message", [
    ({"visible": False}, "control is not visible"),
    ({"enabled": False}, "control is disabled"),
])
@pytest.mark.parametrize("mode", ["xtest", "demo"])
def test_invisible_or_disabled_controls_fail_without_pressing(harness, mode, kwargs, message):
    target, env, backend = harness(**kwargs)
    with pytest.raises(ui.UserInputError, match=message):
        ui.user_click(target, "Start search", mode=mode)
    assert backend.events == []
    assert target.clicks == 0


def test_control_in_a_collapsed_group_says_to_expand_it_and_expands_nothing(harness):
    target, env, backend = harness()
    group = FakeWidget("advancedGroup", cls="ctkCollapsibleButton", text="Advanced settings",
                       parent=target.parent(), collapsed=True)
    target._parent = group
    with pytest.raises(ui.UserInputError, match="not reachable without expanding Advanced settings"):
        ui.user_click(target, "Diagnose", mode="xtest")
    assert backend.events == [] and group.collapsed is True


def test_covered_control_fails_before_the_press(harness):
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


def test_scroll_area_ensure_widget_visible_is_called_before_the_press(harness):
    window = FakeWidget("mainWindow", cls="QMainWindow", width=1200, height=800)
    scroll = FakeScrollArea("workflowScroll", parent=window)
    content = FakeWidget("content", cls="QWidget", parent=scroll)
    target, env, backend = harness()
    target._parent = content
    ui.user_click(target, "Load Robot", mode="xtest")
    assert scroll.ensure_calls and scroll.ensure_calls[0][0] is target
    assert backend.events[0][0] == "move"


def test_device_pixel_ratio_maps_logical_centre_to_physical_pixels(harness):
    target, env, backend = harness(dpr=2.0, x=300, y=400, width=100, height=40)
    record = ui.user_click(target, "Connect", mode="xtest")
    assert record["logical_xy"] == [350, 420]
    assert record["physical_xy"] == [700, 840]
    assert backend.events[0] == ("move", 700, 840)


def test_pointer_that_does_not_reach_the_target_fails_before_the_press(harness, clock):
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


def test_demo_mode_shows_a_click_through_highlight_before_the_check_and_keeps_its_caption(harness):
    target, env, backend = harness(x=300, y=400, width=100, height=40)
    record = ui.user_click(target, "Find Working Configuration", mode="demo")
    overlay_flags = [entry for entry in env.log if entry[0] in ("overlay_show", "overlay_hide", "widgetAt")]
    first_show = overlay_flags.index(("overlay_show", "frame"))
    hide = overlay_flags.index(("overlay_hide", "frame"))
    check = overlay_flags.index(next(entry for entry in overlay_flags if entry[0] == "widgetAt"))
    assert first_show < hide < check, overlay_flags
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
        if name.startswith("_"):
            raise AttributeError(name)
        return self._functions[name]


def make_fake_x(calls, *, display=1, pointer=(640, 480)):
    def record(name, result=None):
        def impl(*args):
            calls.append((name, args))
            return result(args) if callable(result) else result
        return impl

    def query_pointer(args):
        args[4].contents.value = pointer[0]
        args[5].contents.value = pointer[1]
        return 1

    xlib = FakeLibrary({
        "XOpenDisplay": FakeCFunction(record("XOpenDisplay", display)),
        "XDefaultRootWindow": FakeCFunction(record("XDefaultRootWindow", 99)),
        "XQueryPointer": FakeCFunction(record("XQueryPointer", query_pointer)),
        "XFlush": FakeCFunction(record("XFlush", 1)),
    })
    xtst = FakeLibrary({
        "XTestQueryExtension": FakeCFunction(record("XTestQueryExtension", 1)),
        "XTestFakeMotionEvent": FakeCFunction(record("XTestFakeMotionEvent", 1)),
        "XTestFakeButtonEvent": FakeCFunction(record("XTestFakeButtonEvent", 1)),
    })
    return xlib, xtst


def test_xtest_binding_issues_the_expected_xlib_and_xtest_sequence():
    calls = []
    xlib, xtst = make_fake_x(calls)
    backend = ui.XTestBackend(xlib, xtst)
    assert backend.pointer() == (640, 480)
    backend.move(350, 420)
    backend.button(1, True)
    backend.button(1, False)
    names = [name for name, _args in calls]
    assert names[0] == "XOpenDisplay" and names.count("XOpenDisplay") == 1
    assert names[1] == "XTestQueryExtension"
    assert ("XTestFakeMotionEvent", (1, -1, 350, 420, 0)) in calls
    assert ("XTestFakeButtonEvent", (1, 1, 1, 0)) in calls
    assert ("XTestFakeButtonEvent", (1, 1, 0, 0)) in calls
    motion_index = names.index("XTestFakeMotionEvent")
    press_index = calls.index(("XTestFakeButtonEvent", (1, 1, 1, 0)))
    release_index = calls.index(("XTestFakeButtonEvent", (1, 1, 0, 0)))
    assert motion_index < press_index < release_index


def test_xtest_binding_refuses_when_no_display_is_open():
    calls = []
    xlib, xtst = make_fake_x(calls, display=0)
    with pytest.raises(ui.UserInputError, match="X display is unavailable"):
        ui.XTestBackend(xlib, xtst)


def test_backend_loads_libx11_and_libxtst_once_and_caches(monkeypatch):
    loaded = []
    calls = []
    xlib, xtst = make_fake_x(calls)

    def fake_cdll(name):
        loaded.append(name)
        return xlib if "X11" in name else xtst

    monkeypatch.setattr(ui, "_BACKEND", None)
    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)
    first = ui.get_backend()
    second = ui.get_backend()
    assert first is second
    assert loaded == ["libX11.so.6", "libXtst.so.6"]
    assert [name for name, _ in calls].count("XOpenDisplay") == 1


def test_slug_is_a_safe_screenshot_label():
    assert ui.slug("Find Working Configuration") == "find-working-configuration"
    assert ui.slug("  Keep searching!! ") == "keep-searching"
    assert ui.slug("") == "control"
