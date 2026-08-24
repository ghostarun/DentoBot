#!/usr/bin/env python3
"""ROS-level smoke test for DENTOBOT state, TF, and Cartesian planning."""

from __future__ import annotations

import json
import time

import rclpy
from moveit_msgs.srv import GetCartesianPath, GetPositionIK, GetStateValidity
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray, String
from tf2_ros import Buffer, TransformListener


class SmokeNode(Node):
    def __init__(self) -> None:
        super().__init__("dentobot_moveit_smoke")
        self.joint_state = None
        self.guard_status = None
        self.guard_status_sequence = 0
        self.create_subscription(
            JointState,
            "/joint_states",
            self._on_joint_state,
            qos_profile_sensor_data,
        )
        self.command_publisher = self.create_publisher(
            Float64MultiArray,
            "/dentobot/slicer_joint_positions",
            10,
        )
        self.create_subscription(
            String,
            "/dentobot/joint_command_status",
            self._on_guard_status,
            10,
        )
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.cartesian_client = self.create_client(
            GetCartesianPath, "/compute_cartesian_path"
        )
        self.validity_client = self.create_client(
            GetStateValidity, "/check_state_validity"
        )
        self.ik_client = self.create_client(GetPositionIK, "/compute_ik")

    def _on_joint_state(self, message: JointState) -> None:
        self.joint_state = message

    def _on_guard_status(self, message: String) -> None:
        self.guard_status = json.loads(message.data)
        self.guard_status_sequence += 1


def spin_until(node: Node, predicate, timeout_sec: float):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        result = predicate()
        if result:
            return result
    return None


def command_through_guard(node: SmokeNode, values, timeout_sec: float = 15.0):
    """Publish one candidate and return the matching collision-guard result."""
    start_sequence = node.guard_status_sequence
    command = Float64MultiArray()
    command.data = list(values)

    def matching_status():
        status = node.guard_status
        if node.guard_status_sequence <= start_sequence or not status:
            return None
        requested = status.get("requested_positions", [])
        if len(requested) != len(values):
            return None
        return status if all(
            abs(float(actual) - float(expected)) < 1e-9
            for actual, expected in zip(requested, values)
        ) else None

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        node.command_publisher.publish(command)
        result = spin_until(node, matching_status, 0.5)
        if result is not None:
            return result
    raise RuntimeError("collision guard did not answer the requested joint vector")


