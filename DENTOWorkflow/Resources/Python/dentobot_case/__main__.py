"""Command-line access to explicit DentoCase inspection and catalog scans."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from .catalog import Catalog
from .inspection import inspect_package


def _emit(value: object) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m dentobot_case")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="validate one package without catalog writes")
    inspect.add_argument("path")

    scan = commands.add_parser("scan", help="scan explicitly selected package roots")
    scan.add_argument("--database", required=True)
    scan.add_argument("roots", nargs="+")

    list_command = commands.add_parser("list", help="list catalogued cases and locations")
    list_command.add_argument("--database", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            _emit(inspect_package(args.path).to_dict())
            return 0
        with Catalog(args.database) as catalog:
            if args.command == "scan":
                results = catalog.scan(args.roots)
                _emit(results)
                failures = sum(
                    item.get("status") in {"Error", "Conflict"} for item in results
                )
                if failures:
                    print(
                        f"dentobot_case: scan recorded {failures} error or conflict result(s).",
                        file=sys.stderr,
                    )
                    return 1
                return 0
            _emit(catalog.list_cases())
            return 0
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(f"dentobot_case: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
