"""Explicit, nonmodal browser for the metadata-only saved-case library."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from dentobot_case.catalog import Catalog
from dentobot_case.contracts import CHECKPOINTS, CaseInventory
from dentobot_case.lineage import available_cutoffs, select_prefix


def _row(kind: str, text: str, **values) -> dict:
    return {"kind": kind, "text": text, "children": [], **values}


def _target_fdis(inventory: CaseInventory) -> dict[str, str]:
    associations = inventory.metadata.get("targetToothAssociations", ())
    result = {}
    for association in associations:
        if isinstance(association, dict):
            target_id = association.get("targetId")
            fdi = association.get("fdi")
            if isinstance(target_id, str) and isinstance(fdi, str):
                result[target_id] = fdi
    return result


def _checkpoint_state(inventory: CaseInventory, target_id: str, branch_id: str, checkpoint_id: str) -> str:
    states = {
        artifact.state
        for artifact in inventory.artifacts
        if artifact.checkpoint_id == checkpoint_id
        and (
            artifact.scope == "shared"
            or (artifact.scope == "target" and artifact.target_id == target_id)
            or (artifact.scope == "branch" and artifact.target_id == target_id and artifact.branch_id == branch_id)
        )
    }
    return ", ".join(sorted(states)) if states else "No saved artifact"


def _checkpoint_rows(
    inventory: CaseInventory,
    *,
    path: str,
    package_id: str,
    location_status: str,
    target_id: str,
    branch_id: str,
) -> list[dict]:
    full_ok = location_status == "Valid" and inventory.integrity == "Valid"
    allowed_cutoffs = {
        selection.checkpoint_id: selection
        for selection in available_cutoffs(inventory, target_id, branch_id)
    }
    rows = []
    for checkpoint in CHECKPOINTS:
        if checkpoint.id in allowed_cutoffs:
            selection = allowed_cutoffs[checkpoint.id]
        else:
            selection = select_prefix(inventory, target_id, checkpoint.id, branch_id)
        selection_ok = bool(full_ok and selection.allowed)
        state = _checkpoint_state(inventory, target_id, branch_id, checkpoint.id)
        eligibility = "available" if selection_ok else "blocked"
        reason = ""
        if not full_ok:
            reason = f"Location: {location_status}; package integrity: {inventory.integrity}."
        elif not selection.allowed:
            reason = "; ".join(selection.reasons) or "Required saved evidence is unavailable."
            if selection.latest_complete_checkpoint:
                reason += f" Latest complete cutoff: {selection.latest_complete_checkpoint}."
        rows.append(_row(
            "checkpoint",
            f"{checkpoint.label} [{checkpoint.id}] — saved: {state}; cutoff: {eligibility}",
            path=path,
            package_id=package_id,
            location_status=location_status,
            integrity=inventory.integrity,
            checked_at_utc=inventory.checked_at_utc,
            saved_state=state,
            live_freshness=inventory.live_freshness,
            ownership_complete=inventory.ownership_complete,
            unknown_ownership=tuple(inventory.unknown_ownership),
            target_id=target_id,
            branch_id=branch_id,
            checkpoint_id=checkpoint.id,
            latest_complete_checkpoint=selection.latest_complete_checkpoint,
            partial_enabled=selection_ok,
            full_enabled=full_ok,
            included_ids=selection.included_ids if selection.allowed else (),
            excluded_ids=selection.excluded_ids,
            reason=reason,
        ))
    return rows


def build_rows(cases: list[dict]) -> tuple[dict, ...]:
    """Build plain tree rows from Catalog.list_cases() data; no filenames imply identity."""
    roots = []
    for case in cases:
        case_id = case.get("case_id")
        case_row = _row("case", f"Case {case_id}" if case_id else "Unbound scan location")
        revisions = case.get("package_revisions", ())
        locations = case.get("locations", ())
        if not revisions:
            for location in locations:
                path = location.get("path", "")
                reason = location.get("error") or location.get("status", "Unbound location")
                case_row["children"].append(_row(
                    "location",
                    f"{path} — {location.get('status', 'Unknown')}: {reason}",
                    path=path,
                    location_status=location.get("status", "Unknown"),
                    reason=reason,
                    full_enabled=False,
                    partial_enabled=False,
                ))
        for revision in revisions:
            package_id = revision.get("package_id", "Unknown package")
            inventory = CaseInventory.from_dict(revision["inventory"])
            revision_row = _row(
                "revision",
                f"Package {package_id} — SHA-256 {revision.get('sha256', 'unknown')}",
                package_id=package_id,
            )
            for location in locations:
                if location.get("package_id") != package_id:
                    continue
                path = location.get("path", "")
                status = location.get("status", "Unknown")
                full_ok = status == "Valid" and inventory.integrity == "Valid"
                location_reason = location.get("error", "")
                ownership_reason = "; ".join(inventory.unknown_ownership)
                if not inventory.ownership_complete and not ownership_reason:
                    ownership_reason = "Persistent artifact ownership is incomplete."
                detail = "; ".join(item for item in (location_reason, ownership_reason) if item)
                location_row = _row(
                    "location",
                    f"{path} — location: {status}; integrity: {inventory.integrity}; saved: {inventory.label}; live: {inventory.live_freshness}",
                    path=path,
                    package_id=package_id,
                    location_status=status,
                    integrity=inventory.integrity,
                    checked_at_utc=inventory.checked_at_utc,
                    live_freshness=inventory.live_freshness,
                    ownership_complete=inventory.ownership_complete,
                    unknown_ownership=tuple(inventory.unknown_ownership),
                    full_enabled=full_ok,
                    partial_enabled=False,
                    reason=detail,
                )
                if detail:
                    location_row["children"].append(_row("note", detail))
                fdis = _target_fdis(inventory)
                for target_id in inventory.target_ids:
                    fdi = fdis.get(target_id, "Unknown FDI")
                    target_row = _row(
                        "target",
                        f"Tooth {fdi} — target {target_id}",
                        path=path,
                        package_id=package_id,
                        location_status=status,
                        integrity=inventory.integrity,
                        checked_at_utc=inventory.checked_at_utc,
                        live_freshness=inventory.live_freshness,
                        ownership_complete=inventory.ownership_complete,
                        unknown_ownership=tuple(inventory.unknown_ownership),
                        target_id=target_id,
                        full_enabled=full_ok,
                        partial_enabled=False,
                        reason=detail,
                    )
                    branches = [branch for branch in inventory.branches if branch.target_id == target_id]
                    if branches:
                        branch_specs = [("", "No branch selected (before branch checkpoints)")]
                        branch_specs.extend(
                            (branch.id, f"Branch {branch.id} — {branch.state}; {branch.pairing_intent}")
                            for branch in branches
                        )
                    else:
                        branch_specs = [("", "No prepared branch")]
                    for branch_id, branch_label in branch_specs:
                        branch_row = _row(
                            "branch",
                            branch_label,
                            path=path,
                            package_id=package_id,
                            location_status=status,
                            integrity=inventory.integrity,
                            checked_at_utc=inventory.checked_at_utc,
                            live_freshness=inventory.live_freshness,
                            ownership_complete=inventory.ownership_complete,
                            unknown_ownership=tuple(inventory.unknown_ownership),
                            target_id=target_id,
                            branch_id=branch_id,
                            full_enabled=full_ok,
                            partial_enabled=False,
                            reason=detail,
                        )
                        branch_row["children"].extend(_checkpoint_rows(
                            inventory,
                            path=path,
                            package_id=package_id,
                            location_status=status,
                            target_id=target_id,
                            branch_id=branch_id,
                        ))
                        target_row["children"].append(branch_row)
                    location_row["children"].append(target_row)
                revision_row["children"].append(location_row)
            case_row["children"].append(revision_row)
        roots.append(case_row)
    return tuple(roots)


def show_case_library(
    parent,
    *,
    database_path: str,
    on_full_load: Callable[[str], object],
    on_partial_load: Callable[[str, str, str, str], object],
    on_partial_save: Callable[[str, str, str, str, str], object],
):
    """Open the explicit case browser and return its session state."""
    import qt

    dialog = qt.QDialog(parent)
    dialog.setWindowTitle("DENTOBOT Case Library")
    dialog.setModal(False)
    dialog.setAttribute(qt.Qt.WA_DeleteOnClose, False)
    layout = qt.QVBoxLayout(dialog)
    tree = qt.QTreeWidget(dialog)
    tree.setColumnCount(1)
    tree.setHeaderLabels(["Saved cases — package revision/location — tooth — branch — checkpoints"])
    layout.addWidget(tree)
    details = qt.QLabel("Choose an indexed location, tooth, branch or checkpoint to inspect.", dialog)
    details.wordWrap = True
    layout.addWidget(details)
    actions = qt.QHBoxLayout()
    scan_button = qt.QPushButton("Scan folder…", dialog)
    load_button = qt.QPushButton("Load full case", dialog)
    partial_load_button = qt.QPushButton("Load selected prefix", dialog)
    partial_save_button = qt.QPushButton("Save selected prefix as…", dialog)
    for button in (scan_button, load_button, partial_load_button, partial_save_button):
        actions.addWidget(button)
    layout.addLayout(actions)
    status = qt.QLabel("Opening library…", dialog)
    status.wordWrap = True
    layout.addWidget(status)

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dentobot-case-library")
    timer = qt.QTimer(dialog)
    timer.setInterval(80)
    active = {"future": None, "kind": "", "context": None, "dispatching": False}
    rows_by_token: dict[int, dict] = {}
    next_token = [1]
    session = SimpleNamespace(
        dialog=dialog,
        _case_library_executor=executor,
        _case_library_timer=timer,
        _case_library_closed=False,
        _case_library_tree=tree,
        _case_library_rows=rows_by_token,
    )

    def set_busy(value: bool) -> None:
        for button in (scan_button, load_button, partial_load_button, partial_save_button):
            button.setEnabled(not value)
        if value:
            tree.setEnabled(False)
        else:
            tree.setEnabled(True)
            selection_changed()

    def show_error(message: str) -> None:
        status.setText(str(message))

    def add_row(parent_item, row: dict) -> None:
        item = qt.QTreeWidgetItem(parent_item if parent_item is not None else tree)
        item.setText(0, row["text"])
        token = next_token[0]
        next_token[0] += 1
        rows_by_token[token] = row
        item.setData(0, qt.Qt.UserRole, token)
        if row.get("reason"):
            item.setToolTip(0, row["reason"])
        for child in row.get("children", ()):
            add_row(item, child)

    def render_cases(cases: list[dict]) -> None:
        tree.clear()
        rows_by_token.clear()
        for row in build_rows(cases):
            add_row(None, row)
        tree.expandToDepth(2)
        status.setText(f"Library contains {len(cases)} case groups. Scanning occurs only after Scan folder…")
        selection_changed()

    def selected_row() -> dict | None:
        item = tree.currentItem()
        if item is None:
            return None
        try:
            token = int(item.data(0, qt.Qt.UserRole))
        except (TypeError, ValueError):
            return None
        return rows_by_token.get(token)

    def selection_changed(*_args) -> None:
        row = selected_row()
        full_ok = bool(row and row.get("path") and row.get("full_enabled"))
        partial_ok = bool(
            row
            and row.get("path")
            and row.get("kind") == "checkpoint"
            and row.get("partial_enabled")
        )
        load_button.setEnabled(full_ok and active["future"] is None)
        partial_load_button.setEnabled(partial_ok and active["future"] is None)
        partial_save_button.setEnabled(partial_ok and active["future"] is None)
        if row is None:
            details.setText("Choose an indexed location, tooth, branch or checkpoint to inspect.")
            return
        fields = []
        for label, key in (
            ("Location", "location_status"),
            ("Integrity", "integrity"),
            ("Integrity checked (UTC)", "checked_at_utc"),
            ("Saved state", "saved_state"),
            ("Live freshness", "live_freshness"),
            ("Ownership", "ownership_complete"),
            ("Target", "target_id"),
            ("Branch", "branch_id"),
            ("Checkpoint", "checkpoint_id"),
        ):
            if key in row:
                fields.append(f"{label}: {row[key] or 'none'}")
        if row.get("included_ids"):
            fields.append("Included evidence IDs: " + ", ".join(row["included_ids"]))
        if row.get("reason"):
            fields.append("Reason: " + row["reason"])
        if row.get("unknown_ownership"):
            fields.append("Unknown ownership: " + "; ".join(row["unknown_ownership"]))
        details.setText("\n".join(fields) or row["text"])

    def submit(kind: str, worker: Callable, context=None) -> None:
        if active["future"] is not None or session._case_library_closed:
            return
        active.update(future=executor.submit(worker), kind=kind, context=context)
        set_busy(True)
        status.setText({
            "list": "Reading indexed case metadata…",
            "scan": "Scanning the selected folder…",
            "full": "Revalidating selected package…",
            "partial-load": "Revalidating package and prefix…",
            "partial-save": "Revalidating package and prefix…",
        }.get(kind, "Working…"))

    def with_catalog(action: Callable[[Catalog], object]):
        with Catalog(database_path) as catalog:
            return action(catalog)

    def load_index_worker():
        if not Path(database_path).is_file():
            return []
        return with_catalog(lambda catalog: catalog.list_cases())

    def scan_folder(*_args) -> None:
        folder = qt.QFileDialog.getExistingDirectory(dialog, "Select a folder to scan", "")
        if isinstance(folder, tuple):
            folder = folder[0]
        if not folder:
            return

        def worker():
            def scan(catalog):
                catalog.scan(folder)
                return catalog.list_cases()
            return with_catalog(scan)

        submit("scan", worker)

    def full_load(*_args) -> None:
        row = selected_row()
        if not row or not row.get("path") or not row.get("full_enabled"):
            return
        path = row["path"]
        label = row.get("saved_state") or "saved case"
        answer = qt.QMessageBox.question(
            dialog,
            "Replace current scene?",
            f"Load {label} from:\n{path}\n\nThe existing scene will be replaced.",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if answer != qt.QMessageBox.Yes:
            return

        def worker():
            inventory = with_catalog(lambda catalog: catalog.revalidate(path))
            if inventory.integrity != "Valid":
                raise ValueError(f"Package integrity is {inventory.integrity}; full load is blocked.")
            return inventory.path

        submit("full", worker, {"path": path})

    def _selected_prefix() -> dict | None:
        row = selected_row()
        if not row or row.get("kind") != "checkpoint" or not row.get("partial_enabled"):
            return None
        return row

    def partial_load(*_args) -> None:
        row = _selected_prefix()
        if row is None:
            return
        path = row["path"]
        target_id, checkpoint_id, branch_id = row["target_id"], row["checkpoint_id"], row["branch_id"]
        answer = qt.QMessageBox.question(
            dialog,
            "Replace current scene with selected prefix?",
            f"Load the saved prefix through {checkpoint_id} for target {target_id}?\n\nThe existing scene will be replaced.",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if answer != qt.QMessageBox.Yes:
            return

        def worker():
            inventory = with_catalog(lambda catalog: catalog.revalidate(path))
            selection = select_prefix(inventory, target_id, checkpoint_id, branch_id)
            if not selection.allowed:
                raise ValueError("Partial load is blocked: " + "; ".join(selection.reasons))
            return inventory.path

        submit("partial-load", worker, {
            "path": path, "target_id": target_id,
            "checkpoint_id": checkpoint_id, "branch_id": branch_id,
        })

    def partial_save(*_args) -> None:
        row = _selected_prefix()
        if row is None:
            return
        path = row["path"]
        target_id, checkpoint_id, branch_id = row["target_id"], row["checkpoint_id"], row["branch_id"]
        destination = qt.QFileDialog.getSaveFileName(
            dialog,
            "Save independent partial case",
            str(Path(path).with_name(Path(path).stem + "-partial.dentocase")),
            "DENTOBOT case package (*.dentocase)",
        )
        if isinstance(destination, tuple):
            destination = destination[0]
        if not destination:
            return
        def worker():
            inventory = with_catalog(lambda catalog: catalog.revalidate(path))
            selection = select_prefix(inventory, target_id, checkpoint_id, branch_id)
            if not selection.allowed:
                raise ValueError("Partial save is blocked: " + "; ".join(selection.reasons))
            source_resolved = os.path.normcase(os.path.realpath(path))
            destination_resolved = os.path.normcase(os.path.realpath(destination))
            if source_resolved == destination_resolved:
                raise ValueError("Choose a destination distinct from the source package.")
            return inventory.path

        submit("partial-save", worker, {
            "path": path, "target_id": target_id,
            "checkpoint_id": checkpoint_id, "branch_id": branch_id,
            "destination": destination,
        })

    def finish_job() -> None:
        # MRML callbacks pump Qt events; a completed future must be dispatched
        # once even if the polling timer fires during the load/projection.
        if session._case_library_closed or active["dispatching"]:
            return
        future = active["future"]
        if future is None or not future.done():
            return
        kind, context = active["kind"], active["context"]
        active["dispatching"] = True
        try:
            result = future.result()
            if kind in {"list", "scan"}:
                render_cases(result)
                return
            if kind == "full":
                on_full_load(result)
                status.setText(f"Full case load dispatched for {result}.")
            elif kind == "partial-load":
                on_partial_load(
                    result, context["target_id"], context["checkpoint_id"], context["branch_id"]
                )
                status.setText("Partial prefix load dispatched; live workflow owners must revalidate restored state.")
            elif kind == "partial-save":
                on_partial_save(
                    result, context["target_id"], context["checkpoint_id"],
                    context["branch_id"], context["destination"],
                )
                status.setText("Partial save dispatched; source package remains the input authority.")
        except Exception as exc:
            show_error(f"Case library action failed: {exc}")
        finally:
            active.update(future=None, kind="", context=None, dispatching=False)
            if not session._case_library_closed:
                set_busy(False)

    def close_worker(*_args) -> None:
        if session._case_library_closed:
            return
        session._case_library_closed = True
        timer.stop()
        executor.shutdown(wait=False, cancel_futures=True)

    scan_button.clicked.connect(scan_folder)
    load_button.clicked.connect(full_load)
    partial_load_button.clicked.connect(partial_load)
    partial_save_button.clicked.connect(partial_save)
    tree.currentItemChanged.connect(selection_changed)
    timer.timeout.connect(finish_job)
    dialog.finished.connect(close_worker)
    dialog.destroyed.connect(close_worker)
    timer.start()
    submit("list", load_index_worker)
    dialog.show()
    return session
