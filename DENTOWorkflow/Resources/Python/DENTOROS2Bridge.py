"""Thin SlicerROS2 adapter for DENTOBOT Step 6 simulation.

ROS 2 and MoveIt are owned by the desktop launcher. This module observes a
versioned readiness topic, creates MRML robot/control nodes, publishes simulated
joint positions, and requests plans. It never starts, kills, or shells into ROS.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping, Optional, Sequence, Tuple

ROS2_ROBOT_NAME = "dentobot"
ROS2_URDF_PARAM_NODE = "/dentobot_robot_state_publisher"
ROS2_URDF_PARAM_NAME = "robot_description"
ROS2_FIXED_FRAME = "base_link"
ROS2_TF_PREFIX = ""
ROS2_JOINT_STATES_TOPIC = "/joint_states"
ROS2_PLANNING_GROUP = "dentobot_arm"
ROS2_TOOL_TCP_LINK = "dentobot_tool_tcp"
ROS2_SLICER_JOINT_COMMAND_TOPIC = "/dentobot/slicer_joint_positions"
ROS2_JOINT_COMMAND_STATUS_TOPIC = "/dentobot/joint_command_status"
ROS2_JOINT_COMMAND_STATUS_SCHEMA = "dentobot.joint_command_status.v1"
ROS2_SIMULATION_STATUS_TOPIC = "/dentobot/simulation_status"
ROS2_SIMULATION_STATUS_SCHEMA = "dentobot.simulation_status.v1"
ROS2_DEFAULT_SLICER_NODE = "slicer"
ROS2_SLICER_JOINT_PUBLISH_INTERVAL_MS = 50

ROS2_ROBOT_NODE_ATTRIBUTE = "DENTOBOT.Ros2RobotName"
ROS2_MOTION_ACTIVE_ATTRIBUTE = "DENTOBOT.Ros2MotionControlActive"
ROS2_SLICER_JOINT_PUBLISHER_ATTRIBUTE = "DENTOBOT.SlicerJointCommandPublisher"
ROS2_STATUS_SUBSCRIBER_ATTRIBUTE = "DENTOBOT.SimulationStatusSubscriber"
ROS2_JOINT_STATUS_SUBSCRIBER_ATTRIBUTE = "DENTOBOT.JointCommandStatusSubscriber"
ROS2_OBSTACLE_PROXY_ATTRIBUTE = "DENTOBOT.MoveItObstacleProxy"
ROS2_OBSTACLE_SOURCE_ATTRIBUTE = "DENTOBOT.MoveItObstacleSource"
ROS2_MOTION_CONTROL_OBSTACLE_ATTRIBUTE = "ROS2MotionControl.MoveItObstacle"
ROS2_MOTION_CONTROL_OBSTACLE_FRAME_ATTRIBUTE = "ROS2MotionControl.MoveItObstacleFrame"
ROS2_JOINT_SI_ORDER = (
    "link-1_Revolute-1",
    "link-2_Slider-2",
    "link-3_Revolute-3",
    "link-4_Slider-4",
    "link-5_Revolute-5",
    "pneumatic_spindle-Copy_Revolute-6",
)

ROS2_MODULE_NAME = "ROS2"
ROS2_MOTION_MODULE_NAME = "ROS2MotionControl"
ROS2_UNAVAILABLE_MESSAGE = (
    "SlicerROS2 is not loaded. Close Slicer and start DENTO Workflow with "
    "./Workspace/scripts/launch-dentoworkflow.bash."
)
EXTERNAL_STACK_MESSAGE = (
    "The DENTOBOT simulation stack is externally owned. Restart Slicer with "
    "./Workspace/scripts/launch-dentoworkflow.bash; Step 6 does not start or "
    "kill ROS processes."
)


class RuntimeState(str, Enum):
    OFFLINE = "offline"
    DESCRIPTION_READY = "description_ready"
    PLANNING_READY = "planning_ready"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class SimulationStackStatus:
    state: RuntimeState
    description_ready: bool = False
    planning_ready: bool = False
    joint_state_publisher_count: int = 0
    reason: str = ""

    @property
    def ready(self) -> bool:
        return self.state == RuntimeState.READY


@dataclass(frozen=True)
class MoveItCartesianResult:
    success: bool
    message: str
    fraction: float = 0.0
    waypoint_joint_vectors_si: tuple[dict[str, float], ...] = ()
    waypoint_times_sec: tuple[float, ...] = ()


@dataclass(frozen=True)
class JointCommandStatus:
    accepted: bool
    reason: str
    requested_positions: tuple[float, ...] = ()
    accepted_positions: tuple[float, ...] = ()
    checked_samples: int = 0
    minimum_clearance_m: float = 0.005
    minimum_self_distance_m: Optional[float] = None
    minimum_world_distance_m: Optional[float] = None
    first_body: str = ""
    second_body: str = ""
    world_object_count: int = 0


_status_subscriber = None
_status_observer = None
_last_status = SimulationStackStatus(RuntimeState.OFFLINE, reason="No status received.")
_last_status_at = 0.0
_slicer_joint_command_timer = None
_slicer_joint_command_publisher = None
_joint_status_subscriber = None
_joint_status_observer = None
_last_joint_status = None
_last_joint_status_at = 0.0
_configured_motion_widget = None


def parse_simulation_status(payload: str) -> SimulationStackStatus:
    """Validate and convert the launcher status JSON into an explicit state."""
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        return SimulationStackStatus(RuntimeState.ERROR, reason=f"Invalid status JSON: {exc}")
    if data.get("schema") != ROS2_SIMULATION_STATUS_SCHEMA:
        return SimulationStackStatus(
            RuntimeState.ERROR,
            reason="Unsupported or missing simulation-status schema.",
        )
    if data.get("mode") != "simulation_only":
        return SimulationStackStatus(
            RuntimeState.ERROR,
            reason="Refusing a ROS stack that is not marked simulation_only.",
        )
    description_ready = data.get("description_ready") is True
    planning_ready = data.get("planning_ready") is True
    publisher_count = int(data.get("joint_state_publisher_count", 0))
    reason = str(data.get("reason", "") or "")
    if data.get("ready") is True and description_ready and planning_ready and publisher_count == 1:
        state = RuntimeState.READY
    elif planning_ready:
        state = RuntimeState.PLANNING_READY
    elif description_ready:
        state = RuntimeState.DESCRIPTION_READY
    else:
        state = RuntimeState.OFFLINE
    return SimulationStackStatus(
        state=state,
        description_ready=description_ready,
        planning_ready=planning_ready,
        joint_state_publisher_count=publisher_count,
        reason=reason,
    )


def parse_joint_command_status(payload: str) -> JointCommandStatus:
    """Validate the simulation-only collision-guard result contract."""
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid joint-command status JSON: {exc}") from exc
    if data.get("schema") != ROS2_JOINT_COMMAND_STATUS_SCHEMA:
        raise ValueError("Unsupported or missing joint-command status schema.")
    if data.get("mode") != "simulation_only":
        raise ValueError("Refusing joint-command status outside simulation_only mode.")

    def positions(key: str) -> tuple[float, ...]:
        values = data.get(key)
        if not isinstance(values, list) or len(values) != len(ROS2_JOINT_SI_ORDER):
            raise ValueError(f"{key} must contain six ordered joint values.")
        parsed = tuple(float(value) for value in values)
        if not all(isfinite(value) for value in parsed):
            raise ValueError(f"{key} contains a non-finite joint value.")
        return parsed

    def optional_distance(key: str) -> Optional[float]:
        value = data.get(key)
        if value is None:
            return None
        parsed = float(value)
        if not isfinite(parsed):
            raise ValueError(f"{key} must be finite or null.")
        return parsed

    if not isinstance(data.get("accepted"), bool):
        raise ValueError("accepted must be a boolean.")
    minimum_clearance_m = float(data.get("minimum_clearance_m", 0.005))
    if not isfinite(minimum_clearance_m) or minimum_clearance_m < 0.0:
        raise ValueError("minimum_clearance_m must be finite and non-negative.")
    return JointCommandStatus(
        accepted=data["accepted"],
        reason=str(data.get("reason", "") or ""),
        requested_positions=positions("requested_positions"),
        accepted_positions=positions("accepted_positions"),
        checked_samples=max(0, int(data.get("checked_samples", 0))),
        minimum_clearance_m=minimum_clearance_m,
        minimum_self_distance_m=optional_distance("minimum_self_distance_m"),
        minimum_world_distance_m=optional_distance("minimum_world_distance_m"),
        first_body=str(data.get("first_body", "") or ""),
        second_body=str(data.get("second_body", "") or ""),
        world_object_count=max(0, int(data.get("world_object_count", 0))),
    )


def _module_logic(module_name: str):
    try:
        import slicer

        return slicer.util.getModuleLogic(module_name)
    except Exception:
        return None


def ensure_ros2_slicer_modules() -> Tuple[Optional[object], Optional[object], str]:
    """Return already loaded SlicerROS2 logics; never mutate module search paths."""
    ros_logic = _module_logic(ROS2_MODULE_NAME)
    motion_logic = _module_logic(ROS2_MOTION_MODULE_NAME)
    if ros_logic is None:
        return None, None, ROS2_UNAVAILABLE_MESSAGE
    if motion_logic is None:
        return ros_logic, None, (
            "ROS2MotionControl is not loaded. Restart through the DENTOBOT launcher."
        )
    return ros_logic, motion_logic, ""


def get_ros2_logic():
    return _module_logic(ROS2_MODULE_NAME)


def get_motion_control_logic():
    return _module_logic(ROS2_MOTION_MODULE_NAME)


def _remove_ros2_node_reference(ros_node, role: str, node_id: Optional[str]) -> None:
    """Work around SlicerROS2 removing the reference after the final index."""
    if ros_node is None or not node_id:
        return
    for index in reversed(range(ros_node.GetNumberOfNodeReferences(role))):
        if ros_node.GetNthNodeReferenceID(role, index) == node_id:
            ros_node.RemoveNthNodeReferenceID(role, index)


def _mark_node_and_storage_transient(node) -> None:
    """Exclude one runtime node and its owned display/storage helpers from save."""
    if node is None:
        return
    node.SaveWithSceneOff()
    for role in ("display", "storage"):
        for index in range(node.GetNumberOfNodeReferences(role)):
            referenced = node.GetNthNodeReference(role, index)
            if referenced is not None:
                referenced.SaveWithSceneOff()


def mark_slicer_ros2_runtime_nodes_transient() -> int:
    """Keep the live SlicerROS2 graph out of DENTOBOT case scenes."""
    try:
        import slicer
    except ImportError:
        return 0

    runtime_nodes = []
    robot_nodes = []
    for index in range(slicer.mrmlScene.GetNumberOfNodes()):
        node = slicer.mrmlScene.GetNthNode(index)
        if node is None:
            continue
        if node.GetClassName().startswith("vtkMRMLROS2"):
            runtime_nodes.append(node)
        if node.IsA("vtkMRMLROS2RobotNode"):
            robot_nodes.append(node)

    marked_ids = set()

    def mark(node) -> None:
        if node is None:
            return
        node_id = node.GetID() or f"object:{id(node)}"
        if node_id in marked_ids:
            return
        marked_ids.add(node_id)
        _mark_node_and_storage_transient(node)

    for node in runtime_nodes:
        mark(node)

    # SlicerROS2 robot link/goal models and transforms use ordinary MRML
    # classes. They are generated runtime views, unlike the separately tagged
    # DENTOBOT fallback robot and persistent base-placement transform.
    for robot_node in robot_nodes:
        for role in ("model", "goal_model", "goal_transform", "lookup", "parameter"):
            for index in range(robot_node.GetNumberOfNodeReferences(role)):
                mark(robot_node.GetNthNodeReference(role, index))

    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        if node.GetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE) == "true":
            mark(node)

    motion_parameter = slicer.mrmlScene.GetSingletonNode(
        "ROS2MotionControl", "vtkMRMLScriptedModuleNode"
    )
    mark(motion_parameter)
    return len(marked_ids)


def clear_legacy_dentobot_moveit_source_attributes() -> int:
    """Remove old Motion Control tags from persistent DENTOBOT source models."""
    try:
        import slicer
    except ImportError:
        return 0
    cleared = 0
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        if node.GetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE) == "true":
            continue
        if not node.GetAttribute("DENTOBOT.ModelRole"):
            continue
        if node.GetAttribute(ROS2_MOTION_CONTROL_OBSTACLE_ATTRIBUTE) is None:
            continue
        node.RemoveAttribute(ROS2_MOTION_CONTROL_OBSTACLE_ATTRIBUTE)
        node.RemoveAttribute(ROS2_MOTION_CONTROL_OBSTACLE_FRAME_ATTRIBUTE)
        cleared += 1
    return cleared


def clear_stale_ros2_motion_active_attributes() -> int:
    """Clear persisted runtime-active flags when no live ROS robot exists."""
    try:
        import slicer
    except ImportError:
        return 0
    live_robot = any(
        node.GetAttribute(ROS2_ROBOT_NODE_ATTRIBUTE) == ROS2_ROBOT_NAME
        for node in slicer.util.getNodesByClass("vtkMRMLROS2RobotNode")
    )
    if live_robot:
        return 0
    cleared = 0
    for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode"):
        if node.GetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE) != "true":
            continue
        node.RemoveAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE)
        cleared += 1
    return cleared


def ensure_default_ros2_node_in_scene():
    """Reattach SlicerROS2's transient default node after MRML scene clear."""
    try:
        import slicer
    except ImportError:
        return None
    ros_logic = get_ros2_logic()
    ros_node = ros_logic.GetDefaultROS2Node() if ros_logic is not None else None
    if ros_node is None:
        return None
    if ros_node.GetScene() is not slicer.mrmlScene:
        if ros_node.GetScene() is not None:
            return None
        slicer.mrmlScene.AddNode(ros_node)
    # This node is owned for the lifetime of the SlicerROS2 module logic, not
    # by an individual dental case.  Clear(0) retains singleton nodes; letting
    # a case clear destroy this logic-owned native ROS node crashes warm New
    # Case even after its robot/subscribers have been removed.
    if not ros_node.GetSingletonTag():
        ros_node.SetSingletonTag("DENTOBOTRuntimeROS2Default")
    ros_node.HideFromEditorsOn()
    ros_node.SaveWithSceneOff()
    return ros_node


