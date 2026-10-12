#!/usr/bin/env python3
"""Focused, offline regression tests for PROGRESS-DASH-01."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from Workspace.scripts.progress_dashboard import (  # noqa: E402
    focus,
    install,
    item_explanation,
    server,
    work_history,
)


FOCUS_BACKLOG = """# Project tasks
| Priority | Outcome | Work item ID / aliases | State | Remaining completion |
|---|---|---|---|---|
| 1 | Grouped focus test | FOCUS-TST-02..04 / FOCUS-LEGACY | Active | Review receipt |
| 2 | Existing task test | DASH-TEST | Open | Verify current status |
"""


def metadata_document(
    *,
    current_ids: list[str] | None = None,
    spotlight_ids: list[str] | None = None,
    milestones: list[dict[str, object]] | None = None,
    title: str = "Fixture project",
    outcome: str = "Fixture outcome",
) -> str:
    if current_ids is None:
        current_ids = ["DASH-TEST"]
    if spotlight_ids is None:
        spotlight_ids = []
    if milestones is None:
        milestones = [
            {
                "id": "quality",
                "title": "Quality work",
                "goal": "Prove bounded behavior.",
                "status": "unknown",
                "evidence": [],
                "task_ids": [],
                "prefixes": ["DASH-", "FOCUS-TST-"],
            },
            {
                "id": "other",
                "title": "Other recorded work",
                "goal": "Keep unmapped work visible.",
                "status": "unknown",
                "evidence": [],
                "task_ids": [],
                "prefixes": [],
            },
        ]
    payload = {
        "schema_version": 1,
        "current": {
            "title": title,
            "outcome": outcome,
            "task_ids": current_ids,
            "spotlight_task_ids": spotlight_ids,
            "sequence_note": "Fixture selection; does not reorder dependencies.",
        },
        "milestones": milestones,
    }
    return (
        "## Live dashboard display metadata\n\n"
        "<!-- PROGRESS-DASHBOARD:START -->\n```json\n"
        + json.dumps(payload, indent=2)
        + "\n```\n<!-- PROGRESS-DASHBOARD:END -->\n"
    )


class DashboardTestCase(unittest.TestCase):
    """Keep every fixture write inside the approved verification run root."""

    def setUp(self) -> None:
        verification_root = os.environ.get("DENTOBOT_VERIFICATION_DIR")
        if not verification_root:
            self.fail("set DENTOBOT_VERIFICATION_DIR to the approved run directory")
        Path(verification_root).mkdir(parents=True, exist_ok=True)
        self._temporary_directory = tempfile.TemporaryDirectory(dir=verification_root)
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)

    def make_overlay(
        self,
        backlog: str | None = None,
        plan: str | None = None,
    ) -> tuple[Path, Path, Path]:
        overlay = self.root / "overlay"
        docs = overlay / "docs"
        sessions = overlay / "data" / "project-progress" / "sessions"
        (docs / "logbook").mkdir(parents=True)
        sessions.mkdir(parents=True)
        for name in server.CORE_SOURCE_FILES:
            (docs / name).write_text("", encoding="utf-8")
        (docs / "backlog.md").write_text(
            FOCUS_BACKLOG if backlog is None else backlog, encoding="utf-8"
        )
        (docs / "DEVELOPMENT_PLAN.md").write_text(
            metadata_document() if plan is None else plan, encoding="utf-8"
        )
        (docs / "logbook" / "2026-10-10.md").write_text("fixture\n", encoding="utf-8")
        return overlay, docs, sessions


class FocusReceiptTests(DashboardTestCase):
    def _run_focus(
        self, overlay: Path, arguments: list[str], now: str | None = None
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        time_patch = (
            mock.patch.object(focus, "utc_now", return_value=now)
            if now is not None
            else contextlib.nullcontext()
        )
        with (
            mock.patch.object(focus, "BACKLOG_PATH", overlay / "docs" / "backlog.md"),
            mock.patch.object(focus, "PLAN_PATH", overlay / "docs" / "DEVELOPMENT_PLAN.md"),
            time_patch,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = focus.main(arguments)
        return result, stdout.getvalue(), stderr.getvalue()

    def _set_arguments(
        self,
        overlay: Path,
        session: str = "agent_1",
        task_id: str = "FOCUS-TST-03",
    ) -> list[str]:
        return [
            "set", "--overlay", str(overlay), f"--session={session}",
            "--task", task_id, "--milestone", "quality",
            "--role", "main", "--objective", "Close a bounded supporting fix",
            "--acceptance", "Focused host evidence is recorded",
            "--stop-condition", "Stop after the focused check or on a new blocker",
        ]

    def test_shared_parser_normalizes_grouped_ids_and_rejects_unsafe_reports(self) -> None:
        overlay, _, _ = self.make_overlay(FOCUS_BACKLOG)
        result, _, error = self._run_focus(
            overlay, self._set_arguments(overlay, task_id="FOCUS-LEGACY")
        )
        self.assertEqual((result, error), (0, ""))
        receipt = json.loads(
            (overlay / "data/project-progress/sessions/agent_1.json").read_text()
        )
        self.assertEqual(receipt["task_id"], "FOCUS-TST-02..04")
        self.assertEqual(focus.validate_session("a" * 80), "a" * 80)
        with self.assertRaises(focus.FocusError):
            focus.validate_session("a" * 81)

        unknown = self._set_arguments(overlay, "agent_2", "NOT-IN-BACKLOG")
        result, _, error = self._run_focus(overlay, unknown)
        self.assertEqual(result, 2)
        self.assertIn("unknown task ID", error)

        for unsafe_session in ("../outside", "_leading", "-leading"):
            unsafe = self._set_arguments(overlay, unsafe_session)
            result, _, error = self._run_focus(overlay, unsafe)
            self.assertEqual(result, 2)
            self.assertIn("session must start", error)
        sessions = overlay / "data" / "project-progress" / "sessions"
        self.assertEqual(len(list(sessions.glob("*.json"))), 1)

    def test_active_interval_tracks_only_real_status_or_focus_transitions(self) -> None:
        overlay, _, _ = self.make_overlay(FOCUS_BACKLOG)
        times = [f"2026-10-10T12:00:{n:02d}Z" for n in range(10)]
        result, _, error = self._run_focus(overlay, self._set_arguments(overlay), times[0])
        self.assertEqual((result, error), (0, ""))
        session_file = overlay / "data/project-progress/sessions/agent_1.json"
        initial = json.loads(session_file.read_text(encoding="utf-8"))
        started_at = initial["started_at"]
        self.assertEqual(initial["active_since"], times[0])
        self.assertEqual(initial["status_changed_at"], times[0])
        self.assertEqual(initial["focus_changed_at"], times[0])

        def update(at: str, *args: str) -> tuple[int, str]:
            code, _, message = self._run_focus(
                overlay, ["update", "--session", "agent_1", "--overlay", str(overlay), *args], at
            )
            return code, message

        result, error = update(
            times[1], "--status", "active", "--acceptance", "Text-only report update"
        )
        self.assertEqual((result, error), (0, ""))
        updated = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(updated["started_at"], started_at)
        self.assertEqual(updated["active_since"], times[0])
        self.assertEqual(updated["status_changed_at"], times[0])
        self.assertEqual(updated["focus_changed_at"], times[0])

        self.assertEqual(update(times[2], "--status", "blocked"), (0, ""))
        blocked = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertIsNone(blocked["active_since"])
        self.assertEqual(blocked["status_changed_at"], times[2])
        self.assertEqual(blocked["focus_changed_at"], times[0])

        self.assertEqual(update(times[3], "--acceptance", "Still blocked"), (0, ""))
        blocked_heartbeat = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(blocked_heartbeat["status_changed_at"], times[2])
        self.assertIsNone(blocked_heartbeat["active_since"])

        self.assertEqual(update(times[4], "--status", "active"), (0, ""))
        resumed = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(resumed["active_since"], times[4])
        self.assertEqual(resumed["status_changed_at"], times[4])
        self.assertEqual(resumed["focus_changed_at"], times[0])

        self.assertEqual(update(times[5], "--role", "supporting"), (0, ""))
        role_changed = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(role_changed["active_since"], times[5])
        self.assertEqual(role_changed["focus_changed_at"], times[5])
        self.assertEqual(role_changed["status_changed_at"], times[4])

        self.assertEqual(update(times[6], "--task", "DASH-TEST"), (0, ""))
        task_changed = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(task_changed["task_id"], "DASH-TEST")
        self.assertEqual(task_changed["active_since"], times[6])
        self.assertEqual(task_changed["focus_changed_at"], times[6])
        self.assertEqual(task_changed["status_changed_at"], times[4])

        self.assertEqual(update(times[7], "--milestone", "other"), (0, ""))
        milestone_changed = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(milestone_changed["active_since"], times[7])
        self.assertEqual(milestone_changed["focus_changed_at"], times[7])

        result, _, error = self._run_focus(
            overlay,
            ["finish", "--session", "agent_1", "--overlay", str(overlay), "--status", "awaiting-review"],
            times[8],
        )
        self.assertEqual((result, error), (0, ""))
        awaiting = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertIsNone(awaiting["active_since"])
        self.assertEqual(awaiting["status_changed_at"], times[8])

        result, _, error = self._run_focus(
            overlay,
            ["finish", "--session", "agent_1", "--overlay", str(overlay), "--status", "completed"],
            times[9],
        )
        self.assertEqual((result, error), (0, ""))
        completed = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertEqual(completed["started_at"], started_at)
        self.assertEqual(completed["status_changed_at"], times[9])

        events = [json.loads(line) for line in session_file.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(
            [event["action"] for event in events],
            ["set", "update", "update", "update", "update", "update", "update", "update", "finish", "finish"],
        )
        self.assertTrue(all(event["receipt"]["started_at"] == started_at for event in events))

    def test_removed_current_task_cannot_be_heartbeated_but_can_be_finished(self) -> None:
        overlay, docs, _ = self.make_overlay(FOCUS_BACKLOG)
        result, _, error = self._run_focus(overlay, self._set_arguments(overlay), "2026-10-10T12:00:00Z")
        self.assertEqual((result, error), (0, ""))
        receipt_path = overlay / "data/project-progress/sessions/agent_1.json"
        before = json.loads(receipt_path.read_text(encoding="utf-8"))
        (docs / "backlog.md").write_text(
            "| ID | State | Outcome | Remaining |\n|---|---|---|---|\n| `DASH-TEST` | Open | Kept | Verify |\n",
            encoding="utf-8",
        )

        result, _, error = self._run_focus(
            overlay,
            ["update", "--session", "agent_1", "--overlay", str(overlay), "--status", "active"],
            "2026-10-10T12:00:01Z",
        )
        self.assertEqual(result, 2)
        self.assertIn("unknown task ID", error)
        self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8")), before)

        result, _, error = self._run_focus(
            overlay,
            ["finish", "--session", "agent_1", "--overlay", str(overlay), "--status", "completed"],
            "2026-10-10T12:00:02Z",
        )
        self.assertEqual((result, error), (0, ""))
        finished = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(finished["task_id"], "FOCUS-TST-02..04")
        self.assertEqual(finished["status"], "completed")
        self.assertIsNone(finished["active_since"])

    def test_milestones_are_dynamic_and_legacy_fallback_requires_absent_metadata(self) -> None:
        overlay, docs, _ = self.make_overlay(FOCUS_BACKLOG)
        with mock.patch.object(focus, "PLAN_PATH", docs / "DEVELOPMENT_PLAN.md"):
            self.assertEqual(focus.load_milestones(), ("quality", "other"))
            (docs / "DEVELOPMENT_PLAN.md").write_text("No metadata block.\n", encoding="utf-8")
            self.assertEqual(focus.load_milestones(), focus.MILESTONES)
            (docs / "DEVELOPMENT_PLAN.md").write_text(
                "<!-- PROGRESS-DASHBOARD:START -->\n```json\nnot-json\n```\n"
                "<!-- PROGRESS-DASHBOARD:END -->\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(focus.FocusError, "present but has no valid milestones"):
                focus.load_milestones()


class InstallerSafetyTests(DashboardTestCase):
    def test_systemd_argument_quoting_and_narrow_bind_addresses(self) -> None:
        argument = 'folder with space/quote"/$HOME%name\\file'
        quoted = install.systemd_quote(argument)
        self.assertEqual(quoted, '"folder with space/quote\\"/$$HOME%%name\\\\file"')
        with self.assertRaises(ValueError):
            install.systemd_quote("bad\nargument")

        unit = install.build_unit(self.root / "overlay with spaces", 8766, "100.95.7.78")
        self.assertIn('"127.0.0.1"', unit)
        self.assertIn('"100.95.7.78"', unit)
        self.assertNotIn("0.0.0.0", unit)
        self.assertNotIn("--host *", unit)
        self.assertIn("WantedBy=default.target", unit)

    def test_installer_refuses_to_replace_an_unmanaged_unit(self) -> None:
        path = self.root / "systemd" / "dentobot-progress.service"
        path.parent.mkdir(parents=True)
        original = "[Unit]\nDescription=An unrelated service\n"
        path.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "unrelated service"):
            install.write_unit(path, install.build_unit(self.root, 8766, None))
        self.assertEqual(path.read_text(encoding="utf-8"), original)


class BacklogProjectionTests(DashboardTestCase):
    def test_tables_aliases_priority_source_lines_and_narrative_notes(self) -> None:
        source = """# Pending backlog
