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


def test_filesystem_revalidation_runs_off_thread_and_callbacks_run_on_ui_thread(monkeypatch, tmp_path):
    ui_thread = threading.get_ident()
    inv = inventory()
    db = tmp_path / "library.sqlite"
    db.touch()
    worker_threads = []
    received = []
    dialog_ref = []

    class FakeCatalog:
        def __init__(self, _path):
            worker_threads.append(threading.get_ident())

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def list_cases(self):
            assert threading.get_ident() != ui_thread
            return catalog_case(inv)

        def revalidate(self, path):
            assert threading.get_ident() != ui_thread
            assert path == inv.path
            return inv

    monkeypatch.setattr(case_library, "Catalog", FakeCatalog)
    monkeypatch.setitem(sys.modules, "qt", fake_qt_module())

    def on_full_load(path):
        assert threading.get_ident() == ui_thread
        assert dialog_ref[0]._case_library_tree.enabled is False
        assert all(not button.enabled for button in dialog_ref[0].layout.items[2].items)
        received.append(("full", path))

    def on_partial_load(path, target_id, checkpoint_id, branch_id):
        assert threading.get_ident() == ui_thread
        assert dialog_ref[0]._case_library_tree.enabled is False
        assert all(not button.enabled for button in dialog_ref[0].layout.items[2].items)
        received.append(("partial", path, target_id, checkpoint_id, branch_id))

    dialog = case_library.show_case_library(
        None,
        database_path=str(db),
        on_full_load=on_full_load,
        on_partial_load=on_partial_load,
        on_partial_save=lambda *_args: pytest.fail("unexpected partial save callback"),
    )
    dialog_ref.append(dialog)
    timer = dialog._case_library_timer
    pump_until(timer, lambda: bool(dialog._case_library_tree.top))
    items = flatten_items(dialog._case_library_tree.top)
    location = next(item for item in items if item.text.startswith(inv.path))
    dialog._case_library_tree.select(location)
    load_button = next(item for item in dialog.layout.items[2].items if item.text == "Load full case")
    load_button.click()
    pump_until(timer, lambda: len(received) == 1)

    checkpoint_item = next(
        item for item in flatten_items(dialog._case_library_tree.top)
        if "trajectory.plan" in item.text and "cutoff: available" in item.text
    )
    dialog._case_library_tree.select(checkpoint_item)
    partial_button = next(item for item in dialog.layout.items[2].items if item.text == "Load selected prefix")
    partial_button.click()
    pump_until(timer, lambda: len(received) == 2)

    assert worker_threads and all(thread_id != ui_thread for thread_id in worker_threads)
    assert received[0] == ("full", inv.path)
    assert received[1] == ("partial", inv.path, "target-1", "trajectory.plan", "branch-1")
    dialog.finished.emit(0)
    assert dialog._case_library_closed is True
    assert timer.running is False
