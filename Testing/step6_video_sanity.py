#!/usr/bin/env python3
"""Pixel/decode sanity gate for a recorded Slicer screen video (S6-ADVISOR-GUI-01 B verification, evidence rule M2).

    python3 -I Testing/step6_video_sanity.py <video.mkv|mp4> [--manifest <recorder .manifest.json>]
        [--frames-dir DIR] [--out report.json]

``record_slicer_screen.py`` reports ``complete`` from process exit codes alone, so a black recording of an Xwayland
display can be "complete". This reads the finished file only (use ``python3 -I``: OpenCV's FFmpeg backend must not meet
the user-site NumPy 2) and answers four questions with numbers: does it decode with the container's frame count, does
the recorder manifest hash match, do the frames carry picture content (more than 1% of pixels above limited-range
black) for at least half of the recording and in one unbroken stretch of at least 5 s (a whole-run recording is black
before Slicer opens and after it exits), and is that picture alive (several distinct downsampled frames, first
content frame != last content frame). Duration uses the video's captured FPS read before release; missing or invalid
FPS and an unknown container frame count fail closed.
It also writes evenly spaced frames as PNG for a human to look at. A pass says "a real, changing picture was decoded";
it does not say the sequence under test succeeded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

BLACK_MAX = 16
CONTENT_FRACTION = 0.01
MIN_CONTENT_FRAME_RATIO = 0.50
MIN_CONTENT_RUN_SEC = 5.0
MIN_DISTINCT_SMALL_FRAMES = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


FPS_SOURCE = "cv2.VideoCapture(CAP_PROP_FPS) before release"


def _positive_fps(value) -> float | None:
    if value is None or isinstance(value, (bool, str, bytes)):
        return None
    try:
        fps = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return fps if math.isfinite(fps) and fps > 0 else None


def _positive_frame_count(value) -> int | None:
    if value is None or isinstance(value, (bool, str, bytes)):
        return None
    try:
        count = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(count) or count <= 0 or not count.is_integer():
        return None
    return int(count)


def evaluate(rows: list, *, container_frame_count: int | None, manifest: dict | None, file_sha256: str | None,
             fps, manifest_error: str | None = None, decode_error: str | None = None,
             fps_source: str = FPS_SOURCE) -> dict:
    """Pure verdict from per-frame rows ``{yavg, ymax, content_fraction, small_hash}``."""

    checks, reasons = {}, []
    decoded = len(rows)
    checks["decoded_frames"] = decoded
    checks["decodes"] = decoded > 0
    checks["file_sha256_present"] = bool(file_sha256)
    checks["fps"] = _positive_fps(fps)
    checks["fps_valid"] = checks["fps"] is not None
    checks["fps_source"] = fps_source
    checks["container_frame_count"] = _positive_frame_count(container_frame_count)
    checks["container_frame_count_known"] = checks["container_frame_count"] is not None
    checks["decoded_equals_container_count"] = (
        checks["container_frame_count"] == decoded if checks["container_frame_count_known"] else False
    )
    checks["manifest_supplied"] = manifest is not None or manifest_error is not None
    checks["decode_error"] = decode_error
    if not file_sha256:
        reasons.append("the video file could not be hashed")
    if manifest_error:
        reasons.append(f"the recorder manifest could not be read: {manifest_error}")
    if not checks["container_frame_count_known"]:
        reasons.append("the container frame count is missing or invalid")
    elif not checks["decoded_equals_container_count"]:
        reasons.append(
            f"decoded {decoded} frames but the container reports {checks['container_frame_count']}"
        )
    if not checks["fps_valid"]:
        reasons.append("the capture FPS is missing or invalid; recording duration cannot be established")
    if decode_error:
        reasons.append(f"the video decoder failed: {decode_error}")
    if not decoded:
        reasons.append("no frame could be decoded")
    if manifest is not None:
        checks["manifest_sha256_match"] = manifest.get("output_sha256") == file_sha256
        checks["manifest_status"] = manifest.get("status")
        if not checks["manifest_sha256_match"]:
            reasons.append("the recorder manifest SHA-256 does not match the file")
        if manifest.get("status") != "complete":
            reasons.append(f"the recorder manifest status is {manifest.get('status')!r}, not 'complete'")
    if decoded:
        flags = [r["content_fraction"] > CONTENT_FRACTION for r in rows]
        content = sum(flags)
        checks["frames_with_picture_content"] = content
        checks["content_ratio"] = round(content / decoded, 4)
        run = best = 0
        for flag in flags:
            run = run + 1 if flag else 0
            best = max(best, run)
        fps_value = checks["fps"]
        checks["longest_content_run_sec"] = round(best / fps_value, 2) if fps_value is not None else None
        checks["leading_black_frames"] = next((i for i, flag in enumerate(flags) if flag), decoded)
        checks["max_ymax"] = max(r["ymax"] for r in rows)
        checks["mean_yavg"] = round(sum(r["yavg"] for r in rows) / decoded, 3)
        short_content = content / decoded < MIN_CONTENT_FRAME_RATIO
        short_run = fps_value is not None and best / fps_value < MIN_CONTENT_RUN_SEC
        if short_content or short_run:
            duration = f"{best / fps_value:.1f} s" if fps_value is not None else "unknown duration"
            reasons.append(f"picture content in {content}/{decoded} frames, longest unbroken stretch {duration} "
                           "(black or empty recording)")
        live = [r for r in rows if r["content_fraction"] > CONTENT_FRACTION]
        distinct = len({r["small_hash"] for r in live})
        checks["distinct_small_frames"] = distinct
        checks["first_differs_from_last"] = bool(live) and live[0]["small_hash"] != live[-1]["small_hash"]
        if live and (distinct < MIN_DISTINCT_SMALL_FRAMES or not checks["first_differs_from_last"]):
            reasons.append("the picture never changes (frozen or static recording)")
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "checks": checks}


def analyse(video: Path, manifest_path: Path | None, frames_dir: Path | None, frame_count_for_pngs: int = 6) -> dict:
    video = Path(video)
    manifest = None
    manifest_error = None
    if manifest_path is not None:
        try:
            loaded_manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            if not isinstance(loaded_manifest, dict):
                raise ValueError("manifest root must be a JSON object")
            manifest = loaded_manifest
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            manifest_error = f"{type(exc).__name__}: {exc}"

    if not video.is_file():
        report = evaluate([], container_frame_count=None, manifest=manifest, file_sha256=None, fps=None,
                          manifest_error=manifest_error, decode_error="video file is absent or not a regular file")
        report.update(video=str(video), file_bytes=None, file_sha256=None, frames_written=[])
        return report

    try:
        file_bytes = video.stat().st_size
        file_digest = sha256_file(video)
    except OSError as exc:
        report = evaluate([], container_frame_count=None, manifest=manifest, file_sha256=None, fps=None,
                          manifest_error=manifest_error, decode_error=f"video file could not be read: {exc}")
        report.update(video=str(video), file_bytes=None, file_sha256=None, frames_written=[])
        return report

    if not isinstance(frame_count_for_pngs, int) or isinstance(frame_count_for_pngs, bool) or frame_count_for_pngs < 1:
        raise ValueError("frame_count_for_pngs must be a positive integer")

    try:
        import cv2  # imported late: run with python3 -I
    except Exception as exc:
        report = evaluate([], container_frame_count=None, manifest=manifest, file_sha256=file_digest, fps=None,
                          manifest_error=manifest_error,
                          decode_error=f"OpenCV could not be loaded: {type(exc).__name__}: {exc}")
        report.update(video=str(video), file_bytes=file_bytes, file_sha256=file_digest, frames_written=[])
        return report

    capture = None
    container_count = None
    fps = None
    rows, written = [], []
    decoder_error = None
    sample_error = None
    wanted = set()
    index = 0
    try:
        capture = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
        opened = capture.isOpened()
        raw_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        raw_fps = capture.get(cv2.CAP_PROP_FPS)
        container_count = _positive_frame_count(raw_count)
        fps = _positive_fps(raw_fps)
        if not opened:
            decoder_error = "OpenCV could not open the video"
        if frames_dir is not None and container_count is not None:
            try:
                frames_dir = Path(frames_dir)
                frames_dir.mkdir(parents=True, exist_ok=True)
                wanted = {int(i * (container_count - 1) / max(1, frame_count_for_pngs - 1))
                          for i in range(frame_count_for_pngs)}
            except OSError as exc:
                sample_error = f"could not prepare sample directory: {exc}"
        while opened:
            try:
                ok, frame = capture.read()
            except Exception as exc:
                decoder_error = f"{type(exc).__name__}: {exc}"
                break
            if not ok:
                break
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)
            except Exception as exc:
                decoder_error = f"{type(exc).__name__}: {exc}"
                break
            rows.append({"yavg": float(gray.mean()), "ymax": int(gray.max()),
                         "content_fraction": float((gray > BLACK_MAX).mean()),
                         "small_hash": hashlib.sha1(small.tobytes()).hexdigest()[:16]})
            if index in wanted and frames_dir is not None:
                path = frames_dir / f"frame-{index:06d}.png"
                try:
                    if cv2.imwrite(str(path), frame):
                        written.append(str(path))
                    else:
                        sample_error = f"OpenCV could not write sample frame {index}"
                except Exception as exc:
                    sample_error = f"could not write sample frame {index}: {type(exc).__name__}: {exc}"
            index += 1
    except Exception as exc:
        decoder_error = f"{type(exc).__name__}: {exc}"
    finally:
        if capture is not None:
            try:
                capture.release()
            except Exception as exc:
                decoder_error = decoder_error or f"capture release failed: {type(exc).__name__}: {exc}"

    report = evaluate(rows, container_frame_count=container_count, manifest=manifest, file_sha256=file_digest,
                      fps=fps, manifest_error=manifest_error, decode_error=decoder_error)
    if sample_error:
        report["verdict"] = "FAIL"
        report["reasons"].append(f"sample extraction failed: {sample_error}")
    report.update(video=str(video), file_bytes=file_bytes, file_sha256=file_digest, frames_written=written)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = analyse(args.video, args.manifest, args.frames_dir)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