def release_default_ros2_node_singleton() -> None:
    """Allow normal application/module teardown to destroy the ROS host."""
    ros_logic = get_ros2_logic()
    ros_node = ros_logic.GetDefaultROS2Node() if ros_logic is not None else None
    if ros_node is not None and ros_node.GetSingletonTag() == "DENTOBOTRuntimeROS2Default":
        ros_node.SetSingletonTag(None)


def _on_status_modified(caller=None, event=None) -> None:
    del event
    global _last_status, _last_status_at
    try:
        payload = caller.GetLastMessage() if caller is not None else ""
        _last_status = parse_simulation_status(str(payload or ""))
        _last_status_at = time.monotonic()
    except Exception as exc:
        _last_status = SimulationStackStatus(RuntimeState.ERROR, reason=str(exc))
        _last_status_at = time.monotonic()


def _ensure_status_subscriber():
    global _status_subscriber, _status_observer
    ros_node = ensure_default_ros2_node_in_scene()
    if ros_node is None:
        return None
    if _status_subscriber is not None:
        return _status_subscriber
    subscriber = ros_node.GetSubscriberNodeByTopic(ROS2_SIMULATION_STATUS_TOPIC)
    if subscriber is None:
        subscriber = ros_node.CreateAndAddSubscriberNode(
            "String", ROS2_SIMULATION_STATUS_TOPIC
        )
    if subscriber is None:
        return None
    subscriber.SetAttribute(ROS2_STATUS_SUBSCRIBER_ATTRIBUTE, "true")
    subscriber.SaveWithSceneOff()
    _status_subscriber = subscriber
    _status_observer = subscriber.AddObserver("ModifiedEvent", _on_status_modified)
    if subscriber.GetNumberOfMessages() > 0:
        _on_status_modified(subscriber)
    return subscriber


