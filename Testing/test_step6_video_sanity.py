"""Host tests for the recording sanity gate (synthetic rows; one real-decode test when OpenCV is usable)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Testing"))

import step6_video_sanity as sanity  # noqa: E402


def row(yavg=120.0, ymax=255, content=0.6, small="a"):
    return {"yavg": yavg, "ymax": ymax, "content_fraction": content, "small_hash": small}


def live(n=10):
    return [row(small=f"h{i % 4}") for i in range(n - 1)] + [row(small="last")]


def test_a_live_picture_passes_and_reports_its_numbers():
    verdict = sanity.evaluate(live(40), container_frame_count=40, manifest={"output_sha256": "x", "status": "complete"},
                              file_sha256="x", fps=5.0)
    assert verdict["verdict"] == "PASS" and verdict["reasons"] == []
    assert verdict["checks"]["content_ratio"] == 1.0 and verdict["checks"]["distinct_small_frames"] >= 3


def test_a_whole_run_recording_is_black_before_and_after_slicer_and_still_passes():
    rows = ([row(yavg=0.0, ymax=0, content=0.0, small="b")] * 30 + live(160)[:-1] + [row(small="end")]
            + [row(yavg=0.0, ymax=0, content=0.0, small="b")] * 30)
    verdict = sanity.evaluate(rows, container_frame_count=len(rows), manifest=None, file_sha256="x", fps=5.0)
    assert verdict["verdict"] == "PASS" and verdict["checks"]["leading_black_frames"] == 30
    assert verdict["checks"]["longest_content_run_sec"] == 32.0


def test_a_short_flash_of_picture_in_a_black_recording_fails():
    rows = [row(yavg=0.0, ymax=0, content=0.0, small="b")] * 100 + live(10) + [row(yavg=0.0, ymax=0, content=0.0, small="b")] * 100
    assert sanity.evaluate(rows, container_frame_count=len(rows), manifest=None, file_sha256="x", fps=5.0)["verdict"] == "FAIL"


def test_a_complete_but_black_recording_fails_whatever_the_manifest_says():
    black = [row(yavg=0.008, ymax=255, content=0.00006, small="same") for _ in range(50)]  # the Xwayland :0 signature
    verdict = sanity.evaluate(black, container_frame_count=50, manifest={"output_sha256": "x", "status": "complete"}, file_sha256="x", fps=5.0)
    assert verdict["verdict"] == "FAIL" and any("black or empty" in r for r in verdict["reasons"])


def test_frozen_and_miscounted_and_hash_mismatched_recordings_fail():
    frozen = [row(small="same") for _ in range(20)]
    frozen = [row(small="same") for _ in range(40)]
    assert any("never changes" in r for r in sanity.evaluate(frozen, container_frame_count=40, manifest=None, file_sha256="x", fps=5.0)["reasons"])
    assert any("container reports" in r for r in sanity.evaluate(live(40), container_frame_count=42, manifest=None, file_sha256="x", fps=5.0)["reasons"])
    bad = sanity.evaluate(live(40), container_frame_count=40, manifest={"output_sha256": "y", "status": "complete"}, file_sha256="x", fps=5.0)
    assert bad["verdict"] == "FAIL" and any("SHA-256" in r for r in bad["reasons"])
    partial = sanity.evaluate(live(40), container_frame_count=40, manifest={"output_sha256": "x", "status": "partial"}, file_sha256="x", fps=5.0)
    assert partial["verdict"] == "FAIL" and any("not 'complete'" in r for r in partial["reasons"])


def test_nothing_decoded_is_a_failure_not_a_pass():
    assert sanity.evaluate([], container_frame_count=None, manifest=None, file_sha256="x")["verdict"] == "FAIL"


def test_a_real_video_is_decoded_and_judged(tmp_path):
    result = subprocess.run([sys.executable, "-I", "-c", "import cv2, numpy"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("OpenCV is not usable with python3 -I on this host")
    maker = tmp_path / "make.py"
    maker.write_text(
        "import cv2, numpy as np, sys\n"
        "rng = np.random.default_rng(1)\n"
        "w = cv2.VideoWriter(sys.argv[1], cv2.VideoWriter_fourcc(*'MJPG'), 5, (320, 180))\n"
        "for i in range(40):\n"
        "    f = np.zeros((180, 320, 3), np.uint8) if sys.argv[2] == 'black' else rng.integers(0, 255, (180, 320, 3), dtype=np.uint8)\n"
        "    w.write(f)\n"
        "w.release()\n", encoding="utf-8")
    for kind, expected in (("noise", 0), ("black", 1)):
        video = tmp_path / f"{kind}.mkv"
        subprocess.run([sys.executable, "-I", str(maker), str(video), kind], check=True)
        run = subprocess.run([sys.executable, "-I", str(ROOT / "Testing" / "step6_video_sanity.py"), str(video),
                              "--frames-dir", str(tmp_path / f"frames-{kind}"), "--out", str(tmp_path / f"{kind}.json")],
                             capture_output=True, text=True)
        assert run.returncode == expected, run.stdout + run.stderr
        report = json.loads((tmp_path / f"{kind}.json").read_text())
        assert report["verdict"] == ("PASS" if expected == 0 else "FAIL") and report["checks"]["decoded_frames"] == 40
        assert len(report["frames_written"]) == 6 and all(Path(p).is_file() for p in report["frames_written"])
