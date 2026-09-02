"""Acquisition and host-filter constants for the MPX5700 pressure bench.

Sensing and review only. Does not command hardware.

Default 1000 Hz comes from NXP MPX5700 Rev 10: typical response time
tR = 1.0 ms (10-90%), so analog bandwidth is about 350 Hz. 1 kHz is ~3x
that bandwidth. 100 Hz would undersample vibration; above ~1500 Hz the
460800 baud CSV lines start to crowd USB.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np

PIPELINE_FILENAME = "pipeline.json"

SENSOR_NAME = "MPX5700"
ANALOG_PIN = "A0"
ADC_BITS = 14
BAUD = 460800
SAMPLE_HZ_DEFAULT = 1000.0
SAMPLE_HZ_MIN = 200.0
SAMPLE_HZ_MAX = 1500.0
PRESSURE_MIN_KPA = 0.0
PRESSURE_MAX_KPA = 700.0
VS_V = 5.0
RESPONSE_TIME_MS = 1.0
# Vout/Vs = mpx_scale * P_kPa + mpx_offset  (NXP MPX5700 Rev 10)
MPX_SCALE = 0.0012858
MPX_OFFSET = 0.04
MEDIAN_WINDOW = 5
FAST_TAU_S = 0.015
SLOW_TAU_S = 0.40
DERIVATIVE_TAU_S = 0.020

DATASHEET_NOTE = (
    "NXP MPX5700 Rev 10: 0–700 kPa, Vs=5.0 V, tR typ. 1.0 ms (10–90%) "
    "→ analog BW ~350 Hz. Default fs=1000 Hz is ~3× that bandwidth. "
    "14-bit ADC on A0. Transfer: Vout/Vs = 0.0012858·P + 0.04."
)


def clamp_sample_hz(hz: float) -> float:
    return float(min(SAMPLE_HZ_MAX, max(SAMPLE_HZ_MIN, hz)))


def analog_bandwidth_hz(response_time_ms: float = RESPONSE_TIME_MS) -> float:
    if response_time_ms <= 0.0:
        return float("nan")
    return 0.35 / (response_time_ms / 1000.0)


def adc_max(bits: int = ADC_BITS) -> int:
    return (1 << int(bits)) - 1


@dataclass
class PipelineConfig:
    sample_hz: float = SAMPLE_HZ_DEFAULT
    adc_bits: int = ADC_BITS
    analog_pin: str = ANALOG_PIN
    sensor: str = SENSOR_NAME
    pressure_min_kPa: float = PRESSURE_MIN_KPA
    pressure_max_kPa: float = PRESSURE_MAX_KPA
    vs_v: float = VS_V
    response_time_ms: float = RESPONSE_TIME_MS
    mpx_scale: float = MPX_SCALE
    mpx_offset: float = MPX_OFFSET
    median_window: int = MEDIAN_WINDOW
    fast_tau_s: float = FAST_TAU_S
    slow_tau_s: float = SLOW_TAU_S
    derivative_tau_s: float = DERIVATIVE_TAU_S
    baud: int = BAUD
    measured_hz: float = float("nan")

    def __post_init__(self) -> None:
        self.sample_hz = clamp_sample_hz(float(self.sample_hz))
        self.adc_bits = int(self.adc_bits)
        self.median_window = max(1, int(self.median_window))
        self.fast_tau_s = max(0.001, float(self.fast_tau_s))
        self.slow_tau_s = max(0.001, float(self.slow_tau_s))
        self.derivative_tau_s = max(0.001, float(self.derivative_tau_s))
        self.mpx_scale = float(self.mpx_scale)
        self.mpx_offset = float(self.mpx_offset)

    @property
    def adc_max(self) -> int:
        return adc_max(self.adc_bits)

    @property
    def analog_bandwidth_hz(self) -> float:
        return analog_bandwidth_hz(self.response_time_ms)

    def adc_to_pressure(self, raw: float) -> float:
        ratio = float(raw) / float(self.adc_max)
        return (ratio - self.mpx_offset) / self.mpx_scale

    def reset_sensor_to_datasheet(self) -> None:
        self.mpx_scale = MPX_SCALE
        self.mpx_offset = MPX_OFFSET
        self.pressure_min_kPa = PRESSURE_MIN_KPA
        self.pressure_max_kPa = PRESSURE_MAX_KPA
        self.vs_v = VS_V
        self.response_time_ms = RESPONSE_TIME_MS
        self.sensor = SENSOR_NAME
        self.adc_bits = ADC_BITS
        self.analog_pin = ANALOG_PIN

    def copy(self) -> "PipelineConfig":
        return PipelineConfig(**asdict(self))

    def to_json_dict(self) -> dict:
        payload = asdict(self)
        payload["analog_bandwidth_hz"] = self.analog_bandwidth_hz
        payload["datasheet"] = DATASHEET_NOTE
        return payload

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def from_mapping(cls, data: dict) -> "PipelineConfig":
        allowed = {item.name for item in fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in allowed}
        return cls(**kwargs)

    @classmethod
    def load(cls, path: Path) -> "PipelineConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a JSON object")
        return cls.from_mapping(data)


def pipeline_path(run_dir: Path) -> Path:
    return Path(run_dir) / PIPELINE_FILENAME


def load_pipeline(run_dir: Path) -> PipelineConfig | None:
    path = pipeline_path(run_dir)
    if not path.is_file():
        return None
    try:
        return PipelineConfig.load(path)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return None


def measured_hz_from_times(time_s: np.ndarray) -> float:
    t = np.asarray(time_s, dtype=np.float64)
    if t.size < 3:
        return float("nan")
    dt = np.diff(t)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return float("nan")
    median = float(np.median(dt))
    if median <= 0:
        return float("nan")
    return 1.0 / median


def format_hz(hz: float, digits: int = 0) -> str:
    if hz is None or not math.isfinite(float(hz)) or float(hz) <= 0:
        return "n/a"
    if digits <= 0:
        return f"{hz:.0f} Hz"
    return f"{hz:.{digits}f} Hz"


def fs_mismatch(set_hz: float, measured_hz: float, frac: float = 0.10) -> bool:
    if not math.isfinite(set_hz) or not math.isfinite(measured_hz):
        return False
    if set_hz <= 0 or measured_hz <= 0:
        return False
    return abs(measured_hz - set_hz) / set_hz > frac


def status_line(
    config: PipelineConfig,
    *,
    measured_hz: float | None = None,
    extra: str = "",
) -> str:
    meas = config.measured_hz if measured_hz is None else measured_hz
    warn = ""
    if fs_mismatch(config.sample_hz, meas):
        warn = "  fs MISMATCH (flash paced firmware or check USB)"
    parts = [
        f"set fs {format_hz(config.sample_hz)}",
        f"meas {format_hz(meas)}",
        f"{config.adc_bits}-bit",
        config.sensor,
        f"{config.pressure_min_kPa:.0f}–{config.pressure_max_kPa:.0f} kPa",
        f"pin {config.analog_pin}",
        f"τf={1000.0 * config.fast_tau_s:.0f} ms",
        f"τs={1000.0 * config.slow_tau_s:.0f} ms",
        f"med N={config.median_window}",
    ]
    line = "     ".join(parts) + warn
    if extra:
        return f"{line}     {extra}"
    return line


def datasheet_readonly_text(config: PipelineConfig | None = None) -> str:
    cfg = config or PipelineConfig()
    bw = cfg.analog_bandwidth_hz
    return (
        f"{cfg.adc_bits}-bit ADC on {cfg.analog_pin}. "
        f"Vs={cfg.vs_v:.1f} V. tR typ. {cfg.response_time_ms:.1f} ms → "
        f"analog BW ~{bw:.0f} Hz. {DATASHEET_NOTE}"
    )


def build_config_panel(parent=None, *, sample_rate_enabled: bool = True):
    """Editable acquisition/filter form. Returns (widget, getters/setters dict).

    Importing PyQt6 here keeps headless --no-gui analysis from requiring a
    display just to load PipelineConfig.
    """
    from PyQt6 import QtWidgets

    panel = QtWidgets.QWidget(parent)
    form = QtWidgets.QFormLayout(panel)

    sample_hz = QtWidgets.QSpinBox()
    sample_hz.setRange(int(SAMPLE_HZ_MIN), int(SAMPLE_HZ_MAX))
    sample_hz.setSuffix(" Hz")
    sample_hz.setValue(int(SAMPLE_HZ_DEFAULT))
    sample_hz.setEnabled(sample_rate_enabled)
    sample_hz.setToolTip(
        "Firmware pacing only. Host downsample is not a sample rate. "
        "Default 1000 Hz from MPX5700 tR=1 ms (~350 Hz analog BW)."
    )

    mpx_scale = QtWidgets.QDoubleSpinBox()
    mpx_scale.setDecimals(7)
    mpx_scale.setRange(1e-6, 1.0)
    mpx_scale.setSingleStep(0.0000001)
    mpx_scale.setValue(MPX_SCALE)

    mpx_offset = QtWidgets.QDoubleSpinBox()
    mpx_offset.setDecimals(4)
    mpx_offset.setRange(0.0, 1.0)
    mpx_offset.setSingleStep(0.001)
    mpx_offset.setValue(MPX_OFFSET)

    median_window = QtWidgets.QSpinBox()
    median_window.setRange(1, 31)
    median_window.setValue(MEDIAN_WINDOW)

    fast_tau_ms = QtWidgets.QDoubleSpinBox()
    fast_tau_ms.setRange(1.0, 200.0)
    fast_tau_ms.setDecimals(1)
    fast_tau_ms.setSuffix(" ms")
    fast_tau_ms.setValue(1000.0 * FAST_TAU_S)

    slow_tau_ms = QtWidgets.QDoubleSpinBox()
    slow_tau_ms.setRange(10.0, 2000.0)
    slow_tau_ms.setDecimals(0)
    slow_tau_ms.setSuffix(" ms")
    slow_tau_ms.setValue(1000.0 * SLOW_TAU_S)

    deriv_tau_ms = QtWidgets.QDoubleSpinBox()
    deriv_tau_ms.setRange(1.0, 200.0)
    deriv_tau_ms.setDecimals(1)
    deriv_tau_ms.setSuffix(" ms")
    deriv_tau_ms.setValue(1000.0 * DERIVATIVE_TAU_S)

    readonly = QtWidgets.QLabel(datasheet_readonly_text())
    readonly.setWordWrap(True)

    reset_btn = QtWidgets.QPushButton("Reset sensor to datasheet")
    apply_btn = QtWidgets.QPushButton("Apply")
    apply_btn.setToolTip("Send RATE to firmware and rebuild host filters. Disabled while recording.")

    form.addRow("Sample rate", sample_hz)
    form.addRow("MPX scale (1/kPa)", mpx_scale)
    form.addRow("MPX offset", mpx_offset)
    form.addRow("Median window", median_window)
    form.addRow("Fast LPF τ", fast_tau_ms)
    form.addRow("Slow LPF τ", slow_tau_ms)
    form.addRow("dP/dt LPF τ", deriv_tau_ms)
    form.addRow(readonly)
    buttons = QtWidgets.QHBoxLayout()
    buttons.addWidget(reset_btn)
    buttons.addWidget(apply_btn)
    buttons.addStretch(1)
    form.addRow(buttons)

    def to_config(base: PipelineConfig | None = None) -> PipelineConfig:
        cfg = (base or PipelineConfig()).copy()
        cfg.sample_hz = float(sample_hz.value())
        cfg.mpx_scale = float(mpx_scale.value())
        cfg.mpx_offset = float(mpx_offset.value())
        cfg.median_window = int(median_window.value())
        cfg.fast_tau_s = float(fast_tau_ms.value()) / 1000.0
        cfg.slow_tau_s = float(slow_tau_ms.value()) / 1000.0
        cfg.derivative_tau_s = float(deriv_tau_ms.value()) / 1000.0
        return cfg

    def from_config(cfg: PipelineConfig) -> None:
        sample_hz.setValue(int(round(cfg.sample_hz)))
        mpx_scale.setValue(cfg.mpx_scale)
        mpx_offset.setValue(cfg.mpx_offset)
        median_window.setValue(cfg.median_window)
        fast_tau_ms.setValue(1000.0 * cfg.fast_tau_s)
        slow_tau_ms.setValue(1000.0 * cfg.slow_tau_s)
        deriv_tau_ms.setValue(1000.0 * cfg.derivative_tau_s)
        readonly.setText(datasheet_readonly_text(cfg))

    def reset_datasheet() -> None:
        cfg = to_config()
        cfg.reset_sensor_to_datasheet()
        from_config(cfg)

    reset_btn.clicked.connect(reset_datasheet)

    return panel, {
        "sample_hz": sample_hz,
        "apply": apply_btn,
        "reset": reset_btn,
        "to_config": to_config,
        "from_config": from_config,
        "readonly": readonly,
    }
