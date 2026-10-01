"""Explicit, nonmodal browser for the metadata-only saved-case library."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import logging
from pathlib import Path
import threading
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


def _friendly_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError, OverflowError):
        return "Unknown"


def _status_group(value: str) -> tuple[str, str]:
    status = str(value or "Unknown").strip().casefold()
    if status in {"checked", "current", "valid"}:
        return "✓", "green"
    if status in {"changed", "stale", "incomplete"}:
        return "!", "amber"
    if status in {"invalid", "conflict", "blocked", "error"}:
        return "×", "red"
    if status in {"busy", "scanning", "verifying"}:
        return "…", "blue"
    return "–", "grey"


def _preview_saved_state(preview: list[dict], checkpoint_id: str, target_id: str, branch_id: str) -> str:
    states = set()
    for item in preview:
        if not isinstance(item, dict) or item.get("checkpoint_id") != checkpoint_id:
            continue
        scope = item.get("scope")
        matches = (
            scope == "shared"
            or (scope == "target" and item.get("target_id") == target_id)
            or (
                scope == "branch"
                and item.get("target_id") == target_id
                and item.get("branch_id") == branch_id
            )
        )
        if matches:
            states.add(str(item.get("state") or "Unknown"))
    return ", ".join(sorted(states)) if states else "Unknown"


def show_case_library(
    parent,
    *,
    database_path: str,
    on_full_load: Callable[[object], object],
    on_partial_load: Callable[[str, str, str, str], object],
    on_partial_save: Callable[[str, str, str, str, str], object],
):
    """Open the nonmodal case browser; catalog and package I/O stays off the UI thread."""
    import qt

    page_size = 100
    dialog = qt.QDialog(parent)
    dialog.setWindowTitle("DentoCase Library")
    dialog.setModal(False)
    dialog.setAttribute(qt.Qt.WA_DeleteOnClose, False)
    dialog.setMinimumSize(900, 600)
    dialog.resize(1100, 700)
    layout = qt.QVBoxLayout(dialog)

    search_row = qt.QHBoxLayout()
    search = qt.QLineEdit(dialog)
    search.setPlaceholderText("Search case label or known tooth (for example, FDI11)")
    status_filter = qt.QComboBox(dialog)
    status_filter.addItems([
        "All statuses", "Checked", "Current", "Changed", "Stale", "Incomplete",
        "Invalid", "Conflict", "Blocked", "Unchecked", "Unknown", "Missing", "Busy",
    ])
    search_button = qt.QPushButton("Search", dialog)
    search_row.addWidget(search, 1)
    search_row.addWidget(status_filter)
    search_row.addWidget(search_button)
    add_folder = qt.QPushButton("Add folder…", dialog)
    refresh = qt.QPushButton("Refresh", dialog)
    clear = qt.QPushButton("Clear Library", dialog)
    for button in (add_folder, refresh, clear):
        search_row.addWidget(button)
    layout.addLayout(search_row)

    table = qt.QTableWidget(0, 5, dialog)
    table.setObjectName("DENTOBOTCaseLibraryTable")
    table.setHorizontalHeaderLabels(["Case", "Teeth", "Saved", "Package", "Workflow"])
    table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
    table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    table.setMinimumHeight(150)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.horizontalHeader().setStretchLastSection(True)
    for column, width in enumerate((270, 110, 165, 150, 140)):
        table.setColumnWidth(column, width)
    layout.addWidget(table, 2)

    page_row = qt.QHBoxLayout()
    previous_page = qt.QPushButton("‹ Previous", dialog)
    page_label = qt.QLabel("Page 1", dialog)
    next_page = qt.QPushButton("Next ›", dialog)
    page_row.addWidget(previous_page)
    page_row.addWidget(page_label, 1)
    page_row.addWidget(next_page)
    layout.addLayout(page_row)

    details_title = qt.QLabel("Select a saved case to see its preparation and checkpoints.", dialog)
    detail_header = qt.QHBoxLayout()
    detail_header.addWidget(details_title, 1)
    verify = qt.QPushButton("Verify package", dialog)
    detail_header.addWidget(verify)
    layout.addLayout(detail_header)
    revision_row = qt.QHBoxLayout()
    revision_row.addWidget(qt.QLabel("Saved revision:", dialog))
    revision_combo = qt.QComboBox(dialog)
    revision_row.addWidget(revision_combo, 1)
    revision_row.addWidget(qt.QLabel("Location:", dialog))
    location_combo = qt.QComboBox(dialog)
    revision_row.addWidget(location_combo, 1)
    layout.addLayout(revision_row)

    scope_row = qt.QHBoxLayout()
    scope_row.addWidget(qt.QLabel("Tooth:", dialog))
    tooth_combo = qt.QComboBox(dialog)
    scope_row.addWidget(tooth_combo, 1)
    scope_row.addWidget(qt.QLabel("Preparation:", dialog))
    branch_combo = qt.QComboBox(dialog)
    scope_row.addWidget(branch_combo, 2)
    layout.addLayout(scope_row)

    preparation = qt.QLabel("Preparation: Unknown", dialog)
    layout.addWidget(preparation)
    checkpoint_table = qt.QTableWidget(0, 4, dialog)
    checkpoint_table.setObjectName("DENTOBOTCaseLibraryCheckpointTable")
    checkpoint_table.setHorizontalHeaderLabels(["Checkpoint", "Saved state", "Cutoff", "Reason"])
    checkpoint_table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    checkpoint_table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
    checkpoint_table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    checkpoint_table.setMaximumHeight(185)
    checkpoint_table.verticalHeader().setVisible(False)
    checkpoint_table.horizontalHeader().setStretchLastSection(True)
    for column, width in enumerate((270, 120, 130, 280)):
        checkpoint_table.setColumnWidth(column, width)
    layout.addWidget(checkpoint_table, 2)
    readiness = qt.QLabel(
        "Live readiness: Unverified. Loading a saved package does not make its evidence current.",
        dialog,
    )
    readiness.wordWrap = True
    layout.addWidget(readiness)

    technical = qt.QGroupBox("Technical details", dialog)
    technical.setCheckable(True)
    technical.setChecked(False)
    technical_layout = qt.QVBoxLayout(technical)
    technical_text = qt.QPlainTextEdit(technical)
    technical_text.setReadOnly(True)
    technical_layout.addWidget(technical_text)
    copy_button = qt.QPushButton("Copy technical details", technical)
    technical_layout.addWidget(copy_button)
    technical_text.setVisible(False)
    copy_button.setVisible(False)
    def toggle_technical(checked):
        technical_text.setVisible(checked)
        copy_button.setVisible(checked)
        technical.setMaximumHeight(145 if checked else 35)
    technical.toggled.connect(toggle_technical)
    technical.setMaximumHeight(35)
    layout.addWidget(technical)

    actions = qt.QHBoxLayout()
    full_load = qt.QPushButton("Load full case", dialog)
    partial_load = qt.QPushButton("Load selected prefix", dialog)
    partial_save = qt.QPushButton("Save selected prefix as…", dialog)
    for button in (full_load, partial_load, partial_save):
        actions.addWidget(button)
    layout.addLayout(actions)

    progress_row = qt.QHBoxLayout()
    progress_bar = qt.QProgressBar(dialog)
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)
    progress_status = qt.QLabel("Opening the local catalog…", dialog)
    cancel = qt.QPushButton("Cancel", dialog)
    cancel.setEnabled(False)
    progress_row.addWidget(progress_bar)
    progress_row.addWidget(progress_status, 1)
    progress_row.addWidget(cancel)
    layout.addLayout(progress_row)

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dentobot-case-library")
    timer = qt.QTimer(dialog)
    timer.setInterval(75)
    active = {
        "future": None, "kind": "", "context": None, "cancel": None,
        "progress": None, "dispatching": False,
    }
    session = SimpleNamespace(
        dialog=dialog,
        _case_library_executor=executor,
        _case_library_timer=timer,
        _case_library_closed=False,
        _case_library_generation=0,
        _case_library_page=0,
        _case_library_total=0,
        _case_library_rows={},
        _case_library_summaries=[],
        _case_library_details=None,
        _case_library_selected_summary=None,
        _case_library_selected_identity=None,
        _case_library_pending_details=None,
        _case_library_pending_clear=False,
        _case_library_table=table,
        _case_library_checkpoint_table=checkpoint_table,
        _case_library_technical_text="",
        _case_library_tree=table,
        _table=table,
        _checkpoint_table=checkpoint_table,
        _rows=[],
        _details=None,
        _progress_status=progress_status,
        _buttons={"add": add_folder, "refresh": refresh, "clear": clear, "verify": verify,
                  "full": full_load, "partial": partial_load, "save": partial_save, "cancel": cancel},
        _revision_combo=revision_combo, _tooth_combo=tooth_combo, _branch_combo=branch_combo,
        _search=search, _status_filter=status_filter,
    )

    def with_catalog(action: Callable[[Catalog], object]):
        with Catalog(database_path) as catalog:
            return action(catalog)

    def _selected_summary() -> dict | None:
        row = table.currentRow()
        rows = session._case_library_summaries
        return rows[row] if 0 <= row < len(rows) else None

    def _selected_revision() -> dict | None:
        details = session._case_library_details
        if not details:
            return None
        package_id = revision_combo.itemData(revision_combo.currentIndex)
        return next(
            (item for item in details.get("revisions", ())
             if item.get("package_id") == package_id),
            None,
        )

    def _selected_location(revision: dict | None = None) -> dict | None:
        revision = revision if revision is not None else _selected_revision()
        if not revision:
            return None
        path = location_combo.itemData(location_combo.currentIndex)
        return next(
            (item for item in revision.get("locations", ()) if item.get("path") == path),
            None,
        )

    def _selection_identity() -> tuple | None:
        summary = session._case_library_selected_summary
        revision = _selected_revision()
        location = _selected_location(revision)
        if not summary or not revision or not location:
            return None
        return summary.get("case_key"), revision.get("package_id"), location.get("path")

    def _selected_checkpoint() -> dict | None:
        index = checkpoint_table.currentRow()
        return session._case_library_rows.get(index)

    def _update_actions():
        summary = session._case_library_selected_summary
        revision = _selected_revision()
        location = _selected_location(revision)
        identity = _selection_identity()
        session._case_library_selected_identity = identity
        if not summary or not revision or not location or not identity or active["future"] is not None:
            verify.setEnabled(False)
            full_load.setEnabled(False)
            partial_load.setEnabled(False)
            partial_save.setEnabled(False)
            return
        path = location.get("path", "")
        package_status = str(summary.get("package_status") or "Unknown").casefold()
        location_status = str(location.get("status") or "Unknown").casefold()
        blocked = {"invalid", "conflict", "missing", "blocked", "error"}
        full_allowed = bool(path) and not ({package_status, location_status} & blocked)
        verify.setEnabled(bool(path))
        full_load.setEnabled(full_allowed)
        row = _selected_checkpoint()
        partial_allowed = bool(row and row.get("partial_enabled"))
        partial_load.setEnabled(partial_allowed)
        partial_save.setEnabled(partial_allowed)

    def _set_busy(value: bool) -> None:
        activation = active["dispatching"]
        for widget in (
            search, status_filter, search_button, table, previous_page, next_page,
            add_folder, refresh, revision_combo, location_combo, tooth_combo,
            branch_combo, checkpoint_table, verify, full_load, partial_load, partial_save,
        ):
            widget.setEnabled(not value)
        clear.setEnabled(not activation)
        cancel.setEnabled(value and active["cancel"] is not None)
        if not value:
            previous_page.setEnabled(session._case_library_page > 0)
            next_page.setEnabled(
                (session._case_library_page + 1) * page_size < session._case_library_total
            )
            _update_actions()

    def _status_cell(text: str):
        wrapper = qt.QWidget(table)
        cell_layout = qt.QHBoxLayout(wrapper)
        cell_layout.setContentsMargins(3, 0, 3, 0)
        text_label = qt.QLabel(str(text or "Unknown"), wrapper)
        glyph, tone = _status_group(text)
        badge = qt.QLabel(glyph, wrapper)
        colors = {
            "green": ("#26734D", "#FFFFFF", "#BFE7CF", "#14452D"),
            "amber": ("#B56A00", "#FFFFFF", "#FFE2A8", "#633900"),
            "red": ("#A52A2A", "#FFFFFF", "#F4C4C4", "#6E1717"),
            "blue": ("#246B9E", "#FFFFFF", "#C7E4F7", "#16496E"),
            "grey": ("#68737C", "#FFFFFF", "#DDE2E6", "#3B4349"),
        }
        dark = str(qt.QSettings().value("DENTOBOT/ApplicationShell/Theme", "light")).lower() == "dark"
        dark_bg, dark_fg, light_bg, light_fg = colors[tone]
        background, foreground = (dark_bg, dark_fg) if dark else (light_bg, light_fg)
        badge.setStyleSheet(
            f"QLabel {{ background-color: {background}; color: {foreground}; "
            "border-radius: 9px; padding: 1px 6px; font-weight: 700; }"
        )
        cell_layout.addWidget(text_label)
        cell_layout.addWidget(badge)
        cell_layout.addStretch(1)
        return wrapper

    def _set_technical_text(summary=None, revision=None, location=None, inventory=None):
        values = []
        if summary:
            values.extend((
                f"Case key: {summary.get('case_key', '')}",
                f"Label: {summary.get('label', '')}",
                f"Saved: {summary.get('saved_at_utc', '')}",
            ))
        if revision:
            values.extend((
                f"Package ID: {revision.get('package_id', '')}",
                f"Package metadata: {revision.get('metadata', {})}",
            ))
        if location:
            values.extend((
                f"Path: {location.get('path', '')}",
                f"Location status: {location.get('status', '')}",
                f"Diagnostic: {location.get('error') or ''}",
            ))
        if inventory:
            values.extend((
                f"SHA-256: {inventory.package_sha256}",
                f"Integrity checked (UTC): {inventory.checked_at_utc}",
                f"Ownership complete: {inventory.ownership_complete}",
                f"Unknown ownership: {inventory.unknown_ownership}",
                f"Live freshness: {inventory.live_freshness}",
            ))
        session._case_library_technical_text = "\n".join(values)
        technical_text.setPlainText(session._case_library_technical_text)

    def _target_labels(metadata: dict, inventory: CaseInventory | None) -> dict[str, str]:
        labels = {}
        for item in metadata.get("targetToothAssociations", ()):
            if isinstance(item, dict) and isinstance(item.get("targetId"), str) and item.get("targetId"):
                fdi = item.get("fdi")
                labels[item["targetId"]] = ("FDI" + str(fdi).upper().removeprefix("FDI")) if fdi else "Unknown tooth"
        if inventory:
            for target_id in inventory.target_ids:
                labels.setdefault(target_id, "Tooth without FDI label")
        return labels

    def _branches_for(target_id: str, metadata: dict, inventory: CaseInventory | None) -> list[dict]:
        if inventory:
            return [
                {
                    "id": item.id,
                    "target_id": item.target_id,
                    "trajectory_ids": list(item.trajectory_ids),
                    "pairing_intent": item.pairing_intent,
                    "state": item.state,
                }
                for item in inventory.branches if item.target_id == target_id
            ]
        return [
            item for item in metadata.get("branchPreview", ())
            if isinstance(item, dict) and item.get("target_id") == target_id
        ]

    def _branch_label(branch: dict) -> str:
        ids = branch.get("trajectory_ids", ())
        count = len(ids) if isinstance(ids, (list, tuple)) else 0
        intent = str(branch.get("pairing_intent") or "")
        kind = "Paired" if intent.casefold() in {"paired", "explicitpair", "pair"} or count > 1 else (
            "Single" if intent.casefold() == "single" or count == 1 else "Preparation"
        )
        state = str(branch.get("state") or "")
        trajectory_text = f"{count} trajectory" if count == 1 else f"{count} trajectories"
        suffix = f" · {state}" if state else ""
        return f"{kind} · {trajectory_text}{suffix}"

    def _checkpoint_rows_for(target_id: str, branch_id: str, revision: dict, location: dict):
        metadata = revision.get("metadata") or {}
        inventory = revision.get("inventory")
        if isinstance(inventory, dict):
            inventory = CaseInventory.from_dict(inventory)
        verified = isinstance(inventory, CaseInventory)
        preview = metadata.get("checkpointPreview", ())
        location_status = str(location.get("status") or "Unknown")
        valid_location = location_status in {"Valid", "Checked"}
        rows = []
        for checkpoint in CHECKPOINTS:
            if verified:
                saved = _checkpoint_state(inventory, target_id, branch_id, checkpoint.id)
                selection = select_prefix(inventory, target_id, checkpoint.id, branch_id)
                allowed = bool(
                    valid_location
                    and inventory.integrity == "Valid"
                    and inventory.ownership_complete
                    and selection.allowed
                )
                if not valid_location or inventory.integrity != "Valid":
                    reason = f"Package status: {location_status}; integrity: {inventory.integrity}."
                elif not inventory.ownership_complete:
                    reason = "; ".join(inventory.unknown_ownership) or "Artifact ownership is incomplete."
                elif not selection.allowed:
                    reason = "; ".join(selection.reasons) or "Required saved evidence is unavailable."
                else:
                    reason = ""
                if selection.latest_complete_checkpoint and not allowed:
                    reason = (reason + " " if reason else "") + (
                        f"Latest complete cutoff: {selection.latest_complete_checkpoint}."
                    )
                cutoff = "Available" if allowed else "Blocked"
            else:
                saved = _preview_saved_state(list(preview), checkpoint.id, target_id, branch_id)
                allowed = False
                cutoff = "Requires verification"
                reason = "Verify the selected package before using this checkpoint as a cutoff."
                selection = None
            rows.append({
                "kind": "checkpoint",
                "checkpoint_id": checkpoint.id,
                "text": checkpoint.label,
                "saved_state": saved,
                "cutoff": cutoff,
                "partial_enabled": allowed,
                "path": location.get("path", ""),
                "package_id": revision.get("package_id", ""),
                "target_id": target_id,
                "branch_id": branch_id,
                "reason": reason,
                "included_ids": selection.included_ids if verified and allowed else (),
            })
        return rows

    def _render_checkpoint_table(rows: list[dict]):
        session._case_library_rows.clear()
        checkpoint_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            session._case_library_rows[index] = row
            for column, value in enumerate((
                row["text"], row["saved_state"], row["cutoff"], row["reason"],
            )):
                item = qt.QTableWidgetItem(str(value))
                if column == 3 and row["reason"]:
                    item.setToolTip(row["reason"])
                checkpoint_table.setItem(index, column, item)

    def _selected_target_id():
        return tooth_combo.itemData(tooth_combo.currentIndex)

    def _render_scope():
        revision = _selected_revision()
        location = _selected_location(revision)
        if not revision or not location:
            _render_checkpoint_table([])
            preparation.setText("Preparation: Unknown")
            return
        metadata = revision.get("metadata") or {}
        inventory = revision.get("inventory")
        if isinstance(inventory, dict):
            inventory = CaseInventory.from_dict(inventory)
        if not isinstance(inventory, CaseInventory):
            inventory = None
        target_id = _selected_target_id() or ""
        branches = _branches_for(target_id, metadata, inventory)
        prior_branch = branch_combo.itemData(branch_combo.currentIndex) or ""
        branch_combo.blockSignals(True)
        branch_combo.clear()
        branch_combo.addItem("Before a prepared branch", "")
        for branch in branches:
            branch_combo.addItem(_branch_label(branch), branch.get("id", ""))
        ids = [branch.get("id", "") for branch in branches]
        branch_combo.setCurrentIndex(ids.index(prior_branch) + 1 if prior_branch in ids else 0)
        branch_combo.blockSignals(False)
        branch_id = branch_combo.itemData(branch_combo.currentIndex) or ""
        selected_branch = next((item for item in branches if item.get("id") == branch_id), None)
        preparation.setText(
            "Preparation: " + (
                _branch_label(selected_branch) if selected_branch else "No prepared branch selected"
            )
        )
        rows = _checkpoint_rows_for(target_id, branch_id, revision, location) if target_id else []
        _render_checkpoint_table(rows)
        readiness.setText(
            "Live readiness: Unverified. Saved checkpoint state and cutoff eligibility are separate."
            if inventory
            else "Saved checkpoint preview is metadata-only. Cutoffs require package verification; live readiness is Unverified."
        )
        _set_technical_text(session._case_library_selected_summary, revision, location, inventory)
        _update_actions()

    def _fill_teeth(revision: dict | None):
        metadata = revision.get("metadata", {}) if revision else {}
        inventory = revision.get("inventory") if revision else None
        if isinstance(inventory, dict):
            inventory = CaseInventory.from_dict(inventory)
        labels = _target_labels(
            metadata, inventory if isinstance(inventory, CaseInventory) else None,
        )
        tooth_combo.blockSignals(True)
        tooth_combo.clear()
        for target_id, label in sorted(labels.items(), key=lambda pair: pair[1]):
            tooth_combo.addItem(label, target_id)
        tooth_combo.blockSignals(False)

    def _render_location_choices(preferred_path: str = ""):
        revision = _selected_revision()
        locations = list(revision.get("locations", ())) if revision else []
        locations.sort(key=lambda item: (
            0 if item.get("path") == preferred_path else 1,
            0 if item.get("status") in {"Valid", "Checked"} else 1,
            str(item.get("path", "")),
        ))
        location_combo.blockSignals(True)
        location_combo.clear()
        for index, item in enumerate(locations, start=1):
            location_combo.addItem(
                f"Copy {index} · {item.get('status', 'Unknown')}",
                item.get("path", ""),
            )
        location_combo.blockSignals(False)
        _render_scope()

    def _render_revision_choices(details: dict):
        revisions = list(details.get("revisions", ()))
        revisions.sort(key=lambda item: str(item.get("saved_at_utc") or ""), reverse=True)
        revision_combo.blockSignals(True)
        revision_combo.clear()
        for index, revision in enumerate(revisions):
            marker = ("Latest" if index == 0 else "Earlier") if revision.get("saved_at_utc") else "Date unknown"
            revision_combo.addItem(
                f"{marker} · {_friendly_date(revision.get('saved_at_utc'))}",
                revision.get("package_id", ""),
            )
        revision_combo.blockSignals(False)
        _fill_teeth(_selected_revision())
        _render_location_choices(
            session._case_library_selected_summary.get("path", "")
            if session._case_library_selected_summary else ""
        )

    def _render_details(details: dict | None):
        session._case_library_details = details
        session._details = details
        summary = session._case_library_selected_summary
        if not summary or not details:
            details_title.setText("Select a saved case to see its preparation and checkpoints.")
            revision_combo.clear()
            location_combo.clear()
            tooth_combo.clear()
            branch_combo.clear()
            preparation.setText("Preparation: Unknown")
            readiness.setText("Live readiness: Unverified.")
            _render_checkpoint_table([])
            _set_technical_text(summary)
            _update_actions()
            return
        details_title.setText(
            f"{summary.get('label') or 'Saved case'} · saved {_friendly_date(summary.get('saved_at_utc'))}"
        )
        _render_revision_choices(details)

    def _render_page(result: dict):
        summaries = list(result.get("items", ()))[:page_size]
        session._case_library_summaries = summaries
        session._rows = summaries
        session._case_library_total = int(result.get("total", len(summaries)))
        table.setRowCount(len(summaries))
        for index, summary in enumerate(summaries):
            teeth = summary.get("teeth", ())
            if isinstance(teeth, (list, tuple)):
                teeth_text = ", ".join(str(item) for item in teeth)
            else:
                teeth_text = str(teeth or "Unknown")
            values = (
                str(summary.get("label") or "Saved case"),
                teeth_text or "—",
                _friendly_date(summary.get("saved_at_utc", "")),
            )
            for column, value in enumerate(values):
                table.setItem(index, column, qt.QTableWidgetItem(value))
            table.setCellWidget(index, 3, _status_cell(str(summary.get("package_status") or "Unknown")))
            table.setCellWidget(index, 4, _status_cell(str(summary.get("workflow_status") or "Unknown")))
        start = session._case_library_page * page_size
        end = min(start + len(summaries), session._case_library_total)
        page_label.setText(
            f"Cases {start + 1 if summaries else 0}–{end} of {session._case_library_total}"
        )
        session._case_library_selected_summary = None
        session._case_library_selected_identity = None
        _render_details(None)
        if summaries:
            table.setCurrentCell(0, 0)
            _select_summary(summaries[0])
        else:
            progress_status.setText("No indexed cases. Add a folder or refresh the library.")

    def _select_summary(summary: dict):
        if (
            session._case_library_selected_summary is summary
            and (session._case_library_details is not None
                 or session._case_library_pending_details is summary
                 or active["kind"] == "details")
        ):
            return
        session._case_library_selected_summary = summary
        if active["future"] is not None:
            session._case_library_generation += 1
            if active["kind"] == "details":
                active["cancel"].set()
                active["future"].cancel()
            session._case_library_pending_details = summary
            return
        session._case_library_generation += 1
        generation = session._case_library_generation
        case_key = summary.get("case_key")
        session._case_library_selected_identity = (
            case_key, summary.get("package_id"), summary.get("path")
        )
        _render_details(None)
        if not case_key:
            return
        _start_job(
            "details",
            lambda _cancelled, _progress: with_catalog(
                lambda catalog: catalog.get_case_details(case_key)
            ),
            {"case_key": case_key, "generation": generation},
        )

    def _table_selection_changed(*_args):
        summary = _selected_summary()
        if summary:
            _select_summary(summary)

    def _begin_page(*_args, page: int | None = None):
        session._case_library_page = max(0, page) if page is not None else 0
        query = str(search.text or "").strip()
        status_value = "" if status_filter.currentText == "All statuses" else str(status_filter.currentText)
        offset = session._case_library_page * page_size
        generation = session._case_library_generation + 1
        session._case_library_generation = generation

        def worker(_cancelled, _progress):
            return with_catalog(lambda catalog: catalog.list_case_summaries(
                query=query, status=status_value, limit=page_size, offset=offset,
            ))

        _start_job("list", worker, {"generation": generation})

    def _refresh_scan(roots=None):
        query = str(search.text or "").strip()
        status_value = "" if status_filter.currentText == "All statuses" else str(status_filter.currentText)
        offset = session._case_library_page * page_size
        generation = session._case_library_generation + 1
        session._case_library_generation = generation

        def worker(cancelled, report):
            def scan(catalog):
                catalog.scan(
                    roots=roots, validation="metadata", progress=report, cancelled=cancelled,
                )
                return catalog.list_case_summaries(
                    query=query, status=status_value, limit=page_size, offset=offset,
                )
            return with_catalog(scan)

        _start_job("scan", worker, {"generation": generation})

    def _verify_selected():
        identity = _selection_identity()
        location = _selected_location()
        summary = session._case_library_selected_summary
        if not identity or not location or not summary:
            return
        path, case_key = location.get("path"), summary.get("case_key")
        generation = session._case_library_generation

        def worker(cancelled, _progress):
            from dentobot_case.inspection import inventory_from_inspection
            from DENTOCaseBundle import prepare_case_bundle, sha256_file
            with prepare_case_bundle(path, cancelled=cancelled) as prepared:
                inventory = inventory_from_inspection(
                    prepared.path, prepared.inspection, sha256_file(prepared.path))
                prepared.assert_source_unchanged()
                if cancelled():
                    raise RuntimeError("Package verification cancelled.")
                return with_catalog(lambda catalog: (
                    catalog.record_verified(inventory),
                    catalog.get_case_details(inventory.case_id),
                )[1])

        _start_job("verify", worker, {"generation": generation, "identity": identity})

    def _can_full_load(summary, revision, location):
        if not summary or not revision or not location:
            return False
        blocked = {"invalid", "conflict", "missing", "blocked", "error"}
        statuses = {
            str(summary.get("package_status") or "Unknown").casefold(),
            str(location.get("status") or "Unknown").casefold(),
        }
        return bool(location.get("path")) and not statuses.intersection(blocked)

    def _full_load(*_args):
        summary = session._case_library_selected_summary
        revision = _selected_revision()
        location = _selected_location(revision)
        identity = _selection_identity()
        if not _can_full_load(summary, revision, location) or not identity:
            return
        answer = qt.QMessageBox.question(
            dialog,
            "Replace current scene?",
            f"Load {summary.get('label') or 'saved case'} from the selected revision?\n\n"
            "The current scene will be replaced.",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if answer != qt.QMessageBox.Yes:
            return
        path = location["path"]
        case_key = summary["case_key"]
        generation = session._case_library_generation

        def worker(cancelled, _progress):
            from dentobot_case.inspection import inventory_from_inspection
            from DENTOCaseBundle import prepare_case_bundle, sha256_file

            prepared = prepare_case_bundle(path, cancelled=cancelled)
            try:
                inventory = inventory_from_inspection(
                    prepared.path, prepared.inspection, sha256_file(prepared.path),
                )
                prepared.assert_source_unchanged()
                if cancelled():
                    raise RuntimeError("Case preparation cancelled.")
                with_catalog(lambda catalog: catalog.record_verified(inventory))
                return prepared
            except BaseException:
                prepared.close()
                raise

        _start_job("full", worker, {
            "generation": generation, "identity": identity, "case_key": case_key,
        })

    def _selected_prefix():
        row = _selected_checkpoint()
        return row if row and row.get("partial_enabled") else None

    def _run_partial(kind: str, destination: str = ""):
        row = _selected_prefix()
        identity = _selection_identity()
        summary = session._case_library_selected_summary
        if not row or not identity or not summary:
            return
        path = row["path"]
        target_id = row["target_id"]
        checkpoint_id = row["checkpoint_id"]
        branch_id = row["branch_id"]
        case_key = summary["case_key"]
        generation = session._case_library_generation

        def worker(cancelled, _progress):
            from dentobot_case.inspection import inspect_package

            inventory = inspect_package(path)
            if cancelled():
                raise RuntimeError("Package verification cancelled.")
            selection = select_prefix(inventory, target_id, checkpoint_id, branch_id)
            if cancelled():
                raise RuntimeError("Package verification cancelled.")
            details = with_catalog(lambda catalog: (
                catalog.record_verified(inventory),
                catalog.get_case_details(inventory.case_id),
            )[1])
            return {"selection": selection, "path": inventory.path, "details": details}

        _start_job("partial-load" if kind == "load" else "partial-save", worker, {
            "generation": generation, "identity": identity, "target_id": target_id,
            "checkpoint_id": checkpoint_id, "branch_id": branch_id, "destination": destination,
        })

    def _partial_load(*_args):
        row = _selected_prefix()
        if not row:
            return
        answer = qt.QMessageBox.question(
            dialog,
            "Replace current scene with selected prefix?",
            f"Load the saved case through {row['text']} for the selected tooth?\n\n"
            "The current scene will be replaced by an independent partial case.",
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.No,
        )
        if answer == qt.QMessageBox.Yes:
            _run_partial("load")

    def _partial_save(*_args):
        row = _selected_prefix()
        if not row:
            return
        path = row["path"]
        destination = qt.QFileDialog.getSaveFileName(
            dialog, "Save independent partial case",
            str(Path(path).with_name(Path(path).stem + "-partial.dentocase")),
            "DENTOBOT case package (*.dentocase)",
        )
        if isinstance(destination, tuple):
            destination = destination[0]
        if not destination:
            return
        if os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(destination)):
            progress_status.setText("Choose a destination distinct from the source package.")
            return
        _run_partial("save", destination)

    def _start_clear():
        generation = session._case_library_generation
        session._case_library_page = 0

        def worker(cancelled, _progress):
            if cancelled():
                return {"items": [], "total": 0}
            with_catalog(lambda catalog: catalog.clear())
            return {"items": [], "total": 0}

        _start_job("clear", worker, {"generation": generation})

    def _clear_catalog(*_args):
        if active["dispatching"]:
            return
        answer = qt.QMessageBox.question(
            dialog, "Clear case library?",
            "Forget all indexed cases and remembered scan folders?\n\n"
            "Source .dentocase packages and the active scene will be preserved.",
            qt.QMessageBox.Yes | qt.QMessageBox.No, qt.QMessageBox.No,
        )
        if answer != qt.QMessageBox.Yes:
            return
        session._case_library_generation += 1
        session._case_library_selected_summary = None
        session._case_library_selected_identity = None
        if active["future"] is not None:
            active["cancel"].set()
            session._case_library_pending_clear = True
            active["future"].cancel()
            progress_status.setText("Waiting for the current catalog write to stop before clearing…")
            return
        _start_clear()

    def _cancel_job(*_args):
        if active["cancel"] is None or active["future"] is None:
            return
        active["cancel"].set()
        session._case_library_generation += 1
        progress_status.setText("Cancelling…")
        cancel.setEnabled(False)

    def _start_job(kind: str, worker: Callable, context=None):
        if active["future"] is not None or session._case_library_closed:
            return
        cancel_event = threading.Event()
        progress_state = {"snapshot": {}}

        def report(snapshot):
            if isinstance(snapshot, dict):
                progress_state["snapshot"] = dict(snapshot)

        context = dict(context or {})
        context.setdefault("generation", session._case_library_generation)
        active.update(
            future=executor.submit(worker, cancel_event.is_set, report),
            kind=kind, context=context, cancel=cancel_event,
            progress=progress_state, dispatching=False,
        )
        progress_bar.setRange(0, 0)
        progress_status.setText({
            "list": "Reading case summaries…",
            "details": "Reading saved revision details…",
            "scan": "Scanning selected locations…",
            "verify": "Verifying the selected package…",
            "full": "Preparing the selected case…",
            "partial-load": "Verifying the selected prefix…",
            "partial-save": "Verifying the selected prefix…",
            "clear": "Clearing the local case catalog…",
        }.get(kind, "Working…"))
        _set_busy(True)

    def _close_result(result):
        close = getattr(result, "close", None)
        if callable(close):
            close()

    def _finish_job():
        if active["dispatching"] or session._case_library_closed:
            return
        future = active["future"]
        if future is None:
            return
        snapshot = active["progress"]["snapshot"] if active["progress"] else {}
        if snapshot:
            total = snapshot.get("total")
            done = snapshot.get("processed", snapshot.get("done"))
            if isinstance(total, int) and total > 0 and isinstance(done, int):
                progress_bar.setRange(0, total)
                progress_bar.setValue(min(total, max(0, done)))
            progress_status.setText(str(snapshot.get("message") or progress_status.text))
        if not future.done():
            return
        kind, context = active["kind"], active["context"]
        valid = context.get("generation") == session._case_library_generation
        if context.get("identity") is not None:
            valid = valid and context["identity"] == _selection_identity()
        active["dispatching"] = True
        result = None
        try:
            result = future.result()
            if session._case_library_closed or not valid:
                _close_result(result)
            elif kind in {"list", "scan", "clear"}:
                session._case_library_pending_clear = False
                _render_page(result)
                progress_status.setText(
                    f"Showing {len(session._case_library_summaries)} of {session._case_library_total} cases."
                )
            elif kind == "details":
                if context.get("case_key") == (
                    session._case_library_selected_summary or {}
                ).get("case_key"):
                    _render_details(result)
                    progress_status.setText("Saved case details loaded.")
            elif kind == "verify":
                session._case_library_selected_summary["case_key"] = result["case_key"]
                session._case_library_selected_summary["package_status"] = "Checked"
                selected_row = table.currentRow
                selected_row = selected_row() if callable(selected_row) else selected_row
                if selected_row >= 0:
                    table.setCellWidget(selected_row, 3, _status_cell("Checked"))
                _render_details(result)
                progress_status.setText("Package verified; saved cutoffs are ready for review.")
            elif kind == "full":
                clear.setEnabled(False)
                cancel.setEnabled(False)
                result.assert_source_unchanged()
                try:
                    on_full_load(result)
                    progress_status.setText("Full case load completed; live readiness remains Unverified.")
                finally:
                    result.close()
            elif kind in {"partial-load", "partial-save"}:
                session._case_library_selected_summary["case_key"] = result["details"]["case_key"]
                _render_details(result["details"])
                selection = result["selection"]
                if not selection.allowed:
                    progress_status.setText("Partial action blocked: " + "; ".join(selection.reasons))
                elif kind == "partial-load":
                    clear.setEnabled(False)
                    cancel.setEnabled(False)
                    on_partial_load(
                        result["path"], context["target_id"], context["checkpoint_id"],
                        context["branch_id"],
                    )
                    progress_status.setText("Independent partial case loaded; save it as a new package.")
                else:
                    clear.setEnabled(False)
                    cancel.setEnabled(False)
                    on_partial_save(
                        result["path"], context["target_id"], context["checkpoint_id"],
                        context["branch_id"], context["destination"],
                    )
                    progress_status.setText("Independent partial case saved; source remains unchanged.")
        except Exception as exc:
            logging.exception("DentoCase library %s failed", kind)
            if not session._case_library_closed:
                progress_status.setText(
                    "Cancelled." if active["cancel"] and active["cancel"].is_set()
                    else "Case library action failed. See Technical details."
                )
                session._case_library_technical_text += f"\nAction failure ({kind}): {exc}"
                technical_text.setPlainText(session._case_library_technical_text)
            _close_result(result)
        finally:
            was_pending_clear = session._case_library_pending_clear
            pending_details = session._case_library_pending_details
            session._case_library_pending_details = None
            active.update(
                future=None, kind="", context=None, cancel=None, progress=None,
                dispatching=False,
            )
            progress_bar.setRange(0, 1)
            progress_bar.setValue(0)
            if not session._case_library_closed:
                if was_pending_clear:
                    session._case_library_pending_clear = False
                    _start_clear()
                else:
                    _set_busy(False)
                    if pending_details:
                        _select_summary(pending_details)

    def _close_worker(*_args):
        if session._case_library_closed:
            return
        session._case_library_closed = True
        if active["cancel"]:
            active["cancel"].set()
        timer.stop()
        debounce.stop()
        future = active["future"]
        if future is not None and not active["dispatching"]:
            if future.done():
                try:
                    _close_result(future.result())
                except Exception:
                    pass
            else:
                def close_completed(completed):
                    if not completed.cancelled() and completed.exception() is None:
                        _close_result(completed.result())
                future.add_done_callback(close_completed)
        executor.shutdown(wait=False, cancel_futures=active["kind"] != "clear")

    def _change_revision(*_args):
        if active["future"]:
            return
        revision = _selected_revision()
        _fill_teeth(revision)
        _render_location_choices(
            session._case_library_selected_summary.get("path", "")
            if session._case_library_selected_summary else ""
        )

    def _change_scope(*_args):
        if not active["future"]:
            _render_scope()

    def _go_previous(*_args):
        if session._case_library_page > 0:
            _begin_page(page=session._case_library_page - 1)

    def _go_next(*_args):
        if (session._case_library_page + 1) * page_size < session._case_library_total:
            _begin_page(page=session._case_library_page + 1)

    def _add_folder(*_args):
        folder = qt.QFileDialog.getExistingDirectory(dialog, "Add a case folder", "")
        if isinstance(folder, tuple):
            folder = folder[0]
        if folder:
            _refresh_scan([folder])

    def _copy_technical(*_args):
        qt.QApplication.clipboard().setText(session._case_library_technical_text)
        progress_status.setText("Technical details copied to the clipboard.")

    debounce = qt.QTimer(dialog)
    debounce.setSingleShot(True)
    debounce.setInterval(150)
    def schedule_search(*_args):
        debounce.start()
    debounce.timeout.connect(_begin_page)
    search.textChanged.connect(schedule_search)
    status_filter.currentIndexChanged.connect(schedule_search)
    search_button.clicked.connect(_begin_page)
    search.returnPressed.connect(_begin_page)
    previous_page.clicked.connect(_go_previous)
    next_page.clicked.connect(_go_next)
    add_folder.clicked.connect(_add_folder)
    refresh.clicked.connect(lambda *_args: _refresh_scan())
    clear.clicked.connect(_clear_catalog)
    verify.clicked.connect(_verify_selected)
    full_load.clicked.connect(_full_load)
    partial_load.clicked.connect(_partial_load)
    partial_save.clicked.connect(_partial_save)
    cancel.clicked.connect(_cancel_job)
    copy_button.clicked.connect(_copy_technical)
    revision_combo.currentIndexChanged.connect(_change_revision)
    location_combo.currentIndexChanged.connect(_change_scope)
    tooth_combo.currentIndexChanged.connect(_change_scope)
    branch_combo.currentIndexChanged.connect(_change_scope)
    table.itemSelectionChanged.connect(_table_selection_changed)
    checkpoint_table.itemSelectionChanged.connect(lambda *_args: _update_actions())
    timer.timeout.connect(_finish_job)
    dialog.finished.connect(_close_worker)
    dialog.destroyed.connect(_close_worker)
    timer.start()
    _begin_page()
    dialog.show()
    return session
