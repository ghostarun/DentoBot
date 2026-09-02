"""Realtime ΔP / change-point core for pneumatic drilling traces.

Sensing and review only. Does not command hardware.

Pipeline (experimental starting constants, not clinical):

    raw kPa → 5-sample median → fast LPF
         ├→ slow LPF → ΔP = fast − slow
         └→ filtered dP/dt from the fast pressure

Boundary detection is gated: air-off and air-spinup never arm it.
During experiments the live GUI arms only while the annotator marks
DRILL_IN_DENTIN and air is already on.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from pressure_signal import AIR_OFF_ENTER_KPA, AIR_ON_ENTER_KPA
from pressure_config import PipelineConfig

MEDIAN_WINDOW = 5
FAST_TAU_S = 0.015
SLOW_TAU_S = 0.40
DERIVATIVE_TAU_S = 0.020
SPINUP_S = 0.40
PERCENTILE_WINDOW_S = 0.050
MAD_WINDOW_S = 0.40
HISTORY_S = 0.45
MAD_SCALE = 1.4826
MIN_DELTA_KPA = 2.5
K_SIGMA = 4.0
MIN_NOISE_KPA = 0.20
STEP_PRE_S = 0.150
STEP_GAP_S = 0.030
STEP_POST_S = 0.150
REFRACTORY_S = 0.15
RECOVERY_FRAC = 0.35
MIN_STEP_KPA = 2.0
ARMED_STAGE = "DRILL_IN_DENTIN"

AIR_OFF = "AIR_OFF"
AIR_SPINUP = "AIR_SPINUP"
AIR_ON = "AIR_ON"

SAMPLE_COLUMNS = [
    "seq",
    "time_s",
    "raw_adc",
    "pressure_raw_kPa",
    "pressure_median_kPa",
    "pressure_filtered_kPa",
    "baseline_slow_kPa",
    "delta_kPa",
    "dpdt_raw_kPa_s",
    "dpdt_filtered_kPa_s",
    "rolling_noise_kPa",
    "rolling_p10_kPa",
    "rolling_p90_kPa",
    "rolling_spread_kPa",
    "air_state",
    "drill_stage",
    "boundary_score",
    "candidate_state",
]

EVENT_COLUMNS = [
    "event_id",
    "type",
    "start_s",
    "extreme_s",
    "end_s",
    "p_before_kPa",
    "p_after_kPa",
    "step_kPa",
    "peak_delta_kPa",
    "peak_dpdt_kPa_s",
    "spread_before_kPa",
    "spread_after_kPa",
    "duration_ms",
    "score",
    "drill_stage",
]


def lpf_alpha(dt: float, tau: float) -> float:
    if dt <= 0.0 or tau <= 0.0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


def _median(values: list[float]) -> float:
    if not values:
        return float("nan")
    return float(np.median(np.asarray(values, dtype=np.float64)))


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


@dataclass
class FilterSample:
    time_s: float
    seq: int
    raw_adc: int
    pressure_raw_kPa: float
    pressure_median_kPa: float
    pressure_filtered_kPa: float
    baseline_slow_kPa: float
    delta_kPa: float
    dpdt_raw_kPa_s: float
    dpdt_filtered_kPa_s: float
    rolling_noise_kPa: float
    rolling_p10_kPa: float
    rolling_p90_kPa: float
    rolling_spread_kPa: float
    air_state: str
    drill_stage: str
    boundary_score: float
    candidate_state: str
    armed: bool
    event: BoundaryEvent | None = None

    def csv_row(self) -> list[object]:
        return [
            self.seq,
            f"{self.time_s:.6f}",
            self.raw_adc,
            f"{self.pressure_raw_kPa:.4f}",
            f"{self.pressure_median_kPa:.4f}",
            f"{self.pressure_filtered_kPa:.4f}",
            f"{self.baseline_slow_kPa:.4f}",
            f"{self.delta_kPa:.4f}",
            f"{self.dpdt_raw_kPa_s:.4f}",
            f"{self.dpdt_filtered_kPa_s:.4f}",
            f"{self.rolling_noise_kPa:.4f}",
            f"{self.rolling_p10_kPa:.4f}",
            f"{self.rolling_p90_kPa:.4f}",
            f"{self.rolling_spread_kPa:.4f}",
            self.air_state,
            self.drill_stage,
            f"{self.boundary_score:.4f}",
            self.candidate_state,
        ]


@dataclass
class BoundaryEvent:
    event_id: int
    type: str
    start_s: float
    extreme_s: float
    end_s: float
    p_before_kPa: float
    p_after_kPa: float
    step_kPa: float
    peak_delta_kPa: float
    peak_dpdt_kPa_s: float
    spread_before_kPa: float
    spread_after_kPa: float
    duration_ms: float
    score: float
    drill_stage: str

    def csv_row(self) -> list[object]:
        return [
            self.event_id,
            self.type,
            f"{self.start_s:.6f}",
            f"{self.extreme_s:.6f}",
            f"{self.end_s:.6f}",
            f"{self.p_before_kPa:.4f}",
            f"{self.p_after_kPa:.4f}",
            f"{self.step_kPa:.4f}",
            f"{self.peak_delta_kPa:.4f}",
            f"{self.peak_dpdt_kPa_s:.4f}",
            f"{self.spread_before_kPa:.4f}",
            f"{self.spread_after_kPa:.4f}",
            f"{self.duration_ms:.2f}",
            f"{self.score:.4f}",
            self.drill_stage,
        ]


@dataclass
class StageStats:
    label: str
    n: int
    median_p: float
    std_p: float
    spread: float
    mean_delta: float
    max_abs_dpdt: float


class PressureTracker:
    """Streaming filters + gated change-point detector."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config.copy() if config is not None else PipelineConfig()
        self._median_buf: deque[float] = deque(maxlen=self.config.median_window)
        self._fast: float | None = None
        self._slow: float | None = None
        self._dpdt_filt = 0.0
        self._prev_t: float | None = None
        self._prev_raw: float | None = None
        self._prev_fast: float | None = None
        self._air_state = AIR_OFF
        self._spinup_t0: float | None = None
        self._history: deque[tuple[float, float, float]] = deque()
        self._percent: deque[tuple[float, float]] = deque()
        self._mad: deque[tuple[float, float]] = deque()
        self._noise = MIN_NOISE_KPA
        self._frozen_noise: float | None = None
        self._candidate = False
        self._cand_start = 0.0
        self._cand_extreme_t = 0.0
        self._cand_peak_delta = 0.0
        self._cand_peak_dpdt = 0.0
        self._cand_stage = ARMED_STAGE
        self._refractory_until = 0.0
        self._event_id = 0
        self.events: list[BoundaryEvent] = []

    def reset(self) -> None:
        self.__init__(self.config)

    def _trim(self, buf: deque, now: float, span: float, index: int = 0) -> None:
        while buf and now - buf[0][index] > span:
            buf.popleft()

    def _air(self, t: float, p_fast: float) -> str:
        if self._air_state == AIR_OFF:
            if p_fast >= AIR_ON_ENTER_KPA:
                self._air_state = AIR_SPINUP
                self._spinup_t0 = t
        elif self._air_state == AIR_SPINUP:
            if p_fast <= AIR_OFF_ENTER_KPA:
                self._air_state = AIR_OFF
                self._spinup_t0 = None
            elif self._spinup_t0 is not None and (t - self._spinup_t0) >= SPINUP_S:
                self._air_state = AIR_ON
                if self._fast is not None:
                    self._slow = self._fast
        elif p_fast <= AIR_OFF_ENTER_KPA:
            self._air_state = AIR_OFF
            self._spinup_t0 = None
        return self._air_state

    def _window(self, t0: float, t1: float) -> tuple[float, float]:
        pressures = []
        spreads = []
        for ts, pressure, spread in self._history:
            if t0 <= ts <= t1:
                pressures.append(pressure)
                spreads.append(spread)
        return _median(pressures), _median(spreads)

    def _classify(self, t: float, delta_now: float) -> BoundaryEvent | None:
        extreme = self._cand_extreme_t
        p_before, spread_before = self._window(
            extreme - STEP_PRE_S,
            extreme - STEP_GAP_S,
        )
        p_after, spread_after = self._window(
            extreme + STEP_GAP_S,
            extreme + STEP_POST_S,
        )
        step = p_after - p_before
        peak_delta = self._cand_peak_delta
        recovered = abs(delta_now) < RECOVERY_FRAC * max(abs(peak_delta), 1e-6)
        if abs(step) >= MIN_STEP_KPA:
            kind = "STEP"
        elif recovered and abs(peak_delta) >= MIN_DELTA_KPA:
            kind = "TRANSIENT"
        elif abs(step) >= 0.5 * abs(peak_delta) and abs(step) >= MIN_STEP_KPA:
            kind = "STEP"
        else:
            return None
        score = abs(step) + 0.01 * abs(self._cand_peak_dpdt)
        self._event_id += 1
        return BoundaryEvent(
            event_id=self._event_id,
            type=kind,
            start_s=self._cand_start,
            extreme_s=extreme,
            end_s=t,
            p_before_kPa=p_before,
            p_after_kPa=p_after,
            step_kPa=step,
            peak_delta_kPa=peak_delta,
            peak_dpdt_kPa_s=self._cand_peak_dpdt,
            spread_before_kPa=spread_before,
            spread_after_kPa=spread_after,
            duration_ms=(t - self._cand_start) * 1000.0,
            score=score,
            drill_stage=self._cand_stage,
        )

    def update(
        self,
        t: float,
        pressure_raw: float,
        seq: int,
        raw_adc: int,
        drill_stage: str,
    ) -> FilterSample:
        dt = 1.0 / max(self.config.sample_hz, 1.0)
        dpdt_raw = 0.0
        if self._prev_t is not None:
            dt = max(t - self._prev_t, 1e-6)
            if self._prev_raw is not None:
                dpdt_raw = (pressure_raw - self._prev_raw) / dt

        self._median_buf.append(pressure_raw)
        p_median = _median(list(self._median_buf))

        if self._fast is None:
            self._fast = p_median
            self._slow = p_median
            self._dpdt_filt = 0.0
            inst_dpdt = 0.0
        else:
            self._fast += lpf_alpha(dt, self.config.fast_tau_s) * (p_median - self._fast)
            self._slow += lpf_alpha(dt, self.config.slow_tau_s) * (p_median - self._slow)
            inst_dpdt = 0.0
            if self._prev_fast is not None:
                inst_dpdt = (self._fast - self._prev_fast) / dt
            self._dpdt_filt += lpf_alpha(dt, self.config.derivative_tau_s) * (
                inst_dpdt - self._dpdt_filt
            )

        p_fast = float(self._fast)
        p_slow = float(self._slow)
        delta = p_fast - p_slow
        air_state = self._air(t, p_fast)

        self._percent.append((t, p_fast))
        self._trim(self._percent, t, PERCENTILE_WINDOW_S)
        p_vals = [item[1] for item in self._percent]
        p10 = _percentile(p_vals, 10)
        p90 = _percentile(p_vals, 90)
        spread = p90 - p10

        self._history.append((t, p_fast, spread))
        self._trim(self._history, t, HISTORY_S)

        armed = air_state == AIR_ON and drill_stage == ARMED_STAGE
        noise = self._frozen_noise if self._frozen_noise is not None else self._noise
        if armed and not self._candidate:
            self._mad.append((t, delta))
            self._trim(self._mad, t, MAD_WINDOW_S)
            deltas = [item[1] for item in self._mad]
            if len(deltas) >= 20:
                med = _median(deltas)
                mad = _median([abs(item - med) for item in deltas])
                self._noise = max(MAD_SCALE * mad, MIN_NOISE_KPA)
                noise = self._noise

        threshold = max(MIN_DELTA_KPA, K_SIGMA * noise)
        score = abs(delta) / max(noise, MIN_NOISE_KPA)
        candidate_state = ""
        finished: BoundaryEvent | None = None

        if self._candidate:
            candidate_state = "CANDIDATE"
            if abs(delta) > abs(self._cand_peak_delta):
                self._cand_peak_delta = delta
                self._cand_extreme_t = t
            if abs(self._dpdt_filt) > abs(self._cand_peak_dpdt):
                self._cand_peak_dpdt = self._dpdt_filt
            if t >= self._cand_extreme_t + STEP_POST_S:
                finished = self._classify(t, delta)
                if finished is not None:
                    self.events.append(finished)
                    candidate_state = finished.type
                else:
                    candidate_state = ""
                self._candidate = False
                self._frozen_noise = None
                self._refractory_until = t + REFRACTORY_S
        elif (
            armed
            and t >= self._refractory_until
            and abs(delta) >= threshold
        ):
            self._candidate = True
            self._frozen_noise = noise
            self._cand_start = t
            self._cand_extreme_t = t
            self._cand_peak_delta = delta
            self._cand_peak_dpdt = self._dpdt_filt
            self._cand_stage = drill_stage
            candidate_state = "CANDIDATE"

        self._prev_t = t
        self._prev_raw = pressure_raw
        self._prev_fast = p_fast

        return FilterSample(
            time_s=t,
            seq=seq,
            raw_adc=raw_adc,
            pressure_raw_kPa=pressure_raw,
            pressure_median_kPa=p_median,
            pressure_filtered_kPa=p_fast,
            baseline_slow_kPa=p_slow,
            delta_kPa=delta,
            dpdt_raw_kPa_s=dpdt_raw,
            dpdt_filtered_kPa_s=self._dpdt_filt,
            rolling_noise_kPa=noise,
            rolling_p10_kPa=p10,
            rolling_p90_kPa=p90,
            rolling_spread_kPa=spread,
            air_state=air_state,
            drill_stage=drill_stage,
            boundary_score=score,
            candidate_state=candidate_state,
            armed=armed,
            event=finished,
        )


