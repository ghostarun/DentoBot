"""PyQtGraph overlays for the 50 ms median, p10–p90 envelope, and load marks.

Display-only. Does not open serial or command hardware.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore

from pressure_signal import (
    BinnedPressure,
    LoadBoundary,
    finite_runs,
)
from pressure_annotate import STAGE_BY_KEY, ManualAnnotation

MAX_ENVELOPE_SEGMENTS = 24
MAX_BOUNDARY_LINES = 40

MEDIAN_PEN = pg.mkPen("#7fd0ff", width=3)
DIM_RAW_PEN = pg.mkPen((220, 220, 230, 70), width=1)
FULL_RAW_PEN = pg.mkPen("w", width=2)
ENVELOPE_BRUSH = pg.mkBrush(127, 208, 255, 45)

BOUNDARY_PENS = {
    "contact": pg.mkPen("#7dff9a", width=2, style=QtCore.Qt.PenStyle.DashLine),
    "air": pg.mkPen("#ff9f43", width=2, style=QtCore.Qt.PenStyle.DashLine),
    "drop": pg.mkPen("#ff6b9d", width=2, style=QtCore.Qt.PenStyle.DashLine),
    "rise": pg.mkPen("#5ad0ff", width=2, style=QtCore.Qt.PenStyle.DashLine),
}
BOUNDARY_BRUSHES = {
    "contact": pg.mkBrush("#7dff9a"),
    "air": pg.mkBrush("#ff9f43"),
    "drop": pg.mkBrush("#ff6b9d"),
    "rise": pg.mkBrush("#5ad0ff"),
}
BOUNDARY_KINDS = ("contact", "air", "drop", "rise")


def add_envelope_pool(plot, n: int = MAX_ENVELOPE_SEGMENTS):
    items = []
    for _ in range(n):
        low = plot.plot(pen=None, connect="finite")
        high = plot.plot(pen=None, connect="finite")
        fill = pg.FillBetweenItem(low, high, brush=ENVELOPE_BRUSH)
        fill.setZValue(-6)
        plot.addItem(fill)
        items.append((low, high, fill))
    return items


def set_envelope(items, t: np.ndarray, low: np.ndarray, high: np.ndarray) -> None:
    runs = finite_runs(low)
    for index, (low_curve, high_curve, fill) in enumerate(items):
        if index < len(runs):
            start, end = runs[index]
            low_curve.setData(t[start:end], low[start:end])
            high_curve.setData(t[start:end], high[start:end])
            fill.show()
        else:
            low_curve.setData([], [])
            high_curve.setData([], [])
            fill.hide()


def add_median_curve(plot, name: str = "50 ms median"):
    return plot.plot(name=name, pen=MEDIAN_PEN, connect="finite")


def add_boundary_scatters(plot) -> dict[str, pg.ScatterPlotItem]:
    items: dict[str, pg.ScatterPlotItem] = {}
    names = {
        "contact": "Contact",
        "air": "Air / breakthrough",
        "drop": "Load drop",
        "rise": "Load rise",
    }
    symbols = {"contact": "s", "air": "d", "drop": "t", "rise": "t1"}
    for kind in BOUNDARY_KINDS:
        scatter = pg.ScatterPlotItem(
            symbol=symbols[kind],
            size=12,
            brush=BOUNDARY_BRUSHES[kind],
            pen=pg.mkPen("#111111", width=0.5),
            name=names[kind],
        )
        scatter.setZValue(20)
        plot.addItem(scatter)
        items[kind] = scatter
    return items


def add_boundary_lines(plot, n: int = MAX_BOUNDARY_LINES) -> list[pg.InfiniteLine]:
    lines: list[pg.InfiniteLine] = []
    for _ in range(n):
        line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=BOUNDARY_PENS["contact"],
        )
        line.setZValue(-4)
        line.hide()
        plot.addItem(line)
        lines.append(line)
    return lines


def boundary_marker_y(binned: BinnedPressure, time_s: float, fallback: float) -> float:
    if binned.time_s.size == 0:
        return fallback
    index = int(np.searchsorted(binned.time_s, time_s, side="left"))
    index = min(max(index, 0), int(binned.time_s.size) - 1)
    value = float(binned.median_kPa[index])
    if np.isfinite(value):
        return value
    return fallback


def set_boundaries(
    scatters: dict[str, pg.ScatterPlotItem],
    lines: list[pg.InfiniteLine],
    bounds: list[LoadBoundary],
    binned: BinnedPressure,
    t0: float,
    t1: float,
) -> list[LoadBoundary]:
    visible = [item for item in bounds if t0 <= item.time_s <= t1]
    grouped: dict[str, tuple[list[float], list[float]]] = {
        kind: ([], []) for kind in BOUNDARY_KINDS
    }
    for item in visible:
        if item.kind not in grouped:
            continue
        grouped[item.kind][0].append(item.time_s)
        grouped[item.kind][1].append(
            boundary_marker_y(binned, item.time_s, item.to_kPa)
        )
    for kind, scatter in scatters.items():
        xs, ys = grouped[kind]
        scatter.setData(xs, ys)

    for index, line in enumerate(lines):
        if index < len(visible):
            item = visible[index]
            line.setPen(BOUNDARY_PENS.get(item.kind, BOUNDARY_PENS["contact"]))
            line.setPos(item.time_s)
            line.show()
        else:
            line.hide()
    return visible


def clear_smooth_layer(
    envelope_items,
    median_curve,
    scatters: dict[str, pg.ScatterPlotItem],
    lines: list[pg.InfiniteLine],
) -> None:
    set_envelope(
        envelope_items,
        np.asarray([], dtype=np.float64),
        np.asarray([], dtype=np.float64),
        np.asarray([], dtype=np.float64),
    )
    median_curve.setData([], [])
    for scatter in scatters.values():
        scatter.setData([], [])
    for line in lines:
        line.hide()


MAX_ANNOTATION_LINES = 80


def _annotation_pen(label: str, press: bool):
    spec = STAGE_BY_KEY.get(label)
    color = spec.color if spec else "#ffffff"
    if press:
        return pg.mkPen(color, width=1, style=QtCore.Qt.PenStyle.DotLine)
    return pg.mkPen(color, width=3)


def add_annotation_lines(plot, n: int = MAX_ANNOTATION_LINES) -> list[pg.InfiniteLine]:
    lines: list[pg.InfiniteLine] = []
    for _ in range(n):
        line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#ffffff", width=2))
        line.setZValue(12)
        line.hide()
        plot.addItem(line)
        lines.append(line)
    return lines


def set_annotation_lines(
    lines: list[pg.InfiniteLine],
    annotations: list[ManualAnnotation],
    t0: float | None = None,
    t1: float | None = None,
) -> None:
    visible: list[tuple[float, object, bool]] = []
    for item in annotations:
        if t0 is not None and item.corrected_s < t0 and item.press_s < t0:
            continue
        if t1 is not None and item.corrected_s > t1 and item.press_s > t1:
            continue
        if item.kind == "annotate":
            visible.append((item.corrected_s, item, False))
            visible.append((item.press_s, item, True))
        else:
            visible.append((item.press_s, item, True))
    for index, line in enumerate(lines):
        if index < len(visible):
            time_s, item, is_press = visible[index]
            line.setPen(_annotation_pen(item.label, is_press or item.kind == "cue"))
            line.setPos(time_s)
            line.show()
        else:
            line.hide()
