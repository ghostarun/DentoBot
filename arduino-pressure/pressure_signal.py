"""Display-oriented pressure smoothing and load-boundary detection.

Keep aligned with the host Arduino bench. These helpers are for visualization
and post-run review of major load steps (contact vs air). They do not command
hardware.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_BIN_S = 0.05
DEFAULT_IDLE_KPA = 8.0
DEFAULT_LOADED_KPA = 60.0
DEFAULT_INNER_STEP_KPA = 20.0
DEFAULT_MIN_HOLD_S = 0.15

# 2026-08-31 tooth-drilling runs: 50 ms median is bimodal.
# Air-off cluster ~-0.4 kPa (p95 typically < 8 kPa). Air-on / drill-in-air
# plateau ~220–228 kPa. Almost no dwell between ~10 and ~200 kPa except ramps.
AIR_OFF_ENTER_KPA = 8.0
AIR_ON_ENTER_KPA = 25.0


@dataclass
class BinnedPressure:
    time_s: np.ndarray
    median_kPa: np.ndarray
    low_kPa: np.ndarray
    high_kPa: np.ndarray
    dmedian_kPa_s: np.ndarray


@dataclass
class LoadBoundary:
    time_s: float
    kind: str
    from_kPa: float
    to_kPa: float
    delta_kPa: float
    peak_kPa: float = 0.0

    @property
    def label(self) -> str:
        if self.kind == "contact":
            return "Contact / load on"
        if self.kind == "air":
            return "Air / breakthrough"
        if self.kind == "drop":
            return "Load drop"
        if self.kind == "rise":
            return "Load rise"
        return self.kind


def bin_pressure_stats(
    time_s: np.ndarray,
    pressure_kPa: np.ndarray,
    bin_s: float = DEFAULT_BIN_S,
) -> BinnedPressure:
    time_s = np.asarray(time_s, dtype=np.float64)
    pressure_kPa = np.asarray(pressure_kPa, dtype=np.float64)
    if time_s.size == 0:
        empty = np.asarray([], dtype=np.float64)
        return BinnedPressure(empty, empty, empty, empty, empty)

    bin_s = max(float(bin_s), 1e-3)
    start = float(time_s[0])
    stop = float(time_s[-1])
    edges = np.arange(start, stop + bin_s, bin_s)
    if edges.size < 2:
        edges = np.asarray([start, start + bin_s], dtype=np.float64)

    index = np.digitize(time_s, edges)
    valid = (index >= 1) & (index < len(edges))
    index = index[valid]
    vals = pressure_kPa[valid]
    if index.size == 0:
        empty = np.asarray([], dtype=np.float64)
        return BinnedPressure(empty, empty, empty, empty, empty)

    order = np.argsort(index, kind="mergesort")
    index = index[order]
    vals = vals[order]
    uniq, starts = np.unique(index, return_index=True)
    ends = np.append(starts[1:], index.size)

    mids: list[float] = []
    medians: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    for bin_id, start_i, end_i in zip(uniq, starts, ends):
        sl = vals[start_i:end_i]
        mids.append(float(edges[int(bin_id) - 1] + 0.5 * bin_s))
        medians.append(float(np.median(sl)))
        lows.append(float(np.percentile(sl, 10)))
        highs.append(float(np.percentile(sl, 90)))

    t_out = np.asarray(mids, dtype=np.float64)
    med = np.asarray(medians, dtype=np.float64)
    lo = np.asarray(lows, dtype=np.float64)
    hi = np.asarray(highs, dtype=np.float64)
    if med.size >= 2:
        dmed = np.gradient(med, t_out)
    else:
        dmed = np.zeros_like(med)
    return BinnedPressure(t_out, med, lo, hi, dmed)


def detect_load_boundaries(
    binned: BinnedPressure,
    idle_kPa: float = DEFAULT_IDLE_KPA,
    loaded_kPa: float = DEFAULT_LOADED_KPA,
    inner_step_kPa: float = DEFAULT_INNER_STEP_KPA,
    min_hold_s: float = DEFAULT_MIN_HOLD_S,
) -> list[LoadBoundary]:
    """Find contact, air, and held inner load steps on the smoothed median."""
    t = binned.time_s
    med = binned.median_kPa
    if t.size < 3:
        return []

    dt = float(np.median(np.diff(t))) if t.size > 1 else DEFAULT_BIN_S
    hold_bins = max(2, int(round(min_hold_s / max(dt, 1e-3))))
    boundaries: list[LoadBoundary] = []
    i = 0
    n = int(t.size)

    while i < n:
        if med[i] <= idle_kPa:
            j = i + 1
            while j < n and med[j] <= idle_kPa:
                j += 1
            if j >= n:
                break
            k = j
            while k < n and med[k] < loaded_kPa:
                k += 1
            if k >= n:
                break
            from_level = float(np.median(med[i:j]))
            to_level = float(np.median(med[k:min(n, k + hold_bins)]))
            boundaries.append(
                LoadBoundary(
                    time_s=float(t[j]),
                    kind="contact",
                    from_kPa=from_level,
                    to_kPa=to_level,
                    delta_kPa=to_level - from_level,
                    peak_kPa=float(np.max(med[j:min(n, k + hold_bins)])),
                )
            )
            i = k
            continue

        start = i
        peak = float(med[i])
        j = i + 1
        while j < n and med[j] > idle_kPa:
            peak = max(peak, float(med[j]))
            j += 1

        activity = med[start:j]
        if activity.size >= hold_bins and peak >= loaded_kPa:
            inner = _inner_held_steps(
                t[start:j],
                activity,
                inner_step_kPa,
                hold_bins,
            )
            boundaries.extend(inner)
            if j < n:
                from_level = float(np.median(activity[-hold_bins:]))
                to_level = float(med[j])
                boundaries.append(
                    LoadBoundary(
                        time_s=float(t[j]),
                        kind="air",
                        from_kPa=from_level,
                        to_kPa=to_level,
                        delta_kPa=to_level - from_level,
                        peak_kPa=peak,
                    )
                )
        i = j if j > i else i + 1

    return boundaries


def _inner_held_steps(
    t: np.ndarray,
    med: np.ndarray,
    inner_step_kPa: float,
    hold_bins: int,
) -> list[LoadBoundary]:
    """Held median steps inside a loaded burst, not the idle contact/air edges."""
    if med.size < hold_bins * 2:
        return []
    steps: list[LoadBoundary] = []
    i = 0
    n = int(med.size)
    while i < n:
        plateau = [float(med[i])]
        j = i + 1
        while j < n and abs(float(med[j]) - float(np.median(plateau))) < inner_step_kPa:
            plateau.append(float(med[j]))
            j += 1
        if j >= n:
            break
        nxt = [float(med[j])]
        k = j + 1
        while k < n and abs(float(med[k]) - float(np.median(nxt))) < inner_step_kPa:
            nxt.append(float(med[k]))
            k += 1
        if len(plateau) >= hold_bins and len(nxt) >= hold_bins:
            from_level = float(np.median(plateau))
            to_level = float(np.median(nxt))
            delta = to_level - from_level
            if abs(delta) >= inner_step_kPa:
                steps.append(
                    LoadBoundary(
                        time_s=float(t[j]),
                        kind="drop" if delta < 0 else "rise",
                        from_kPa=from_level,
                        to_kPa=to_level,
                        delta_kPa=delta,
                        peak_kPa=max(from_level, to_level),
                    )
                )
        i = j
    return steps


def estimate_air_thresholds(
    time_s: np.ndarray,
    pressure_kPa: np.ndarray,
    bin_s: float = DEFAULT_BIN_S,
) -> tuple[float, float]:
    """Two-mode split on 50 ms medians. Falls back to today's 8 / 25 kPa gates."""
    binned = bin_pressure_stats(time_s, pressure_kPa, bin_s=bin_s)
    med = binned.median_kPa
    if med.size < 20:
        return AIR_OFF_ENTER_KPA, AIR_ON_ENTER_KPA

    vals = np.sort(med)
    best_var = None
    split = 0.5 * (vals[0] + vals[-1])
    low_mean = float(vals[0])
    high_mean = float(vals[-1])
    for i in range(5, len(vals) - 5):
        low = vals[:i]
        high = vals[i:]
        w1 = low.size / vals.size
        w2 = high.size / vals.size
        var = w1 * float(low.var()) + w2 * float(high.var())
        if best_var is None or var < best_var:
            best_var = var
            split = 0.5 * (float(low[-1]) + float(high[0]))
            low_mean = float(low.mean())
            high_mean = float(high.mean())

    if high_mean - low_mean < 40.0:
        return AIR_OFF_ENTER_KPA, AIR_ON_ENTER_KPA

    off_kPa = float(np.clip(max(low_mean + 6.0, split * 0.15), 5.0, 20.0))
    on_kPa = float(np.clip(min(high_mean * 0.2, split * 0.4), off_kPa + 5.0, 80.0))
    return off_kPa, on_kPa