def _restore_motion_control_positions(values: Sequence[float]) -> None:
    """Return the ROS2MotionControl sliders to the guard's accepted state."""
    if len(values) != len(ROS2_JOINT_SI_ORDER):
        return
    try:
        import slicer

        widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
        setter = getattr(widget, "_setJointUi_SIToSlicer", None) if widget else None
        if widget is None or not callable(setter):
            return
        restored = [float(value) for value in values]
        widget.jointPositionsRad = restored
        setter(restored)
    except Exception:
        return


def _on_joint_status_modified(caller=None, event=None) -> None:
    del event
    global _last_joint_status, _last_joint_status_at
    try:
        payload = caller.GetLastMessage() if caller is not None else ""
        parsed = parse_joint_command_status(str(payload or ""))
        _last_joint_status = parsed
        _last_joint_status_at = time.monotonic()
        if not parsed.accepted:
            _restore_motion_control_positions(parsed.accepted_positions)
    except (TypeError, ValueError):
        return


def _ensure_joint_status_subscriber():
    global _joint_status_subscriber, _joint_status_observer
    ros_node = ensure_default_ros2_node_in_scene()
    if ros_node is None:
        return None
    if _joint_status_subscriber is not None:
        return _joint_status_subscriber
    subscriber = ros_node.GetSubscriberNodeByTopic(ROS2_JOINT_COMMAND_STATUS_TOPIC)
    if subscriber is None:
        subscriber = ros_node.CreateAndAddSubscriberNode(
            "String", ROS2_JOINT_COMMAND_STATUS_TOPIC
        )
    if subscriber is None:
        return None
    subscriber.SetAttribute(ROS2_JOINT_STATUS_SUBSCRIBER_ATTRIBUTE, "true")
    subscriber.SaveWithSceneOff()
    _joint_status_subscriber = subscriber
    _joint_status_observer = subscriber.AddObserver(
        "ModifiedEvent", _on_joint_status_modified
    )
    if subscriber.GetNumberOfMessages() > 0:
        _on_joint_status_modified(subscriber)
    return subscriber


def joint_command_status(max_age_sec: float = 2.5) -> Optional[JointCommandStatus]:
    """Return the latest fresh collision-guard result, if available."""
    subscriber = _ensure_joint_status_subscriber()
    if subscriber is None:
        return None
    ros_logic = get_ros2_logic()
    if ros_logic is not None:
        try:
            ros_logic.Spin()
        except Exception:
            pass
    if subscriber.GetNumberOfMessages() > 0 and _last_joint_status_at == 0.0:
        _on_joint_status_modified(subscriber)
    if _last_joint_status_at == 0.0:
        return None
    if time.monotonic() - _last_joint_status_at > float(max_age_sec):
        return None
    return _last_joint_status


def last_accepted_joint_positions_si() -> dict[str, float]:
    """Return the collision guard's most recent accepted six-joint state."""
    status = joint_command_status()
    if status is None or len(status.accepted_positions) != len(ROS2_JOINT_SI_ORDER):
        return {}
    return dict(zip(ROS2_JOINT_SI_ORDER, status.accepted_positions))


def _wait_for_joint_command_result(
    requested: Sequence[float],
    *,
    after_monotonic: float,
    timeout_sec: float = 1.5,
) -> Optional[JointCommandStatus]:
    """Wait for the guard response corresponding to one candidate vector."""
    expected = tuple(float(value) for value in requested)
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        ros_logic = get_ros2_logic()
        if ros_logic is not None:
            try:
                ros_logic.Spin()
            except Exception:
                pass
        try:
            import slicer

            slicer.app.processEvents()
        except Exception:
            pass
        status = _last_joint_status
        if (
            status is not None
            and _last_joint_status_at > after_monotonic
            and len(status.requested_positions) == len(expected)
            and all(
                abs(actual - wanted) <= 1e-9
                for actual, wanted in zip(status.requested_positions, expected)
            )
        ):
            return status
        time.sleep(0.01)
    return None


def simulation_stack_status(max_age_sec: float = 2.5) -> SimulationStackStatus:
    """Return the most recent fresh external-stack status."""
    subscriber = _ensure_status_subscriber()
    if subscriber is None:
        return SimulationStackStatus(
            RuntimeState.OFFLINE,
            reason="Simulation-status subscriber could not be created.",
        )
    ros_logic = get_ros2_logic()
    if ros_logic is not None:
        try:
            ros_logic.Spin()
        except Exception:
            pass
    if subscriber.GetNumberOfMessages() > 0 and _last_status_at == 0.0:
        _on_status_modified(subscriber)
    if _last_status_at == 0.0:
        return SimulationStackStatus(
            RuntimeState.OFFLINE,
            reason="Waiting for the external DENTOBOT simulation stack.",
        )
    age = time.monotonic() - _last_status_at
    if age > float(max_age_sec):
        return SimulationStackStatus(
            RuntimeState.OFFLINE,
            reason=f"Simulation status is stale ({age:.1f} s).",
        )
    return _last_status


def description_stack_running(*, force: bool = False) -> Tuple[bool, str]:
    del force
    status = simulation_stack_status()
    if status.description_ready:
        return True, ""
    return False, status.reason or EXTERNAL_STACK_MESSAGE


def slicer_motion_stack_ready(*, force: bool = False) -> Tuple[bool, str]:
    del force
    status = simulation_stack_status()
    if status.ready:
        return True, ""
    return False, status.reason or EXTERNAL_STACK_MESSAGE


