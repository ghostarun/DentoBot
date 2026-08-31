import sys
import csv
import time
import signal
import bisect
from pathlib import Path
from datetime import datetime

import numpy as np
import serial
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

from pressure_signal import (
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
    ANNOTATION_COLUMNS,
    DEFAULT_CUE_INTERVAL_S,
    DEFAULT_LATENCY_S,
    ManualAnnotation,
    STAGES,
    StageBeeper,
    corrected_time,
    cue_index_after_label,
    next_cue_key,
    stage_spec,
)
from pressure_filter import (
    AIR_ON,
    EVENT_COLUMNS,
    SAMPLE_COLUMNS,
    PressureTracker,
)
from pressure_cli import apply_monitor_cli


# ============================================================
# CONFIGURATION
# ============================================================

PORT, BAUD = apply_monitor_cli()

ADC_BITS = 14
ADC_MAX = (1 << ADC_BITS) - 1       # 16383

# MPX5700 datasheet transfer function:
# Vout/Vs = 0.0012858 * P + 0.04
MPX_SCALE = 0.0012858
MPX_OFFSET = 0.04

# GUI
GUI_REFRESH_MS = 50
LIVE_WINDOW_S = 1.0
PIP_WIDTH = 460
PIP_HEIGHT = 250
PIP_MARGIN = 14

# Keep live display responsive during longer acquisitions.
# RAW CSV STILL STORES EVERY SAMPLE.
MAX_DISPLAY_POINTS = 40000


# ============================================================
# OUTPUT DIRECTORY / RECORDING
# ============================================================

RUNS_ROOT = (
    Path(__file__).resolve().parent
    / "pressure_runs"
)

recording = False

run_dir = None
samples_path = None
events_path = None
annotations_path = None

samples_file = None
events_file = None
annotations_file = None
samples_writer = None
events_writer = None
annotations_writer = None

annotation_id = 0
live_annotations = []
cue_index = 0
annotated_stage = "AIR_OFF"
auto_cue_running = False
last_cued_label = None


# ============================================================
# SERIAL
# ============================================================

print(f"Opening {PORT} at {BAUD}...")

try:
    ser = serial.Serial(
        PORT,
        BAUD,
        timeout=0
    )
except serial.SerialException as exc:
    print(
        f"Could not open {PORT} at {BAUD}: {exc}\n"
        "List ports:  python pressure_monitor.py --list-ports\n"
        "Then retry:  python pressure_monitor.py --port <device>"
    )
    raise SystemExit(1) from exc

time.sleep(1.0)
ser.reset_input_buffer()

print("Connected.")
print("Live display is idle until Start Recording + Cues.\n")


# ============================================================
# PRESSURE CONVERSION
# ============================================================

def adc_to_pressure(raw):
    ratio = raw / ADC_MAX

    pressure_kpa = (
        ratio - MPX_OFFSET
    ) / MPX_SCALE

    return pressure_kpa


# ============================================================
# SIGNAL STATE
# ============================================================

tracker = PressureTracker()

first_full_us = None
previous_micros = None
micros_wrap_offset = 0

last_seq = None
lost_samples = 0


# ============================================================
# LIVE PLOT STORAGE
# ============================================================

times = []
pressures = []
filtered = []
deltas = []
dpdts = []
spreads = []
air_states = []
event_times = []
event_deltas = []
event_kinds = []
last_sample = None


# ============================================================
# GUI
# ============================================================

pg.setConfigOptions(
    antialias=False
)

app = QtWidgets.QApplication(sys.argv)

main_window = QtWidgets.QWidget()
main_window.setWindowTitle(
    "DENTOBOT Pneumatic Pressure Monitor"
)
main_window.resize(1400, 920)

record_button = QtWidgets.QPushButton(
    "Start Recording + Cues"
)
record_button.setMinimumWidth(180)
record_button.setFixedHeight(36)

record_path_label = QtWidgets.QLabel(
    "Not recording"
)

controls = QtWidgets.QHBoxLayout()
controls.addWidget(record_button)
controls.addWidget(record_path_label, 1)

view_mode = QtWidgets.QComboBox()
view_mode.addItem("Overview + 1 s inset")
view_mode.addItem("1 s live only")
view_mode.setMinimumWidth(200)
view_mode.setToolTip(
    "Overview shows the whole run with a 1-second live inset. "
    "1 s live only fills the plot with the latest second."
)
controls.addWidget(QtWidgets.QLabel("View"))
controls.addWidget(view_mode)

air_filter = QtWidgets.QComboBox()
air_filter.addItem("Hide air-off")
air_filter.addItem("Highlight air-off")
air_filter.addItem("Show all")
air_filter.setMinimumWidth(170)
air_filter.setToolTip(
    "Air-off is the idle ~0 kPa cluster from the 2026-08-31 runs. "
    "Air-on is the ~225 kPa drill-in-air plateau. Hide drops those "
    "samples from the plot; highlight draws them grey."
)
controls.addWidget(QtWidgets.QLabel("Air"))
controls.addWidget(air_filter)

