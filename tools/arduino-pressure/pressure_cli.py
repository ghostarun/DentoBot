"""CLI defaults for pressure_monitor.py (serial or WiFi TCP).

Sensing only. Does not command a robot or drill.
"""

from __future__ import annotations

import argparse
import os
import sys

from pressure_transport import PressureLink, open_pressure_link


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


def default_wifi_host() -> str:
    return os.environ.get("PRESSURE_WIFI_HOST", "").strip()


def default_wifi_port() -> int:
    env = os.environ.get("PRESSURE_WIFI_PORT", "").strip()
    if env:
        return int(env)
    return 8765


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
            "Serial device (USB). Default: PRESSURE_PORT, else COM3 on Windows "
            "or /dev/ttyACM0 on Linux."
        ),
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=default_baud(),
        help="Serial baud. Default: PRESSURE_BAUD or 460800. Ignored with --wifi.",
    )
    parser.add_argument(
        "--wifi",
        action="store_true",
        help=(
            "Use WiFi TCP to Arduino UNO R4 WiFi (same line protocol as USB). "
            "Requires --wifi-host or PRESSURE_WIFI_HOST."
        ),
    )
    parser.add_argument(
        "--wifi-host",
        default=default_wifi_host(),
        metavar="IP",
        help="Arduino IP when using --wifi. Default: PRESSURE_WIFI_HOST.",
    )
    parser.add_argument(
        "--wifi-port",
        type=int,
        default=default_wifi_port(),
        help="TCP port on the board. Default: PRESSURE_WIFI_PORT or 8765.",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="Print serial ports and exit without opening the monitor.",
    )
    args, _unknown = parser.parse_known_args(argv)
    if not args.wifi and (args.wifi_host or "").strip():
        args.wifi = True
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
    """Legacy helper: port and baud only (serial mode)."""
    args = parse_monitor_args(argv)
    if args.list_ports:
        list_serial_ports()
        raise SystemExit(0)
    return args.port, args.baud


def connect_monitor_link(argv: list[str] | None = None) -> PressureLink:
    args = parse_monitor_args(argv)
    if args.list_ports:
        list_serial_ports()
        raise SystemExit(0)
    return open_pressure_link(
        args.port,
        args.baud,
        use_wifi=args.wifi,
        wifi_host=args.wifi_host,
        wifi_port=args.wifi_port,
    )