def classify_air_off_mask(
    time_s: np.ndarray,
    pressure_kPa: np.ndarray,
    off_kPa: float = AIR_OFF_ENTER_KPA,
    on_kPa: float = AIR_ON_ENTER_KPA,
    bin_s: float = DEFAULT_BIN_S,
) -> np.ndarray:
    """True where the 50 ms median hysteresis says air is off.

    Hysteresis: enter air-on when the binned median reaches `on_kPa`, return
    to air-off when it falls to `off_kPa`. Raw CSV is not modified.
    """
    time_s = np.asarray(time_s, dtype=np.float64)
    pressure_kPa = np.asarray(pressure_kPa, dtype=np.float64)
    n = int(time_s.size)
    if n == 0:
        return np.zeros(0, dtype=bool)

    binned = bin_pressure_stats(time_s, pressure_kPa, bin_s=bin_s)
    if binned.time_s.size == 0:
        return pressure_kPa <= off_kPa

    state_off = True
    bin_off = np.empty(binned.time_s.size, dtype=bool)
    for i, median in enumerate(binned.median_kPa):
        if state_off:
            if median >= on_kPa:
                state_off = False
        elif median <= off_kPa:
            state_off = True
        bin_off[i] = state_off

    index = np.searchsorted(binned.time_s, time_s, side="right") - 1
    np.clip(index, 0, bin_off.size - 1, out=index)
    return bin_off[index]


