#!/usr/bin/env python3
"""Opt-in recording of a complete X11 display for headed Slicer checks."""

from __future__ import annotations

import argparse
import atexit
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ScreenRecorder:
    """Capture one whole X11 screen; call ``stop`` from a ``finally`` block."""

    def __init__(self, display: str, output: str | Path, fps: int = 30, stop_timeout: float = 8.0):
        if not display or display.strip() != display or "\x00" in display:
            raise ValueError("a valid X11 display is required")
        if isinstance(fps, bool) or not isinstance(fps, int) or fps < 1:
            raise ValueError("fps must be a positive integer")
        if not math.isfinite(stop_timeout) or stop_timeout <= 0:
            raise ValueError("stop timeout must be positive")

        requested = Path(output)
        if not requested.is_absolute() or requested.suffix.lower() not in {".mkv", ".mp4"}:
            raise ValueError("output must be an absolute .mkv or .mp4 path")
        self.display = display
        self.output = requested.resolve()
        self.manifest_path = self.output.with_name(f"{self.output.stem}.manifest.json")
        self.fps = fps
        self.stop_timeout = stop_timeout
        self.width: int | None = None
        self.height: int | None = None
        self.started_at_utc: str | None = None
        self._manifest_file = None
        self._process: subprocess.Popen | None = None
        self._result: dict | None = None
        self._failure_reason: str | None = None
        self.command_exit_status: int | None = None
        self._atexit_registered = False

    def _prepare_directory(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(self.output) or os.path.lexists(self.manifest_path):
            raise FileExistsError("recording output or manifest already exists")
        if not self.output.parent.is_dir() or any(self.output.parent.iterdir()):
            raise FileExistsError("recording output directory must be fresh and empty")

    def _display_size(self) -> tuple[int, int]:
        result = subprocess.run(
            ["xdpyinfo", "-display", self.display],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        match = re.search(r"^\s*dimensions:\s*(\d+)x(\d+)\s+pixels\b", result.stdout, re.MULTILINE)
        if not match:
            raise RuntimeError("X11 display dimensions were not reported")
        return int(match.group(1)), int(match.group(2))

    def _manifest(self, status: str, end: str | None, digest: str | None, exit_status: int | None,
                  ffmpeg_exit_status: int | None) -> dict:
        return {
            "schema": "dentobot.screen-recording.v1",
            "status": status,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": end,
            "display": self.display,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "output_sha256": digest,
            "exit_status": exit_status,
            "command_exit_status": self.command_exit_status,
            "ffmpeg_exit_status": ffmpeg_exit_status,
            "failure_reason": self._failure_reason,
        }

    def _write_manifest(self, data: dict) -> None:
        self._manifest_file.seek(0)
        self._manifest_file.truncate()
        self._manifest_file.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
        self._manifest_file.flush()
        os.fsync(self._manifest_file.fileno())

    def start(self) -> "ScreenRecorder":
        if self.started_at_utc is not None:
            raise RuntimeError("recorder can only be started once")
        self.started_at_utc = _utc_now()
        self._prepare_directory()
        self._manifest_file = self.manifest_path.open("x", encoding="utf-8")
        self._write_manifest(self._manifest("recording", None, None, None, None))
        try:
            self.width, self.height = self._display_size()
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                "-f", "x11grab", "-draw_mouse", "1", "-framerate", str(self.fps),
                "-video_size", f"{self.width}x{self.height}", "-i", f"{self.display}+0,0",
                "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                "-pix_fmt", "yuv420p", str(self.output),
            ]
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            atexit.register(self.stop)
            self._atexit_registered = True
        except (OSError, RuntimeError, subprocess.SubprocessError):
            self._failure_reason = "display inspection or ffmpeg startup failed"
            if self._process is None:
                self._finish(None, unexpected=True, forced=False, requested_exit_status=1)
            else:
                self.stop(exit_status=1)
            raise RuntimeError("could not start screen recording; see the manifest") from None

        return self

    def stop(self, exit_status: int = 0) -> dict:
        """Finalize the video, reap ffmpeg, and return the written manifest."""
        if self._result is not None:
            return dict(self._result)
        if self._manifest_file is None:
            raise RuntimeError("recorder has not been started")
        if isinstance(exit_status, bool) or not isinstance(exit_status, int):
            raise ValueError("exit status must be an integer")

        process = self._process
        unexpected = process is None
        forced = False
        ffmpeg_exit_status = None
        if process is not None:
            unexpected = process.poll() is not None
            if not unexpected:
                try:
                    process.stdin.write(b"q\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    process.stdin.close()
                except OSError:
                    pass
            try:
                process.wait(timeout=self.stop_timeout)
            except subprocess.TimeoutExpired:
                forced = True
                try:
                    process.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            ffmpeg_exit_status = process.returncode

        self._finish(ffmpeg_exit_status, unexpected, forced, exit_status)
        if self._atexit_registered:
            atexit.unregister(self.stop)
            self._atexit_registered = False
        return dict(self._result)

    def _finish(self, ffmpeg_exit_status: int | None, unexpected: bool, forced: bool,
                requested_exit_status: int) -> None:
        digest = None
        has_video = self.output.is_file()
        if has_video:
            hasher = hashlib.sha256()
            with self.output.open("rb") as video:
                for chunk in iter(lambda: video.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            has_video = self.output.stat().st_size > 0

        complete = (
            ffmpeg_exit_status == 0 and not unexpected and not forced and has_video
            and requested_exit_status == 0
        )
        if not complete and self._failure_reason is None:
            if requested_exit_status != 0:
                self._failure_reason = "recording owner exited with a nonzero status"
            elif forced:
                self._failure_reason = "ffmpeg required forced shutdown"
            elif unexpected:
                self._failure_reason = "ffmpeg exited before a requested stop"
            elif ffmpeg_exit_status != 0:
                self._failure_reason = "ffmpeg exited with an error"
            elif not has_video:
                self._failure_reason = "ffmpeg produced no video"
        status = "complete" if complete else ("partial" if has_video else "failed")
        actual_exit_status = requested_exit_status if requested_exit_status != 0 or complete else 1
        result = self._manifest(status, _utc_now(), digest, actual_exit_status, ffmpeg_exit_status)
        self._write_manifest(result)
        self._manifest_file.close()
        self._result = result

    def __enter__(self) -> "ScreenRecorder":
        return self.start()

    def __exit__(self, exc_type, _exc, _traceback) -> bool:
        if exc_type is not None:
            self._failure_reason = "recording owner raised an exception"
        self.stop(exit_status=1 if exc_type else 0)
        return False


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("duration must be a positive number") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be a positive number")
    return seconds


def _positive_fps(value: str) -> int:
    try:
        fps = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("fps must be a positive integer") from None
    if fps < 1:
        raise argparse.ArgumentTypeError("fps must be a positive integer")
    return fps


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--" in raw_args:
        separator = raw_args.index("--")
        command_args = raw_args[separator + 1:]
        option_args = raw_args[:separator]
    else:
        command_args = []
        option_args = raw_args

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", required=True, help="X11 display, for example :0")
    parser.add_argument("--output", required=True, help="absolute .mkv or .mp4 path in a fresh empty directory")
    ending = parser.add_mutually_exclusive_group(required=True)
    ending.add_argument("--duration", type=_positive_seconds, help="record for this many seconds")
    ending.add_argument("--until-enter", action="store_true", help="record until Enter is pressed")
    ending.add_argument("--command", action="store_true", help="record while running arguments after --")
    parser.add_argument("--fps", type=_positive_fps, default=30, help="capture frames per second (default: 30)")
    args = parser.parse_args(option_args)
    if args.command and not command_args:
        parser.error("--command requires a command after --")
    if not args.command and command_args:
        parser.error("command arguments after -- require --command")

    recorder = None
    try:
        recorder = ScreenRecorder(args.display, args.output, fps=args.fps)
        recorder.start()
        if args.duration is not None:
            deadline = time.monotonic() + args.duration
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 1.0))
        elif args.command:
            command_exit_status = 1
            try:
                try:
                    command_exit_status = subprocess.run(command_args, check=False).returncode
                except OSError:
                    command_exit_status = 127
                    recorder._failure_reason = "automation command could not be started"
                except KeyboardInterrupt:
                    command_exit_status = 130
                    raise
            finally:
                recorder.command_exit_status = command_exit_status
                result = recorder.stop(exit_status=command_exit_status)
            return result["exit_status"]
        else:
            input("Recording the full display. Press Enter to stop.\n")
    except KeyboardInterrupt:
        if recorder is not None and recorder._manifest_file is not None and recorder._result is None:
            recorder.stop(exit_status=130)
        return 130
    except EOFError:
        pass
    except (OSError, RuntimeError, ValueError) as error:
        if recorder is not None and recorder._manifest_file is not None and recorder._result is None:
            recorder._failure_reason = "screen recording failed"
            recorder.stop(exit_status=1)
        print(f"screen recording failed ({type(error).__name__}); see the manifest if one was written", file=sys.stderr)
        return 1
    if recorder is None:
        return 1
    result = recorder.stop()
    return result["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
