#!/usr/bin/env python3
"""Chronology projection for the read-only project progress dashboard.

This module reads only configured, bounded project records and operational
metadata. It keeps project chronology separate from the live-focus receipt
projection: a completed or stale item can remain the latest project work while
``active_now`` continues to mean a fresh explicit focus receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable
from urllib.parse import quote


CONFIG_NAME = "work-history-config.json"
T3_OBSERVATIONS_NAME = "t3-work-observations.json"
CACHE_DIRECTORY = "work-history"
CACHE_NAME = "section-observations.json"
CONFIG_MAX_BYTES = 128 * 1024
T3_MAX_BYTES = 128 * 1024
DOCUMENT_MAX_BYTES = 4 * 1024 * 1024
EVENT_SOURCE_MAX_BYTES = 2 * 1024 * 1024
EVENT_SOURCE_MAX_LINES = 1500
MAX_RECENT_WORK = 6
MAX_TITLE = 300
MAX_OBJECTIVE = 1200
MAX_SUMMARY = 320
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TASK_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?:\.{1,2}[A-Z0-9]+)*(?![A-Z0-9])"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
ISO_RE = re.compile(
    r"(?<![\w])\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})(?![\w])"
)
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
SAFE_EVENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
STATUS_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:status|state)(?:\*\*)?\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)
FIELD_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(objective|outcome|milestone|kind|role)"
    r"(?:\*\*)?\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)

ALLOWED_CANONICAL_FILES = frozenset(
    {
        "backlog.md",
        "TASKS.md",
        "DEVELOPMENT_PLAN.md",
        "DECISIONS.md",
        "PROJECT_CONTEXT.md",
        "logbook/2026-10-11.md",
    }
)
ALLOWED_ADVISOR_WORKTREE_FILES = frozenset(
    {"TASKS.md", "DECISIONS.md", "logbook/2026-10-11.md"}
)
ADVISOR_WORKTREE_NAME = "FDI34 advisor worktree records"
ADVISOR_WORKTREE_PATH = Path(
    "/home/tarun/dentobot-worktrees/dcp-partial-case-complete-astra-20261011/Workspace/docs"
)
CODEX_SESSION_ROOT = Path("/home/tarun/.codex/sessions")
CODEX_LIFECYCLE_DB = Path("/home/tarun/.codex/thread_history_1.sqlite")
CODEX_EXPECTED_CWD = Path(
    "/home/tarun/dentobot-worktrees/dcp-partial-case-complete-astra-20261011"
)
CANONICAL_ROOT_NAME = "canonical project records"

_CACHE_LOCK = threading.Lock()


def _clean(value: Any, limit: int = MAX_OBJECTIVE) -> str:
    if not isinstance(value, str):
        return ""
    return CONTROL_CHARS_RE.sub("", value).strip()[:limit]


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _day_timestamp(value: date) -> datetime:
    return datetime.combine(value, datetime_time.min, tzinfo=timezone.utc)


def _safe_relative_file(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    normalized = path.as_posix()
    return normalized if normalized == value else None


def _read_small_json(path: Path, limit: int, *, no_symlink: bool = True) -> tuple[Any | None, str | None]:
    try:
        if no_symlink and path.is_symlink():
            return None, "is a symlink"
        if path.stat().st_size > limit:
            return None, "is oversized"
        raw = path.read_bytes()
    except OSError as exc:
        return None, exc.strerror or "is unavailable"
    try:
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeError, json.JSONDecodeError):
        return None, "is not valid UTF-8 JSON"


def _read_regular_file(root: Path, relative: str, limit: int = DOCUMENT_MAX_BYTES) -> tuple[str | None, str | None, str | None]:
    """Read one allowlisted path without following file or directory symlinks."""
    safe = _safe_relative_file(relative)
    if safe is None:
        return None, None, "has an unsafe configured path"
    candidate = root
    for part in PurePosixPath(safe).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return None, None, "contains a symlink"
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file() or not resolved.is_relative_to(resolved_root):
            return None, None, "is not a regular file inside its configured root"
        if resolved.stat().st_size > limit:
            return None, None, "is oversized"
        content = resolved.read_bytes().decode("utf-8")
        modified = _utc_iso(datetime.fromtimestamp(resolved.stat().st_mtime, timezone.utc))
    except (OSError, UnicodeError, ValueError) as exc:
        detail = getattr(exc, "strerror", None) or str(exc) or "is unavailable"
        return None, None, detail[:160]
    return content, modified, None


def _source_slug(name: str) -> str:
    if name == ADVISOR_WORKTREE_NAME:
        return "FDI34-advisor"
    if name == CANONICAL_ROOT_NAME:
        return "canonical"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return cleaned[:64] or "configured"


def _source_url(file_name: str, line: int) -> str:
    line = max(1, int(line))
    return f"/source?file={quote(file_name, safe='')}&line={line}#L{line}"


def _valid_config_root(
    item: dict[str, Any],
    overlay_root: Path,
    docs_root: Path,
) -> tuple[Path | None, list[str], dict[str, str], str | None, str | None]:
    name = _clean(item.get("name"), 120)
    raw_path = item.get("path")
    files_raw = item.get("files")
    bindings_raw = item.get("task_bindings", {})
    if not name or not isinstance(raw_path, str) or not isinstance(files_raw, list):
        return None, [], {}, "has an invalid name, path, or files field", None
    supplied = Path(raw_path).expanduser()
    try:
        resolved = supplied.resolve(strict=True)
    except OSError:
        return None, [], {}, "is unavailable", None
    try:
        canonical_expected = docs_root.resolve(strict=True)
    except OSError:
        canonical_expected = None
    try:
        advisor_expected = ADVISOR_WORKTREE_PATH.resolve(strict=True)
    except OSError:
        advisor_expected = ADVISOR_WORKTREE_PATH
    if canonical_expected is not None and resolved == canonical_expected:
        root_type = "canonical"
        allowed_by_name = ALLOWED_CANONICAL_FILES
    elif resolved == advisor_expected:
        root_type = "advisor_worktree"
        allowed_by_name = ALLOWED_ADVISOR_WORKTREE_FILES
        if supplied.absolute() != ADVISOR_WORKTREE_PATH:
            return None, [], {}, "does not use the exact approved worktree docs path", None
    else:
        return None, [], {}, "does not resolve to an approved controlled-record root", None
    if not resolved.is_dir():
        return None, [], {}, "is not a controlled-record directory", None
    if root_type == "canonical" and not resolved.is_relative_to(overlay_root):
        return None, [], {}, "resolves outside the overlay", None

    files: list[str] = []
    for raw_file in files_raw:
        filename = _safe_relative_file(raw_file)
        if filename is None or filename not in allowed_by_name:
            return None, [], {}, "contains a file outside its strict allowlist", None
        if filename not in files:
            files.append(filename)
    if not files:
        return None, [], {}, "has no allowlisted files", None
    if not isinstance(bindings_raw, dict):
        return None, [], {}, "has an invalid task_bindings map", None
    bindings: dict[str, str] = {}
    for alias, canonical in bindings_raw.items():
        alias_value = _clean(alias, 100)
        canonical_value = _clean(canonical, 100)
        if not alias_value or not TASK_TOKEN_RE.fullmatch(alias_value) or not TASK_TOKEN_RE.fullmatch(canonical_value):
            return None, [], {}, "contains an invalid task binding", None
        bindings[alias_value] = canonical_value
    return resolved, files, bindings, None, root_type


def _load_config(
    overlay_root: Path,
    docs_root: Path,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    config_path = overlay_root / "data" / "project-progress" / CONFIG_NAME
    payload, error = _read_small_json(config_path, CONFIG_MAX_BYTES)
    if error:
        warnings.append(f"Work-history configuration {error}; configured project sources were not read.")
        return [], [], []
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        warnings.append("Work-history configuration has an unsupported schema; configured project sources were not read.")
        return [], [], []
    roots_raw = payload.get("roots")
    if not isinstance(roots_raw, list):
        warnings.append("Work-history configuration has no roots list.")
        roots_raw = []
    roots: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in roots_raw:
        if not isinstance(item, dict):
            warnings.append("Skipped malformed work-history root configuration.")
            continue
        name = _clean(item.get("name"), 120)
        if name in seen_names:
            warnings.append(f"Skipped duplicate work-history root {name!r}.")
            continue
        resolved, files, bindings, reason, root_type = _valid_config_root(item, overlay_root, docs_root)
        if reason or resolved is None:
            warnings.append(f"Skipped work-history root {name or '(unnamed)'!r}: {reason or 'invalid root'}.")
            continue
        seen_names.add(name)
        roots.append(
            {
                "name": name,
                "path": resolved,
                "files": files,
                "task_bindings": bindings,
                "slug": _source_slug(name),
                "root_type": root_type,
            }
        )
    supporting_raw = payload.get("supporting_task_ids", [])
    supporting: list[str] = []
    if not isinstance(supporting_raw, list):
        warnings.append("Work-history supporting_task_ids is invalid; no supporting-role overrides were applied.")
    else:
        for item in supporting_raw:
            value = _clean(item, 100)
            if value and TASK_TOKEN_RE.fullmatch(value) and value not in supporting:
                supporting.append(value)
            else:
                warnings.append("Skipped an invalid work-history supporting task ID.")
    event_sources_raw = payload.get("event_sources", [])
    if not isinstance(event_sources_raw, list):
        warnings.append("Work-history event_sources is invalid; no configured event sources were read.")
        event_sources_raw = []
    event_sources = [item for item in event_sources_raw if isinstance(item, dict)]
    if len(event_sources) != len(event_sources_raw):
        warnings.append("Skipped malformed configured event source entries.")
    return roots, supporting, event_sources


def _canonical_id(
    reported: str,
    task_map: dict[str, dict[str, Any]],
    bindings: dict[str, str] | None,
) -> str | None:
    value = _clean(reported, 100)
    if not value:
        return None
    target = (bindings or {}).get(value, value)
    resolved = task_map.get(target) or task_map.get(value)
    if not isinstance(resolved, dict):
        return None
    canonical = resolved.get("task_id")
    return canonical if isinstance(canonical, str) and canonical else None


def _milestone_for(task_id: str, task_map: dict[str, dict[str, Any]]) -> str:
    task = task_map.get(task_id)
    milestone = task.get("milestone") if isinstance(task, dict) else None
    return _clean(milestone, 100)


def _role_for(
    task_id: str,
    supporting_ids: set[str],
    explicit_kind: Any = "",
) -> str:
    if task_id in supporting_ids:
        return "supporting"
    value = _clean(explicit_kind, 40).casefold()
    if value in {"main", "supporting"}:
        return value
    return "main"


def _status(value: Any, warnings: list[str], context: str) -> str:
    raw = _clean(value, 100).casefold().replace("_", "-")
    compact = re.sub(r"\s+", "-", raw)
    aliases = {
        "active": "running",
        "in-progress": "running",
        "in progress": "running",
        "inprogress": "running",
        "running": "running",
        "paused": "paused",
        "blocked": "blocked",
        "completed": "completed",
        "complete": "completed",
        "awaiting-review": "awaiting-review",
        "awaitingreview": "awaiting-review",
        "unknown": "unknown",
        "": "unknown",
    }
    result = aliases.get(compact)
    if result is None:
        warnings.append(f"Unrecognized explicit work status in {context}; displayed as unknown.")
        return "unknown"
    return result


def _explicit_status(value: Any) -> str:
    """Return only statuses expressed as a recognizable structured value."""
    raw = _clean(value, 100).casefold().replace("_", "-")
    compact = re.sub(r"\s+", "-", raw)
    return {
        "active": "running",
        "in-progress": "running",
        "inprogress": "running",
        "running": "running",
        "paused": "paused",
        "blocked": "blocked",
        "completed": "completed",
        "complete": "completed",
        "awaiting-review": "awaiting-review",
        "awaitingreview": "awaiting-review",
        "unknown": "unknown",
    }.get(compact, "")


def _summary_lines(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = FIELD_LINE_RE.match(line)
        if match:
            key = match.group(1).casefold()
            found.setdefault(key, _clean(match.group(2), MAX_OBJECTIVE))
    return found


def _heading_date(value: str, filename: str, warnings: list[str], context: str) -> tuple[datetime | None, str, bool]:
    """Use a dated section title or logbook date; never turn mtime into activity."""
    timestamps = ISO_RE.findall(value)
    if timestamps:
        parsed_values: list[datetime] = []
        invalid = False
        for stamp in timestamps:
            parsed = parse_timestamp(stamp)
            if parsed is None:
                invalid = True
            else:
                parsed_values.append(parsed)
        if invalid:
            warnings.append(f"Invalid explicit timestamp in {context}; that section was skipped.")
            return None, "invalid_timestamp", True
        return max(parsed_values), "section_timestamp", False

    date_values = DATE_RE.findall(value)
    if date_values:
        parsed_dates = [_parse_date(item) for item in date_values]
        if any(item is None for item in parsed_dates):
            warnings.append(f"Invalid explicit date in {context}; that section was skipped.")
            return None, "invalid_date", True
        return _day_timestamp(max(item for item in parsed_dates if item is not None)), "section_date", False

    if filename.startswith("logbook/"):
        stem = Path(filename).stem
        parsed_day = _parse_date(stem)
        if parsed_day is not None:
            return _day_timestamp(parsed_day), "logbook_date", False
    return None, "undated", False


def _extract_markdown_sections(
    filename: str,
    content: str,
    task_map: dict[str, dict[str, Any]],
    bindings: dict[str, str],
    modified_at: str | None,
    *,
    root_name: str,
    slug: str,
    source_namespace: str | None,
    url_for_file: Callable[[str, int], str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Project only sections whose own heading carries a mapped task ID."""
    lines = content.splitlines()
    heading_rows: list[tuple[int, int, str, set[str]]] = []
    for line_number, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        ids: set[str] = set()
        for token in TASK_TOKEN_RE.findall(heading.upper()):
            canonical = _canonical_id(token, task_map, bindings)
            if canonical:
                ids.add(canonical)
        heading_rows.append((line_number, level, heading, ids))

    result: list[dict[str, Any]] = []
    for index, (line_number, level, heading, ids) in enumerate(heading_rows):
        if not ids:
            continue
        end_line = len(lines)
        for later_line, later_level, _, _ in heading_rows[index + 1 :]:
            if later_level <= level:
                end_line = later_line - 1
                break
        section_text = "\n".join(lines[line_number - 1 : end_line])
        source_file = filename
        if source_namespace:
            source_file = f"work-history/{slug}/{filename}"
        section_day, basis, invalid = _heading_date(heading, filename, warnings, f"{filename}:{line_number}")
        if invalid:
            continue
        fields = _summary_lines(section_text)
        # Remove task tokens with the same grammar used for canonical mapping.
        heading_title = re.sub(
            r"(?<![A-Z0-9])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?:\.{1,2}[A-Z0-9]+)*(?![A-Z0-9])",
            " ",
            heading,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"[\s|–—:-]+", " ", heading_title).strip()[:MAX_TITLE]
        status_match = next(
            (match for line in section_text.splitlines() if (match := STATUS_LINE_RE.match(line))),
            None,
        )
        explicit_status = status_match.group(1) if status_match else ""
        kind = fields.get("kind") or fields.get("role", "")
        objective = fields.get("objective") or fields.get("outcome", "")
        for canonical_id in ids:
            result.append(
                {
                    "task_id": canonical_id,
                    "heading": heading,
                    "line": line_number,
                    "section_text": section_text,
                    "title": title,
                    "objective": objective,
                    "status": _explicit_status(explicit_status),
                    "kind": kind,
                    "milestone": fields.get("milestone") or _milestone_for(canonical_id, task_map),
                    "occurred_at": _utc_iso(section_day) if section_day is not None else None,
                    "timestamp_basis": basis,
                    "observed_at": modified_at,
                    "source_file": source_file,
                    "source_url": url_for_file(source_file, line_number),
                    "source_label": root_name if source_namespace else Path(filename).name,
                    "source_type": "controlled_record",
                    "cache_key": f"{source_file}\0{canonical_id}\0{heading.casefold()}",
                }
            )
    return result


