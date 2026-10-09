"""Host tests for combo row selection (S6-ADVISOR-GUI-01 harness: ``select_combo_item``).

No Qt, Slicer or X server is used. The fake combo reproduces the 6.0 registry combo's shape: a tree
model whose one top-level row ('Scene') holds the selectable items as children, a popup list that is
its own X window, and rows whose geometry becomes valid after a delay. The fake backend presses like
a pointer: the release over a row selects it, and the popup closes. The assertions cover the row index
under the root, the wait for stable geometry, the popup-window hit at the row, the verified index and the
loud refusals (no press is sent on a refusal before the row press).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step6_user_input as ui  # noqa: E402
import test_step6_user_input as base  # noqa: E402  (FakeClock, FakeRect, FakePoint)

MAIN = 0x1000
MAIN_CHILD = 0x1001
POPUP = 0x2000055  # the popup list's own X window (Xwayland top-level)
TEXTS = [
    "None",
    "[Step 4A] DENTO FDI 14 - Trajectory 1 [Complete]",
    "[Step 4A] DENTO FDI 34 - Trajectory 1 [Complete]",
    "[Step 4A] DENTO FDI 31 - Trajectory 1 [Complete]",
    "[Step 4A] DENTO FDI 42 - Trajectory 1 [Complete]",
    "[Step 4A] DENTO FDI 11 - Trajectory 1 [Complete]",
]
TARGET_ROW = 2
TARGET_TEXT = TEXTS[TARGET_ROW]
START_ROW = 5
ROW_H = 15
POPUP_W = 420
POPUP_H = 92
COMBO_X, COMBO_Y, COMBO_W, COMBO_H = 300, 380, 420, 30
POPUP_X, POPUP_Y = 300, 411


@pytest.fixture
def clock(monkeypatch):
    fake = base.FakeClock()
    monkeypatch.setattr(ui, "_NOW", fake.now)
    monkeypatch.setattr(ui, "_SLEEP", fake.sleep)
    return fake


class FakeIndex:
    def __init__(self, row, parent, valid, data=""):
        self.row, self.parent, self._valid, self._data = row, parent, valid, data

    def isValid(self):
        return self._valid


class FakeModel:
    """Tree model as in the 6.0 combo: the top level holds one root; the items are the root's children."""

    def __init__(self):
        self.root = FakeIndex(0, None, True, "Scene")
        self.children = [FakeIndex(i, self.root, True, text) for i, text in enumerate(TEXTS)]

    def index(self, row, column, parent=None):
        if parent is self.root:
            return self.children[row] if 0 <= row < len(self.children) else FakeIndex(row, parent, False)
        if parent is None or not parent.isValid():
            return self.root if row == 0 else FakeIndex(row, None, False)
        return FakeIndex(row, parent, False)

    def data(self, index):
        return index._data if index.isValid() else None

    def rowCount(self, parent=None):
        return len(self.children) if parent is self.root else 1


