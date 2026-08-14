#!/usr/bin/env python3
"""Publish manually selected DENTOBOT joint states from a small Qt window.

This executable is visualization-only. It has no command subscriber,
controller, hardware interface, or robot actuation path.
"""

from dataclasses import dataclass
from itertools import combinations
from math import cos, degrees, isfinite, pi, radians, sin, sqrt
import os
from pathlib import Path
import signal
import struct
import sys
from xml.etree import ElementTree


Vector3 = tuple[float, float, float]
Matrix4 = tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True)
class JointControl:
    """A movable URDF joint expressed in operator-friendly display units."""

    name: str
    joint_type: str
    lower_si: float
    upper_si: float
    display_unit: str

    @property
    def lower_display(self) -> float:
        return self.si_to_display(self.lower_si)

    @property
    def upper_display(self) -> float:
        return self.si_to_display(self.upper_si)

    def si_to_display(self, value: float) -> float:
        if self.joint_type == "prismatic":
            return value * 1000.0
        return degrees(value)

    def display_to_si(self, value: float) -> float:
        if self.joint_type == "prismatic":
            return value / 1000.0
        return radians(value)

    def clamp_si(self, value: float) -> float:
        return min(max(value, self.lower_si), self.upper_si)


@dataclass(frozen=True)
class JointKinematics:
    """One URDF parent-to-child transform and its optional motion."""

    name: str
    joint_type: str
    parent: str
    child: str
    origin: Matrix4
    axis: Vector3


@dataclass(frozen=True)
class CollisionGeometry:
    """Eight collision-mesh bounding corners expressed in the link frame."""

    link: str
    corners: tuple[Vector3, ...]


@dataclass(frozen=True)
class AxisAlignedBox:
    """A coarse mesh-derived AABB expressed in base_link coordinates."""

    link: str
    minimum: Vector3
    maximum: Vector3


@dataclass(frozen=True)
class ClearanceViolation:
    """A non-adjacent pair whose AABB separation is below the draft margin."""

    first_link: str
    second_link: str
    distance_m: float


@dataclass(frozen=True)
class ClearanceEvaluation:
    """Draft state feedback for manual workspace exploration."""

    boxes: tuple[AxisAlignedBox, ...]
    violations: tuple[ClearanceViolation, ...]
    checked_pair_count: int
    burr_origin_m: Vector3


def _numbers(text: str | None, *, default: Vector3) -> Vector3:
    if text is None:
        return default
    values = tuple(float(value) for value in text.split())
    if len(values) != 3 or not all(isfinite(value) for value in values):
        raise ValueError(f"Expected three finite values, received {text!r}")
    return values  # type: ignore[return-value]


