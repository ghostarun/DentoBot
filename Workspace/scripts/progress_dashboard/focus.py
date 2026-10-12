#!/usr/bin/env python3
"""Write explicit operational focus receipts for the progress dashboard.

This CLI records what an agent reports. It does not infer whether an agent is
running, create backlog entries, or grant execution authority.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

if __package__:
    from . import server as dashboard_server
else:
    repository_root = Path(__file__).resolve().parents[3]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    from Workspace.scripts.progress_dashboard import server as dashboard_server


DEFAULT_OVERLAY = Path("/home/tarun/dentobot")
DOCS_PATH = Path(__file__).resolve().parents[2] / "docs"
BACKLOG_PATH = DOCS_PATH / "backlog.md"
PLAN_PATH = DOCS_PATH / "DEVELOPMENT_PLAN.md"
SESSION_RE = dashboard_server.SESSION_FILE_RE
MILESTONES = (
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
ROLES = ("main", "supporting")
STATUSES = ("active", "blocked", "awaiting-review", "completed")
RECEIPT_FIELDS = (
    "task_id",
    "milestone",
    "role",
    "objective",
    "acceptance",
    "stop_condition",
)
TEXT_LIMIT = 4000


class FocusError(Exception):
    """A report could not be safely read or written."""


def utc_now() -> str:
    """Return an aware UTC timestamp in a compact ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def validate_session(session: str) -> str:
    if not SESSION_RE.fullmatch(session):
        raise FocusError(
            "session must start with an ASCII letter or digit and contain at most "
            "80 ASCII letters, digits, underscores, or hyphens"
        )
    return session