def ros2_node_list(*, force: bool = False) -> Tuple[bool, list[str], str]:
    """Compatibility status view without calling the ROS CLI from Slicer."""
    del force
    if get_ros2_logic() is None:
        return False, [], ROS2_UNAVAILABLE_MESSAGE
    status = simulation_stack_status()
    nodes = ["/slicer"]
    if status.description_ready:
        nodes.extend(
            [
                "/dentobot_robot_state_publisher",
                "/dentobot_slicer_joint_state_publisher",
                "/dentobot_collision_guard",
            ]
        )
    if status.planning_ready:
        nodes.append("/move_group")
    return True, nodes, status.reason


def start_description_stack_background() -> Tuple[bool, str]:
    return False, EXTERNAL_STACK_MESSAGE


def ros2_unavailable_message() -> str:
    return ROS2_UNAVAILABLE_MESSAGE


def is_ros2_module_missing_message(message: str) -> bool:
    lowered = (message or "").lower()
    return "slicerros2 is not loaded" in lowered or "ros2motioncontrol is not loaded" in lowered


def is_ros2_runtime_unavailable_message(message: str) -> bool:
    lowered = (message or "").lower()
    return is_ros2_module_missing_message(message) or "external" in lowered or "status" in lowered


def slicer_ros2_runtime_status(
    *,
    require_stack: bool = False,
    require_slicer_node: bool = True,
) -> Tuple[bool, str]:
    del require_slicer_node
    ros_logic, motion_logic, error = ensure_ros2_slicer_modules()
    if ros_logic is None or motion_logic is None:
        return False, error
    if ros_logic.GetDefaultROS2Node() is None:
        return False, "ROS2 default node is not initialized."
    if require_stack:
        return slicer_motion_stack_ready()
    return True, ""


def ensure_slicer_ros2_runtime(*, require_stack: bool = False) -> Tuple[bool, str]:
    """Check the pre-launched runtime; this function never starts processes."""
    return slicer_ros2_runtime_status(require_stack=require_stack)


def joint_si_vector(positions_si: Mapping[str, float]) -> list[float]:
    missing = [name for name in ROS2_JOINT_SI_ORDER if name not in positions_si]
    if missing:
        raise ValueError("Missing joint values: " + ", ".join(missing))
    return [float(positions_si[name]) for name in ROS2_JOINT_SI_ORDER]


def find_ros2_robot_by_name(robot_name: str):
    try:
        import slicer
    except ImportError:
        return None
    for node in slicer.util.getNodesByClass("vtkMRMLROS2RobotNode"):
        if node.GetAttribute(ROS2_ROBOT_NODE_ATTRIBUTE) == robot_name:
            return node
    ros_node = ensure_default_ros2_node_in_scene()
    return ros_node.GetRobotNodeByName(robot_name) if ros_node is not None else None


def wait_for_robot_urdf(robot_node, process_events, timeout_sec: float = 30.0) -> bool:
    """Wait for the remote description without querying an unparsed URDF.

    ``FindRootAndTipLinks`` logs an error (and enters native robot code) when
    the asynchronous parameter callback has not populated the URDF yet.  In a
    warm Slicer process that produced a tight stream of native calls against a
    robot that could concurrently be torn down by New Case or module reload.
    """
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        process_events()
        ros_logic = get_ros2_logic()
        if ros_logic is not None:
            ros_logic.Spin()
        parameter_node = robot_node.GetNodeReference("parameter")
        if parameter_node is not None and parameter_node.IsParameterSet(
            ROS2_URDF_PARAM_NAME, True
        ):
            # The parameter event parses the URDF synchronously.  Only enter
            # FindRootAndTipLinks after the source parameter is present.
            process_events()
            root_and_tip = robot_node.FindRootAndTipLinks()
            return bool(root_and_tip and len(root_and_tip) >= 2)
        time.sleep(0.1)
    return False


def align_ros2_robot_to_base_transform(robot_node, base_transform) -> bool:
    lookup = robot_node.GetNthNodeReference("lookup", 0)
    if lookup is None or base_transform is None:
        return False
    lookup.SetAndObserveTransformNodeID(base_transform.GetID())
    return True


def align_ros2_goal_to_base_transform(robot_node, base_transform) -> bool:
    """Parent the duplicated goal hierarchy under the mounted robot base.

    SlicerROS2 copies the live lookup hierarchy when it creates the goal robot,
    but the root goal transform has no lookup parent from which to inherit the
    external Step 6 mount.  Pair the first goal transform with the same base
    transform used by the first live lookup so current and goal configurations
    differ only at movable joints.
    """
    goal_root = robot_node.GetNthNodeReference("goal_transform", 0)
    if goal_root is None or base_transform is None:
        return False
    goal_root.SetAndObserveTransformNodeID(base_transform.GetID())
    return True


def _motion_ui_status(widget, text: str, *, error: bool = False) -> None:
    label = getattr(widget, "_dentobotMotionStatusLabel", None)
    if label is None:
        return
    label.text = str(text)
    label.styleSheet = (
        "color: #b00020; font-weight: 600;"
        if error
        else "color: #176b2c; font-weight: 600;"
    )


def _trajectory_motion_summary(trajectory) -> Tuple[bool, str]:
    if trajectory is None:
        return False, "No new trajectory was returned. Set a distinct IK goal first."
    try:
        points = trajectory.GetJointTrajectory().GetPoints()
    except Exception:
        return False, "The planner returned an unreadable trajectory."
    if not points:
        return False, "The planner returned an empty trajectory."
    first = [float(value) for value in points[0].GetPositions()]
    last = [float(value) for value in points[-1].GetPositions()]
    if len(first) == len(last) and all(
        abs(start - goal) <= 1e-9 for start, goal in zip(first, last)
    ):
        return False, (
            "Plan contains no motion: current and goal states are identical. "
            "Open 3D Control and drag the TCP probe to create an IK goal."
        )
    return True, (
        f"Plan ready: {len(points)} point(s). Preview animates the goal model only; "
        "DENTOBOT Execute is disabled."
    )


def _ensure_dentobot_tcp_in_motion_widget(widget) -> None:
    """Expose the configured chain tip even without an SRDF end-effector group."""
    if widget is None or getattr(widget, "ui", None) is None:
        return
    combo = widget.ui.endEffectorLinkComboBox
    count = int(combo.count)
    selected_index = -1
    for index in range(count):
        if str(combo.itemData(index) or "") == ROS2_TOOL_TCP_LINK:
            selected_index = index
            break
    if selected_index < 0:
        combo.addItem(
            f"DENTOBOT provisional TCP ({ROS2_TOOL_TCP_LINK})",
            ROS2_TOOL_TCP_LINK,
        )
        selected_index = int(combo.count) - 1
    combo.setCurrentIndex(selected_index)
    widget.tiplink = ROS2_TOOL_TCP_LINK
    widget.goaltiplink = ROS2_TOOL_TCP_LINK
    logic = getattr(widget, "logic", None)
    if logic is not None:
        logic.tipLink = ROS2_TOOL_TCP_LINK


