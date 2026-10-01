from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


PYTHON_ROOT = Path(__file__).resolve().parents[1] / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PYTHON_ROOT))

from dentobot_case.contracts import Artifact, Branch, CaseInventory, CHECKPOINTS  # noqa: E402
from dentobot_workflow import case_library  # noqa: E402


def inventory(*, owned=True, unknown=(), integrity="Valid"):
    artifacts = (
        Artifact("source", "source.volume", "shared"),
        Artifact("segmentation", "anatomy.segmentation", "shared", dependencies=("source",)),
        Artifact("pose", "foundation.pose", "shared", dependencies=("segmentation",)),
        Artifact(
            "trajectory", "trajectory.plan", "target", target_id="target-1",
            dependencies=("pose",), trajectory_ids=("trajectory-1",),
        ),
    )
    return CaseInventory(
        path="/cases/name-is-not-identity.dentocase",
        package_id="package-revision-1",
        case_id="case-stable-1",
        label="Saved synthetic case",
        archive_schema="2.0",
        package_sha256="a" * 64,
        checked_at_utc="2026-10-01T00:00:00Z",
        target_ids=("target-1",),
        artifacts=artifacts,
        branches=(Branch("branch-1", "target-1", ("trajectory-1",), "Single", "Ready"),),
        ownership_complete=owned,
        unknown_ownership=tuple(unknown),
        integrity=integrity,
        live_freshness="Unverified",
        metadata={"targetToothAssociations": [{"targetId": "target-1", "fdi": "FDI11"}]},
    )


def catalog_case(inv, *, location_status="Valid"):
    return [{
        "case_id": inv.case_id,
        "package_revisions": [{
            "package_id": inv.package_id,
            "sha256": inv.package_sha256,
            "case_id": inv.case_id,
            "inventory": inv.to_dict(),
        }],
        "locations": [{
            "path": inv.path,
            "package_id": inv.package_id,
            "status": location_status,
            "error": "rescan required" if location_status != "Valid" else None,
        }],
    }]


def rows_of_kind(rows, kind):
    found = []
    pending = list(rows)
    while pending:
        row = pending.pop()
        if row["kind"] == kind:
            found.append(row)
        pending.extend(row.get("children", ()))
    return found


def test_changed_location_disables_full_and_partial_actions():
    rows = case_library.build_rows(catalog_case(inventory(), location_status="Changed"))
    location = rows_of_kind(rows, "location")[0]
    checkpoint = next(row for row in rows_of_kind(rows, "checkpoint") if row["checkpoint_id"] == "trajectory.plan")

    assert location["full_enabled"] is False
    assert "rescan required" in location["reason"]
    assert checkpoint["partial_enabled"] is False
    assert checkpoint["location_status"] == "Changed"


def test_unknown_ownership_is_visible_but_partial_actions_stay_disabled():
    rows = case_library.build_rows(catalog_case(inventory(owned=False, unknown=("unmapped node group",))))
    location = rows_of_kind(rows, "location")[0]
    checkpoints = rows_of_kind(rows, "checkpoint")

    assert location["full_enabled"] is True
    assert location["ownership_complete"] is False
    assert "unmapped node group" in location["reason"]
    assert any("unmapped node group" in row["reason"] for row in checkpoints)
    assert not any(row["partial_enabled"] for row in checkpoints)


def test_prefix_tree_lists_only_closed_allowed_cutoffs_and_uses_fdi_metadata():
    rows = case_library.build_rows(catalog_case(inventory()))
    target = rows_of_kind(rows, "target")[0]
    checkpoint_rows = rows_of_kind(target["children"], "checkpoint")
    available = {row["checkpoint_id"] for row in checkpoint_rows if row["partial_enabled"]}
    expected = {CHECKPOINTS[index].id for index in (0, 1, 2, 4)}

    assert "Tooth FDI11 — target target-1" == target["text"]
    assert available == expected
    trajectory = next(row for row in checkpoint_rows if row["checkpoint_id"] == "trajectory.plan")
    assert {"source", "segmentation", "pose", "trajectory"}.issubset(trajectory["included_ids"])
    blocked_branch_cutoff = next(row for row in checkpoint_rows if row["checkpoint_id"] == "support.selection")
    assert not blocked_branch_cutoff["partial_enabled"]
    assert "Latest complete cutoff: trajectory.plan" in blocked_branch_cutoff["reason"]


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in tuple(self.callbacks):
            callback(*args)


class Widget:
    def __init__(self, *_args):
        self.enabled = True
        self.text = ""

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)


class Label(Widget):
    def setText(self, text):
        self.text = str(text)


