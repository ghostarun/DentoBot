#!/usr/bin/env python3
"""Inspect Record3D / iPhone LiDAR OBJ point-cloud exports.

Record3D's OBJ point-cloud export is a coloured vertex list in the iPhone
camera frame, in metres, typically with no faces:

    v x y z r g b

This host tool opens a zip, a folder, or a single OBJ so those scans can be
viewed and checked before any Slicer/RAS registration work. It does not
convert camera coordinates into Slicer RAS and does not treat a plausible
render as anatomical or clinical validation.

Run with the host GUI interpreter, not Slicer or the inference Conda env:

    /home/light-tarun/pressure-env/bin/python \\
        scripts/view_record3d_scan.py \\
        --source /home/light-tarun/dentobot/data/3dscan_iphone.zip
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


SCRIPT_PATH = Path(__file__).resolve()
OBJ_SUFFIXES = {".obj"}
ARCHIVE_SUFFIXES = {".zip"}
DEFAULT_PLAY_FPS = 8.0
DEFAULT_POINT_SIZE = 3.0
DISPLAY_POINT_CAP = 250_000
TINY_FRAME_FRACTION = 0.25


def workspace_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "data").is_dir() and (parent / "ros2_ws").is_dir():
            return parent
    return Path("/home/light-tarun/dentobot")


DEFAULT_SOURCE = workspace_root() / "data" / "3dscan_iphone.zip"


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PointCloud:
    xyz: np.ndarray
    rgb: np.ndarray | None
    source_name: str
    n_raw: int
    n_dropped: int

    @property
    def n_points(self) -> int:
        return int(self.xyz.shape[0])

    @property
    def has_color(self) -> bool:
        return self.rgb is not None and self.rgb.shape[0] == self.n_points


@dataclass(slots=True)
class FrameRef:
    name: str
    key: str
    size_bytes: int
    index: int | None


@dataclass(slots=True)
class ScanCatalog:
    source: Path
    kind: str
    frames: list[FrameRef]
    missing_indices: list[int] = field(default_factory=list)

    @property
    def n_frames(self) -> int:
        return len(self.frames)


@dataclass(slots=True)
class FrameReport:
    name: str
    n_points: int
    n_dropped: int
    has_color: bool
    xyz_min: np.ndarray
    xyz_max: np.ndarray
    centroid: np.ndarray
    extent_m: np.ndarray
    warnings: list[str]


class ScanStore:
    """Read OBJ frames from a zip, directory, or single file without unpacking."""

    def __init__(self, source: Path) -> None:
        self.source = source.expanduser().resolve()
        if not self.source.exists():
            raise FileNotFoundError(f"Scan source not found: {self.source}")
        self._zip: zipfile.ZipFile | None = None
        self.catalog = self._open_catalog()

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def read_bytes(self, frame: FrameRef) -> bytes:
        if self.catalog.kind == "zip":
            assert self._zip is not None
            return self._zip.read(frame.key)
        return Path(frame.key).read_bytes()

    def load_cloud(self, frame: FrameRef) -> PointCloud:
        return parse_obj_point_cloud(self.read_bytes(frame), frame.name)

    def _open_catalog(self) -> ScanCatalog:
        suffix = self.source.suffix.lower()
        if self.source.is_file() and suffix in ARCHIVE_SUFFIXES:
            self._zip = zipfile.ZipFile(self.source)
            frames = []
            for info in self._zip.infolist():
                path = Path(info.filename)
                if info.is_dir() or path.suffix.lower() not in OBJ_SUFFIXES:
                    continue
                if path.name.startswith("._") or "__MACOSX" in path.parts:
                    continue
                frames.append(
                    FrameRef(
                        name=path.name,
                        key=info.filename,
                        size_bytes=int(info.file_size),
                        index=_frame_index(path.stem),
                    )
                )
            if not frames:
                raise ValueError(f"No OBJ files inside zip: {self.source}")
            frames.sort(key=_frame_sort_key)
            return ScanCatalog(
                source=self.source,
                kind="zip",
                frames=frames,
                missing_indices=_missing_indices(frames),
            )

        if self.source.is_dir():
            paths = [
                p
                for p in self.source.rglob("*")
                if p.is_file()
                and p.suffix.lower() in OBJ_SUFFIXES
                and not p.name.startswith("._")
            ]
            if not paths:
                raise ValueError(f"No OBJ files in directory: {self.source}")
            frames = [
                FrameRef(
                    name=p.name,
                    key=str(p),
                    size_bytes=int(p.stat().st_size),
                    index=_frame_index(p.stem),
                )
                for p in paths
            ]
            frames.sort(key=_frame_sort_key)
            return ScanCatalog(
                source=self.source,
                kind="dir",
                frames=frames,
                missing_indices=_missing_indices(frames),
            )

        if self.source.is_file() and suffix in OBJ_SUFFIXES:
            frame = FrameRef(
                name=self.source.name,
                key=str(self.source),
                size_bytes=int(self.source.stat().st_size),
                index=_frame_index(self.source.stem),
            )
            return ScanCatalog(self.source, "obj", [frame], [])

        raise ValueError(
            f"Unsupported scan source {self.source}. "
            "Provide a Record3D OBJ, a folder of OBJ files, or a zip of OBJ files."
        )


def _frame_index(stem: str) -> int | None:
    return int(stem) if stem.isdigit() else None


def _frame_sort_key(frame: FrameRef) -> tuple[int, str]:
    return (frame.index if frame.index is not None else 10**12, frame.name)


def _missing_indices(frames: list[FrameRef]) -> list[int]:
    present = [f.index for f in frames if f.index is not None]
    if len(present) < 2:
        return []
    lo, hi = min(present), max(present)
    have = set(present)
    return [i for i in range(lo, hi + 1) if i not in have]


def parse_obj_point_cloud(data: bytes, source_name: str = "") -> PointCloud:
    payload = b"\n".join(
        line[2:]
        for line in data.splitlines()
        if line.startswith(b"v ") or line.startswith(b"v\t")
    )
    if not payload.strip():
        return PointCloud(
            xyz=np.zeros((0, 3), dtype=np.float32),
            rgb=None,
            source_name=source_name,
            n_raw=0,
            n_dropped=0,
        )

    first = payload.splitlines()[0].split()
    ncols = len(first)
    if ncols < 3:
        raise ValueError(f"{source_name or 'OBJ'} vertex line has fewer than 3 values")

    try:
        arr = np.loadtxt(io.BytesIO(payload), dtype=np.float64, ndmin=2)
    except ValueError:
        rows = []
        for line in payload.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            rows.append([float(x) for x in parts[: max(6, min(len(parts), 7))]])
        if not rows:
            raise ValueError(f"{source_name or 'OBJ'} contains no usable vertices")
        width = max(len(r) for r in rows)
        arr = np.zeros((len(rows), width), dtype=np.float64)
        for i, row in enumerate(rows):
            arr[i, : len(row)] = row
        ncols = width

    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[1] < 3:
        raise ValueError(f"{source_name or 'OBJ'} vertices do not contain XYZ")

    xyz = arr[:, :3]
    finite = np.isfinite(xyz).all(axis=1)
    n_raw = int(xyz.shape[0])
    n_dropped = int((~finite).sum())
    xyz = xyz[finite]

    rgb = None
    if arr.shape[1] >= 6:
        rgb = arr[finite, 3:6]
        if rgb.size and float(np.nanmax(rgb)) > 1.5:
            rgb = rgb / 255.0
        rgb = np.clip(rgb, 0.0, 1.0).astype(np.float32)

    return PointCloud(
        xyz=xyz.astype(np.float32, copy=False),
        rgb=rgb,
        source_name=source_name,
        n_raw=n_raw,
        n_dropped=n_dropped,
    )


def report_cloud(cloud: PointCloud) -> FrameReport:
    warnings: list[str] = []
    if cloud.n_points == 0:
        warnings.append("No finite vertices")
        zeros = np.zeros(3, dtype=np.float64)
        return FrameReport(
            name=cloud.source_name,
            n_points=0,
            n_dropped=cloud.n_dropped,
            has_color=False,
            xyz_min=zeros,
            xyz_max=zeros,
            centroid=zeros,
            extent_m=zeros,
            warnings=warnings,
        )

    xyz = cloud.xyz.astype(np.float64, copy=False)
    xyz_min = xyz.min(axis=0)
    xyz_max = xyz.max(axis=0)
    extent = xyz_max - xyz_min
    if cloud.n_dropped:
        warnings.append(f"Dropped {cloud.n_dropped} non-finite vertices")
    if not cloud.has_color:
        warnings.append("No vertex colours")
    if float(extent.max()) <= 1e-6:
        warnings.append("Degenerate bounding box")
    elif float(extent.max()) > 5.0:
        warnings.append(
            f"Extent {extent.max():.2f} m is large for an intraoral LiDAR capture"
        )
    return FrameReport(
        name=cloud.source_name,
        n_points=cloud.n_points,
        n_dropped=cloud.n_dropped,
        has_color=cloud.has_color,
        xyz_min=xyz_min,
        xyz_max=xyz_max,
        centroid=xyz.mean(axis=0),
        extent_m=extent,
        warnings=warnings,
    )


def format_extent_mm(extent_m: np.ndarray) -> str:
    mm = extent_m * 1000.0
    return f"{mm[0]:.1f} × {mm[1]:.1f} × {mm[2]:.1f} mm"


def format_xyz_m(values: np.ndarray) -> str:
    return f"({values[0]:+.4f}, {values[1]:+.4f}, {values[2]:+.4f}) m"


def format_index_ranges(indices: list[int]) -> str:
    if not indices:
        return "none"
    ranges: list[str] = []
    start = prev = indices[0]
    for value in indices[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}" if start == prev else f"{start}–{prev}")
        start = prev = value
    ranges.append(f"{start}" if start == prev else f"{start}–{prev}")
    return ", ".join(ranges)


def subsample_cloud(cloud: PointCloud, cap: int) -> tuple[np.ndarray, np.ndarray | None]:
    n = cloud.n_points
    if n <= cap:
        return cloud.xyz, cloud.rgb
    # Record3D vertices are scan-order, so a stride keeps spatial coverage.
    step = int(np.ceil(n / cap))
    xyz = cloud.xyz[::step]
    rgb = None if cloud.rgb is None else cloud.rgb[::step]
    return xyz, rgb


def height_colors(xyz: np.ndarray) -> np.ndarray:
    z = xyz[:, 2]
    zmin = float(z.min()) if z.size else 0.0
    zmax = float(z.max()) if z.size else 1.0
    span = max(zmax - zmin, 1e-9)
    t = (z - zmin) / span
    # Teal-to-amber ramp that stays readable on a dark background.
    rgb = np.column_stack((0.12 + 0.84 * t, 0.62 - 0.18 * t, 0.72 - 0.62 * t))
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


def catalog_summary(catalog: ScanCatalog) -> str:
    sizes = np.array([f.size_bytes for f in catalog.frames], dtype=np.int64)
    median = int(np.median(sizes)) if sizes.size else 0
    tiny = [
        f.name
        for f in catalog.frames
        if median and f.size_bytes < TINY_FRAME_FRACTION * median
    ]
    lines = [
        f"Source: {catalog.source}",
        f"Kind: {catalog.kind}",
        f"OBJ frames: {catalog.n_frames}",
    ]
    indexed = [f.index for f in catalog.frames if f.index is not None]
    if indexed:
        lines.append(f"Index range: {min(indexed)}–{max(indexed)}")
    lines.append(f"Missing indices: {format_index_ranges(catalog.missing_indices)}")
    if sizes.size:
        lines.append(
            "Uncompressed OBJ sizes: "
            f"min {int(sizes.min())} B, median {median} B, max {int(sizes.max())} B"
        )
    if tiny:
        preview = ", ".join(tiny[:12])
        extra = "" if len(tiny) <= 12 else f" … +{len(tiny) - 12} more"
        lines.append(f"Unusually small frames: {preview}{extra}")
    return "\n".join(lines)


def report_text(store: ScanStore, scan_all: bool) -> str:
    catalog = store.catalog
    blocks = [catalog_summary(catalog), ""]
    if not scan_all:
        cloud = store.load_cloud(catalog.frames[0])
        blocks.append(_format_frame_report(report_cloud(cloud)))
        blocks.append("")
        blocks.append(
            "Pass --scan-all to parse every OBJ. Coordinates are Record3D "
            "camera metres, not Slicer RAS."
        )
        return "\n".join(blocks)

    counts = []
    for i, frame in enumerate(catalog.frames, start=1):
        report = report_cloud(store.load_cloud(frame))
        counts.append(report.n_points)
        if report.warnings:
            blocks.append(_format_frame_report(report))
            blocks.append("")
        if i == 1 or i == catalog.n_frames or i % 50 == 0:
            print(f"parsed {i}/{catalog.n_frames}: {frame.name}", file=sys.stderr)
    counts_arr = np.array(counts, dtype=np.int64)
    blocks.append(
        "All-frame point counts: "
        f"min {int(counts_arr.min())}, median {int(np.median(counts_arr))}, "
        f"max {int(counts_arr.max())}"
    )
    empty = [f.name for f, n in zip(catalog.frames, counts) if n == 0]
    if empty:
        blocks.append("Empty frames: " + ", ".join(empty))
    else:
        blocks.append("Empty frames: none")
    return "\n".join(blocks).rstrip() + "\n"


def _format_frame_report(report: FrameReport) -> str:
    lines = [
        f"Frame: {report.name}",
        f"Points: {report.n_points:,}",
        f"Colours: {'RGB 0–1' if report.has_color else 'none'}",
        f"Centroid: {format_xyz_m(report.centroid)}",
        f"BBox min: {format_xyz_m(report.xyz_min)}",
        f"BBox max: {format_xyz_m(report.xyz_max)}",
        f"Extent: {format_extent_mm(report.extent_m)}",
    ]
    if report.warnings:
        lines.append("Warnings: " + "; ".join(report.warnings))
    return "\n".join(lines)


def run_self_test() -> int:
    ascii_obj = (
        "v 0.10 -0.20 0.30 1.0 0.0 0.0\n"
        "v 0.11 -0.20 0.30 0.0 1.0 0.0\n"
        "v 0.10 -0.19 0.30 0.0 0.0 1.0\n"
        "f 1 2 3\n"
    ).encode("ascii")
    cloud = parse_obj_point_cloud(ascii_obj, "synthetic.obj")
    assert cloud.n_points == 3, cloud.n_points
    assert cloud.has_color
    assert np.allclose(cloud.xyz[0], (0.10, -0.20, 0.30))
    rgb255 = parse_obj_point_cloud(b"v 1 2 3 255 128 0\n", "rgb255.obj")
    assert np.allclose(rgb255.rgb[0], (1.0, 128 / 255.0, 0.0), atol=1e-5)
    empty = parse_obj_point_cloud(b"# comment only\n", "empty.obj")
    assert empty.n_points == 0
    print("self-test passed")
    return 0


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


def launch_gui(source: Path) -> int:
    from vispy.app import use_app
    from vispy import scene
    from PyQt6 import QtCore, QtGui, QtWidgets

    use_app("pyqt6")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("DENTOBOT Record3D Scan Viewer")
    window = ScanViewerWindow(source, scene)
    window.show()
    window.load_source(source)
    return app.exec()


class ScanViewerWindow:
    def __init__(self, initial_source: Path, scene_module) -> None:
        from PyQt6 import QtCore, QtGui, QtWidgets

        self._Qt = QtWidgets
        self._QtCore = QtCore
        self._scene = scene_module
        self.store: ScanStore | None = None
        self._cloud: PointCloud | None = None
        self._playing = False
        self._fit_on_next = True

        self.win = QtWidgets.QMainWindow()
        self.win.setWindowTitle("DENTOBOT Record3D Scan Viewer")
        self.win.resize(1280, 800)
        self.win.setStyleSheet(_stylesheet())
        self.win.closeEvent = self._on_close  # type: ignore[method-assign]

        root = QtWidgets.QWidget()
        self.win.setCentralWidget(root)
        split = QtWidgets.QSplitter()
        split.setChildrenCollapsible(False)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(split)

        self.canvas = scene_module.SceneCanvas(
            keys="interactive",
            show=False,
            bgcolor="#101418",
            create_native=True,
        )
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = "arcball"
        self.view.camera.fov = 45.0
        self.scatter = scene_module.visuals.Markers(
            parent=self.view.scene,
            scaling="fixed",
            antialias=0,
            spherical=False,
        )
        self.scatter.set_gl_state(depth_test=True, blend=False)
        self.axis = scene_module.visuals.XYZAxis(parent=self.view.scene)
        native = self.canvas.native
        native.setMinimumSize(640, 480)
        split.addWidget(native)

        side = QtWidgets.QWidget()
        side.setMinimumWidth(320)
        side.setMaximumWidth(420)
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(8, 0, 0, 0)
        split.addWidget(side)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 2)

        source_row = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Open zip/OBJ…")
        self.open_btn.clicked.connect(self._choose_file)
        self.open_dir_btn = QtWidgets.QPushButton("Open folder…")
        self.open_dir_btn.clicked.connect(self._choose_folder)
        self.source_label = QtWidgets.QLabel(str(initial_source))
        self.source_label.setWordWrap(True)
        source_row.addWidget(self.open_btn)
        source_row.addWidget(self.open_dir_btn)
        source_row.addWidget(self.source_label, 1)
        side_layout.addLayout(source_row)

        self.hint = QtWidgets.QLabel(
            "Drag to orbit · Shift-drag to pan · Scroll to zoom · "
            "Space play/pause · ←/→ frames · R reset view"
        )
        self.hint.setWordWrap(True)
        side_layout.addWidget(self.hint)

        self.frame_list = QtWidgets.QListWidget()
        self.frame_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.frame_list.currentRowChanged.connect(self._on_list_row)
        side_layout.addWidget(self.frame_list, 2)

        transport = QtWidgets.QHBoxLayout()
        self.prev_btn = QtWidgets.QPushButton("Prev")
        self.play_btn = QtWidgets.QPushButton("Play")
        self.next_btn = QtWidgets.QPushButton("Next")
        self.prev_btn.clicked.connect(lambda: self.step_frame(-1))
        self.next_btn.clicked.connect(lambda: self.step_frame(1))
        self.play_btn.clicked.connect(self.toggle_play)
        transport.addWidget(self.prev_btn)
        transport.addWidget(self.play_btn, 1)
        transport.addWidget(self.next_btn)
        side_layout.addLayout(transport)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._on_slider)
        side_layout.addWidget(self.slider)

        self.frame_label = QtWidgets.QLabel("Frame —")
        side_layout.addWidget(self.frame_label)

        size_row = QtWidgets.QHBoxLayout()
        size_row.addWidget(QtWidgets.QLabel("Point size"))
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.size_slider.setRange(10, 120)
        self.size_slider.setValue(int(DEFAULT_POINT_SIZE * 10))
        self.size_slider.valueChanged.connect(lambda _: self._redraw(fit=False))
        size_row.addWidget(self.size_slider, 1)
        side_layout.addLayout(size_row)

        self.color_combo = QtWidgets.QComboBox()
        self.color_combo.addItems(["Vertex RGB", "Height (Z)"])
        self.color_combo.currentIndexChanged.connect(lambda _: self._redraw(fit=False))
        side_layout.addWidget(self.color_combo)

        self.scan_all_btn = QtWidgets.QPushButton("Verify all frames")
        self.scan_all_btn.clicked.connect(self._verify_all_frames)
        side_layout.addWidget(self.scan_all_btn)

        self.stats = QtWidgets.QPlainTextEdit()
        self.stats.setReadOnly(True)
        self.stats.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        side_layout.addWidget(self.stats, 3)

        note = QtWidgets.QLabel(
            "Camera-frame metres from Record3D. This is a scan-quality check, "
            "not a Slicer RAS import or registration result."
        )
        note.setWordWrap(True)
        side_layout.addWidget(note)

        self.timer = QtCore.QTimer(self.win)
        self.timer.setInterval(int(1000 / DEFAULT_PLAY_FPS))
        self.timer.timeout.connect(lambda: self.step_frame(1, wrap=True))

        QtGui.QShortcut(QtGui.QKeySequence("Space"), self.win).activated.connect(
            self.toggle_play
        )
        QtGui.QShortcut(QtGui.QKeySequence("Left"), self.win).activated.connect(
            lambda: self.step_frame(-1)
        )
        QtGui.QShortcut(QtGui.QKeySequence("Right"), self.win).activated.connect(
            lambda: self.step_frame(1)
        )
        QtGui.QShortcut(QtGui.QKeySequence("R"), self.win).activated.connect(
            lambda: self._redraw(fit=True)
        )
        QtGui.QShortcut(QtGui.QKeySequence("O"), self.win).activated.connect(
            self._choose_file
        )

    def show(self) -> None:
        self.win.show()

    def load_source(self, source: Path) -> None:
        if self.store is not None:
            self.store.close()
        try:
            self.store = ScanStore(source)
        except (OSError, ValueError) as exc:
            self._Qt.QMessageBox.critical(self.win, "Cannot open scan", str(exc))
            return
        self.source_label.setText(str(self.store.catalog.source))
        self._populate_frames()
        self._fit_on_next = True
        self.set_frame(0)

    def _populate_frames(self) -> None:
        assert self.store is not None
        catalog = self.store.catalog
        sizes = np.array([f.size_bytes for f in catalog.frames], dtype=np.int64)
        median = float(np.median(sizes)) if sizes.size else 0.0
        self.frame_list.blockSignals(True)
        self.frame_list.clear()
        for frame in catalog.frames:
            item = self._Qt.QListWidgetItem(
                f"{frame.name}   ({frame.size_bytes / 1e6:.2f} MB)"
            )
            if median and frame.size_bytes < TINY_FRAME_FRACTION * median:
                item.setForeground(self._QtCore.Qt.GlobalColor.yellow)
            self.frame_list.addItem(item)
        self.frame_list.blockSignals(False)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(catalog.n_frames - 1, 0))
        self.slider.setValue(0)
        self.slider.blockSignals(False)

    def current_index(self) -> int:
        return int(self.slider.value())

    def set_frame(self, index: int) -> None:
        if self.store is None or not self.store.catalog.frames:
            return
        index = int(np.clip(index, 0, self.store.catalog.n_frames - 1))
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self.frame_list.blockSignals(True)
        self.frame_list.setCurrentRow(index)
        self.frame_list.blockSignals(False)
        frame = self.store.catalog.frames[index]
        try:
            self._cloud = self.store.load_cloud(frame)
        except Exception as exc:  # noqa: BLE001 — show parse failures in the panel
            self._cloud = None
            self.stats.setPlainText(f"Failed to parse {frame.name}:\n{exc}")
            self.scatter.set_data(np.zeros((1, 3), dtype=np.float32), size=0.1)
            return
        self._redraw(fit=self._fit_on_next)
        self._fit_on_next = False

    def step_frame(self, delta: int, wrap: bool = False) -> None:
        if self.store is None:
            return
        n = self.store.catalog.n_frames
        if n <= 0:
            return
        nxt = self.current_index() + delta
        if wrap:
            nxt %= n
        elif nxt < 0 or nxt >= n:
            self._playing = False
            self.timer.stop()
            self.play_btn.setText("Play")
            return
        self.set_frame(nxt)

    def toggle_play(self) -> None:
        self._playing = not self._playing
        if self._playing:
            self.play_btn.setText("Pause")
            self.timer.start()
        else:
            self.play_btn.setText("Play")
            self.timer.stop()

    def _on_slider(self, value: int) -> None:
        self.set_frame(value)

    def _on_list_row(self, row: int) -> None:
        if row >= 0:
            self.set_frame(row)

    def _choose_file(self) -> None:
        path, _ = self._Qt.QFileDialog.getOpenFileName(
            self.win,
            "Open Record3D OBJ or zip",
            str(workspace_root() / "data"),
            "Record3D scans (*.zip *.obj);;All files (*)",
        )
        if path:
            self.load_source(Path(path))

    def _choose_folder(self) -> None:
        directory = self._Qt.QFileDialog.getExistingDirectory(
            self.win,
            "Open folder of OBJ frames",
            str(workspace_root() / "data"),
        )
        if directory:
            self.load_source(Path(directory))

    def _point_size(self) -> float:
        return self.size_slider.value() / 10.0

    def _redraw(self, fit: bool) -> None:
        cloud = self._cloud
        if cloud is None:
            return
        xyz, rgb = subsample_cloud(cloud, DISPLAY_POINT_CAP)
        if xyz.shape[0] == 0:
            self.scatter.set_data(np.zeros((1, 3), dtype=np.float32), size=0.1)
        else:
            if self.color_combo.currentIndex() == 1 or rgb is None:
                colors = height_colors(xyz)
            else:
                colors = rgb
            self.scatter.set_data(
                xyz,
                face_color=colors,
                edge_color=colors,
                edge_width=0,
                size=self._point_size(),
                symbol="o",
            )
        if fit and cloud.n_points:
            lo = cloud.xyz.min(axis=0)
            hi = cloud.xyz.max(axis=0)
            self.view.camera.set_range(
                x=(float(lo[0]), float(hi[0])),
                y=(float(lo[1]), float(hi[1])),
                z=(float(lo[2]), float(hi[2])),
            )
        self._update_stats()

    def _update_stats(self) -> None:
        if self.store is None or self._cloud is None:
            return
        catalog = self.store.catalog
        report = report_cloud(self._cloud)
        shown = min(report.n_points, DISPLAY_POINT_CAP)
        idx = self.current_index()
        frame = catalog.frames[idx]
        lines = [
            catalog_summary(catalog),
            "",
            _format_frame_report(report),
            f"Displaying: {shown:,} of {report.n_points:,} points",
            f"File bytes: {frame.size_bytes:,}",
        ]
        self.frame_label.setText(
            f"Frame {idx + 1} / {catalog.n_frames}   {frame.name}"
        )
        self.stats.setPlainText("\n".join(lines))

    def _verify_all_frames(self) -> None:
        if self.store is None:
            return
        catalog = self.store.catalog
        progress = self._Qt.QProgressDialog(
            "Parsing every OBJ frame…",
            "Cancel",
            0,
            catalog.n_frames,
            self.win,
        )
        progress.setWindowModality(self._QtCore.Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        counts: list[int] = []
        warned: list[str] = []
        cancelled = False
        for i, frame in enumerate(catalog.frames):
            progress.setValue(i)
            progress.setLabelText(f"Parsing {frame.name} ({i + 1}/{catalog.n_frames})")
            self._Qt.QApplication.processEvents()
            if progress.wasCanceled():
                cancelled = True
                break
            try:
                report = report_cloud(self.store.load_cloud(frame))
            except Exception as exc:  # noqa: BLE001
                counts.append(0)
                warned.append(f"{frame.name}: parse error ({exc})")
                continue
            counts.append(report.n_points)
            if report.warnings:
                warned.append(f"{frame.name}: {'; '.join(report.warnings)}")
        progress.setValue(catalog.n_frames if not cancelled else progress.value())
        if cancelled:
            return
        arr = np.array(counts, dtype=np.int64)
        extra = [
            "",
            "Full-sequence parse",
            f"Point counts min/median/max: {int(arr.min())} / {int(np.median(arr))} / {int(arr.max())}",
        ]
        empty = [f.name for f, n in zip(catalog.frames, counts) if n == 0]
        extra.append("Empty frames: " + (", ".join(empty) if empty else "none"))
        if warned:
            extra.append("Frame warnings:")
            extra.extend(warned[:40])
            if len(warned) > 40:
                extra.append(f"… {len(warned) - 40} more")
        else:
            extra.append("Frame warnings: none")
        current = self.stats.toPlainText().rstrip()
        self.stats.setPlainText(current + "\n" + "\n".join(extra))

    def _on_close(self, event) -> None:
        self.timer.stop()
        if self.store is not None:
            self.store.close()
        event.accept()


def _stylesheet() -> str:
    return """
    QMainWindow, QWidget { background: #15181d; color: #e8eaed; }
    QLabel { color: #d5d9e0; }
    QPlainTextEdit {
        background: #0f1216;
        color: #e8eaed;
        border: 1px solid #2a313c;
        font-family: monospace;
        font-size: 12px;
    }
    QListWidget {
        background: #0f1216;
        color: #e8eaed;
        border: 1px solid #2a313c;
    }
    QListWidget::item:selected { background: #2f5d8a; }
    QPushButton {
        background: #2b3340;
        color: #f3f5f7;
        border: 1px solid #3d4756;
        padding: 6px 10px;
        border-radius: 4px;
    }
    QPushButton:hover { background: #3a4554; }
    QSlider::groove:horizontal { height: 6px; background: #2a313c; }
    QSlider::handle:horizontal {
        width: 14px; margin: -5px 0; background: #7aa2d6; border-radius: 7px;
    }
    QComboBox {
        background: #0f1216; color: #e8eaed; padding: 4px; border: 1px solid #2a313c;
    }
    """


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="View and verify Record3D iPhone OBJ point-cloud exports."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="OBJ file, folder of OBJ frames, or zip (default: data/3dscan_iphone.zip)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print catalog/frame stats without opening the 3D window",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="With --report-only, parse every OBJ frame",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a tiny synthetic OBJ parser check and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    if args.report_only:
        store = ScanStore(args.source)
        try:
            sys.stdout.write(report_text(store, scan_all=args.scan_all))
        finally:
            store.close()
        return 0
    return launch_gui(args.source)


if __name__ == "__main__":
    sys.exit(main())