def configure_dentobot_motion_control_ui(widget, parameter_node) -> bool:
    """Adapt the generic Motion Control UI to the plan-only DENTOBOT contract."""
    global _configured_motion_widget
    if widget is None or getattr(widget, "ui", None) is None:
        return False
    if getattr(widget, "_dentobotUiConfigured", False):
        _ensure_dentobot_tcp_in_motion_widget(widget)
        return True

    import qt

    widget._dentobotUiConfigured = True
    widget._dentobotMoveGroupCheckboxText = widget.ui.moveGroupExistsCheckBox.text
    widget._dentobotMoveGroupCheckboxEnabled = widget.ui.moveGroupExistsCheckBox.enabled
    widget._dentobotExecuteVisible = widget.ui.executeButton.visible
    widget._dentobotExecuteEnabled = widget.ui.executeButton.enabled
    widget._dentobotPlanGroupEnabled = widget.ui.planGroupComboBox.enabled
    widget._dentobotEndEffectorEnabled = widget.ui.endEffectorLinkComboBox.enabled
    widget._dentobotOriginalRefreshEndEffector = widget.refreshEndEffectorLinkComboBox
    widget._dentobotOriginalLoadPlannedTrajectory = widget.loadPlannedTrajectory
    widget._dentobotOriginalComputeMoveItIK = widget.logic.computeIKWithMoveIt

    status_label = qt.QLabel()
    status_label.objectName = "dentobotMotionStatusLabel"
    status_label.wordWrap = True
    status_label.toolTip = (
        "The DENTOBOT stack is simulation-only. IK and planning are enabled; "
        "trajectory execution is intentionally unavailable."
    )
    widget.ui.moveItTab.layout().addRow(status_label)
    widget._dentobotMotionStatusLabel = status_label

    def refresh_end_effector(*args, **kwargs):
        result = widget._dentobotOriginalRefreshEndEffector(*args, **kwargs)
        _ensure_dentobot_tcp_in_motion_widget(widget)
        return result

    def load_planned_trajectory(
        trajectory,
        enableExecute=True,
        lockPlanning=False,
    ):
        del enableExecute
        result = widget._dentobotOriginalLoadPlannedTrajectory(
            trajectory,
            enableExecute=False,
            lockPlanning=lockPlanning,
        )
        widget.ui.executeButton.enabled = False
        widget.ui.executeButton.visible = False
        ok, message = _trajectory_motion_summary(
            widget.trajectoryData if result else None
        )
        _motion_ui_status(widget, message, error=not ok)
        return result

    def compute_moveit_ik(*args, **kwargs):
        solution = widget._dentobotOriginalComputeMoveItIK(*args, **kwargs)
        if solution:
            _motion_ui_status(
                widget,
                "IK solution found for dentobot_tool_tcp. Press Plan to compute "
                "a collision-aware path from the current state.",
            )
        else:
            _motion_ui_status(
                widget,
                "IK failed for the requested TCP pose. Move the probe closer or "
                "change its orientation; the goal state was not accepted.",
                error=True,
            )
        return solution

    def remember_trajectory_before_plan():
        widget._dentobotTrajectoryBeforePlan = widget.trajectoryData

    def report_plan_result(checked=False):
        del checked
        trajectory = widget.trajectoryData
        if trajectory is getattr(widget, "_dentobotTrajectoryBeforePlan", None):
            _motion_ui_status(
                widget,
                "Planning returned no new trajectory. Verify the IK goal, planning "
                "group, and collision state.",
                error=True,
            )
            return
        ok, message = _trajectory_motion_summary(trajectory)
        _motion_ui_status(widget, message, error=not ok)

    widget.refreshEndEffectorLinkComboBox = refresh_end_effector
    widget.loadPlannedTrajectory = load_planned_trajectory
    widget.logic.computeIKWithMoveIt = compute_moveit_ik
    widget._dentobotRememberTrajectoryBeforePlan = remember_trajectory_before_plan
    widget._dentobotReportPlanResult = report_plan_result
    widget.ui.planButton.connect("pressed()", remember_trajectory_before_plan)
    widget.ui.planButton.connect("clicked(bool)", report_plan_result)

    parameter_node.moveGroupExists = True
    parameter_node.planningGroup = ROS2_PLANNING_GROUP
    checkbox = widget.ui.moveGroupExistsCheckBox
    checkbox.blockSignals(True)
    checkbox.checked = True
    checkbox.text = "MoveIt ready (detected)"
    checkbox.enabled = False
    checkbox.toolTip = (
        "Read-only DENTOBOT status. The external launcher reported /move_group "
        "and required planning services ready."
    )
    checkbox.blockSignals(False)

    group_combo = widget.ui.planGroupComboBox
    group_index = group_combo.findText(ROS2_PLANNING_GROUP)
    if group_index < 0:
        group_combo.addItem(ROS2_PLANNING_GROUP)
        group_index = group_combo.findText(ROS2_PLANNING_GROUP)
    group_combo.setCurrentIndex(group_index)
    group_combo.enabled = False
    group_combo.toolTip = "DENTOBOT uses the fixed dentobot_arm planning group."

    _ensure_dentobot_tcp_in_motion_widget(widget)
    widget.ui.endEffectorLinkComboBox.enabled = False
    widget.ui.endEffectorLinkComboBox.toolTip = (
        "Provisional uncalibrated TCP at the CAD burr origin."
    )
    widget.ui.executeButton.enabled = False
    widget.ui.executeButton.visible = False
    _motion_ui_status(
        widget,
        "MoveIt ready · group dentobot_arm · TCP dentobot_tool_tcp · plan/preview "
        "only. In 3D Control, drag the TCP probe to solve IK before Plan.",
    )
    _configured_motion_widget = widget
    return True


def release_dentobot_motion_control_ui() -> None:
    """Remove adapter callbacks before reload, scene clear, or robot teardown."""
    global _configured_motion_widget
    widget = _configured_motion_widget
    _configured_motion_widget = None
    if widget is None or not getattr(widget, "_dentobotUiConfigured", False):
        return
    try:
        widget.ui.planButton.disconnect(
            "pressed()", widget._dentobotRememberTrajectoryBeforePlan
        )
        widget.ui.planButton.disconnect(
            "clicked(bool)", widget._dentobotReportPlanResult
        )
    except Exception:
        pass
    try:
        widget.refreshEndEffectorLinkComboBox = (
            widget._dentobotOriginalRefreshEndEffector
        )
        widget.loadPlannedTrajectory = widget._dentobotOriginalLoadPlannedTrajectory
        widget.logic.computeIKWithMoveIt = widget._dentobotOriginalComputeMoveItIK
        widget.ui.moveGroupExistsCheckBox.text = (
            widget._dentobotMoveGroupCheckboxText
        )
        widget.ui.moveGroupExistsCheckBox.enabled = (
            widget._dentobotMoveGroupCheckboxEnabled
        )
        widget.ui.executeButton.visible = widget._dentobotExecuteVisible
        widget.ui.executeButton.enabled = widget._dentobotExecuteEnabled
        widget.ui.planGroupComboBox.enabled = widget._dentobotPlanGroupEnabled
        widget.ui.endEffectorLinkComboBox.enabled = (
            widget._dentobotEndEffectorEnabled
        )
        status_label = getattr(widget, "_dentobotMotionStatusLabel", None)
        if status_label is not None:
            layout = widget.ui.moveItTab.layout()
            if layout is not None:
                layout.removeWidget(status_label)
            status_label.setParent(None)
            status_label.deleteLater()
            widget._dentobotMotionStatusLabel = None
    except Exception:
        pass
    widget._dentobotUiConfigured = False


def set_mrml_link_models_visible(model_nodes: list, visible: bool) -> None:
    for model_node in model_nodes:
        if model_node.GetDisplayNode() is None:
            model_node.CreateDefaultDisplayNodes()
        display = model_node.GetDisplayNode()
        if display is not None:
            display.SetVisibility(bool(visible))


