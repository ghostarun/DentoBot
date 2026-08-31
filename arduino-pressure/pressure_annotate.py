"""Manual drilling-stage annotations, operator latency, and cue tones.

Display and review helpers only. They do not command hardware. samples.csv
is not modified; annotations live in annotations.csv beside the run.
"""

from __future__ import annotations

import math
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pressure_signal import bin_pressure_stats

DEFAULT_LATENCY_S = 0.40
DEFAULT_CUE_INTERVAL_S = 10.0
DEFAULT_DIP_SEARCH_S = 0.80
DEFAULT_DIP_PRE_S = 0.15

ANNOTATION_COLUMNS = [
    "event_id",
    "kind",
    "label",
    "press_s",
    "latency_s",
    "corrected_s",
    "pressure_kPa",
    "seq",
]


@dataclass(frozen=True)
class StageSpec:
    key: str
    button: str
    color: str
    freq_hz: float
    pulses: int
    shortcut: str


STAGES: tuple[StageSpec, ...] = (
    StageSpec("AIR_OFF", "AIR OFF", "#9ca3af", 330.0, 1, "F1"),
    StageSpec("DRILL_IN_AIR", "DRILL IN AIR", "#38bdf8", 660.0, 1, "F2"),
    StageSpec("DRILL_IN_DENTIN", "DRILL IN DENTIN", "#fbbf24", 880.0, 2, "F3"),
    StageSpec("DRILL_IN_PULP", "DRILL IN PULP", "#f472b6", 1175.0, 3, "F4"),
)

STAGE_BY_KEY = {item.key: item for item in STAGES}
CUE_ORDER = tuple(item.key for item in STAGES)


@dataclass
class ManualAnnotation:
    event_id: int
    kind: str
    label: str
    press_s: float
    latency_s: float
    corrected_s: float
    pressure_kPa: float
    seq: int

    @property
    def spec(self) -> StageSpec | None:
        return STAGE_BY_KEY.get(self.label)

    @property
    def is_annotate(self) -> bool:
        return self.kind == "annotate"


@dataclass
class AnnotationDipMatch:
    annotation: ManualAnnotation
    dip_s: float
    from_kPa: float
    to_kPa: float
    delta_kPa: float
    offset_from_corrected_s: float
    offset_from_press_s: float


def stage_spec(key: str) -> StageSpec:
    return STAGE_BY_KEY[key]


def corrected_time(press_s: float, latency_s: float, t_min: float | None = None) -> float:
    corrected = float(press_s) - max(0.0, float(latency_s))
    if t_min is not None:
        corrected = max(float(t_min), corrected)
    return corrected


def next_cue_key(current_index: int) -> tuple[str, int]:
    key = CUE_ORDER[current_index % len(CUE_ORDER)]
    return key, (current_index + 1) % len(CUE_ORDER)


def cue_index_after_label(label: str) -> int | None:
    if label not in CUE_ORDER:
        return None
    return (CUE_ORDER.index(label) + 1) % len(CUE_ORDER)


def write_tone_wav(
    path: Path,
    freq_hz: float,
    pulses: int,
    pulse_ms: int = 90,
    gap_ms: int = 80,
    volume: float = 0.32,
    rate: int = 22050,
) -> None:
    """Write a short PCM beep train. Used by the live cue/annotate tones."""
    samples: list[int] = []
    for pulse in range(max(1, int(pulses))):
        count = int(rate * pulse_ms / 1000.0)
        for index in range(count):
            envelope = min(1.0, index / 180.0) * min(1.0, (count - index) / 360.0)
            value = math.sin(2.0 * math.pi * freq_hz * index / rate)
            samples.append(int(32767.0 * volume * envelope * value))
        if pulse + 1 < pulses:
            samples.extend([0] * int(rate * gap_ms / 1000.0))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in samples))


def load_annotations(path: Path) -> list[ManualAnnotation]:
    import csv

    items: list[ManualAnnotation] = []
    if not path.is_file():
        return items
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            items.append(
                ManualAnnotation(
                    event_id=int(float(row["event_id"])),
                    kind=row["kind"].strip().lower(),
                    label=row["label"].strip().upper(),
                    press_s=float(row["press_s"]),
                    latency_s=float(row["latency_s"]),
                    corrected_s=float(row["corrected_s"]),
                    pressure_kPa=float(row["pressure_kPa"]) if row.get("pressure_kPa") else float("nan"),
                    seq=int(float(row["seq"])) if row.get("seq") else -1,
                )
            )
    return items