def main() -> None:
    rclpy.init()
    node = SmokeNode()
    report = {}
    try:
        if not node.cartesian_client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError("/compute_cartesian_path unavailable")
        if not node.validity_client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError("/check_state_validity unavailable")
        if not node.ik_client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError("/compute_ik unavailable")
        if spin_until(node, lambda: node.joint_state, 10.0) is None:
            raise RuntimeError("/joint_states unavailable")
        accepted_command = [0.1, 0.02, 0.2, 0.02, 0.1, 0.0]
        accepted_status = command_through_guard(node, accepted_command)
        if not accepted_status.get("accepted"):
            raise RuntimeError(
                "known-safe command was rejected: " + accepted_status.get("reason", "")
            )
        if spin_until(
            node,
            lambda: node.joint_state
            if node.joint_state
            and all(
                abs(actual - expected) < 1e-6
                for actual, expected in zip(
                    node.joint_state.position, accepted_command
                )
            )
            else None,
            5.0,
        ) is None:
            raise RuntimeError("simulated J2/J4 command did not update /joint_states")
        report["manual_joint_command_applied"] = True
        report["guard_checked_samples"] = int(accepted_status["checked_samples"])
        report["guard_minimum_self_distance_m"] = accepted_status[
            "minimum_self_distance_m"
        ]
        report["j2_m"] = float(node.joint_state.position[1])
        report["j4_m"] = float(node.joint_state.position[3])

        rejected_command = [0.1, 0.08, 0.2, 0.075, 0.1, 0.0]
        rejected_status = command_through_guard(node, rejected_command)
        if rejected_status.get("accepted"):
            raise RuntimeError("known under-clearance command was accepted")
        if not all(
            abs(actual - expected) < 1e-6
            for actual, expected in zip(node.joint_state.position, accepted_command)
        ):
            raise RuntimeError("rejected command changed /joint_states")
        report["under_clearance_rejected"] = True
        report["rejected_pair"] = [
            rejected_status.get("first_body", ""),
            rejected_status.get("second_body", ""),
        ]
        report["rejection_reason"] = rejected_status.get("reason", "")
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
            raise RuntimeError("base_link -> dentobot_drill_tip_provisional TF unavailable")

        validity = GetStateValidity.Request()
        validity.group_name = "dentobot_arm"
        validity.robot_state.joint_state = node.joint_state
        validity.robot_state.is_diff = False
        future = node.validity_client.call_async(validity)
        rclpy.spin_until_future_complete(node, future, timeout_sec=10.0)
        validity_response = future.result()
        if validity_response is None:
            raise RuntimeError("state-validity request timed out")
        report["commanded_state_valid"] = bool(validity_response.valid)
        report["commanded_state_contacts"] = sorted(
            {
                tuple(sorted((contact.contact_body_1, contact.contact_body_2)))
                for contact in validity_response.contacts
            }
        )

        from geometry_msgs.msg import Pose

        ik_response = None
        ik_offset = None
        for offset in (
            (0.001, 0.0, 0.0),
            (-0.001, 0.0, 0.0),
            (0.0, 0.001, 0.0),
            (0.0, -0.001, 0.0),
            (0.0, 0.0, 0.001),
            (0.0, 0.0, -0.001),
        ):
            ik_request = GetPositionIK.Request()
            ik_request.ik_request.group_name = "dentobot_arm"
            ik_request.ik_request.robot_state.joint_state = node.joint_state
            ik_request.ik_request.robot_state.is_diff = False
            ik_request.ik_request.ik_link_name = "dentobot_drill_tip_provisional"
            ik_request.ik_request.pose_stamped.header.frame_id = "base_link"
            ik_request.ik_request.pose_stamped.pose.position.x = (
                transform.transform.translation.x + offset[0]
            )
            ik_request.ik_request.pose_stamped.pose.position.y = (
                transform.transform.translation.y + offset[1]
            )
            ik_request.ik_request.pose_stamped.pose.position.z = (
                transform.transform.translation.z + offset[2]
            )
            ik_request.ik_request.pose_stamped.pose.orientation = (
                transform.transform.rotation
            )
            ik_request.ik_request.avoid_collisions = True
            ik_request.ik_request.timeout.sec = 2
            future = node.ik_client.call_async(ik_request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
            ik_response = future.result()
            if ik_response is None:
                raise RuntimeError("IK request timed out")
            if int(ik_response.error_code.val) == 1:
                ik_offset = offset
                break
        if ik_response is None or int(ik_response.error_code.val) != 1:
            raise RuntimeError("KDL/MoveIt failed all 1 mm IK probes")
        report["ik_success"] = True
        report["ik_offset_m"] = ik_offset
        report["ik_solution_joint_count"] = len(
            ik_response.solution.joint_state.position
        )

        response = None
        selected_offset = None
        for offset in (
            (0.001, 0.0, 0.0),
            (-0.001, 0.0, 0.0),
            (0.0, 0.001, 0.0),
            (0.0, -0.001, 0.0),
            (0.0, 0.0, 0.001),
            (0.0, 0.0, -0.001),
        ):
            request = GetCartesianPath.Request()
            request.header.frame_id = "base_link"
            request.start_state.joint_state = node.joint_state
            request.start_state.is_diff = False
            request.group_name = "dentobot_arm"
            request.link_name = "dentobot_drill_tip_provisional"
            for scale in (0.0, 1.0):
                pose = Pose()
                pose.position.x = transform.transform.translation.x + scale * offset[0]
                pose.position.y = transform.transform.translation.y + scale * offset[1]
                pose.position.z = transform.transform.translation.z + scale * offset[2]
                pose.orientation = transform.transform.rotation
                request.waypoints.append(pose)
            request.max_step = 0.0005
            request.jump_threshold = 0.0
            request.avoid_collisions = True
            request.max_velocity_scaling_factor = 0.2
            request.max_acceleration_scaling_factor = 0.2
            future = node.cartesian_client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=15.0)
            response = future.result()
            if response is None:
                raise RuntimeError("Cartesian request timed out")
            if response.fraction >= 0.99 and response.solution.joint_trajectory.points:
                selected_offset = offset
                break
        report["cartesian_fraction_collision_aware"] = float(response.fraction)
        report["cartesian_points"] = len(response.solution.joint_trajectory.points)
        report["cartesian_offset_m"] = selected_offset
        report["error_code"] = int(response.error_code.val)
        print(json.dumps(report, indent=2, sort_keys=True))
        if response.fraction < 0.99 or not response.solution.joint_trajectory.points:
            raise RuntimeError("MoveIt did not produce the 1 mm smoke trajectory")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
