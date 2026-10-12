#!/usr/bin/env python3
"""Read-only local project progress dashboard server.

The public data helpers are intentionally small so focused tests can exercise
the Markdown projection without starting an HTTP listener:

* ``parse_backlog(text, project_goal='')`` parses task rows and dated notes.
* ``build_snapshot(overlay)`` reads the current allowlisted documents and
  operational focus receipts for one fresh API snapshot.

No request can write files or choose an arbitrary filesystem path.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlsplit

if __package__:
    from . import item_explanation, work_history
else:  # Direct `python server.py` entry point.
    import item_explanation
    import work_history


DEFAULT_OVERLAY = Path("/home/tarun/dentobot")
DEFAULT_PORT = 8766
DEFAULT_HOST = "127.0.0.1"
TAILSCALE_IPV4_NETWORK = ipaddress.ip_network("100.64.0.0/10")
STALE_AFTER_SECONDS = 15 * 60
SUPPORTING_ATTENTION_SECONDS = 30 * 60
MAX_SESSION_BYTES = 64 * 1024
MAX_EVENT_TAIL_BYTES = 1024 * 1024
MAX_EVENT_LINES_PER_FILE = 500
MAX_ACTIVITY_EVENTS = 100
MAX_CONTEXT_PER_TASK = 5
MAX_CONTEXT_CHARS = 1200
MAX_RANGE_EXPANSION = 100
MAX_EXPLANATION_BODY_BYTES = 4096

CORE_SOURCE_FILES: tuple[str, ...] = (
    "backlog.md",
    "TASKS.md",
    "DEVELOPMENT_PLAN.md",
    "DECISIONS.md",
    "PROJECT_CONTEXT.md",
)

SOURCE_RELATIVE_PATHS: dict[str, str] = {
    "backlog.md": "backlog.md",
    "TASKS.md": "TASKS.md",
    "DEVELOPMENT_PLAN.md": "DEVELOPMENT_PLAN.md",
    "DECISIONS.md": "DECISIONS.md",
    "PROJECT_CONTEXT.md": "PROJECT_CONTEXT.md",
}

MILESTONE_ORDER: tuple[str, ...] = (
    "imaging",
    "planning",
    "templates",
    "simulation",
    "reliability",
    "case-platform",
    "physical",
    "platform",
    "other",
)

MILESTONE_TITLES: dict[str, str] = {
    "imaging": "Imaging",
    "planning": "Planning",
    "templates": "Templates",
    "simulation": "Simulation",
    "reliability": "Reliability",
    "case-platform": "Case platform",
    "physical": "Physical system",
    "platform": "Platform and verification",
    "other": "Other backlog items",
}

TASK_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?:\.{1,2}[A-Z0-9]+)*$")
TASK_TOKEN_RE = re.compile(r"(?<![A-Z0-9])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?:\.{1,2}[A-Z0-9]+)*(?![A-Z0-9])")
SESSION_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
LOGBOOK_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _utc_iso(value: datetime | None = None) -> str:
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mtime_iso(path: Path) -> str | None:
    try:
        return _utc_iso(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
    except OSError:
        return None


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _clean_text(value: Any, limit: int = 2000) -> str:
    if not isinstance(value, str):
        return ""
    return CONTROL_CHARS_RE.sub("", value).strip()[:limit]


def _source_url(filename: str, line: int = 1) -> str:
    selected_line = max(1, line)
    return "/source?" + urlencode({"file": filename, "line": str(selected_line)}) + f"#L{selected_line}"


def _split_markdown_row(line: str) -> list[str]:
    """Split one Markdown table row, honoring escaped pipe characters."""
    source = line.strip()
    if source.startswith("|"):
        source = source[1:]
    if source.endswith("|") and not source.endswith("\\|"):
        source = source[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in source:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _is_table_separator(line: str) -> bool:
    cells = _split_markdown_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _normalized_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", header.casefold()).strip()


def _header_index(headers: list[str], predicate: Any) -> int | None:
    for index, header in enumerate(headers):
        if predicate(_normalized_header(header)):
            return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


def _task_id(cell: str) -> str:
    values = _task_ids_in_cell(cell)
    return values[0] if values else ""


def _task_ids_in_cell(cell: str) -> list[str]:
    values = re.findall(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?:\.{1,2}[A-Z0-9]+)*", cell)
    return list(dict.fromkeys(value for value in values if TASK_ID_RE.fullmatch(value)))


def _priority_rank(priority: str) -> int | None:
    values = {
        int(match.group(1))
        for match in re.finditer(r"(?<![A-Za-z0-9])(?:P|Priority\s*)?([0-4])(?:\b|$)", priority, re.IGNORECASE)
    }
    return next(iter(values)) if len(values) == 1 else None


def _milestone_for(task_id: str) -> str:
    value = task_id.upper()
    if value.startswith(("S6-P2-03", "S6-U-01", "QA-", "VIEW-")):
        return "reliability"
    if value.startswith(("S3", "IMG")):
        return "imaging"
    if value.startswith(("S4", "W4")):
        return "planning"
    if value.startswith("W5"):
        return "templates"
    if value.startswith("S6"):
        return "simulation"
    if value.startswith(("DCP", "DSS", "CASE", "UI-")):
        return "case-platform"
    if value.startswith(("A-", "POC", "ROS", "DHW")):
        return "physical"
    if value.startswith(("PLAT", "VERIFY", "PROGRESS")):
        return "platform"
    return "other"


def _rows_from_tables(text: str) -> Iterable[tuple[str, int, list[str], list[str]]]:
    lines = text.splitlines()
    section = ""
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        heading = re.match(r"^(#{1,2})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            section = heading.group(2).strip()
        if stripped.startswith("|") and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            headers = _split_markdown_row(lines[index])
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = _split_markdown_row(lines[index])
                if len(row) < len(headers):
                    row.extend([""] * (len(headers) - len(row)))
                elif len(row) > len(headers):
                    row = row[: len(headers) - 1] + [" | ".join(row[len(headers) - 1 :])]
                yield section, index + 1, headers, row
                index += 1
            continue
        index += 1


def _extract_top_checkpoints(text: str) -> list[dict[str, Any]]:
    """Return source paragraphs in the backlog preamble before its first H2."""
    checkpoints: list[dict[str, Any]] = []
    lines = text.splitlines()
    block: list[str] = []
    start_line = 0

    def flush() -> None:
        nonlocal block, start_line
        if block:
            paragraph = " ".join(part.strip() for part in block if part.strip())
            if paragraph and not paragraph.startswith("# "):
                checkpoints.append(
                    {"text": paragraph, "source_line": start_line, "source_url": _source_url("backlog.md", start_line)}
                )
        block = []
        start_line = 0

    for line_number, line in enumerate(lines, start=1):
        if re.match(r"^##\s+", line.strip()):
            flush()
            break
        if re.match(r"^#\s+", line.strip()):
            # The backlog title is a heading, not part of the first
            # checkpoint paragraph. Flush any preceding text and begin
            # narrative collection on the following source line.
            flush()
            continue
        if line.strip().startswith("|") or not line.strip():
            flush()
            continue
        if not block:
            start_line = line_number
        block.append(line)
    else:
        flush()
    return checkpoints


def _extract_advisor_notes(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    active = False
    started_list = False
    owner = "S6-ADVISOR-GUI-01"
    notes: list[dict[str, Any]] = []
    current: list[str] = []
    current_line = 0

    def flush() -> None:
        nonlocal current, current_line
        if current:
            notes.append(
                {
                    "owner": owner,
                    "text": " ".join(part.strip() for part in current if part.strip()),
                    "source_line": current_line,
                    "source_url": _source_url("backlog.md", current_line),
                }
            )
        current = []
        current_line = 0

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+", stripped):
            if active:
                flush()
                break
            if "S6-ADVISOR-GUI-01" in stripped and "backlog items" in stripped.casefold():
                active = True
            continue
        if not active:
            continue
        item = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if item:
            flush()
            started_list = True
            current_line = line_number
            current = [item.group(2)]
        elif current and stripped:
            current.append(stripped)
        elif started_list and not stripped:
            flush()
    flush()
    return notes


def _build_milestones(tasks: list[dict[str, Any]], project_goal: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {milestone: [] for milestone in MILESTONE_ORDER}
    for task in tasks:
        milestone = task["milestone"]
        grouped[milestone].append(task["id"])
    return [
        {
            "id": milestone,
            "title": MILESTONE_TITLES[milestone],
            "goal": project_goal,
            "task_ids": grouped[milestone],
            "pending_count": len(grouped[milestone]),
        }
        for milestone in MILESTONE_ORDER
        if grouped[milestone] or milestone != "other"
    ]


def parse_backlog(text: str, project_goal: str = "") -> dict[str, Any]:
    """Parse backlog tables by their header labels, preserving every ID row."""
    tasks: list[dict[str, Any]] = []
    for section, line_number, headers, row in _rows_from_tables(text):
        id_index = _header_index(headers, lambda value: value == "id" or value.startswith("id aliases"))
        if id_index is None:
            id_index = _header_index(headers, lambda value: "id" in value.split())
        if id_index is None:
            continue
        task_id = _task_id(_cell(row, id_index))
        if not task_id:
            continue

        priority_index = _header_index(headers, lambda value: value == "priority" or value.startswith("source priority"))
        outcome_index = _header_index(headers, lambda value: value == "outcome" or value == "main outcome")
        deliverable_index = _header_index(headers, lambda value: value == "pending deliverable")
        state_index = _header_index(headers, lambda value: value in {"state", "status"})
        remaining_index = _header_index(
            headers,
            lambda value: value.startswith("remaining") or value == "next acceptance action",
        )
        boundary_index = _header_index(
            headers,
            lambda value: "boundary" in value
            or "dependency overlap" in value
            or value == "entry condition overlap"
            or ("dependencies" in value and ("overlap" in value or "entry condition" in value)),
        )
        priority = _cell(row, priority_index)
        id_cell = _cell(row, id_index)
        aliases = _task_ids_in_cell(id_cell)[1:]
        state = _cell(row, state_index)
        if not state:
            evidence_index = _header_index(headers, lambda value: value == "evidence summary")
            state = _cell(row, evidence_index)
        outcome = _cell(row, outcome_index) or _cell(row, deliverable_index)
        is_source_priority = priority_index is not None and _normalized_header(headers[priority_index]).startswith("source priority")
        tasks.append(
            {
                "id": task_id,
                "id_cell": id_cell,
                "aliases": aliases,
                "priority": priority,
                "priority_rank": None if is_source_priority else _priority_rank(priority),
                "section": section,
                "outcome": outcome,
                "state": state,
                "remaining": _cell(row, remaining_index),
                "boundary": _cell(row, boundary_index),
                "source_line": line_number,
                "source_url": _source_url("backlog.md", line_number),
                "milestone": _milestone_for(task_id),
            }
        )

    return {
        "tasks": tasks,
        "milestones": _build_milestones(tasks, project_goal),
        "checkpoints": _extract_top_checkpoints(text),
        "notes": _extract_advisor_notes(text),
    }


def _expand_task_id_range(task_id: str) -> list[str]:
    """Expand a bounded numeric ID group such as ``DCP-02..08``."""
    match = re.fullmatch(r"(?P<prefix>.*?)(?P<first>\d+)\.\.(?P<last>\d+)", task_id)
    if not match:
        return []
    first = int(match.group("first"))
    last = int(match.group("last"))
    if last < first or last - first + 1 > MAX_RANGE_EXPANSION:
        return []
    width = max(len(match.group("first")), len(match.group("last")))
    prefix = match.group("prefix")
    return [f"{prefix}{number:0{width}d}" for number in range(first, last + 1)]


def canonical_task_map(backlog_text: str) -> dict[str, dict[str, Any]]:
    """Map canonical IDs, aliases and range members to their canonical row.

    Every value is a copy of the row returned by ``parse_backlog`` with
    ``task_id`` naming the canonical display ID. Canonical rows always win
    collisions with a range member or alias.
    """
    parsed = parse_backlog(backlog_text)
    rows: dict[str, dict[str, Any]] = {}
    for task in parsed["tasks"]:
        canonical_id = task["id"]
        rows[canonical_id] = {**task, "task_id": canonical_id}
    for task in parsed["tasks"]:
        canonical_id = task["id"]
        row = rows[canonical_id]
        keys = [*task.get("aliases", []), *_expand_task_id_range(canonical_id)]
        keys.extend(
            expanded
            for alias in task.get("aliases", [])
            for expanded in _expand_task_id_range(alias)
        )
        for key in keys:
            if key and TASK_ID_RE.fullmatch(key):
                rows.setdefault(key, row)
    return rows


def _metadata_text(value: Any, limit: int = 1200) -> str:
    return _clean_text(value, limit)


def _metadata_id_list(value: Any, label: str, warnings: list[str]) -> list[str]:
    if not isinstance(value, list):
        warnings.append(f"Dashboard metadata {label} must be a list of task IDs.")
        return []
    selected: list[str] = []
    for raw in value:
        candidate = _metadata_text(raw, 120).upper()
        if candidate and TASK_ID_RE.fullmatch(candidate):
            if candidate not in selected:
                selected.append(candidate)
        else:
            warnings.append(f"Dashboard metadata ignored an invalid task ID in {label}.")
    return selected


def _metadata_file_allowed(filename: str) -> bool:
    return filename in CORE_SOURCE_FILES or bool(
        re.fullmatch(r"logbook/\d{4}-\d{2}-\d{2}\.md", filename)
    )


def parse_dashboard_metadata(plan_text: str) -> dict[str, Any]:
    """Read the explicit schema-1 display metadata from DEVELOPMENT_PLAN.md.

    The parsed status/evidence are display metadata only; this helper never
    derives completion from backlog row counts or narrative prose.
    """
    empty: dict[str, Any] = {
        "schema_version": None,
        "current": {},
        "milestones": [],
        "metadata_source": None,
        "metadata_present": False,
        "metadata_valid": False,
        "metadata_warnings": [],
    }
    lines = plan_text.splitlines()
    start_markers = [index for index, line in enumerate(lines) if line.strip() == "<!-- PROGRESS-DASHBOARD:START -->"]
    end_markers = [index for index, line in enumerate(lines) if line.strip() == "<!-- PROGRESS-DASHBOARD:END -->"]
    if not start_markers and not end_markers:
        empty["metadata_warnings"] = [
            "Explicit dashboard metadata is absent; legacy display grouping is in use and acceptance is unknown."
        ]
        return empty
    empty["metadata_present"] = True
    if len(start_markers) != 1 or len(end_markers) != 1 or end_markers[0] <= start_markers[0]:
        empty["metadata_warnings"] = ["Explicit dashboard metadata markers are malformed or duplicated."]
        return empty

    start_index = start_markers[0]
    end_index = end_markers[0]
    fence_start = next(
        (index for index in range(start_index + 1, end_index) if lines[index].strip().casefold() == "```json"),
        None,
    )
    if fence_start is None:
        empty["metadata_warnings"] = ["Explicit dashboard metadata has no JSON code block."]
        return empty
    fence_end = next(
        (index for index in range(fence_start + 1, end_index) if lines[index].strip() == "```"),
        None,
    )
    if fence_end is None:
        empty["metadata_warnings"] = ["Explicit dashboard metadata JSON code block is unterminated."]
        return empty

    metadata_source = {
        "file": "DEVELOPMENT_PLAN.md",
        "start_line": fence_start + 1,
        "end_line": fence_end + 1,
        "url": _source_url("DEVELOPMENT_PLAN.md", fence_start + 1),
    }
    try:
        raw = json.loads("\n".join(lines[fence_start + 1 : fence_end]))
    except json.JSONDecodeError as exc:
        empty["metadata_source"] = metadata_source
        empty["metadata_warnings"] = [f"Explicit dashboard metadata JSON is invalid at line {exc.lineno}."]
        return empty
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        empty["metadata_source"] = metadata_source
        empty["metadata_warnings"] = ["Explicit dashboard metadata must be a schema-version-1 object."]
        return empty

    warnings: list[str] = []
    current_raw = raw.get("current")
    if not isinstance(current_raw, dict):
        empty["metadata_source"] = metadata_source
        empty["metadata_warnings"] = ["Explicit dashboard metadata current selection is missing or malformed."]
        return empty
    current = {
        "title": _metadata_text(current_raw.get("title"), 300),
        "outcome": _metadata_text(current_raw.get("outcome"), 1200),
        "task_ids": _metadata_id_list(current_raw.get("task_ids", []), "current.task_ids", warnings),
        "spotlight_task_ids": _metadata_id_list(
            current_raw.get("spotlight_task_ids", []), "current.spotlight_task_ids", warnings
        ),
        "sequence_note": _metadata_text(current_raw.get("sequence_note"), 1200),
    }
    raw_milestones = raw.get("milestones")
    if not isinstance(raw_milestones, list):
        empty["metadata_source"] = metadata_source
        empty["metadata_warnings"] = ["Explicit dashboard metadata milestones must be a list."]
        return empty

    milestones: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_milestone in enumerate(raw_milestones):
        if not isinstance(raw_milestone, dict):
            warnings.append(f"Dashboard metadata milestone {index + 1} is not an object and was ignored.")
            continue
        milestone_id = _metadata_text(raw_milestone.get("id"), 80).casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", milestone_id):
            warnings.append(f"Dashboard metadata milestone {index + 1} has an invalid ID and was ignored.")
            continue
        if milestone_id in seen_ids:
            warnings.append(f"Dashboard metadata repeats milestone ID {milestone_id!r}; later copy was ignored.")
            continue
        title = _metadata_text(raw_milestone.get("title"), 300)
        goal = _metadata_text(raw_milestone.get("goal"), 1200)
        status = _metadata_text(raw_milestone.get("status"), 120)
        if not title or not status:
            warnings.append(f"Dashboard metadata milestone {milestone_id!r} needs a title and explicit status.")
            continue
        task_ids = _metadata_id_list(raw_milestone.get("task_ids", []), f"{milestone_id}.task_ids", warnings)
        raw_prefixes = raw_milestone.get("prefixes", [])
        prefixes: list[str] = []
        if not isinstance(raw_prefixes, list):
            warnings.append(f"Dashboard metadata {milestone_id}.prefixes must be a list.")
        else:
            for raw_prefix in raw_prefixes:
                prefix = _metadata_text(raw_prefix, 120).upper()
                if prefix and re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-?", prefix):
                    if prefix not in prefixes:
                        prefixes.append(prefix)
                else:
                    warnings.append(f"Dashboard metadata ignored an invalid prefix for {milestone_id}.")

        evidence: list[dict[str, Any]] = []
        raw_evidence = raw_milestone.get("evidence", [])
        if not isinstance(raw_evidence, list):
            warnings.append(f"Dashboard metadata {milestone_id}.evidence must be a list.")
        else:
            for evidence_index, raw_item in enumerate(raw_evidence):
                if not isinstance(raw_item, dict):
                    warnings.append(f"Dashboard metadata evidence {milestone_id}[{evidence_index + 1}] is malformed.")
                    continue
                filename = _metadata_text(raw_item.get("file"), 200)
                line = raw_item.get("line")
                label = _metadata_text(raw_item.get("label"), 1000)
                if not _metadata_file_allowed(filename) or not isinstance(line, int) or isinstance(line, bool) or line < 1 or not label:
                    warnings.append(f"Dashboard metadata evidence {milestone_id}[{evidence_index + 1}] has an invalid source reference.")
                    continue
                evidence.append(
                    {
                        "label": label,
                        "file": filename,
                        "line": line,
                        "url": _source_url(filename, line),
                    }
                )
        milestones.append(
            {
                "id": milestone_id,
                "title": title,
                "goal": goal,
                "status": status,
                "evidence": evidence,
                "task_ids": task_ids,
                "prefixes": prefixes,
            }
        )
        seen_ids.add(milestone_id)

    if not current["title"] or not current["outcome"] or not milestones:
        empty["metadata_source"] = metadata_source
        empty["metadata_warnings"] = [*warnings, "Explicit dashboard metadata is missing its current outcome or milestone definitions."]
        return empty
    return {
        "schema_version": 1,
        "current": current,
        "milestones": milestones,
        "metadata_source": metadata_source,
        "metadata_present": True,
        "metadata_valid": True,
        "metadata_warnings": warnings,
    }


def _empty_milestone(
    milestone_id: str,
    title: str,
    goal: str,
    status: str = "unknown",
    evidence: list[dict[str, Any]] | None = None,
    metadata_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": milestone_id,
        "title": title,
        "goal": goal,
        "status": status,
        "evidence": evidence or [],
        "task_ids": [],
        "pending_count": 0,
        "metadata_source": metadata_source,
    }


def _project_milestones(
    tasks: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
    project_goal: str,
    documents: dict[str, str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Assign backlog rows to roadmap display groups without inferring status."""
    metadata_source = metadata.get("metadata_source")
    if not metadata.get("metadata_present"):
        assignments: dict[str, str] = {}
        for task in tasks:
            assignments[task["id"]] = _milestone_for(task["id"])
        milestones = []
        grouped: dict[str, list[str]] = {milestone_id: [] for milestone_id in MILESTONE_ORDER}
        for task_id, milestone_id in assignments.items():
            grouped.setdefault(milestone_id, []).append(task_id)
        for milestone_id in MILESTONE_ORDER:
            if grouped.get(milestone_id) or milestone_id != "other":
                milestone = _empty_milestone(
                    milestone_id,
                    MILESTONE_TITLES[milestone_id],
                    project_goal,
                    status="unknown",
                )
                milestone["task_ids"] = grouped.get(milestone_id, [])
                milestone["pending_count"] = len(milestone["task_ids"])
                milestones.append(milestone)
        projected = [{**task, "milestone": assignments[task["id"]]} for task in tasks]
        return milestones, projected

    if not metadata.get("metadata_valid"):
        milestone = _empty_milestone(
            "other",
            "Unmapped work",
            "Explicit roadmap metadata is unavailable; task assignments and acceptance remain unknown.",
            metadata_source=metadata_source,
        )
        milestone["task_ids"] = [task["id"] for task in tasks]
        milestone["pending_count"] = len(tasks)
        return [milestone], [{**task, "milestone": "other"} for task in tasks]

    specs = metadata["milestones"]
    by_id: dict[str, dict[str, Any]] = {}
    for spec in specs:
        evidence: list[dict[str, Any]] = []
        for item in spec["evidence"]:
            filename = item["file"]
            source_text = documents.get(filename)
            source_lines = source_text.splitlines() if source_text is not None else []
            available = source_text is not None and item["line"] <= len(source_lines)
            evidence.append(
                {
                    **item,
                    "available": available,
                    "url": item["url"] if available else None,
                }
            )
            if not available:
                warnings.append(
                    f"Dashboard evidence source {filename} line {item['line']} for milestone {spec['id']} is unavailable."
                )
        milestone = _empty_milestone(
            spec["id"],
            spec["title"],
            spec["goal"],
            status=spec["status"],
            evidence=evidence,
            metadata_source=metadata_source,
        )
        milestone["explicit_task_ids"] = list(spec["task_ids"])
        milestone["prefixes"] = list(spec["prefixes"])
        by_id[spec["id"]] = milestone

    exact_assignments: dict[str, str] = {}
    conflicting_ids: set[str] = set()
    for spec in specs:
        for selector in spec["task_ids"]:
            matched = task_map.get(selector)
            if matched is None:
                warnings.append(
                    f"Dashboard milestone {spec['id']} names task ID {selector!r} that is not in the current backlog."
                )
                continue
            canonical_id = matched["task_id"]
            prior = exact_assignments.get(canonical_id)
            if prior is not None and prior != spec["id"]:
                conflicting_ids.add(canonical_id)
                warnings.append(
                    f"Dashboard task {canonical_id} has conflicting exact milestone assignments; it is shown as other."
                )
                continue
            exact_assignments[canonical_id] = spec["id"]

    assignments: dict[str, str] = {}
    for task in tasks:
        canonical_id = task["id"]
        if canonical_id in conflicting_ids:
            assignments[canonical_id] = "other"
            continue
        exact = exact_assignments.get(canonical_id)
        if exact is not None:
            assignments[canonical_id] = exact
            continue
        candidate_prefixes: list[tuple[int, str]] = []
        for spec in specs:
            for prefix in spec["prefixes"]:
                if canonical_id.upper().startswith(prefix.upper()):
                    candidate_prefixes.append((len(prefix), spec["id"]))
        if candidate_prefixes:
            longest = max(length for length, _ in candidate_prefixes)
            winners = list(dict.fromkeys(milestone_id for length, milestone_id in candidate_prefixes if length == longest))
            if len(winners) == 1:
                assignments[canonical_id] = winners[0]
                continue
            warnings.append(
                f"Dashboard task {canonical_id} matches conflicting longest prefixes; it is shown as other."
            )
        assignments[canonical_id] = "other"

    if "other" not in by_id:
        by_id["other"] = _empty_milestone(
            "other",
            "Unmapped work",
            "No explicit roadmap assignment is recorded for these backlog rows.",
            metadata_source=metadata_source,
        )
    projected: list[dict[str, Any]] = []
    for task in tasks:
        milestone_id = assignments[task["id"]]
        milestone = by_id[milestone_id]
        milestone["task_ids"].append(task["id"])
        milestone["pending_count"] += 1
        projected.append({**task, "milestone": milestone_id})
    ordered = list(by_id.values())
    return ordered, projected


