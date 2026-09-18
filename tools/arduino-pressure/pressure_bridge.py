#!/usr/bin/env python3
"""USB serial to TCP bridge for the pressure firmware line protocol.

Use when the Arduino cannot join campus WPA2-Enterprise (LDAP/eduroam): the
laptop handles campus WiFi login; the UNO stays on USB. Point
pressure_monitor.py at this machine with --wifi --wifi-host <laptop-ip>.

Sensing only. Does not command a robot or drill.
"""

from __future__ import annotations

import argparse
import select
import socket
import sys
import time

import serial

from pressure_cli import default_baud, default_serial_port, list_serial_ports


def parse_listen(value: str) -> tuple[str, int]:
    host, port_text = value.rsplit(":", 1)
    return host, int(port_text)


def relay_loop(ser: serial.Serial, client: socket.socket) -> None:
    client.setblocking(False)
    pending_tcp = b""
    while True:
        try:
            serial_ready, _, _ = select.select([ser], [], [], 0.05)
        except (ValueError, OSError):
            break
        if serial_ready:
            try:
                chunk = ser.read(ser.in_waiting or 1)
            except (OSError, serial.SerialException):
                break
            if chunk:
                try:
                    client.sendall(chunk)
                except OSError:
                    break
        try:
            chunk = client.recv(65536)
        except BlockingIOError:
            chunk = b""
        except OSError:
            break
        if chunk == b"":
            break
        pending_tcp += chunk
        while b"\n" in pending_tcp or b"\r" in pending_tcp:
            for sep in (b"\n", b"\r"):
                if sep in pending_tcp:
                    line, pending_tcp = pending_tcp.split(sep, 1)
                    if line:
                        ser.write(line + b"\n")
                    break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bridge USB pressure firmware to TCP (campus WiFi / LDAP workaround)."
        )
    )
    parser.add_argument("--port", default=default_serial_port())
    parser.add_argument("--baud", type=int, default=default_baud())
    parser.add_argument(
        "--listen",
        default="0.0.0.0:8765",
        help="TCP listen address (default 0.0.0.0:8765).",
    )
    parser.add_argument("--list-ports", action="store_true")
    args = parser.parse_args(argv)

    if args.list_ports:
        list_serial_ports()
        return 0

    listen_host, listen_port = parse_listen(args.listen)
    print(f"Opening {args.port} at {args.baud}...")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0)
    except serial.SerialException as exc:
        print(f"Serial open failed: {exc}", file=sys.stderr)
        return 1
    time.sleep(1.0)
    ser.reset_input_buffer()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((listen_host, listen_port))
    server.listen(1)
    print(
        f"Listening on {listen_host}:{listen_port}. "
        "Connect: python pressure_monitor.py --wifi --wifi-host <this-pc-ip>"
    )

    try:
        while True:
            client, addr = server.accept()
            print(f"Client connected from {addr[0]}:{addr[1]}")
            try:
                relay_loop(ser, client)
            finally:
                try:
                    client.close()
                except OSError:
                    pass
            print("Client disconnected; waiting for next connection...")
    except KeyboardInterrupt:
        print("\nStopping bridge.")
    finally:
        server.close()
        if ser.is_open:
            ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