trace_mode = QtWidgets.QComboBox()
trace_mode.addItem("Filtered")
trace_mode.addItem("Raw + filtered")
trace_mode.addItem("Raw")
trace_mode.setMinimumWidth(180)
trace_mode.setToolTip(
    "Top plot: fast low-pass pressure (default), optional raw overlay, "
    "or raw only. ΔP and dP/dt always use the filtered pipeline. "
    "CSV still stores every raw sample."
)
controls.addWidget(QtWidgets.QLabel("Trace"))
controls.addWidget(trace_mode)

stage_banner = QtWidgets.QLabel()
stage_banner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
stage_banner.setMinimumHeight(52)

annotate_row = QtWidgets.QHBoxLayout()
annotate_buttons = {}
for spec in STAGES:
    button = QtWidgets.QPushButton(f"{spec.button}\n{spec.shortcut}")
    button.setMinimumHeight(58)
    button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    button.setStyleSheet(
        "QPushButton {"
        f" font-size: 15px; font-weight: 800; background: {spec.color};"
        " color: #111111; border-radius: 8px; padding: 8px 10px;"
        " border: 2px solid rgba(0,0,0,80);"
        "}"
        "QPushButton:pressed { background: #ffffff; }"
    )
    button.setToolTip(
        "Marks this tissue/air stage on the recording. "
        "The stored time is press minus operator latency, because the "
        "button is pressed after the driller notices the change."
    )
    annotate_row.addWidget(button, 1)
    annotate_buttons[spec.key] = button

cue_row = QtWidgets.QHBoxLayout()
cue_button = QtWidgets.QPushButton("CUE NEXT STAGE  (Space)")
cue_button.setMinimumHeight(42)
cue_button.setMinimumWidth(220)
cue_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
cue_button.setStyleSheet(
    "QPushButton {"
    " font-size: 15px; font-weight: 800; background: #111827; color: #f8fafc;"
    " border-radius: 8px; padding: 8px 16px; border: 2px solid #fbbf24;"
    "}"
    "QPushButton:pressed { background: #fbbf24; color: #111111; }"
)
cue_button.setToolTip(
    "Skip ahead now: flash + beep the next stage. Manual Space/click still "
    "works while the auto timer is running and resets the countdown. "
    "Start Recording + Cues loops AIR OFF → DRILL IN AIR → DENTIN → PULP."
)
cue_next_label = QtWidgets.QLabel()
cue_countdown_label = QtWidgets.QLabel("Cues: stopped")
cue_interval_spin = QtWidgets.QDoubleSpinBox()
cue_interval_spin.setRange(1.0, 600.0)
cue_interval_spin.setDecimals(0)
cue_interval_spin.setSingleStep(1.0)
cue_interval_spin.setValue(DEFAULT_CUE_INTERVAL_S)
cue_interval_spin.setSuffix(" s")
cue_interval_spin.setToolTip(
    "Seconds between automatic stage cues after Start Recording + Cues. "
    "Order: AIR OFF → DRILL IN AIR → DRILL IN DENTIN → DRILL IN PULP, then loop. "
    "Stop Recording stops the timer."
)
latency_spin = QtWidgets.QSpinBox()
latency_spin.setRange(0, 2500)
latency_spin.setSingleStep(50)
latency_spin.setValue(int(round(DEFAULT_LATENCY_S * 1000.0)))
latency_spin.setSuffix(" ms")
latency_spin.setToolTip(
    "Subtracted from the button-press time. Typical simple reaction is "
    "300–500 ms; raise this if the annotator lags the driller. The value "
    "at each press is stored in annotations.csv."
)
mute_beep = QtWidgets.QCheckBox("Mute beep")
cue_row.addWidget(cue_button)
cue_row.addWidget(cue_next_label, 1)
cue_row.addWidget(cue_countdown_label)
cue_row.addWidget(QtWidgets.QLabel("Cue every"))
cue_row.addWidget(cue_interval_spin)
cue_row.addWidget(QtWidgets.QLabel("Operator latency"))
cue_row.addWidget(latency_spin)
cue_row.addWidget(mute_beep)

window = pg.GraphicsLayoutWidget()

root_layout = QtWidgets.QVBoxLayout(
    main_window
)
root_layout.setContentsMargins(8, 8, 8, 8)
root_layout.addLayout(controls)
root_layout.addWidget(stage_banner)
root_layout.addLayout(annotate_row)
root_layout.addLayout(cue_row)
root_layout.addWidget(window, 1)

status = pg.LabelItem(
    justify="left"
)

window.addItem(
    status,
    row=0,
    col=0
)