class Button(Widget):
    def __init__(self, *_args):
        super().__init__()
        self.text = str(_args[0]) if _args else ""
        self.clicked = Signal()

    def click(self):
        if self.enabled:
            self.clicked.emit()


class Layout:
    def __init__(self, parent=None):
        self.items = []
        if isinstance(parent, Dialog):
            parent.layout = self

    def addWidget(self, widget):
        self.items.append(widget)

    def addLayout(self, layout):
        self.items.append(layout)


class TreeItem:
    def __init__(self, parent):
        self.parent = parent
        self.children = []
        self.values = {}
        if isinstance(parent, Tree):
            parent.top.append(self)
        else:
            parent.children.append(self)

    def setText(self, _column, text):
        self.text = str(text)

    def setData(self, _column, role, value):
        self.values[role] = value

    def data(self, _column, role):
        return self.values.get(role)

    def setToolTip(self, _column, text):
        self.tooltip = text


class Tree(Widget):
    def __init__(self, *_args):
        super().__init__()
        self.top = []
        self.currentItemChanged = Signal()
        self.current = None

    def setColumnCount(self, _count):
        pass

    def setHeaderLabels(self, _labels):
        pass

    def clear(self):
        self.top = []
        self.current = None

    def expandToDepth(self, _depth):
        pass

    def currentItem(self):
        return self.current

    def select(self, item):
        old, self.current = self.current, item
        self.currentItemChanged.emit(item, old)


class Timer:
    def __init__(self, *_args):
        self.timeout = Signal()
        self.running = False

    def setInterval(self, _milliseconds):
        pass

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def fire(self):
        if self.running:
            self.timeout.emit()


class Dialog(Widget):
    def __init__(self, *_args):
        super().__init__()
        self.finished = Signal()
        self.destroyed = Signal()

    def __setattr__(self, name, value):
        if name.startswith("_case_library_"):
            raise AttributeError(f"native QDialog rejects {name}")
        object.__setattr__(self, name, value)

    def setWindowTitle(self, _title):
        pass

    def setModal(self, _modal):
        pass

    def setAttribute(self, *_args):
        pass

    def show(self):
        pass


def fake_qt_module():
    return SimpleNamespace(
        QDialog=Dialog,
        QVBoxLayout=Layout,
        QHBoxLayout=Layout,
        QTreeWidget=Tree,
        QTreeWidgetItem=TreeItem,
        QLabel=Label,
        QPushButton=Button,
        QTimer=Timer,
        Qt=SimpleNamespace(WA_DeleteOnClose=1, UserRole=32),
        QMessageBox=SimpleNamespace(Yes=1, No=2, question=lambda *_args: 1),
        QFileDialog=SimpleNamespace(
            getExistingDirectory=lambda *_args: "",
            getSaveFileName=lambda *_args: "",
        ),
    )


def flatten_items(items):
    result = []
    pending = list(items)
    while pending:
        item = pending.pop()
        result.append(item)
        pending.extend(item.children)
    return result