def _motion_control_joint_positions() -> list[float]:
    try:
        import slicer

        widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
        values = getattr(widget, "jointPositionsRad", None) if widget else None
        return [float(value) for value in values] if values else []
    except Exception:
        return []


def _publish_slicer_joint_command() -> bool:
    if _slicer_joint_command_publisher is None:
        return False
    positions = _motion_control_joint_positions()
    if len(positions) != len(ROS2_JOINT_SI_ORDER):
        return False
    import vtk

    values = vtk.vtkDoubleArray()
    values.SetNumberOfValues(len(positions))
    for index, value in enumerate(positions):
        values.SetValue(index, value)
    _slicer_joint_command_publisher.Publish(values)
    return True


def start_slicer_joint_command_stream() -> Tuple[bool, str]:
    global _slicer_joint_command_timer, _slicer_joint_command_publisher
    import qt

    status = simulation_stack_status()
    if not status.ready or status.joint_state_publisher_count != 1:
        return False, status.reason or EXTERNAL_STACK_MESSAGE
    ros_node = ensure_default_ros2_node_in_scene()
    if ros_node is None:
        return False, "ROS2 default node is not initialized."
    if _ensure_joint_status_subscriber() is None:
        return False, "Could not create the collision-guard status subscriber."
    publisher = ros_node.GetPublisherNodeByTopic(ROS2_SLICER_JOINT_COMMAND_TOPIC)
    if publisher is None:
        publisher = ros_node.CreateAndAddPublisherNode(
            "DoubleArray", ROS2_SLICER_JOINT_COMMAND_TOPIC
        )
    if publisher is None:
        return False, "Could not create the simulated joint-position publisher."
    publisher.SetAttribute(ROS2_SLICER_JOINT_PUBLISHER_ATTRIBUTE, "true")
    publisher.SaveWithSceneOff()
    mark_slicer_ros2_runtime_nodes_transient()
    _slicer_joint_command_publisher = publisher
    if _slicer_joint_command_timer is None:
        _slicer_joint_command_timer = qt.QTimer()
        _slicer_joint_command_timer.setInterval(ROS2_SLICER_JOINT_PUBLISH_INTERVAL_MS)
        _slicer_joint_command_timer.timeout.connect(_publish_slicer_joint_command)
    _slicer_joint_command_timer.start()
    return True, ""


def stop_slicer_joint_command_stream(*, delete_publisher: bool = True) -> None:
    global _slicer_joint_command_timer, _slicer_joint_command_publisher
    publisher = _slicer_joint_command_publisher
    if _slicer_joint_command_timer is not None:
        _slicer_joint_command_timer.stop()
        _slicer_joint_command_timer = None
    if delete_publisher:
        ros_logic = get_ros2_logic()
        ros_node = ros_logic.GetDefaultROS2Node() if ros_logic is not None else None
        if ros_node is not None:
            if publisher is None:
                publisher = ros_node.GetPublisherNodeByTopic(
                    ROS2_SLICER_JOINT_COMMAND_TOPIC
                )
            if (
                publisher is not None
                and publisher.GetAttribute(ROS2_SLICER_JOINT_PUBLISHER_ATTRIBUTE)
                == "true"
            ):
                publisher_id = publisher.GetID()
                try:
                    ros_node.RemoveAndDeletePublisherNode(
                        ROS2_SLICER_JOINT_COMMAND_TOPIC
                    )
                finally:
                    _remove_ros2_node_reference(
                        ros_node, "publisher", publisher_id
                    )
    _slicer_joint_command_publisher = None


def apply_joint_positions_si_to_motion_control(
    positions_si: Mapping[str, float],
) -> Tuple[bool, str]:
    """Apply one simulated joint vector and publish it; report every failure."""
    try:
        import slicer

        widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
    except Exception as exc:
        return False, f"ROS2MotionControl widget is unavailable ({exc})."
    if widget is None or getattr(widget, "robot", None) is None:
        return False, "ROS2MotionControl is not active for the DENTOBOT robot."
    try:
        values = joint_si_vector(positions_si)
    except (KeyError, TypeError, ValueError) as exc:
        return False, str(exc)
    widget.jointPositionsRad = list(values)
    setter = getattr(widget, "_setJointUi_SIToSlicer", None)
    if not callable(setter):
        return False, "ROS2MotionControl joint UI conversion is unavailable."
    setter(values)
    stream_was_active = bool(
        _slicer_joint_command_timer is not None
        and _slicer_joint_command_timer.isActive()
    )
    if stream_was_active:
        _slicer_joint_command_timer.stop()
    status_before = _last_joint_status_at
    try:
        if not _publish_slicer_joint_command():
            return False, "Failed to publish the simulated joint vector."
        result = _wait_for_joint_command_result(
            values,
            after_monotonic=status_before,
        )
        if result is None:
            return False, "Collision guard did not answer the simulated joint request."
        if not result.accepted:
            _restore_motion_control_positions(result.accepted_positions)
            pair = ""
            if result.first_body or result.second_body:
                pair = f" ({result.first_body or '?'} ↔ {result.second_body or '?'})"
            return False, f"Collision guard rejected the move: {result.reason}{pair}"
        return True, result.reason
    finally:
        if stream_was_active and _slicer_joint_command_timer is not None:
            _slicer_joint_command_timer.start()


def connect_dentobot_motion_control(
    base_transform,
    hide_mrml_robot: bool = True,
    mrml_robot_models: Optional[list] = None,
    open_motion_module: bool = True,
    start_stack_if_needed: bool = True,
) -> Tuple[Optional[object], str]:
    """Create the Slicer robot and attach MoveIt plan-only motion control."""
    del start_stack_if_needed
    import slicer

    ready, message = ensure_slicer_ros2_runtime(require_stack=True)
    if not ready:
        return None, message
    ros_logic, motion_logic, error = ensure_ros2_slicer_modules()
    if ros_logic is None or motion_logic is None:
        return None, error
    if base_transform is None:
        return None, "Select or create the Step 6 robot-base transform first."
    ros_node = ensure_default_ros2_node_in_scene()
    if ros_node is None:
        return None, "ROS2 default node is not initialized in the active scene."
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    if robot_node is None:
        robot_node = ros_node.CreateAndAddRobotNode(
            ROS2_ROBOT_NAME,
            ROS2_URDF_PARAM_NODE,
            ROS2_URDF_PARAM_NAME,
            ROS2_FIXED_FRAME,
            ROS2_TF_PREFIX,
        )
        if robot_node is None:
            return None, "CreateAndAddRobotNode failed for the external robot description."
        robot_node.SetAttribute(ROS2_ROBOT_NODE_ATTRIBUTE, ROS2_ROBOT_NAME)
    if not wait_for_robot_urdf(robot_node, slicer.app.processEvents):
        # Never leave a half-created robot/parameter observer in the scene.
        # Such a node poisons the next Connect, New Case, and module reload.
        try:
            ros_logic.RemoveRobot(ROS2_ROBOT_NAME)
        except Exception:
            pass
        return None, "Timed out resolving DENTOBOT URDF/TF from the external stack."
    if not align_ros2_robot_to_base_transform(robot_node, base_transform):
        return None, "Could not align base_link with the Step 6 base transform."

    parameter_node = motion_logic.getParameterNode()
    parameter_node.robotNodeID = robot_node.GetID()
    parameter_node.jointStateTopic = ROS2_JOINT_STATES_TOPIC
    parameter_node.moveGroupExists = True
    parameter_node.planningGroup = ROS2_PLANNING_GROUP
    if not motion_logic.SetupRobotForMotionControl(parameter_node):
        return None, "SetupRobotForMotionControl failed."
    if not align_ros2_goal_to_base_transform(robot_node, base_transform):
        return None, "Could not align the goal robot with the Step 6 base transform."
    if not motion_logic.SetupMoveItPlanningGroup(robot_node, ROS2_PLANNING_GROUP):
        return None, "MoveIt planning group dentobot_arm could not be initialized."

    streamed, stream_error = start_slicer_joint_command_stream()
    if not streamed:
        return None, stream_error
    base_transform.SetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE, "true")
    if hide_mrml_robot and mrml_robot_models:
        set_mrml_link_models_visible(mrml_robot_models, False)
    widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
    if widget is not None:
        widget.setParameterNode(parameter_node)
        if not configure_dentobot_motion_control_ui(widget, parameter_node):
            return None, "Could not configure the DENTOBOT plan-only Motion Control UI."
    if open_motion_module:
        try:
            if slicer.util.mainWindow() is not None:
                slicer.util.selectModule(ROS2_MOTION_MODULE_NAME)
        except RuntimeError:
            pass
    return robot_node, ""


