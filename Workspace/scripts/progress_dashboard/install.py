#!/usr/bin/env python3
"""Render or install the per-user DentoBot progress dashboard service."""

from __future__ import annotations

import argparse
import ipaddress
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_OVERLAY = Path("/home/tarun/dentobot")
SERVICE_NAME = "dentobot-progress.service"
MANAGED_MARKER = "# Managed by PROGRESS-DASH-01 installer."
TAILSCALE_IPV4 = ipaddress.ip_network("100.64.0.0/10")


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1024 and 65535")
    return port


def systemd_quote(value: str | Path) -> str:
    """Quote one ExecStart argument for a systemd unit, without a shell."""
    text = str(value)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        raise ValueError("systemd arguments cannot contain control characters")
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("%", "%%")
        .replace("$", "$$")
    )
    return f'"{escaped}"'


def detect_tailscale_ipv4() -> str:
    executable = shutil.which("tailscale")
    if executable is None:
        raise RuntimeError("tailscale was requested but the tailscale command is unavailable")
    try:
        result = subprocess.run(
            [executable, "ip", "-4"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"could not read the Tailscale IPv4 address: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"tailscale ip -4 failed: {detail}")

    addresses = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(addresses) != 1:
        raise RuntimeError("tailscale ip -4 did not return exactly one IPv4 address")
    try:
        address = ipaddress.ip_address(addresses[0])
    except ValueError as exc:
        raise RuntimeError("tailscale ip -4 returned an invalid address") from exc
    if not isinstance(address, ipaddress.IPv4Address) or address not in TAILSCALE_IPV4:
        raise RuntimeError("tailscale ip -4 did not return an address in 100.64.0.0/10")
    return str(address)


def build_unit(overlay: Path, port: int, tailscale_ip: str | None) -> str:
    server_path = Path(__file__).resolve().with_name("server.py")
    executable_path = Path(sys.executable).resolve()
    overlay_path = overlay.expanduser().resolve()
    command = [
        str(executable_path),
        str(server_path),
        "--overlay",
        str(overlay_path),
        "--host",
        "127.0.0.1",
    ]
    if tailscale_ip is not None:
        command.extend(("--host", tailscale_ip))
    command.extend(("--port", str(port)))
    exec_start = " ".join(systemd_quote(argument) for argument in command)
    return (
        f"{MANAGED_MARKER}\n"
        "[Unit]\n"
        "Description=DentoBot project progress dashboard\n"
        "After=network.target\n"
        "Wants=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME


def write_unit(path: Path, unit: str) -> None:
    if path.is_symlink():
        raise RuntimeError(f"refusing to replace symlink at {path}")
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"cannot inspect existing service {path}: {exc}") from exc
        if MANAGED_MARKER not in existing:
            raise RuntimeError(
                f"refusing to overwrite existing unrelated service file {path}"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{SERVICE_NAME}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(unit)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def run_systemctl(*arguments: str) -> None:
    try:
        result = subprocess.run(
            ["systemctl", "--user", *arguments], check=False, text=True
        )
    except OSError as exc:
        raise RuntimeError(f"could not run systemctl --user: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"systemctl --user {' '.join(arguments)} failed with exit {result.returncode}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the local per-user progress dashboard service."
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        default=DEFAULT_OVERLAY,
        help=f"Ubuntu overlay root (default: {DEFAULT_OVERLAY})",
    )
    parser.add_argument("--port", type=valid_port, default=8766)
    parser.add_argument(
        "--tailscale",
        action="store_true",
        help="also bind to the current Tailscale IPv4 address from `tailscale ip -4`",
    )
    parser.add_argument(
        "--print-only",
        "--dry-run",
        action="store_true",
        help="print the exact unit without writing it or calling systemctl",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        tailscale_ip = detect_tailscale_ipv4() if args.tailscale else None
        unit = build_unit(args.overlay, args.port, tailscale_ip)
        destination = unit_path()
        print(f"Unit path: {destination}")
        print(unit, end="")
        if args.print_only:
            return 0
        write_unit(destination, unit)
        run_systemctl("daemon-reload")
        run_systemctl("enable", SERVICE_NAME)
        run_systemctl("restart", SERVICE_NAME)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"progress-dashboard installer: {exc}", file=sys.stderr)
        return 2
    print(f"Enabled user service {SERVICE_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