def _cache_path(progress_root: Path) -> Path | None:
    try:
        directory = progress_root / CACHE_DIRECTORY
        if directory.is_symlink():
            return None
        resolved_root = progress_root.resolve(strict=True)
        if not directory.exists():
            directory.mkdir(mode=0o700)
        resolved_directory = directory.resolve(strict=True)
        if not resolved_directory.is_relative_to(resolved_root) or not resolved_directory.is_dir():
            return None
        cache = resolved_directory / CACHE_NAME
        if cache.is_symlink():
            return None
        return cache
    except OSError:
        return None


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temp_path: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".work-history-", suffix=".tmp", dir=path.parent)
        temp_path = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _cache_observations(
    progress_root: Path,
    records: list[dict[str, Any]],
    now: datetime,
    warnings: list[str],
) -> None:
    """Keep per-section observation times stable when a containing file changes."""
    path = _cache_path(progress_root)
    if path is None:
        warnings.append("Per-section work-history cache is unavailable or unsafe; undated source timing is unknown.")
        for record in records:
            if record.get("timestamp_basis") == "undated":
                record["timestamp_basis"] = "unknown_record_timing"
        return
    payload: Any = {}
    if path.exists():
        payload, error = _read_small_json(path, 2 * 1024 * 1024)
        if error or not isinstance(payload, dict) or payload.get("schema_version") != 1:
            warnings.append("Per-section work-history cache is malformed; a new baseline will be recorded.")
            payload = {}
    old_entries = payload.get("sections", {}) if isinstance(payload, dict) else {}
    if not isinstance(old_entries, dict):
        old_entries = {}
    updated_entries: dict[str, Any] = {}
    changed = False
    for record in records:
        if record.get("timestamp_basis") not in {
            "undated",
            "record_modified_initial_observation",
            "record_modified_after_section_change",
            "unknown_record_timing",
        }:
            continue
        body = str(record.get("section_text", ""))
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        source_file = str(record.get("source_file", ""))
        stable_header = re.sub(r"\s+", " ", str(record.get("heading", ""))).strip().casefold()
        key = str(record.get("cache_key") or f"{source_file}\0{record.get('task_id', '')}\0{stable_header}")
        previous = old_entries.get(key)
        if isinstance(previous, dict) and previous.get("sha256") == digest:
            observed = previous.get("observed_at")
            parsed = parse_timestamp(observed)
            if parsed is not None and parsed <= now:
                record["observed_at"] = _utc_iso(parsed)
                record["timestamp_basis"] = str(previous.get("timestamp_basis") or "record_modified_initial_observation")
            else:
                warnings.append(f"Cached observation time for {record.get('task_id')} is invalid or future; chronology is unknown.")
                record["observed_at"] = None
                record["timestamp_basis"] = "unknown_record_timing"
        else:
            modified = parse_timestamp(record.get("observed_at"))
            if modified is not None and modified <= now:
                is_baseline = not isinstance(previous, dict)
                record["observed_at"] = _utc_iso(modified)
                # A file modification is an observation about the record, not
                # proof that an agent acted at that instant.
                record["occurred_at"] = None
                record["timestamp_basis"] = (
                    "record_modified_initial_observation" if is_baseline else "record_modified_after_section_change"
                )
            else:
                if record.get("observed_at"):
                    warnings.append(f"Modified time for {record.get('source_file')} is invalid or future; chronology is unknown.")
                record["observed_at"] = None
                record["occurred_at"] = None
                record["timestamp_basis"] = "unknown_record_timing"
            changed = True
        updated_entries[key] = {
            "sha256": digest,
            "observed_at": record.get("observed_at"),
            "timestamp_basis": record.get("timestamp_basis"),
        }
    # Preserve entries for sources temporarily unavailable so a transient read
    # failure cannot reset a task's observation clock.
    for key, value in old_entries.items():
        updated_entries.setdefault(key, value)
    if changed or not path.exists():
        try:
            with _CACHE_LOCK:
                _atomic_json_write(path, {"schema_version": 1, "sections": updated_entries})
        except OSError:
            warnings.append("Could not persist the per-section work-history cache; undated record timing may reset.")


