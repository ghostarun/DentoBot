#!/usr/bin/env python3
"""Live ROS smoke test for DENTOBOT's simulation-only phased task guard."""

from __future__ import annotations

import json
import math
import time

import rclpy
from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


UNDER_CLEARANCE_JOINTS = [0.1, 0.08, 0.2, 0.075, 0.1, 0.0]
TASK = "phase-smoke-task-v1"
TARGET_ID = "dentobot_phase_smoke_target"
FORBIDDEN_ID = "dentobot_phase_smoke_forbidden"


class PhaseSmokeNode(Node):
    def __init__(self) -> None:
        super().__init__("dentobot_phase_guard_smoke")
        self.joint_state = None
        self.status = None
        self.status_generation = 0
        self.create_subscription(
            JointState, "/joint_states", self._on_joint_state, qos_profile_sensor_data
        )
        self.create_subscription(
            String, "/dentobot/task_joint_status", self._on_status, 10
        )
        self.config_publisher = self.create_publisher(
            String, "/dentobot/task_guard_config", 10
        )
        self.command_publisher = self.create_publisher(
            String, "/dentobot/task_joint_command", 10
        )
        self.collision_publisher = self.create_publisher(
            CollisionObject, "/collision_object", 10
        )
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

    def _on_joint_state(self, message: JointState) -> None:
        self.joint_state = message

    def _on_status(self, message: String) -> None:
        self.status = json.loads(message.data)
        self.status_generation += 1


def spin_until(node: Node, predicate, timeout_sec: float):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        result = predicate()
        if result is not None and result is not False:
            return result
    return None


def quaternion_rotate(q, vector):
    x, y, z, w = q.x, q.y, q.z, q.w
    q_vector = (x, y, z)
    cross_1 = (
        q_vector[1] * vector[2] - q_vector[2] * vector[1],
        q_vector[2] * vector[0] - q_vector[0] * vector[2],
        q_vector[0] * vector[1] - q_vector[1] * vector[0],
    )
    cross_2 = (
        q_vector[1] * cross_1[2] - q_vector[2] * cross_1[1],
        q_vector[2] * cross_1[0] - q_vector[0] * cross_1[2],
        q_vector[0] * cross_1[1] - q_vector[1] * cross_1[0],
    )
    return tuple(
        vector[index] + 2.0 * (w * cross_1[index] + cross_2[index])
        for index in range(3)
    )


def publish_sphere(node: PhaseSmokeNode, object_id: str, centre, *, remove=False):
    message = CollisionObject()
    message.header.frame_id = "base_link"
    message.id = object_id
    message.operation = CollisionObject.REMOVE if remove else CollisionObject.ADD
    if not remove:
        sphere = SolidPrimitive()
        sphere.type = SolidPrimitive.SPHERE
        sphere.dimensions = [0.001]
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = centre
        pose.orientation.w = 1.0
        message.primitives = [sphere]
        message.primitive_poses = [pose]
    for _ in range(5):
        node.collision_publisher.publish(message)
        rclpy.spin_once(node, timeout_sec=0.1)


def config_payload(entry, target):
    return {
        "schema": "dentobot.task_guard_config.v1",
        "mode": "simulation_only",
        "task_fingerprint": TASK,
        "target_object_id": TARGET_ID,
        "allowed_robot_link": "burr",
        "tool_tip_frame": "dentobot_drill_tip_provisional",
        "entry_base_m": list(entry),
        "target_base_m": list(target),
        "corridor_radius_m": 0.00075,
        "approach_standoff_m": 0.005,
    }


def task_command(
    node: PhaseSmokeNode,
    *,
    config,
    joints,
    phase,
    sequence,
    fingerprint=TASK,
    timeout_sec=5.0,
):
    config_message = String()
    config_message.data = json.dumps(config, sort_keys=True, separators=(",", ":"))
    command_payload = {
        "schema": "dentobot.task_joint_command.v1",
        "mode": "simulation_only",
        "task_fingerprint": fingerprint,
        "phase": phase,
        "sequence": sequence,
        "joint_positions": list(joints),
    }
    command_message = String()
    command_message.data = json.dumps(
        command_payload, sort_keys=True, separators=(",", ":")
    )
    generation = node.status_generation

    def matching():
        status = node.status
        if node.status_generation <= generation or not status:
            return None
        if (
            status.get("task_fingerprint") == fingerprint
            and status.get("phase") == phase
            and int(status.get("sequence", -2)) == sequence
        ):
            return status
        return None

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        node.config_publisher.publish(config_message)
        rclpy.spin_once(node, timeout_sec=0.1)
        node.command_publisher.publish(command_message)
        status = spin_until(node, matching, 0.5)
        if status is not None:
            return status
    raise RuntimeError(f"phase guard did not answer {phase} sequence {sequence}")


