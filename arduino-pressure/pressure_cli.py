"""Portable serial defaults so this folder can run on another Windows or Ubuntu PC.

Sensing only. Does not command a robot or drill.
"""

from __future__ import annotations

import argparse
import os
import sys


def default_serial_port() -> str:
    env = os.environ.get("PRESSURE_PORT", "").strip()
    if env:
        return env
    if sys.platform.startswith("win"):
        return "COM3"
    return "/dev/ttyACM0"


def default_baud() -> int:
    env = os.environ.get("PRESSURE_BAUD", "").strip()
    if env:
        return int(env)
    return 460800


def parse_monitor_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "DENTOBOT pneumatic pressure monitor. Sensing only; "
            "does not command a robot or drill."
        )
    )
    parser.add_argument(
        "--port",
        default=default_serial_port(),
        help=(
            "Serial device. Default: PRESSURE_PORT, else COM3 on Windows "
            "or /dev/ttyACM0 on Linux."
        ),
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=default_baud(),
        help="Serial baud. Default: PRESSURE_BAUD or 460800.",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="Print serial ports and exit without opening the monitor.",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def list_serial_ports() -> None:
    from serial.tools import list_ports

    found = list(list_ports.comports())
    if not found:
        print("No serial ports found.")
        return
    for item in found:
        extra = f"  [{item.hwid}]" if item.hwid else ""
        print(f"{item.device}\t{item.description}{extra}")


def apply_monitor_cli(argv: list[str] | None = None) -> tuple[str, int]:
    args = parse_monitor_args(argv)
    if args.list_ports:
        list_serial_ports()
        raise SystemExit(0)
    return args.port, args.baud
