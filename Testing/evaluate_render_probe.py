"""Judge one render-probe log against the workstation graphics acceptance.

Reads the last ``DENTOBOT_RENDER_FRAME_PROBE {json}`` line written by
``run_dentobot_render_frame_probe.py`` (via ``launch-dentoworkflow.bash
--render-probe``) and writes a verdict. Exit 0 PASS, 1 FAIL, 2 no report.
"""

import argparse
import json
import sys
from pathlib import Path


REPORT_PREFIX = "DENTOBOT_RENDER_FRAME_PROBE "
# >=60 FPS target. 17.0 ms (not 16.7) keeps a VSync-locked 60 Hz display,
# whose intervals jitter around 16.67 ms, from failing on timer noise.
MAX_MEDIAN_INTERVAL_MS = 17.0


def find_report(text):
    report = None
    for line in text.splitlines():
        index = line.find(REPORT_PREFIX)
        if index < 0:
            continue
        try:
            report = json.loads(line[index + len(REPORT_PREFIX):])
        except json.JSONDecodeError:
            continue
    return report


def evaluate(report, graphics_mode):
    renderer = report.get("renderer") or {}
    context = report.get("render_context") or {}
    render = report.get("render") or {}
    renderer_text = " ".join(
        str(renderer.get(key) or "") for key in ("renderer_string", "vendor_string")
    )
    median = render.get("median_interval_ms")
    checks = {
        "probe_complete": report.get("status") == "complete",
        "case_loaded": report.get("case_loaded") is True,
        "real_display": context.get("headless_detected") is False,
        "hardware_renderer": bool(renderer.get("renderer_string"))
        and context.get("software_renderer_detected") is False,
        "median_interval_within_60fps": median is not None
        and float(median) <= MAX_MEDIAN_INTERVAL_MS,
    }
    if graphics_mode == "nvidia":
        checks["nvidia_renderer"] = "nvidia" in renderer_text.lower()
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--graphics-mode", required=True)
    parser.add_argument("--launch-status", type=int, default=None)
    parser.add_argument("--case", default=None)
    parser.add_argument("--source-head", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    report = find_report(args.log.read_text(encoding="utf-8", errors="replace"))
    verdict = {
        "graphics_mode": args.graphics_mode,
        "launch_status": args.launch_status,
        "case": args.case,
        "source_head": args.source_head,
        "max_median_interval_ms": MAX_MEDIAN_INTERVAL_MS,
        "probe_log": str(args.log),
    }
    if report is None:
        verdict.update(status="NO_REPORT", checks={})
        exit_code = 2
    else:
        checks = evaluate(report, args.graphics_mode)
        render = report.get("render") or {}
        renderer = report.get("renderer") or {}
        verdict.update(
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            renderer_string=renderer.get("renderer_string"),
            vendor_string=renderer.get("vendor_string"),
            opengl_version=renderer.get("opengl_version"),
            median_interval_ms=render.get("median_interval_ms"),
            p95_interval_ms=render.get("p95_interval_ms"),
            event_rate_hz=render.get("event_rate_hz"),
            missed_16_7ms_budget_percent=render.get("missed_16_7ms_budget_percent"),
            render_window_size_pixels=report.get("render_window_size_pixels"),
            qt_heartbeat_median_interval_ms=(report.get("qt_heartbeat") or {}).get(
                "median_interval_ms"
            ),
            render_context=report.get("render_context"),
        )
        exit_code = 0 if verdict["status"] == "PASS" else 1
    if args.output is not None:
        args.output.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"DENTOBOT_RENDER_ACCEPTANCE {verdict['status']}", flush=True)
    for name, passed in verdict["checks"].items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}", flush=True)
    if report is not None:
        print(f"  renderer: {verdict['renderer_string']}", flush=True)
        print(
            f"  median {verdict['median_interval_ms']} ms, p95 {verdict['p95_interval_ms']} ms, "
            f"rate {verdict['event_rate_hz']} Hz",
            flush=True,
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