class FakeQRect:
    def __init__(self, x, y, width, height):
        self._x, self._y, self._w, self._h = x, y, width, height

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h

    def isValid(self):
        return self._w > 0 and self._h > 0

    def center(self):
        return base.FakePoint(self._x + self._w // 2, self._y + self._h // 2)


class FakeWidget:
    """A widget with global origin, class names and an X window id."""

    def __init__(self, name, cls, *, parent=None, x=0, y=0, width=0, height=0, native=0):
        self.objectName = name
        self._class = cls
        self._parent = parent
        self._origin = (x, y)
        self.width = width
        self.height = height
        self._native = native
        self.visible = True
        self.enabled = True
        self.collapsed = False
        self._inherits = {cls, "QWidget", "QObject"}
        self.raised = 0
        self.activated = 0

    @property
    def rect(self):
        return base.FakeRect(self.width, self.height)

    def className(self):
        return self._class

    def inherits(self, name):
        return name in self._inherits

    def parent(self):
        return self._parent

    def winId(self):
        return self._native

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
        return base.FakePoint(self._origin[0] + point.x(), self._origin[1] + point.y())

    def raise_(self):
        self.raised += 1

    def activateWindow(self):
        self.activated += 1


class World:
    """The combo, its popup and the pointer. ``rows_valid_after`` delays row geometry after opening;
    ``popup_x_mapped`` False keeps the popup off the X stack; ``opens``/``selects`` break the press."""

    def __init__(self, *, rows_valid_after=0.0, popup_x_mapped=True, selects=True, opens=True, wheel=True):
        self.rows_valid_after = rows_valid_after
        self.popup_x_mapped = popup_x_mapped
        self.selects = selects
        self.opens = opens
        self.wheel = wheel
        self.scroll = 0  # pixels the popup list is scrolled by wheel notches
        self.popup_open = False
        self.opened_at = None
        self.position = (0, 0)
        self.current = START_ROW
        self.events = []
        self.model = FakeModel()
        self.main = FakeWidget("mainWindow", "QMainWindow", x=0, y=0, width=1200, height=800, native=MAIN)
        self.main_child = FakeWidget("qt_child", "QWidget", parent=self.main, x=0, y=500, width=1200,
                                     height=300, native=MAIN_CHILD)
        self.combo = FakeCombo(self)
        self.view = FakeView(self)
        self.container = FakeWidget("QComboBoxPrivateContainer", "QComboBoxPrivateContainer",
                                    x=POPUP_X, y=POPUP_Y, width=POPUP_W, height=POPUP_H, native=POPUP)
        self.viewport = FakeWidget("qt_scrollarea_viewport", "QWidget", x=POPUP_X, y=POPUP_Y,
                                   width=POPUP_W, height=POPUP_H)
        self.viewport._parent = self.view
        self.view._container = self.container
        self.container._parent = None

    # --- geometry ---
    def in_popup(self, point):
        x, y = point
        return POPUP_X <= x < POPUP_X + POPUP_W and POPUP_Y <= y < POPUP_Y + POPUP_H

    def in_combo(self, point):
        x, y = point
        return COMBO_X <= x < COMBO_X + COMBO_W and COMBO_Y <= y < COMBO_Y + COMBO_H

    def row_rect(self, row):
        if not self.popup_open or ui._NOW() - self.opened_at < self.rows_valid_after:
            return FakeQRect(0, 0, 0, 0)
        if not 0 <= row < len(TEXTS):
            return FakeQRect(0, 0, 0, 0)
        return FakeQRect(0, row * ROW_H - self.scroll, POPUP_W - 2, ROW_H)

    def max_scroll(self):
        return max(0, len(TEXTS) * ROW_H - POPUP_H)

    # --- pointer ---
    def move(self, x, y):
        self.position = (int(x), int(y))
        self.events.append(("move", int(x), int(y)))

    def chain(self):
        if self.popup_open and self.popup_x_mapped and self.in_popup(self.position):
            return [POPUP]
        return [MAIN, MAIN_CHILD]

    def button(self, button, pressed):
        self.events.append(("button", int(button), bool(pressed)))
        if int(button) in (ui.POPUP_WHEEL_UP, ui.POPUP_WHEEL_DOWN):
            if pressed and self.wheel and self.popup_open and self.in_popup(self.position):
                step = 3 * ROW_H if int(button) == ui.POPUP_WHEEL_DOWN else -3 * ROW_H
                self.scroll = min(max(self.scroll + step, 0), self.max_scroll())
            return
        if not pressed:
            self._release()

    def _release(self):
        point = self.position
        if not self.popup_open:
            if self.in_combo(point) and self.opens:
                self.popup_open = True
                self.opened_at = ui._NOW()
            return
        if self.in_popup(point) and self.popup_x_mapped:
            row = (point[1] - POPUP_Y + self.scroll) // ROW_H
            if self.selects and 0 <= row < len(TEXTS):
                self.current = row
        self.popup_open = False


class FakeCombo(FakeWidget):
    def __init__(self, world):
        super().__init__("S6ComboFake", "ctkComboBox", parent=world.main, x=COMBO_X, y=COMBO_Y,
                         width=COMBO_W, height=COMBO_H)
        self._inherits.add("QComboBox")
        self._world = world

    @property
    def count(self):
        return len(TEXTS)

    def itemText(self, index):
        return TEXTS[int(index)]

    @property
    def currentIndex(self):
        return self._world.current

    @property
    def currentText(self):
        return TEXTS[self._world.current]

    def model(self):
        return self._world.model

    def rootModelIndex(self):
        return self._world.model.root

    def view(self):
        return self._world.view


class FakeView(FakeWidget):
    def __init__(self, world):
        super().__init__("S6ComboFakeView", "QComboBoxListView", parent=world.main)
        self._world = world
        self._container = None

    def isVisible(self):
        return self._world.popup_open

    def window(self):
        return self._container

    def model(self):
        return self._world.model

    def visualRect(self, index):
        if not index.isValid():
            return FakeQRect(0, 0, 0, 0)
        return self._world.row_rect(index.row)

    def viewport(self):
        return self._world.viewport

    def isAncestorOf(self, other):
        return other is self._world.viewport


class FakeApp:
    def __init__(self, world):
        self._world = world

    def processEvents(self):
        return None

    def widgetAt(self, point):
        xy = (point.x(), point.y())
        if self._world.popup_open and self._world.in_popup(xy):
            return self._world.viewport
        if self._world.in_combo(xy):
            return self._world.combo
        return self._world.main_child

    def activePopupWidget(self):
        return None

    def screenAt(self, point):
        return SimpleNamespace(devicePixelRatio=1.0)


class FakeXBackend:
    """Pointer, chain and EWMH activation for the world (the object the harness calls)."""

    def __init__(self, world):
        self._world = world

    def pointer(self):
        return self._world.position

    def move(self, x, y):
        self._world.move(x, y)

    def button(self, button, pressed):
        self._world.button(button, pressed)

    def pointer_chain(self):
        return list(self._world.chain())

    def activate_window(self, window):
        return None

    def active_window(self):
        return MAIN

    def window_name(self, window):
        return "Slicer" if window == POPUP else ""

    def desktop_size(self):
        return (1920, 1080)


def install(monkeypatch, world):
    qt = SimpleNamespace(QApplication=FakeApp(world), QPoint=lambda x, y: base.FakePoint(x, y))
    slicer = SimpleNamespace(util=SimpleNamespace(mainWindow=lambda: world.main))
    backend = FakeXBackend(world)
    monkeypatch.setattr(ui, "_runtime", lambda: (qt, slicer))
    monkeypatch.setattr(ui, "get_backend", lambda: backend)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: backend)
    return backend