def drill_stages_from_annotations(time_s: np.ndarray, annotations) -> np.ndarray:
    """Forward-fill annotate marks onto the sample clock. Cues are ignored."""
    marks = [
        (item.corrected_s, item.label)
        for item in annotations
        if getattr(item, "kind", "annotate") == "annotate"
    ]
    marks.sort(key=lambda item: item[0])
    stages = np.full(time_s.shape, "AIR_OFF", dtype=object)
    if not marks:
        return stages
    index = 0
    label = "AIR_OFF"
    for i, t in enumerate(time_s):
        while index < len(marks) and t >= marks[index][0]:
            label = marks[index][1]
            index += 1
        stages[i] = label
    return stages


def replay_tracker(
    time_s: np.ndarray,
    pressure_raw: np.ndarray,
    seq: np.ndarray | None = None,
    raw_adc: np.ndarray | None = None,
    drill_stages: np.ndarray | None = None,
    config: PipelineConfig | None = None,
) -> tuple[list[FilterSample], list[BoundaryEvent]]:
    tracker = PressureTracker(config)
    samples: list[FilterSample] = []
    n = int(time_s.size)
    for i in range(n):
        stage = "AIR_OFF"
        if drill_stages is not None:
            stage = str(drill_stages[i])
        sample = tracker.update(
            float(time_s[i]),
            float(pressure_raw[i]),
            int(seq[i]) if seq is not None else i,
            int(raw_adc[i]) if raw_adc is not None else 0,
            stage,
        )
        samples.append(sample)
    return samples, list(tracker.events)