def _trajectory_time_seconds(point) -> float:
    value = point.GetTimeFromStart()
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    seconds = getattr(value, "GetSeconds", None)
    nanoseconds = getattr(value, "GetNanoseconds", None)
    if callable(seconds):
        return float(seconds()) + (float(nanoseconds()) * 1e-9 if callable(nanoseconds) else 0.0)
    return 0.0


def tool_pose_matrices_world_mm(
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    sample_count: int,
):
    """Create right-handed poses whose +Z axis follows Entry-to-Target."""
    import numpy as np
    import vtk

    entry = np.asarray(entry_ras_mm, dtype=float)
    target = np.asarray(target_ras_mm, dtype=float)
    if entry.shape != (3,) or target.shape != (3,) or not np.all(np.isfinite([entry, target])):
        raise ValueError("Entry and Target must be finite 3D RAS points.")
    direction = target - entry
    length = float(np.linalg.norm(direction))
    if length <= 1e-6:
        raise ValueError("Entry and Target must define a non-zero trajectory.")
    z_axis = direction / length
    reference = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(reference, z_axis))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0])
    x_axis = reference - np.dot(reference, z_axis) * z_axis
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    y_axis /= np.linalg.norm(y_axis)
    x_axis = np.cross(y_axis, z_axis)

    matrices = []
    for point in np.linspace(entry, target, max(2, int(sample_count))):
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        for row in range(3):
            matrix.SetElement(row, 0, float(x_axis[row]))
            matrix.SetElement(row, 1, float(y_axis[row]))
            matrix.SetElement(row, 2, float(z_axis[row]))
            matrix.SetElement(row, 3, float(point[row]))
        matrices.append(matrix)
    return matrices


def plan_moveit_cartesian_path(
    *,
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    sample_count: int,
    base_transform,
    avoid_collisions: bool = True,
    minimum_fraction: float = 0.99,
) -> MoveItCartesianResult:
    """Plan a collision-aware TCP path and convert it for Step 6 preview."""
    status = simulation_stack_status()
    if not status.ready:
        return MoveItCartesianResult(False, status.reason or EXTERNAL_STACK_MESSAGE)
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    motion_logic = get_motion_control_logic()
    if robot_node is None or motion_logic is None:
        return MoveItCartesianResult(False, "Connect DENTOBOT Motion Control first.")
    parameter_node = motion_logic.getParameterNode()
    motion_node = None
    try:
        import slicer

        motion_node = slicer.mrmlScene.GetNodeByID(parameter_node.motionControlNodeID)
    except Exception:
        pass
    if motion_node is None:
        return MoveItCartesianResult(False, "MoveIt motion-control node is unavailable.")
    try:
        poses = tool_pose_matrices_world_mm(entry_ras_mm, target_ras_mm, sample_count)
        trajectory = motion_logic.PlanMoveItCartesianTrajectoryFromPoseMarkers(
            motionControlNode=motion_node,
            groupName=ROS2_PLANNING_GROUP,
            poseMarkers=poses,
            relativeToNode=base_transform,
            robotNode=robot_node,
            eefStepMeters=0.001,
            jumpThreshold=0.0,
            avoidCollisions=bool(avoid_collisions),
            velocityScaling=0.2,
            accelerationScaling=0.2,
            planningTimeSec=10.0,
            linkName=ROS2_TOOL_TCP_LINK,
        )
    except Exception as exc:
        return MoveItCartesianResult(False, f"MoveIt Cartesian request failed: {exc}")
    fraction = float(motion_node.GetLastCartesianPathFraction())
    if trajectory is None:
        return MoveItCartesianResult(
            False,
            f"MoveIt returned no Cartesian trajectory (fraction {fraction:.3f}).",
            fraction=fraction,
        )
    if fraction < float(minimum_fraction):
        return MoveItCartesianResult(
            False,
            f"MoveIt planned only {fraction * 100.0:.1f}% of the requested path.",
            fraction=fraction,
        )
    joint_trajectory = trajectory.GetJointTrajectory()
    names = [str(name) for name in joint_trajectory.GetJointNames()]
    missing = [name for name in ROS2_JOINT_SI_ORDER if name not in names]
    if missing:
        return MoveItCartesianResult(False, "MoveIt trajectory omitted: " + ", ".join(missing))
    waypoints: list[dict[str, float]] = []
    times: list[float] = []
    for point in joint_trajectory.GetPoints():
        values = [float(value) for value in point.GetPositions()]
        if len(values) != len(names):
            return MoveItCartesianResult(False, "MoveIt returned a malformed joint point.")
        by_name = dict(zip(names, values))
        waypoints.append({name: by_name[name] for name in ROS2_JOINT_SI_ORDER})
        times.append(_trajectory_time_seconds(point))
    if not waypoints:
        return MoveItCartesianResult(False, "MoveIt returned an empty trajectory.")
    return MoveItCartesianResult(
        True,
        f"MoveIt planned {len(waypoints)} points with Cartesian fraction {fraction:.3f}.",
        fraction=fraction,
        waypoint_joint_vectors_si=tuple(waypoints),
        waypoint_times_sec=tuple(times),
    )


