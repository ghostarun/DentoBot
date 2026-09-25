"""Measure bounded 3-D render throughput and Qt heartbeats on one loaded case."""

import json
import math
import os
import statistics
import sys
import time
from pathlib import Path


MAX_DURATION_NS = 5_000_000_000
MAX_RENDER_SAMPLES = 600
HEARTBEAT_INTERVAL_MS = 100
FRAME_BUDGET_NS = 16_700_000
CAMERA_ROTATION_DEGREES_PER_SECOND = 12.0
SOFTWARE_RENDERER_MARKERS = ("llvmpipe", "softpipe", "swrast", "swiftshader", "software rasterizer")


def _renderer_flags(renderer_string):
    renderer = (renderer_string or "").lower()
    return {
        "software_renderer_detected": any(marker in renderer for marker in SOFTWARE_RENDERER_MARKERS),
        "d3d12_backend_detected": "d3d12" in renderer or "direct3d 12" in renderer,
    }


def _nearest_rank(values, fraction):
    return sorted(values)[max(0, math.ceil(fraction * len(values)) - 1)] if values else None


def _summarize_timestamps(timestamps):
    intervals_ms = [
        (right - left) / 1_000_000.0
        for left, right in zip(timestamps, timestamps[1:])
    ]
    elapsed_ns = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0
    return {
        "timestamp_count": len(timestamps),
        "interval_count": len(intervals_ms),
        "median_interval_ms": round(statistics.median(intervals_ms), 3) if intervals_ms else None,
        "p95_interval_ms": round(_nearest_rank(intervals_ms, 0.95), 3) if intervals_ms else None,
        "max_interval_ms": round(max(intervals_ms), 3) if intervals_ms else None,
        "event_rate_hz": round((len(timestamps) - 1) * 1_000_000_000 / elapsed_ns, 3)
        if elapsed_ns > 0 else None,
    }


def _self_check():
    summary = _summarize_timestamps([0, 10_000_000, 30_000_000, 60_000_000])
    assert summary["median_interval_ms"] == 20.0
    assert summary["p95_interval_ms"] == 30.0
    assert summary["event_rate_hz"] == 50.0
    assert _summarize_timestamps([1])["event_rate_hz"] is None
    assert _renderer_flags("OpenGL renderer string: swrast") == {
        "software_renderer_detected": True,
        "d3d12_backend_detected": False,
    }
    assert _renderer_flags("D3D12 (NVIDIA)") == {
        "software_renderer_detected": False,
        "d3d12_backend_detected": True,
    }
    print("DENTOBOT_RENDER_FRAME_PROBE_SELF_CHECK_PASS", flush=True)


def _xvfb_process_detected():
    try:
        process_ids = os.listdir("/proc")
    except OSError:
        return None
    for process_id in process_ids:
        if not process_id.isdigit():
            continue
        try:
            command = Path("/proc", process_id, "cmdline").read_bytes().split(b"\0", 1)[0]
        except OSError:
            continue
        if command.rsplit(b"/", 1)[-1].lower() in (b"xvfb", b"xvfb.wrap"):
            return True
    return False


def _renderer_identity(render_window):
    identity = {
        "render_window_class": render_window.GetClassName(),
        "renderer_string": None,
        "vendor_string": None,
        "opengl_version": None,
    }
    report_capabilities = getattr(render_window, "ReportCapabilities", None)
    if not callable(report_capabilities):
        return identity
    try:
        capabilities = str(report_capabilities() or "")
    except Exception:
        return identity
    for line in capabilities.splitlines():
        lower = line.lower()
        if "opengl" not in lower:
            continue
        if "renderer" in lower and identity["renderer_string"] is None:
            identity["renderer_string"] = line.strip()
        elif "vendor" in lower and identity["vendor_string"] is None:
            identity["vendor_string"] = line.strip()
        elif "version" in lower and identity["opengl_version"] is None:
            identity["opengl_version"] = line.strip()
    return identity


