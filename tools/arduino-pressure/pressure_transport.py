"""Host link to pressure firmware: USB serial or WiFi TCP (UNO R4 WiFi).

Sensing only. Does not command a robot or drill.
"""

from __future__ import annotations

import socket
import time
from abc import ABC, abstractmethod

import serial


class PressureLink(ABC):
    """Same line protocol as firmware: data `seq,micros,raw_adc`, host `RATE <hz>`."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        ...

    @abstractmethod
    def reset_input_buffer(self) -> None:
        ...

    @abstractmethod
    def read_chunk(self) -> bytes:
        """All bytes currently available without blocking."""

    @abstractmethod
    def write(self, data: bytes) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def write_line(self, text: str) -> None:
        payload = text.strip()
        if not payload:
            return
        self.write(f"{payload}\n".encode("ascii"))


class SerialPressureLink(PressureLink):
    def __init__(self, port: str, baud: int) -> None:
        self._ser = serial.Serial(port, baud, timeout=0)

    @property
    def is_open(self) -> bool:
        return bool(self._ser.is_open)

    def reset_input_buffer(self) -> None:
        self._ser.reset_input_buffer()

    def read_chunk(self) -> bytes:
        waiting = self._ser.in_waiting
        if not waiting:
            return b""
        return self._ser.read(waiting)

    def write(self, data: bytes) -> None:
        self._ser.write(data)

    def close(self) -> None:
        if self._ser.is_open:
            self._ser.close()


class TcpPressureLink(PressureLink):
    """TCP client to the UNO R4 WiFi firmware server (same text lines as serial)."""

    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout_s: float = 15.0,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(connect_timeout_s)
        try:
            self._sock.connect((self._host, self._port))
        except OSError as exc:
            self._sock.close()
            raise ConnectionError(
                f"Could not connect to {self._host}:{self._port}: {exc}"
            ) from exc
        self._sock.settimeout(0.0)
        self._pending = b""
        self._closed = False

    @property
    def is_open(self) -> bool:
        return not self._closed

    def reset_input_buffer(self) -> None:
        self._pending = b""

    def read_chunk(self) -> bytes:
        if self._closed:
            return b""
        while True:
            try:
                data = self._sock.recv(65536)
            except BlockingIOError:
                break
            except OSError:
                self._closed = True
                break
            if not data:
                self._closed = True
                break
            self._pending += data
        out = self._pending
        self._pending = b""
        return out

    def write(self, data: bytes) -> None:
        if self._closed:
            return
        try:
            self._sock.sendall(data)
        except OSError:
            self._closed = True

    def close(self) -> None:
        self._closed = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


def open_pressure_link(
    port: str,
    baud: int,
    *,
    use_wifi: bool,
    wifi_host: str,
    wifi_port: int,
) -> PressureLink:
    if use_wifi:
        if not wifi_host.strip():
            raise SystemExit(
                "WiFi mode requires --wifi-host or PRESSURE_WIFI_HOST "
                "(Arduino IP from Serial Monitor after flash)."
            )
        return TcpPressureLink(wifi_host.strip(), wifi_port)
    try:
        return SerialPressureLink(port, baud)
    except serial.SerialException as exc:
        raise SystemExit(
            f"Could not open {port} at {baud}: {exc}\n"
            "Board AP mode (no USB):  python pressure_monitor.py "
            "--wifi --wifi-host 192.168.4.1\n"
            "  or:  export PRESSURE_WIFI_HOST=192.168.4.1 && "
            "python pressure_monitor.py\n"
            "List USB ports:  python pressure_monitor.py --list-ports"
        ) from exc
