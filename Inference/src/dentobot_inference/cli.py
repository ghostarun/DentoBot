"""Command-line interface used by Slicer's asynchronous process adapters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from dentobot_inference.health import collect_health


def _emit_json(document: dict[str, Any]) -> None:
    print(json.dumps(document, separators=(",", ":"), sort_keys=True), flush=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dentobot-inference")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser(
        "health",
        help="Report interpreter, package, and compute-device health.",
    )
    health_parser.add_argument("--json", action="store_true", dest="as_json")
    health_parser.add_argument("--require-cuda", action="store_true")
    health_parser.add_argument(
        "--require-device",
        choices=("cpu", "cuda:0"),
        help="Require the explicitly selected segmentation device.",
    )

    roundtrip_parser = subparsers.add_parser(
        "roundtrip",
        help="Rewrite and validate a NIfTI image.",
    )
    roundtrip_parser.add_argument("--input", type=Path, required=True)
    roundtrip_parser.add_argument("--output", type=Path, required=True)
    roundtrip_parser.add_argument("--result-json", type=Path, required=True)
    roundtrip_parser.add_argument("--run-id", required=True)

    teeth_parser = subparsers.add_parser(
        "segment-teeth",
        help="Run TotalSegmentator teeth segmentation on an explicit device.",
    )
    teeth_parser.add_argument("--input", type=Path, required=True)
    teeth_parser.add_argument("--output", type=Path, required=True)
    teeth_parser.add_argument("--result-json", type=Path, required=True)
    teeth_parser.add_argument("--run-id", required=True)
    teeth_parser.add_argument(
        "--device",
        choices=("cpu", "cuda:0"),
        default="cuda:0",
        help="Execution device. CPU use is explicit and never a fallback.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "health":
        report = collect_health(
            require_cuda=args.require_cuda,
            require_device=args.require_device,
        )
        if args.as_json:
            _emit_json(report)
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "ok" else 2

    if args.command == "roundtrip":
        from dentobot_inference.roundtrip import run_roundtrip

        report = run_roundtrip(
            input_path=args.input,
            output_path=args.output,
            result_json_path=args.result_json,
            run_id=args.run_id,
            progress_callback=_emit_json,
        )
        _emit_json(report)
        return 0 if report["status"] == "ok" else 3

    if args.command == "segment-teeth":
        from dentobot_inference.segmentation import run_teeth_segmentation

        report = run_teeth_segmentation(
            input_path=args.input,
            output_path=args.output,
            result_json_path=args.result_json,
            run_id=args.run_id,
            device=args.device,
            progress_callback=_emit_json,
        )
        _emit_json(report)
        return 0 if report["status"] == "ok" else 4

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