def _linked_task_ids(text: str, task_map: dict[str, dict[str, Any]]) -> set[str]:
    linked: set[str] = set()
    for match in TASK_TOKEN_RE.finditer(text.upper()):
        token = match.group(0)
        task = task_map.get(token)
        if task is not None:
            linked.add(task["task_id"])
    return linked


def _extract_source_context(
    filename: str,
    content: str,
    updated_at: str | None,
    task_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Keep only the latest explicit ID-linked paragraph/section per source."""
    latest: dict[str, dict[str, Any]] = {}
    current_heading = ""
    current_heading_line = 0
    current_heading_ids: set[str] = set()
    block: list[str] = []
    block_start = 0
    in_fence = False

    def save(text: str, line_number: int, ids: set[str], section: str) -> None:
        if not ids or not text.strip():
            return
        full_text = text.strip()
        truncated = len(full_text) > MAX_CONTEXT_CHARS
        visible_text = full_text[:MAX_CONTEXT_CHARS].rstrip()
        if truncated:
            visible_text += " …"
        source_date = Path(filename).stem if filename.startswith("logbook/") else None
        for canonical_id in ids:
            latest[canonical_id] = {
                "file": filename,
                "source_line": max(1, line_number),
                "updated_at": updated_at,
                "source_date": source_date,
                "section": section[:300],
                "text": visible_text,
                "url": _source_url(filename, max(1, line_number)),
                "truncated": truncated,
            }

    def flush() -> None:
        nonlocal block, block_start
        if block:
            paragraph = "\n".join(block)
            body_lines: dict[str, int] = {}
            for offset, paragraph_line in enumerate(block):
                for canonical_id in _linked_task_ids(paragraph_line, task_map):
                    body_lines.setdefault(canonical_id, block_start + offset)
            ids = current_heading_ids | set(body_lines)
            excerpt = (current_heading + "\n" if current_heading else "") + paragraph
            for canonical_id in ids:
                line_number = body_lines.get(canonical_id, current_heading_line)
                save(excerpt, line_number, {canonical_id}, current_heading)
        block = []
        block_start = 0

    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"^#{1,6}\s+", stripped):
            flush()
            current_heading = stripped.lstrip("#").strip()
            current_heading_line = line_number
            current_heading_ids = _linked_task_ids(current_heading, task_map)
            if current_heading_ids:
                for canonical_id in current_heading_ids:
                    save(current_heading, current_heading_line, {canonical_id}, current_heading)
            continue
        if not stripped or stripped.startswith("|"):
            flush()
            continue
        if not block:
            block_start = line_number
        block.append(line)
    flush()
    return latest


def _attach_task_context(
    tasks: list[dict[str, Any]],
    documents: dict[str, str],
    sources: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    context_files = ["backlog.md", "TASKS.md", "DECISIONS.md", "DEVELOPMENT_PLAN.md"]
    context_files.extend(source["file"] for source in sources if source["file"].startswith("logbook/"))
    source_by_file = {source["file"]: source for source in sources}
    indexed: dict[str, list[dict[str, Any]]] = {task["id"]: [] for task in tasks}
    for filename in context_files:
        content = documents.get(filename)
        if content is None:
            continue
        per_source = _extract_source_context(
            filename,
            content,
            source_by_file.get(filename, {}).get("updated_at"),
            task_map,
        )
        for canonical_id, excerpt in per_source.items():
            if canonical_id in indexed:
                indexed[canonical_id].append(
                    {**excerpt, "sha256": source_by_file.get(filename, {}).get("sha256")}
                )
    file_order = {filename: index for index, filename in enumerate(context_files)}
    projected: list[dict[str, Any]] = []
    for task in tasks:
        excerpts = indexed.get(task["id"], [])
        excerpts.sort(
            key=lambda item: (
                item["source_date"] or "",
                file_order.get(item["file"], 0),
                item["source_line"],
            ),
            reverse=True,
        )
        truncated = len(excerpts) > MAX_CONTEXT_PER_TASK or any(item["truncated"] for item in excerpts)
        bounded = excerpts[:MAX_CONTEXT_PER_TASK]
        projected.append({**task, "context": bounded, "context_truncated": truncated})
    return projected


def _resolve_current_selection(
    metadata: dict[str, Any],
    tasks: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    selection = metadata.get("current") if metadata.get("metadata_valid") else {}
    if not isinstance(selection, dict):
        selection = {}
    tasks_by_id = {task["id"]: task for task in tasks}

    def resolve(ids: list[str], label: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for selector in ids:
            canonical = task_map.get(selector, {}).get("task_id")
            task = tasks_by_id.get(canonical or "")
            if task is None:
                warnings.append(f"Current dashboard selection {selector!r} in {label} is not a current backlog task.")
                continue
            if canonical not in seen:
                result.append(task)
                seen.add(canonical)
        return result

    raw_task_ids = list(selection.get("task_ids", []))
    raw_spotlight_ids = list(selection.get("spotlight_task_ids", []))
    resolved_tasks = resolve(raw_task_ids, "current.task_ids")
    resolved_spotlights = resolve(raw_spotlight_ids, "current.spotlight_task_ids")
    return {
        "title": _metadata_text(selection.get("title"), 300),
        "outcome": _metadata_text(selection.get("outcome"), 1200),
        "task_ids": raw_task_ids,
        "spotlight_task_ids": raw_spotlight_ids,
        "sequence_note": _metadata_text(selection.get("sequence_note"), 1200),
        "tasks": resolved_tasks,
        "spotlight_tasks": resolved_spotlights,
        "metadata_source": metadata.get("metadata_source"),
    }


def _extract_project_goal(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().casefold() == "## current poc closure contract":
            paragraph: list[str] = []
            started = False
            for following in lines[index + 1 :]:
                if not following.strip():
                    if started:
                        break
                    continue
                if following.lstrip().startswith("#"):
                    break
                paragraph.append(following.strip())
                started = True
            return " ".join(paragraph)
    return ""


def _docs_root(overlay: Path) -> Path | None:
    candidate = overlay / "docs"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_dir() or not _within(resolved, overlay):
        return None
    return resolved


def _select_logbook_source(docs_root: Path, local_today: Any = None) -> str | None:
    directory = docs_root / "logbook"
    try:
        if directory.is_symlink():
            return None
        resolved = directory.resolve(strict=True)
        if not _within(resolved, docs_root) or not resolved.is_dir():
            return None
        dates: list[tuple[datetime, str]] = []
        for path in resolved.iterdir():
            if path.is_symlink() or not path.is_file() or not LOGBOOK_NAME_RE.fullmatch(path.name):
                continue
            try:
                parsed = datetime.strptime(path.stem, "%Y-%m-%d")
            except ValueError:
                continue
            dates.append((parsed, path.name))
    except OSError:
        return None
    if not dates:
        return None
    target_date = local_today or datetime.now().astimezone().date()
    target = target_date.strftime("%Y-%m-%d") + ".md"
    if any(name == target for _, name in dates):
        return "logbook/" + target
    eligible = [(parsed, name) for parsed, name in dates if parsed.date() <= target_date]
    selected = max(eligible or dates, key=lambda item: item[0])[1]
    return "logbook/" + selected


def _read_allowlisted_document(
    docs_root: Path,
    filename: str,
    selected_logbook: str | None = None,
) -> tuple[str | None, str | None]:
    relative = SOURCE_RELATIVE_PATHS.get(filename)
    if relative is None and selected_logbook and filename == selected_logbook and LOGBOOK_NAME_RE.fullmatch(Path(filename).name):
        relative = selected_logbook
    if relative is None:
        return None, None
    candidate = docs_root / relative
    try:
        # Do not follow file or subdirectory symlinks from the allowlist.
        cursor = docs_root
        for part in Path(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return None, None
        resolved = candidate.resolve(strict=True)
        if not _within(resolved, docs_root) or not resolved.is_file():
            return None, None
        content = resolved.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return None, None
    return content, _mtime_iso(resolved)


def _safe_overlay(path: str | os.PathLike[str]) -> tuple[Path, str | None]:
    requested = Path(path).expanduser()
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        return requested.absolute(), f"Overlay directory is unavailable: {exc.strerror or 'not found'}."
    if not resolved.is_dir():
        return resolved, "Overlay path is not a directory."
    return resolved, None


def _repo_root(overlay: Path, docs_root: Path) -> Path | None:
    candidates = (
        overlay / "ros2_ws" / "src" / "DentoBot",
        docs_root.parent.parent,
        overlay,
    )
    for candidate in candidates:
        try:
            if (candidate / ".git").exists() and candidate.is_dir():
                return candidate.resolve(strict=True)
        except OSError:
            continue
    return None


_GIT_CACHE_LOCK = threading.Lock()
_GIT_CACHE: dict[str, tuple[float, dict[str, Any], str | None]] = {}


def _repo_state(repo_root: Path | None) -> tuple[dict[str, Any], str | None]:
    empty = {"branch": None, "sha": None, "dirty": None}
    if repo_root is None:
        return empty, "Git repository metadata is unavailable."
    key = str(repo_root)
    now_mono = time.monotonic()
    with _GIT_CACHE_LOCK:
        cached = _GIT_CACHE.get(key)
        if cached and cached[0] > now_mono:
            return dict(cached[1]), cached[2]
        warning: str | None = None
        state = dict(empty)
        try:
            status = subprocess.run(
                ["git", "-C", key, "status", "--porcelain=v1", "--branch", "--untracked-files=normal"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            sha_result = subprocess.run(
                ["git", "-C", key, "rev-parse", "--verify", "HEAD"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            if status.returncode == 0:
                lines = status.stdout.splitlines()
                branch_line = next((line for line in lines if line.startswith("## ")), "")
                state["branch"] = branch_line[3:].split("...", 1)[0] if branch_line else None
                state["dirty"] = any(line and not line.startswith("## ") for line in lines)
            else:
                warning = "Git status could not be read."
            if sha_result.returncode == 0:
                state["sha"] = sha_result.stdout.strip() or None
            elif warning is None:
                warning = "Git revision could not be read."
        except (OSError, subprocess.TimeoutExpired):
            warning = "Git metadata lookup timed out or failed."
        _GIT_CACHE[key] = (now_mono + 2.0, dict(state), warning)
        return state, warning


def _safe_progress_root(overlay: Path) -> tuple[Path | None, str | None]:
    data_root = overlay / "data"
    progress_root = data_root / "project-progress"
    try:
        if data_root.is_symlink() or progress_root.is_symlink():
            return None, "Operational progress data uses a symlink; no session files were read."
        resolved_data = data_root.resolve(strict=True)
        resolved_progress = progress_root.resolve(strict=True)
        if not _within(resolved_data, overlay) or not _within(resolved_progress, resolved_data):
            return None, "Operational progress data is outside the overlay; no session files were read."
        if not resolved_progress.is_dir():
            return None, "Operational progress data directory is unavailable."
        return resolved_progress, None
    except OSError:
        return None, "Operational progress data directory is unavailable."


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _receipt_fields(receipt: dict[str, Any], filename_session: str = "") -> dict[str, str]:
    role_value = receipt.get("role", receipt.get("kind", ""))
    role = _clean_text(role_value, 40)
    return {
        "session": _clean_text(receipt.get("session"), 100) or filename_session,
        "task_id": _clean_text(receipt.get("task_id"), 100),
        "milestone": _clean_text(receipt.get("milestone"), 100),
        "kind": role,
        "role": role,
        "objective": _clean_text(receipt.get("objective"), 1500),
        "acceptance": _clean_text(receipt.get("acceptance"), 1500),
        "stop_condition": _clean_text(receipt.get("stop_condition"), 1500),
        "status": _clean_text(receipt.get("status"), 100),
        "started_at": _clean_text(receipt.get("started_at"), 100),
        "updated_at": _clean_text(receipt.get("updated_at"), 100),
        "active_since": _clean_text(receipt.get("active_since"), 100),
        "status_changed_at": _clean_text(receipt.get("status_changed_at"), 100),
        "focus_changed_at": _clean_text(receipt.get("focus_changed_at"), 100),
    }


def _read_session_receipts(
    progress_root: Path,
    now: datetime,
    task_map: dict[str, dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sessions_dir = progress_root / "sessions"
    try:
        if sessions_dir.is_symlink():
            warnings.append("Operational session directory is a symlink; no session files were read.")
            return [], []
        resolved_sessions = sessions_dir.resolve(strict=True)
        if not _within(resolved_sessions, progress_root) or not resolved_sessions.is_dir():
            warnings.append("Operational session directory is unavailable; no live focus was read.")
            return [], []
    except OSError:
        warnings.append("Operational session directory is unavailable; no live focus was read.")
        return [], []

    current_focus: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    for path in sorted(resolved_sessions.iterdir(), key=lambda item: item.name.casefold()):
        if path.suffix != ".json":
            continue
        if path.is_symlink() or not SESSION_FILE_RE.fullmatch(path.stem):
            warnings.append("Skipped an unsafe operational session receipt filename.")
            continue
        try:
            if path.stat().st_size > MAX_SESSION_BYTES:
                warnings.append(f"Skipped oversized operational session receipt {path.name}.")
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            warnings.append(f"Skipped unreadable operational session receipt {path.name}.")
            continue
        if not isinstance(payload, dict):
            warnings.append(f"Skipped malformed operational session receipt {path.name}.")
            continue
        fields = _receipt_fields(payload, path.stem)
        if fields["session"] != path.stem:
            warnings.append(f"Skipped session receipt with mismatched session identity {path.name}.")
            continue
        if fields["kind"] not in {"main", "supporting"} or not fields["task_id"] or not fields["status"]:
            warnings.append(f"Skipped incomplete operational session receipt {path.name}.")
            continue

        reported_task_id = fields["task_id"]
        resolved_task = task_map.get(reported_task_id)
        started = _parse_timestamp(fields["started_at"])
        updated = _parse_timestamp(fields["updated_at"])
        active_since = _parse_timestamp(fields["active_since"])
        status_changed = _parse_timestamp(fields["status_changed_at"])
        focus_changed = _parse_timestamp(fields["focus_changed_at"])
        age_seconds: int | None = None
        wall_elapsed_seconds: int | None = None
        timestamp_order_invalid = False
        if updated is None:
            warnings.append(f"Session receipt {path.name} has a missing or invalid updated_at value.")
        elif updated > now:
            timestamp_order_invalid = True
            warnings.append(f"Session receipt {path.name} has a future updated_at value; it is marked stale.")
        if started is None:
            warnings.append(f"Session receipt {path.name} has a missing or invalid started_at value.")
        elif started > now:
            timestamp_order_invalid = True
            warnings.append(f"Session receipt {path.name} has a future started_at value; it is marked stale.")
        if started is not None and updated is not None and updated < started:
            timestamp_order_invalid = True
            warnings.append(f"Session receipt {path.name} has updated_at earlier than started_at; it is marked stale.")
        for label, transition in (("active_since", active_since), ("status_changed_at", status_changed), ("focus_changed_at", focus_changed)):
            if fields[label] and transition is None:
                warnings.append(f"Session receipt {path.name} has an invalid {label} value.")
                timestamp_order_invalid = True
            if transition is not None and transition > now:
                timestamp_order_invalid = True
                warnings.append(f"Session receipt {path.name} has a future {label} value; it is marked stale.")
            if transition is not None and updated is not None and transition > updated:
                timestamp_order_invalid = True
                warnings.append(f"Session receipt {path.name} has {label} later than updated_at; it is marked stale.")
        active_since_valid = active_since is not None and not timestamp_order_invalid
        active_bounds = [value for value in (started, status_changed, focus_changed) if value is not None]
        if active_since is not None and active_bounds and active_since < max(active_bounds):
            active_since_valid = False
            timestamp_order_invalid = True
            warnings.append(
                f"Session receipt {path.name} has active_since earlier than its latest focus transition; it is marked stale."
            )
        if updated is not None and updated <= now and not (started is not None and updated < started):
            age_seconds = max(0, int((now - updated).total_seconds()))
        if started is not None and started <= now and not (updated is not None and updated < started):
            wall_end = updated if fields["status"].casefold() == "completed" and updated is not None else now
            if wall_end >= started and wall_end <= now:
                wall_elapsed_seconds = max(0, int((wall_end - started).total_seconds()))
        stale = timestamp_order_invalid or age_seconds is None or age_seconds > STALE_AFTER_SECONDS
        if age_seconds is not None and age_seconds > STALE_AFTER_SECONDS and fields["status"].casefold() != "completed":
            warnings.append(f"Session receipt {path.name} has not been updated for more than 15 minutes; it is marked stale.")
        status = fields["status"].casefold()
        if status == "completed":
            classification = "completed"
        elif resolved_task is None:
            classification = "orphaned"
        elif stale:
            classification = "stale"
        elif status == "blocked":
            classification = "blocked"
        elif status == "awaiting-review":
            classification = "awaiting-review"
        elif status == "active":
            classification = "fresh-active"
        else:
            classification = "stale"
            warnings.append(f"Session receipt {path.name} has an unrecognized status and is shown outside current work.")

        active_elapsed_seconds: int | None = None
        if active_since is not None:
            if active_since > now or (updated is not None and active_since > updated):
                active_since_valid = False
        if classification == "fresh-active" and active_since_valid and active_since is not None:
            active_elapsed_seconds = max(0, int((now - active_since).total_seconds()))
        elif classification == "fresh-active" and not fields["active_since"]:
            warnings.append(f"Session receipt {path.name} has no active_since value; active duration is unknown.")

        canonical_id = resolved_task["task_id"] if resolved_task is not None else reported_task_id
        if resolved_task is None and status != "completed":
            warnings.append(f"Session receipt {path.name} references a task ID or alias absent from the current backlog; shown as orphaned.")
        projected = {
            **fields,
            "reported_task_id": reported_task_id,
            "task_id": canonical_id,
            "task_alias_match": canonical_id != reported_task_id,
            "milestone": resolved_task.get("milestone", fields["milestone"]) if resolved_task is not None else fields["milestone"],
            "reported_milestone": fields["milestone"],
            "classification": classification,
            "is_current": classification == "fresh-active",
            "age_seconds": age_seconds,
            "stale": stale,
            "active_elapsed_seconds": active_elapsed_seconds,
            "wall_elapsed_seconds": wall_elapsed_seconds,
        }
        if classification == "fresh-active":
            current_focus.append(projected)
            if (
                fields["kind"] == "supporting"
                and active_elapsed_seconds is not None
                and active_elapsed_seconds > SUPPORTING_ATTENTION_SECONDS
            ):
                warnings.append(
                    f"Supporting session {fields['session']} has been active for more than 30 minutes; "
                    "this is an attention flag, not proof of a retry spiral."
                )
        else:
            history.append(projected)
    current_focus.sort(key=lambda item: (item["kind"] != "main", item["age_seconds"] is None, item["age_seconds"] or 0))
    history.sort(
        key=lambda item: (
            {"blocked": 0, "awaiting-review": 1, "stale": 2, "orphaned": 3, "completed": 4}.get(item["classification"], 5),
            item["age_seconds"] is None,
            item["age_seconds"] or 0,
        )
    )
    return current_focus, history


def _event_receipt(event: dict[str, Any]) -> dict[str, Any]:
    nested = event.get("receipt")
    source = nested if isinstance(nested, dict) else event
    fields = _receipt_fields(source, _clean_text(event.get("session"), 100))
    return {key: value for key, value in fields.items() if value}


def _read_activity(
    progress_root: Path,
    task_map: dict[str, dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    sessions_dir = progress_root / "sessions"
    try:
        resolved_sessions = sessions_dir.resolve(strict=True)
        if sessions_dir.is_symlink() or not _within(resolved_sessions, progress_root) or not resolved_sessions.is_dir():
            return []
    except OSError:
        return []

    events: list[tuple[datetime, dict[str, Any]]] = []
    for path in sorted(resolved_sessions.iterdir(), key=lambda item: item.name.casefold()):
        if path.suffix != ".jsonl":
            continue
        if path.is_symlink() or not SESSION_FILE_RE.fullmatch(path.stem):
            warnings.append("Skipped an unsafe operational event-log filename.")
            continue
        try:
            with path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                start = max(0, size - MAX_EVENT_TAIL_BYTES)
                if start:
                    stream.seek(start)
                    stream.readline()  # discard a partial first JSONL record
                else:
                    stream.seek(0)
                raw = stream.read()
        except OSError:
            warnings.append(f"Could not read operational event log {path.name}.")
            continue
        if size > MAX_EVENT_TAIL_BYTES:
            warnings.append(f"Read only the latest event-log tail from {path.name}.")
        lines = raw.decode("utf-8", errors="replace").splitlines()[-MAX_EVENT_LINES_PER_FILE:]
        malformed = 0
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(event, dict):
                malformed += 1
                continue
            occurred_at = _clean_text(event.get("occurred_at"), 100)
            parsed_time = _parse_timestamp(occurred_at)
            if parsed_time is None:
                malformed += 1
                continue
            receipt = _event_receipt(event)
            reported_task_id = receipt.get("task_id", "")
            resolved_task = task_map.get(reported_task_id)
            canonical_task_id = resolved_task["task_id"] if resolved_task is not None else reported_task_id
            item = {
                "occurred_at": occurred_at,
                "action": _clean_text(event.get("action"), 80),
                "session": receipt.get("session", path.stem),
                "task_id": canonical_task_id,
                "reported_task_id": reported_task_id,
                "milestone": resolved_task.get("milestone", receipt.get("milestone", "")) if resolved_task else receipt.get("milestone", ""),
                "kind": receipt.get("kind", ""),
                "status": receipt.get("status", ""),
                "objective": receipt.get("objective", ""),
                "acceptance": receipt.get("acceptance", ""),
                "stop_condition": receipt.get("stop_condition", ""),
                "active_since": receipt.get("active_since", ""),
                "status_changed_at": receipt.get("status_changed_at", ""),
                "focus_changed_at": receipt.get("focus_changed_at", ""),
                "task_classification": "orphaned" if reported_task_id and resolved_task is None else "linked",
                "receipt": receipt,
            }
            events.append((parsed_time, item))
        if malformed:
            warnings.append(f"Ignored {malformed} malformed event record(s) in {path.name}.")
    events.sort(key=lambda pair: pair[0], reverse=True)
    return [event for _, event in events[:MAX_ACTIVITY_EVENTS]]


def build_snapshot(
    overlay: str | os.PathLike[str],
    *,
    now: datetime | None = None,
    runtime_warnings: Iterable[str] = (),
) -> dict[str, Any]:
    """Read all current allowlisted sources and build one JSON-ready snapshot."""
    generated = now or datetime.now(timezone.utc)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    generated = generated.astimezone(timezone.utc)
    warnings: list[str] = []
    overlay_root, overlay_warning = _safe_overlay(overlay)
    if overlay_warning:
        warnings.append(overlay_warning)
    docs_root = _docs_root(overlay_root)
    if docs_root is None:
        warnings.append("Allowlisted project documents are unavailable under the overlay docs directory.")

    documents: dict[str, str] = {}
    sources: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}
    if docs_root is not None:
        logbook_source = _select_logbook_source(docs_root, generated.astimezone().date())
        source_files = [*CORE_SOURCE_FILES]
        if logbook_source:
            source_files.append(logbook_source)
        else:
            warnings.append("No valid dated logbook source was found under docs/logbook.")
        for filename in source_files:
            content, updated_at = _read_allowlisted_document(docs_root, filename, logbook_source)
            if content is None:
                warnings.append(f"Allowlisted source {filename} is unavailable or unsafe.")
            else:
                documents[filename] = content
                source_hashes[filename] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            sources.append(
                {
                    "file": filename,
                    "updated_at": updated_at,
                    "sha256": source_hashes.get(filename),
                    "url": _source_url(filename),
                }
            )
    else:
        sources = [
            {"file": filename, "updated_at": None, "sha256": None, "url": _source_url(filename)}
            for filename in CORE_SOURCE_FILES
        ]

    project_goal = _extract_project_goal(documents.get("PROJECT_CONTEXT.md", ""))
    if documents.get("PROJECT_CONTEXT.md") and not project_goal:
        warnings.append("Current PoC goal could not be read from PROJECT_CONTEXT.md.")
    backlog_data = parse_backlog(documents.get("backlog.md", ""), project_goal)
    metadata = parse_dashboard_metadata(documents.get("DEVELOPMENT_PLAN.md", ""))
    if "DEVELOPMENT_PLAN.md" not in documents:
        metadata["metadata_present"] = True
        metadata["metadata_valid"] = False
        metadata["metadata_warnings"] = [
            "Explicit dashboard metadata source is unavailable; legacy milestone grouping was not applied."
        ]
    metadata_source = metadata.get("metadata_source")
    if isinstance(metadata_source, dict):
        plan_source = next((item for item in sources if item["file"] == "DEVELOPMENT_PLAN.md"), {})
        metadata_source = {
            **metadata_source,
            "updated_at": plan_source.get("updated_at"),
            "sha256": plan_source.get("sha256"),
        }
        metadata["metadata_source"] = metadata_source
    warnings.extend(metadata.get("metadata_warnings", []))

    task_map = canonical_task_map(documents.get("backlog.md", ""))
    milestones, projected_tasks = _project_milestones(
        backlog_data["tasks"],
        task_map,
        metadata,
        project_goal,
        documents,
        warnings,
    )
    projected_by_id = {task["id"]: {**task, "task_id": task["id"]} for task in projected_tasks}
    task_map = {
        key: projected_by_id.get(task["task_id"], task)
        for key, task in task_map.items()
    }
    projected_tasks = _attach_task_context(projected_tasks, documents, sources, task_map)
    projected_by_id = {task["id"]: {**task, "task_id": task["id"]} for task in projected_tasks}
    task_map = {key: projected_by_id.get(task["task_id"], task) for key, task in task_map.items()}
    current = _resolve_current_selection(metadata, projected_tasks, task_map, warnings)

    repo_root = _repo_root(overlay_root, docs_root) if docs_root is not None else None
    repo, git_warning = _repo_state(repo_root)
    if git_warning:
        warnings.append(git_warning)

    progress_root, progress_warning = _safe_progress_root(overlay_root)
    if progress_warning:
        warnings.append(progress_warning)
    if progress_root is not None:
        focus, focus_history = _read_session_receipts(progress_root, generated, task_map, warnings)
        activity = _read_activity(progress_root, task_map, warnings)
    else:
        focus = []
        focus_history = []
        activity = []
    chronology = work_history.build_work_history(
        overlay_root=overlay_root,
        docs_root=docs_root,
        documents=documents,
        backlog_rows=backlog_data["tasks"],
        source_metadata=sources,
        task_map=task_map,
        focus=focus,
        focus_history=focus_history,
        activity=activity,
        now=generated,
        url_for_file=_source_url,
    )
    history_metadata = chronology.get("work_history_sources", {})
    if isinstance(history_metadata, dict):
        history_warnings = history_metadata.get("warnings", [])
        if isinstance(history_warnings, list):
            warnings.extend(str(item) for item in history_warnings)
    warnings.extend(runtime_warnings)

    source_times = [source["updated_at"] for source in sources if source["updated_at"]]
    source_updated_at = max(source_times) if source_times else None
    # Preserve first occurrence while avoiding repeated warning noise.
    unique_warnings = list(dict.fromkeys(_clean_text(item, 500) for item in warnings if _clean_text(item, 500)))
    return {
        "generated_at": _utc_iso(generated),
        "source_updated_at": source_updated_at,
        "repo": repo,
        "tasks": projected_tasks,
        "current": current,
        "milestones": milestones,
        "focus": focus,
        "focus_history": focus_history,
        "focus_counts": {
            "total": len(focus),
            "main": sum(1 for item in focus if item["kind"] == "main"),
            "supporting": sum(1 for item in focus if item["kind"] == "supporting"),
        },
        "activity": activity,
        **chronology,
        "warnings": unique_warnings,
        "metadata_warnings": metadata.get("metadata_warnings", []),
        "sources": sources,
        "notes": backlog_data["notes"],
        "checkpoints": backlog_data["checkpoints"],
    }


class _RuntimeWarnings:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: set[str] = set()

    def add(self, message: str) -> None:
        with self._lock:
            self._items.add(message)

    def discard(self, message: str) -> None:
        with self._lock:
            self._items.discard(message)

    def snapshot(self) -> list[str]:
        with self._lock:
            return sorted(self._items)


def _send_bytes(handler: BaseHTTPRequestHandler, status: HTTPStatus, content_type: str, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler(
    overlay: Path,
    runtime_warnings: _RuntimeWarnings,
    explanation_manager: item_explanation.ExplanationManager | None = None,
) -> type[BaseHTTPRequestHandler]:
    explanations = (
        explanation_manager
        if explanation_manager is not None
        else item_explanation.ExplanationManager()
    )

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "DentobotProgress/1.0"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._serve_index()
            elif parsed.path == "/api/snapshot":
                self._serve_snapshot()
            elif parsed.path == "/api/explanations/models":
                if parsed.query:
                    self._api_error(HTTPStatus.BAD_REQUEST, "invalid_query", "This endpoint does not accept query parameters.")
                else:
                    self._send_json(HTTPStatus.OK, explanations.models())
            elif parsed.path.startswith("/api/explanations/"):
                if parsed.query:
                    self._api_error(HTTPStatus.BAD_REQUEST, "invalid_query", "This endpoint does not accept query parameters.")
                    return
                job_id = parsed.path.removeprefix("/api/explanations/")
                job = explanations.get(job_id)
                if job is None:
                    self._api_error(HTTPStatus.NOT_FOUND, "job_not_found", "Explanation job was not found.")
                else:
                    self._send_json(HTTPStatus.OK, job)
            elif parsed.path == "/source":
                self._serve_source(parsed.query)
            else:
                self._error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            if parsed.path != "/api/explanations":
                self._method_not_allowed()
                return
            if parsed.query or parsed.fragment:
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_query", "This endpoint does not accept query parameters.")
                return
            if not self._same_origin_json_request():
                self._api_error(HTTPStatus.FORBIDDEN, "same_origin_required", "Explanation requests must come from this dashboard origin.")
                return
            content_types = self.headers.get_all("Content-Type", [])
            if len(content_types) != 1:
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_content_type", "Send one application/json content type.")
                return
            content_type = content_types[0].split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_content_type", "Send an application/json request.")
                return
            if self.headers.get("Transfer-Encoding"):
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_body", "Chunked request bodies are not accepted.")
                return
            content_lengths = self.headers.get_all("Content-Length", [])
            if len(content_lengths) != 1:
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_body", "One bounded Content-Length is required.")
                return
            raw_length = content_lengths[0]
            if not raw_length.isdecimal():
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_body", "A bounded Content-Length is required.")
                return
            body_length = int(raw_length)
            if body_length > MAX_EXPLANATION_BODY_BYTES:
                self._api_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "The request body exceeds the 4 KB limit.")
                return
            if body_length == 0:
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_body", "The request body is required.")
                return
            body = self.rfile.read(body_length)
            if len(body) != body_length:
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_body", "The request body was incomplete.")
                return
            try:
                request = json.loads(body.decode("utf-8"), parse_constant=self._reject_json_constant)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_json", "The request body must be valid JSON.")
                return
            if not isinstance(request, dict) or set(request) != {"task_id", "occurred_at", "model"}:
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_request", "Provide only task_id, occurred_at, and model.")
                return
            if not all(isinstance(request.get(key), str) for key in ("task_id", "occurred_at", "model")):
                self._api_error(HTTPStatus.BAD_REQUEST, "invalid_request", "task_id, occurred_at, and model must be strings.")
                return
            try:
                snapshot = build_snapshot(overlay, runtime_warnings=runtime_warnings.snapshot())
            except Exception:
                self._api_error(HTTPStatus.SERVICE_UNAVAILABLE, "snapshot_unavailable", "The current dashboard snapshot is temporarily unavailable.")
                return
            status, response = explanations.submit(
                snapshot,
                request["task_id"],
                request["occurred_at"],
                request["model"],
            )
            self._send_json(HTTPStatus(status), response)

        def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._method_not_allowed()

        def _method_not_allowed(self) -> None:
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Read-only service")

        def _error(self, status: HTTPStatus, message: str) -> None:
            body = (message + "\n").encode("utf-8")
            _send_bytes(self, status, "text/plain; charset=utf-8", body)

        @staticmethod
        def _reject_json_constant(value: str) -> None:
            raise ValueError(f"invalid JSON constant: {value}")

        def _send_json(self, status: HTTPStatus, value: dict[str, Any]) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            _send_bytes(self, status, "application/json; charset=utf-8", body)

        def _api_error(self, status: HTTPStatus, code: str, message: str) -> None:
            self._send_json(status, {"error": {"code": code, "message": message}})

        def _same_origin_json_request(self) -> bool:
            hosts = self.headers.get_all("Host", [])
            origins = self.headers.get_all("Origin", [])
            if len(hosts) != 1 or len(origins) != 1:
                return False
            host_header = hosts[0]
            origin_header = origins[0]
            fetch_site = self.headers.get("Sec-Fetch-Site", "").casefold()
            if not host_header or not origin_header or fetch_site not in {"", "same-origin", "none"}:
                return False
            try:
                host_parts = urlsplit("//" + host_header)
                origin_parts = urlsplit(origin_header)
                host_name = host_parts.hostname
                origin_name = origin_parts.hostname
                host_port = host_parts.port
                origin_port = origin_parts.port
                bound_name = str(self.server.server_address[0])
                bound_port = int(self.server.server_address[1])
                if (
                    not host_name
                    or not origin_name
                    or host_parts.username is not None
                    or host_parts.password is not None
                    or host_parts.path
                    or host_parts.query
                    or host_parts.fragment
                    or origin_parts.scheme != "http"
                    or origin_parts.username is not None
                    or origin_parts.password is not None
                    or origin_parts.path not in {"", "/"}
                    or origin_parts.query
                    or origin_parts.fragment
                    or host_port != bound_port
                    or origin_port != bound_port
                    or host_name.casefold() != origin_name.casefold()
                ):
                    return False
                bound_ip = ipaddress.ip_address(bound_name)
                if not bound_ip.is_loopback and bound_ip not in TAILSCALE_IPV4_NETWORK:
                    return False
                try:
                    host_ip = ipaddress.ip_address(host_name)
                    origin_ip = ipaddress.ip_address(origin_name)
                except ValueError:
                    # Browsers commonly serialize a loopback dashboard as
                    # localhost. Accept that reserved name only when bound to
                    # loopback; arbitrary DNS names are never resolved here.
                    if not bound_ip.is_loopback or host_name.casefold() != "localhost":
                        return False
                else:
                    if bound_ip != host_ip or host_ip != origin_ip:
                        return False
            except (ValueError, TypeError):
                return False
            return True

        def _serve_index(self) -> None:
            index_path = Path(__file__).with_name("index.html")
            try:
                if index_path.is_symlink() or not index_path.is_file():
                    raise OSError("missing dashboard UI")
                body = index_path.read_bytes()
            except OSError:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "Dashboard UI is not available yet")
                return
            _send_bytes(self, HTTPStatus.OK, "text/html; charset=utf-8", body)

        def _serve_snapshot(self) -> None:
            snapshot = build_snapshot(overlay, runtime_warnings=runtime_warnings.snapshot())
            body = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            _send_bytes(self, HTTPStatus.OK, "application/json; charset=utf-8", body)

        def _serve_source(self, query: str) -> None:
            try:
                values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "Malformed source query")
                return
            if set(values) - {"file", "line"} or len(values.get("file", [])) != 1 or len(values.get("line", [])) > 1:
                self._error(HTTPStatus.BAD_REQUEST, "Expected one allowlisted file and an optional line number")
                return
            filename = values["file"][0]
            line_number = 1
            if values.get("line"):
                raw_line = values["line"][0]
                if not raw_line.isdecimal() or int(raw_line) < 1:
                    self._error(HTTPStatus.BAD_REQUEST, "Line number must be a positive integer")
                    return
                line_number = int(raw_line)

            if filename == work_history.T3_OBSERVATIONS_NAME or filename.startswith("work-history/"):
                source_text, source_error = work_history.read_allowlisted_source(overlay, filename)
                if source_text is None:
                    self._error(HTTPStatus.NOT_FOUND, "Source document is unavailable")
                    return
                escaped_title = html.escape(filename, quote=True)
                rendered: list[str] = []
                for number, source_line in enumerate(source_text.splitlines(), start=1):
                    escaped_line = html.escape(source_line, quote=False)
                    marker = " class=\"selected\"" if number == line_number else ""
                    rendered.append(
                        f'<span id="L{number}"{marker}><a href="#L{number}" aria-label="Line {number}">{number:5}</a> '
                        f"{escaped_line}</span>"
                    )
                document = (
                    "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
                    "content=\"width=device-width,initial-scale=1\"><title>"
                    + escaped_title
                    + "</title><style>body{margin:0;background:#111827;color:#e5e7eb;font:14px/1.55 monospace}"
                    "header{position:sticky;top:0;padding:.7rem 1rem;background:#1f2937}a{color:#93c5fd;text-decoration:none}"
                    "pre{margin:0;padding:1rem;overflow:auto}span{display:block;white-space:pre}span.selected{background:#334155}"
                    "</style></head><body><header>"
                    + escaped_title
                    + "</header><pre>"
                    + "\n".join(rendered)
                    + "</pre></body></html>"
                )
                _send_bytes(self, HTTPStatus.OK, "text/html; charset=utf-8", document.encode("utf-8"))
                return

            docs_root = _docs_root(overlay)
            if docs_root is None:
                self._error(HTTPStatus.NOT_FOUND, "Source documents are unavailable")
                return
            logbook_source = _select_logbook_source(docs_root)
            if filename not in SOURCE_RELATIVE_PATHS and filename != logbook_source:
                self._error(HTTPStatus.NOT_FOUND, "Source file is not allowlisted")
                return
            source_text, _ = _read_allowlisted_document(docs_root, filename, logbook_source)
            if source_text is None:
                self._error(HTTPStatus.NOT_FOUND, "Source document is unavailable")
                return
            escaped_title = html.escape(filename, quote=True)
            rendered: list[str] = []
            for number, source_line in enumerate(source_text.splitlines(), start=1):
                escaped_line = html.escape(source_line, quote=False)
                marker = " class=\"selected\"" if number == line_number else ""
                rendered.append(
                    f'<span id="L{number}"{marker}><a href="#L{number}" aria-label="Line {number}">{number:5}</a> '
                    f"{escaped_line}</span>"
                )
            document = (
                "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
                "content=\"width=device-width,initial-scale=1\"><title>"
                + escaped_title
                + "</title><style>body{margin:0;background:#111827;color:#e5e7eb;font:14px/1.55 monospace}"
                "header{position:sticky;top:0;padding:.7rem 1rem;background:#1f2937}a{color:#93c5fd;text-decoration:none}"
                "pre{margin:0;padding:1rem;overflow:auto}span{display:block;white-space:pre}span.selected{background:#334155}"
                "</style></head><body><header>"
                + escaped_title
                + "</header><pre>"
                + "\n".join(rendered)
                + "</pre></body></html>"
            )
            _send_bytes(self, HTTPStatus.OK, "text/html; charset=utf-8", document.encode("utf-8"))

        def log_message(self, format_string: str, *args: Any) -> None:
            # Keep standard request/error visibility without exposing source content.
            sys.stderr.write("progress-dashboard: " + (format_string % args) + "\n")

    return DashboardHandler


class _DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _validated_host(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("host must be a specific IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise argparse.ArgumentTypeError("host must be an IPv4 address")
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        raise argparse.ArgumentTypeError("host must be a specific, non-wildcard IPv4 address")
    if not address.is_loopback and address not in TAILSCALE_IPV4_NETWORK:
        raise argparse.ArgumentTypeError("additional hosts must be localhost or a specific Tailscale IPv4 address in 100.64.0.0/10")
    return str(address)


def _serve_optional_host(
    host: str,
    port: int,
    handler: type[BaseHTTPRequestHandler],
    stopping: threading.Event,
    runtime_warnings: _RuntimeWarnings,
) -> None:
    warning = f"Optional dashboard bind {host}:{port} is unavailable; retrying while localhost remains active."
    while not stopping.is_set():
        server: _DashboardHTTPServer | None = None
        try:
            server = _DashboardHTTPServer((host, port), handler)
            runtime_warnings.discard(warning)
            sys.stderr.write(f"progress-dashboard: serving optional {host}:{port}\n")
            server.serve_forever(poll_interval=0.5)
        except OSError as exc:
            runtime_warnings.add(warning)
            sys.stderr.write(f"progress-dashboard: {warning} ({exc})\n")
            stopping.wait(10.0)
        finally:
            if server is not None:
                server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the read-only Dentobot project progress dashboard")
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY, help="Dentobot overlay root")
    parser.add_argument(
        "--host",
        action="append",
        type=_validated_host,
        default=[],
        metavar="IP",
        help="additional specific IPv4 address to bind (repeatable); localhost is always bound",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP port (default: 8766)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    overlay, overlay_warning = _safe_overlay(args.overlay)
    if overlay_warning:
        sys.stderr.write(f"progress-dashboard: {overlay_warning}\n")
    runtime_warnings = _RuntimeWarnings()
    handler = _make_handler(overlay, runtime_warnings)
    hosts = list(dict.fromkeys([DEFAULT_HOST, *args.host]))
    local_server = _DashboardHTTPServer((DEFAULT_HOST, args.port), handler)
    stopping = threading.Event()
    optional_threads: list[threading.Thread] = []
    for host in hosts:
        if host == DEFAULT_HOST:
            continue
        thread = threading.Thread(
            target=_serve_optional_host,
            args=(host, args.port, handler, stopping, runtime_warnings),
            name=f"dashboard-{host}",
            daemon=True,
        )
        thread.start()
        optional_threads.append(thread)

    sys.stderr.write(f"progress-dashboard: serving http://{DEFAULT_HOST}:{args.port}\n")
    try:
        local_server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stopping.set()
        local_server.shutdown()
        local_server.server_close()
        for thread in optional_threads:
            thread.join(timeout=1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