def _record_key(record: dict[str, Any], now: datetime) -> tuple[int, float, int, int, str, int, str]:
    occurred = parse_timestamp(record.get("occurred_at"))
    observed = parse_timestamp(record.get("observed_at"))
    selected = occurred or observed
    source_type = record.get("source_type")
    source_rank = {
        "native_turn": 6,
        "t3_observation": 5,
        "focus_activity": 4,
        "focus_receipt": 3,
        "controlled_record": 2,
        "event_source": 1,
    }.get(source_type, 0)
    return (
        1 if occurred is not None else 0,
        selected.timestamp() if selected is not None else float("-inf"),
        source_rank,
        1 if record.get("turn_id") else 0,
        str(record.get("source", {}).get("file", "")),
        int(record.get("source", {}).get("line", 0) or 0),
        str(record.get("thread_id") or record.get("session") or ""),
    )


def _event_dedup_key(item: dict[str, Any]) -> tuple[str, str, str]:
    occurred = parse_timestamp(item.get("occurred_at"))
    observed = parse_timestamp(item.get("observed_at"))
    moment = occurred or observed
    moment_key = _utc_iso(moment) if moment is not None else ""
    detail = _clean(item.get("objective") or item.get("summary") or item.get("title"), MAX_OBJECTIVE)
    return (
        str(item.get("task_id") or ""),
        moment_key,
        re.sub(r"\s+", " ", detail).strip().casefold(),
    )


