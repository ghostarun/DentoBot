#!/usr/bin/env python3
"""Probe every DENTOBOT joint against a live external-state TF launch."""

from math import acos, sqrt
import time

import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import JointState
from tf2_ros import Buffer, TransformException, TransformListener


JOINTS = (
    ("link-1_Revolute-1", "revolute", "link-2", 0.35),
    ("link-2_Slider-2", "prismatic", "link-3", 0.02),
    ("link-3_Revolute-3", "revolute", "link-4", 0.35),
    ("link-4_Slider-4", "prismatic", "link-5", 0.02),
    ("link-5_Revolute-5", "revolute", "pneumatic_spindle-Copy", 0.35),
    (
        "pneumatic_spindle-Copy_Revolute-6",
        "continuous",
        "burr",
        0.35,
    ),
)
LINKS = (
    "base_link",
    "link-1",
    "link-2",
    "link-3",
    "link-4",
    "link-5",
    "pneumatic_spindle-Copy",
    "burr",
)


def _translation_distance(first, second) -> float:
    return sqrt(
        (first.x - second.x) ** 2
        + (first.y - second.y) ** 2
        + (first.z - second.z) ** 2
    )


def _orientation_distance(first, second) -> float:
    dot = abs(
        first.x * second.x
        + first.y * second.y
        + first.z * second.z
        + first.w * second.w
    )
    return 2.0 * acos(min(1.0, max(-1.0, dot)))


def _pose_delta(first, second) -> tuple[float, float]:
    return (
        _translation_distance(first.translation, second.translation),
        _orientation_distance(first.rotation, second.rotation),
    )


class KinematicsProbe(Node):
    """Publish bounded test states and inspect robot_state_publisher TF."""

    def __init__(self) -> None:
        super().__init__("dentobot_runtime_kinematics_probe")
        self.publisher = self.create_publisher(JointState, "joint_states", 10)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.positions = [0.0] * len(JOINTS)

    def publish_for(self, duration_seconds: float = 0.4) -> int:
        deadline = time.monotonic() + duration_seconds
        first_stamp_ns = 0
        while time.monotonic() < deadline:
            message = JointState()
            message.header.stamp = self.get_clock().now().to_msg()
            if first_stamp_ns == 0:
                first_stamp_ns = (
                    message.header.stamp.sec * 1_000_000_000
                    + message.header.stamp.nanosec
                )
            message.name = [joint[0] for joint in JOINTS]
            message.position = list(self.positions)
            self.publisher.publish(message)
            rclpy.spin_once(self, timeout_sec=0.02)
        return first_stamp_ns

    def wait_for_subscriber(self) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.publisher.get_subscription_count() >= 1:
                return
            rclpy.spin_once(self, timeout_sec=0.05)
        raise RuntimeError("robot_state_publisher did not subscribe to joint_states")

    def snapshot(self, minimum_dynamic_stamp_ns: int = 0) -> dict[str, object]:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                snapshot = {}
                for link in LINKS:
                    stamped = self.buffer.lookup_transform(
                        "base_link",
                        link,
                        Time(),
                        timeout=Duration(seconds=0.2),
                    )
                    stamp_ns = (
                        stamped.header.stamp.sec * 1_000_000_000
                        + stamped.header.stamp.nanosec
                    )
                    if link not in {"base_link", "link-1"} and (
                        stamp_ns < minimum_dynamic_stamp_ns
                    ):
                        raise TransformException(
                            f"{link} TF is older than the requested joint state"
                        )
                    snapshot[link] = stamped.transform
                return snapshot
            except TransformException:
                self.publish_for(0.1)
        raise RuntimeError("The complete base_link-to-burr TF tree was unavailable")


def main() -> None:
    rclpy.init()
    probe = KinematicsProbe()
    try:
        probe.wait_for_subscriber()

        for index, (joint_name, joint_type, child_link, test_value) in enumerate(JOINTS):
            probe.positions = [0.0] * len(JOINTS)
            neutral_stamp_ns = probe.publish_for(0.6)
            neutral = probe.snapshot(neutral_stamp_ns)

            probe.positions[index] = test_value
            moved_stamp_ns = probe.publish_for(0.6)
            moved = probe.snapshot(moved_stamp_ns)

            child_index = LINKS.index(child_link)
            for upstream_link in LINKS[:child_index]:
                translation_delta, angle_delta = _pose_delta(
                    neutral[upstream_link], moved[upstream_link]
                )
                if translation_delta > 1e-7 or angle_delta > 1e-7:
                    raise AssertionError(
                        f"{joint_name} unexpectedly moved upstream frame "
                        f"{upstream_link}: {translation_delta=} {angle_delta=}"
                    )

            child_translation, child_angle = _pose_delta(
                neutral[child_link], moved[child_link]
            )
            burr_translation, burr_angle = _pose_delta(neutral["burr"], moved["burr"])
            if joint_type == "prismatic":
                if child_translation < 0.019 or child_angle > 1e-6:
                    raise AssertionError(
                        f"{joint_name} did not produce the expected translation-only "
                        f"child motion: {child_translation=} {child_angle=}"
                    )
                if joint_name == "link-4_Slider-4":
                    neutral_translation = neutral[child_link].translation
                    moved_translation = moved[child_link].translation
                    x_displacement = moved_translation.x - neutral_translation.x
                    if x_displacement > -0.019:
                        raise AssertionError(
                            "link-4_Slider-4 positive travel did not move in the "
                            f"selected negative base-X direction: {x_displacement=}"
                        )
            elif child_angle < 0.34 or child_translation > 1e-6:
                raise AssertionError(
                    f"{joint_name} did not produce the expected rotation-only child "
                    f"motion: {child_translation=} {child_angle=}"
                )
            if burr_translation < 1e-6 and burr_angle < 0.34:
                raise AssertionError(
                    f"{joint_name} did not move the downstream burr frame"
                )
            print(
                "PASS",
                joint_name,
                f"child={child_link}",
                f"child_translation_m={child_translation:.6f}",
                f"child_angle_rad={child_angle:.6f}",
                f"burr_translation_m={burr_translation:.6f}",
                f"burr_angle_rad={burr_angle:.6f}",
            )

        probe.positions = [0.0] * len(JOINTS)
        probe.publish_for()
        print("DENTOBOT_RUNTIME_KINEMATICS_PASS")
    finally:
        probe.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