plot = window.addPlot(
    row=1,
    col=0
)
delta_plot = window.addPlot(
    row=2,
    col=0
)
dpdt_plot = window.addPlot(
    row=3,
    col=0
)
spread_plot = window.addPlot(
    row=4,
    col=0
)
delta_plot.setXLink(plot)
dpdt_plot.setXLink(plot)
spread_plot.setXLink(plot)
window.ci.layout.setRowStretchFactor(1, 3)
window.ci.layout.setRowStretchFactor(2, 3)
window.ci.layout.setRowStretchFactor(3, 2)
window.ci.layout.setRowStretchFactor(4, 1)

plot.setLabel("left", "Filtered pressure", units="kPa")
plot.showGrid(x=True, y=True, alpha=0.25)
plot.addLegend()
plot.showAxis("bottom", False)

delta_plot.setLabel("left", "ΔP (fast − slow)", units="kPa")
delta_plot.showGrid(x=True, y=True, alpha=0.25)
delta_plot.showAxis("bottom", False)

dpdt_plot.setLabel("left", "Filtered dP/dt", units="kPa/s")
dpdt_plot.showGrid(x=True, y=True, alpha=0.25)
dpdt_plot.showAxis("bottom", False)

spread_plot.setLabel("left", "p90 − p10", units="kPa")
spread_plot.setLabel("bottom", "Elapsed time", units="s")
spread_plot.showGrid(x=True, y=True, alpha=0.25)

pressure_curve = plot.plot(
    name="Raw",
    pen=FULL_RAW_PEN,
    connect="finite"
)
air_off_curve = plot.plot(
    name="Air off",
    pen=pg.mkPen((130, 130, 140), width=1),
    connect="finite"
)
filtered_curve = plot.plot(
    name="Filtered P",
    pen=pg.mkPen("#7fd0ff", width=2),
    connect="finite"
)
annotation_lines = add_annotation_lines(plot)
delta_annotation_lines = add_annotation_lines(delta_plot)

delta_curve = delta_plot.plot(
    name="ΔP",
    pen=pg.mkPen("#fbbf24", width=2),
    connect="finite"
)
delta_zero = delta_plot.plot(
    pen=pg.mkPen((180, 180, 180), width=1, style=QtCore.Qt.PenStyle.DashLine),
)
step_scatter = pg.ScatterPlotItem(
    symbol="d",
    size=12,
    brush=pg.mkBrush("#f472b6"),
    name="Step",
)
transient_scatter = pg.ScatterPlotItem(
    symbol="o",
    size=10,
    brush=pg.mkBrush("#38bdf8"),
    name="Transient",
)
delta_plot.addItem(step_scatter)
delta_plot.addItem(transient_scatter)

dpdt_curve = dpdt_plot.plot(
    pen=pg.mkPen("#fb7185", width=2),
    connect="finite"
)
spread_curve = spread_plot.plot(
    pen=pg.mkPen("#a3e635", width=2),
    connect="finite"
)

live_region = pg.LinearRegionItem(
    values=(0.0, LIVE_WINDOW_S),
    movable=False,
    brush=pg.mkBrush(255, 179, 71, 40),
    pen=pg.mkPen("#ffb347", width=1)
)
live_region.setZValue(-10)
plot.addItem(live_region)

live_plot = pg.PlotWidget(
    parent=window
)
live_plot.setTitle("Live 1 s")
live_plot.setLabel(
    "left",
    "kPa"
)
live_plot.setLabel(
    "bottom",
    "s"
)
live_plot.showGrid(
    x=True,
    y=True,
    alpha=0.3
)
live_plot.setBackground("#15181e")
live_plot.setStyleSheet(
    "border: 2px solid #ffb347;"
)
live_plot.getPlotItem().hideButtons()
live_plot.setMenuEnabled(False)

live_pressure_curve = live_plot.plot(
    pen=DIM_RAW_PEN,
    connect="finite"
)
live_air_off_curve = live_plot.plot(
    pen=pg.mkPen((130, 130, 140), width=1),
    connect="finite"
)
live_filtered_curve = live_plot.plot(
    pen=pg.mkPen("#7fd0ff", width=2),
    connect="finite"
)

main_window.show()


# ============================================================
# SERIAL RECEIVE BUFFER
# ============================================================

rx_buffer = ""

last_flush = time.monotonic()


# ============================================================
# RECORDING CONTROL
# ============================================================

def update_record_controls():

    if recording:

        record_button.setText(
            "Stop Recording"
        )

        record_button.setStyleSheet(
            "QPushButton {"
            " font-size: 14px;"
            " font-weight: bold;"
            " padding: 6px 16px;"
            " background: #8b1e1e;"
            " color: white;"
            "}"
        )

        record_path_label.setText(
            f"Recording + cues every {cue_interval_spin.value():.0f} s: {run_dir}"
        )

    else:

        record_button.setText(
            "Start Recording + Cues"
        )

        record_button.setStyleSheet(
            "QPushButton {"
            " font-size: 14px;"
            " font-weight: bold;"
            " padding: 6px 16px;"
            " background: #1e6b3a;"
            " color: white;"
            "}"
        )

        record_path_label.setText(
            "Not recording"
        )