def _make_item(
    *,
    task_id: str,
    title: Any,
    objective: Any,
    status: Any,
    occurred_at: Any,
    observed_at: Any,
    timestamp_basis: Any,
    milestone: Any,
    kind: Any,
    source_file: Any,
    source_line: Any,
    source_url: Any,
    source_label: Any,
    source_type: str,
    warnings: list[str],
    context: str,
    session: Any = None,
    thread_id: Any = None,
    summary: Any = None,
) -> dict[str, Any]:
    occurred = parse_timestamp(occurred_at)
    observed = parse_timestamp(observed_at)
    result: dict[str, Any] = {
        "id": task_id,
        "task_id": task_id,
        "title": _clean(title, MAX_TITLE) or task_id,
        "objective": _clean(objective, MAX_OBJECTIVE),
        "status": _status(status, warnings, context),
        "occurred_at": _utc_iso(occurred) if occurred is not None else None,
        "observed_at": _utc_iso(observed) if observed is not None else None,
        "timestamp_basis": _clean(timestamp_basis, 200) or "unknown",
        "milestone": _clean(milestone, 100),
        "kind": "supporting" if _clean(kind, 40).casefold() == "supporting" else "main",
        "source": {
            "file": _clean(source_file, 240),
            "line": max(1, int(source_line or 1)),
            "url": _clean(source_url, 1000),
            "label": _clean(source_label, 160),
        },
        "source_type": source_type,
    }
    clean_session = _clean(session, 100)
    clean_thread = _clean(thread_id, 140)
    clean_summary = _clean(summary, MAX_SUMMARY)
    if clean_session:
        result["session"] = clean_session
    if clean_thread:
        result["thread_id"] = clean_thread
    if clean_summary:
        result["summary"] = clean_summary
    return result


def _candidate_from_controlled(
    record: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    bindings: dict[str, str],
    supporting_ids: set[str],
    now: datetime,
    warnings: list[str],
) -> dict[str, Any] | None:
    task_id = record.get("task_id")
    occurred = parse_timestamp(record.get("occurred_at"))
    observed = parse_timestamp(record.get("observed_at"))
    if occurred is not None and occurred > now:
        warnings.append(f"Future work timestamp in {record.get('source_file')} was skipped.")
        return None
    if record.get("occurred_at") and occurred is None:
        warnings.append(f"Invalid work timestamp in {record.get('source_file')} was skipped.")
        return None
    if observed is not None and observed > now:
        warnings.append(f"Future record observation in {record.get('source_file')} was skipped.")
        return None
    canonical = _canonical_id(str(task_id or ""), task_map, bindings)
    if canonical is None:
        warnings.append(f"Skipped work-history record with an unknown task ID in {record.get('source_file')}.")
        return None
    return _make_item(
        task_id=canonical,
        title=record.get("title"),
        objective=record.get("objective"),
        status=record.get("status"),
        occurred_at=record.get("occurred_at"),
        observed_at=record.get("observed_at"),
        timestamp_basis=record.get("timestamp_basis"),
        milestone=record.get("milestone") or _milestone_for(canonical, task_map),
        kind=_role_for(canonical, supporting_ids, record.get("kind")),
        source_file=record.get("source_file"),
        source_line=record.get("line"),
        source_url=record.get("source_url"),
        source_label=record.get("source_label"),
        source_type="controlled_record",
        warnings=warnings,
        context=str(record.get("source_file") or "controlled record"),
    )


