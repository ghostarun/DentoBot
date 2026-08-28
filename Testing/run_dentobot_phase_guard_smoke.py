#!/usr/bin/env python3
"""Live ROS smoke test for DENTOBOT's simulation-only phased task guard."""

from __future__ import annotations

import json
import math
import time

import rclpy
from geometry_msgs.msg import Pose
from moveit_msgs.msg import CollisionObject, PlanningSceneComponents
from moveit_msgs.srv import GetPlanningScene
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


UNDER_CLEARANCE_JOINTS = [0.1, 0.08, 0.2, 0.075, 0.1, 0.0]
TASK = "phase-smoke-task-v1"
TARGET_ID = "[Mask] DENTOBOT phase-smoke target — FDI 14"
FORBIDDEN_ID = "dentobot_phase_smoke_forbidden"
ROBOT_OBSTACLE_ID = "dentobot_phase_smoke_non_tool_obstacle"
GUIDE_ID = "[Step 5C] DENTOBOT phase-smoke guide — final"


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
        self.planning_scene_client = self.create_client(
            GetPlanningScene, "/get_planning_scene"
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


def planning_scene_world_ids(node: PhaseSmokeNode):
    if not node.planning_scene_client.wait_for_service(timeout_sec=2.0):
        return None
    request = GetPlanningScene.Request()
    request.components.components = PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
    future = node.planning_scene_client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=2.0)
    response = future.result()
    if response is None:
        return None
    return {item.id for item in response.scene.world.collision_objects}


def publish_sphere(
    node: PhaseSmokeNode,
    object_id: str,
    centre,
    *,
    radius_m=0.001,
    remove=False,
):
    message = CollisionObject()
    message.header.frame_id = "base_link"
    message.id = object_id
    message.operation = CollisionObject.REMOVE if remove else CollisionObject.ADD
    if not remove:
        sphere = SolidPrimitive()
        sphere.type = SolidPrimitive.SPHERE
        sphere.dimensions = [float(radius_m)]
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = centre
        pose.orientation.w = 1.0
        message.primitives = [sphere]
        message.primitive_poses = [pose]
    if spin_until(
        node,
        lambda: node.collision_publisher.get_subscription_count() > 0,
        5.0,
    ) is None:
        raise RuntimeError("MoveIt collision-object subscriber is unavailable")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        node.collision_publisher.publish(message)
        rclpy.spin_once(node, timeout_sec=0.1)
        world_ids = planning_scene_world_ids(node)
        if world_ids is not None and ((object_id not in world_ids) if remove else (object_id in world_ids)):
            return
    action = "remove" if remove else "add"
    raise RuntimeError(f"planning scene did not {action} {object_id}")