def close_recording_files():

    global recording
    global samples_file
    global events_file
    global annotations_file
    global samples_writer
    global events_writer
    global annotations_writer

    if samples_file is not None:

        try:
            samples_file.flush()
            samples_file.close()
        except Exception:
            pass

        samples_file = None
        samples_writer = None

    if events_file is not None:

        try:
            events_file.flush()
            events_file.close()
        except Exception:
            pass

        events_file = None
        events_writer = None

    if annotations_file is not None:

        try:
            annotations_file.flush()
            annotations_file.close()
        except Exception:
            pass

        annotations_file = None
        annotations_writer = None

    recording = False


def start_recording():

    global recording
    global run_dir
    global samples_path
    global events_path
    global annotations_path
    global samples_file
    global events_file
    global annotations_file
    global samples_writer
    global events_writer
    global annotations_writer
    global annotation_id
    global live_annotations
    global cue_index
    global annotated_stage

    if recording:
        return

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    run_dir = (
        RUNS_ROOT
        / f"run_{timestamp}"
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    samples_path = run_dir / "samples.csv"
    events_path = run_dir / "events.csv"
    annotations_path = run_dir / "annotations.csv"

    samples_file = open(
        samples_path,
        "w",
        newline=""
    )

    events_file = open(
        events_path,
        "w",
        newline=""
    )

    annotations_file = open(
        annotations_path,
        "w",
        newline=""
    )

    samples_writer = csv.writer(
        samples_file
    )

    events_writer = csv.writer(
        events_file
    )

    annotations_writer = csv.writer(
        annotations_file
    )

    samples_writer.writerow(
        SAMPLE_COLUMNS
    )

    events_writer.writerow(
        EVENT_COLUMNS
    )

    annotations_writer.writerow(
        ANNOTATION_COLUMNS
    )

    samples_file.flush()
    events_file.flush()
    annotations_file.flush()

    annotation_id = 0
    live_annotations = []
    cue_index = 0
    annotated_stage = "AIR_OFF"
    refresh_annotation_marks()
    update_stage_banner()

    recording = True

    print(
        f"Recording started:\n"
        f"{run_dir}\n"
        f"Auto cues every {cue_interval_spin.value():.0f} s: "
        "AIR OFF → DRILL IN AIR → DENTIN → PULP\n"
    )

    update_record_controls()
    start_auto_cues(fire_now=True)


def stop_recording():

    stop_auto_cues()

    if not recording:

        close_recording_files()
        update_record_controls()
        return

    saved_samples = samples_path
    saved_events = events_path
    saved_annotations = annotations_path

    close_recording_files()

    print(
        "\nRecording stopped."
    )

    print(
        f"Samples saved:\n"
        f"{saved_samples}"
    )

    print(
        f"\nEvents saved:\n"
        f"{saved_events}"
    )

    print(
        f"\nAnnotations saved:\n"
        f"{saved_annotations}\n"
    )

    update_record_controls()
    update_stage_banner()


def toggle_recording():

    if recording:
        stop_recording()
    else:
        start_recording()


record_button.clicked.connect(
    toggle_recording
)

update_record_controls()


# ============================================================
# STAGE CUES AND MANUAL ANNOTATIONS
# ============================================================

beeper = StageBeeper(main_window)


def current_sample_clock():
    if times:
        seq = last_seq if last_seq is not None else -1
        return float(times[-1]), float(pressures[-1]), int(seq)
    return 0.0, float("nan"), -1


def refresh_annotation_marks():
    set_annotation_lines(annotation_lines, live_annotations)
    set_annotation_lines(delta_annotation_lines, live_annotations)


def update_stage_banner():
    annotated = stage_spec(annotated_stage)
    next_key = next_cue_key(cue_index)[0]
    nxt = stage_spec(next_key)
    rec = "REC" if recording else "not recording"
    stage_banner.setText(
        f"ANNOTATED  {annotated.button}      ·      CUE NEXT  {nxt.button}      ·      {rec}"
    )
    stage_banner.setStyleSheet(
        "QLabel {"
        f" background: {annotated.color}; color: #111111;"
        " font-size: 20px; font-weight: 800; padding: 8px 12px;"
        " border-radius: 8px;"
        "}"
    )
    cue_next_label.setText(f"Next cue:  {nxt.button}")
    cue_next_label.setStyleSheet(
        f"QLabel {{ color: {nxt.color}; font-size: 16px; font-weight: 700; padding: 4px 10px; }}"
    )


def flash_stage_banner(text, color):
    stage_banner.setText(text)
    stage_banner.setStyleSheet(
        "QLabel {"
        " background: #ffffff; color: #111111;"
        " font-size: 26px; font-weight: 900; padding: 8px 12px;"
        " border-radius: 8px; border: 3px solid #111111;"
        "}"
    )
    QtCore.QTimer.singleShot(
        140,
        lambda: stage_banner.setStyleSheet(
            "QLabel {"
            f" background: {color}; color: #111111;"
            " font-size: 26px; font-weight: 900; padding: 8px 12px;"
            " border-radius: 8px;"
            "}"
        ),
    )
    QtCore.QTimer.singleShot(1100, update_stage_banner)


def persist_annotation(item):
    if (
        recording
        and annotations_writer is not None
        and annotations_file is not None
    ):
        annotations_writer.writerow(
            [
                item.event_id,
                item.kind,
                item.label,
                f"{item.press_s:.6f}",
                f"{item.latency_s:.4f}",
                f"{item.corrected_s:.6f}",
                f"{item.pressure_kPa:.4f}" if item.pressure_kPa == item.pressure_kPa else "",
                item.seq,
            ]
        )
        annotations_file.flush()
        return True
    return False


def annotate_stage(label):
    global annotation_id
    global annotated_stage
    global cue_index
    global live_annotations

    spec = stage_spec(label)
    press_s, pressure, seq = current_sample_clock()
    t_min = float(times[0]) if times else 0.0
    latency = latency_spin.value() / 1000.0
    annotation_id += 1
    item = ManualAnnotation(
        event_id=annotation_id,
        kind="annotate",
        label=label,
        press_s=press_s,
        latency_s=latency,
        corrected_s=corrected_time(press_s, latency, t_min),
        pressure_kPa=pressure,
        seq=seq,
    )
    live_annotations.append(item)
    annotated_stage = label
    if not auto_cue_running:
        following = cue_index_after_label(label)
        if following is not None:
            cue_index = following
    beeper.muted = mute_beep.isChecked()
    beeper.play(label)
    saved = persist_annotation(item)
    refresh_annotation_marks()
    note = "" if saved else "  ·  NOT SAVED (start recording)"
    flash_stage_banner(f"{spec.button}{note}", spec.color)
    print(
        f"Annotate {spec.button}: press={press_s:.3f}s  "
        f"latency={1000.0 * latency:.0f} ms  corrected={item.corrected_s:.3f}s"
        f"{'' if saved else ' (not recording)'}"
    )


def cue_next_stage(source="manual"):
    global annotation_id
    global cue_index
    global live_annotations

    if source is True or source is False:
        source = "manual"

    key, cue_index = next_cue_key(cue_index)
    spec = stage_spec(key)
    press_s, pressure, seq = current_sample_clock()
    annotation_id += 1
    item = ManualAnnotation(
        event_id=annotation_id,
        kind="cue",
        label=key,
        press_s=press_s,
        latency_s=0.0,
        corrected_s=press_s,
        pressure_kPa=pressure,
        seq=seq,
    )
    live_annotations.append(item)
    beeper.muted = mute_beep.isChecked()
    beeper.play(key)
    saved = persist_annotation(item)
    refresh_annotation_marks()
    highlight_cued_button(key)
    note = "" if saved else "  ·  cue only"
    flash_stage_banner(f"CHANGE TO   {spec.button}{note}", spec.color)
    origin = "auto" if source == "auto" else "manual"
    print(
        f"Cue {spec.button} at {press_s:.3f}s ({origin})"
        f"{'' if saved else ' (not recording)'}"
    )
    if source != "auto":
        restart_cue_interval()
    update_cue_countdown()


def cue_interval_ms():
    return max(1000, int(round(float(cue_interval_spin.value()) * 1000.0)))


def highlight_cued_button(label):
    global last_cued_label
    last_cued_label = label
    for key, button in annotate_buttons.items():
        spec = stage_spec(key)
        border = "5px solid #111111" if key == label else "2px solid rgba(0,0,0,80)"
        button.setStyleSheet(
            "QPushButton {"
            f" font-size: 15px; font-weight: 800; background: {spec.color};"
            " color: #111111; border-radius: 8px; padding: 8px 10px;"
            f" border: {border};"
            "}"
            "QPushButton:pressed { background: #ffffff; }"
        )


def update_cue_countdown():
    if not auto_cue_running:
        cue_countdown_label.setText("Cues: stopped")
        return
    remain_s = max(0.0, cue_timer.remainingTime() / 1000.0)
    nxt = stage_spec(next_cue_key(cue_index)[0])
    cue_countdown_label.setText(
        f"Next auto cue in {remain_s:.1f} s → {nxt.button}"
    )
    cue_countdown_label.setStyleSheet(
        f"QLabel {{ color: {nxt.color}; font-size: 15px; font-weight: 700; padding: 4px 8px; }}"
    )


def start_auto_cues(fire_now=True):
    global auto_cue_running
    auto_cue_running = True
    cue_timer.setInterval(cue_interval_ms())
    cue_timer.start()
    cue_countdown_timer.start()
    if fire_now:
        cue_next_stage(source="auto")
    update_cue_countdown()
    update_record_controls()


def stop_auto_cues():
    global auto_cue_running
    auto_cue_running = False
    cue_timer.stop()
    cue_countdown_timer.stop()
    cue_countdown_label.setText("Cues: stopped")
    cue_countdown_label.setStyleSheet("QLabel { font-size: 15px; padding: 4px 8px; }")


def restart_cue_interval():
    if not auto_cue_running:
        return
    cue_timer.start(cue_interval_ms())
    update_cue_countdown()


def on_cue_interval_changed(_value=None):
    if auto_cue_running:
        restart_cue_interval()
        update_record_controls()


cue_timer = QtCore.QTimer(main_window)
cue_timer.setSingleShot(False)
cue_timer.timeout.connect(lambda: cue_next_stage(source="auto"))

cue_countdown_timer = QtCore.QTimer(main_window)
cue_countdown_timer.setInterval(200)
cue_countdown_timer.timeout.connect(update_cue_countdown)

cue_interval_spin.valueChanged.connect(on_cue_interval_changed)

for spec in STAGES:
    annotate_buttons[spec.key].clicked.connect(
        lambda checked=False, key=spec.key: annotate_stage(key)
    )
    shortcut = QtGui.QShortcut(
        QtGui.QKeySequence(spec.shortcut),
        main_window,
    )
    shortcut.activated.connect(
        lambda key=spec.key: annotate_stage(key)
    )

cue_button.clicked.connect(
    lambda checked=False: cue_next_stage(source="manual")
)
cue_shortcut = QtGui.QShortcut(
    QtGui.QKeySequence("Space"),
    main_window,
)
cue_shortcut.activated.connect(
    lambda: cue_next_stage(source="manual")
)
mute_beep.toggled.connect(
    lambda checked: setattr(beeper, "muted", bool(checked))
)
update_stage_banner()


# ============================================================
# SAMPLE PROCESSING
# ============================================================

def process_sample(seq, micros_value, raw):

    global first_full_us
    global previous_micros
    global micros_wrap_offset
    global last_seq
    global lost_samples
    global recording
    global samples_writer
    global events_writer
    global events_file
    global last_sample

    if last_seq is not None:

        expected = last_seq + 1

        if seq > expected:
            lost_samples += seq - expected

    last_seq = seq

    if previous_micros is not None:

        if micros_value < previous_micros:
            micros_wrap_offset += 2**32

    previous_micros = micros_value

    full_us = (
        micros_wrap_offset
        + micros_value
    )

    if first_full_us is None:
        first_full_us = full_us

    t = (
        full_us - first_full_us
    ) / 1_000_000.0

    pressure = adc_to_pressure(raw)
    sample = tracker.update(
        t,
        pressure,
        seq,
        raw,
        annotated_stage,
    )
    last_sample = sample

    if (
        recording
        and samples_writer is not None
    ):
        samples_writer.writerow(sample.csv_row())

    if sample.event is not None:
        event = sample.event
        event_times.append(event.extreme_s)
        event_deltas.append(event.peak_delta_kPa)
        event_kinds.append(event.type)
        if recording and events_writer is not None:
            events_writer.writerow(event.csv_row())
            if events_file is not None:
                events_file.flush()
        print(
            f"{event.type}  t={event.extreme_s:.4f}s  "
            f"{event.drill_stage}  "
            f"P {event.p_before_kPa:.1f}->{event.p_after_kPa:.1f}  "
            f"step={event.step_kPa:+.2f} kPa  "
            f"dP/dt={event.peak_dpdt_kPa_s:.1f}  "
            f"{event.duration_ms:.0f} ms"
        )

    times.append(t)
    pressures.append(pressure)
    filtered.append(sample.pressure_filtered_kPa)
    deltas.append(sample.delta_kPa)
    dpdts.append(sample.dpdt_filtered_kPa_s)
    spreads.append(sample.rolling_spread_kPa)
    air_states.append(sample.air_state)


# ============================================================
# LIVE WINDOW / INSET
# ============================================================

def live_window_start_index():

    if not times:
        return 0

    start_t = times[-1] - LIVE_WINDOW_S

    return bisect.bisect_left(
        times,
        start_t
    )


def padded_y_range(values, min_span=4.0):

    arr = np.asarray(values, dtype=np.float64)
    finite = arr[np.isfinite(arr)]

    if finite.size == 0:
        return -2.0, 12.0

    lo = float(finite.min())
    hi = float(finite.max())
    span = hi - lo

    if span < min_span:

        mid = 0.5 * (lo + hi)
        lo = mid - 0.5 * min_span
        hi = mid + 0.5 * min_span

    pad = 0.08 * (hi - lo)

    return (
        lo - pad,
        hi + pad
    )


def _air_filter_mode():

    return normalize_air_filter_mode(
        air_filter.currentText()
    )


def _trace_mode():

    return trace_mode.currentText()


def _slice_series(values, start_i, stride):
    return np.asarray(values[start_i::stride], dtype=np.float64)


def _nan_unless(values, keep):
    out = np.asarray(values, dtype=np.float64).copy()
    if keep.size != out.size:
        return out
    out[~keep] = np.nan
    return out


def set_linked_curves(start_i, stride=1):

    display_t = _slice_series(times, start_i, stride)
    raw = _slice_series(pressures, start_i, stride)
    filt = _slice_series(filtered, start_i, stride)
    delta = _slice_series(deltas, start_i, stride)
    deriv = _slice_series(dpdts, start_i, stride)
    spread = _slice_series(spreads, start_i, stride)
    states = np.asarray(air_states[start_i::stride], dtype=object)
    off = states == "AIR_OFF"
    on = states == AIR_ON
    mode = _air_filter_mode()
    shown_raw, overlay = apply_air_display(raw, off, mode)
    shown_filt, _ = apply_air_display(filt, off, mode)
    delta_on = _nan_unless(delta, on)
    deriv_on = _nan_unless(deriv, on)
    spread_on = _nan_unless(spread, on)

    trace = _trace_mode()
    if trace == "Raw":
        pressure_curve.setData(display_t, shown_raw)
        pressure_curve.setPen(FULL_RAW_PEN)
        pressure_curve.setVisible(True)
        filtered_curve.setData([], [])
        filtered_curve.setVisible(False)
        y_p = shown_raw
    elif trace == "Raw + filtered":
        pressure_curve.setData(display_t, shown_raw)
        pressure_curve.setPen(DIM_RAW_PEN)
        pressure_curve.setVisible(True)
        filtered_curve.setData(display_t, shown_filt)
        filtered_curve.setVisible(True)
        y_p = shown_filt
    else:
        pressure_curve.setData([], [])
        pressure_curve.setVisible(False)
        filtered_curve.setData(display_t, shown_filt)
        filtered_curve.setVisible(True)
        y_p = shown_filt

    if overlay is None:
        air_off_curve.setData([], [])
        air_off_curve.setVisible(False)
    else:
        air_off_curve.setData(display_t, overlay)
        air_off_curve.setVisible(True)

    delta_curve.setData(display_t, delta_on)
    if display_t.size:
        delta_zero.setData([float(display_t[0]), float(display_t[-1])], [0.0, 0.0])
    dpdt_curve.setData(display_t, deriv_on)
    spread_curve.setData(display_t, spread_on)

    start_t = times[start_i]
    latest = times[-1]
    steps_t = []
    steps_y = []
    trans_t = []
    trans_y = []
    for event_t, event_y, kind in zip(event_times, event_deltas, event_kinds):
        if event_t < start_t:
            continue
        if kind == "STEP":
            steps_t.append(event_t)
            steps_y.append(event_y)
        else:
            trans_t.append(event_t)
            trans_y.append(event_y)
    step_scatter.setData(steps_t, steps_y)
    transient_scatter.setData(trans_t, trans_y)
    set_annotation_lines(annotation_lines, live_annotations, start_t, latest)
    set_annotation_lines(delta_annotation_lines, live_annotations, start_t, latest)
    return y_p, delta_on, deriv_on, spread_on


def update_live_inset(start_i):

    display_t = np.asarray(times[start_i:], dtype=np.float64)
    raw = np.asarray(pressures[start_i:], dtype=np.float64)
    filt = np.asarray(filtered[start_i:], dtype=np.float64)
    states = np.asarray(air_states[start_i:], dtype=object)
    off = states == "AIR_OFF"
    shown_raw, overlay = apply_air_display(raw, off, _air_filter_mode())
    shown_filt, _ = apply_air_display(filt, off, _air_filter_mode())
    live_pressure_curve.setData(display_t, shown_raw)
    live_filtered_curve.setData(display_t, shown_filt)
    if overlay is None:
        live_air_off_curve.setData([], [])
        live_air_off_curve.setVisible(False)
    else:
        live_air_off_curve.setData(display_t, overlay)
        live_air_off_curve.setVisible(True)

    start_t = times[start_i]
    latest = times[-1]
    live_plot.setXRange(start_t, latest, padding=0.02)
    y_lo, y_hi = padded_y_range(np.concatenate([shown_raw, shown_filt]))
    live_plot.setYRange(y_lo, y_hi, padding=0.0)
    live_region.setRegion((start_t, latest))


def place_live_inset():

    if view_mode.currentIndex() != 0:

        live_plot.hide()
        return

    live_plot.show()

    rect = window.rect()

    live_plot.setGeometry(
        max(
            PIP_MARGIN,
            rect.width() - PIP_WIDTH - PIP_MARGIN
        ),
        max(
            PIP_MARGIN,
            rect.height() - PIP_HEIGHT - PIP_MARGIN
        ),
        PIP_WIDTH,
        PIP_HEIGHT
    )

    live_plot.raise_()


class _InsetResizeFilter(QtCore.QObject):

    def eventFilter(self, watched, event):

        if event.type() == QtCore.QEvent.Type.Resize:

            place_live_inset()

        return False


_inset_resize_filter = _InsetResizeFilter(window)
window.installEventFilter(_inset_resize_filter)
place_live_inset()


# ============================================================
# GUI / SERIAL UPDATE
# ============================================================

def update():

    global rx_buffer
    global last_flush

    if not ser.is_open:
        return

    try:
        waiting = ser.in_waiting
    except (
        TypeError,
        OSError,
        serial.SerialException
    ):
        return

    if waiting:

        chunk = ser.read(
            waiting
        ).decode(
            errors="ignore"
        )

        rx_buffer += chunk

        lines = rx_buffer.split("\n")

        rx_buffer = lines[-1]

        for line in lines[:-1]:

            line = line.strip()

            if not line:
                continue

            if line.startswith("seq"):
                continue

            try:

                seq_text, us_text, raw_text = (
                    line.split(",")
                )

                process_sample(
                    int(seq_text),
                    int(us_text),
                    int(raw_text)
                )

            except ValueError:
                continue


    # --------------------------------------------------------
    # Update plot
    # --------------------------------------------------------

    if times:

        latest_t = times[-1]
        start_i = live_window_start_index()
        live_only = view_mode.currentIndex() == 1

        if live_only:
            live_plot.hide()
            live_region.hide()
            y_p, y_d, y_v, y_s = set_linked_curves(start_i, stride=1)
            plot.setXRange(times[start_i], latest_t, padding=0.02)
        else:
            live_region.show()
            n = len(times)
            stride = max(1, n // MAX_DISPLAY_POINTS)
            y_p, y_d, y_v, y_s = set_linked_curves(0, stride=stride)
            plot.setXRange(0, max(5.0, latest_t), padding=0.01)
            update_live_inset(start_i)
            place_live_inset()

        plot.setYRange(*padded_y_range(y_p, min_span=8.0), padding=0.0)
        delta_plot.setYRange(*padded_y_range(y_d, min_span=4.0), padding=0.0)
        dpdt_plot.setYRange(*padded_y_range(y_v, min_span=20.0), padding=0.0)
        spread_plot.setYRange(*padded_y_range(y_s, min_span=2.0), padding=0.0)

        rec_label = "REC" if recording else "Idle"
        sample = last_sample
        gate = "ARMED" if sample.armed else sample.air_state.replace("AIR_", "")
        status.setText(
            f"<b>{rec_label}</b>     "
            f"<b>P</b> {sample.pressure_filtered_kPa:.1f} kPa     "
            f"<b>ΔP</b> {sample.delta_kPa:+.2f}     "
            f"<b>dP/dt</b> {sample.dpdt_filtered_kPa_s:.0f}     "
            f"<b>spread</b> {sample.rolling_spread_kPa:.1f}     "
            f"<b>Air</b> {sample.air_state.replace('AIR_', '')}     "
            f"<b>Stage</b> {sample.drill_stage}     "
            f"<b>{gate}</b>     "
            f"<b>noise</b> {sample.rolling_noise_kPa:.2f}     "
            f"<b>Lost</b> {lost_samples}     "
            f"<b>Events</b> {len(event_times)}"
        )


    # --------------------------------------------------------
    # Flush data every ~1 second
    # --------------------------------------------------------

    now = time.monotonic()

    if (
        recording
        and samples_file is not None
        and now - last_flush >= 1.0
    ):

        samples_file.flush()

        last_flush = now


# ============================================================
# CLEANUP
# ============================================================

def cleanup():

    print("\nStopping acquisition...")

    try:
        timer.stop()
    except NameError:
        pass

    try:
        stop_recording()
    finally:

        if ser.is_open:

            try:
                ser.close()
            except Exception:
                pass


app.aboutToQuit.connect(
    cleanup
)

signal.signal(
    signal.SIGINT,
    lambda *args: app.quit()
)


def on_view_mode_changed():

    place_live_inset()
    update()


view_mode.currentIndexChanged.connect(
    on_view_mode_changed
)
air_filter.currentIndexChanged.connect(
    on_view_mode_changed
)
trace_mode.currentIndexChanged.connect(
    on_view_mode_changed
)


timer = QtCore.QTimer()

timer.timeout.connect(
    update
)

timer.start(
    GUI_REFRESH_MS
)


sys.exit(
    app.exec()
)