def sync_moveit_obstacle_polydata(
    *,
    source_id: str,
    source_name: str,
    polydata_base_mm,
) -> Tuple[bool, str]:
    """Create/update one hidden base_link-frame collision mesh in MoveIt."""
    try:
        import slicer
    except ImportError:
        return False, ROS2_UNAVAILABLE_MESSAGE
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    motion_logic = get_motion_control_logic()
    if robot_node is None or motion_logic is None:
        return False, "Connect DENTOBOT Motion Control before syncing obstacles."
    if polydata_base_mm is None or polydata_base_mm.GetNumberOfPoints() == 0:
        return False, f"Obstacle {source_name} has no surface points."

    proxy = None
    for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        if (
            node.GetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE) == "true"
            and node.GetAttribute(ROS2_OBSTACLE_SOURCE_ATTRIBUTE) == source_id
        ):
            proxy = node
            break
    if proxy is None:
        proxy = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode", f"[Step 6] MoveIt obstacle - {source_name}"
        )
        proxy.SetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE, "true")
        proxy.SetAttribute(ROS2_OBSTACLE_SOURCE_ATTRIBUTE, source_id)
    proxy.SaveWithSceneOff()
    proxy.SetAndObservePolyData(polydata_base_mm)
    proxy.CreateDefaultDisplayNodes()
    proxy.GetDisplayNode().SetVisibility(False)
    # Do not use AddMoveItObstacle here.  The upstream helper schedules
    # delayed Qt callbacks that retain publisher/robot wrappers for one second;
    # New Case or developer reload can delete those nodes before the callbacks
    # fire.  Tag and publish once synchronously instead.
    proxy.SetAttribute(ROS2_MOTION_CONTROL_OBSTACLE_ATTRIBUTE, "1")
    proxy.SetAttribute(
        ROS2_MOTION_CONTROL_OBSTACLE_FRAME_ATTRIBUTE,
        ROS2_FIXED_FRAME,
    )
    if not motion_logic.PublishMoveItObstacle(proxy, ROS2_FIXED_FRAME, robot_node):
        return False, f"Failed to publish MoveIt obstacle {source_name}."
    mark_slicer_ros2_runtime_nodes_transient()
    return True, ""


def remove_stale_moveit_obstacle_proxies(active_source_ids: set[str]) -> None:
    """Remove collision proxies whose source no longer belongs to Step 6."""
    try:
        import slicer
    except ImportError:
        return
    motion_logic = get_motion_control_logic()
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    for node in list(slicer.util.getNodesByClass("vtkMRMLModelNode")):
        if node.GetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE) != "true":
            continue
        if node.GetAttribute(ROS2_OBSTACLE_SOURCE_ATTRIBUTE) in active_source_ids:
            continue
        if motion_logic is not None:
            motion_logic.RemoveMoveItObstacle(node, robot_node)
        slicer.mrmlScene.RemoveNode(node)


def disconnect_dentobot_motion_control(
    mrml_robot_models: Optional[list] = None,
) -> Tuple[bool, str]:
    try:
        import slicer
    except ImportError:
        return False, ROS2_UNAVAILABLE_MESSAGE
    ros_logic = get_ros2_logic()
    if ros_logic is None:
        return False, ROS2_UNAVAILABLE_MESSAGE
    # The SlicerROS2 robot owns teardown of its associated publisher reference.
    # Stop our timer and release the Python handle, then let RemoveRobot delete it.
    stop_slicer_joint_command_stream(delete_publisher=False)
    motion_logic = get_motion_control_logic()
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    if motion_logic is not None and robot_node is not None:
        for node in list(slicer.util.getNodesByClass("vtkMRMLModelNode")):
            if node.GetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE) != "true":
                continue
            # Publish the removal synchronously.  RemoveMoveItObstacle queues a
            # second callback holding native wrappers, which is unsafe across
            # scene clear or scripted-module replacement.
            try:
                publisher = motion_logic._getCollisionObjectPublisher(
                    robot_node, create=False
                )
                if publisher is not None:
                    publisher.SetFrameId(
                        node.GetAttribute(
                            ROS2_MOTION_CONTROL_OBSTACLE_FRAME_ATTRIBUTE
                        )
                        or ROS2_FIXED_FRAME
                    )
                    publisher.PublishRemove(node)
            except Exception:
                pass
            node.RemoveAttribute(ROS2_MOTION_CONTROL_OBSTACLE_ATTRIBUTE)
            node.RemoveAttribute(ROS2_MOTION_CONTROL_OBSTACLE_FRAME_ATTRIBUTE)
            slicer.mrmlScene.RemoveNode(node)
    if motion_logic is not None:
        # Quiesce the scripted Motion Control widget before emitting the robot
        # NodeAboutToBeRemoved event.  Its callback otherwise performs a
        # second teardown re-entrantly from inside native RemoveRobot.
        try:
            widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
            timer = getattr(widget, "trajectoryTimer", None) if widget else None
            if timer is not None:
                timer.stop()
            if widget is not None:
                widget.exitControlMode()
            motion_logic.removeObserver()
        except Exception:
            pass
        release_dentobot_motion_control_ui()
        motion_subscriber = getattr(motion_logic, "joint_state_subscriber", None)
        motion_subscriber_id = (
            motion_subscriber.GetID() if motion_subscriber is not None else None
        )
        motion_ros_node = getattr(motion_logic, "joint_state_ros2_node", None)
        motion_logic.ClearJointStateSubscriber()
        # Pinned SlicerROS2 removes the subscriber node but can leave the last
        # reference slot on its ROS node.  Remove that null/stale slot before
        # adapter subscriber lookup during scene close.
        _remove_ros2_node_reference(
            motion_ros_node or ros_node,
            "subscriber",
            motion_subscriber_id,
        )
        parameter_node = motion_logic.getParameterNode()
        parameter_node.robotNodeID = ""
        parameter_node.moveGroupExists = False
        parameter_node.planningGroup = ""
        try:
            if widget is not None:
                widget.robot = None
                widget.isRobotLoaded = False
        except Exception:
            pass
    if robot_node is not None:
        ros_logic.RemoveRobot(ROS2_ROBOT_NAME)
    for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode"):
        if node.GetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE) == "true":
            node.RemoveAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE)
    if mrml_robot_models:
        set_mrml_link_models_visible(mrml_robot_models, True)
    return True, "ROS 2 simulation motion control disconnected."


def shutdown_slicer_adapter() -> None:
    """Release adapter-owned MRML pub/sub nodes during tests or scene teardown."""
    global _status_subscriber, _status_observer, _last_status, _last_status_at
    global _joint_status_subscriber, _joint_status_observer
    global _last_joint_status, _last_joint_status_at
    release_dentobot_motion_control_ui()
    stop_slicer_joint_command_stream()
    subscriber = _status_subscriber
    if subscriber is not None and _status_observer is not None:
        try:
            subscriber.RemoveObserver(_status_observer)
        except Exception:
            pass
    ros_logic = get_ros2_logic()
    ros_node = ros_logic.GetDefaultROS2Node() if ros_logic is not None else None
    if ros_node is not None and subscriber is not None:
        subscriber_id = subscriber.GetID()
        try:
            ros_node.RemoveAndDeleteSubscriberNode(ROS2_SIMULATION_STATUS_TOPIC)
        except Exception:
            pass
        finally:
            _remove_ros2_node_reference(ros_node, "subscriber", subscriber_id)
    joint_subscriber = _joint_status_subscriber
    if joint_subscriber is not None and _joint_status_observer is not None:
        try:
            joint_subscriber.RemoveObserver(_joint_status_observer)
        except Exception:
            pass
    if ros_node is not None and joint_subscriber is not None:
        joint_subscriber_id = joint_subscriber.GetID()
        try:
            ros_node.RemoveAndDeleteSubscriberNode(ROS2_JOINT_COMMAND_STATUS_TOPIC)
        except Exception:
            pass
        finally:
            _remove_ros2_node_reference(
                ros_node, "subscriber", joint_subscriber_id
            )
    _status_subscriber = None
    _status_observer = None
    _last_status = SimulationStackStatus(RuntimeState.OFFLINE, reason="No status received.")
    _last_status_at = 0.0
    _joint_status_subscriber = None
    _joint_status_observer = None
    _last_joint_status = None
    _last_joint_status_at = 0.0