def normalize_air_filter_mode(mode: str) -> str:
    key = str(mode).strip().lower().replace("_", "-").replace(" ", "-")
    if key in ("hide", "hide-air-off"):
        return "hide"
    if key in ("highlight", "highlight-air-off"):
        return "highlight"
    return "all"


def apply_air_display(
    values: np.ndarray,
    mask_off: np.ndarray,
    mode: str,
) -> tuple[np.ndarray, np.ndarray | None]:
    """NaN air-off samples, or return a grey overlay series for highlight."""
    values = np.asarray(values, dtype=np.float64)
    mask_off = np.asarray(mask_off, dtype=bool)
    mode = normalize_air_filter_mode(mode)
    if (
        mode == "all"
        or mask_off.size == 0
        or mask_off.size != values.size
    ):
        return values.copy(), None
    shown = values.copy()
    shown[mask_off] = np.nan
    if mode == "hide":
        return shown, None
    overlay = values.copy()
    overlay[~mask_off] = np.nan
    return shown, overlay


def air_state_for_series(
    time_s: np.ndarray,
    pressure_kPa: np.ndarray,
    *,
    auto: bool = False,
) -> tuple[np.ndarray, float, float]:
    if auto:
        off_kPa, on_kPa = estimate_air_thresholds(time_s, pressure_kPa)
    else:
        off_kPa, on_kPa = AIR_OFF_ENTER_KPA, AIR_ON_ENTER_KPA
    mask = classify_air_off_mask(
        time_s,
        pressure_kPa,
        off_kPa=off_kPa,
        on_kPa=on_kPa,
    )
    return mask, off_kPa, on_kPa


def air_state_summary(
    mask_off: np.ndarray,
    off_kPa: float,
    on_kPa: float,
) -> str:
    n = int(mask_off.size)
    if n == 0:
        return "Air state: no samples"
    n_off = int(np.count_nonzero(mask_off))
    return (
        f"Air-off {100.0 * n_off / n:.1f}% ({n_off}/{n})    "
        f"air-on {100.0 * (n - n_off) / n:.1f}%    "
        f"gates {off_kPa:.1f}/{on_kPa:.1f} kPa (50 ms median hysteresis)"
    )


def finite_runs(values: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive-start exclusive-end slices where `values` is finite."""
    finite = np.isfinite(np.asarray(values, dtype=np.float64))
    runs: list[tuple[int, int]] = []
    n = int(finite.size)
    i = 0
    while i < n:
        if not finite[i]:
            i += 1
            continue
        j = i + 1
        while j < n and finite[j]:
            j += 1
        runs.append((i, j))
        i = j
    return runs


def apply_air_to_binned(
    binned: BinnedPressure,
    sample_times: np.ndarray,
    mask_off: np.ndarray | None,
    mode: str,
) -> BinnedPressure:
    """NaN air-off bins for hide mode. Highlight keeps the smoothed trace."""
    mode = normalize_air_filter_mode(mode)
    if (
        mask_off is None
        or mode in ("all", "highlight")
        or binned.time_s.size == 0
        or np.asarray(mask_off).size == 0
    ):
        return binned
    sample_times = np.asarray(sample_times, dtype=np.float64)
    mask_off = np.asarray(mask_off, dtype=bool)
    idx = np.searchsorted(sample_times, binned.time_s, side="left")
    np.clip(idx, 0, mask_off.size - 1, out=idx)
    bin_mask = mask_off[idx]
    med, _ = apply_air_display(binned.median_kPa, bin_mask, "hide")
    lo, _ = apply_air_display(binned.low_kPa, bin_mask, "hide")
    hi, _ = apply_air_display(binned.high_kPa, bin_mask, "hide")
    return BinnedPressure(
        binned.time_s,
        med,
        lo,
        hi,
        binned.dmedian_kPa_s,
    )


def load_boundaries_for_series(
    time_s: np.ndarray,
    pressure_kPa: np.ndarray,
    bin_s: float = DEFAULT_BIN_S,
) -> tuple[BinnedPressure, list[LoadBoundary]]:
    binned = bin_pressure_stats(time_s, pressure_kPa, bin_s=bin_s)
    return binned, detect_load_boundaries(binned)
