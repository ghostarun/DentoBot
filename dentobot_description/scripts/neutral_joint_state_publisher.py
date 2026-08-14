#!/usr/bin/env python3
"""Publish a neutral visualization pose without exposing motion commands."""

from math import isfinite
from typing import Dict, List
from xml.etree import ElementTree

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState


class NeutralJointStatePublisher(Node):
    """Publish deterministic neutral states for all movable URDF joints."""

    def __init__(self) -> None:
        super().__init__("dentobot_neutral_joint_state_publisher")
        self.declare_parameter("robot_description", "")
        self.declare_parameter("publish_rate_hz", 10.0)

        robot_description = (
            self.get_parameter("robot_description").get_parameter_value().string_value
        )
        publish_rate_hz = (
            self.get_parameter("publish_rate_hz").get_parameter_value().double_value
        )
        if not robot_description.strip():
            raise ValueError("robot_description must contain the DENTOBOT URDF")
        if not isfinite(publish_rate_hz) or publish_rate_hz <= 0.0:
            raise ValueError("publish_rate_hz must be finite and greater than zero")

        self._joint_names, self._joint_positions = self._neutral_positions(
            robot_description
        )
        self._publisher = self.create_publisher(JointState, "joint_states", 10)
        self._timer = self.create_timer(1.0 / publish_rate_hz, self._publish)
        self.get_logger().info(
            "Publishing simulated neutral joint states for %d joints; this node "
            "has no robot command or hardware interface." % len(self._joint_names)
        )

    @staticmethod
    def _neutral_positions(robot_description: str) -> tuple[List[str], List[float]]:
        root = ElementTree.fromstring(robot_description)
        names: List[str] = []
        positions: List[float] = []
        seen: Dict[str, None] = {}

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

            position = 0.0
            limit = joint.find("limit")
            if joint_type in {"revolute", "prismatic"}:
                if limit is None:
                    raise ValueError(f"joint {name} is missing its limits")
                lower = float(limit.get("lower", "nan"))
                upper = float(limit.get("upper", "nan"))
                if not isfinite(lower) or not isfinite(upper) or lower > upper:
                    raise ValueError(f"joint {name} has invalid limits")
                position = min(max(position, lower), upper)

            names.append(name)
            positions.append(position)

        if not names:
            raise ValueError("robot_description contains no movable joints")
        return names, positions

    def _publish(self) -> None:
        message = JointState()
        message.header.stamp = self.get_clock().now().to_msg()
        message.name = self._joint_names
        message.position = self._joint_positions
        self._publisher.publish(message)


def main(args: List[str] | None = None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = NeutralJointStatePublisher()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            try:
                node.destroy_node()
            except KeyboardInterrupt:
                # A supervising launch process may forward a second SIGINT
                # while the first one is already tearing down the ROS context.
                pass
        if rclpy.ok():
            try:
                rclpy.shutdown()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