def _emit(report):
    print("DENTOBOT_RENDER_FRAME_PROBE " + json.dumps(report, sort_keys=True), flush=True)


def run(qt, slicer, vtk):
    state = {
        "finished": False,
        "stage": "case_input",
        "case_loaded": False,
        "render_window": None,
        "observer_tag": None,
        "camera": None,
        "original_camera": None,
        "render_window_size_pixels": None,
        "timers": [],
        "case_load_started_ns": None,
        "case_load_ended_ns": None,
        "started_ns": None,
        "ended_ns": None,
        "frames": [],
        "heartbeats": [],
        "renderer": None,
    }

    def finish(stop_reason, error=None):
        if state["finished"]:
            return
        state["finished"] = True
        state["ended_ns"] = time.monotonic_ns()
        cleanup_errors = []

        for timer in state["timers"]:
            try:
                timer.stop()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)

        window = state["render_window"]
        observer_tag = state["observer_tag"]
        if window is not None and observer_tag is not None:
            try:
                window.RemoveObserver(observer_tag)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)

        camera = state["camera"]
        original_camera = state["original_camera"]
        if camera is not None and original_camera is not None:
            try:
                camera.DeepCopy(original_camera)
                window.Render()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)

        frames = state["frames"]
        frame_stats = _summarize_timestamps(frames)
        missed = sum(
            right - left > FRAME_BUDGET_NS
            for left, right in zip(frames, frames[1:])
        )
        frame_stats["frame_budget_ms"] = 16.7
        frame_stats["missed_16_7ms_budget_intervals"] = missed
        frame_stats["missed_16_7ms_budget_percent"] = round(
            100.0 * missed / frame_stats["interval_count"], 2
        ) if frame_stats["interval_count"] else None

        heartbeat_stats = _summarize_timestamps(state["heartbeats"])
        heartbeat_stats["requested_interval_ms"] = HEARTBEAT_INTERVAL_MS

        context = {
            "display_available": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
            "qt_platform": os.environ.get("QT_QPA_PLATFORM") or None,
            "xvfb_detected": _xvfb_process_detected(),
        }
        qpa = (context["qt_platform"] or "").lower().split(":", 1)[0]
        renderer_text = (state["renderer"] or {}).get("renderer_string") or ""
        renderer_flags = _renderer_flags(renderer_text)
        context["headless_detected"] = (
            not context["display_available"] or qpa in ("offscreen", "minimal")
            or context["xvfb_detected"] is True
        )
        context.update(renderer_flags)
        enough_frames = len(frames) >= 2

        start_ns = state["started_ns"]
        end_ns = state["ended_ns"]
        report = {
            "status": "complete" if not error and not cleanup_errors and enough_frames else "failed",
            "stop_reason": stop_reason,
            "error_stage": error[0] if error else None,
            "error_type": error[1] if error else None,
            "measurement_error": None if enough_frames else "fewer than two completed render events",
            "case_loaded": state["case_loaded"],
            "case_load_duration_seconds": round(
                (state["case_load_ended_ns"] - state["case_load_started_ns"]) / 1_000_000_000.0, 3
            ) if state["case_load_started_ns"] is not None and state["case_load_ended_ns"] is not None else None,
            "measurement_duration_seconds": round((end_ns - start_ns) / 1_000_000_000.0, 3)
            if start_ns is not None and end_ns is not None else 0.0,
            "max_duration_seconds": MAX_DURATION_NS / 1_000_000_000.0,
            "max_render_samples": MAX_RENDER_SAMPLES,
            "render": frame_stats,
            "render_window_size_pixels": state["render_window_size_pixels"],
            "render_measurement": "forced VTK RenderWindow EndEvent throughput, not presented or VSync FPS",
            "qt_heartbeat": heartbeat_stats,
            "renderer": state["renderer"],
            "render_context": context,
            "hardware_60_fps_acceptance": "NOT_ESTABLISHED",
            "headless_or_xvfb_acceptance": "DIAGNOSTIC_ONLY",
            "acceptance_note": (
                "Headless, Xvfb, or software-rendered results are diagnostic only "
                "and do not establish hardware 60 FPS. D3D12 backend identity alone "
                "does not establish hardware acceleration or presented 60 FPS."
            ),
            "cleanup_errors": cleanup_errors,
        }
        _emit(report)
        slicer.app.exit(1 if report["status"] == "failed" else 0)

    try:
        state["stage"] = "case_input"
        case_value = os.environ.get("DENTOBOT_PERF_CASE")
        if not case_value:
            raise ValueError("DENTOBOT_PERF_CASE is required")
        case_path = Path(case_value).expanduser()
        if not case_path.is_file():
            raise FileNotFoundError("case file is unavailable")

        state["stage"] = "load_case"
        state["case_load_started_ns"] = time.monotonic_ns()
        try:
            slicer.util.selectModule("DENTOWorkflow")
            widget = slicer.util.getModuleWidget("DENTOWorkflow")
            if widget is None or widget.logic is None:
                raise RuntimeError("DENTOWorkflow widget is unavailable")
            widget._openCaseBundle(str(case_path))
        finally:
            state["case_load_ended_ns"] = time.monotonic_ns()
        state["case_loaded"] = True

        state["stage"] = "prepare_view"
        view = slicer.app.layoutManager().threeDWidget(0).threeDView()
        window = view.renderWindow()
        renderer = window.GetRenderers().GetFirstRenderer()
        if renderer is None:
            raise RuntimeError("3-D renderer is unavailable")
        camera = renderer.GetActiveCamera()
        if camera is None:
            raise RuntimeError("3-D camera is unavailable")
        state["render_window"] = window
        state["camera"] = camera
        state["original_camera"] = vtk.vtkCamera()
        state["original_camera"].DeepCopy(camera)
        window.Render()
        size = window.GetSize()
        state["render_window_size_pixels"] = [int(size[0]), int(size[1])]
        state["renderer"] = _renderer_identity(window)

        frame_times = state["frames"]
        heartbeat_times = state["heartbeats"]

        def on_render_end(caller, event):
            if len(frame_times) < MAX_RENDER_SAMPLES:
                frame_times.append(time.monotonic_ns())

        state["stage"] = "measure"
        state["observer_tag"] = window.AddObserver("EndEvent", on_render_end)
        state["started_ns"] = time.monotonic_ns()
        deadline_ns = state["started_ns"] + MAX_DURATION_NS
        last_motion_ns = [state["started_ns"]]

        def heartbeat():
            heartbeat_times.append(time.monotonic_ns())

        def render_tick():
            now_ns = time.monotonic_ns()
            if now_ns >= deadline_ns:
                finish("duration_limit")
                return
            if len(frame_times) >= MAX_RENDER_SAMPLES:
                finish("sample_limit")
                return
            try:
                elapsed = (now_ns - last_motion_ns[0]) / 1_000_000_000.0
                camera.Azimuth(CAMERA_ROTATION_DEGREES_PER_SECOND * elapsed)
                last_motion_ns[0] = now_ns
                window.Render()
            except Exception as exc:
                finish("render_error", ("measure", type(exc).__name__))

        heartbeat_timer = qt.QTimer()
        heartbeat_timer.setInterval(HEARTBEAT_INTERVAL_MS)
        heartbeat_timer.connect("timeout()", heartbeat)
        render_timer = qt.QTimer()
        render_timer.setInterval(0)
        render_timer.connect("timeout()", render_tick)
        state["timers"].extend((heartbeat_timer, render_timer))
        heartbeat_timer.start()
        render_timer.start()
    except Exception as exc:
        finish("probe_error", (state["stage"], type(exc).__name__))


if __name__ == "__main__":
    if "--self-check" in sys.argv[1:]:
        _self_check()
    else:
        import qt
        import slicer
        import vtk

        qt.QTimer.singleShot(0, lambda: run(qt, slicer, vtk))