def config_payload(entry, target, guard_session_id):
    return {
        "schema": "dentobot.task_guard_config.v2",
        "mode": "simulation_only",
        "task_fingerprint": TASK,
        "guard_session_id": guard_session_id,
        "target_object_id": TARGET_ID,
        "allowed_robot_link": "burr",
        "clearance_exempt_object_ids": [GUIDE_ID],
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
    publish_config=True,
    timeout_sec=5.0,
):
    config_message = String()
    config_message.data = json.dumps(config, sort_keys=True, separators=(",", ":"))
    command_payload = {
        "schema": "dentobot.task_joint_command.v2",
        "mode": "simulation_only",
        "task_fingerprint": fingerprint,
        "guard_session_id": config["guard_session_id"],
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
            and status.get("guard_session_id") == config["guard_session_id"]
            and status.get("phase") == phase
            and int(status.get("sequence", -2)) == sequence
        ):
            return status
        return None

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if publish_config:
            node.config_publisher.publish(config_message)
            rclpy.spin_once(node, timeout_sec=0.1)
        node.command_publisher.publish(command_message)
        status = spin_until(node, matching, 0.5)
        if status is not None:
            if (
                publish_config
                and (
                    "No valid simulation task-guard configuration"
                    in str(status.get("reason", ""))
                    or "guard session does not match"
                    in str(status.get("reason", ""))
                )
            ):
                generation = node.status_generation
                continue
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
        publish_sphere(node, GUIDE_ID, (tip.x + 1.0, tip.y, tip.z))
        config = config_payload(entry, target, "phase-smoke-main")

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
        if not accepted_contact.get("exploratory_tool_contact_suppressed"):
            raise RuntimeError(
                "accepted target contact was not reported as exploratory suppression"
            )
        report["selected_burr_target_contact_accepted"] = True
        report["selected_burr_target_contact_reported"] = True

        continued_contact = task_command(
            node,
            config=config,
            joints=safe_joints,
            phase="drilling",
            sequence=1,
            publish_config=False,
        )
        require(continued_contact, True, "continued guard session")
        report["sequence_continues_without_config_reset"] = True

        duplicate = task_command(
            node,
            config=config,
            joints=safe_joints,
            phase="drilling",
            sequence=1,
            publish_config=False,
        )
        require(duplicate, False, "duplicate sequence", "stale or duplicated")
        report["duplicate_sequence_rejected_without_config_reset"] = True

        publish_sphere(node, FORBIDDEN_ID, contact_centre)
        unconfigured = task_command(
            node,
            config=config_payload(entry, target, "phase-smoke-unconfigured"),
            joints=safe_joints,
            phase="drilling",
            sequence=0,
        )
        require(
            unconfigured,
            False,
            "unconfigured task-object collision",
            "unconfigured collision",
        )
        report["unconfigured_tool_contact_rejected"] = True

        exploratory_config = config_payload(
            entry, target, "phase-smoke-exploratory-tool"
        )
        exploratory_config["clearance_exempt_object_ids"].append(FORBIDDEN_ID)
        exploratory = task_command(
            node,
            config=exploratory_config,
            joints=safe_joints,
            phase="drilling",
            sequence=0,
        )
        require(exploratory, True, "configured exploratory tool contact")
        if not exploratory.get("exploratory_tool_contact_suppressed"):
            raise RuntimeError(
                f"configured tool contact was not reported: {exploratory}"
            )
        if int(exploratory.get("suppressed_tool_contact_sample_count", 0)) < 1:
            raise RuntimeError(
                f"configured tool contact did not count suppressed samples: {exploratory}"
            )
        report["configured_tool_contact_suppressed_and_reported"] = True
        publish_sphere(node, FORBIDDEN_ID, contact_centre, remove=True)

        link_transform = spin_until(
            node,
            lambda: node.tf_buffer.lookup_transform(
                "base_link", "link-3", rclpy.time.Time()
            )
            if node.tf_buffer.can_transform(
                "base_link", "link-3", rclpy.time.Time()
            )
            else None,
            5.0,
        )
        if link_transform is None:
            raise RuntimeError("link-3 TF unavailable for non-tool collision test")
        link_origin = link_transform.transform.translation
        publish_sphere(
            node,
            ROBOT_OBSTACLE_ID,
            (link_origin.x, link_origin.y, link_origin.z),
            radius_m=0.01,
        )
        non_tool = task_command(
            node,
            config=config_payload(entry, target, "phase-smoke-non-tool"),
            joints=safe_joints,
            phase="drilling",
            sequence=0,
        )
        require(non_tool, False, "non-tool collision", "non-tool")
        if ROBOT_OBSTACLE_ID not in {
            non_tool.get("first_body"),
            non_tool.get("second_body"),
        }:
            raise RuntimeError(f"non-tool obstacle pair missing: {non_tool}")
        report["non_tool_world_collision_rejected"] = True
        publish_sphere(node, ROBOT_OBSTACLE_ID, link_origin, remove=True)

        lateral_entry = (entry[0] + 0.010, entry[1], entry[2])
        lateral_target = (
            lateral_entry[0], lateral_entry[1] + 0.010, lateral_entry[2]
        )
        lateral = task_command(
            node,
            config=config_payload(
                lateral_entry, lateral_target, "phase-smoke-lateral"
            ),
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
            config=config_payload(
                overshoot_entry, overshoot_target, "phase-smoke-overshoot"
            ),
            joints=safe_joints,
            phase="drilling",
            sequence=0,
        )
        require(overshoot, False, "overshoot", "overshot")
        report["overshoot_rejected"] = True

        bounds = task_command(
            node,
            config=config_payload(entry, target, "phase-smoke-bounds"),
            joints=[99.0] * 6,
            phase="drilling",
            sequence=0,
        )
        require(bounds, False, "joint bounds", "bounds")
        report["joint_bounds_rejected"] = True

        publish_sphere(node, TARGET_ID, contact_centre, remove=True)
        one_mm_clearance = task_command(
            node,
            config=config_payload(entry, target, "phase-smoke-self"),
            joints=UNDER_CLEARANCE_JOINTS,
            phase="approach",
            sequence=0,
        )
        require(one_mm_clearance, True, "one-millimetre research clearance")
        self_distance = float(one_mm_clearance.get("minimum_self_distance_m"))
        if not 0.001 <= self_distance < 0.005:
            raise RuntimeError(
                f"expected a state between the new and old margins: {one_mm_clearance}"
            )
        report["one_mm_margin_accepts_previous_five_mm_rejection"] = True

        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        try:
            publish_sphere(node, TARGET_ID, (0.0, 0.0, 0.0), remove=True)
            publish_sphere(node, FORBIDDEN_ID, (0.0, 0.0, 0.0), remove=True)
            publish_sphere(node, ROBOT_OBSTACLE_ID, (0.0, 0.0, 0.0), remove=True)
            publish_sphere(node, GUIDE_ID, (0.0, 0.0, 0.0), remove=True)
        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