def _identity_matrix() -> Matrix4:
    return (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _matrix_multiply(first: Matrix4, second: Matrix4) -> Matrix4:
    return tuple(
        tuple(
            sum(first[row][index] * second[index][column] for index in range(4))
            for column in range(4)
        )
        for row in range(4)
    )


def _pose_matrix(xyz: Vector3, rpy: Vector3) -> Matrix4:
    """Return the URDF fixed-axis roll/pitch/yaw pose matrix."""
    roll, pitch, yaw = rpy
    cr, sr = cos(roll), sin(roll)
    cp, sp = cos(pitch), sin(pitch)
    cy, sy = cos(yaw), sin(yaw)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, xyz[0]),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, xyz[1]),
        (-sp, cp * sr, cp * cr, xyz[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def _axis_motion_matrix(joint_type: str, axis: Vector3, value: float) -> Matrix4:
    axis_length = sqrt(sum(component * component for component in axis))
    if axis_length <= 0.0:
        raise ValueError("A movable joint has a zero-length axis")
    x, y, z = (component / axis_length for component in axis)
    if joint_type == "prismatic":
        return _pose_matrix((x * value, y * value, z * value), (0.0, 0.0, 0.0))
    if joint_type in {"revolute", "continuous"}:
        cosine, sine = cos(value), sin(value)
        one_minus_cosine = 1.0 - cosine
        return (
            (
                cosine + x * x * one_minus_cosine,
                x * y * one_minus_cosine - z * sine,
                x * z * one_minus_cosine + y * sine,
                0.0,
            ),
            (
                y * x * one_minus_cosine + z * sine,
                cosine + y * y * one_minus_cosine,
                y * z * one_minus_cosine - x * sine,
                0.0,
            ),
            (
                z * x * one_minus_cosine - y * sine,
                z * y * one_minus_cosine + x * sine,
                cosine + z * z * one_minus_cosine,
                0.0,
            ),
            (0.0, 0.0, 0.0, 1.0),
        )
    return _identity_matrix()


def _transform_point(matrix: Matrix4, point: Vector3) -> Vector3:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def _box_corners(minimum: Vector3, maximum: Vector3) -> tuple[Vector3, ...]:
    return tuple(
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    )


def _binary_stl_bounds(path: Path) -> tuple[Vector3, Vector3]:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"Collision mesh is not a binary STL: {path}")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + triangle_count * 50:
        raise ValueError(f"Binary STL length/triangle count mismatch: {path}")
    minimum = [float("inf")] * 3
    maximum = [float("-inf")] * 3
    for triangle_index in range(triangle_count):
        offset = 84 + triangle_index * 50 + 12
        coordinates = struct.unpack_from("<9f", data, offset)
        for vertex_index in range(3):
            for axis_index in range(3):
                value = coordinates[vertex_index * 3 + axis_index]
                minimum[axis_index] = min(minimum[axis_index], value)
                maximum[axis_index] = max(maximum[axis_index], value)
    if not all(isfinite(value) for value in minimum + maximum):
        raise ValueError(f"Collision mesh has no finite vertices: {path}")
    return tuple(minimum), tuple(maximum)  # type: ignore[return-value]


def aabb_separation(first: AxisAlignedBox, second: AxisAlignedBox) -> float:
    """Return Euclidean separation between two AABBs, or zero on overlap."""
    squared_gap = 0.0
    for axis_index in range(3):
        gap = max(
            first.minimum[axis_index] - second.maximum[axis_index],
            second.minimum[axis_index] - first.maximum[axis_index],
            0.0,
        )
        squared_gap += gap * gap
    return sqrt(squared_gap)


class CoarseKinematicModel:
    """Evaluate URDF forward transforms and mesh-derived link AABBs."""

    def __init__(self, robot_description: str, package_share: Path) -> None:
        root = ElementTree.fromstring(robot_description)
        self.joints: list[JointKinematics] = []
        self.adjacent_pairs: set[frozenset[str]] = set()
        child_links: set[str] = set()
        all_links = {link.get("name", "") for link in root.findall("link")}
        for joint in root.findall("joint"):
            parent = joint.find("parent")
            child = joint.find("child")
            if parent is None or child is None:
                raise ValueError("URDF joint is missing parent or child")
            parent_link = parent.get("link", "")
            child_link = child.get("link", "")
            origin = joint.find("origin")
            axis = joint.find("axis")
            joint_type = joint.get("type", "")
            self.joints.append(
                JointKinematics(
                    name=joint.get("name", ""),
                    joint_type=joint_type,
                    parent=parent_link,
                    child=child_link,
                    origin=_pose_matrix(
                        _numbers(
                            origin.get("xyz") if origin is not None else None,
                            default=(0.0, 0.0, 0.0),
                        ),
                        _numbers(
                            origin.get("rpy") if origin is not None else None,
                            default=(0.0, 0.0, 0.0),
                        ),
                    ),
                    axis=_numbers(
                        axis.get("xyz") if axis is not None else None,
                        default=(1.0, 0.0, 0.0),
                    ),
                )
            )
            child_links.add(child_link)
            self.adjacent_pairs.add(frozenset((parent_link, child_link)))
        roots = all_links - child_links
        if len(roots) != 1:
            raise ValueError(f"Expected one URDF root link, found {sorted(roots)}")
        self.root_link = next(iter(roots))

        package_share = package_share.resolve()
        geometries: list[CollisionGeometry] = []
        for link in root.findall("link"):
            collision = link.find("collision")
            if collision is None:
                continue
            mesh = collision.find("geometry/mesh")
            if mesh is None:
                continue
            filename = mesh.get("filename", "")
            prefix = "package://dentobot_description/"
            if not filename.startswith(prefix):
                raise ValueError(f"Unsupported collision mesh URI: {filename!r}")
            relative_mesh_path = Path(filename[len(prefix) :])
            if relative_mesh_path.is_absolute() or ".." in relative_mesh_path.parts:
                raise ValueError(f"Collision mesh escapes package: {filename!r}")
            # With colcon --symlink-install the installed mesh path resolves back
            # into the source tree, so validate the URI components before resolve.
            mesh_path = (package_share / relative_mesh_path).resolve()
            minimum, maximum = _binary_stl_bounds(mesh_path)
            scale = _numbers(mesh.get("scale"), default=(1.0, 1.0, 1.0))
            collision_origin = collision.find("origin")
            collision_pose = _pose_matrix(
                _numbers(
                    collision_origin.get("xyz")
                    if collision_origin is not None
                    else None,
                    default=(0.0, 0.0, 0.0),
                ),
                _numbers(
                    collision_origin.get("rpy")
                    if collision_origin is not None
                    else None,
                    default=(0.0, 0.0, 0.0),
                ),
            )
            scaled_corners = tuple(
                (corner[0] * scale[0], corner[1] * scale[1], corner[2] * scale[2])
                for corner in _box_corners(minimum, maximum)
            )
            geometries.append(
                CollisionGeometry(
                    link=link.get("name", ""),
                    corners=tuple(
                        _transform_point(collision_pose, corner)
                        for corner in scaled_corners
                    ),
                )
            )
        self.geometries = tuple(geometries)
        if not self.geometries:
            raise ValueError("URDF contains no mesh collision geometry")

    def link_transforms(self, positions: dict[str, float]) -> dict[str, Matrix4]:
        transforms = {self.root_link: _identity_matrix()}
        pending = list(self.joints)
        while pending:
            progressed = False
            for joint in pending[:]:
                if joint.parent not in transforms:
                    continue
                motion = _axis_motion_matrix(
                    joint.joint_type,
                    joint.axis,
                    positions.get(joint.name, 0.0),
                )
                transforms[joint.child] = _matrix_multiply(
                    transforms[joint.parent],
                    _matrix_multiply(joint.origin, motion),
                )
                pending.remove(joint)
                progressed = True
            if not progressed:
                raise ValueError("URDF joint graph is disconnected or cyclic")
        return transforms

    def evaluate(
        self,
        positions: dict[str, float],
        clearance_m: float,
    ) -> ClearanceEvaluation:
        if not isfinite(clearance_m) or clearance_m < 0.0:
            raise ValueError("AABB clearance must be finite and non-negative")
        transforms = self.link_transforms(positions)
        boxes: list[AxisAlignedBox] = []
        for geometry in self.geometries:
            world_corners = tuple(
                _transform_point(transforms[geometry.link], corner)
                for corner in geometry.corners
            )
            boxes.append(
                AxisAlignedBox(
                    link=geometry.link,
                    minimum=tuple(
                        min(corner[index] for corner in world_corners)
                        for index in range(3)
                    ),
                    maximum=tuple(
                        max(corner[index] for corner in world_corners)
                        for index in range(3)
                    ),
                )
            )

        violations: list[ClearanceViolation] = []
        checked_pair_count = 0
        for first, second in combinations(boxes, 2):
            if frozenset((first.link, second.link)) in self.adjacent_pairs:
                continue
            checked_pair_count += 1
            distance = aabb_separation(first, second)
            if distance < clearance_m:
                violations.append(
                    ClearanceViolation(first.link, second.link, distance)
                )
        violations.sort(key=lambda violation: violation.distance_m)
        return ClearanceEvaluation(
            boxes=tuple(boxes),
            violations=tuple(violations),
            checked_pair_count=checked_pair_count,
            burr_origin_m=_transform_point(
                transforms.get("burr", _identity_matrix()),
                (0.0, 0.0, 0.0),
            ),
        )


def controls_from_urdf(robot_description: str) -> list[JointControl]:
    """Return movable joints in URDF order with bounded manual ranges."""
    root = ElementTree.fromstring(robot_description)
    if root.tag != "robot":
        raise ValueError("robot_description does not contain a URDF robot root")

    controls: list[JointControl] = []
    for joint in root.findall("joint"):
        joint_type = joint.get("type", "")
        if joint_type == "fixed":
            continue
        name = joint.get("name", "").strip()
        if not name:
            raise ValueError("A movable URDF joint has no name")

        if joint_type == "continuous":
            lower_si, upper_si = -pi, pi
        elif joint_type in {"revolute", "prismatic"}:
            limit = joint.find("limit")
            if limit is None:
                raise ValueError(f"Joint {name!r} has no limits")
            lower_si = float(limit.get("lower", "nan"))
            upper_si = float(limit.get("upper", "nan"))
        else:
            raise ValueError(f"Unsupported movable joint type {joint_type!r}")

        if not all(isfinite(value) for value in (lower_si, upper_si)):
            raise ValueError(f"Joint {name!r} has non-finite limits")
        if lower_si > upper_si:
            raise ValueError(f"Joint {name!r} has reversed limits")
        if not lower_si <= 0.0 <= upper_si:
            raise ValueError(f"Joint {name!r} does not admit the neutral zero pose")

        controls.append(
            JointControl(
                name=name,
                joint_type=joint_type,
                lower_si=lower_si,
                upper_si=upper_si,
                display_unit="mm" if joint_type == "prismatic" else "deg",
            )
        )
    if not controls:
        raise ValueError("robot_description contains no movable joints")
    return controls


def main() -> None:
    """Run the ROS publisher and Qt slider window in one process."""
    if not os.environ.get("DISPLAY"):
        raise SystemExit(
            "DISPLAY is not set; manual joint control requires a graphical session"
        )

    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from geometry_msgs.msg import Point
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from PyQt5 import QtCore, QtWidgets
    from visualization_msgs.msg import Marker, MarkerArray

    class ManualJointStateNode(Node):
        def __init__(self) -> None:
            super().__init__("dentobot_manual_joint_state_publisher")
            self.declare_parameter("robot_description", "")
            robot_description = (
                self.get_parameter("robot_description").get_parameter_value().string_value
            )
            if not robot_description.strip():
                raise RuntimeError("robot_description parameter is empty")
            self.controls = controls_from_urdf(robot_description)
            self.positions = {
                control.name: control.clamp_si(0.0) for control in self.controls
            }
            self.declare_parameter("coarse_clearance_mm", 5.0)
            self.clearance_m = (
                self.get_parameter("coarse_clearance_mm")
                .get_parameter_value()
                .double_value
                / 1000.0
            )
            if not isfinite(self.clearance_m) or self.clearance_m < 0.0:
                raise RuntimeError("coarse_clearance_mm must be non-negative")
            self.kinematic_model = CoarseKinematicModel(
                robot_description,
                Path(get_package_share_directory("dentobot_description")),
            )
            self.publisher = self.create_publisher(JointState, "joint_states", 10)
            self.marker_publisher = self.create_publisher(
                MarkerArray,
                "dentobot/coarse_self_collision_boxes",
                10,
            )
            self.latest_evaluation = self.kinematic_model.evaluate(
                self.positions,
                self.clearance_m,
            )
            self.timer = self.create_timer(0.05, self.publish_state)

        def set_display_position(
            self,
            control: JointControl,
            value: float,
        ) -> ClearanceEvaluation:
            self.positions[control.name] = control.clamp_si(
                control.display_to_si(value)
            )
            self.publish_state()
            return self.latest_evaluation

        def publish_state(self) -> None:
            message = JointState()
            message.header.stamp = self.get_clock().now().to_msg()
            message.name = [control.name for control in self.controls]
            message.position = [self.positions[name] for name in message.name]
            self.publisher.publish(message)
            self.latest_evaluation = self.kinematic_model.evaluate(
                self.positions,
                self.clearance_m,
            )
            self._publish_boxes(message.header.stamp)

        def _publish_boxes(self, stamp) -> None:
            delete_all = Marker()
            delete_all.header.frame_id = "base_link"
            delete_all.header.stamp = stamp
            delete_all.action = Marker.DELETEALL
            markers = [delete_all]
            warning_links = {
                link
                for violation in self.latest_evaluation.violations
                for link in (violation.first_link, violation.second_link)
            }
            edge_indices = (
                (0, 1),
                (0, 2),
                (0, 4),
                (1, 3),
                (1, 5),
                (2, 3),
                (2, 6),
                (3, 7),
                (4, 5),
                (4, 6),
                (5, 7),
                (6, 7),
            )
            for marker_id, box in enumerate(self.latest_evaluation.boxes):
                marker = Marker()
                marker.header.frame_id = "base_link"
                marker.header.stamp = stamp
                marker.ns = "dentobot_coarse_link_aabbs"
                marker.id = marker_id
                marker.type = Marker.LINE_LIST
                marker.action = Marker.ADD
                marker.pose.orientation.w = 1.0
                marker.scale.x = 0.001
                if box.link in warning_links:
                    marker.color.r = 1.0
                    marker.color.g = 0.15
                    marker.color.b = 0.05
                else:
                    marker.color.r = 0.15
                    marker.color.g = 0.95
                    marker.color.b = 0.55
                marker.color.a = 1.0
                corners = _box_corners(box.minimum, box.maximum)
                for first_index, second_index in edge_indices:
                    for corner_index in (first_index, second_index):
                        point = Point()
                        point.x, point.y, point.z = corners[corner_index]
                        marker.points.append(point)
                markers.append(marker)
            self.marker_publisher.publish(MarkerArray(markers=markers))

    class ManualJointWindow(QtWidgets.QWidget):
        slider_steps = 2000

        def __init__(self, node: ManualJointStateNode) -> None:
            super().__init__()
            self.node = node
            self.rows: list[
                tuple[JointControl, QtWidgets.QSlider, QtWidgets.QDoubleSpinBox]
            ] = []
            self.setWindowTitle("DENTOBOT Manual Joint Control — Simulation Only")
            self.setMinimumWidth(760)

            outer = QtWidgets.QVBoxLayout(self)
            warning = QtWidgets.QLabel(
                "SIMULATION ONLY — values come from an uncalibrated CAD export. "
                "No controller or hardware command is connected."
            )
            warning.setWordWrap(True)
            warning.setStyleSheet(
                "font-weight: bold; color: #8b1a1a; background: #ffe8e8; "
                "padding: 8px; border: 1px solid #c65c5c;"
            )
            outer.addWidget(warning)

            grid = QtWidgets.QGridLayout()
            for column, title in enumerate(
                ("Joint", "Type", "Position", "Value", "Unit")
            ):
                label = QtWidgets.QLabel(title)
                label.setStyleSheet("font-weight: bold;")
                grid.addWidget(label, 0, column)

            for row, control in enumerate(node.controls, start=1):
                name_label = QtWidgets.QLabel(control.name)
                type_label = QtWidgets.QLabel(control.joint_type)
                slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
                slider.setRange(0, self.slider_steps)
                spin = QtWidgets.QDoubleSpinBox()
                spin.setDecimals(2)
                spin.setRange(control.lower_display, control.upper_display)
                spin.setSingleStep(0.5 if control.display_unit == "mm" else 1.0)
                unit_label = QtWidgets.QLabel(control.display_unit)

                neutral_display = control.si_to_display(control.clamp_si(0.0))
                slider.setValue(self._display_to_slider(control, neutral_display))
                spin.setValue(neutral_display)
                slider.valueChanged.connect(
                    lambda value, c=control, s=spin: self._slider_changed(c, s, value)
                )
                spin.valueChanged.connect(
                    lambda value, c=control, s=slider: self._spin_changed(c, s, value)
                )

                grid.addWidget(name_label, row, 0)
                grid.addWidget(type_label, row, 1)
                grid.addWidget(slider, row, 2)
                grid.addWidget(spin, row, 3)
                grid.addWidget(unit_label, row, 4)
                self.rows.append((control, slider, spin))

            outer.addLayout(grid)

            self.clearance_status = QtWidgets.QLabel()
            self.clearance_status.setWordWrap(True)
            outer.addWidget(self.clearance_status)
            self.workspace_status = QtWidgets.QLabel()
            self.workspace_status.setWordWrap(True)
            outer.addWidget(self.workspace_status)

            reset = QtWidgets.QPushButton("Reset all joints to zero")
            reset.clicked.connect(self._reset_zero)
            outer.addWidget(reset)
            self._update_draft_status()

        def _display_to_slider(self, control: JointControl, value: float) -> int:
            span = control.upper_display - control.lower_display
            if span <= 0.0:
                return 0
            fraction = (value - control.lower_display) / span
            return round(fraction * self.slider_steps)

        def _slider_to_display(self, control: JointControl, value: int) -> float:
            fraction = value / self.slider_steps
            return control.lower_display + fraction * (
                control.upper_display - control.lower_display
            )

        def _slider_changed(
            self,
            control: JointControl,
            spin: QtWidgets.QDoubleSpinBox,
            value: int,
        ) -> None:
            display_value = self._slider_to_display(control, value)
            blocker = QtCore.QSignalBlocker(spin)
            spin.setValue(display_value)
            del blocker
            self.node.set_display_position(control, display_value)
            self._update_draft_status()

        def _spin_changed(
            self,
            control: JointControl,
            slider: QtWidgets.QSlider,
            value: float,
        ) -> None:
            blocker = QtCore.QSignalBlocker(slider)
            slider.setValue(self._display_to_slider(control, value))
            del blocker
            self.node.set_display_position(control, value)
            self._update_draft_status()

        def _reset_zero(self) -> None:
            for control, slider, spin in self.rows:
                neutral_display = control.si_to_display(control.clamp_si(0.0))
                slider_blocker = QtCore.QSignalBlocker(slider)
                spin_blocker = QtCore.QSignalBlocker(spin)
                slider.setValue(self._display_to_slider(control, neutral_display))
                spin.setValue(neutral_display)
                del slider_blocker, spin_blocker
                self.node.set_display_position(control, neutral_display)
            self._update_draft_status()

        def _update_draft_status(self) -> None:
            evaluation = self.node.latest_evaluation
            clearance_mm = self.node.clearance_m * 1000.0
            if evaluation.violations:
                pair_text = "; ".join(
                    f"{violation.first_link} ↔ {violation.second_link} "
                    f"({violation.distance_m * 1000.0:.1f} mm)"
                    for violation in evaluation.violations[:4]
                )
                extra = len(evaluation.violations) - 4
                if extra > 0:
                    pair_text += f"; +{extra} more"
                self.clearance_status.setText(
                    f"DRAFT AABB WARNING — {len(evaluation.violations)} of "
                    f"{evaluation.checked_pair_count} non-adjacent pairs are below "
                    f"the {clearance_mm:.1f} mm box-clearance margin: {pair_text}"
                )
                self.clearance_status.setStyleSheet(
                    "font-weight: bold; color: #8b1a1a; background: #ffe8e8; "
                    "padding: 7px; border: 1px solid #c65c5c;"
                )
            else:
                self.clearance_status.setText(
                    f"DRAFT AABB CLEAR — all {evaluation.checked_pair_count} "
                    f"non-adjacent link-box pairs are at least {clearance_mm:.1f} mm "
                    "apart. Adjacent joint pairs are intentionally ignored."
                )
                self.clearance_status.setStyleSheet(
                    "font-weight: bold; color: #175b32; background: #e7f7ed; "
                    "padding: 7px; border: 1px solid #55a675;"
                )
            burr_mm = tuple(value * 1000.0 for value in evaluation.burr_origin_m)
            self.workspace_status.setText(
                "CAD burr-link origin in base_link (not a calibrated TCP): "
                f"X {burr_mm[0]:.1f} mm, Y {burr_mm[1]:.1f} mm, "
                f"Z {burr_mm[2]:.1f} mm. RViz boxes: green=clear, red=warning."
            )

    rclpy.init(args=sys.argv)
    node = ManualJointStateNode()
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        [sys.argv[0]]
    )
    window = ManualJointWindow(node)
    spin_timer = QtCore.QTimer()
    spin_timer.timeout.connect(lambda: rclpy.spin_once(node, timeout_sec=0.0))
    spin_timer.start(10)
    signal.signal(signal.SIGINT, lambda *_: application.quit())
    window.show()
    node.publish_state()
    try:
        application.exec_()
    finally:
        spin_timer.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