def require(status, accepted, label, reason_contains=""):
    if bool(status.get("accepted")) is not bool(accepted):
        raise RuntimeError(f"{label}: unexpected status {status}")
    if reason_contains and reason_contains.lower() not in str(status.get("reason", "")).lower():
        raise RuntimeError(f"{label}: missing reason {reason_contains!r}: {status}")


def main() -> None:
    rclpy.init()
    node = PhaseSmokeNode()
    report = {}
    try:
        if spin_until(node, lambda: node.joint_state, 10.0) is None:
            raise RuntimeError("/joint_states unavailable")
        safe_joints = list(node.joint_state.position)
        transform = spin_until(
            node,
            lambda: node.tf_buffer.lookup_transform(
                "base_link", "dentobot_drill_tip_provisional", rclpy.time.Time()
            )
            if node.tf_buffer.can_transform(
                "base_link", "dentobot_drill_tip_provisional", rclpy.time.Time()
            )
            else None,
            10.0,
        )
        if transform is None:
            raise RuntimeError("provisional drill-tip TF unavailable")
        tip = transform.transform.translation
        direction = quaternion_rotate(transform.transform.rotation, (0.0, 0.0, 1.0))
        direction_norm = math.sqrt(sum(value * value for value in direction))
        direction = tuple(value / direction_norm for value in direction)
        entry = (tip.x, tip.y, tip.z)
        target = tuple(entry[index] + 0.010 * direction[index] for index in range(3))
        contact_centre = tuple(
            entry[index] - 0.0004 * direction[index] for index in range(3)
        )
        publish_sphere(node, TARGET_ID, contact_centre)
        config = config_payload(entry, target)

        wrong_task = task_command(
            node,
            config=config,
            joints=safe_joints,
            phase="drilling",
            sequence=0,
            fingerprint="wrong-task",
        )
        require(wrong_task, False, "wrong task", "fingerprint")
        report["wrong_task_rejected"] = True

        strict_contact = task_command(
            node, config=config, joints=safe_joints, phase="approach", sequence=0
        )
        require(strict_contact, False, "strict target contact", "collision")
        report["strict_target_contact_rejected"] = True

        accepted_contact = task_command(
            node, config=config, joints=safe_joints, phase="drilling", sequence=0
        )
        require(accepted_contact, True, "selected burr-target contact")
        pair = {accepted_contact.get("first_body"), accepted_contact.get("second_body")}
        if pair != {"burr", TARGET_ID}:
            raise RuntimeError(f"unexpected accepted contact pair: {pair}")
        if not accepted_contact.get("corridor_ok"):
            raise RuntimeError("in-corridor target contact did not report corridor_ok")
        report["selected_burr_target_contact_accepted"] = True

        publish_sphere(node, FORBIDDEN_ID, contact_centre)
        forbidden = task_command(
            node, config=config, joints=safe_joints, phase="drilling", sequence=0
        )
        require(forbidden, False, "non-target collision", "disallowed collision")
        report["non_target_contact_rejected"] = True
        publish_sphere(node, FORBIDDEN_ID, contact_centre, remove=True)

        lateral_entry = (entry[0] + 0.010, entry[1], entry[2])
        lateral_target = (
            lateral_entry[0], lateral_entry[1] + 0.010, lateral_entry[2]
        )
        lateral = task_command(
            node,
            config=config_payload(lateral_entry, lateral_target),
            joints=safe_joints,
            phase="drilling",
            sequence=0,
        )
        require(lateral, False, "corridor escape", "corridor")
        report["lateral_corridor_escape_rejected"] = True

        overshoot_entry = tuple(entry[index] - 0.010 * direction[index] for index in range(3))
        overshoot_target = tuple(entry[index] - 0.005 * direction[index] for index in range(3))
        overshoot = task_command(
            node,
            config=config_payload(overshoot_entry, overshoot_target),
            joints=safe_joints,
            phase="drilling",
            sequence=0,
        )
        require(overshoot, False, "overshoot", "overshot")
        report["overshoot_rejected"] = True

        bounds = task_command(
            node,
            config=config,
            joints=[99.0] * 6,
            phase="drilling",
            sequence=0,
        )
        require(bounds, False, "joint bounds", "bounds")
        report["joint_bounds_rejected"] = True

        publish_sphere(node, TARGET_ID, contact_centre, remove=True)
        self_collision = task_command(
            node,
            config=config,
            joints=UNDER_CLEARANCE_JOINTS,
            phase="approach",
            sequence=0,
        )
        require(self_collision, False, "self clearance")
        if not ({self_collision.get("first_body"), self_collision.get("second_body")} & {"link-1", "link-3"}):
            raise RuntimeError(f"self-collision pair missing: {self_collision}")
        report["self_collision_rejected"] = True

        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        try:
            publish_sphere(node, TARGET_ID, (0.0, 0.0, 0.0), remove=True)
            publish_sphere(node, FORBIDDEN_ID, (0.0, 0.0, 0.0), remove=True)
        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