def run_select(world, tmp_path, *, text=TARGET_TEXT, row=TARGET_ROW, mode="uinput"):
    ledger = tmp_path / "session" / "user-input-ledger.jsonl"
    try:
        record = ui.select_combo_item(world.combo, row, text, mode=mode, evidence=ledger)
        return record, None, ledger
    except ui.UserInputError as refusal:
        return None, refusal, ledger


def test_a_list_row_is_indexed_under_the_combo_root_and_the_top_level_index_is_invalid():
    world = World()
    assert ui.combo_row_index(world.combo, TARGET_ROW).isValid()
    assert ui.combo_row_index(world.combo, TARGET_ROW).parent is world.model.root
    assert world.model.index(TARGET_ROW, 0).isValid() is False


def test_the_row_is_pressed_on_its_popup_geometry_and_the_selection_is_verified(monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, ledger = run_select(world, tmp_path)
    assert refusal is None
    assert record["delivered"] is True and record["row"] == TARGET_ROW
    assert world.current == TARGET_ROW and world.combo.currentText == TARGET_TEXT
    presses = [event for event in world.events if event[0] == "button" and event[2]]
    assert len(presses) == 2  # the press that opens the popup, then the row press
    moves = [event[1:] for event in world.events if event[0] == "move"]
    expected_row_xy = (POPUP_X + (POPUP_W - 2) // 2, POPUP_Y + TARGET_ROW * ROW_H + ROW_H // 2)
    assert moves[-1] == expected_row_xy
    steps = {step["step"] for step in record["steps"]}
    assert {"open_press", "row_stable", "row_hit", "release"} <= steps
    assert not hasattr(world.combo, "setCurrentIndex")  # the selection is made by the pointer only
    saved = json.loads(ledger.read_text().splitlines()[0])
    assert saved["action"] == "combo row selection" and saved["delivered"] is True


def test_geometry_that_settles_late_is_waited_for_and_then_pressed(monkeypatch, clock, tmp_path):
    world = World(rows_valid_after=0.6)
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path)
    assert refusal is None and world.current == TARGET_ROW
    assert record["steps"][1]["step"] == "row_stable"


def test_a_row_that_never_gets_valid_geometry_is_refused_before_the_row_press(monkeypatch, clock, tmp_path):
    world = World(rows_valid_after=1e9)
    install(monkeypatch, world)
    record, refusal, ledger = run_select(world, tmp_path)
    assert record is None and "no stable valid geometry" in str(refusal)
    assert world.current == START_ROW
    assert [event for event in world.events if event[0] == "button"] == [
        ("button", 1, True), ("button", 1, False)]  # only the press that opened the popup
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["delivered"] is False and "no stable valid geometry" in entry["refused"]


def test_a_row_point_that_is_not_over_the_popup_window_is_refused_without_a_row_press(monkeypatch, clock, tmp_path):
    world = World(popup_x_mapped=False)
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path)
    assert record is None and "not over the popup window" in str(refusal)
    assert world.current == START_ROW
    assert [event for event in world.events if event[0] == "button"] == [
        ("button", 1, True), ("button", 1, False)]


