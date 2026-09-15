"""Run the exact Stage 6 smoke once per required FDI target.

This is a serialized launcher.  It reuses the existing Slicer runner so each
target gets an isolated Slicer process, diagnostic JSON, saved .dentocase, and
save/reopen check.  It never invents a missing upstream case.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys


REQUIRED_TARGETS = ("31", "32", "11", "12", "13", "14")
PASS_MARKER = "DENTOBOT_STEP65_EXACT_CASE_PASS"


def _fdi_key(value: object) -> str:
    text = str(value or "").strip().upper()
    return text[3:] if text.startswith("FDI") else text


def load_case_manifest(path: str | Path) -> dict[str, Path]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    targets = payload.get("targets", payload) if isinstance(payload, dict) else None
    if not isinstance(targets, dict):
        raise ValueError("Stage 6 target manifest must contain a targets object")
    result: dict[str, Path] = {}
    for raw_fdi, raw_case in targets.items():
        fdi = _fdi_key(raw_fdi)
        if fdi in result:
            raise ValueError(f"duplicate Stage 6 target FDI: {fdi}")
        source = (
            raw_case.get("source")
            if isinstance(raw_case, dict)
            else raw_case
        )
        if not source:
            raise ValueError(f"target FDI {fdi} has no source case")
        result[fdi] = Path(str(source))
    missing = [fdi for fdi in REQUIRED_TARGETS if fdi not in result]
    extra = [fdi for fdi in result if fdi not in REQUIRED_TARGETS]
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(f"FDI{fdi}" for fdi in missing))
        if extra:
            details.append("unexpected " + ", ".join(f"FDI{fdi}" for fdi in extra))
        raise ValueError("invalid Stage 6 target manifest: " + "; ".join(details))
    absent = [f"FDI{fdi}: {path}" for fdi, path in result.items() if not path.is_file()]
    if absent:
        raise FileNotFoundError("missing reviewed input case(s): " + "; ".join(absent))
    return {fdi: result[fdi] for fdi in REQUIRED_TARGETS}


def _report_after_marker(stdout: str) -> dict[str, object] | None:
    marker_index = stdout.rfind(PASS_MARKER)
    if marker_index < 0:
        return None
    tail = stdout[marker_index + len(PASS_MARKER):].lstrip()
    try:
        report, _end = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError:
        return None
    return report if isinstance(report, dict) else None


def smoke_report_issues(report: dict[str, object] | None, fdi: str) -> tuple[str, ...]:
    """Require the saved-case smoke evidence that this matrix publishes."""

    if not isinstance(report, dict):
        return ("missing structured Stage 6 smoke report",)
    issues = []
    if _fdi_key(report.get("targetFdi")) != str(fdi):
        issues.append("reported target FDI does not match the requested target")
    bore = report.get("guideBore")
    if not isinstance(bore, dict) or any(
        not isinstance(bore.get(field), (int, float))
        or float(bore[field]) < 2.0
        for field in ("channelDiameterMm", "sleeveInnerDiameterMm")
    ):
        issues.append("report lacks a 2.0 mm trajectory-guide bore")
    for field in (
        "guarded_preview_complete",
        "guarded_return_home_complete",
        "repeat_guarded_preview_complete",
    ):
        if report.get(field) is not True:
            issues.append(f"report lacks {field}")
    for field in (
        "final_target_position_error_mm",
        "repeat_final_target_position_error_mm",
    ):
        value = report.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            issues.append(f"report lacks finite {field}")
    saved_case = report.get("savedCase")
    if not isinstance(saved_case, dict) or saved_case.get("reopened") is not True:
        issues.append("report lacks saved-case reopen evidence")
    elif _fdi_key(saved_case.get("restoredFdi")) != str(fdi):
        issues.append("reopened case target FDI does not match")
    elif (
        not isinstance(saved_case.get("restoredPlanSelection"), dict)
        or saved_case["restoredPlanSelection"].get("state") != "locked"
    ):
        issues.append("reopened case did not retain the locked route")
    if report.get("hardware_execution_enabled") is not False:
        issues.append("report does not prove hardware execution stayed disabled")
    return tuple(issues)


def _runner_command(slicer: str, module_root: str, runner: str) -> list[str]:
    return [
        "xvfb-run",
        "-a",
        slicer,
        "--no-splash",
        "--additional-module-paths",
        module_root,
        "--python-script",
        runner,
    ]


def run_matrix(
    manifest: str | Path,
    output_dir: str | Path,
    *,
    slicer: str,
    module_root: str,
    runner: str,
    timeout_sec: int,
    dry_run: bool = False,
) -> dict[str, object]:
    cases = load_case_manifest(manifest)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    base_command = _runner_command(slicer, module_root, runner)
    results = []
    for fdi, source in cases.items():
        target_root = output_root / f"FDI{fdi}"
        target_root.mkdir(parents=True, exist_ok=True)
        saved_case = target_root / f"dentobot-stage6-FDI{fdi}.dentocase"
        diagnostic = target_root / f"dentobot-stage6-FDI{fdi}-diagnostic.json"
        log_path = target_root / "slicer.log"
        environment = os.environ.copy()
        for name in (
            "DENTOBOT_PLAN_ONLY",
            "DENTOBOT_GOAL1_ONLY",
            "DENTOBOT_AUDIT_ACTUAL_CONTACT_ONLY",
            "DENTOBOT_FOCUSED_STAGE3_DIAG",
            "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE",
            "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW",
        ):
            environment.pop(name, None)
        environment.update(
            {
                "DENTOBOT_EXACT_CASE": str(source),
                "DENTOBOT_EXPECTED_FDI": fdi,
                "DENTOBOT_OUTPUT_CASE": str(saved_case),
                "DENTOBOT_REOPEN_SAVED_CASE": "1",
                "DENTOBOT_LOCK_SELECTED_ROUTE": "1",
                "DENTOBOT_DIAGNOSTIC_OUTPUT": str(diagnostic),
            }
        )
        command = list(base_command)
        result: dict[str, object] = {
            "fdi": fdi,
            "source": str(source),
            "command": command,
            "saved_case": str(saved_case),
            "diagnostic": str(diagnostic),
            "log": str(log_path),
        }
        if dry_run:
            result["status"] = "not-run"
            results.append(result)
            continue
        try:
            completed = subprocess.run(
                command,
                env=environment,
                text=True,
                capture_output=True,
                timeout=max(1, int(timeout_sec)),
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            log_path.write_text(
                stdout + "\n--- STDERR ---\n" + stderr,
                encoding="utf-8",
            )
            report = _report_after_marker(stdout)
            report_issues = smoke_report_issues(report, fdi)
            result.update(
                {
                    "status": (
                        "passed"
                        if completed.returncode == 0
                        and PASS_MARKER in stdout
                        and saved_case.is_file()
                        and diagnostic.is_file()
                        and not report_issues
                        else "failed"
                    ),
                    "returncode": completed.returncode,
                    "pass_marker": PASS_MARKER in stdout,
                    "saved_case_exists": saved_case.is_file(),
                    "diagnostic_exists": diagnostic.is_file(),
                    "report": report,
                    "report_issues": list(report_issues),
                }
            )
        except subprocess.TimeoutExpired as exc:
            log_path.write_text(
                (exc.stdout or "")
                + "\n--- STDERR ---\n"
                + (exc.stderr or "")
                + "\nTIMEOUT\n",
                encoding="utf-8",
            )
            result.update({"status": "timeout", "returncode": None})
        results.append(result)
    summary = {
        "schemaVersion": "1.0",
        "requiredTargets": [f"FDI{fdi}" for fdi in REQUIRED_TARGETS],
        "manifest": str(Path(manifest)),
        "outputDir": str(output_root),
        "dryRun": bool(dry_run),
        "results": results,
    }
    (output_root / "stage6-target-matrix-report.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="JSON target-to-case map")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--slicer",
        default=os.environ.get(
            "DENTOBOT_SLICER_BIN",
            "/opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer",
        ),
    )
    parser.add_argument(
        "--module-root",
        default="/workspace/ros2_ws/src/DentoBot/DENTOWorkflow",
    )
    parser.add_argument(
        "--runner",
        default="/workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_step65_exact_case_smoke.py",
    )
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = run_matrix(
            args.manifest,
            args.output_dir,
            slicer=args.slicer,
            module_root=args.module_root,
            runner=args.runner,
            timeout_sec=args.timeout_sec,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"DENTOBOT_STAGE6_TARGET_MATRIX_BLOCKED: {exc}", file=sys.stderr)
        return 2
    passed = all(result.get("status") == "passed" for result in summary["results"])
    print(
        "DENTOBOT_STAGE6_TARGET_MATRIX_PASS"
        if passed and not args.dry_run
        else "DENTOBOT_STAGE6_TARGET_MATRIX_DRY_RUN"
        if args.dry_run
        else "DENTOBOT_STAGE6_TARGET_MATRIX_FAILED",
        flush=True,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    return 0 if passed or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