def _project_backlog_rows(
    backlog_rows: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
    supporting_ids: set[str],
    source_metadata: dict[str, dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for task in backlog_rows:
        task_id = str(task.get("id") or "")
        canonical = _canonical_id(task_id, task_map, {})
        if canonical is None:
            continue
        filename = "backlog.md"
        metadata = source_metadata.get(filename, {})
        section = _clean(task.get("section"), 300)
        occurred, basis, invalid = _heading_date(section, filename, warnings, f"backlog.md:{task.get('source_line', 1)}")
        if invalid:
            continue
        status = _explicit_status(task.get("state", ""))
        title = task.get("outcome") or task.get("remaining") or canonical
        line = int(task.get("source_line") or 1)
        records.append(
            {
                "task_id": canonical,
                "heading": section or canonical,
                "line": line,
                "section_text": "\n".join(
                    str(task.get(key) or "") for key in ("outcome", "state", "remaining", "boundary")
                ),
                "title": title,
                "objective": task.get("outcome") or "",
                "status": status,
                "kind": "supporting" if canonical in supporting_ids else "main",
                "milestone": task.get("milestone") or _milestone_for(canonical, task_map),
                "occurred_at": _utc_iso(occurred) if occurred else None,
                "timestamp_basis": basis,
                "observed_at": metadata.get("updated_at"),
                "source_file": filename,
                "source_url": task.get("source_url") or _source_url(filename, line),
                "source_label": "Canonical backlog",
                "source_type": "controlled_record",
            }
        )
    return records


def _read_t3_observations(
    overlay_root: Path,
    task_map: dict[str, dict[str, Any]],
    supporting_ids: set[str],
    warnings: list[str],
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = overlay_root / "data" / "project-progress" / T3_OBSERVATIONS_NAME
    payload, error = _read_small_json(path, T3_MAX_BYTES)
    metadata: dict[str, Any] = {
        "file": T3_OBSERVATIONS_NAME,
        "label": "Coordinator-supplied T3 observation",
        "available": error is None,
        "live_connection": False,
    }
    if error:
        if path.exists() or path.is_symlink():
            warnings.append(f"T3 observation source {error}; no T3 observation was projected.")
        metadata["available"] = False
        return [], metadata
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("observations"), list):
        warnings.append("T3 observation source has an unsupported schema; no observations were projected.")
        metadata["available"] = False
        return [], metadata
    try:
        metadata["updated_at"] = _utc_iso(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
        metadata["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        metadata["updated_at"] = None
    result: list[dict[str, Any]] = []
    for index, entry in enumerate(payload["observations"]):
        context = f"{T3_OBSERVATIONS_NAME}[{index}]"
        if not isinstance(entry, dict):
            warnings.append(f"Skipped malformed T3 observation {index}.")
            continue
        task_id = _canonical_id(str(entry.get("task_id") or ""), task_map, {})
        occurred = parse_timestamp(entry.get("occurred_at"))
        observed = parse_timestamp(entry.get("observed_at"))
        if occurred is None or observed is None:
            warnings.append(f"Skipped T3 observation with an invalid timestamp in {context}.")
            continue
        if occurred > now or observed > now:
            warnings.append(f"Skipped future T3 observation in {context}.")
            continue
        if task_id is None:
            warnings.append(f"Skipped T3 observation with an unknown task ID in {context}.")
            continue
        thread = _clean(entry.get("thread_id"), 140)
        if not thread:
            warnings.append(f"Skipped T3 observation without a thread ID in {context}.")
            continue
        line = index + 1
        result.append(
            _make_item(
                task_id=task_id,
                title=entry.get("title"),
                objective=entry.get("objective"),
                status=entry.get("status"),
                occurred_at=entry.get("occurred_at"),
                observed_at=entry.get("observed_at"),
                timestamp_basis=entry.get("timestamp_basis") or "dated T3 observation; not a live connection",
                milestone=entry.get("milestone") or _milestone_for(task_id, task_map),
                kind=_role_for(task_id, supporting_ids, entry.get("kind")),
                source_file=T3_OBSERVATIONS_NAME,
                source_line=line,
                source_url=_source_url(T3_OBSERVATIONS_NAME, line),
                source_label=_clean(entry.get("source_label"), 160) or "T3 metadata observation",
                source_type="t3_observation",
                warnings=warnings,
                context=context,
                session=entry.get("session"),
                thread_id=thread,
                summary=entry.get("summary"),
            )
        )
    return result, metadata


def _receipt_status(value: Any) -> str:
    raw = _clean(value, 100).casefold()
    return {
        "active": "running",
        "running": "running",
        "paused": "paused",
        "blocked": "blocked",
        "completed": "completed",
        "awaiting-review": "awaiting-review",
    }.get(raw, "unknown")


def _project_receipts_and_activity(
    receipts: Iterable[dict[str, Any]],
    activity: Iterable[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
    supporting_ids: set[str],
    now: datetime,
    warnings: list[str],
    url_for_file: Callable[[str, int], str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for receipt in receipts:
        reported = str(receipt.get("reported_task_id") or receipt.get("task_id") or "")
        task_id = _canonical_id(reported, task_map, {})
        occurred_value = receipt.get("updated_at")
        occurred = parse_timestamp(occurred_value)
        if task_id is None:
            continue
        if occurred is None:
            warnings.append(f"Skipped focus receipt {receipt.get('session', '')} with an invalid update time.")
            continue
        if occurred > now:
            warnings.append(f"Skipped focus receipt {receipt.get('session', '')} with a future update time.")
            continue
        source_file = "sessions/" + _clean(receipt.get("session"), 100) + ".json"
        result.append(
            _make_item(
                task_id=task_id,
                title=receipt.get("objective") or task_id,
                objective=receipt.get("objective"),
                status=_receipt_status(receipt.get("status")),
                occurred_at=occurred_value,
                observed_at=_utc_iso(now),
                timestamp_basis="explicit focus receipt updated_at",
                milestone=receipt.get("milestone") or _milestone_for(task_id, task_map),
                kind=_role_for(task_id, supporting_ids, receipt.get("kind")),
                source_file=source_file,
                source_line=1,
                source_url="",
                source_label="Operational focus receipt",
                source_type="focus_receipt",
                warnings=warnings,
                context=source_file,
                session=receipt.get("session"),
            )
        )

    for event in activity:
        reported = str(event.get("reported_task_id") or event.get("task_id") or "")
        task_id = _canonical_id(reported, task_map, {})
        occurred_value = event.get("occurred_at")
        occurred = parse_timestamp(occurred_value)
        if task_id is None:
            continue
        if occurred is None:
            warnings.append(f"Skipped a focus activity event with an invalid timestamp for {reported}.")
            continue
        if occurred > now:
            warnings.append(f"Skipped a future focus activity event for {reported}.")
            continue
        session = _clean(event.get("session"), 100)
        source_file = "sessions/" + session + ".jsonl"
        result.append(
            _make_item(
                task_id=task_id,
                title=event.get("objective") or event.get("action") or task_id,
                objective=event.get("objective"),
                status=_receipt_status(event.get("status")),
                occurred_at=occurred_value,
                observed_at=_utc_iso(now),
                timestamp_basis="explicit focus activity occurred_at",
                milestone=event.get("milestone") or _milestone_for(task_id, task_map),
                kind=_role_for(task_id, supporting_ids, event.get("kind")),
                source_file=source_file,
                source_line=1,
                source_url="",
                source_label="Operational focus activity",
                source_type="focus_activity",
                warnings=warnings,
                context=source_file,
                session=session,
                summary=event.get("action"),
            )
        )
    return result


def _epoch_timestamp(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = datetime.fromtimestamp(float(value), timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return _utc_iso(parsed)


def _safe_codex_rollout_path(raw_path: Any, session: str) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path, str) or not raw_path:
        return None, "has no rollout path"
    supplied = Path(raw_path)
    allowed_root = CODEX_SESSION_ROOT
    if not supplied.is_absolute() or ".." in supplied.parts:
        return None, "has an unsafe rollout path"
    if not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", session):
        return None, "has an invalid native session ID"
    if not supplied.name.startswith("rollout-") or not supplied.name.endswith(f"-{session}.jsonl"):
        return None, "does not match its configured native session ID"
    try:
        root = allowed_root.resolve(strict=True)
        if allowed_root.is_symlink():
            return None, "uses a symlinked Codex session root"
        lexical_root = allowed_root.absolute()
        lexical_candidate = supplied.absolute()
        if not lexical_candidate.is_relative_to(lexical_root):
            return None, "is outside the approved Codex session root"
        cursor = lexical_root
        for part in lexical_candidate.relative_to(lexical_root).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return None, "contains a symlink"
        candidate = supplied.resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            return None, "is outside the approved Codex session root"
        if candidate.stat().st_size > 256 * 1024 * 1024:
            return None, "is oversized"
    except OSError:
        return None, "is unavailable"
    return candidate, None


def _read_codex_session_meta(path: Path, session: str, expected_cwd: Path) -> tuple[bool, str | None]:
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(262145)
    except OSError:
        return False, "could not read session metadata"
    if len(first_line) > 262144 or not first_line.endswith(b"\n"):
        return False, "has oversized or incomplete session metadata"
    try:
        event = json.loads(first_line.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False, "has malformed session metadata"
    payload = event.get("payload") if isinstance(event, dict) and event.get("type") == "session_meta" else None
    if not isinstance(payload, dict):
        return False, "does not begin with a session_meta record"
    raw_cwd = payload.get("cwd")
    if payload.get("id") != session or not isinstance(raw_cwd, str):
        return False, "does not match the configured native session ID"
    try:
        actual_cwd = Path(raw_cwd).resolve(strict=True)
        configured_cwd = expected_cwd.resolve(strict=True)
    except OSError:
        return False, "has an unavailable configured working directory"
    if actual_cwd != configured_cwd:
        return False, "does not match the configured worktree binding"
    return True, None


def _read_codex_rollout_tail(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], str | None]:
    """Return only bounded decoded JSON records; callers extract allowlisted fields."""
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            start = max(0, size - EVENT_SOURCE_MAX_BYTES)
            stream.seek(start)
            raw = stream.read(EVENT_SOURCE_MAX_BYTES)
    except OSError:
        return [], "could not read the bounded rollout tail"
    if start:
        first_newline = raw.find(b"\n")
        raw = raw[first_newline + 1 :] if first_newline >= 0 else b""
    records: list[tuple[int, dict[str, Any]]] = []
    bad = 0
    for offset, line in enumerate(raw.splitlines()[-EVENT_SOURCE_MAX_LINES:], start=1):
        if len(line) > 256 * 1024:
            bad += 1
            continue
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            bad += 1
            continue
        if isinstance(decoded, dict):
            records.append((offset, decoded))
    warning = "ignored malformed records in the bounded rollout tail" if bad else None
    return records, warning


def _latest_codex_turn(
    database: Path,
    thread_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if database.is_symlink():
        return None, "uses a symlinked lifecycle database"
    try:
        resolved = database.resolve(strict=True)
    except OSError:
        return None, "lifecycle database is unavailable"
    uri = f"file:{quote(str(resolved), safe='/')}?mode=ro"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=0.25)
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute(
            "SELECT turn_id,status,started_at,completed_at,duration_ms "
            "FROM thread_turns WHERE thread_id=? "
            "ORDER BY rollout_ordinal DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
    except sqlite3.Error:
        return None, "could not read the allowlisted latest-turn metadata"
    finally:
        if connection is not None:
            connection.close()
    if row is None:
        return None, "has no lifecycle row for the configured thread"
    turn_id, raw_status, started_at, completed_at, duration_ms = row
    return {
        "turn_id": _clean(turn_id, 100),
        "status": _clean(raw_status, 40),
        "started_at": _epoch_timestamp(started_at),
        "completed_at": _epoch_timestamp(completed_at),
        "duration_ms": duration_ms if isinstance(duration_ms, int) and 0 <= duration_ms < 7 * 24 * 3600 * 1000 else None,
    }, None


def _read_codex_rollout(
    entry: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    supporting_ids: set[str],
    now: datetime,
    warnings: list[str],
    url_for_file: Callable[[str, int], str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = _clean(entry.get("session"), 80)
    task_id = _canonical_id(str(entry.get("task_id") or ""), task_map, {})
    thread_id = _clean(entry.get("thread_id"), 140)
    expected_cwd = Path(str(entry.get("expected_cwd") or ""))
    configured_session_root = entry.get("allowed_session_root")
    metadata: dict[str, Any] = {
        "file": "native-turn/" + session if session else "native-turn",
        "label": "Local Codex turn metadata",
        "type": "codex_rollout",
        "available": False,
        "live_connection": False,
    }
    if not task_id or not thread_id or not session:
        warnings.append("Skipped Codex rollout source with missing task, thread, or session binding.")
        return [], metadata
    try:
        configured_root_path = Path(str(configured_session_root)).expanduser()
        if configured_root_path.absolute() != CODEX_SESSION_ROOT.absolute() or configured_root_path.is_symlink():
            raise OSError("unapproved session root")
        configured_root = configured_root_path.resolve(strict=True)
        approved_root = CODEX_SESSION_ROOT.resolve(strict=True)
    except OSError:
        warnings.append("Skipped Codex rollout source because its allowlisted session root is unavailable.")
        return [], metadata
    try:
        if expected_cwd.absolute() != CODEX_EXPECTED_CWD.absolute():
            raise OSError("unapproved worktree cwd")
        configured_cwd = expected_cwd.resolve(strict=True)
        approved_cwd = CODEX_EXPECTED_CWD.resolve(strict=True)
    except OSError:
        warnings.append("Skipped Codex rollout source because its worktree binding is unavailable.")
        return [], metadata
    if configured_root != approved_root or configured_cwd != approved_cwd:
        warnings.append("Skipped Codex rollout source with an unapproved root or working-directory binding.")
        return [], metadata
    path, error = _safe_codex_rollout_path(entry.get("path"), session)
    if error or path is None:
        warnings.append(f"Codex rollout source {error or 'is unavailable' }.")
        return [], metadata
    valid_meta, meta_error = _read_codex_session_meta(path, session, configured_cwd)
    if not valid_meta:
        warnings.append(f"Codex rollout source {meta_error or 'has invalid session metadata'}.")
        return [], metadata
    configured_db = entry.get("lifecycle_db")
    try:
        db_path = Path(str(configured_db)).expanduser()
        if db_path.absolute() != CODEX_LIFECYCLE_DB.absolute() or db_path.is_symlink():
            raise OSError("unapproved lifecycle database path")
        db_path.resolve(strict=True)
    except OSError:
        warnings.append("Skipped Codex lifecycle lookup because its database path is not the exact approved file.")
        db_path = CODEX_LIFECYCLE_DB
        lifecycle = None
        lifecycle_error = "unapproved or unavailable database path"
    else:
        lifecycle, lifecycle_error = _latest_codex_turn(db_path, session)
    if lifecycle_error:
        warnings.append(f"Codex lifecycle metadata {lifecycle_error}; turn status is unknown.")
    records, tail_warning = _read_codex_rollout_tail(path)
    if tail_warning:
        warnings.append(f"Codex rollout {tail_warning}.")
    assistant_events: list[tuple[datetime, str]] = []
    for _, event in records:
        payload = event.get("payload")
        if event.get("type") != "response_item" or not isinstance(payload, dict):
            continue
        if payload.get("type") != "message" or payload.get("role") != "assistant":
            continue
        if payload.get("phase") not in {"commentary", "final"}:
            continue
        occurred = parse_timestamp(event.get("timestamp"))
        if occurred is None or occurred > now:
            continue
        content = payload.get("content")
        if not isinstance(content, list):
            continue
        text_parts = [
            _clean(item.get("text"), MAX_SUMMARY)
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        summary = _clean(" ".join(part for part in text_parts if part), MAX_SUMMARY)
        if summary:
            assistant_events.append((occurred, summary))
    assistant_events.sort(key=lambda pair: pair[0])
    latest_agent_at, latest_agent_text = assistant_events[-1] if assistant_events else (None, "")

    raw_status = str(lifecycle.get("status") or "") if lifecycle else ""
    status_key = re.sub(r"[^a-z]", "", raw_status.casefold())
    if status_key == "inprogress":
        status = "running"
        lifecycle_at = lifecycle.get("started_at")
        if lifecycle.get("completed_at"):
            warnings.append("Codex lifecycle row is inProgress but includes completed_at; running state was retained.")
    elif status_key in {"completed", "complete", "idle"} and lifecycle and lifecycle.get("completed_at"):
        status = "completed"
        lifecycle_at = lifecycle.get("completed_at")
    else:
        status = "unknown"
        lifecycle_at = None
        if lifecycle and status_key not in {"inprogress", "completed", "complete", "idle"}:
            warnings.append("Codex lifecycle status is not a recognized structured state; displayed as unknown.")
    if lifecycle_at is not None and parse_timestamp(lifecycle_at) and parse_timestamp(lifecycle_at) > now:
        warnings.append("Future Codex lifecycle timestamp was ignored.")
        lifecycle_at = None
        status = "unknown"
    completed_at = parse_timestamp(lifecycle.get("completed_at")) if lifecycle else None
    if status == "completed" and completed_at is not None:
        if latest_agent_at is not None and latest_agent_at > completed_at:
            warnings.append(
                "An eligible assistant event is later than the completed lifecycle timestamp; completed status was retained and the later event time was used."
            )
            occurred_at = _utc_iso(latest_agent_at)
            basis = "latest eligible assistant event timestamp after native turn completion metadata"
        else:
            occurred_at = _utc_iso(completed_at)
            basis = "native thread turn completed_at from read-only lifecycle metadata"
    elif latest_agent_at is not None:
        occurred_at = _utc_iso(latest_agent_at)
        basis = "latest eligible assistant event timestamp in bounded rollout tail"
    elif lifecycle and lifecycle.get("started_at"):
        occurred_at = lifecycle.get("started_at")
        basis = "native thread turn started_at; no eligible assistant event in bounded tail"
    else:
        occurred_at = None
        basis = "native lifecycle observation; activity timestamp unavailable"
    filename = f"native-turn/{session}"
    task_source = task_map.get(task_id, {})
    task_line = int(task_source.get("source_line") or 1) if str(task_source.get("source_line", "1")).isdecimal() else 1
    item = _make_item(
        task_id=task_id,
        title=entry.get("title") or task_id,
        objective=latest_agent_text or entry.get("title") or task_id,
        status=status,
        occurred_at=occurred_at,
        observed_at=_utc_iso(now),
        timestamp_basis=basis,
        milestone=entry.get("milestone") or _milestone_for(task_id, task_map),
        kind=_role_for(task_id, supporting_ids, entry.get("kind")),
        source_file=filename,
        source_line=1,
        source_url=url_for_file("backlog.md", task_line),
        source_label="Local Codex thread (sanitized assistant summary; raw rollout hidden)",
        source_type="native_turn",
        warnings=warnings,
        context=filename,
        session=session,
        thread_id=thread_id,
        summary=latest_agent_text,
    )
    freshness_age = (now - latest_agent_at).total_seconds() if latest_agent_at else None
    item["freshness"] = "fresh" if freshness_age is not None and 0 <= freshness_age <= 15 * 60 else "stale"
    item["last_agent_event_at"] = _utc_iso(latest_agent_at) if latest_agent_at else None
    if lifecycle and lifecycle.get("turn_id"):
        item["turn_id"] = lifecycle["turn_id"]
    try:
        rollout_modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except (OSError, OverflowError, ValueError):
        rollout_modified = None
    if rollout_modified is not None and rollout_modified > now:
        warnings.append("Future Codex rollout file modification time was omitted from source metadata.")
        rollout_modified = None
    metadata.update(
        {
            "available": True,
            "updated_at": _utc_iso(rollout_modified) if rollout_modified else None,
            "status": status,
            "freshness": item["freshness"],
            "last_agent_event_at": item["last_agent_event_at"],
            "lifecycle_available": lifecycle is not None,
        }
    )
    progress_events: list[dict[str, Any]] = []
    for event_time, summary in assistant_events:
        progress_events.append(
            _make_item(
                task_id=task_id,
                title=entry.get("title") or task_id,
                objective=summary,
                status="unknown",
                occurred_at=_utc_iso(event_time),
                observed_at=_utc_iso(now),
                timestamp_basis="assistant commentary/final event timestamp in bounded rollout tail; historical status unknown",
                milestone=entry.get("milestone") or _milestone_for(task_id, task_map),
                kind=_role_for(task_id, supporting_ids, entry.get("kind")),
                source_file=filename,
                source_line=1,
                source_url=url_for_file("backlog.md", task_line),
                source_label="Local Codex progress event (sanitized assistant summary)",
                source_type="native_turn",
                warnings=warnings,
                context=filename,
                session=session,
                thread_id=thread_id,
                summary=summary,
            )
        )
    progress_events.append(item)
    return progress_events, metadata


def _read_event_sources(
    event_sources: list[dict[str, Any]],
    progress_root: Path,
    task_map: dict[str, dict[str, Any]],
    supporting_ids: set[str],
    now: datetime,
    warnings: list[str],
    url_for_file: Callable[[str, int], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read only explicitly configured structured event sources.

    Adapter dispatch is intentionally closed. New event types require a narrow
    parser for their documented, privacy-safe metadata format; arbitrary rollout
    or transcript JSONL is never passed through this generic adapter.
    """
    result: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    for entry in event_sources[:16]:
        source_type = _clean(entry.get("type"), 40)
        if source_type == "codex_rollout":
            records, source_info = _read_codex_rollout(
                entry, task_map, supporting_ids, now, warnings, url_for_file
            )
            result.extend(records)
            metadata.append(source_info)
            continue
        source_name = _clean(entry.get("name"), 80)
        relative = _safe_relative_file(entry.get("path"))
        if not source_name or not SAFE_EVENT_NAME_RE.fullmatch(source_name) or relative is None:
            warnings.append("Skipped an unsafe configured event source.")
            continue
        if source_type != "work_items_jsonl":
            warnings.append(f"Configured event source {source_name!r} uses an unsupported adapter type.")
            continue
        if not relative.startswith("event-sources/") or not relative.endswith(".jsonl"):
            warnings.append(f"Configured event source {source_name!r} is outside the event-sources allowlist.")
            continue
        content, modified_at, error = _read_regular_file(progress_root, relative, EVENT_SOURCE_MAX_BYTES)
        metadata.append(
            {
                "file": relative,
                "label": source_name,
                "type": source_type,
                "available": error is None,
                "updated_at": modified_at,
            }
        )
        if error or content is None:
            warnings.append(f"Configured event source {source_name!r} {error or 'is unavailable'}.")
            continue
        lines = content.splitlines()[-EVENT_SOURCE_MAX_LINES:]
        if len(content.splitlines()) > EVENT_SOURCE_MAX_LINES:
            warnings.append(f"Read only the latest bounded event tail from {source_name!r}.")
        for line_number, line in enumerate(lines, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"Ignored malformed JSONL record in {source_name!r}.")
                continue
            if not isinstance(event, dict):
                continue
            task_id = _canonical_id(str(event.get("task_id") or ""), task_map, {})
            occurred = parse_timestamp(event.get("occurred_at"))
            observed = parse_timestamp(event.get("observed_at"))
            if task_id is None or occurred is None or occurred > now:
                warnings.append(f"Skipped invalid, future, or unbound event in {source_name!r}.")
                continue
            if event.get("observed_at") and (observed is None or observed > now):
                warnings.append(f"Skipped event with an invalid observation time in {source_name!r}.")
                continue
            result.append(
                _make_item(
                    task_id=task_id,
                    title=event.get("title"),
                    objective=event.get("objective"),
                    status=event.get("status"),
                    occurred_at=event.get("occurred_at"),
                    observed_at=event.get("observed_at") or modified_at,
                    timestamp_basis=event.get("timestamp_basis") or "explicit structured event timestamp",
                    milestone=event.get("milestone") or _milestone_for(task_id, task_map),
                    kind=_role_for(task_id, supporting_ids, event.get("kind")),
                    source_file=relative,
                    source_line=line_number,
                    source_url="",
                    source_label=source_name,
                    source_type="event_source",
                    warnings=warnings,
                    context=f"{source_name}:{line_number}",
                    session=event.get("session"),
                    thread_id=event.get("thread_id"),
                    summary=event.get("summary"),
                )
            )
    if len(event_sources) > 16:
        warnings.append("Only the first 16 configured event sources were considered.")
    return result, metadata


def build_work_history(
    *,
    overlay_root: Path,
    docs_root: Path | None,
    documents: dict[str, str],
    backlog_rows: list[dict[str, Any]],
    source_metadata: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
    focus: list[dict[str, Any]],
    focus_history: list[dict[str, Any]],
    activity: list[dict[str, Any]],
    now: datetime,
    url_for_file: Callable[[str, int], str] = _source_url,
) -> dict[str, Any]:
    """Build latest-per-task chronology, current main work, and recent sequence."""
    warnings: list[str] = []
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    progress_root = overlay_root / "data" / "project-progress"
    try:
        resolved_progress = progress_root.resolve(strict=True)
        resolved_data = (overlay_root / "data").resolve(strict=True)
        if not resolved_progress.is_dir() or not resolved_progress.is_relative_to(resolved_data):
            raise OSError("unsafe work-history data root")
        progress_root = resolved_progress
    except OSError:
        warnings.append("Work-history operational data root is unavailable or unsafe.")
        progress_root = overlay_root / "data" / "project-progress"

    configured_roots: list[dict[str, Any]] = []
    supporting_ids: set[str] = set()
    configured_events: list[dict[str, Any]] = []
    if docs_root is not None:
        configured_roots, supporting_values, configured_events = _load_config(
            overlay_root, docs_root, warnings
        )
        for reported in supporting_values:
            canonical = _canonical_id(reported, task_map, {})
            if canonical is None:
                warnings.append(f"Configured supporting task {reported!r} is absent from the backlog.")
            else:
                supporting_ids.add(canonical)
    else:
        warnings.append("Canonical documents are unavailable; configured work-history roots were not read.")

    source_by_name = {str(item.get("file")): item for item in source_metadata if isinstance(item, dict)}
    records: list[dict[str, Any]] = []
    records.extend(_project_backlog_rows(backlog_rows, task_map, supporting_ids, source_by_name, warnings))

    external_metadata: list[dict[str, Any]] = []
    canonical_bindings: dict[str, str] = {}
    for root in configured_roots:
        root_name = root["name"]
        root_type = root["root_type"]
        bindings = root["task_bindings"]
        if root_type == "canonical":
            canonical_bindings.update(bindings)
            filenames = [name for name in documents if name in root["files"]]
            # Core source documents are already loaded through the server's
            # canonical allowlist; do not reread them or follow a second path.
            for filename in filenames:
                content = documents.get(filename)
                if content is None:
                    continue
                metadata = source_by_name.get(filename, {})
                if not isinstance(content, str):
                    continue
                records.extend(
                    _extract_markdown_sections(
                        filename,
                        content,
                        task_map,
                        bindings,
                        metadata.get("updated_at"),
                        root_name=root_name,
                        slug="canonical",
                        source_namespace=None,
                        url_for_file=url_for_file,
                        warnings=warnings,
                    )
                )
        elif root_type == "advisor_worktree":
            source_slug = "FDI34-advisor"
            for filename in root["files"]:
                content, modified_at, error = _read_regular_file(root["path"], filename)
                virtual_file = f"work-history/{source_slug}/{filename}"
                external_metadata.append(
                    {
                        "file": virtual_file,
                        "label": root_name,
                        "available": error is None,
                        "updated_at": modified_at,
                    }
                )
                if error or content is None:
                    warnings.append(f"Configured controlled source {virtual_file} {error or 'is unavailable'}.")
                    continue
                records.extend(
                    _extract_markdown_sections(
                        filename,
                        content,
                        task_map,
                        bindings,
                        modified_at,
                        root_name=root_name,
                        slug=source_slug,
                        source_namespace=source_slug,
                        url_for_file=url_for_file,
                        warnings=warnings,
                    )
                )

    _cache_observations(progress_root, records, now, warnings)
    candidates: list[dict[str, Any]] = []
    for record in records:
        candidate = _candidate_from_controlled(
            record, task_map, canonical_bindings, supporting_ids, now, warnings
        )
        if candidate:
            candidates.append(candidate)

    t3_records, t3_metadata = _read_t3_observations(
        overlay_root, task_map, supporting_ids, warnings, now
    )
    candidates.extend(t3_records)
    candidates.extend(
        _project_receipts_and_activity(
            [*focus, *focus_history],
            activity,
            task_map,
            supporting_ids,
            now,
            warnings,
            url_for_file,
        )
    )
    event_records, event_metadata = _read_event_sources(
        configured_events, progress_root, task_map, supporting_ids, now, warnings, url_for_file
    )
    candidates.extend(event_records)

    latest_by_task: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        existing = latest_by_task.get(candidate["task_id"])
        if existing is None or _record_key(candidate, now) > _record_key(existing, now):
            latest_by_task[candidate["task_id"]] = candidate
    ordered = sorted(
        latest_by_task.values(),
        key=lambda item: (_record_key(item, now), item["task_id"]),
        reverse=True,
    )
    main_items = [item for item in ordered if item.get("kind") == "main"]
    current_work = main_items[0] if main_items else None
    if current_work is None and ordered:
        warnings.append("Chronology has supporting work only; no main project item was promoted to current work.")
    recent_work: list[dict[str, Any]] = []
    current_event_key = _event_dedup_key(current_work) if current_work else None
    seen_events: set[tuple[str, str, str]] = set()
    for candidate in sorted(
        (item for item in candidates if item.get("kind") == "main"),
        key=lambda item: (_record_key(item, now), item["task_id"]),
        reverse=True,
    ):
        event_key = _event_dedup_key(candidate)
        if event_key == current_event_key or event_key in seen_events:
            continue
        seen_events.add(event_key)
        recent_work.append(candidate)
        if len(recent_work) >= MAX_RECENT_WORK:
            break

    source_list: list[dict[str, Any]] = []
    for root in configured_roots:
        if root["root_type"] == "canonical":
            for filename in root["files"]:
                metadata = source_by_name.get(filename, {})
                source_list.append(
                    {
                        "file": filename,
                        "label": "Canonical project records",
                        "available": filename in documents,
                        "updated_at": metadata.get("updated_at"),
                        "sha256": metadata.get("sha256"),
                    }
                )
    source_list.extend(external_metadata)
    source_list.append(t3_metadata)
    source_list.extend(event_metadata)
    native_active: list[dict[str, Any]] = []
    for item in event_records:
        if (
            item.get("source_type") == "native_turn"
            and item.get("status") == "running"
            and item.get("freshness") == "fresh"
            and item.get("last_agent_event_at")
        ):
            native_active.append(item)
    native_keys = {
        (str(item.get("session") or ""), str(item.get("task_id") or ""))
        for item in native_active
        if item.get("session")
    }
    existing_active = [
        item
        for item in focus
        if not (
            item.get("session")
            and (str(item.get("session")), str(item.get("task_id") or item.get("id") or "")) in native_keys
        )
    ]
    active_now = [*existing_active, *native_active]
    active_now.sort(
        key=lambda item: (
            parse_timestamp(item.get("updated_at") or item.get("last_agent_event_at") or item.get("occurred_at"))
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    unique_warnings = list(dict.fromkeys(_clean(item, 500) for item in warnings if _clean(item, 500)))
    return {
        "work_items": ordered,
        "current_work": current_work,
        "recent_work": recent_work,
        "active_now": active_now,
        "work_history_sources": {
            "coverage": "configured project records, focus receipts/activity, dated T3 observations, and bounded local Codex turn metadata; no live T3 connection or GUI-runtime claim",
            "live_t3_connection": False,
            "sources": source_list,
            "warnings": unique_warnings,
        },
    }


def read_allowlisted_source(overlay_root: Path, filename: str) -> tuple[str | None, str | None]:
    """Resolve only virtual source names emitted by this module."""
    if filename == T3_OBSERVATIONS_NAME:
        path = overlay_root / "data" / "project-progress" / T3_OBSERVATIONS_NAME
        payload, error = _read_small_json(path, T3_MAX_BYTES)
        if error or not isinstance(payload, dict):
            return None, error or "is malformed"
        observations = payload.get("observations")
        if not isinstance(observations, list):
            return None, "has no observations list"
        safe = {
            "schema_version": 1,
            "observations": [
                {
                    key: _clean(item.get(key), 300)
                    for key in (
                        "task_id",
                        "thread_id",
                        "status",
                        "occurred_at",
                        "observed_at",
                        "title",
                        "objective",
                        "kind",
                        "milestone",
                        "source_label",
                        "timestamp_basis",
                    )
                    if isinstance(item, dict) and item.get(key) is not None
                }
                for item in observations
                if isinstance(item, dict)
            ],
        }
        return json.dumps(safe, ensure_ascii=False, indent=2) + "\n", None

    match = re.fullmatch(r"work-history/FDI34-advisor/(TASKS\.md|DECISIONS\.md|logbook/2026-10-11\.md)", filename)
    if not match:
        return None, "is not allowlisted"
    relative = match.group(1)
    content, _, error = _read_regular_file(ADVISOR_WORKTREE_PATH, relative)
    return content, error
