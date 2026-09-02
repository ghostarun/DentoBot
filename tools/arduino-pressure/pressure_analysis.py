#!/usr/bin/env python3
"""Load a pressure-monitor run and inspect dips, peaks, and anomalies.

Uses the same host venv as pressure_monitor.py. Does not open serial or
command hardware.

    /home/light-tarun/pressure-env/bin/python pressure_analysis.py
    /home/light-tarun/pressure-env/bin/python pressure_analysis.py run_20260831_181114
    /home/light-tarun/pressure-env/bin/python pressure_analysis.py --no-gui samples.csv
    /home/light-tarun/pressure-env/bin/python pressure_analysis.py --no-gui --auto-air-thresholds
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets, QtGui

from pressure_signal import (
    AIR_OFF_ENTER_KPA,
    AIR_ON_ENTER_KPA,
    air_state_for_series,
    air_state_summary,
    apply_air_display,
    normalize_air_filter_mode,
)
from pressure_plot import (
    DIM_RAW_PEN,
    FULL_RAW_PEN,
    add_annotation_lines,
    set_annotation_lines,
)
from pressure_annotate import (
    ManualAnnotation,
    format_annotation_lines,
    load_annotations,
    match_annotation_dip,
)
from pressure_filter import (
    BoundaryEvent,
    drill_stages_from_annotations,
    format_stage_table,
    replay_tracker,
    stage_statistics,
)
from pressure_config import (
    ADC_BITS,
    PipelineConfig,
    build_config_panel,
    load_pipeline,
    measured_hz_from_times,
    status_line,
)

ADC_MAX = (1 << ADC_BITS) - 1
MAX_DISPLAY_POINTS = 40000
DEFAULT_MIN_DURATION_MS = 20.0
RUNS_ROOT = Path(__file__).resolve().parent / "pressure_runs"

LEGACY_SAMPLE_COLUMNS = [
    "seq",
    "time_s",
    "raw_adc",
    "pressure_kPa",
    "baseline_kPa",
    "residual_kPa",
    "threshold_kPa",
    "dpdt_kPa_per_s",
    "event_state",
]


@dataclass
class DetectedEvent:
    event_id: int
    type: str
    start_s: float
    extreme_s: float
    end_s: float
    baseline_kPa: float
    extreme_pressure_kPa: float
    amplitude_kPa: float
    duration_ms: float
    max_abs_dpdt_kPa_per_s: float
    source: str
    score: float = 0.0
    drill_stage: str = ""

    @property
    def is_dip(self) -> bool:
        if self.type in ("STEP", "TRANSIENT"):
            return self.amplitude_kPa < 0
        return self.type == "DIP"


@dataclass
class Anomaly:
    kind: str
    time_s: float
    detail: str


@dataclass
class PressureRun:
    run_dir: Path
    samples_path: Path
    events_path: Path | None
    seq: np.ndarray
    time_s: np.ndarray
    raw_adc: np.ndarray
    pressure_kPa: np.ndarray
    baseline_kPa: np.ndarray
    residual_kPa: np.ndarray
    threshold_kPa: np.ndarray
    dpdt_kPa_per_s: np.ndarray
    event_state: np.ndarray
    filtered_kPa: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=np.float64))
    spread_kPa: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=np.float64))
    air_state: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=object))
    recorded_events: list[DetectedEvent] = field(default_factory=list)
    annotations: list[ManualAnnotation] = field(default_factory=list)
    annotations_path: Path | None = None
    pipeline: PipelineConfig | None = None
    measured_hz: float = float("nan")


def resolve_run_dir(target: str | Path | None) -> Path:
    if target is None:
        runs = [
            path
            for path in RUNS_ROOT.glob("run_*")
            if path.is_dir() and (path / "samples.csv").is_file()
        ]
        if not runs:
            raise FileNotFoundError(
                f"No pressure runs with samples.csv under {RUNS_ROOT}"
            )
        return max(runs, key=lambda path: path.name)

    path = Path(target).expanduser().resolve()
    if path.is_file() and path.name == "samples.csv":
        return path.parent
    if path.is_dir():
        return path
    named = RUNS_ROOT / path.name
    if named.is_dir():
        return named
    raise FileNotFoundError(f"No pressure run at {path}")


def _float_cell(value: str) -> float:
    if value == "" or value.lower() == "nan":
        return float("nan")
    return float(value)


def _optional_float(row: dict, key: str, default: float = float("nan")) -> float:
    if key not in row:
        return default
    return _float_cell(row[key])


def boundary_to_detected(event: BoundaryEvent, source: str) -> DetectedEvent:
    return DetectedEvent(
        event_id=event.event_id,
        type=event.type,
        start_s=event.start_s,
        extreme_s=event.extreme_s,
        end_s=event.end_s,
        baseline_kPa=event.p_before_kPa,
        extreme_pressure_kPa=event.p_after_kPa,
        amplitude_kPa=event.step_kPa,
        duration_ms=event.duration_ms,
        max_abs_dpdt_kPa_per_s=abs(event.peak_dpdt_kPa_s),
        source=source,
        score=event.score,
        drill_stage=event.drill_stage,
    )


def load_recorded_events(path: Path) -> list[DetectedEvent]:
    events: list[DetectedEvent] = []
    if not path.is_file():
        return events

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        for row in reader:
            if "p_before_kPa" in fields:
                before = _float_cell(row["p_before_kPa"])
                after = _float_cell(row["p_after_kPa"])
                events.append(
                    DetectedEvent(
                        event_id=int(float(row["event_id"])),
                        type=row["type"].strip().upper(),
                        start_s=float(row["start_s"]),
                        extreme_s=float(row["extreme_s"]),
                        end_s=float(row["end_s"]),
                        baseline_kPa=before,
                        extreme_pressure_kPa=after,
                        amplitude_kPa=_float_cell(row.get("step_kPa", str(after - before))),
                        duration_ms=float(row["duration_ms"]),
                        max_abs_dpdt_kPa_per_s=abs(_float_cell(row.get("peak_dpdt_kPa_s", "nan"))),
                        source="recorded",
                        score=_optional_float(row, "score", 0.0),
                        drill_stage=row.get("drill_stage", "").strip(),
                    )
                )
            else:
                events.append(
                    DetectedEvent(
                        event_id=int(float(row["event_id"])),
                        type=row["type"].strip().upper(),
                        start_s=float(row["start_s"]),
                        extreme_s=float(row["extreme_s"]),
                        end_s=float(row["end_s"]),
                        baseline_kPa=float(row["baseline_kPa"]),
                        extreme_pressure_kPa=float(row["extreme_pressure_kPa"]),
                        amplitude_kPa=float(row["amplitude_kPa"]),
                        duration_ms=float(row["duration_ms"]),
                        max_abs_dpdt_kPa_per_s=float(row["max_abs_dpdt_kPa_per_s"]),
                        source="recorded",
                    )
                )
    return events


def _arrays_from_replay(time_s, pressure, seq, raw_adc, annotations, config=None):
    stages = drill_stages_from_annotations(time_s, annotations)
    samples, events = replay_tracker(
        time_s, pressure, seq, raw_adc, stages, config=config
    )
    filtered = np.asarray([item.pressure_filtered_kPa for item in samples], dtype=np.float64)
    slow = np.asarray([item.baseline_slow_kPa for item in samples], dtype=np.float64)
    delta = np.asarray([item.delta_kPa for item in samples], dtype=np.float64)
    deriv = np.asarray([item.dpdt_filtered_kPa_s for item in samples], dtype=np.float64)
    spread = np.asarray([item.rolling_spread_kPa for item in samples], dtype=np.float64)
    air = np.asarray([item.air_state for item in samples], dtype=object)
    state = np.asarray([item.candidate_state for item in samples], dtype=object)
    return filtered, slow, delta, deriv, spread, air, state, events


def load_run(target: str | Path | None = None) -> PressureRun:
    run_dir = resolve_run_dir(target)
    samples_path = run_dir / "samples.csv"
    if not samples_path.is_file():
        raise FileNotFoundError(f"Missing {samples_path}")

    with samples_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if "seq" not in fields or "time_s" not in fields or "raw_adc" not in fields:
            raise ValueError(f"{samples_path} is missing seq/time_s/raw_adc")
        rows = list(reader)

    if not rows:
        raise ValueError(f"{samples_path} has no sample rows")

    seq = np.asarray([int(float(row["seq"])) for row in rows], dtype=np.int64)
    time_s = np.asarray([_float_cell(row["time_s"]) for row in rows], dtype=np.float64)
    raw_adc = np.asarray([int(float(row["raw_adc"])) for row in rows], dtype=np.int32)
    if "pressure_raw_kPa" in fields:
        pressure = np.asarray([_float_cell(row["pressure_raw_kPa"]) for row in rows], dtype=np.float64)
    elif "pressure_kPa" in fields:
        pressure = np.asarray([_float_cell(row["pressure_kPa"]) for row in rows], dtype=np.float64)
    else:
        raise ValueError(f"{samples_path} has no pressure column")

    events_path = run_dir / "events.csv"
    annotations_path = run_dir / "annotations.csv"
    annotations = load_annotations(annotations_path)

    if "pressure_filtered_kPa" in fields and "delta_kPa" in fields:
        filtered = np.asarray([_float_cell(row["pressure_filtered_kPa"]) for row in rows], dtype=np.float64)
        slow = np.asarray([_float_cell(row["baseline_slow_kPa"]) for row in rows], dtype=np.float64)
        delta = np.asarray([_float_cell(row["delta_kPa"]) for row in rows], dtype=np.float64)
        deriv = np.asarray([_float_cell(row["dpdt_filtered_kPa_s"]) for row in rows], dtype=np.float64)
        spread = np.asarray([_float_cell(row["rolling_spread_kPa"]) for row in rows], dtype=np.float64)
        air = np.asarray([row.get("air_state", "").strip() for row in rows], dtype=object)
        state = np.asarray([row.get("candidate_state", "").strip() for row in rows], dtype=object)
    else:
        filtered, slow, delta, deriv, spread, air, state, _ = _arrays_from_replay(
            time_s, pressure, seq, raw_adc, annotations, load_pipeline(run_dir)
        )

    pipeline = load_pipeline(run_dir)
    measured = measured_hz_from_times(time_s)
    if pipeline is None:
        pipeline = PipelineConfig()
        if math.isfinite(measured) and measured > 0:
            pipeline.sample_hz = measured
    pipeline.measured_hz = measured

    return PressureRun(
        run_dir=run_dir,
        samples_path=samples_path,
        events_path=events_path if events_path.is_file() else None,
        seq=seq,
        time_s=time_s,
        raw_adc=raw_adc,
        pressure_kPa=pressure,
        baseline_kPa=slow,
        residual_kPa=delta,
        threshold_kPa=np.full(pressure.shape, np.nan),
        dpdt_kPa_per_s=deriv,
        event_state=state,
        filtered_kPa=filtered,
        spread_kPa=spread,
        air_state=air,
        recorded_events=load_recorded_events(events_path),
        annotations=annotations,
        annotations_path=annotations_path if annotations_path.is_file() else None,
        pipeline=pipeline,
        measured_hz=measured,
    )


def redetect_events(
    run: PressureRun,
    config: PipelineConfig | None = None,
) -> list[DetectedEvent]:
    """Replay the gated ΔP / change-point detector on this file."""
    cfg = config if config is not None else run.pipeline
    _, _, _, _, _, _, _, events = _arrays_from_replay(
        run.time_s,
        run.pressure_kPa,
        run.seq,
        run.raw_adc,
        run.annotations,
        cfg,
    )
    return [boundary_to_detected(item, "redetected") for item in events]


def find_anomalies(
    run: PressureRun,
    events: list[DetectedEvent],
    min_duration_ms: float,
) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    seen_glitches: set[tuple] = set()
    seq_diff = np.diff(run.seq)
    gap_idx = np.where(seq_diff > 1)[0]
    for index in gap_idx:
        lost = int(seq_diff[index] - 1)
        anomalies.append(
            Anomaly(
                kind="seq_gap",
                time_s=float(run.time_s[index + 1]),
                detail=f"lost {lost} sample(s) before seq {int(run.seq[index + 1])}",
            )
        )

    rail = np.where((run.raw_adc <= 0) | (run.raw_adc >= ADC_MAX))[0]
    if rail.size:
        anomalies.append(
            Anomaly(
                kind="adc_rail",
                time_s=float(run.time_s[int(rail[0])]),
                detail=f"{rail.size} sample(s) at ADC 0 or {ADC_MAX}",
            )
        )

    for event in events:
        if event.duration_ms < min_duration_ms:
            key = (
                round(event.extreme_s, 3),
                event.type,
                round(event.duration_ms, 1),
            )
            if key in seen_glitches:
                continue
            seen_glitches.add(key)
            anomalies.append(
                Anomaly(
                    kind="short_glitch",
                    time_s=event.extreme_s,
                    detail=(
                        f"{event.type} {event.duration_ms:.1f} ms "
                        f"ΔP={event.amplitude_kPa:+.2f} kPa ({event.source})"
                    ),
                )
            )
    return anomalies


def confirmed_events(
    events: list[DetectedEvent],
    min_duration_ms: float,
) -> list[DetectedEvent]:
    return [event for event in events if event.duration_ms >= min_duration_ms]


def format_summary(
    run: PressureRun,
    redetected: list[DetectedEvent],
    min_duration_ms: float,
    air_line: str | None = None,
    annotation_lines: list[str] | None = None,
) -> str:
    duration = float(run.time_s[-1] - run.time_s[0])
    lost = int(np.sum(np.maximum(np.diff(run.seq) - 1, 0)))
    confirmed = confirmed_events(redetected, min_duration_ms)
    glitches = [event for event in redetected if event.duration_ms < min_duration_ms]
    lines = [
        f"Run: {run.run_dir}",
        f"Samples: {len(run.seq)}    duration: {duration:.3f} s    "
        f"t={run.time_s[0]:.3f}–{run.time_s[-1]:.3f} s    lost seq: {lost}",
    ]
    cfg = run.pipeline or PipelineConfig()
    cfg = cfg.copy()
    cfg.measured_hz = run.measured_hz
    lines.append(status_line(cfg, measured_hz=run.measured_hz))
    lines.append(
        f"Pressure: min {run.pressure_kPa.min():.2f} / "
        f"median {np.median(run.pressure_kPa):.2f} / "
        f"max {run.pressure_kPa.max():.2f} kPa"
    )
    if air_line:
        lines.append(air_line)
    steps = [event for event in confirmed if event.type == "STEP"]
    transients = [event for event in confirmed if event.type == "TRANSIENT"]
    lines.extend(
        [
            f"Recorded events.csv: {len(run.recorded_events)}",
            f"Redetected ≥{min_duration_ms:.0f} ms: {len(steps)} step(s), "
            f"{len(transients)} transient(s)    "
            f"short <{min_duration_ms:.0f} ms: {len(glitches)}",
        ]
    )
    if annotation_lines:
        lines.extend(annotation_lines)
    stats = stage_statistics(
        run.time_s,
        run.filtered_kPa if run.filtered_kPa.size else run.pressure_kPa,
        run.residual_kPa,
        run.dpdt_kPa_per_s,
        run.spread_kPa if run.spread_kPa.size else np.zeros_like(run.time_s),
        run.annotations,
        None,
    )
    lines.append(format_stage_table(stats))
    if confirmed:
        lines.append("Boundary events:")
        for event in confirmed:
            lines.append(
                f"  {event.type:10s}  t={event.extreme_s:.3f}s  "
                f"{event.baseline_kPa:.1f}→{event.extreme_pressure_kPa:.1f} kPa  "
                f"step={event.amplitude_kPa:+.2f}  "
                f"|dP/dt|={event.max_abs_dpdt_kPa_per_s:.1f}  "
                f"{event.duration_ms:.0f} ms  {event.drill_stage}"
            )
    return "\n".join(lines)


def _stride_view(values: np.ndarray, stride: int) -> np.ndarray:
    return values[::stride]


def _air_off_at(time_s: np.ndarray, mask_off: np.ndarray, t: float) -> bool:
    if mask_off.size == 0:
        return False
    index = int(np.searchsorted(time_s, t, side="left"))
    index = min(max(index, 0), int(mask_off.size) - 1)
    return bool(mask_off[index])


class PressureAnalysisWindow(QtWidgets.QWidget):
    def __init__(
        self,
        run: PressureRun,
        min_duration_ms: float,
        air_filter: str = "hide",
        auto_air: bool = False,
    ) -> None:
        super().__init__()
        self.run = run
        self.min_duration_ms = min_duration_ms
        self.redetected = redetect_events(run)
        self._initial_air_filter = normalize_air_filter_mode(air_filter)
        self._initial_auto_air = bool(auto_air)
        self.annotation_matches = []
        self._suspend_range = False
        self._shown_raw = np.asarray([], dtype=np.float64)
        self._shown_filt = np.asarray([], dtype=np.float64)
        self._shown_residual = np.asarray([], dtype=np.float64)
        self._shown_deriv = np.asarray([], dtype=np.float64)
        self._shown_overlay = None
        self._build()
        self.pipeline_widgets["from_config"](self._pipeline_for_run())
        self._refresh(reset_x=True)

    def _build(self) -> None:
        self.setWindowTitle("DENTOBOT Pressure Run Analysis")
        self.resize(1400, 900)

        self.open_button = QtWidgets.QPushButton("Open Run…")
        self.path_label = QtWidgets.QLabel()
        self.path_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(0.0, 5000.0)
        self.duration_spin.setDecimals(0)
        self.duration_spin.setSuffix(" ms")
        self.duration_spin.setValue(self.min_duration_ms)
        self.duration_spin.setToolTip(
            "Hide redetected events shorter than this from the confirmed table"
        )
        self.source_box = QtWidgets.QComboBox()
        self.source_box.addItems(["Redetected", "Recorded", "Both"])

        self.air_filter = QtWidgets.QComboBox()
        self.air_filter.addItem("Hide air-off")
        self.air_filter.addItem("Highlight air-off")
        self.air_filter.addItem("Show all")
        self.air_filter.setToolTip(
            "Air-off is the idle ~0 kPa cluster from the 2026-08-31 runs. "
            "Air-on is the ~225 kPa drill-in-air plateau. Hide drops those "
            "samples; highlight draws them grey. CSV is unchanged."
        )
        mode = self._initial_air_filter
        self.air_filter.setCurrentIndex(
            {"hide": 0, "highlight": 1, "all": 2}.get(mode, 0)
        )
        self.auto_air = QtWidgets.QCheckBox("Auto air gates")
        self.auto_air.setChecked(self._initial_auto_air)
        self.auto_air.setToolTip(
            "Estimate the 50 ms median hysteresis gates from this file. "
            "Off uses the 8 / 25 kPa split from today's drilling runs."
        )
        self.trace_mode = QtWidgets.QComboBox()
        self.trace_mode.addItem("Filtered")
        self.trace_mode.addItem("Raw + filtered")
        self.trace_mode.addItem("Raw")
        self.trace_mode.setToolTip(
            "Top plot: fast low-pass pressure, optional raw overlay, or raw."
        )
        self.plot_focus = QtWidgets.QComboBox()
        self.plot_focus.addItems(["All traces", "Pressure", "ΔP", "dP/dt"])
        self.plot_focus.setToolTip(
            "Show one trace at the full plot height. Double-click a plot "
            "to isolate it; double-click again for all three."
        )
        self.auto_y = QtWidgets.QCheckBox("Auto Y")
        self.auto_y.setChecked(True)
        self.auto_y.setToolTip(
            "Scale each Y axis to the visible time window so small steps "
            "are readable after a zoom."
        )
        self.fit_time_btn = QtWidgets.QPushButton("Fit time")
        self.fit_time_btn.setToolTip("Show the full recording on the time axis.")
        self.plots_only_btn = QtWidgets.QPushButton("Plots only")
        self.plots_only_btn.setCheckable(True)
        self.plots_only_btn.setShortcut(QtGui.QKeySequence("F11"))
        self.plots_only_btn.setToolTip(
            "Hide the tables so the traces fill the window. F11 toggles; "
            "Esc restores the tables."
        )

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.open_button)
        top.addWidget(self.path_label, 1)
        top.addWidget(QtWidgets.QLabel("Min duration"))
        top.addWidget(self.duration_spin)
        top.addWidget(QtWidgets.QLabel("Markers"))
        top.addWidget(self.source_box)
        top.addWidget(QtWidgets.QLabel("Air"))
        top.addWidget(self.air_filter)
        top.addWidget(self.auto_air)
        top.addWidget(QtWidgets.QLabel("Trace"))
        top.addWidget(self.trace_mode)
        top.addWidget(QtWidgets.QLabel("Show"))
        top.addWidget(self.plot_focus)
        top.addWidget(self.auto_y)
        top.addWidget(self.fit_time_btn)
        top.addWidget(self.plots_only_btn)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        pg.setConfigOptions(antialias=False)
        self.graphics = pg.GraphicsLayoutWidget()
        self.graphics.setMinimumHeight(280)
        self.graphics.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.pressure_plot = self.graphics.addPlot(row=0, col=0)
        self.pressure_plot.setLabel("left", "Filtered pressure", units="kPa")
        self.pressure_plot.showGrid(x=True, y=True, alpha=0.25)
        self.pressure_plot.addLegend()
        self._configure_plot(self.pressure_plot)
        self.pressure_curve = self.pressure_plot.plot(
            name="Raw",
            pen=pg.mkPen("w", width=2),
            connect="finite",
        )
        self.air_off_curve = self.pressure_plot.plot(
            name="Air off",
            pen=pg.mkPen((130, 130, 140), width=1),
            connect="finite",
        )
        self.filtered_curve = self.pressure_plot.plot(
            name="Filtered P",
            pen=pg.mkPen("#7fd0ff", width=2),
            connect="finite",
        )
        self._configure_curve(self.pressure_curve)
        self._configure_curve(self.air_off_curve)
        self._configure_curve(self.filtered_curve)
        self.step_scatter = pg.ScatterPlotItem(
            symbol="d",
            size=12,
            brush=pg.mkBrush("#f472b6"),
            name="Step",
        )
        self.transient_scatter = pg.ScatterPlotItem(
            symbol="o",
            size=10,
            brush=pg.mkBrush("#38bdf8"),
            name="Transient",
        )
        self.pressure_plot.addItem(self.step_scatter)
        self.pressure_plot.addItem(self.transient_scatter)
        self.annotation_marks = add_annotation_lines(self.pressure_plot)

        self.residual_plot = self.graphics.addPlot(row=1, col=0)
        self.residual_plot.setLabel("left", "ΔP", units="kPa")
        self.residual_plot.showGrid(x=True, y=True, alpha=0.25)
        self.residual_plot.setXLink(self.pressure_plot)
        self.residual_plot.showAxis("bottom", False)
        self._configure_plot(self.residual_plot)
        self.residual_curve = self.residual_plot.plot(
            pen=pg.mkPen("#fbbf24", width=2),
            connect="finite",
        )
        self.residual_zero = self.residual_plot.plot(
            pen=pg.mkPen((180, 180, 180), width=1, style=QtCore.Qt.PenStyle.DashLine),
        )
        self._configure_curve(self.residual_curve)

        self.dpdt_plot = self.graphics.addPlot(row=2, col=0)
        self.dpdt_plot.setLabel("left", "Filtered dP/dt", units="kPa/s")
        self.dpdt_plot.setLabel("bottom", "Elapsed time", units="s")
        self.dpdt_plot.showGrid(x=True, y=True, alpha=0.25)
        self.dpdt_plot.setXLink(self.pressure_plot)
        self._configure_plot(self.dpdt_plot)
        self.dpdt_curve = self.dpdt_plot.plot(
            pen=pg.mkPen("#fb7185", width=2),
            connect="finite",
        )
        self._configure_curve(self.dpdt_curve)
        grid = self.graphics.ci.layout
        grid.setRowStretchFactor(0, 3)
        grid.setRowStretchFactor(1, 2)
        grid.setRowStretchFactor(2, 2)
        self.pressure_plot.sigXRangeChanged.connect(self._on_x_range_changed)
        self.graphics.scene().sigMouseClicked.connect(self._on_plot_clicked)

        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Source",
                "Type",
                "Start s",
                "Extreme s",
                "End s",
                "Extreme kPa",
                "ΔP kPa",
                "Duration ms",
            ]
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.anomaly_box = QtWidgets.QPlainTextEdit()
        self.anomaly_box.setReadOnly(True)

        self.boundary_table = QtWidgets.QTableWidget(0, 7)
        self.boundary_table.setHorizontalHeaderLabels(
            ["Stage", "N", "Median P", "Std", "p90-p10", "Mean ΔP", "max|dP/dt|"]
        )
        self.boundary_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.boundary_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.boundary_table.verticalHeader().setVisible(False)
        self.boundary_table.horizontalHeader().setStretchLastSection(True)

        self.annotation_table = QtWidgets.QTableWidget(0, 7)
        self.annotation_table.setHorizontalHeaderLabels(
            [
                "Kind",
                "Stage",
                "Press s",
                "Latency ms",
                "Corrected s",
                "Step s",
                "ΔP kPa",
            ]
        )
        self.annotation_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.annotation_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.annotation_table.verticalHeader().setVisible(False)
        self.annotation_table.horizontalHeader().setStretchLastSection(True)

        plot_pane = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_pane)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addWidget(self.graphics, 1)

        self.tables_tabs = QtWidgets.QTabWidget()
        self.tables_tabs.addTab(self.table, "Events")
        self.tables_tabs.addTab(self.boundary_table, "Stage statistics")
        self.tables_tabs.addTab(self.annotation_table, "Annotations")
        self.tables_tabs.addTab(self.anomaly_box, "Anomalies")
        self.pipeline_page, self.pipeline_widgets = build_config_panel(
            sample_rate_enabled=False
        )
        self.pipeline_widgets["apply"].setText("Redetect with these filters")
        self.pipeline_widgets["apply"].setToolTip(
            "Replay the ΔP detector with the filter taus below. "
            "Sample rate is whatever this CSV already contains."
        )
        self.tables_tabs.addTab(self.pipeline_page, "Pipeline")

        self.tables_panel = QtWidgets.QWidget()
        tables_layout = QtWidgets.QVBoxLayout(self.tables_panel)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.addWidget(self.tables_tabs)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.splitter.addWidget(plot_pane)
        self.splitter.addWidget(self.tables_panel)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([720, 180])
        self.splitter.setChildrenCollapsible(False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.status_label)
        layout.addWidget(self.splitter, 1)

        self.open_button.clicked.connect(self._open_run)
        self.duration_spin.valueChanged.connect(self._refresh)
        self.source_box.currentIndexChanged.connect(self._refresh)
        self.air_filter.currentIndexChanged.connect(self._refresh)
        self.auto_air.toggled.connect(self._refresh)
        self.trace_mode.currentIndexChanged.connect(self._refresh)
        self.plot_focus.currentIndexChanged.connect(self._apply_plot_focus)
        self.auto_y.toggled.connect(self._apply_auto_y)
        self.fit_time_btn.clicked.connect(self._fit_time)
        self.plots_only_btn.toggled.connect(self._set_plots_only)
        self.table.itemSelectionChanged.connect(self._zoom_selected)
        self.annotation_table.itemSelectionChanged.connect(self._zoom_annotation)
        self.pipeline_widgets["apply"].clicked.connect(self._apply_redetect)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, self._restore_layout)
        self._apply_auto_y(True)

    def _pipeline_for_run(self) -> PipelineConfig:
        cfg = self.run.pipeline.copy() if self.run.pipeline is not None else PipelineConfig()
        cfg.measured_hz = self.run.measured_hz
        return cfg

    def _apply_redetect(self) -> None:
        cfg = self.pipeline_widgets["to_config"](self._pipeline_for_run())
        if self.run.pipeline is not None:
            cfg.sample_hz = self.run.pipeline.sample_hz
        elif math.isfinite(self.run.measured_hz) and self.run.measured_hz > 0:
            cfg.sample_hz = self.run.measured_hz
        else:
            cfg.sample_hz = 1000.0
        self.run.pipeline = cfg
        self.redetected = redetect_events(self.run, cfg)
        self.pipeline_widgets["from_config"](cfg)
        self._refresh()

    @staticmethod
    def _configure_plot(plot: pg.PlotItem) -> None:
        plot.setAutoVisible(y=True)
        plot.enableAutoRange(axis="y", enable=True)
        plot.getViewBox().setAspectLocked(False)
        plot.getViewBox().setMouseEnabled(x=True, y=True)

    @staticmethod
    def _configure_curve(curve: pg.PlotDataItem) -> None:
        curve.setClipToView(True)
        curve.setDownsampling(auto=True, method="peak")

    def _set_plots_only(self, on: bool) -> None:
        self.tables_panel.setVisible(not on)
        if on:
            self.plots_only_btn.setText("Show tables")
        else:
            self.plots_only_btn.setText("Plots only")

    def _restore_layout(self) -> None:
        if self.plots_only_btn.isChecked():
            self.plots_only_btn.setChecked(False)
            return
        if self.plot_focus.currentIndex() != 0:
            self.plot_focus.setCurrentIndex(0)

    def _apply_auto_y(self, on: bool) -> None:
        enabled = bool(on)
        for plot in (self.pressure_plot, self.residual_plot, self.dpdt_plot):
            plot.setAutoVisible(y=enabled)
            plot.enableAutoRange(axis="y", enable=enabled)

    def _apply_plot_focus(self) -> None:
        choice = self.plot_focus.currentText()
        named = {
            "Pressure": (self.pressure_plot, 0, 3),
            "ΔP": (self.residual_plot, 1, 2),
            "dP/dt": (self.dpdt_plot, 2, 2),
        }
        grid = self.graphics.ci.layout
        show_all = choice == "All traces"
        for name, (plot, row, stretch) in named.items():
            visible = show_all or name == choice
            plot.setVisible(visible)
            if visible:
                grid.setRowMaximumHeight(row, 1_000_000)
                grid.setRowPreferredHeight(row, 120)
                grid.setRowStretchFactor(row, stretch if show_all else 1)
            else:
                grid.setRowStretchFactor(row, 0)
                grid.setRowPreferredHeight(row, 0)
                grid.setRowMaximumHeight(row, 0)
        self.pressure_plot.showAxis("bottom", show_all or choice == "Pressure")
        self.residual_plot.showAxis("bottom", choice == "ΔP")
        self.dpdt_plot.showAxis("bottom", show_all or choice == "dP/dt")
        if choice == "ΔP":
            self.residual_plot.setLabel("bottom", "Elapsed time", units="s")
        else:
            self.residual_plot.setLabel("bottom", "")

    def _on_plot_clicked(self, event) -> None:
        if not event.double():
            return
        pos = event.scenePos()
        for name, plot in (
            ("Pressure", self.pressure_plot),
            ("ΔP", self.residual_plot),
            ("dP/dt", self.dpdt_plot),
        ):
            if plot.isVisible() and plot.sceneBoundingRect().contains(pos):
                if self.plot_focus.currentText() == name:
                    self.plot_focus.setCurrentIndex(0)
                else:
                    self.plot_focus.setCurrentText(name)
                return

    def _on_x_range_changed(self, *_args) -> None:
        if self._suspend_range:
            return
        self._update_traces()

    def _fit_time(self) -> None:
        self._reset_x_range()
        self._update_traces()

    def _reset_x_range(self) -> None:
        if self.run.time_s.size == 0:
            return
        span = max(5.0, float(self.run.time_s[-1] - self.run.time_s[0]))
        self._suspend_range = True
        try:
            self.pressure_plot.setXRange(
                float(self.run.time_s[0]),
                float(self.run.time_s[0]) + span,
                padding=0.02,
            )
        finally:
            self._suspend_range = False

    def _visible_index_slice(self) -> slice:
        t = self.run.time_s
        n = int(t.size)
        if n == 0:
            return slice(0, 0)
        fallback = slice(0, n, max(1, n // MAX_DISPLAY_POINTS))
        try:
            x0, x1 = self.pressure_plot.viewRange()[0]
        except Exception:
            return fallback
        if not math.isfinite(x0) or not math.isfinite(x1) or x1 <= x0:
            return fallback
        pad = max(0.01, 0.08 * (x1 - x0))
        i0 = int(np.searchsorted(t, x0 - pad, side="left"))
        i1 = int(np.searchsorted(t, x1 + pad, side="right"))
        i0 = max(0, min(i0, n))
        i1 = max(i0, min(i1, n))
        window = i1 - i0
        if window <= 0:
            return fallback
        return slice(i0, i1, max(1, window // MAX_DISPLAY_POINTS))

    def _update_traces(self) -> None:
        run = self.run
        if run.time_s.size == 0 or self._shown_raw.size == 0:
            return
        view = self._visible_index_slice()
        t = run.time_s[view]

        def take(arr: np.ndarray) -> np.ndarray:
            if arr.size != run.time_s.size:
                return np.full(t.shape, np.nan)
            return arr[view]

        shown = take(self._shown_raw)
        shown_filt = take(self._shown_filt)
        residual = take(self._shown_residual)
        deriv = take(self._shown_deriv)
        overlay = (
            None
            if self._shown_overlay is None
            else take(self._shown_overlay)
        )

        trace = self.trace_mode.currentText()
        if trace == "Raw":
            self.pressure_curve.setData(t, shown)
            self.pressure_curve.setPen(FULL_RAW_PEN)
            self.pressure_curve.setVisible(True)
            self.filtered_curve.setData([], [])
            self.filtered_curve.setVisible(False)
        elif trace == "Raw + filtered":
            self.pressure_curve.setData(t, shown)
            self.pressure_curve.setPen(DIM_RAW_PEN)
            self.pressure_curve.setVisible(True)
            self.filtered_curve.setData(t, shown_filt)
            self.filtered_curve.setVisible(True)
        else:
            self.pressure_curve.setData([], [])
            self.pressure_curve.setVisible(False)
            self.filtered_curve.setData(t, shown_filt)
            self.filtered_curve.setVisible(True)
        if overlay is None or not self.pressure_curve.isVisible():
            self.air_off_curve.setData([], [])
            self.air_off_curve.setVisible(False)
        else:
            self.air_off_curve.setData(t, overlay)
            self.air_off_curve.setVisible(True)
        self.residual_curve.setData(t, residual)
        self.residual_zero.setData(
            [float(run.time_s[0]), float(run.time_s[-1])],
            [0.0, 0.0],
        )
        self.dpdt_curve.setData(t, deriv)

    def _visible_events(self) -> list[DetectedEvent]:
        min_duration = float(self.duration_spin.value())
        source = self.source_box.currentText()
        events: list[DetectedEvent] = []
        if source in ("Redetected", "Both"):
            events.extend(confirmed_events(self.redetected, min_duration))
        if source in ("Recorded", "Both"):
            events.extend(confirmed_events(self.run.recorded_events, min_duration))
        events.sort(key=lambda event: (event.start_s, event.source, event.event_id))
        return events

    def _refresh(self, *args, reset_x: bool = False) -> None:
        run = self.run
        self.path_label.setText(str(run.run_dir))
        mode = normalize_air_filter_mode(self.air_filter.currentText())
        mask_off, off_kPa, on_kPa = air_state_for_series(
            run.time_s,
            run.pressure_kPa,
            auto=self.auto_air.isChecked(),
        )
        shown, overlay = apply_air_display(run.pressure_kPa, mask_off, mode)
        filt = run.filtered_kPa if run.filtered_kPa.size else run.pressure_kPa
        shown_filt, _ = apply_air_display(filt, mask_off, mode)
        residual, _ = apply_air_display(run.residual_kPa, mask_off, mode)
        deriv, _ = apply_air_display(run.dpdt_kPa_per_s, mask_off, mode)
        self._shown_raw = np.asarray(shown, dtype=np.float64)
        self._shown_filt = np.asarray(shown_filt, dtype=np.float64)
        self._shown_residual = np.asarray(residual, dtype=np.float64)
        self._shown_deriv = np.asarray(deriv, dtype=np.float64)
        self._shown_overlay = (
            None if overlay is None else np.asarray(overlay, dtype=np.float64)
        )
        if reset_x:
            self._reset_x_range()
        self._update_traces()
        set_annotation_lines(
            self.annotation_marks,
            run.annotations,
            float(run.time_s[0]),
            float(run.time_s[-1]),
        )
        self.annotation_matches = [
            match_annotation_dip(run.time_s, run.pressure_kPa, item)
            for item in run.annotations
        ]

        events = self._visible_events()
        steps = [event for event in events if event.type == "STEP"]
        transients = [event for event in events if event.type != "STEP"]
        if mode == "hide":
            steps = [
                event
                for event in steps
                if not _air_off_at(run.time_s, mask_off, event.extreme_s)
            ]
            transients = [
                event
                for event in transients
                if not _air_off_at(run.time_s, mask_off, event.extreme_s)
            ]
        self.step_scatter.setData(
            [event.extreme_s for event in steps],
            [event.extreme_pressure_kPa for event in steps],
        )
        self.transient_scatter.setData(
            [event.extreme_s for event in transients],
            [event.extreme_pressure_kPa for event in transients],
        )

        min_duration = float(self.duration_spin.value())
        air_line = air_state_summary(mask_off, off_kPa, on_kPa)
        cfg = self._pipeline_for_run()
        summary_line = format_summary(
            run,
            self.redetected,
            min_duration,
            air_line=air_line,
        ).split("\n")
        sample_line = summary_line[1] if len(summary_line) > 1 else ""
        self.status_label.setText(
            status_line(cfg, measured_hz=run.measured_hz)
            + "     "
            + sample_line
            + f"     {air_line}     "
            f"annotations: {len(run.annotations)}     "
            f"visible: {len(steps)} step(s), {len(transients)} other"
        )

        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                event.source,
                event.type,
                f"{event.start_s:.4f}",
                f"{event.extreme_s:.4f}",
                f"{event.end_s:.4f}",
                f"{event.extreme_pressure_kPa:.3f}",
                f"{event.amplitude_kPa:+.3f}",
                f"{event.duration_ms:.1f}",
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if event.is_dip:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#ff8a8a")))
                else:
                    item.setForeground(QtGui.QBrush(QtGui.QColor("#ffe08a")))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

        stats = stage_statistics(
            run.time_s,
            run.filtered_kPa if run.filtered_kPa.size else run.pressure_kPa,
            run.residual_kPa,
            run.dpdt_kPa_per_s,
            run.spread_kPa if run.spread_kPa.size else np.zeros_like(run.time_s),
            run.annotations,
        )
        self.boundary_table.setRowCount(len(stats))
        for row, item in enumerate(stats):
            values = [
                item.label,
                str(item.n),
                f"{item.median_p:.2f}",
                f"{item.std_p:.2f}",
                f"{item.spread:.2f}",
                f"{item.mean_delta:.2f}",
                f"{item.max_abs_dpdt:.1f}",
            ]
            for column, value in enumerate(values):
                self.boundary_table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        self.boundary_table.resizeColumnsToContents()

        self.annotation_table.setRowCount(len(run.annotations))
        for row, item in enumerate(run.annotations):
            found = self.annotation_matches[row]
            spec = item.spec
            values = [
                item.kind,
                spec.button if spec else item.label,
                f"{item.press_s:.3f}",
                f"{1000.0 * item.latency_s:.0f}",
                f"{item.corrected_s:.3f}",
                f"{found.dip_s:.3f}" if found is not None else "",
                f"{found.delta_kPa:+.1f}" if found is not None else "",
            ]
            color = spec.color if spec else "#ffffff"
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                cell.setForeground(QtGui.QBrush(QtGui.QColor(color)))
                self.annotation_table.setItem(row, column, cell)
        self.annotation_table.resizeColumnsToContents()

        anomalies = find_anomalies(run, self.redetected + run.recorded_events, min_duration)
        if anomalies:
            self.anomaly_box.setPlainText(
                "\n".join(
                    f"t={item.time_s:.3f}s  {item.kind}: {item.detail}"
                    for item in anomalies
                )
            )
        else:
            self.anomaly_box.setPlainText("No sequence gaps, ADC rails, or short glitches.")

    def _zoom_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        events = self._visible_events()
        event = events[rows[0].row()]
        pad = max(0.25, (event.end_s - event.start_s) * 0.25)
        self.pressure_plot.setXRange(event.start_s - pad, event.end_s + pad, padding=0.0)

    def _zoom_annotation(self) -> None:
        rows = self.annotation_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.run.annotations[rows[0].row()]
        found = self.annotation_matches[rows[0].row()]
        center = found.dip_s if found is not None else item.corrected_s
        pad = max(0.6, item.press_s - item.corrected_s + 0.4)
        self.pressure_plot.setXRange(center - pad, center + pad, padding=0.0)

    def _open_run(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Open pressure run folder",
            str(RUNS_ROOT),
        )
        if not directory:
            return
        try:
            self.run = load_run(directory)
        except (OSError, ValueError) as error:
            QtWidgets.QMessageBox.warning(self, "Could not load run", str(error))
            return
        self.redetected = redetect_events(self.run)
        self.pipeline_widgets["from_config"](self._pipeline_for_run())
        self._refresh(reset_x=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a pressure-monitor CSV run and inspect dips/anomalies."
    )
    parser.add_argument(
        "run",
        nargs="?",
        default=None,
        help="Run folder, samples.csv, or run_* name under pressure_runs/. Default: latest.",
    )
    parser.add_argument(
        "--min-duration-ms",
        type=float,
        default=DEFAULT_MIN_DURATION_MS,
        help="Confirmed-event duration floor (default: 20 ms).",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Print the summary and exit.",
    )
    parser.add_argument(
        "--air-filter",
        choices=["hide", "highlight", "all"],
        default="hide",
        help="GUI display filter for air-off samples (default: hide). CSV is unchanged.",
    )
    parser.add_argument(
        "--auto-air-thresholds",
        action="store_true",
        help=(
            "Estimate 50 ms median hysteresis gates from this run instead of "
            f"{AIR_OFF_ENTER_KPA:.0f}/{AIR_ON_ENTER_KPA:.0f} kPa."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run = load_run(args.run)
    redetected = redetect_events(run)
    mask_off, off_kPa, on_kPa = air_state_for_series(
        run.time_s,
        run.pressure_kPa,
        auto=args.auto_air_thresholds,
    )
    matches = [
        match_annotation_dip(run.time_s, run.pressure_kPa, item)
        for item in run.annotations
    ]
    print(
        format_summary(
            run,
            redetected,
            args.min_duration_ms,
            air_line=air_state_summary(mask_off, off_kPa, on_kPa),
            annotation_lines=format_annotation_lines(run.annotations, matches),
        )
    )
    anomalies = find_anomalies(
        run,
        redetected + run.recorded_events,
        args.min_duration_ms,
    )
    if anomalies:
        print("Anomalies:")
        for item in anomalies:
            print(f"  t={item.time_s:.3f}s  {item.kind}: {item.detail}")
    if args.no_gui:
        return 0

    app = QtWidgets.QApplication(sys.argv)
    window = PressureAnalysisWindow(
        run,
        args.min_duration_ms,
        air_filter=args.air_filter,
        auto_air=args.auto_air_thresholds,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