def validate_text(name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise FocusError(f"{name} must not be empty")
    if len(cleaned) > TEXT_LIMIT:
        raise FocusError(f"{name} must be at most {TEXT_LIMIT} characters")
    return cleaned


def _has_aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def load_task_map(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Use the dashboard's canonical parser for IDs, aliases and ID ranges."""
    path = path or BACKLOG_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FocusError(f"cannot read canonical backlog at {path}: {exc}") from exc
    try:
        tasks = dashboard_server.canonical_task_map(text)
    except (TypeError, ValueError) as exc:
        raise FocusError(f"cannot parse canonical task IDs from {path}: {exc}") from exc
    if not isinstance(tasks, dict):
        raise FocusError(f"canonical task parser returned an invalid mapping for {path}")
    return tasks


def load_milestones(path: Path | None = None) -> tuple[str, ...]:
    """Read choices from current plan metadata, with legacy fallback only if absent."""
    path = path or PLAN_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FocusError(f"cannot read canonical dashboard metadata at {path}: {exc}") from exc
    try:
        metadata = dashboard_server.parse_dashboard_metadata(text)
    except (TypeError, ValueError) as exc:
        raise FocusError(f"cannot parse dashboard milestone metadata at {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise FocusError(f"dashboard metadata parser returned an invalid result for {path}")

    milestones = metadata.get("milestones")
    if isinstance(milestones, list) and milestones:
        ids = tuple(
            item["id"]
            for item in milestones
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item["id"]
        )
        if ids and len(ids) == len(milestones):
            return ids
        raise FocusError("canonical dashboard metadata has no valid milestone IDs")
    if metadata.get("metadata_present") is False:
        return MILESTONES
    raise FocusError("canonical dashboard metadata is present but has no valid milestones")


def validate_task(task_id: str, task_map: dict[str, dict[str, Any]]) -> str:
    cleaned = task_id.strip()
    task = task_map.get(cleaned)
    if task is None:
        raise FocusError(
            f"unknown task ID {cleaned!r}; choose an exact ID, alias, or expanded range ID "
            "from the backlog table"
        )
    canonical = task.get("task_id")
    if not isinstance(canonical, str) or not canonical:
        raise FocusError(f"canonical task ID mapping for {cleaned!r} is malformed")
    return canonical


def storage_dir(overlay: Path) -> Path:
    directory = overlay.expanduser().resolve() / "data" / "project-progress" / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def session_lock(directory: Path, session: str) -> Iterator[None]:
    lock_path = directory / f".{session}.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def receipt_path(directory: Path, session: str) -> Path:
    return directory / f"{session}.json"


def _read_receipt(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FocusError(f"cannot read focus receipt {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FocusError(f"focus receipt {path} is not a JSON object")
    return data


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise FocusError(f"cannot atomically write focus receipt {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _append_event(directory: Path, action: str, receipt: dict[str, Any]) -> None:
    path = directory / f"{receipt['session']}.jsonl"
    event = {
        "schema_version": 1,
        "occurred_at": receipt["updated_at"],
        "action": action,
        "session": receipt["session"],
        "receipt": receipt,
    }
    line = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(line)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while appending focus event")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise FocusError(f"cannot append focus event {path}: {exc}") from exc
    finally:
        os.close(descriptor)


def _validate_fields(
    values: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    milestones: tuple[str, ...],
) -> dict[str, Any]:
    validated = dict(values)
    if "task_id" in validated:
        validated["task_id"] = validate_task(str(validated["task_id"]), task_map)
    if "milestone" in validated and validated["milestone"] not in milestones:
        raise FocusError(f"milestone must be one of: {', '.join(milestones)}")
    if "role" in validated and validated["role"] not in ROLES:
        raise FocusError(f"role must be one of: {', '.join(ROLES)}")
    for field in ("objective", "acceptance", "stop_condition"):
        if field in validated:
            validated[field] = validate_text(field, str(validated[field]))
    if "status" in validated and validated["status"] not in STATUSES:
        raise FocusError(f"status must be one of: {', '.join(STATUSES)}")
    return validated


def create_receipt(args: argparse.Namespace, directory: Path) -> dict[str, Any]:
    session = validate_session(args.session)
    path = receipt_path(directory, session)
    task_map = load_task_map()
    milestones = load_milestones()
    fields = _validate_fields(
        {
            "task_id": args.task_id,
            "milestone": args.milestone,
            "role": args.role,
            "objective": args.objective,
            "acceptance": args.acceptance,
            "stop_condition": args.stop_condition,
            "status": args.status,
        },
        task_map,
        milestones,
    )
    now = utc_now()
    active = fields["status"] == "active"
    receipt = {
        "session": session,
        **fields,
        "started_at": now,
        "updated_at": now,
        "status_changed_at": now,
        "focus_changed_at": now,
        "active_since": now if active else None,
    }
    with session_lock(directory, session):
        if path.exists():
            raise FocusError(
                f"session {session!r} already has a receipt; use update to preserve its start time"
            )
        _atomic_write_json(path, receipt)
        _append_event(directory, "set", receipt)
    return receipt


def update_receipt(args: argparse.Namespace, directory: Path) -> dict[str, Any]:
    session = validate_session(args.session)
    path = receipt_path(directory, session)
    changes = {
        field: getattr(args, field)
        for field in (*RECEIPT_FIELDS, "status")
        if getattr(args, field, None) is not None
    }
    if not changes:
        raise FocusError("update needs at least one changed field")
    task_map = load_task_map()
    milestones = load_milestones()
    changes = _validate_fields(changes, task_map, milestones)
    with session_lock(directory, session):
        if not path.exists():
            raise FocusError(f"no focus receipt exists for session {session!r}")
        receipt = _read_receipt(path)
        if receipt.get("session") != session:
            raise FocusError(f"focus receipt {path} has a mismatched session name")
        old_status = receipt.get("status")
        old_focus = tuple(receipt.get(field) for field in ("task_id", "milestone", "role"))
        receipt.update(changes)
        receipt["task_id"] = validate_task(str(receipt.get("task_id", "")), task_map)
        if receipt.get("milestone") not in milestones:
            raise FocusError("focus receipt milestone is no longer in canonical dashboard metadata")
        now = utc_now()
        new_status = receipt.get("status")
        new_focus = tuple(receipt.get(field) for field in ("task_id", "milestone", "role"))
        status_changed = new_status != old_status
        focus_changed = new_focus != old_focus
        if status_changed:
            receipt["status_changed_at"] = now
        if focus_changed:
            receipt["focus_changed_at"] = now
        if new_status == "active":
            # A legacy receipt has no defensible active interval. Start one at
            # this explicit report; never backfill it from started_at.
            if status_changed or focus_changed or not _has_aware_timestamp(
                receipt.get("active_since")
            ):
                receipt["active_since"] = now
        else:
            receipt["active_since"] = None
        receipt["updated_at"] = now
        _atomic_write_json(path, receipt)
        _append_event(directory, "update", receipt)
    return receipt


def finish_receipt(args: argparse.Namespace, directory: Path) -> dict[str, Any]:
    session = validate_session(args.session)
    path = receipt_path(directory, session)
    with session_lock(directory, session):
        if not path.exists():
            raise FocusError(f"no focus receipt exists for session {session!r}")
        receipt = _read_receipt(path)
        if receipt.get("session") != session:
            raise FocusError(f"focus receipt {path} has a mismatched session name")
        now = utc_now()
        if receipt.get("status") != args.status:
            receipt["status_changed_at"] = now
        receipt["status"] = args.status
        receipt["active_since"] = None
        receipt["updated_at"] = now
        _atomic_write_json(path, receipt)
        _append_event(directory, "finish", receipt)
    return receipt


def read_receipt(args: argparse.Namespace, directory: Path) -> dict[str, Any]:
    session = validate_session(args.session)
    path = receipt_path(directory, session)
    with session_lock(directory, session):
        if not path.exists():
            raise FocusError(f"no focus receipt exists for session {session!r}")
        return _read_receipt(path)


def add_overlay_argument(parser: argparse.ArgumentParser) -> None:
    # Accept --overlay either before or after the subcommand.
    parser.add_argument(
        "--overlay",
        type=Path,
        default=argparse.SUPPRESS,
        help=f"Ubuntu overlay root (default: {DEFAULT_OVERLAY})",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explicitly report an agent's current project focus."
    )
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    subparsers = parser.add_subparsers(dest="command", required=True)
    milestones = load_milestones()

    set_parser = subparsers.add_parser("set", help="start a new focus receipt")
    add_overlay_argument(set_parser)
    set_parser.add_argument("--session", required=True)
    set_parser.add_argument("--task", dest="task_id", required=True)
    set_parser.add_argument("--milestone", choices=milestones, required=True)
    set_parser.add_argument("--role", choices=ROLES, required=True)
    set_parser.add_argument("--objective", required=True)
    set_parser.add_argument("--acceptance", required=True)
    set_parser.add_argument("--stop-condition", required=True)
    set_parser.add_argument("--status", choices=STATUSES, default="active")
    set_parser.set_defaults(handler=create_receipt)

    update_parser = subparsers.add_parser("update", help="update an existing receipt")
    add_overlay_argument(update_parser)
    update_parser.add_argument("--session", required=True)
    update_parser.add_argument("--task", dest="task_id")
    update_parser.add_argument("--milestone", choices=milestones)
    update_parser.add_argument("--role", choices=ROLES)
    update_parser.add_argument("--objective")
    update_parser.add_argument("--acceptance")
    update_parser.add_argument("--stop-condition")
    update_parser.add_argument("--status", choices=STATUSES)
    update_parser.set_defaults(handler=update_receipt)

    finish_parser = subparsers.add_parser(
        "finish", help="mark a receipt completed or awaiting review"
    )
    add_overlay_argument(finish_parser)
    finish_parser.add_argument("--session", required=True)
    finish_parser.add_argument(
        "--status", choices=("completed", "awaiting-review"), default="completed"
    )
    finish_parser.set_defaults(handler=finish_receipt)

    status_parser = subparsers.add_parser("status", help="show one focus receipt")
    add_overlay_argument(status_parser)
    status_parser.add_argument("--session", required=True)
    status_parser.set_defaults(handler=read_receipt)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        directory = storage_dir(args.overlay)
        receipt = args.handler(args, directory)
    except FocusError as exc:
        print(f"focus: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