def stage_statistics(
    time_s: np.ndarray,
    pressure: np.ndarray,
    delta: np.ndarray,
    dpdt: np.ndarray,
    spread: np.ndarray,
    annotations,
    events: list[BoundaryEvent] | None = None,
) -> list[StageStats]:
    """Per-annotate-interval descriptors plus one row per boundary event."""
    time_s = np.asarray(time_s, dtype=np.float64)
    pressure = np.asarray(pressure, dtype=np.float64)
    delta = np.asarray(delta, dtype=np.float64)
    dpdt = np.asarray(dpdt, dtype=np.float64)
    spread = np.asarray(spread, dtype=np.float64)
    marks = [
        (item.corrected_s, item.label, getattr(item.spec, "button", item.label))
        for item in annotations
        if getattr(item, "kind", "annotate") == "annotate"
    ]
    marks.sort(key=lambda item: item[0])
    rows: list[StageStats] = []

    def _row(label: str, mask: np.ndarray) -> StageStats | None:
        if not np.any(mask):
            return None
        p = pressure[mask]
        d = delta[mask]
        deriv = dpdt[mask]
        sp = spread[mask]
        finite_p = p[np.isfinite(p)]
        if finite_p.size == 0:
            return None
        finite_d = d[np.isfinite(d)]
        finite_sp = sp[np.isfinite(sp)]
        finite_dv = deriv[np.isfinite(deriv)]
        return StageStats(
            label=label,
            n=int(finite_p.size),
            median_p=float(np.median(finite_p)),
            std_p=float(np.std(finite_p)) if finite_p.size > 1 else 0.0,
            spread=float(np.median(finite_sp)) if finite_sp.size else float("nan"),
            mean_delta=float(np.mean(finite_d)) if finite_d.size else float("nan"),
            max_abs_dpdt=float(np.max(np.abs(finite_dv))) if finite_dv.size else float("nan"),
        )

    if not marks:
        row = _row("unmarked", np.ones(time_s.shape, dtype=bool))
        if row is not None:
            rows.append(row)
    else:
        edges = (
            [float(time_s[0])]
            + [item[0] for item in marks]
            + [float(time_s[-1]) + 1e-9]
        )
        for i in range(len(edges) - 1):
            label = "before first mark" if i == 0 else marks[i - 1][2]
            mask = (time_s >= edges[i]) & (time_s < edges[i + 1])
            row = _row(label, mask)
            if row is not None:
                rows.append(row)

    for event in events or []:
        mask = (time_s >= event.start_s) & (time_s <= event.end_s)
        row = _row(f"{event.type} @{event.extreme_s:.2f}s", mask)
        if row is not None:
            rows.append(row)
    return rows


def format_stage_table(rows: list[StageStats]) -> str:
    if not rows:
        return "Stage statistics: no annotated intervals"
    header = (
        f"{'Stage':<28} {'N':>7} {'Median P':>10} {'Std':>8} "
        f"{'p90-p10':>8} {'Mean ΔP':>9} {'max|dP/dt|':>11}"
    )
    lines = ["Stage statistics (illustrative descriptors, not clinical claims)", header]
    for row in rows:
        lines.append(
            f"{row.label:<28} {row.n:7d} {row.median_p:10.2f} {row.std_p:8.2f} "
            f"{row.spread:8.2f} {row.mean_delta:9.2f} {row.max_abs_dpdt:11.1f}"
        )
    return "\n".join(lines)
