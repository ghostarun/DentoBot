#!/usr/bin/env python3
"""Publish the externally owned DENTOBOT simulation stack contract.

The JSON status is intentionally small and transport-only. Slicer consumes it
without spawning processes or invoking the ROS CLI. This node never exposes a
controller or hardware command interface.
"""

from __future__ import annotations

import json
from typing import Iterable, Sequence

STATUS_SCHEMA = "dentobot.simulation_status.v1"
REQUIRED_DESCRIPTION_NODES = frozenset(
    {
        "/dentobot_robot_state_publisher",
        "/dentobot_slicer_joint_state_publisher",
        "/dentobot_collision_guard",
    }
)
REQUIRED_PLANNING_NODES = frozenset({"/move_group"})
REQUIRED_PLANNING_SERVICES = frozenset(
    {
        "/check_state_validity",
        "/compute_cartesian_path",
        "/compute_ik",
    }
)


def normalized_graph_names(
    names_and_namespaces: Iterable[tuple[str, str]],
) -> set[str]:
    """Return canonical absolute node names from an rclpy graph result."""
    names: set[str] = set()
    for name, namespace in names_and_namespaces:
        namespace = (namespace or "/").strip()
        prefix = "/" if namespace == "/" else "/" + namespace.strip("/") + "/"
        names.add(prefix + name.strip("/"))
    return names


def build_status(
    *,
    node_names: set[str],
    service_names: set[str],
    joint_state_publishers: int,
) -> dict[str, object]:
    """Build a deterministic readiness payload from graph observations."""
    missing_description = sorted(REQUIRED_DESCRIPTION_NODES - node_names)
    missing_planning_nodes = sorted(REQUIRED_PLANNING_NODES - node_names)
    missing_planning_services = sorted(REQUIRED_PLANNING_SERVICES - service_names)
    description_ready = not missing_description and joint_state_publishers == 1
    planning_ready = not missing_planning_nodes and not missing_planning_services
    ready = description_ready and planning_ready

    reasons: list[str] = []
    if missing_description:
        reasons.append("missing nodes: " + ", ".join(missing_description))
    if joint_state_publishers != 1:
        reasons.append(
            "expected exactly one /joint_states publisher, found "
            f"{joint_state_publishers}"
        )
    if missing_planning_nodes:
        reasons.append("missing planner nodes: " + ", ".join(missing_planning_nodes))
    if missing_planning_services:
        reasons.append(
            "missing planner services: " + ", ".join(missing_planning_services)
        )

    return {
        "schema": STATUS_SCHEMA,
        "mode": "simulation_only",
        "description_ready": description_ready,
        "planning_ready": planning_ready,
        "joint_state_publisher_count": int(joint_state_publishers),
        "ready": ready,
        "reason": "; ".join(reasons),
    }


def main(args: Sequence[str] | None = None) -> None:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class SimulationStatusPublisher(Node):
        def __init__(self) -> None:
            super().__init__("dentobot_simulation_status_publisher")
            self._publisher = self.create_publisher(
                String,
                "/dentobot/simulation_status",
                1,
            )
            self.create_timer(0.5, self._publish_status)

        def _publish_status(self) -> None:
            node_names = normalized_graph_names(self.get_node_names_and_namespaces())
            service_names = {name for name, _types in self.get_service_names_and_types()}
            joint_publishers = len(self.get_publishers_info_by_topic("/joint_states"))
            status = build_status(
                node_names=node_names,
                service_names=service_names,
                joint_state_publishers=joint_publishers,
            )
            message = String()
            message.data = json.dumps(status, separators=(",", ":"), sort_keys=True)
            self._publisher.publish(message)

    rclpy.init(args=args)
    node = SimulationStatusPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
