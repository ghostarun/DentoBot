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
content frame != last content frame).
It also writes evenly spaced frames as PNG for a human to look at. A pass says "a real, changing picture was decoded";
it does not say the sequence under test succeeded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def evaluate(rows: list, *, container_frame_count: int | None, manifest: dict | None, file_sha256: str,
             fps: float = 5.0) -> dict:
    """Pure verdict from per-frame rows ``{yavg, ymax, content_fraction, small_hash}``."""

    checks, reasons = {}, []
    decoded = len(rows)
    checks["decoded_frames"] = decoded
    checks["decodes"] = decoded > 0
    if not decoded:
        return {"verdict": "FAIL", "reasons": ["no frame could be decoded"], "checks": checks}
    if container_frame_count is not None and container_frame_count > 0:
        checks["decoded_equals_container_count"] = decoded == int(container_frame_count)
        if not checks["decoded_equals_container_count"]:
            reasons.append(f"decoded {decoded} frames but the container reports {int(container_frame_count)}")
    if manifest is not None:
        checks["manifest_sha256_match"] = manifest.get("output_sha256") == file_sha256
        checks["manifest_status"] = manifest.get("status")
        if not checks["manifest_sha256_match"]:
            reasons.append("the recorder manifest SHA-256 does not match the file")
        if manifest.get("status") != "complete":
            reasons.append(f"the recorder manifest status is {manifest.get('status')!r}, not 'complete'")
    flags = [r["content_fraction"] > CONTENT_FRACTION for r in rows]
    content = sum(flags)
    checks["frames_with_picture_content"] = content
    checks["content_ratio"] = round(content / decoded, 4)
    run = best = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    checks["longest_content_run_sec"] = round(best / float(fps), 2)
    checks["leading_black_frames"] = next((i for i, flag in enumerate(flags) if flag), decoded)
    checks["max_ymax"] = max(r["ymax"] for r in rows)
    checks["mean_yavg"] = round(sum(r["yavg"] for r in rows) / decoded, 3)
    if content / decoded < MIN_CONTENT_FRAME_RATIO or best / float(fps) < MIN_CONTENT_RUN_SEC:
        reasons.append(f"picture content in {content}/{decoded} frames, longest unbroken stretch {best / float(fps):.1f} s "
                       "(black or empty recording)")
    live = [r for r in rows if r["content_fraction"] > CONTENT_FRACTION]
    distinct = len({r["small_hash"] for r in live})
    checks["distinct_small_frames"] = distinct
    checks["first_differs_from_last"] = bool(live) and live[0]["small_hash"] != live[-1]["small_hash"]
    if live and (distinct < MIN_DISTINCT_SMALL_FRAMES or not checks["first_differs_from_last"]):
        reasons.append("the picture never changes (frozen or static recording)")
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "checks": checks}


def analyse(video: Path, manifest_path: Path | None, frames_dir: Path | None, frame_count_for_pngs: int = 6) -> dict:
    import cv2  # imported late: run with python3 -I

    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path else None
    capture = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
    if not capture.isOpened():
        return {"video": str(video), **evaluate([], container_frame_count=None, manifest=manifest, file_sha256=sha256_file(video))}
    container_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    rows, index = [], 0
    wanted = set()
    if frames_dir is not None and container_count > 0:
        frames_dir.mkdir(parents=True, exist_ok=True)
        wanted = {int(i * (container_count - 1) / max(1, frame_count_for_pngs - 1)) for i in range(frame_count_for_pngs)}
    written = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA)
        rows.append({"yavg": float(gray.mean()), "ymax": int(gray.max()),
                     "content_fraction": float((gray > BLACK_MAX).mean()),
                     "small_hash": hashlib.sha1(small.tobytes()).hexdigest()[:16]})
        if index in wanted:
            path = frames_dir / f"frame-{index:06d}.png"
            cv2.imwrite(str(path), frame)
            written.append(str(path))
        index += 1
    capture.release()
    fps = float((manifest or {}).get("fps") or capture.get(cv2.CAP_PROP_FPS) or 5.0)
    report = evaluate(rows, container_frame_count=container_count, manifest=manifest, file_sha256=sha256_file(video), fps=fps)
    report.update(video=str(video), file_bytes=video.stat().st_size, file_sha256=sha256_file(video), frames_written=written)
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