Current checkpoint mentions `NARRATIVE-ONLY` but is not a task row.

## Main work
| ID | Priority | State | Outcome | Remaining completion | Boundary |
|---|---|---|---|---|---|
| `MAIN-01` / `MAIN-ALIAS` | 0 | Active | Main goal \| preserve a pipe | Review result | Keep scope |

## Visual review
| ID | Priority | Outcome | Evidence summary | Remaining user action | Dependency / overlap |
|---|---|---|---|---|---|
| `VIEW-U-01` | 1 | Opened view correction | Image evidence | Operator review | Existing owner |

## External source metadata
| ID / aliases | Source priority / owner | Pending deliverable | Dependencies / acceptance / overlap |
|---|---|---|---|
| `A-036` | P1 in register / P2 dashboard; Tarun | Internal sensing outline | Resolve source conflict |
| `DCP-02..08` / `DCP-LEGACY` | P3 / team | Remaining domain proof | Reuse accepted foundations |
| `DSS-01..05` | P3 | Studio migration | Guarded preview parity; DCP-00 |
| `DSS-06..12` | P3 | Studies and replay | Procedure/research separation; DSS-01..05 |
| `DHW-01..02` | P4 | Hardware-session boundary | Interface/data boundary; A-004/A-013 |

## S6-ADVISOR-GUI-01 backlog items
1. **Consent binding.** Observed: review needs an explicit decision.
   Preserve this continuation in the same note.
