"""Host-only checks for the Step 6 run-local evidence summarizer."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from Testing.summarize_step6_evidence import main, summarize


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def make_bundle(root: Path, *, item_status="PASS", video_status="complete",
                command_exit=0, include_video=True, include_screenshot=True,
                workflow_claimed=True, cleanup=None, include_cleanup=True,
                include_manual_record=False):
    root.mkdir(parents=True, exist_ok=True)
    if include_screenshot:
        (root / "case.png").write_bytes(b"png evidence")
    (root / "slicer.log").write_text("run log\n", encoding="utf-8")
    video = root / "screen.mp4"
    if include_video:
        video.write_bytes(b"video evidence")
    report = {
        "status": "PASS",
        "full_workflow_claimed": workflow_claimed,
        "operator_verdict": None,
        "items": {"case opened": {"status": item_status, "reason": "recorded result"}},
        "screenshots": {"case": "case.png"},
        "case_source": "cases/example.mrb",
        "checkout": {"revision": "abc123"},
        "native_preflight": {"status": "PASS"},
    }
    manifest = {
        "status": video_status,
        "output_sha256": hashlib.sha256(video.read_bytes()).hexdigest() if include_video else "expected-hash",
        "exit_status": 0,
        "command_exit_status": command_exit,
        "ffmpeg_exit_status": 0,
    }
    write_json(root / "report.json", report)
    write_json(root / "video-manifest.json", manifest)
    if include_manual_record:
        (root / "step6-manual-record-probe.json").write_bytes(b"manual record json")
        (root / "step6-manual-record-probe.report.txt").write_bytes(b"manual record report")
    if include_cleanup:
        write_json(root / "cleanup.json", cleanup if cleanup is not None else {
            "owned_process_cleanup": True,
            "remaining_owned_processes": [],
        })
    return root / "report.json", root / "video-manifest.json", root / "cleanup.json"


class SummarizeStep6EvidenceTests(unittest.TestCase):
    def test_complete_report_keeps_verdict_pending_and_hashes_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            report, manifest, cleanup = make_bundle(root)
            output, complete = summarize(str(root), "report.json", "video-manifest.json", "cleanup.json",
                                         "session-1", "S6-LIVE-01")
            text = output.read_text(encoding="utf-8")

            self.assertTrue(complete)
            self.assertIn("**Whole-run evidence:** COMPLETE", text)
            self.assertIn("**Functional checklist:** PASS", text)
            self.assertIn("**Runner full-workflow claim:** true", text)
            self.assertIn("**Owned-process cleanup:** PASS", text)
            self.assertIn("exact owned PID/PGID checks", text)
            self.assertIn("**Operator verdict:** PENDING", text)
            self.assertIn("case opened | PASS | recorded result", text)
            self.assertIn("case.case_source", text)
            self.assertIn("checkout.revision", text)
            self.assertIn("native_preflight.status", text)
            for path in (root / "case.png", root / "slicer.log", root / "screen.mp4",
                         report, manifest, cleanup):
                self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), text)
            self.assertNotIn(hashlib.sha256(output.read_bytes()).hexdigest(), text)

    def test_not_run_check_never_claims_whole_run_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            make_bundle(root, item_status="NOT_RUN")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--report", "report.json", "--video-manifest", "video-manifest.json",
                               "--cleanup-report", "cleanup.json",
                               "--run-dir", str(root), "--session", "session-2", "--plan-gate", "gate"])

            self.assertEqual(result, 1)
            text = (root / "diagnostics.md").read_text(encoding="utf-8")
            self.assertIn("**Whole-run evidence:** INCOMPLETE", text)
            self.assertIn("**Functional checklist:** INCOMPLETE", text)
            self.assertIn("NOT_RUN", text)

    def test_fail_partial_recording_and_nonzero_command_exit_are_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            make_bundle(root, item_status="FAIL", video_status="partial", command_exit=1)
            output, complete = summarize(str(root), "report.json", "video-manifest.json", "cleanup.json",
                                         "session-3", "gate")
            text = output.read_text(encoding="utf-8")

            self.assertFalse(complete)
            self.assertIn("**Whole-run evidence:** INCOMPLETE", text)
            self.assertIn("**Functional checklist:** FAIL", text)
            self.assertIn("**Process/recording shutdown:** command exit 1", text)
            self.assertIn("video status partial", text)
            self.assertIn("command_exit_status is 1", text)

    def test_missing_video_and_screenshot_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            make_bundle(root, include_video=False, include_screenshot=False)
            output, complete = summarize(str(root), "report.json", "video-manifest.json", "cleanup.json",
                                         "session-4", "gate")
            text = output.read_text(encoding="utf-8")

            self.assertFalse(complete)
            self.assertIn("Screenshot reference | `case.png` | MISSING", text)
            self.assertIn("no local video matches", text)
            self.assertIn("no screenshot evidence is present", text)

    def test_rejects_inputs_outside_run_dir_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "run"
            report, manifest, cleanup = make_bundle(root)
            outside = base / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                summarize(str(root), str(outside), "video-manifest.json", "cleanup.json", "session", "gate")
            self.assertFalse((root / "diagnostics.md").exists())

            summarize(str(root), report.name, manifest.name, cleanup.name, "session", "gate")
            with self.assertRaises(FileExistsError):
                summarize(str(root), report.name, manifest.name, cleanup.name, "session", "gate")

    def test_unsafe_screenshot_reference_is_not_hashed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "run"
            report, manifest, cleanup = make_bundle(root)
            outside = base / "outside.png"
            outside.write_bytes(b"outside")
            value = json.loads(report.read_text(encoding="utf-8"))
            value["screenshots"] = {"case": "../outside.png"}
            write_json(report, value)

            output, complete = summarize(str(root), report.name, manifest.name, cleanup.name, "session", "gate")
            text = output.read_text(encoding="utf-8")

            self.assertFalse(complete)
            self.assertIn("Screenshot reference | `outside.png` | UNSAFE", text)
            self.assertNotIn(hashlib.sha256(outside.read_bytes()).hexdigest(), text)

    def test_workflow_and_cleanup_attestations_are_required(self):
        cases = (
            ("workflow false", {"workflow_claimed": False}, "runner full_workflow_claimed is not true"),
            ("cleanup missing", {"include_cleanup": False}, "cleanup report is missing"),
            ("cleanup false", {"cleanup": {"owned_process_cleanup": False,
                                             "remaining_owned_processes": []}},
             "owned_process_cleanup is not true"),
            ("process remains", {"cleanup": {"owned_process_cleanup": True,
                                               "remaining_owned_processes": ["slicer"]}},
             "remaining_owned_processes is not an empty list"),
        )
        for label, options, blocker in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "run"
                make_bundle(root, **options)
                output, complete = summarize(str(root), "report.json", "video-manifest.json",
                                             "cleanup.json", "session", "gate")
                text = output.read_text(encoding="utf-8")

                self.assertFalse(complete)
                self.assertIn("**Whole-run evidence:** INCOMPLETE", text)
                self.assertIn(blocker, text)

    def test_manual_record_artifacts_are_hashed_once_when_present(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            report, manifest, cleanup = make_bundle(root, include_manual_record=True)

            output, complete = summarize(str(root), report.name, manifest.name, cleanup.name,
                                         "session", "S6-LIVE-01")
            text = output.read_text(encoding="utf-8")

            self.assertTrue(complete)
            for name, kind in (
                ("step6-manual-record-probe.json", "Manual record JSON"),
                ("step6-manual-record-probe.report.txt", "Manual record report"),
            ):
                path = root / name
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertIn(digest, text)
                row = f"| {kind} | `{name}` | PRESENT | `{digest}` |"
                self.assertEqual(text.count(row), 1)
            self.assertEqual(text.count("| Runner report | `report.json`"), 1)
            self.assertEqual(text.count("| Video manifest | `video-manifest.json`"), 1)

    def test_absent_manual_record_outputs_do_not_complete_a_bounded_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "run"
            report, manifest, cleanup = make_bundle(root, workflow_claimed=False)

            output, complete = summarize(str(root), report.name, manifest.name, cleanup.name,
                                         "session", "S6-LIVE-01")
            text = output.read_text(encoding="utf-8")

            self.assertFalse(complete)
            self.assertIn("**Whole-run evidence:** INCOMPLETE", text)
            self.assertIn("runner full_workflow_claimed is not true", text)
            self.assertNotIn("Manual record JSON", text)
            self.assertNotIn("Manual record report", text)


if __name__ == "__main__":
    unittest.main()