def match_annotation_dip(
    time_s: np.ndarray,
    pressure_kPa: np.ndarray,
    annotation: ManualAnnotation,
    search_s: float = DEFAULT_DIP_SEARCH_S,
    pre_s: float = DEFAULT_DIP_PRE_S,
) -> AnnotationDipMatch | None:
    """Find the strongest 50 ms median step near the latency-corrected press.

    Prefers a drop of at least 3 kPa (tissue-boundary dip). If the window is
    a load-on ramp instead, falls back to the largest |Δmedian|. The operator
    marks after noticing the change, so the step is expected before `press_s`.
    """
    if annotation.kind != "annotate":
        return None
    time_s = np.asarray(time_s, dtype=np.float64)
    pressure_kPa = np.asarray(pressure_kPa, dtype=np.float64)
    if time_s.size < 8:
        return None

    t0 = float(annotation.corrected_s) - max(0.0, float(pre_s))
    t1 = min(float(annotation.press_s), float(annotation.corrected_s) + max(0.05, float(search_s)))
    if t1 <= t0:
        t1 = t0 + max(0.2, float(search_s))

    mask = (time_s >= t0) & (time_s <= t1)
    if int(np.count_nonzero(mask)) < 8:
        return None

    binned = bin_pressure_stats(time_s[mask], pressure_kPa[mask], bin_s=0.05)
    if binned.median_kPa.size < 3:
        index = int(np.argmin(pressure_kPa[mask]))
        dip_s = float(time_s[mask][index])
        value = float(pressure_kPa[mask][index])
        return AnnotationDipMatch(
            annotation=annotation,
            dip_s=dip_s,
            from_kPa=value,
            to_kPa=value,
            delta_kPa=0.0,
            offset_from_corrected_s=dip_s - float(annotation.corrected_s),
            offset_from_press_s=dip_s - float(annotation.press_s),
        )

    drops = np.diff(binned.median_kPa)
    drop_i = int(np.argmin(drops))
    step_i = int(np.argmax(np.abs(drops)))
    index = drop_i if float(drops[drop_i]) <= -3.0 else step_i
    dip_s = 0.5 * (float(binned.time_s[index]) + float(binned.time_s[index + 1]))
    from_kPa = float(binned.median_kPa[index])
    to_kPa = float(binned.median_kPa[index + 1])
    return AnnotationDipMatch(
        annotation=annotation,
        dip_s=dip_s,
        from_kPa=from_kPa,
        to_kPa=to_kPa,
        delta_kPa=to_kPa - from_kPa,
        offset_from_corrected_s=dip_s - float(annotation.corrected_s),
        offset_from_press_s=dip_s - float(annotation.press_s),
    )


def format_annotation_lines(
    annotations: list[ManualAnnotation],
    matches: list[AnnotationDipMatch | None] | None = None,
) -> list[str]:
    if not annotations:
        return []
    lines = ["Manual annotations (press minus operator latency):"]
    match_by_id = {}
    if matches:
        for item in matches:
            if item is not None:
                match_by_id[item.annotation.event_id] = item
    for item in annotations:
        spec = item.spec
        name = spec.button if spec else item.label
        line = (
            f"  {item.kind:8s}  {name:16s}  press={item.press_s:.3f}s  "
            f"latency={1000.0 * item.latency_s:.0f} ms  "
            f"corrected={item.corrected_s:.3f}s"
        )
        found = match_by_id.get(item.event_id)
        if found is not None:
            line += (
                f"  step@{found.dip_s:.3f}s  "
                f"{found.from_kPa:.1f}→{found.to_kPa:.1f} kPa  "
                f"ΔP={found.delta_kPa:+.1f}  "
                f"vs corrected {1000.0 * found.offset_from_corrected_s:+.0f} ms"
            )
        lines.append(line)
    return lines


class StageBeeper:
    """Distinct beep trains per drilling stage. Falls back to QApplication.beep()."""

    def __init__(self, parent=None) -> None:
        self.muted = False
        self._effects = {}
        self._dir = Path(tempfile.mkdtemp(prefix="dentobot_stage_tones_"))
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QSoundEffect
        except Exception:
            self._effects = {}
            return
        for spec in STAGES:
            path = self._dir / f"{spec.key}.wav"
            write_tone_wav(path, spec.freq_hz, spec.pulses)
            effect = QSoundEffect(parent)
            effect.setSource(QUrl.fromLocalFile(str(path)))
            effect.setVolume(0.75)
            self._effects[spec.key] = effect

    def play(self, label: str) -> None:
        if self.muted:
            return
        effect = self._effects.get(label)
        if effect is not None:
            effect.play()
            return
        try:
            from PyQt6.QtWidgets import QApplication

            QApplication.beep()
        except Exception:
            pass