"""
        parsed = server.parse_backlog(source, "Project goal")
        rows = {row["id"]: row for row in parsed["tasks"]}
        self.assertEqual(
            set(rows),
            {"MAIN-01", "VIEW-U-01", "A-036", "DCP-02..08", "DSS-01..05", "DSS-06..12", "DHW-01..02"},
        )
        self.assertEqual(rows["MAIN-01"]["aliases"], ["MAIN-ALIAS"])
        self.assertEqual(rows["MAIN-01"]["priority_rank"], 0)
        self.assertEqual(rows["MAIN-01"]["outcome"], "Main goal | preserve a pipe")
        main_line = next(i for i, line in enumerate(source.splitlines(), 1) if "`MAIN-01`" in line)
        self.assertEqual(rows["MAIN-01"]["source_line"], main_line)
        self.assertTrue(rows["MAIN-01"]["source_url"].endswith(f"#L{main_line}"))
        self.assertEqual(rows["VIEW-U-01"]["state"], "Image evidence")
        self.assertEqual(rows["A-036"]["outcome"], "Internal sensing outline")
        self.assertIsNone(rows["A-036"]["priority_rank"])
        self.assertEqual(rows["DCP-02..08"]["aliases"], ["DCP-LEGACY"])
        self.assertIsNone(rows["DCP-02..08"]["priority_rank"])
        self.assertIsNone(rows["DSS-01..05"]["priority_rank"])
        self.assertEqual(rows["DSS-06..12"]["id"], "DSS-06..12")
        self.assertIsNone(rows["DHW-01..02"]["priority_rank"])
        self.assertNotIn("NARRATIVE-ONLY", rows)
        note_line = next(
            i for i, line in enumerate(source.splitlines(), 1)
            if line.startswith("1. **Consent binding.")
        )
        self.assertEqual(parsed["notes"][0]["source_line"], note_line)
        self.assertIn("Preserve this continuation", parsed["notes"][0]["text"])
        self.assertEqual(parsed["checkpoints"][0]["source_line"], 2)


class SnapshotAndSourceSafetyTests(DashboardTestCase):
    def test_stale_completed_supporting_future_and_corrupt_receipts(self) -> None:
        overlay, _, sessions = self.make_overlay()
        now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)

        def stamp(delta: timedelta) -> str:
            return (now + delta).isoformat().replace("+00:00", "Z")

        def receipt(
            session: str,
            started: str,
            updated: str,
            status: str = "active",
            role: str = "main",
            active_since: str | None = None,
        ) -> dict[str, str | None]:
            return {"session": session, "task_id": "DASH-TEST", "milestone": "reliability", "role": role,
                    "objective": "fixture", "acceptance": "fixture", "stop_condition": "fixture",
                    "status": status, "started_at": started, "updated_at": updated,
                    "status_changed_at": started, "focus_changed_at": started,
                    "active_since": active_since if active_since is not None else started}

        fixtures = {
            "fresh": receipt("fresh", stamp(-timedelta(minutes=5)), stamp(-timedelta(minutes=1)),
                             active_since=stamp(-timedelta(minutes=2))),
            "support": receipt("support", stamp(-timedelta(minutes=35)), stamp(-timedelta(minutes=1)),
                               role="supporting", active_since=stamp(-timedelta(minutes=31))),
            "stale": receipt("stale", stamp(-timedelta(minutes=20)), stamp(-timedelta(minutes=16))),
            "future": receipt("future", stamp(-timedelta(minutes=1)), stamp(timedelta(minutes=1))),
            "corrupt": receipt("corrupt", stamp(-timedelta(minutes=1)), "not-a-time"),
            "done": receipt("done", stamp(-timedelta(minutes=2)), stamp(-timedelta(minutes=1)), status="completed"),
        }
        legacy = receipt("legacy", stamp(-timedelta(minutes=1)), stamp(-timedelta(seconds=30)))
        legacy["kind"] = legacy.pop("role")
        fixtures["legacy"] = legacy
        for name, value in fixtures.items():
            (sessions / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
        (sessions / "malformed.json").write_text("{broken", encoding="utf-8")
        (sessions / "nonobject.json").write_text("[]", encoding="utf-8")
        event = {
            "schema_version": 1,
            "occurred_at": stamp(-timedelta(seconds=10)),
            "action": "finish",
            "session": "done",
            "receipt": fixtures["done"],
        }
        (sessions / "done.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

        snapshot = server.build_snapshot(overlay, now=now)
        current = {item["session"]: item for item in snapshot["focus"]}
        self.assertIn("fresh", current)
        self.assertEqual(current["legacy"]["kind"], "main")
        self.assertEqual(current["fresh"]["classification"], "fresh-active")
        self.assertEqual(current["fresh"]["active_elapsed_seconds"], 120)
        self.assertEqual(current["fresh"]["wall_elapsed_seconds"], 300)
        self.assertEqual(current["support"]["active_elapsed_seconds"], 31 * 60)
        self.assertTrue(all(item["is_current"] for item in current.values()))
        history = {item["session"]: item for item in snapshot["focus_history"]}
        self.assertEqual(history["done"]["classification"], "completed")
        self.assertEqual(history["stale"]["classification"], "stale")
        self.assertEqual(history["future"]["classification"], "stale")
        self.assertEqual(history["corrupt"]["classification"], "stale")
        self.assertFalse(any(item["is_current"] for item in history.values()))
        self.assertEqual(snapshot["focus_counts"], {"total": 3, "main": 2, "supporting": 1})
        self.assertTrue(any("more than 30 minutes" in item for item in snapshot["warnings"]))
        self.assertTrue(any("future updated_at" in item for item in snapshot["warnings"]))
        self.assertTrue(any("Skipped unreadable operational session receipt malformed.json" in item for item in snapshot["warnings"]))
        self.assertTrue(any("Skipped malformed operational session receipt nonobject.json" in item for item in snapshot["warnings"]))
        activity = snapshot["activity"][0]
        self.assertEqual((activity["action"], activity["session"], activity["status"]), ("finish", "done", "completed"))
        self.assertEqual(activity["task_classification"], "linked")
        self.assertEqual(activity["active_since"], fixtures["done"]["active_since"])

    def test_dynamic_metadata_selection_assignments_and_source_changes_are_fresh(self) -> None:
        overlay, docs, _ = self.make_overlay(FOCUS_BACKLOG)
        milestones = [
            {"id": "exact", "title": "Exact assignment", "goal": "Exact wins.", "status": "unknown",
             "evidence": [], "task_ids": ["FOCUS-TST-03"], "prefixes": ["FOCUS-TST-"]},
            {"id": "prefix", "title": "Prefix assignment", "goal": "Use longest prefix.", "status": "planned",
             "evidence": [], "task_ids": [], "prefixes": ["DASH-"]},
            {"id": "empty", "title": "No current rows", "goal": "Acceptance is explicit only.", "status": "unknown",
             "evidence": [], "task_ids": [], "prefixes": []},
        ]
        plan = metadata_document(
            current_ids=["FOCUS-TST-03", "DASH-TEST"],
            spotlight_ids=["FOCUS-LEGACY"],
            milestones=milestones,
            title="First selection",
        )
        (docs / "DEVELOPMENT_PLAN.md").write_text(plan, encoding="utf-8")
        now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        first = server.build_snapshot(overlay, now=now)
        self.assertEqual(first["current"]["title"], "First selection")
        self.assertEqual([task["id"] for task in first["current"]["tasks"]], ["FOCUS-TST-02..04", "DASH-TEST"])
        self.assertEqual([task["id"] for task in first["current"]["spotlight_tasks"]], ["FOCUS-TST-02..04"])
        task_milestones = {task["id"]: task["milestone"] for task in first["tasks"]}
        self.assertEqual(task_milestones["FOCUS-TST-02..04"], "exact")
        self.assertEqual(task_milestones["DASH-TEST"], "prefix")
        empty = next(item for item in first["milestones"] if item["id"] == "empty")
        self.assertEqual(empty["pending_count"], 0)
        self.assertEqual(empty["status"], "unknown")

        first_hashes = {item["file"]: item["sha256"] for item in first["sources"]}
        (docs / "backlog.md").write_text(FOCUS_BACKLOG + "\nA non-task source change.\n", encoding="utf-8")
        changed_plan = metadata_document(
            current_ids=["DASH-TEST"],
            spotlight_ids=["FOCUS-LEGACY"],
            milestones=milestones,
            title="Updated selection",
            outcome="Read again without restarting the server.",
        )
        (docs / "DEVELOPMENT_PLAN.md").write_text(changed_plan, encoding="utf-8")
        second = server.build_snapshot(overlay, now=now)
        second_hashes = {item["file"]: item["sha256"] for item in second["sources"]}
        self.assertEqual(second["current"]["title"], "Updated selection")
        self.assertEqual([task["id"] for task in second["current"]["tasks"]], ["DASH-TEST"])
        self.assertEqual(second["current"]["spotlight_tasks"][0]["id"], "FOCUS-TST-02..04")
        self.assertNotEqual(first_hashes["backlog.md"], second_hashes["backlog.md"])
        self.assertNotEqual(first_hashes["DEVELOPMENT_PLAN.md"], second_hashes["DEVELOPMENT_PLAN.md"])

    def test_task_linked_narrative_context_is_provenance_not_acceptance(self) -> None:
        overlay, docs, _ = self.make_overlay(FOCUS_BACKLOG)
        sources = {
            "TASKS.md": "# Task record\n\n## DASH-TEST bounded checkpoint\n\nEvidence remains under review for DASH-TEST.\n",
            "DECISIONS.md": "# Decisions\n\nDASH-TEST remains open under the existing decision.\n",
            "logbook/2026-10-10.md": "# Daily evidence\n\nDASH-TEST observation: a fixture, not acceptance.\n",
        }
        for filename, content in sources.items():
            (docs / filename).write_text(content, encoding="utf-8")
        snapshot = server.build_snapshot(
            overlay,
            now=datetime(2026, 10, 10, 12, tzinfo=timezone.utc),
        )
        task = next(row for row in snapshot["tasks"] if row["id"] == "DASH-TEST")
        self.assertEqual(task["state"], "Open")
        self.assertEqual(task["priority_rank"], 2)
        self.assertEqual(task["milestone"], "quality")
        context = {item["file"]: item for item in task["context"]}
        self.assertEqual(set(context), set(sources))
        self.assertIn("under review", context["TASKS.md"]["text"])
        self.assertIn("remains open", context["DECISIONS.md"]["text"])
        self.assertEqual(context["logbook/2026-10-10.md"]["source_date"], "2026-10-10")
        for filename, item in context.items():
            source_lines = sources[filename].splitlines()
            self.assertGreaterEqual(item["source_line"], 1)
            self.assertLessEqual(item["source_line"], len(source_lines))
            self.assertTrue(item["url"].endswith(f"#L{item['source_line']}"))
            self.assertTrue(item["sha256"])

    def test_only_fresh_active_receipts_are_current_and_pauses_do_not_add_active_time(self) -> None:
        overlay, docs, sessions = self.make_overlay(FOCUS_BACKLOG)
        (docs / "backlog.md").write_text(
            "| ID | State | Outcome | Remaining completion |\n|---|---|---|---|\n"
            "| DASH-TEST | Open | Current fixture | Verify |\n",
            encoding="utf-8",
        )
        now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)

        def stamp(delta: timedelta) -> str:
            return (now + delta).isoformat().replace("+00:00", "Z")

        def make_receipt(name: str, *, status: str = "active", task: str = "DASH-TEST",
                         role: str = "main", updated: timedelta = -timedelta(minutes=1),
                         active_since: str | None = None) -> dict[str, object]:
            started = stamp(-timedelta(hours=1))
            return {
                "session": name, "task_id": task, "milestone": "quality", "role": role,
                "objective": "Explicit report", "acceptance": "Operator review",
                "stop_condition": "Stop at the boundary", "status": status,
                "started_at": started, "updated_at": stamp(updated),
                "status_changed_at": started, "focus_changed_at": started,
                "active_since": active_since,
            }

        fixtures = {
            "active": make_receipt("active", active_since=stamp(-timedelta(minutes=10))),
            "legacy": make_receipt("legacy"),
            "blocked": make_receipt("blocked", status="blocked"),
            "review": make_receipt("review", status="awaiting-review"),
            "stale": make_receipt("stale", updated=-timedelta(minutes=16)),
            "orphan": make_receipt("orphan", task="REMOVED-01"),
            "completed": make_receipt("completed", status="completed"),
        }
        for name, payload in fixtures.items():
            (sessions / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
        snapshot = server.build_snapshot(overlay, now=now)
        current = {item["session"]: item for item in snapshot["focus"]}
        history = {item["session"]: item for item in snapshot["focus_history"]}
        self.assertEqual(set(current), {"active", "legacy"})
        self.assertEqual(current["active"]["classification"], "fresh-active")
        self.assertEqual(current["active"]["active_elapsed_seconds"], 600)
        self.assertEqual(current["active"]["wall_elapsed_seconds"], 3600)
        self.assertEqual(current["legacy"]["active_elapsed_seconds"], None)
        self.assertEqual(current["legacy"]["classification"], "fresh-active")
        self.assertEqual(
            {name: history[name]["classification"] for name in history},
            {"blocked": "blocked", "review": "awaiting-review", "stale": "stale",
             "orphan": "orphaned", "completed": "completed"},
        )
        self.assertEqual(snapshot["focus_counts"], {"total": 2, "main": 2, "supporting": 0})
        self.assertTrue(any("legacy.json has no active_since" in warning for warning in snapshot["warnings"]))
        self.assertFalse(any("active for more than 30 minutes" in warning for warning in snapshot["warnings"]))

    def test_legacy_active_heartbeat_starts_interval_at_explicit_update(self) -> None:
        overlay, _, _ = self.make_overlay(FOCUS_BACKLOG)
        set_at = "2026-10-10T12:00:00Z"
        update_at = "2026-10-10T12:00:12Z"
        def run_focus(arguments: list[str], reported_at: str) -> tuple[int, str]:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(focus, "BACKLOG_PATH", overlay / "docs" / "backlog.md"),
                mock.patch.object(focus, "PLAN_PATH", overlay / "docs" / "DEVELOPMENT_PLAN.md"),
                mock.patch.object(focus, "utc_now", return_value=reported_at),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = focus.main(arguments)
            return code, stderr.getvalue()

        result, error = run_focus(
            [
                "set", "--overlay", str(overlay), "--session", "agent_1",
                "--task", "FOCUS-TST-03", "--milestone", "quality", "--role", "main",
                "--objective", "Explicit legacy fixture", "--acceptance", "Review the report",
                "--stop-condition", "Stop at the fixture boundary",
            ],
            set_at,
        )
        self.assertEqual((result, error), (0, ""))
        receipt_path = overlay / "data/project-progress/sessions/agent_1.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        started_at = receipt["started_at"]
        for field in ("active_since", "status_changed_at", "focus_changed_at"):
            receipt.pop(field)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        result, error = run_focus(
            ["update", "--session", "agent_1", "--overlay", str(overlay), "--status", "active"],
            update_at,
        )
        self.assertEqual((result, error), (0, ""))
        repaired = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(repaired["started_at"], started_at)
        self.assertEqual(repaired["active_since"], update_at)
        snapshot = server.build_snapshot(
            overlay,
            now=datetime(2026, 10, 10, 12, 0, 15, tzinfo=timezone.utc),
        )
        projected = next(item for item in snapshot["focus"] if item["session"] == "agent_1")
        self.assertEqual(projected["active_elapsed_seconds"], 3)
        self.assertEqual(projected["wall_elapsed_seconds"], 15)

    def _source_request(self, overlay: Path, request_path: str) -> tuple[int, str]:
        handler_type = server._make_handler(overlay, server._RuntimeWarnings())
        handler = object.__new__(handler_type)
        handler.path = request_path
        handler.wfile = io.BytesIO()
        response: dict[str, int] = {}
        handler.send_response = lambda code, *args: response.setdefault("status", int(code))
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        handler.do_GET()
        return response["status"], handler.wfile.getvalue().decode("utf-8")

    def test_source_route_is_allowlisted_escaped_anchored_and_rejects_bad_queries(self) -> None:
        overlay, docs, _ = self.make_overlay("safe\n<script>alert('x') & more</script>\n")
        cases = overlay / "data" / "cases"
        cases.mkdir(parents=True)
        (cases / "private.md").write_text("CASE-CANARY", encoding="utf-8")

        code, page = self._source_request(overlay, "/source?file=backlog.md&line=2")
        self.assertEqual(code, HTTPStatus.OK)
        self.assertIn('<span id="L2" class="selected">', page)
        self.assertIn("&lt;script&gt;alert('x') &amp; more&lt;/script&gt;", page)
        self.assertNotIn("<script>alert", page)
        self.assertIsNone(server._read_allowlisted_document(docs, "cases/private.md")[0])

        for query, expected in (
            ("broken", HTTPStatus.BAD_REQUEST),
            ("file=backlog.md&extra=1", HTTPStatus.BAD_REQUEST),
            ("file=backlog.md&line=0", HTTPStatus.BAD_REQUEST),
            ("file=../data/cases/private.md", HTTPStatus.NOT_FOUND),
        ):
            status, body = self._source_request(overlay, "/source?" + query)
            self.assertEqual(status, expected)
            self.assertNotIn("CASE-CANARY", body)

    def test_host_validation_allows_only_loopback_or_specific_tailnet_address(self) -> None:
        self.assertEqual(server._validated_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(server._validated_host("100.95.7.78"), "100.95.7.78")
        for address in ("0.0.0.0", "192.168.1.4", "8.8.8.8", "::1"):
            with self.subTest(address=address), self.assertRaises(argparse.ArgumentTypeError):
                server._validated_host(address)


class CodexChronologyTests(DashboardTestCase):
    """Exercise the bounded native rollout adapter using isolated metadata fixtures."""

    NATIVE_SESSION = "01a12b43-c250-7ae0-9125-a374b2b3f40a"
    EXTERNAL_THREAD = "mcp:external-thread-alias"
    NOW = datetime(2026, 10, 11, 14, 5, tzinfo=timezone.utc)

    def _assistant_event(self, stamp: str, phase: str, text: str) -> dict[str, object]:
        return {
            "timestamp": stamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "phase": phase,
                "content": [{"type": "text", "text": text}],
            },
        }

    def _write_codex_source(
        self,
        overlay: Path,
        docs: Path,
        *,
        assistant_events: list[dict[str, object]],
        lifecycle_status: str = "completed",
        started_at: datetime = datetime(2026, 10, 11, 14, 0, tzinfo=timezone.utc),
        completed_at: datetime | None = datetime(2026, 10, 11, 14, 2, tzinfo=timezone.utc),
        malformed_tail: bool = False,
    ) -> tuple[Path, Path, Path]:
        session_root = self.root / "codex-sessions"
        session_root.mkdir(parents=True)
        expected_cwd = self.root / "advisor-worktree"
        expected_cwd.mkdir()
        rollout = session_root / f"rollout-2026-10-11T14-00-23-{self.NATIVE_SESSION}.jsonl"
        records: list[str] = [
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {"id": self.NATIVE_SESSION, "cwd": str(expected_cwd)},
                }
            ),
            *(json.dumps(event) for event in assistant_events),
            json.dumps(
                {
                    "timestamp": "2026-10-11T14:01:45Z",
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "output": "RAW_TOOL_OUTPUT_CANARY",
                    },
                }
            ),
        ]
        if malformed_tail:
            records.append("{malformed rollout record")
        rollout.write_text("\n".join(records) + "\n", encoding="utf-8")

        database = self.root / "thread-history.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "CREATE TABLE thread_turns ("
                "thread_id TEXT, turn_id TEXT, rollout_ordinal INTEGER, status TEXT, "
                "error_json TEXT, started_at REAL, completed_at REAL, duration_ms INTEGER, "
                "first_user_item_id TEXT, final_agent_item_id TEXT, rollout_byte_offset INTEGER, "
                "rollout_end_ordinal INTEGER, rollout_end_byte_offset INTEGER, root_turn_id TEXT)"
            )
            connection.execute(
                "INSERT INTO thread_turns "
                "(thread_id, turn_id, rollout_ordinal, status, started_at, completed_at, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self.NATIVE_SESSION,
                    "turn-fixture-1",
                    1,
                    lifecycle_status,
                    started_at.timestamp(),
                    completed_at.timestamp() if completed_at is not None else None,
                    120_000,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        progress_root = overlay / "data" / "project-progress"
        progress_root.mkdir(parents=True, exist_ok=True)
        config = {
            "schema_version": 1,
            "event_sources": [
                {
                    "type": "codex_rollout",
                    "path": str(rollout),
                    "task_id": "DASH-ALIAS",
                    "thread_id": self.EXTERNAL_THREAD,
                    "session": self.NATIVE_SESSION,
                    "kind": "main",
                    "milestone": "quality",
                    "title": "Native chronology fixture",
                    "expected_cwd": str(expected_cwd),
                    "allowed_session_root": str(session_root),
                    "lifecycle_db": str(database),
                }
            ],
        }
        (progress_root / "work-history-config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        return session_root, expected_cwd, database

    def _build_history(
        self,
        overlay: Path,
        docs: Path,
        *,
        session_root: Path,
        expected_cwd: Path,
        database: Path,
        focus_items: list[dict[str, object]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        task_map = {
            "DASH-TEST": {"task_id": "DASH-TEST", "milestone": "quality", "source_line": 4},
            "DASH-ALIAS": {"task_id": "DASH-TEST", "milestone": "quality", "source_line": 4},
            "DASH-SUPPORT": {"task_id": "DASH-SUPPORT", "milestone": "quality", "source_line": 5},
        }
        with (
            mock.patch.object(work_history, "CODEX_SESSION_ROOT", session_root),
            mock.patch.object(work_history, "CODEX_EXPECTED_CWD", expected_cwd),
            mock.patch.object(work_history, "CODEX_LIFECYCLE_DB", database),
        ):
            return work_history.build_work_history(
                overlay_root=overlay,
                docs_root=docs,
                documents={"backlog.md": "fixture backlog"},
                backlog_rows=[
                    {
                        "id": "DASH-TEST",
                        "outcome": "Baseline task record",
                        "state": "Open",
                        "section": "DASH-TEST",
                        "source_line": 4,
                    }
                ],
                source_metadata=[],
                task_map=task_map,
                focus=focus_items or [],
                focus_history=[],
                activity=[],
                now=now or self.NOW,
            )

    def test_native_lifecycle_and_agent_events_form_main_chronology_without_leaking_tool_output(self) -> None:
        overlay, docs, _ = self.make_overlay()
        assistant_events = [
            self._assistant_event(
                "2026-10-11T14:00:30Z", "commentary", "Reviewed the bounded fixture path."
            ),
            self._assistant_event(
                "2026-10-11T14:01:30Z", "final", "Latest sanitized progress summary."
            ),
            self._assistant_event(
                "2026-10-11T14:10:00Z", "final", "Future progress must be ignored."
            ),
        ]
        session_root, expected_cwd, database = self._write_codex_source(
            overlay, docs, assistant_events=assistant_events, malformed_tail=True
        )
        progress_root = overlay / "data" / "project-progress"
        (progress_root / "t3-work-observations.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "observations": [
                        {
                            "task_id": "DASH-SUPPORT",
                            "title": "Newer supporting item",
                            "objective": "Supporting fixture is contextual.",
                            "status": "completed",
                            "kind": "supporting",
                            "occurred_at": "2026-10-11T14:04:00Z",
                            "observed_at": "2026-10-11T14:04:00Z",
                            "thread_id": "fixture-support-thread",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        older_focus = [
            {
                "task_id": "DASH-TEST",
                "session": "older-running",
                "status": "running",
                "updated_at": "2026-10-11T13:59:00Z",
                "kind": "main",
            },
            {
                "task_id": "DASH-TEST",
                "session": "older-paused",
                "status": "paused",
                "updated_at": "2026-10-11T13:57:00Z",
                "kind": "main",
            },
        ]

        history = self._build_history(
            overlay,
            docs,
            session_root=session_root,
            expected_cwd=expected_cwd,
            database=database,
            focus_items=older_focus,
        )

        current = history["current_work"]
        self.assertIsInstance(current, dict)
        self.assertEqual(current["task_id"], "DASH-TEST")
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["occurred_at"], "2026-10-11T14:02:00.000Z")
        self.assertEqual(current["session"], self.NATIVE_SESSION)
        self.assertEqual(current["thread_id"], self.EXTERNAL_THREAD)
        self.assertEqual(current["turn_id"], "turn-fixture-1")
        self.assertIn("native thread turn completed_at", current["timestamp_basis"])

        work_items = history["work_items"]
        self.assertEqual(work_items[0]["task_id"], "DASH-SUPPORT")
        self.assertEqual(work_items[0]["kind"], "supporting")
        self.assertEqual(history["current_work"]["kind"], "main")
        self.assertEqual([item["status"] for item in history["active_now"]], ["running", "paused"])
        recent = history["recent_work"]
        self.assertEqual(recent[0]["summary"], "Latest sanitized progress summary.")
        self.assertEqual(recent[1]["summary"], "Reviewed the bounded fixture path.")
        self.assertTrue(any(item.get("session") == "older-running" for item in recent))
        self.assertTrue(any(item.get("session") == "older-paused" for item in recent))
        self.assertFalse(any(item.get("task_id") == "DASH-SUPPORT" for item in recent))
        self.assertFalse(any(item.get("summary") == "Future progress must be ignored." for item in recent))
        self.assertTrue(any("ignored malformed records" in item for item in history["work_history_sources"]["warnings"]))
        serialized = json.dumps(history, sort_keys=True)
        self.assertNotIn("RAW_TOOL_OUTPUT_CANARY", serialized)

    def test_completed_status_is_retained_when_assistant_event_follows_terminal_time(self) -> None:
        overlay, docs, _ = self.make_overlay()
        session_root, expected_cwd, database = self._write_codex_source(
            overlay,
            docs,
            assistant_events=[
                self._assistant_event(
                    "2026-10-11T14:04:00Z", "commentary", "Assistant commentary after terminal metadata."
                )
            ],
            completed_at=datetime(2026, 10, 11, 14, 1, tzinfo=timezone.utc),
        )
        history = self._build_history(
            overlay,
            docs,
            session_root=session_root,
            expected_cwd=expected_cwd,
            database=database,
        )
        current = history["current_work"]
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["occurred_at"], "2026-10-11T14:04:00.000Z")
        self.assertIn("after native turn completion metadata", current["timestamp_basis"])
        self.assertTrue(
            any(
                "assistant" in warning.casefold()
                and "completed lifecycle timestamp" in warning.casefold()
                for warning in history["work_history_sources"]["warnings"]
            )
        )

    def test_missing_lifecycle_database_keeps_status_unknown_and_reports_limited_source(self) -> None:
        overlay, docs, _ = self.make_overlay()
        session_root, expected_cwd, database = self._write_codex_source(
            overlay,
            docs,
            assistant_events=[
                self._assistant_event("2026-10-11T14:01:00Z", "commentary", "Bounded update remains visible.")
            ],
        )
        database.unlink()
        history = self._build_history(
            overlay,
            docs,
            session_root=session_root,
            expected_cwd=expected_cwd,
            database=database,
        )
        current = history["current_work"]
        self.assertEqual(current["status"], "unknown")
        self.assertEqual(current["summary"], "Bounded update remains visible.")
        self.assertTrue(
            any(
                "codex lifecycle metadata" in warning.casefold()
                and "turn status is unknown" in warning.casefold()
                for warning in history["work_history_sources"]["warnings"]
            )
        )
        source = next(
            item
            for item in history["work_history_sources"]["sources"]
            if item.get("type") == "codex_rollout"
        )
        self.assertTrue(source["available"])
        self.assertFalse(source["live_connection"])


class ExplanationFixtureTests(DashboardTestCase):
    TASK_ID = "DASH-EXPLAIN"
    OCCURRED_AT = "2026-10-11T15:00:00.000Z"

    def _snapshot(
        self,
        task_id: str = TASK_ID,
        occurred_at: str = OCCURRED_AT,
        *,
        context_text: str = "Fixture detail that can be interpreted.",
    ) -> dict[str, object]:
        return {
            "generated_at": "2026-10-11T15:01:00.000Z",
            "source_updated_at": "2026-10-11T14:59:00.000Z",
            "current_work": {
                "task_id": task_id,
                "title": "Fixture current item",
                "objective": "Interpret this recorded outcome.",
                "summary": "A bounded fixture source update.",
                "status": "completed",
                "occurred_at": occurred_at,
                "timestamp_basis": "recorded completion timestamp",
                "milestone": "quality",
                "kind": "main",
                "source": {
                    "file": "docs/TASKS.md",
                    "line": 42,
                    "label": "Task contract",
                },
                "session": "SESSION_SECRET_CANARY",
                "thread_id": "THREAD_SECRET_CANARY",
                "path": "/secret/clinical/path",
                "raw_payload": "RAW_PAYLOAD_SECRET_CANARY",
                "prompt": "PROMPT_SECRET_CANARY",
                "tool_output": "RAW_TOOL_SECRET_CANARY",
                "clinical_measurement": "CLINICAL_SECRET_CANARY",
            },
            "recent_work": [
                {
                    "task_id": task_id,
                    "title": "Earlier fixture item",
                    "objective": "Earlier recorded objective.",
                    "summary": "Earlier recorded summary.",
                    "status": "running",
                    "occurred_at": "2026-10-11T14:55:00.000Z",
                    "timestamp_basis": "recorded update timestamp",
                    "milestone": "quality",
                    "kind": "main",
                    "source": {
                        "file": "docs/logbook/2026-10-11.md",
                        "line": 8,
                        "label": "Dated evidence",
                    },
                    "session": "RECENT_SESSION_SECRET_CANARY",
                },
                {
                    "task_id": "OTHER-TASK",
                    "summary": "Other task must stay outside this packet.",
                    "occurred_at": "2026-10-11T14:58:00.000Z",
                    "raw_payload": "OTHER_RAW_SECRET_CANARY",
                },
            ],
            "tasks": [
                {
                    "id": task_id,
                    "priority": "Unprioritized",
                    "section": "Fixture tasks",
                    "outcome": "Record the bounded current item.",
                    "state": "Open",
                    "remaining": "Capture reviewed evidence.",
                    "acceptance": "Capture reviewed evidence.",
                    "boundary": "No runtime action is implied.",
                    "milestone": "quality",
                    "source": {
                        "file": "docs/TASKS.md",
                        "line": 42,
                        "url": "/source?path=docs/TASKS.md&line=42",
                        "path": "/private/source/root",
                    },
                    "context": [
                        {
                            "file": "docs/DECISIONS.md",
                            "source_line": 17,
                            "source_date": "2026-10-11",
                            "section": "Fixture scope",
                            "text": context_text,
                            "truncated": False,
                            "updated_at": "2026-10-11T14:59:00.000Z",
                            "raw_user_message": "USER_SECRET_CANARY",
                            "file_path": "/secret/context/path",
                        }
                    ],
                    "private_notes": "TASK_SECRET_CANARY",
                }
            ],
            "milestones": [
                {
                    "id": "quality",
                    "title": "Quality work",
                    "goal": "Prove bounded behavior.",
                    "status": "unknown",
                    "unreviewed_payload": "MILESTONE_SECRET_CANARY",
                }
            ],
            "sources": [
                {
                    "file": "docs/TASKS.md",
                    "updated_at": "2026-10-11T14:59:00.000Z",
                    "sha256": "fixture-source-hash",
                    "path": "/secret/source/path",
                    "raw": "RAW_SOURCE_SECRET_CANARY",
                }
            ],
            "warnings": ["WARNING_SECRET_CANARY"],
            "prompt": "SNAPSHOT_PROMPT_SECRET_CANARY",
        }

    def _manager(self, runner: object | None = None) -> item_explanation.ExplanationManager:
        return item_explanation.ExplanationManager(
            runner=runner,
            probe=lambda _model_id: {"available": True},
        )

    def _wait_for_job(
        self, manager: item_explanation.ExplanationManager, job_id: str
    ) -> dict[str, object]:
        import time

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            job = manager.get(job_id)
            if job is not None and job.get("status") in {"completed", "error"}:
                return job
            time.sleep(0.01)
        self.fail(f"explanation job {job_id} did not reach a terminal state")

    @contextlib.contextmanager
    def _serve_http(
        self,
        overlay: Path,
        snapshot: dict[str, object],
        manager: item_explanation.ExplanationManager,
    ):
        import threading
        from http.server import ThreadingHTTPServer

        with mock.patch.object(server, "build_snapshot", return_value=snapshot):
            handler = server._make_handler(
                overlay,
                server._RuntimeWarnings(),
                explanation_manager=manager,
            )
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            httpd.daemon_threads = True
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                yield httpd.server_address
            finally:
                httpd.shutdown()
                worker.join(timeout=2.0)
                httpd.server_close()

    def _http_request(
        self,
        address: tuple[str, int],
        method: str,
        target: str,
        body: dict[str, object] | bytes | None = None,
        headers: dict[str, str] | None = None,
        *,
        omit_origin: bool = False,
    ) -> tuple[int, object]:
        from http.client import HTTPConnection

        request_headers = {
            "Accept": "application/json",
            "Origin": f"http://{address[0]}:{address[1]}",
        }
        request_headers.update(headers or {})
        if omit_origin:
            request_headers.pop("Origin", None)
        request_body: bytes | None
        if isinstance(body, dict):
            request_body = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        else:
            request_body = body
        connection = HTTPConnection(address[0], address[1], timeout=2.0)
        try:
            connection.request(method, target, body=request_body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            if not raw:
                payload: object = {}
            else:
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = raw.decode("utf-8", errors="replace")
            return response.status, payload
        finally:
            connection.close()

    def test_context_packet_is_allowlisted_bounded_and_stale_safe(self) -> None:
        snapshot = self._snapshot(context_text="x" * 15_000)
        packet = item_explanation.capture_selected_context(
            snapshot, self.TASK_ID, self.OCCURRED_AT
        )
        self.assertEqual(
            set(packet),
            {"selected", "recent_same_task", "task", "milestone", "provenance"},
        )
        encoded = json.dumps(packet, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), 10 * 1024)
        self.assertIn("Interpret this recorded outcome.", encoded)
        self.assertIn("Earlier recorded summary.", encoded)
        for canary in (
            "SESSION_SECRET_CANARY",
            "THREAD_SECRET_CANARY",
            "RAW_PAYLOAD_SECRET_CANARY",
            "PROMPT_SECRET_CANARY",
            "RAW_TOOL_SECRET_CANARY",
            "CLINICAL_SECRET_CANARY",
            "RECENT_SESSION_SECRET_CANARY",
            "OTHER_RAW_SECRET_CANARY",
            "Other task must stay outside this packet.",
            "USER_SECRET_CANARY",
            "TASK_SECRET_CANARY",
            "MILESTONE_SECRET_CANARY",
            "RAW_SOURCE_SECRET_CANARY",
            "SNAPSHOT_PROMPT_SECRET_CANARY",
            "WARNING_SECRET_CANARY",
            "/secret/clinical/path",
            "/secret/context/path",
            "/secret/source/path",
            "/private/source/root",
        ):
            self.assertNotIn(canary, encoded)

        with self.assertRaises(item_explanation.StaleSelection) as stale:
            item_explanation.capture_selected_context(
                snapshot, self.TASK_ID, "2026-10-11T15:00:01.000Z"
            )
        self.assertEqual(stale.exception.code, "stale_selection")

    def test_cli_argv_pins_models_effort_and_no_tool_mcp_restrictions(self) -> None:
        workspace = self.root / "empty-model-workspace"
        workspace.mkdir()
        codex_features = item_explanation.parse_codex_features(
            "shell_tool stable false\n"
            "apps stable false\n"
            "multi_agent stable false\n"
            "removed_feature removed true\n"
        )
        self.assertEqual(set(codex_features), {"shell_tool", "apps", "multi_agent"})
        missing_required_features = item_explanation.parse_codex_features(
            "shell_tool stable true\nmulti_agent stable false\n"
        )
        self.assertIsNone(missing_required_features)
        with mock.patch.object(
            item_explanation,
            "_vetted_executable",
            return_value="/fixture/bin/model-cli",
        ):
            luna_argv = item_explanation.build_cli_argv(
                "luna-max", str(workspace), codex_features=codex_features
            )
            haiku_argv = item_explanation.build_cli_argv("haiku", str(workspace))
        self.assertEqual(
            luna_argv[luna_argv.index("--model") + 1], "gpt-6-luna"
        )
        self.assertIn("--ignore-user-config", luna_argv)
        self.assertIn("--ephemeral", luna_argv)
        self.assertIn("--skip-git-repo-check", luna_argv)
        self.assertIn("--sandbox", luna_argv)
        self.assertEqual(luna_argv[luna_argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(luna_argv[luna_argv.index("--cd") + 1], str(workspace))
        self.assertEqual(luna_argv[-1], "-")
        self.assertIn('model_reasoning_effort="max"', luna_argv)
        codex_configs = [
            luna_argv[index + 1]
            for index, value in enumerate(luna_argv[:-1])
            if value == "-c"
        ]
        self.assertIn("mcp_servers={}", codex_configs)
        self.assertIn('web_search="disabled"', codex_configs)
        disabled_features = {
            luna_argv[index + 1]
            for index, value in enumerate(luna_argv[:-1])
            if value == "--disable"
        }
        self.assertEqual(disabled_features, set(codex_features))

        self.assertEqual(
            haiku_argv[haiku_argv.index("--model") + 1], "claude-haiku-5-5"
        )
        self.assertEqual(haiku_argv[haiku_argv.index("--tools") + 1], "")
        self.assertIn("--restricted", haiku_argv)
        self.assertIn("--safe-mode", haiku_argv)
        self.assertEqual(
            haiku_argv[haiku_argv.index("--permission-mode") + 1], "dontAsk"
        )
        self.assertIn("--strict-mcp-config", haiku_argv)
        self.assertEqual(
            haiku_argv[haiku_argv.index("--mcp-config") + 1],
            '{"mcpServers":{}}',
        )
        self.assertIn("--no-session-persistence", haiku_argv)
        self.assertIn("--no-chrome", haiku_argv)
        self.assertEqual(
            haiku_argv[
                haiku_argv.index("--permission-prompts") + 1
            ],
            "none",
        )
        self.assertIn("--print", haiku_argv)
        self.assertEqual(
            haiku_argv[haiku_argv.index("--output-format") + 1], "text"
        )
        self.assertEqual(
            haiku_argv[haiku_argv.index("--input-format") + 1], "text"
        )

    def test_manager_reuses_one_job_for_duplicate_and_keeps_old_item_identity(self) -> None:
        import threading

        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        calls: list[tuple[str, object]] = []

        def runner(model_id: str, context: object) -> str:
            calls.append((model_id, context))
            if len(calls) == 1:
                started.set()
                release.wait(timeout=2.0)
            return "Plain explanation fixture result."

        manager = self._manager(runner)
        first_snapshot = self._snapshot()
        status, first = manager.submit(
            first_snapshot, self.TASK_ID, self.OCCURRED_AT, "luna-max"
        )
        self.assertEqual(status, HTTPStatus.ACCEPTED)
        first_id = first["job_id"]
        self.assertTrue(started.wait(timeout=1.0))

        duplicate_status, duplicate = manager.submit(
            first_snapshot, self.TASK_ID, self.OCCURRED_AT, "luna-max"
        )
        self.assertEqual(duplicate_status, HTTPStatus.ACCEPTED)
        self.assertEqual(duplicate["job_id"], first_id)
        self.assertTrue(duplicate["cached"])

        changed_snapshot = self._snapshot(
            "DASH-OTHER", "2026-10-11T15:02:00.000Z"
        )
        busy_status, busy = manager.submit(
            changed_snapshot,
            "DASH-OTHER",
            "2026-10-11T15:02:00.000Z",
            "haiku",
        )
        self.assertEqual(busy_status, HTTPStatus.CONFLICT)
        self.assertIn("error", busy)
        release.set()

        completed = self._wait_for_job(manager, first_id)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["task_id"], self.TASK_ID)
        self.assertEqual(completed["occurred_at"], self.OCCURRED_AT)
        self.assertEqual(completed["model"], "luna-max")
        self.assertEqual(completed["summary"], "Plain explanation fixture result.")
        self.assertIn("provenance", completed)

        refreshed_snapshot = self._snapshot()
        refreshed_snapshot["generated_at"] = "2026-10-11T15:05:00.000Z"
        refreshed_snapshot["source_updated_at"] = "2026-10-11T15:04:00.000Z"
        refreshed_snapshot["sources"][0]["updated_at"] = "2026-10-11T15:04:00.000Z"
        refreshed_snapshot["sources"][0]["sha256"] = "refreshed-source-hash"
        cached_status, cached = manager.submit(
            refreshed_snapshot, self.TASK_ID, self.OCCURRED_AT, "luna-max"
        )
        self.assertEqual(cached_status, HTTPStatus.ACCEPTED)
        self.assertEqual(cached["job_id"], first_id)
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["provenance"], completed["provenance"])
        self.assertEqual(len(calls), 1)

        changed_objective_snapshot = self._snapshot()
        changed_objective_snapshot["current_work"]["objective"] = (
            "Interpret a semantically different recorded outcome."
        )
        changed_objective_snapshot["tasks"][0]["outcome"] = (
            "Compare a distinct semantic result."
        )
        objective_status, objective_job = manager.submit(
            changed_objective_snapshot,
            self.TASK_ID,
            self.OCCURRED_AT,
            "luna-max",
        )
        self.assertEqual(objective_status, HTTPStatus.ACCEPTED)
        self.assertNotEqual(objective_job["job_id"], first_id)
        objective_completed = self._wait_for_job(manager, objective_job["job_id"])
        self.assertEqual(objective_completed["status"], "completed")
        self.assertEqual(len(calls), 2)

        next_status, next_job = manager.submit(
            changed_snapshot,
            "DASH-OTHER",
            "2026-10-11T15:02:00.000Z",
            "haiku",
        )
        self.assertEqual(next_status, HTTPStatus.ACCEPTED)
        self.assertNotEqual(next_job["job_id"], first_id)
        next_completed = self._wait_for_job(manager, next_job["job_id"])
        self.assertEqual(next_completed["task_id"], "DASH-OTHER")
        old_job = manager.get(first_id)
        self.assertEqual(old_job["task_id"], self.TASK_ID)
        self.assertEqual(old_job["occurred_at"], self.OCCURRED_AT)
        self.assertEqual(len(calls), 3)

    def test_error_output_is_sanitized_and_releases_the_global_job_slot(self) -> None:
        calls = 0

        def runner(_model_id: str, _context: object) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("RAW_TIMEOUT_SECRET_CANARY")
            return "Recovered fixture result."

        manager = self._manager(runner)
        overlay, _, _ = self.make_overlay()
        with self._serve_http(overlay, self._snapshot(), manager) as address:
            status, first = self._http_request(
                address,
                "POST",
                "/api/explanations",
                {
                    "task_id": self.TASK_ID,
                    "occurred_at": self.OCCURRED_AT,
                    "model": "luna-max",
                },
            )
            self.assertEqual(status, HTTPStatus.ACCEPTED)
            failed = self._wait_for_job(manager, first["job_id"])
            self.assertEqual(failed["status"], "error")
            browser_status, browser_job = self._http_request(
                address,
                "GET",
                f"/api/explanations/{first['job_id']}",
            )

        self.assertEqual(browser_status, HTTPStatus.OK)
        self.assertEqual(browser_job["status"], "error")
        self.assertNotIn("RAW_TIMEOUT_SECRET_CANARY", json.dumps(browser_job))
        self.assertIn("error", browser_job)

        next_task = "DASH-RECOVERED"
        next_time = "2026-10-11T15:03:00.000Z"
        next_status, next_job = manager.submit(
            self._snapshot(next_task, next_time), next_task, next_time, "haiku"
        )
        self.assertEqual(next_status, HTTPStatus.ACCEPTED)
        recovered = self._wait_for_job(manager, next_job["job_id"])
        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(recovered["summary"], "Recovered fixture result.")
        self.assertEqual(calls, 2)

    def test_local_runner_timeout_kills_process_and_joins_blocked_stdin_writer(self) -> None:
        import os
        import signal
        import subprocess
        import threading

        stdin_read, stdin_write = os.pipe()
        os.set_blocking(stdin_write, False)
        while True:
            try:
                os.write(stdin_write, b"x" * 4096)
            except BlockingIOError:
                break
        os.set_blocking(stdin_write, True)

        stdout_read, stdout_write = os.pipe()
        stderr_read, stderr_write = os.pipe()

        class FakeProcess:
            pid = 424242

            def __init__(self) -> None:
                self.stdin = os.fdopen(stdin_write, "wb", buffering=0)
                self.stdout = os.fdopen(stdout_read, "rb", buffering=0)
                self.stderr = os.fdopen(stderr_read, "rb", buffering=0)
                self.child_ends = {stdin_read, stdout_write, stderr_write}
                self.returncode: int | None = None
                self.terminated = threading.Event()

            def poll(self) -> int | None:
                return self.returncode

            def wait(self, timeout: float | None = None) -> int:
                if not self.terminated.wait(timeout):
                    raise subprocess.TimeoutExpired("fixture-cli", timeout)
                return self.returncode or 0

            def stop(self) -> None:
                self.returncode = -signal.SIGTERM
                for fd in tuple(self.child_ends):
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    self.child_ends.discard(fd)
                self.terminated.set()

            def cleanup(self) -> None:
                self.stop()
                for stream in (self.stdin, self.stdout, self.stderr):
                    try:
                        stream.close()
                    except OSError:
                        pass

        process = FakeProcess()
        self.addCleanup(process.cleanup)
        started_threads: list[threading.Thread] = []
        original_start = threading.Thread.start

        def track_thread_start(
            thread: threading.Thread, *args: object, **kwargs: object
        ) -> object:
            if thread.name.startswith("explanation-"):
                started_threads.append(thread)
            return original_start(thread, *args, **kwargs)

        killed_signals: list[int] = []

        def kill_group(pid: int, signum: int) -> None:
            self.assertEqual(pid, process.pid)
            killed_signals.append(signum)
            process.stop()

        with (
            mock.patch.object(
                item_explanation, "probe_model_capability", return_value={"available": True}
            ),
            mock.patch.object(
                item_explanation,
                "build_cli_argv",
                return_value=["/fixture/bin/claude"],
            ),
            mock.patch.object(item_explanation, "JOB_TIMEOUT_SECONDS", 0.05),
            mock.patch.object(item_explanation.subprocess, "Popen", return_value=process),
            mock.patch.object(os, "killpg", side_effect=kill_group),
            mock.patch.object(threading.Thread, "start", new=track_thread_start),
        ):
            with self.assertRaises(item_explanation.ExplanationError) as timeout:
                item_explanation.run_local_summary(
                    "haiku", {"selected": {"title": "Blocked stdin fixture"}}
                )

        self.assertEqual(timeout.exception.code, "model_timeout")
        self.assertEqual(timeout.exception.status_code, 504)
        self.assertIn(signal.SIGTERM, killed_signals)
        self.assertEqual(
            {thread.name for thread in started_threads},
            {"explanation-stdin", "explanation-stdout", "explanation-stderr"},
        )
        self.assertTrue(all(not thread.is_alive() for thread in started_threads))

    def test_http_gets_list_capabilities_without_starting_model_work(self) -> None:
        probe = mock.Mock(return_value={"available": True})
        runner = mock.Mock(return_value="Must not run from GET.")
        manager = item_explanation.ExplanationManager(runner=runner, probe=probe)
        overlay, _, _ = self.make_overlay()
        with self._serve_http(overlay, self._snapshot(), manager) as address:
            snapshot_status, snapshot_body = self._http_request(
                address, "GET", "/api/snapshot"
            )
            models_status, models_body = self._http_request(
                address, "GET", "/api/explanations/models"
            )

        self.assertEqual(snapshot_status, HTTPStatus.OK)
        self.assertEqual(models_status, HTTPStatus.OK)
        self.assertEqual(
            {model["id"] for model in models_body["models"]},
            {"luna-max", "haiku"},
        )
        self.assertTrue(all(model["available"] for model in models_body["models"]))
        self.assertEqual(probe.call_count, 2)
        runner.assert_not_called()

        unavailable_runner = mock.Mock(return_value="Must not substitute models.")
        missing_capability_features = item_explanation.parse_codex_features(
            "shell_tool stable true\nmulti_agent stable false\n"
        )
        self.assertIsNone(missing_capability_features)

        def missing_capability_probe(model_id: str) -> dict[str, object]:
            if model_id == "luna-max":
                return {
                    "available": missing_capability_features is not None,
                    "reason": (
                        "Safe isolation cannot be confirmed because required CLI "
                        "feature metadata is missing."
                    ),
                }
            return {"available": True}

        unavailable_manager = item_explanation.ExplanationManager(
            runner=unavailable_runner,
            probe=missing_capability_probe,
        )
        unavailable_models = unavailable_manager.models()["models"]
        luna = next(model for model in unavailable_models if model["id"] == "luna-max")
        self.assertFalse(luna["available"])
        self.assertIn("required", luna["reason"])
        rejected_status, rejected = unavailable_manager.submit(
            self._snapshot(), self.TASK_ID, self.OCCURRED_AT, "luna-max"
        )
        self.assertEqual(rejected_status, HTTPStatus.CONFLICT)
        self.assertIn("error", rejected)
        unavailable_runner.assert_not_called()

    def test_http_submit_and_rejects_stale_unsupported_unsafe_and_legacy_writes(self) -> None:
        runner = mock.Mock(return_value="HTTP fixture explanation.")
        manager = self._manager(runner)
        overlay, _, _ = self.make_overlay()
        with self._serve_http(overlay, self._snapshot(), manager) as address:
            request = {
                "task_id": self.TASK_ID,
                "occurred_at": self.OCCURRED_AT,
                "model": "luna-max",
            }
            accepted_status, accepted = self._http_request(
                address, "POST", "/api/explanations", request
            )
            self.assertEqual(accepted_status, HTTPStatus.ACCEPTED)
            job = self._wait_for_job(manager, accepted["job_id"])
            self.assertEqual(job["status"], "completed")
            fetched_status, fetched = self._http_request(
                address, "GET", f"/api/explanations/{accepted['job_id']}"
            )

            stale_status, stale = self._http_request(
                address,
                "POST",
                "/api/explanations",
                {**request, "task_id": "DASH-OTHER"},
            )
            unsupported_status, _ = self._http_request(
                address,
                "POST",
                "/api/explanations",
                {**request, "model": "unapproved-model"},
            )
            extra_field_status, _ = self._http_request(
                address,
                "POST",
                "/api/explanations",
                {**request, "prompt": "PROMPT_SECRET_CANARY"},
            )
            missing_origin_status, _ = self._http_request(
                address,
                "POST",
                "/api/explanations",
                request,
                omit_origin=True,
            )
            origin_status, _ = self._http_request(
                address,
                "POST",
                "/api/explanations",
                request,
                headers={"Origin": "https://untrusted.example"},
            )
            content_type_status, _ = self._http_request(
                address,
                "POST",
                "/api/explanations",
                b"{}",
                headers={"Content-Type": "text/plain"},
            )
            oversized_status, _ = self._http_request(
                address,
                "POST",
                "/api/explanations",
                b"x" * (server.MAX_EXPLANATION_BODY_BYTES + 1),
                headers={"Content-Type": "application/json"},
            )
            legacy_write_status, _ = self._http_request(
                address, "POST", "/api/snapshot", {}
            )

        self.assertEqual(fetched_status, HTTPStatus.OK)
        self.assertEqual(fetched["job_id"], accepted["job_id"])
        self.assertEqual(fetched["summary"], "HTTP fixture explanation.")
        self.assertEqual(stale_status, HTTPStatus.CONFLICT)
        self.assertEqual(stale["error"]["code"], "stale_selection")
        self.assertEqual(unsupported_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(extra_field_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(missing_origin_status, HTTPStatus.FORBIDDEN)
        self.assertEqual(origin_status, HTTPStatus.FORBIDDEN)
        self.assertEqual(content_type_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(oversized_status, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(legacy_write_status, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
