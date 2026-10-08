"""Host tests for the recording sanity gate (synthetic rows; one real-decode test when OpenCV is usable)."""

import hashlib
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
    assert verdict["checks"]["fps"] == 5.0 and verdict["checks"]["fps_source"] == sanity.FPS_SOURCE


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
    frozen = [row(small="same") for _ in range(40)]
    assert any("never changes" in r for r in sanity.evaluate(frozen, container_frame_count=40, manifest=None, file_sha256="x", fps=5.0)["reasons"])
    assert any("container reports" in r for r in sanity.evaluate(live(40), container_frame_count=42, manifest=None, file_sha256="x", fps=5.0)["reasons"])
    bad = sanity.evaluate(live(40), container_frame_count=40, manifest={"output_sha256": "y", "status": "complete"}, file_sha256="x", fps=5.0)
    assert bad["verdict"] == "FAIL" and any("SHA-256" in r for r in bad["reasons"])
    partial = sanity.evaluate(live(40), container_frame_count=40, manifest={"output_sha256": "x", "status": "partial"}, file_sha256="x", fps=5.0)
    assert partial["verdict"] == "FAIL" and any("not 'complete'" in r for r in partial["reasons"])


def test_nothing_decoded_is_a_failure_not_a_pass():
    assert sanity.evaluate([], container_frame_count=None, manifest=None, file_sha256="x", fps=None)["verdict"] == "FAIL"


@pytest.mark.parametrize("fps", [0.0, -1.0, float("nan"), float("inf"), float("-inf"), None, "bad", True])
def test_invalid_fps_fails_without_inventing_a_duration(fps):
    verdict = sanity.evaluate(live(40), container_frame_count=40, manifest=None, file_sha256="x", fps=fps)
    assert verdict["verdict"] == "FAIL"
    assert verdict["checks"]["fps_valid"] is False
    assert verdict["checks"]["longest_content_run_sec"] is None
    assert any("FPS is missing or invalid" in reason for reason in verdict["reasons"])


def test_unknown_container_frame_count_fails_closed():
    verdict = sanity.evaluate(live(40), container_frame_count=None, manifest=None, file_sha256="x", fps=5.0)
    assert verdict["verdict"] == "FAIL"
    assert verdict["checks"]["container_frame_count_known"] is False
    assert any("frame count is missing or invalid" in reason for reason in verdict["reasons"])


@pytest.mark.parametrize("count", [None, 0, -1, float("nan"), float("inf"), 40.5, "40", True])
def test_invalid_container_frame_count_fails_closed(count):
    verdict = sanity.evaluate(live(40), container_frame_count=count, manifest=None, file_sha256="x", fps=5.0)
    assert verdict["verdict"] == "FAIL"
    assert verdict["checks"]["container_frame_count_known"] is False


def test_absent_video_fails_with_a_structured_report(tmp_path):
    report = sanity.analyse(tmp_path / "missing.mkv", None, None)
    assert report["verdict"] == "FAIL"
    assert report["file_sha256"] is None and report["frames_written"] == []
    assert any("absent" in reason for reason in report["reasons"])


def test_invalid_manifest_fails_closed(tmp_path):
    manifest = tmp_path / "broken.manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")
    report = sanity.analyse(tmp_path / "missing.mkv", manifest, None)
    assert report["verdict"] == "FAIL"
    assert report["checks"]["manifest_supplied"] is True
    assert any("manifest could not be read" in reason for reason in report["reasons"])


def test_missing_opencv_fails_with_a_structured_report(tmp_path, monkeypatch):
    video = tmp_path / "unreadable.mkv"
    video.write_bytes(b"video bytes")
    monkeypatch.setitem(sys.modules, "cv2", None)
    report = sanity.analyse(video, None, None)
    assert report["verdict"] == "FAIL"
    assert report["file_sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert any("OpenCV could not be loaded" in reason for reason in report["reasons"])


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
    for kind, expected in (("noise", 0), ("black", 1), ("corrupt", 1)):
        video = tmp_path / f"{kind}.mkv"
        if kind == "corrupt":
            video.write_bytes(b"not a video stream")
        else:
            subprocess.run([sys.executable, "-I", str(maker), str(video), kind], check=True)
        manifest = {"output_sha256": hashlib.sha256(video.read_bytes()).hexdigest(), "status": "complete", "fps": 5}
        manifest_path = tmp_path / f"{kind}.manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        run = subprocess.run([sys.executable, "-I", str(ROOT / "Testing" / "step6_video_sanity.py"), str(video),
                              "--manifest", str(manifest_path), "--frames-dir", str(tmp_path / f"frames-{kind}"),
                              "--out", str(tmp_path / f"{kind}.json")],
                             capture_output=True, text=True)
        assert run.returncode == expected, run.stdout + run.stderr
        report = json.loads((tmp_path / f"{kind}.json").read_text())
        assert report["verdict"] == ("PASS" if expected == 0 else "FAIL")
        assert report["file_sha256"] == manifest["output_sha256"]
        assert report["checks"]["manifest_sha256_match"] is True
        if kind != "corrupt":
            assert report["checks"]["decoded_frames"] == 40
            assert report["checks"]["fps"] == 5.0
            assert report["checks"]["fps_source"] == sanity.FPS_SOURCE
            assert len(report["frames_written"]) == 6 and all(Path(p).is_file() for p in report["frames_written"])


def test_capture_fps_is_read_before_release_and_drives_sample_duration(tmp_path):
    result_dir = tmp_path / "capture-fps"
    video = tmp_path / "capture-fps.mkv"
    video.write_bytes(b"synthetic capture fixture")
    probe = tmp_path / "capture_probe.py"
    probe.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import cv2, numpy as np\n"
        "import step6_video_sanity as sanity\n"
        "class Capture:\n"
        "    def __init__(self): self.released = False; self.index = 0\n"
        "    def isOpened(self): return True\n"
        "    def get(self, prop):\n"
        "        if self.released: return 0.0\n"
        "        if prop == cv2.CAP_PROP_FRAME_COUNT: return 40.0\n"
        "        if prop == cv2.CAP_PROP_FPS: return 7.5\n"
        "        return 0.0\n"
        "    def read(self):\n"
        "        if self.index >= 40: return False, None\n"
        "        rng = np.random.default_rng(self.index)\n"
        "        frame = rng.integers(20, 255, (180, 320, 3), dtype=np.uint8)\n"
        "        self.index += 1\n"
        "        return True, frame\n"
        "    def release(self): self.released = True\n"
        "capture = Capture()\n"
        "cv2.VideoCapture = lambda *args: capture\n"
        "report = sanity.analyse(Path(sys.argv[2]), None, Path(sys.argv[3]))\n"
        "print(json.dumps(report))\n",
        encoding="utf-8",
    )
    run = subprocess.run([sys.executable, "-I", str(probe), str(ROOT / "Testing"), str(video), str(result_dir)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    report = json.loads(run.stdout)
    assert report["verdict"] == "PASS"
    assert report["checks"]["fps"] == 7.5
    assert report["checks"]["longest_content_run_sec"] == 5.33
    assert report["checks"]["fps_source"] == sanity.FPS_SOURCE
    assert len(report["frames_written"]) == 6 and all(Path(p).is_file() for p in report["frames_written"])
