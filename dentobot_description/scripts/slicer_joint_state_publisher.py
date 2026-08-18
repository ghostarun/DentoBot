#!/usr/bin/env python3
"""Publish visualization joint states from Slicer Motion Control sliders.

This node is simulation-only. It has no hardware interface, controller,
or robot command path. It republishes clamped Slicer slider values as
``sensor_msgs/JointState`` so ``robot_state_publisher`` can update TF.
"""

from __future__ import annotations

from math import isfinite
from typing import List, Sequence, Tuple
from xml.etree import ElementTree

JointSpec = Tuple[str, float, float]


def movable_joints_from_urdf(robot_description: str) -> List[JointSpec]:
    """Return (name, lower, upper) for every movable URDF joint.

    Continuous joints use infinite limits so Slicer values are not clamped.
    """
    root = ElementTree.fromstring(robot_description)
    joints: List[JointSpec] = []
    seen: dict[str, None] = {}

    for joint in root.findall("joint"):
        joint_type = joint.get("type", "")
        if joint_type in {"fixed", "floating", "planar"}:
            continue

        name = joint.get("name", "").strip()
        if not name:
            raise ValueError("every movable joint must have a name")
        if name in seen:
            raise ValueError(f"duplicate movable joint name: {name}")
        seen[name] = None

        lower = float("-inf")
        upper = float("inf")
        limit = joint.find("limit")
        if joint_type in {"revolute", "prismatic"}:
            if limit is None:
                raise ValueError(f"joint {name} is missing its limits")
            lower = float(limit.get("lower", "nan"))
            upper = float(limit.get("upper", "nan"))
            if not isfinite(lower) or not isfinite(upper) or lower > upper:
                raise ValueError(f"joint {name} has invalid limits")

        joints.append((name, lower, upper))

    if not joints:
        raise ValueError("robot_description contains no movable joints")
    return joints


def clamp_joint_positions(
    joints: Sequence[JointSpec],
    values: Sequence[float],
) -> List[float]:
    """Clamp a Slicer command vector to URDF limits, preserving order."""
    if len(values) != len(joints):
        raise ValueError(
            f"expected {len(joints)} joint positions, received {len(values)}"
        )
    clamped: List[float] = []
    for (name, lower, upper), value in zip(joints, values):
        if not isfinite(value):
            raise ValueError(f"joint {name} received a non-finite command")
        if isfinite(lower):
            value = max(value, lower)
        if isfinite(upper):
            value = min(value, upper)
        clamped.append(value)
    return clamped


def main(args: List[str] | None = None) -> None:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64MultiArray

    class SlicerJointStatePublisher(Node):
        """Hold last Slicer command and publish JointState at a fixed rate."""

        def __init__(self) -> None:
            super().__init__("dentobot_slicer_joint_state_publisher")
            self.declare_parameter("robot_description", "")
            self.declare_parameter("publish_rate_hz", 10.0)
            self.declare_parameter(
                "command_topic",
                "dentobot/slicer_joint_positions",
            )

            robot_description = (
                self.get_parameter("robot_description")
                .get_parameter_value()
                .string_value
            )
            publish_rate_hz = (
                self.get_parameter("publish_rate_hz")
                .get_parameter_value()
                .double_value
            )
            command_topic = (
                self.get_parameter("command_topic")
                .get_parameter_value()
                .string_value
                .strip()
            )
            if not robot_description.strip():
                raise ValueError("robot_description must contain the DENTOBOT URDF")
            if not isfinite(publish_rate_hz) or publish_rate_hz <= 0.0:
                raise ValueError("publish_rate_hz must be finite and greater than zero")
            if not command_topic:
                raise ValueError("command_topic must be a non-empty topic name")

            self._joints = movable_joints_from_urdf(robot_description)
            self._positions = [
                0.0
                if not isfinite(lower) or not isfinite(upper)
                else min(max(0.0, lower), upper)
                for _name, lower, upper in self._joints
            ]
            self._publisher = self.create_publisher(JointState, "joint_states", 10)
            self.create_subscription(
                Float64MultiArray,
                command_topic,
                self._on_command,
                10,
            )
            self.create_timer(1.0 / publish_rate_hz, self._publish)
            self.get_logger().info(
                "Publishing simulated joint states for %d joints from Slicer "
                "topic %s; this node has no robot command or hardware interface."
                % (len(self._joints), command_topic)
            )

        def _on_command(self, message: Float64MultiArray) -> None:
            try:
                self._positions = clamp_joint_positions(self._joints, message.data)
            except ValueError as exc:
                self.get_logger().warning(str(exc))

        def _publish(self) -> None:
            message = JointState()
            message.header.stamp = self.get_clock().now().to_msg()
            message.name = [name for name, _lower, _upper in self._joints]
            message.position = list(self._positions)
            self._publisher.publish(message)

    rclpy.init(args=args)
    node = None
    try:
        node = SlicerJointStatePublisher()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            try:
                node.destroy_node()
            except KeyboardInterrupt:
                pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