def pump_until(timer, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        timer.fire()
        time.sleep(0.005)
    timer.fire()
    assert predicate(), "asynchronous browser operation did not complete"


# The browser now uses QTableWidget and paged queries; keep a compact host
# adapter for thread/reset behavior, then verify real PythonQt separately.
class Control(Widget):
    def __init__(self, *args):
        super().__init__()
        self.text = str(args[0]) if args and isinstance(args[0], str) else ""
        self.clicked = Signal()
        self.toggled = Signal()
        self.textChanged = Signal()
        self.returnPressed = Signal()
        self.itemSelectionChanged = Signal()
        self.currentIndexChanged = Signal()
        self.currentIndex = 0
        self.items = []
        self.cells = {}
        self.row = -1
        self.blocked = False
    def __getattr__(self, name):
        if name.startswith('set') or name in {'resize', 'show'}:
            return lambda *args: None
        raise AttributeError(name)
    @property
    def currentText(self):
        return self.items[self.currentIndex][0] if self.items else ''
    def addItem(self, label, data=None): self.items.append((label, data))
    def addItems(self, labels):
        for label in labels: self.addItem(label)
    def clear(self): self.items = []; self.currentIndex = 0
    def itemData(self, index): return self.items[index][1] if 0 <= index < len(self.items) else None
    def setCurrentIndex(self, index):
        self.currentIndex = index
        if not self.blocked: self.currentIndexChanged.emit(index)
    def blockSignals(self, value): self.blocked = value
    def currentRow(self): return self.row
    def setCurrentCell(self, row, col):
        self.row = row
        self.itemSelectionChanged.emit()
    def setItem(self, row, col, value): self.cells[row, col] = value
    def horizontalHeader(self): return Control()
    def verticalHeader(self): return Control()
    def click(self):
        if self.enabled: self.clicked.emit()

class TableLayout(Layout):
    def addWidget(self, widget, *args): self.items.append(widget)
    def addStretch(self, *args): pass
    def setContentsMargins(self, *args): pass

class BrowserDialog(Dialog, Control):
    def __init__(self, *args):
        Control.__init__(self, *args)
        self.finished = Signal()
        self.destroyed = Signal()
    def setMinimumSize(self, *args): pass
    def resize(self, *args): pass

class BrowserTimer(Timer):
    def setSingleShot(self, *args): pass


def browser_qt():
    result = fake_qt_module()
    result.QDialog = BrowserDialog
    result.QVBoxLayout = result.QHBoxLayout = TableLayout
    result.QTimer = BrowserTimer
    for name in ('QLineEdit', 'QComboBox', 'QTableWidget', 'QTableWidgetItem',
                 'QWidget', 'QLabel', 'QPushButton', 'QGroupBox', 'QPlainTextEdit', 'QProgressBar'):
        setattr(result, name, Control)
    result.QSettings = lambda: SimpleNamespace(value=lambda *args: 'light')
    result.QAbstractItemView = SimpleNamespace(SelectRows=1, SingleSelection=1, NoEditTriggers=1)
    return result


def test_browser_io_main_thread_activation_and_clear_generation(monkeypatch, tmp_path):
    import DENTOCaseBundle as owner
    import dentobot_case.inspection as inspector
    ui = threading.get_ident()
    inv = inventory()
    summary = {'case_key': inv.case_id, 'package_id': inv.package_id, 'path': inv.path,
               'label': inv.label, 'teeth': ['FDI11'], 'saved_at_utc': '',
               'package_status': 'Checked', 'workflow_status': 'Current'}
    state = {'cleared': False, 'threads': [], 'closed': False}
    scan_started, scan_stopped = threading.Event(), threading.Event()
    class FakeCatalog:
        def __init__(self, path):
            state['threads'].append(threading.get_ident())
            assert threading.get_ident() != ui
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def list_case_summaries(self, **kwargs):
            return {'items': [] if state['cleared'] else [summary], 'total': 0 if state['cleared'] else 1}
        def get_case_details(self, key):
            return {'case_key': inv.case_id, 'revisions': [{'package_id': inv.package_id,
                'saved_at_utc': '', 'inventory': inv, 'metadata': inv.metadata,
                'locations': [{'path': inv.path, 'status': 'Valid', 'error': None}]}]}
        def record_verified(self, value): assert value == inv
        def scan(self, **kwargs):
            scan_started.set()
            while not kwargs['cancelled']():
                time.sleep(.001)
            scan_stopped.set()
        def clear(self):
            assert scan_stopped.is_set(), 'Reset must await the catalog writer'
            state['cleared'] = True
    prepared = SimpleNamespace(path=inv.path, inspection=object(),
        assert_source_unchanged=lambda: None, close=lambda: state.update(closed=True))
    monkeypatch.setattr(case_library, 'Catalog', FakeCatalog)
    monkeypatch.setitem(sys.modules, 'qt', browser_qt())
    monkeypatch.setattr(owner, 'prepare_case_bundle', lambda *args, **kwargs: prepared)
    monkeypatch.setattr(owner, 'sha256_file', lambda *args: inv.package_sha256)
    monkeypatch.setattr(inspector, 'inventory_from_inspection', lambda *args: inv)
    received = []
    session = None
    def loaded(value):
        assert threading.get_ident() == ui and value is prepared
        assert not session._buttons['clear'].enabled
        received.append(value)
        session._case_library_timer.fire()
        assert len(received) == 1
    session = case_library.show_case_library(None, database_path=str(tmp_path/'library.sqlite'),
        on_full_load=loaded, on_partial_load=lambda *args: None, on_partial_save=lambda *args: None)
    timer = session._case_library_timer
    pump_until(timer, lambda: session._details is not None and session._buttons['full'].enabled)
    session._buttons['full'].click()
    pump_until(timer, lambda: bool(received))
    assert state['closed']
    session._buttons['refresh'].click()
    pump_until(timer, scan_started.is_set)
    session._buttons['clear'].click()
    pump_until(timer, lambda: state['cleared'] and not session._rows)
    assert session._case_library_total == 0  # stale scan completion cannot repopulate

    assert state['threads'] and all(value != ui for value in state['threads'])
    session.dialog.finished.emit(0)
    assert session._case_library_closed and not timer.running