def test_a_press_that_does_not_select_the_row_is_refused_loudly_and_no_other_row_is_chosen(monkeypatch, clock, tmp_path):
    world = World(selects=False)
    install(monkeypatch, world)
    record, refusal, ledger = run_select(world, tmp_path)
    assert record is None and f"did not select row {TARGET_ROW}" in str(refusal)
    assert world.current == START_ROW
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["delivered"] is False


def test_a_popup_that_does_not_open_is_refused_before_any_row_is_touched(monkeypatch, clock, tmp_path):
    world = World(opens=False)
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path)
    assert record is None and "the popup did not open" in str(refusal)
    assert world.current == START_ROW


def test_an_expected_text_that_does_not_match_the_row_is_refused_before_any_press(monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path, text=TEXTS[1])
    assert record is None and "expected" in str(refusal)
    assert world.events == []


def test_only_real_pointer_modes_may_select_a_combo_row(monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path, mode="qt_click")
    assert record is None and "real pointer input" in str(refusal)
    assert world.events == []


def test_xtest_mode_selects_the_row_through_the_same_path(monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path, mode="xtest")
    assert refusal is None and world.current == TARGET_ROW and record["mode"] == "xtest"


# --- the stage combo: 11 rows in a popup that shows 10 (Qt maxVisibleItems default) ----------------------
# The row "6 · Robot Placement" (row 10) is below the visible list; select_combo_item must scroll the list with
# real wheel notches over the popup before it presses the row. Visible rows get no wheel.
STAGE_TEXTS = [f"{index} · Stage {index}" for index in range(11)]
STAGE_TARGET = 10


@pytest.fixture
def stage_popup(monkeypatch):
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "TEXTS", STAGE_TEXTS)
    monkeypatch.setattr(module, "POPUP_H", 10 * ROW_H + 2)  # ten rows visible
    return STAGE_TEXTS


def _presses(world):
    return [event for event in world.events if event[0] == "button" and event[2] and event[1] == 1]


def test_a_row_below_the_visible_popup_is_reached_with_wheel_notches_then_pressed(stage_popup, monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, ledger = run_select(world, tmp_path, text=stage_popup[STAGE_TARGET], row=STAGE_TARGET, mode="xtest")
    assert refusal is None, refusal
    assert world.current == STAGE_TARGET and world.combo.currentText == stage_popup[STAGE_TARGET]
    wheel_down = [event for event in world.events if event[0] == "button" and event[1] == ui.POPUP_WHEEL_DOWN]
    assert wheel_down and all(event[2] for event in wheel_down[::2])  # press/release pairs, all downward
    assert not [event for event in world.events if event[0] == "button" and event[1] == ui.POPUP_WHEEL_UP]
    scroll = next(step for step in record["steps"] if step["step"] == "popup_scroll")
    assert scroll["notches"] == len([event for event in wheel_down if event[2]]) >= 1
    assert record["delivered"] is True
    assert json.loads(ledger.read_text().splitlines()[0])["delivered"] is True


def test_a_wheel_that_never_brings_the_row_into_the_popup_is_refused_before_the_row_press(stage_popup, monkeypatch, clock, tmp_path):
    world = World(wheel=False)
    install(monkeypatch, world)
    record, refusal, ledger = run_select(world, tmp_path, text=stage_popup[STAGE_TARGET], row=STAGE_TARGET, mode="xtest")
    assert record is None and "did not come into the popup" in str(refusal)
    assert world.current == START_ROW
    assert len(_presses(world)) == 1  # only the press that opened the popup
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["delivered"] is False and "did not come into the popup" in entry["refused"]


def test_uinput_mode_refuses_the_wheel_and_presses_nothing_for_a_row_below_the_popup(stage_popup, monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path, text=stage_popup[STAGE_TARGET], row=STAGE_TARGET, mode="uinput")
    assert record is None and "wheel is not sent in uinput mode" in str(refusal)
    assert world.current == START_ROW
    assert not [event for event in world.events if event[0] == "button" and event[1] in (ui.POPUP_WHEEL_UP, ui.POPUP_WHEEL_DOWN)]
    assert len(_presses(world)) == 1


def test_a_visible_row_is_pressed_without_any_wheel_notch(stage_popup, monkeypatch, clock, tmp_path):
    world = World()
    install(monkeypatch, world)
    record, refusal, _ledger = run_select(world, tmp_path, text=stage_popup[3], row=3, mode="xtest")
    assert refusal is None and world.current == 3
    assert not [event for event in world.events if event[0] == "button" and event[1] in (ui.POPUP_WHEEL_UP, ui.POPUP_WHEEL_DOWN)]
    assert not [step for step in record["steps"] if step["step"] == "popup_scroll"]
